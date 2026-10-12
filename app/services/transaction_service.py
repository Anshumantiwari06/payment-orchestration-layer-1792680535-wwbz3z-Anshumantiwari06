
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.schemas.transaction import TransactionCreateRequest
from app.models.transaction import Transaction
from app.state_machine.engine import transition_transaction
from app.state_machine.states import PaymentState
from app.gateways.orchestrator import PaymentOrchestrator
from app.gateways.schemas import GatewayOutcome
from app.models.idempotency_record import IdempotencyRecord
from app.services.idempotency_service import (
    IdempotencyConflictError,
    calculate_request_hash,
    get_idempotency_record,
    validate_existing_request,
)
def change_transaction_state(
    db: Session,
    transaction_id: UUID,
    new_state: PaymentState,
    reason: str | None = None,
    correlation_id: str | None = None,
) -> Transaction:
    transaction = db.scalar(
        select(Transaction).where(Transaction.id == transaction_id)
    )

    if transaction is None:
        raise ValueError(
            f"Transaction {transaction_id} was not found"
        )

    state_log = transition_transaction(
        transaction=transaction,
        new_state=new_state,
        reason=reason,
        correlation_id=correlation_id,
    )

    db.add(state_log)

    try:
        db.commit()
        db.refresh(transaction)
    except Exception:
        db.rollback()
        raise

    return transaction

def create_transaction(
    db: Session,
    request: TransactionCreateRequest,
) -> Transaction:
    transaction = Transaction(
        merchant_id=request.merchant_id,
        merchant_order_id=request.merchant_order_id,
        amount=request.amount,
        currency=request.currency,
        status=PaymentState.CREATED.value,
    )

    db.add(transaction)

    try:
        db.commit()
        db.refresh(transaction)
    except Exception:
        db.rollback()
        raise

    return transaction



def authorize_transaction(
    db: Session,
    transaction_id: UUID,
    orchestrator: PaymentOrchestrator,
    idempotency_key: str,
    correlation_id: str | None = None,
) -> Transaction:
    transaction = db.scalar(
        select(Transaction).where(Transaction.id == transaction_id)
    )
    if transaction is None:
        raise ValueError(f"Transaction {transaction_id} was not found")

    request_hash = calculate_request_hash(
        merchant_id=transaction.merchant_id,
        transaction_id=str(transaction.id),
        amount=transaction.amount,
        currency=transaction.currency,
    )

    record = get_idempotency_record(
        db,
        transaction.merchant_id,
        idempotency_key,
    )

    if record is not None:
        validate_existing_request(record, request_hash)

        if record.status == "COMPLETED":
            return transaction

        if record.status == "IN_PROGRESS":
            raise IdempotencyConflictError(
                "This payment request is already being processed"
            )

        if record.status == "UNKNOWN":
            raise IdempotencyConflictError(
                "Payment outcome is unknown; reconciliation is required"
            )

    if transaction.status != PaymentState.CREATED.value:
        raise ValueError(
            f"Cannot authorize transaction in state {transaction.status}"
        )

    record = IdempotencyRecord(
        merchant_id=transaction.merchant_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        status="IN_PROGRESS",
    )

    try:
        db.add(record)
        db.flush()

        route_log = transition_transaction(
            transaction,
            PaymentState.ROUTE_SELECTED,
            reason="Gateway routing started",
            correlation_id=correlation_id,
        )
        db.add(route_log)
        db.flush()

        auth_log = transition_transaction(
            transaction,
            PaymentState.AUTH_INITIATED,
            reason="Authorization attempt started",
            correlation_id=correlation_id,
        )
        db.add(auth_log)
        db.flush()

        result = orchestrator.authorize(
            amount=transaction.amount,
            currency=transaction.currency,
            idempotency_key=idempotency_key,
        )

        transaction.selected_gateway = result.gateway_name
        transaction.gateway_reference = result.gateway_reference

        if result.outcome == GatewayOutcome.AUTHORISED:
            final_state = PaymentState.AUTHORISED
            record.status = "COMPLETED"
        elif result.outcome == GatewayOutcome.DECLINED:
            final_state = PaymentState.AUTH_FAILED
            record.status = "COMPLETED"
        else:
            final_state = PaymentState.AUTH_UNKNOWN
            record.status = "UNKNOWN"

        state_log = transition_transaction(
            transaction,
            final_state,
            reason=result.message,
            correlation_id=correlation_id,
        )
        db.add(state_log)

        record.response_data = {
            "transaction_id": str(transaction.id),
            "status": transaction.status,
            "selected_gateway": transaction.selected_gateway,
            "gateway_reference": transaction.gateway_reference,
        }

        db.commit()
        db.refresh(transaction)

    except Exception:
        db.rollback()
        raise

    return transaction
