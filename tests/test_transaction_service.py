
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.gateways.schemas import GatewayOutcome
from app.models.transaction import Transaction
from app.services.transaction_service import (
    _get_existing_response,
    authorize_transaction,
)
from app.services.idempotency_service import IdempotencyConflictError
from app.state_machine.states import PaymentState


def test_existing_completed_idempotency_response(monkeypatch):
    record = SimpleNamespace(
        status="COMPLETED",
        response_data={
            "transaction_id": "tx-1",
            "status": "AUTHORISED",
            "selected_gateway": "stripe",
            "gateway_reference": "gw-1",
        },
    )
    monkeypatch.setattr(
        "app.services.transaction_service.validate_existing_request",
        lambda record, request_hash: None,
    )

    result = _get_existing_response(record, "hash")

    assert result["transaction_id"] == "tx-1"
    assert result["status"] == "AUTHORISED"
    assert result["selected_gateway"] == "stripe"


@pytest.mark.parametrize(
    "status",
    ["IN_PROGRESS", "UNKNOWN", "UNSUPPORTED"],
)
def test_existing_non_completed_idempotency_record_rejected(
    monkeypatch, status
):
    record = SimpleNamespace(status=status, response_data=None)
    monkeypatch.setattr(
        "app.services.transaction_service.validate_existing_request",
        lambda record, request_hash: None,
    )

    with pytest.raises(IdempotencyConflictError):
        _get_existing_response(record, "hash")


def test_completed_record_with_invalid_response_rejected(monkeypatch):
    record = SimpleNamespace(status="COMPLETED", response_data={})
    monkeypatch.setattr(
        "app.services.transaction_service.validate_existing_request",
        lambda record, request_hash: None,
    )

    with pytest.raises(IdempotencyConflictError, match="invalid stored response"):
        _get_existing_response(record, "hash")


def test_authorize_missing_transaction_raises():
    db = Mock()
    db.scalar.return_value = None

    with pytest.raises(ValueError, match="was not found"):
        authorize_transaction(
            db, uuid4(), Mock(), "idem-test"
        )



def test_authorize_rejects_non_created_transaction(monkeypatch):
    transaction = Mock()
    transaction.id = uuid4()
    transaction.merchant_id = "merchant-1"
    transaction.amount = 100
    transaction.currency = "INR"
    transaction.status = PaymentState.AUTHORISED.value

    db = Mock()
    db.scalar.return_value = transaction

    monkeypatch.setattr(
        "app.services.transaction_service.get_idempotency_record",
        lambda db, merchant_id, idempotency_key: None,
    )

    with pytest.raises(ValueError, match="Cannot authorize"):
        authorize_transaction(
            db, transaction.id, Mock(), "idem-test"
        )

def test_authorize_successful_gateway_result(monkeypatch):
    transaction = Mock()
    transaction.id = uuid4()
    transaction.merchant_id = "merchant-1"
    transaction.amount = 100
    transaction.currency = "INR"
    transaction.status = PaymentState.CREATED.value

    idempotency_record = Mock()
    idempotency_record.status = "IN_PROGRESS"

    gateway_result = SimpleNamespace(
        outcome=GatewayOutcome.AUTHORISED,
        gateway_name="mock_primary",
        gateway_reference="gw-ref-001",
        message="Authorization successful",
    )

    db = Mock()
    db.scalar.return_value = transaction

    monkeypatch.setattr(
        "app.services.transaction_service.get_idempotency_record",
        lambda db, merchant_id, idempotency_key: None,
    )

    # Return the reserved record when the service checks again after gateway authorization.
    calls = iter([None, idempotency_record])
    monkeypatch.setattr(
        "app.services.transaction_service.get_idempotency_record",
        lambda db, merchant_id, idempotency_key: next(calls),
    )

    orchestrator = Mock()
    orchestrator.authorize.return_value = gateway_result

    result = authorize_transaction(
        db,
        transaction.id,
        orchestrator,
        "idem-success",
    )

    assert result is transaction
    assert transaction.selected_gateway == "mock_primary"
    assert transaction.gateway_reference == "gw-ref-001"
    assert idempotency_record.status == "COMPLETED"
    assert idempotency_record.response_data["status"] == PaymentState.AUTHORISED.value
    orchestrator.authorize.assert_called_once()
    db.commit.assert_called()
    db.refresh.assert_called_once_with(transaction)
def test_authorize_declined_gateway_result(monkeypatch):
    transaction = Mock()
    transaction.id = uuid4()
    transaction.merchant_id = "merchant-1"
    transaction.amount = 100
    transaction.currency = "INR"
    transaction.status = PaymentState.CREATED.value

    idempotency_record = Mock()
    idempotency_record.status = "IN_PROGRESS"

    gateway_result = SimpleNamespace(
        outcome=GatewayOutcome.DECLINED,
        gateway_name="mock_primary",
        gateway_reference="gw-declined-001",
        message="Payment declined",
    )

    db = Mock()
    db.scalar.return_value = transaction

    calls = iter([None, idempotency_record])
    monkeypatch.setattr(
        "app.services.transaction_service.get_idempotency_record",
        lambda db, merchant_id, idempotency_key: next(calls),
    )

    orchestrator = Mock()
    orchestrator.authorize.return_value = gateway_result

    result = authorize_transaction(
        db,
        transaction.id,
        orchestrator,
        "idem-declined",
    )

    assert result is transaction
    assert transaction.status == PaymentState.AUTH_FAILED.value
    assert transaction.selected_gateway == "mock_primary"
    assert idempotency_record.status == "COMPLETED"
    assert idempotency_record.response_data["status"] == PaymentState.AUTH_FAILED.value
    orchestrator.authorize.assert_called_once()
    db.commit.assert_called()

def test_authorize_returns_existing_idempotent_response(monkeypatch):
    transaction = Mock()
    transaction.id = uuid4()
    transaction.merchant_id = "merchant-1"
    transaction.amount = 100
    transaction.currency = "INR"

    record = SimpleNamespace(
        status="COMPLETED",
        response_data={
            "transaction_id": str(transaction.id),
            "status": "AUTHORISED",
            "selected_gateway": "stripe",
            "gateway_reference": "gw-1",
        },
    )

    db = Mock()
    db.scalar.return_value = transaction

    monkeypatch.setattr(
        "app.services.transaction_service.calculate_request_hash",
        lambda **kwargs: "same-hash",
    )
    monkeypatch.setattr(
        "app.services.transaction_service.get_idempotency_record",
        lambda *args: record,
    )
    monkeypatch.setattr(
        "app.services.transaction_service.validate_existing_request",
        lambda *args: None,
    )

    orchestrator = Mock()
    result = authorize_transaction(
        db, transaction.id, orchestrator, "idem-replay"
    )

    assert result["status"] == "AUTHORISED"
    assert result["gateway_reference"] == "gw-1"
    orchestrator.authorize.assert_not_called()
    db.commit.assert_not_called()


def test_authorize_gateway_exception_marks_outcome_unknown(monkeypatch):
    transaction = Mock()
    transaction.id = uuid4()
    transaction.merchant_id = "merchant-1"
    transaction.amount = 100
    transaction.currency = "INR"
    transaction.status = PaymentState.CREATED.value

    record = Mock()
    record.status = "IN_PROGRESS"
    calls = iter([None, record])

    db = Mock()
    db.scalar.return_value = transaction

    monkeypatch.setattr(
        "app.services.transaction_service.get_idempotency_record",
        lambda *args: next(calls),
    )

    def fake_transition(transaction, new_state, reason, correlation_id):
        transaction.status = new_state.value
        return Mock()

    monkeypatch.setattr(
        "app.services.transaction_service.transition_transaction",
        fake_transition,
    )

    orchestrator = Mock()
    orchestrator.authorize.side_effect = RuntimeError("gateway timeout")

    with pytest.raises(RuntimeError, match="gateway timeout"):
        authorize_transaction(
            db, transaction.id, orchestrator, "idem-timeout"
        )

    assert transaction.status == PaymentState.AUTH_UNKNOWN.value
    assert record.status == "UNKNOWN"
    db.rollback.assert_not_called()  # The service's uncertainty handler commits if possible.
    db.commit.assert_called()


def test_authorize_initial_database_commit_failure_rolls_back(monkeypatch):
    transaction = Mock()
    transaction.id = uuid4()
    transaction.merchant_id = "merchant-1"
    transaction.amount = 100
    transaction.currency = "INR"
    transaction.status = PaymentState.CREATED.value

    db = Mock()
    db.scalar.return_value = transaction
    db.commit.side_effect = RuntimeError("database unavailable")

    monkeypatch.setattr(
        "app.services.transaction_service.get_idempotency_record",
        lambda *args: None,
    )

    def fake_transition(transaction, new_state, reason, correlation_id):
        transaction.status = new_state.value
        return Mock()

    monkeypatch.setattr(
        "app.services.transaction_service.transition_transaction",
        fake_transition,
    )

    orchestrator = Mock()

    with pytest.raises(RuntimeError, match="database unavailable"):
        authorize_transaction(
            db, transaction.id, orchestrator, "idem-db-failure"
        )

    db.rollback.assert_called_once()
    orchestrator.authorize.assert_not_called()
