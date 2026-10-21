
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.models.idempotency_record import IdempotencyRecord
from app.services.idempotency_service import calculate_request_hash
from app.services.transaction_service import authorize_transaction


def test_gateway_exception_marks_idempotency_record_unknown():
    transaction_id = uuid4()

    transaction = Mock()
    transaction.id = transaction_id
    transaction.merchant_id = "merchant_001"
    transaction.amount = Decimal("1250.50")
    transaction.currency = "INR"
    transaction.status = "CREATED"

    request_hash = calculate_request_hash(
        merchant_id="merchant_001",
        transaction_id=str(transaction_id),
        amount=Decimal("1250.50"),
        currency="INR",
    )

    record = IdempotencyRecord(
        merchant_id="merchant_001",
        idempotency_key="order_timeout_001",
        request_hash=request_hash,
        status="IN_PROGRESS",
    )

    db = Mock()
    db.scalar.return_value = transaction

    orchestrator = Mock()
    orchestrator.authorize.side_effect = TimeoutError("Gateway timed out")

    from app.services import transaction_service

    original_get_record = transaction_service.get_idempotency_record
    transaction_service.get_idempotency_record = Mock(
        side_effect=[None, record, record]
    )

    try:
        # First request: gateway timeout must mark the record UNKNOWN.
        with pytest.raises(TimeoutError, match="Gateway timed out"):
            authorize_transaction(
                db=db,
                transaction_id=transaction_id,
                orchestrator=orchestrator,
                idempotency_key="order_timeout_001",
            )

        assert record.status == "UNKNOWN"
        orchestrator.authorize.assert_called_once()
        assert db.commit.call_count >= 2

        # Retry: UNKNOWN outcome must be rejected before calling the gateway again.
        with pytest.raises(
            transaction_service.IdempotencyConflictError,
            match="Payment outcome is unknown",
        ):
            authorize_transaction(
                db=db,
                transaction_id=transaction_id,
                orchestrator=orchestrator,
                idempotency_key="order_timeout_001",
            )

        orchestrator.authorize.assert_called_once()

    finally:
        transaction_service.get_idempotency_record = original_get_record
