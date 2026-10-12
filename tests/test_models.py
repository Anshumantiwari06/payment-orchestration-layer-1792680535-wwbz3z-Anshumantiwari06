
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import Numeric
from app.models.idempotency_record import IdempotencyRecord
from app.db.base import Base
from app.models.transaction import Transaction
from app.models.transaction_state_log import TransactionStateLog
from app.state_machine.engine import (
    InvalidTransitionError,
    transition_transaction,
)
from app.state_machine.states import PaymentState


def test_models_are_registered_in_metadata():
    assert "transactions" in Base.metadata.tables
    assert "transaction_state_log" in Base.metadata.tables


def test_transaction_amount_uses_numeric_precision():
    amount_column = Transaction.__table__.c.amount
    assert isinstance(amount_column.type, Numeric)
    assert amount_column.type.precision == 15
    assert amount_column.type.scale == 2

    amount = Decimal("1250.50")
    assert amount == Decimal("1250.50")


def test_transaction_primary_key_uses_uuid():
    id_column = Transaction.__table__.c.id

    assert id_column.primary_key is True
    assert id_column.type.as_uuid is True


def test_state_log_has_transaction_foreign_key():
    transaction_id_column = TransactionStateLog.__table__.c.transaction_id

    foreign_keys = list(transaction_id_column.foreign_keys)

    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "transactions.id"


def test_required_transaction_fields_are_not_nullable():
    required_fields = [
        "merchant_id",
        "merchant_order_id",
        "amount",
        "currency",
        "status",
        "version",
    ]

    for field in required_fields:
        assert Transaction.__table__.c[field].nullable is False


def test_valid_transition_updates_status_and_creates_log():
    transaction = Transaction(
        id=uuid.uuid4(),
        status=PaymentState.CREATED.value,
    )

    state_log = transition_transaction(
        transaction,
        PaymentState.ROUTE_SELECTED,
        reason="Gateway selected",
        correlation_id="test-request-001",
    )

    assert transaction.status == PaymentState.ROUTE_SELECTED.value
    assert state_log.transaction_id == transaction.id
    assert state_log.previous_state == PaymentState.CREATED.value
    assert state_log.new_state == PaymentState.ROUTE_SELECTED.value
    assert state_log.event_type == "STATE_TRANSITION"
    assert state_log.reason == "Gateway selected"
    assert state_log.correlation_id == "test-request-001"


def test_invalid_transition_does_not_change_status():
    transaction = Transaction(
        id=uuid.uuid4(),
        status=PaymentState.CREATED.value,
    )

    with pytest.raises(InvalidTransitionError):
        transition_transaction(
            transaction,
            PaymentState.CAPTURED,
        )

    assert transaction.status == PaymentState.CREATED.value

def test_confirmed_authorization_failure_can_return_to_routing():
    from app.state_machine.engine import transition

    result = transition(
        PaymentState.AUTH_FAILED,
        PaymentState.ROUTE_SELECTED,
    )

    assert result == PaymentState.ROUTE_SELECTED
def test_idempotency_record_is_registered_in_metadata():
    assert "idempotency_records" in Base.metadata.tables