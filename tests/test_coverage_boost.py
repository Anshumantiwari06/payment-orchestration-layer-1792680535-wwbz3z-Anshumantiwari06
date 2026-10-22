
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.gateways.circuit_breaker import CircuitBreaker, CircuitState
from app.gateways.schemas import GatewayOutcome
from app.models.idempotency_record import IdempotencyRecord
from app.models.transaction import Transaction
from app.models.webhook_event import WebhookEvent
from app.schemas.transaction import TransactionCreateRequest
from app.services import transaction_service as ts
from app.services import webhook_retry_service as ws
from app.services.idempotency_service import IdempotencyConflictError
from app.state_machine.states import PaymentState


# ---------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------

@pytest.mark.parametrize("threshold", [0, -1, True, 1.5])
def test_circuit_breaker_rejects_invalid_threshold(threshold):
    with pytest.raises(ValueError):
        CircuitBreaker(failure_threshold=threshold)


@pytest.mark.parametrize("timeout", [0, -1])
def test_circuit_breaker_rejects_invalid_timeout(timeout):
    with pytest.raises(ValueError):
        CircuitBreaker(recovery_timeout=timeout)


def test_circuit_opens_at_failure_threshold():
    breaker = CircuitBreaker(failure_threshold=2)
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 1

    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert breaker.allow_request() is False


def test_circuit_allows_only_one_half_open_probe(monkeypatch):
    times = iter([100.0, 105.0])
    monkeypatch.setattr(
        "app.gateways.circuit_breaker.time.monotonic",
        lambda: next(times),
    )
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=5)
    breaker.record_failure()

    assert breaker.state == CircuitState.HALF_OPEN
    assert breaker.allow_request() is True
    assert breaker.allow_request() is False


def test_half_open_probe_failure_reopens_circuit(monkeypatch):
    clock = [10.0]

    monkeypatch.setattr(
        "app.gateways.circuit_breaker.time.monotonic",
        lambda: clock[0],
    )

    breaker = CircuitBreaker(
        failure_threshold=1,
        recovery_timeout=5,
    )

    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    clock[0] = 15.0
    assert breaker.state == CircuitState.HALF_OPEN

    assert breaker.allow_request() is True

    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN


def test_success_resets_circuit():
    breaker = CircuitBreaker(failure_threshold=3)
    breaker.record_failure()
    breaker.record_failure()

    breaker.record_success()

    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0
    assert breaker.allow_request() is True


# ---------------------------------------------------------
# Webhook retry service
# ---------------------------------------------------------

def _event(event_type="payment.authorized", amount=None):
    payload = {} if amount is None else {"amount": str(amount)}
    return SimpleNamespace(
        id=uuid4(),
        event_id="evt-test",
        event_type=event_type,
        payload=payload,
        status="RECEIVED",
        error_message=None,
        attempt_count=1,
        last_attempt_at=None,
        transaction_id=None,
        gateway="razorpay",
        created_at=None,
    )


def _transaction(status="AUTH_INITIATED", amount="100", captured="0", refunded="0"):
    return SimpleNamespace(
        id=uuid4(),
        status=status,
        amount=Decimal(amount),
        captured_amount=Decimal(captured),
        refunded_amount=Decimal(refunded),
    )


def test_webhook_unsupported_event_is_ignored():
    db, event, transaction = Mock(), _event("payment.unknown"), _transaction()

    ws.apply_webhook_event(db, event, transaction)

    assert event.status == "IGNORED"
    assert event.error_message == "Unsupported event type"


def test_webhook_already_at_target_is_idempotent():
    db, event, transaction = Mock(), _event(), _transaction("AUTHORISED")

    ws.apply_webhook_event(db, event, transaction)

    assert event.status == "PROCESSED"
    assert event.error_message is None
    db.add.assert_not_called()


def test_capture_webhook_defaults_to_remaining_amount(monkeypatch):
    db, event = Mock(), _event("payment.captured")
    transaction = _transaction("AUTHORISED", "100", "30")
    monkeypatch.setattr(
        ws, "transition_transaction",
        lambda transaction, new_state, **kwargs:
            SimpleNamespace(new_state=new_state.value),
    )

    ws.apply_webhook_event(db, event, transaction)

    assert transaction.captured_amount == Decimal("100")
    assert event.status == "PROCESSED"
    assert db.add.call_count >= 1


@pytest.mark.parametrize("amount", ["0", "-1", "101"])
def test_capture_webhook_rejects_invalid_amount(amount):
    db, event = Mock(), _event("payment.captured", amount)
    transaction = _transaction("AUTHORISED", "100", "0")

    with pytest.raises(ValueError, match="capture amount"):
        ws.apply_webhook_event(db, event, transaction)


def test_partial_capture_webhook(monkeypatch):
    db, event = Mock(), _event("payment.captured", "40")
    transaction = _transaction("AUTHORISED", "100", "0")
    monkeypatch.setattr(
        ws, "transition_transaction",
        lambda transaction, new_state, **kwargs:
            SimpleNamespace(new_state=new_state.value),
    )

    ws.apply_webhook_event(db, event, transaction)

    assert transaction.captured_amount == Decimal("40")
    assert event.status == "PROCESSED"


def test_refund_webhook_defaults_to_refundable_balance(monkeypatch):
    db, event = Mock(), _event("payment.refunded")
    transaction = _transaction("CAPTURED", "100", "80", "20")
    monkeypatch.setattr(
        ws, "transition_transaction",
        lambda transaction, new_state, **kwargs:
            SimpleNamespace(new_state=new_state.value),
    )

    ws.apply_webhook_event(db, event, transaction)

    assert transaction.refunded_amount == Decimal("80")
    assert event.status == "PROCESSED"


@pytest.mark.parametrize("amount", ["0", "-1", "81"])
def test_refund_webhook_rejects_invalid_amount(amount):
    db, event = Mock(), _event("payment.refunded", amount)
    transaction = _transaction("CAPTURED", "100", "80", "0")

    with pytest.raises(ValueError, match="refund amount"):
        ws.apply_webhook_event(db, event, transaction)


def test_retry_rejects_wrong_status_or_exhausted_attempts():
    db = Mock()
    wrong_status = _event()
    wrong_status.status = "PROCESSED"
    assert ws.process_failed_webhook(db, wrong_status) is False

    exhausted = _event()
    exhausted.status = "FAILED"
    exhausted.attempt_count = 8
    assert ws.process_failed_webhook(db, exhausted) is False


def test_retry_without_transaction_id_is_ignored():
    db, event = Mock(), _event()
    event.status = "FAILED"
    event.transaction_id = None

    assert ws.process_failed_webhook(db, event) is True
    assert event.status == "IGNORED"
    db.commit.assert_called_once()


def test_retry_missing_transaction_returns_false():
    db, event = Mock(), _event()
    event.status = "FAILED"
    event.transaction_id = str(uuid4())
    db.get.return_value = None

    assert ws.process_failed_webhook(db, event) is False
    assert event.status == "FAILED"
    assert event.error_message == "Transaction not found"
    db.commit.assert_called_once()


def test_retry_invalid_uuid_is_caught_and_saved_as_failed():
    db, event = Mock(), _event()
    event.status = "FAILED"
    event.transaction_id = "not-a-uuid"
    db.get.side_effect = [None, event]

    assert ws.process_failed_webhook(db, event) is False
    db.rollback.assert_called_once()
    assert event.status == "FAILED"


def test_retry_batch_empty_result():
    db = Mock()
    db.scalars.return_value.all.return_value = []

    result = ws.retry_batch(db)

    assert result == {
        "selected": 0,
        "processed": 0,
        "failed_or_deferred": 0,
    }


# ---------------------------------------------------------
# Transaction service: idempotency helper and persistence
# ---------------------------------------------------------

def test_existing_completed_idempotency_response_is_returned():
    record = SimpleNamespace(
        status="COMPLETED",
        response_data={
            "transaction_id": "txn-1",
            "status": "AUTHORISED",
            "selected_gateway": "razorpay",
            "gateway_reference": "gw-1",
            "extra": "ignored",},
        request_hash="hash"
        
    )

    result = ts._get_existing_response(record, "hash")

    assert result == {
        "transaction_id": "txn-1",
        "status": "AUTHORISED",
        "selected_gateway": "razorpay",
        "gateway_reference": "gw-1",
    }


@pytest.mark.parametrize(
    "status",
    ["IN_PROGRESS", "UNKNOWN", "UNSUPPORTED"],
)
def test_existing_noncompleted_idempotency_record_conflicts(status):
    record = SimpleNamespace(
        status=status,
        response_data=None,
        request_hash="hash",
    )

    with pytest.raises(IdempotencyConflictError):
        ts._get_existing_response(record, "hash")


@pytest.mark.parametrize(
    "response",
    [None, [], {"transaction_id": "txn-1"}],
)
def test_completed_idempotency_record_with_invalid_response_conflicts(response):
    record = SimpleNamespace(
        status="COMPLETED",
        response_data=response,
        request_hash="hash",
    )

    with pytest.raises(IdempotencyConflictError, match="invalid stored response"):
        ts._get_existing_response(record, "hash")


def test_create_transaction_rolls_back_when_commit_fails():
    db = Mock()
    db.commit.side_effect = RuntimeError("commit failed")
    request = SimpleNamespace(
        merchant_id="merchant-1",
        merchant_order_id="order-1",
        amount=Decimal("25"),
        currency="INR",
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        ts.create_transaction(db, request)

    db.add.assert_called_once()
    db.rollback.assert_called_once()


def test_change_transaction_state_raises_for_missing_transaction():
    db = Mock()
    db.scalar.return_value = None

    with pytest.raises(ValueError, match="was not found"):
        ts.change_transaction_state(
            db, uuid4(), PaymentState.AUTHORISED
        )


def test_change_transaction_state_rolls_back_on_commit_failure(monkeypatch):
    transaction = SimpleNamespace(id=uuid4(), status="CREATED")
    db = Mock()
    db.scalar.return_value = transaction
    db.commit.side_effect = RuntimeError("commit failed")
    monkeypatch.setattr(
        ts, "transition_transaction",
        lambda **kwargs: SimpleNamespace(new_state="AUTHORISED"),
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        ts.change_transaction_state(
            db, transaction.id, PaymentState.AUTHORISED
        )

    db.rollback.assert_called_once()


def test_mark_authorization_unknown_swallows_persistence_error(monkeypatch):
    db = Mock()
    db.scalar.side_effect = RuntimeError("database unavailable")

    # This helper intentionally swallows its own persistence errors.
    ts._mark_authorization_unknown(
        db=db,
        transaction_id=uuid4(),
        merchant_id="merchant-1",
        idempotency_key="key-1",
        reason="uncertain",
        correlation_id=None,
    )

    db.rollback.assert_called_once()
