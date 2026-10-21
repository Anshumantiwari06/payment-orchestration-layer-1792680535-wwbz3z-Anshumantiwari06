
import hashlib
import json
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.idempotency_record import IdempotencyRecord


class IdempotencyConflictError(Exception):
    pass


def calculate_request_hash(
    merchant_id: str,
    transaction_id: str,
    amount: Decimal,
    currency: str,
    payment_method: str = "card",
) -> str:
    payload = {
        "merchant_id": merchant_id,
        "transaction_id": transaction_id,
        "amount": str(amount),
        "currency": currency.upper(),
        "payment_method": payment_method.lower(),
    }

    canonical_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def get_idempotency_record(
    db: Session,
    merchant_id: str,
    idempotency_key: str,
) -> IdempotencyRecord | None:
    return db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.merchant_id == merchant_id,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
    )


def validate_existing_request(
    record: IdempotencyRecord,
    request_hash: str,
) -> None:
    if record.request_hash != request_hash:
        raise IdempotencyConflictError(
            "Idempotency key was already used for a different request"
        )
