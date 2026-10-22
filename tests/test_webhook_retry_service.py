
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.services.webhook_retry_service import (
    apply_webhook_event,
    process_failed_webhook,
    retry_batch,
)
from app.state_machine.states import PaymentState


def make_transaction(status=PaymentState.AUTHORISED.value):
    transaction = Mock()
    transaction.id = uuid4()
    transaction.status = status
    transaction.amount = 100
    transaction.captured_amount = 0
    transaction.refunded_amount = 0
    return transaction


def make_event(event_type="payment.captured", amount=None):
    event = Mock()
    event.id = uuid4()
    event.event_id = "evt_test_001"
    event.event_type = event_type
    event.status = "RECEIVED"
    event.error_message = None
    event.transaction_id = None
    event.attempt_count = 1
    event.last_attempt_at = None
    event.payload = {"amount": amount} if amount is not None else {}
    return event


def test_unsupported_event_is_ignored():
    db = Mock()
    event = make_event("payment.unknown")
    transaction = make_transaction()

    apply_webhook_event(db, event, transaction)

    assert event.status == "IGNORED"
    assert event.error_message == "Unsupported event type"
    db.add.assert_not_called()


def test_already_applied_event_is_processed_idempotently():
    db = Mock()
    event = make_event("payment.authorized")
    transaction = make_transaction(PaymentState.AUTHORISED.value)

    apply_webhook_event(db, event, transaction)

    assert event.status == "PROCESSED"
    db.add.assert_not_called()


@pytest.mark.parametrize(
    "amount",
    ["0", "-1", "101"],
)
def test_invalid_capture_amount_is_rejected(amount):
    db = Mock()
    event = make_event("payment.captured", amount)
    transaction = make_transaction()

    with pytest.raises(ValueError, match="capture amount"):
        apply_webhook_event(db, event, transaction)


def test_partial_capture_updates_captured_amount():
    db = Mock()
    event = make_event("payment.captured", "40")
    transaction = make_transaction()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "app.services.webhook_retry_service.transition_transaction",
            lambda transaction, new_state, **kwargs: Mock(),
        )
        apply_webhook_event(db, event, transaction)

    assert transaction.captured_amount == 40
    assert event.status == "PROCESSED"
    assert db.add.call_count == 2


def test_retry_stops_when_attempt_limit_reached():
    db = Mock()
    event = make_event()
    event.status = "FAILED"
    event.attempt_count = 8

    assert process_failed_webhook(db, event, max_attempts=8) is False
    db.commit.assert_not_called()


def test_retry_without_transaction_id_is_ignored():
    db = Mock()
    event = make_event()
    event.status = "FAILED"
    event.transaction_id = None

    result = process_failed_webhook(db, event)

    assert result is True
    assert event.status == "IGNORED"
    db.commit.assert_called_once()


def test_retry_missing_transaction_stays_failed():
    db = Mock()
    event = make_event()
    event.status = "FAILED"
    event.transaction_id = str(uuid4())
    db.get.return_value = None

    result = process_failed_webhook(db, event)

    assert result is False
    assert event.status == "FAILED"
    db.commit.assert_called_once()


def test_retry_batch_reports_empty_batch():
    db = Mock()
    db.scalars.return_value.all.return_value = []

    result = retry_batch(db)

    assert result == {
        "selected": 0,
        "processed": 0,
        "failed_or_deferred": 0,
    }
