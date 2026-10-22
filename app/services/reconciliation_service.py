
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.gateways.base import PaymentGateway
from app.gateways.schemas import GatewayOutcome
from app.models.transaction import Transaction
from app.state_machine.engine import transition_transaction
from app.state_machine.states import PaymentState


def reconcile_transaction(
    db: Session,
    transaction_id: UUID,
    gateways: list[PaymentGateway],
    correlation_id: str | None = None,
) -> Transaction:
    transaction = db.scalar(
        select(Transaction).where(
            Transaction.id == transaction_id
        )
    )

    if transaction is None:
        raise ValueError(
            f"Transaction {transaction_id} was not found"
        )

    if transaction.status != PaymentState.AUTH_UNKNOWN.value:
        raise ValueError(
            "Only AUTH_UNKNOWN transactions can be reconciled"
        )

    if not transaction.selected_gateway:
        raise ValueError(
            "Cannot reconcile without the original gateway"
        )

    if not transaction.gateway_reference:
        raise ValueError(
            "Cannot reconcile without a gateway reference"
        )

    gateway = next(
        (
            item
            for item in gateways
            if item.name == transaction.selected_gateway
        ),
        None,
    )

    if gateway is None:
        raise ValueError(
            "The original gateway is not configured"
        )

    try:
        result = gateway.get_status(
            gateway_reference=transaction.gateway_reference
        )
    except Exception:
        # A failed status lookup does not prove payment failure.
        db.refresh(transaction)
        return transaction

    if result.outcome == GatewayOutcome.UNKNOWN:
        return transaction

    if result.outcome == GatewayOutcome.AUTHORISED:
        new_state = PaymentState.AUTHORISED
    elif result.outcome == GatewayOutcome.DECLINED:
        new_state = PaymentState.AUTH_FAILED
    else:
        return transaction

    try:
        state_log = transition_transaction(
            transaction=transaction,
            new_state=new_state,
            reason=(
                f"Reconciliation confirmed gateway outcome: "
                f"{result.outcome.value}"
            ),
            correlation_id=correlation_id,
        )
        db.add(state_log)
        db.commit()
        db.refresh(transaction)
    except Exception:
        db.rollback()
        raise

    return transaction
