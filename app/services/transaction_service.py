
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.schemas.transaction import TransactionCreateRequest
from app.models.transaction import Transaction
from app.state_machine.engine import transition_transaction
from app.state_machine.states import PaymentState
from app.gateways.orchestrator import PaymentOrchestrator
from app.gateways.schemas import GatewayOutcome

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
        raise ValueError(
            f"Transaction {transaction_id} was not found"
        )

    if transaction.status != PaymentState.CREATED.value:
        raise ValueError(
            f"Cannot authorize transaction in state {transaction.status}"
        )

    try:
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
        elif result.outcome == GatewayOutcome.DECLINED:
            final_state = PaymentState.AUTH_FAILED
        else:
            final_state = PaymentState.AUTH_UNKNOWN

        state_log = transition_transaction(
            transaction,
            final_state,
            reason=result.message,
            correlation_id=correlation_id,
        )
        db.add(state_log)

        db.commit()
        db.refresh(transaction)

    except Exception:
        db.rollback()
        raise

    return transaction
