from app.models.transaction_state_log import TransactionStateLog
from app.state_machine.states import PaymentState
from app.state_machine.transitions import ALLOWED_TRANSITIONS


class InvalidTransitionError(Exception):
    """Raised when a payment state transition is not allowed."""


def transition(
    current_state: PaymentState,
    new_state: PaymentState,
) -> PaymentState:
    allowed_states = ALLOWED_TRANSITIONS.get(current_state, set())

    if new_state not in allowed_states:
        raise InvalidTransitionError(
            f"Cannot transition from {current_state} to {new_state}"
        )

    return new_state

def transition_transaction(
    transaction,
    new_state: PaymentState,
    reason: str | None = None,
    correlation_id: str | None = None,
) -> TransactionStateLog:
    current_state = PaymentState(transaction.status)

    transition(current_state, new_state)

    state_log = TransactionStateLog(
        transaction_id=transaction.id,
        previous_state=current_state.value,
        new_state=new_state.value,
        event_type="STATE_TRANSITION",
        reason=reason,
        correlation_id=correlation_id,
    )

    transaction.status = new_state.value

    return state_log