
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.gateways.schemas import GatewayOutcome
from app.services.reconciliation_service import reconcile_transaction
from app.state_machine.states import PaymentState


def make_transaction(status=PaymentState.AUTH_UNKNOWN.value):
    transaction = Mock()
    transaction.id = uuid4()
    transaction.status = status
    transaction.selected_gateway = "razorpay"
    transaction.gateway_reference = "gateway-ref-001"
    return transaction


def make_gateway(outcome=GatewayOutcome.AUTHORISED):
    gateway = Mock()
    gateway.name = "razorpay"
    gateway.get_status.return_value = Mock(outcome=outcome)
    return gateway


def test_reconcile_authorised_payment():
    db = Mock()
    transaction = make_transaction()
    db.scalar.return_value = transaction
    gateway = make_gateway(GatewayOutcome.AUTHORISED)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "app.services.reconciliation_service.transition_transaction",
            lambda **kwargs: Mock(),
        )
        result = reconcile_transaction(
            db, transaction.id, [gateway], "corr-001"
        )

    assert result is transaction
    db.add.assert_called_once()
    db.commit.assert_called_once()
    gateway.get_status.assert_called_once_with(
        gateway_reference="gateway-ref-001"
    )


def test_reconcile_declined_payment():
    db = Mock()
    transaction = make_transaction()
    db.scalar.return_value = transaction
    gateway = make_gateway(GatewayOutcome.DECLINED)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "app.services.reconciliation_service.transition_transaction",
            lambda **kwargs: Mock(),
        )
        reconcile_transaction(db, transaction.id, [gateway])

    db.add.assert_called_once()
    db.commit.assert_called_once()


@pytest.mark.parametrize(
    "outcome",
    [GatewayOutcome.UNKNOWN, GatewayOutcome.PARTIALLY_CAPTURED],
)
def test_reconcile_nonfinal_gateway_outcome_does_not_transition(outcome):
    db = Mock()
    transaction = make_transaction()
    db.scalar.return_value = transaction
    gateway = make_gateway(outcome)

    result = reconcile_transaction(db, transaction.id, [gateway])

    assert result is transaction
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_gateway_status_exception_refreshes_transaction():
    db = Mock()
    transaction = make_transaction()
    db.scalar.return_value = transaction
    gateway = make_gateway()
    gateway.get_status.side_effect = TimeoutError("gateway timeout")

    result = reconcile_transaction(db, transaction.id, [gateway])

    assert result is transaction
    db.refresh.assert_called_once_with(transaction)
    db.commit.assert_not_called()


def test_missing_transaction_raises():
    db = Mock()
    db.scalar.return_value = None

    with pytest.raises(ValueError, match="was not found"):
        reconcile_transaction(db, uuid4(), [make_gateway()])


@pytest.mark.parametrize(
    ("attribute", "value", "message"),
    [
        ("status", PaymentState.CREATED.value, "Only AUTH_UNKNOWN"),
        ("selected_gateway", None, "without the original gateway"),
        ("gateway_reference", None, "without a gateway reference"),
    ],
)
def test_invalid_transaction_cannot_be_reconciled(attribute, value, message):
    db = Mock()
    transaction = make_transaction()
    setattr(transaction, attribute, value)
    db.scalar.return_value = transaction

    with pytest.raises(ValueError, match=message):
        reconcile_transaction(db, transaction.id, [make_gateway()])


def test_original_gateway_not_configured():
    db = Mock()
    transaction = make_transaction()
    db.scalar.return_value = transaction
    other_gateway = Mock()
    other_gateway.name = "stripe"

    with pytest.raises(ValueError, match="not configured"):
        reconcile_transaction(db, transaction.id, [other_gateway])


def test_state_transition_failure_rolls_back():
    db = Mock()
    transaction = make_transaction()
    db.scalar.return_value = transaction
    gateway = make_gateway()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "app.services.reconciliation_service.transition_transaction",
            Mock(side_effect=RuntimeError("transition failed")),
        )

        with pytest.raises(RuntimeError, match="transition failed"):
            reconcile_transaction(db, transaction.id, [gateway])

    db.rollback.assert_called_once()
