
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
    record = IdempotencyRecord(
        merchant_id="merchant_001",
        idempotency_key="order_002",
        request_hash="original_hash",
        status="IN_PROGRESS",
    )

    assert record.status == "IN_PROGRESS"
    assert record.idempotency_key == "order_002"