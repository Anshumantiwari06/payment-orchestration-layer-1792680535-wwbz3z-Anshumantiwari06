import pytest

from app.state_machine.engine import InvalidTransitionError, transition
from app.state_machine.states import PaymentState
from app.state_machine.transitions import ALLOWED_TRANSITIONS

VALID_EDGES = [(current, target) for current, targets in ALLOWED_TRANSITIONS.items() for target in targets]
ALL_EDGES = [(current, target) for current in PaymentState for target in PaymentState]
INVALID_EDGES = [(current, target) for current, target in ALL_EDGES
                 if target not in ALLOWED_TRANSITIONS.get(current, set()) and current != target][:15]

@pytest.mark.parametrize("current,target", VALID_EDGES)
def test_every_declared_valid_transition_is_accepted(current, target):
    assert transition(current, target) == target

@pytest.mark.parametrize("current,target", INVALID_EDGES)
def test_fifteen_invalid_transitions_are_rejected(current, target):
    with pytest.raises(InvalidTransitionError):
        transition(current, target)
