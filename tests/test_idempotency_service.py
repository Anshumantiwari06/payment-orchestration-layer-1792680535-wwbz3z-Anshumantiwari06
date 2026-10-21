
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.idempotency_record import IdempotencyRecord
from app.services.idempotency_service import (
    IdempotencyConflictError,
    calculate_request_hash,
    validate_existing_request,
)


def test_same_request_produces_same_hash():
    transaction_id = str(uuid4())

    first = calculate_request_hash(
        "merchant_001",
        transaction_id,
        Decimal("1250.50"),
        "INR",
    )
    second = calculate_request_hash(
        "merchant_001",
        transaction_id,
        Decimal("1250.50"),
        "INR",
    )

    assert first == second


def test_currency_case_does_not_change_hash():
    transaction_id = str(uuid4())

    first = calculate_request_hash(
        "merchant_001",
        transaction_id,
        Decimal("1250.50"),
        "INR",
    )
    second = calculate_request_hash(
        "merchant_001",
        transaction_id,
        Decimal("1250.50"),
        "inr",
    )

    assert first == second


def test_different_amount_produces_different_hash():
    transaction_id = str(uuid4())

    first = calculate_request_hash(
        "merchant_001",
        transaction_id,
        Decimal("1250.50"),
        "INR",
    )
    second = calculate_request_hash(
        "merchant_001",
        transaction_id,
        Decimal("1500.00"),
        "INR",
    )

    assert first != second


def test_reusing_key_with_different_request_is_rejected():
    record = IdempotencyRecord(
        merchant_id="merchant_001",
        idempotency_key="order_001",
        request_hash="original_hash",
        status="COMPLETED",
    )

    with pytest.raises(IdempotencyConflictError):
        validate_existing_request(record, "different_hash")
def test_in_progress_record_rejects_reused_key():
    from unittest.mock import Mock

    from app.services.transaction_service import authorize_transaction

    transaction_id = uuid4()

    transaction = Mock()
    transaction.id = transaction_id
    transaction.merchant_id = "merchant_001"
    transaction.amount = Decimal("1250.50")
    transaction.currency = "INR"
    transaction.status = "CREATED"

    record = IdempotencyRecord(
        merchant_id="merchant_001",
        idempotency_key="order_002",
        request_hash=calculate_request_hash(
            "merchant_001",
            str(transaction_id),
            Decimal("1250.50"),
            "INR",
        ),
        status="IN_PROGRESS",
    )

    db = Mock()
    db.scalar.return_value = transaction

    from app.services import transaction_service

    original_get_record = transaction_service.get_idempotency_record
    transaction_service.get_idempotency_record = Mock(return_value=record)

    orchestrator = Mock()

    try:
        with pytest.raises(
            IdempotencyConflictError,
            match="already being processed",
        ):
            authorize_transaction(
                db=db,
                transaction_id=transaction_id,
                orchestrator=orchestrator,
                idempotency_key="order_002",
            )

        orchestrator.authorize.assert_not_called()
        db.add.assert_not_called()
        db.commit.assert_not_called()
    finally:
        transaction_service.get_idempotency_record = original_get_record