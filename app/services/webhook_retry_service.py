"""Idempotent application and bounded retry for persisted webhook events."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.webhook_event import WebhookEvent
from app.models.transaction import Transaction
from app.state_machine.engine import transition_transaction
from app.state_machine.states import PaymentState
from app.state_machine.transitions import ALLOWED_TRANSITIONS

EVENT_STATES = {
    "payment.authorized": PaymentState.AUTHORISED,
    "payment.captured": PaymentState.CAPTURED,
    "payment.failed": PaymentState.AUTH_FAILED,
    "payment.refunded": PaymentState.REFUNDED,
    "payment.voided": PaymentState.VOIDED,
    "payment.expired": PaymentState.AUTH_EXPIRED,
}
INTERMEDIATE_STATES = {
    PaymentState.CAPTURED: PaymentState.CAPTURE_INITIATED,
    PaymentState.REFUNDED: PaymentState.REFUND_INITIATED,
    PaymentState.VOIDED: PaymentState.VOID_INITIATED,
}

def apply_webhook_event(db: Session, event: WebhookEvent, transaction: Transaction) -> None:
    target = EVENT_STATES.get(event.event_type)
    if target is None:
        event.status = "IGNORED"
        event.error_message = "Unsupported event type"
        return
    if transaction.status == target.value:
        event.status = "PROCESSED"
        event.error_message = None
        return
    amount_value = event.payload.get("amount") if event.payload else None
    amount = Decimal(str(amount_value)) if amount_value is not None else None
    if target == PaymentState.CAPTURED:
        if amount is None:
            amount = Decimal(transaction.amount) - Decimal(transaction.captured_amount or 0)
        if amount <= 0 or Decimal(transaction.captured_amount or 0) + amount > Decimal(transaction.amount):
            raise ValueError("Webhook capture amount exceeds remaining authorized amount")
        transaction.captured_amount = Decimal(transaction.captured_amount or 0) + amount
        if transaction.captured_amount < transaction.amount:
            target = PaymentState.PARTIALLY_CAPTURED
    elif target == PaymentState.REFUNDED:
        captured = Decimal(transaction.captured_amount or 0)
        refunded = Decimal(transaction.refunded_amount or 0)
        if amount is None:
            amount = captured - refunded
        if amount <= 0 or refunded + amount > captured:
            raise ValueError("Webhook refund amount exceeds refundable balance")
        transaction.refunded_amount = refunded + amount
        if transaction.refunded_amount < captured:
            target = PaymentState.PARTIALLY_REFUNDED
    intermediate = {
        "payment.captured": PaymentState.CAPTURE_INITIATED,
        "payment.refunded": PaymentState.REFUND_INITIATED,
        "payment.voided": PaymentState.VOID_INITIATED,
    }.get(event.event_type)
    if intermediate and transaction.status != intermediate.value:
        current = PaymentState(transaction.status)
        if intermediate in ALLOWED_TRANSITIONS.get(current, set()):
            db.add(transition_transaction(transaction, intermediate, reason=f"Webhook {event.event_type} received", correlation_id=event.event_id))
    db.add(transition_transaction(transaction, target, reason=f"Webhook {event.event_type}", correlation_id=event.event_id))
    event.status = "PROCESSED"
    event.error_message = None

def process_failed_webhook(db: Session, event: WebhookEvent, max_attempts: int = 8) -> bool:
    if event.status not in {"FAILED", "REJECTED"} or (event.attempt_count or 0) >= max_attempts:
        return False
    event.attempt_count = (event.attempt_count or 0) + 1
    event.last_attempt_at = datetime.now(timezone.utc)
    try:
        if not event.transaction_id:
            event.status = "IGNORED"
            event.error_message = "No transaction_id supplied; event cannot be applied"
            db.commit()
            return True
        transaction = db.get(Transaction, UUID(event.transaction_id))
        if transaction is None:
            event.status = "FAILED"
            event.error_message = "Transaction not found"
            db.commit()
            return False
        apply_webhook_event(db, event, transaction)
        db.commit()
        return event.status in {"PROCESSED", "IGNORED"}
    except Exception as exc:
        db.rollback()
        saved = db.get(WebhookEvent, event.id)
        if saved:
            saved.status = "FAILED"
            saved.error_message = str(exc)[:1000]
            saved.last_attempt_at = datetime.now(timezone.utc)
            db.commit()
        return False

def retry_batch(db: Session, batch_size: int = 100, max_attempts: int = 8) -> dict:
    events = db.scalars(select(WebhookEvent).where(
        WebhookEvent.status.in_(["FAILED", "REJECTED"]),
        WebhookEvent.attempt_count < max_attempts,
    ).order_by(WebhookEvent.created_at).limit(batch_size).with_for_update(skip_locked=True)).all()
    processed = sum(1 for event in events if process_failed_webhook(db, event, max_attempts))
    return {"selected": len(events), "processed": processed, "failed_or_deferred": len(events) - processed}
