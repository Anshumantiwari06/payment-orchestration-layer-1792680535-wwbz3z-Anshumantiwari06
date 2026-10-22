
import hashlib
import hmac
import json
import os
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db


SECRET = "test-webhook-secret"


def signed_headers(payload):
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(
        SECRET.encode(),
        raw,
        hashlib.sha256,
    ).hexdigest()
    return raw, {"X-Webhook-Signature": f"sha256={signature}"}


def test_webhook_rejects_invalid_signature():
    db = Mock()
    app.dependency_overrides[get_db] = lambda: db

    try:
        with patch.dict(os.environ, {"RAZORPAY_WEBHOOK_SECRET": SECRET}):
            client = TestClient(app)
            response = client.post(
                "/api/v1/webhooks/razorpay",
                content=b'{"event_id":"evt_1","event_type":"payment.updated"}',
                headers={"X-Webhook-Signature": "invalid"},
            )

        assert response.status_code == 401
        db.add.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_webhook_rejects_request_when_secret_is_missing():
    db = Mock()
    app.dependency_overrides[get_db] = lambda: db

    try:
        with patch.dict(os.environ, {"RAZORPAY_WEBHOOK_SECRET": ""}):
            client = TestClient(app)
            response = client.post(
                "/api/v1/webhooks/razorpay",
                content=b'{"event_id":"evt_2","event_type":"payment.updated"}',
            )

        assert response.status_code == 503
        db.add.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_duplicate_webhook_event_is_ignored():
    db = Mock()
    db.commit.side_effect = Exception("unique constraint violation")
    # The endpoint catches SQLAlchemy IntegrityError specifically.
    from sqlalchemy.exc import IntegrityError
    db.commit.side_effect = IntegrityError("duplicate", {}, Exception())

    app.dependency_overrides[get_db] = lambda: db
    payload = {
        "event_id": "evt_duplicate_1",
        "event_type": "payment.updated",
        "transaction_id": None,
        "status": "UNKNOWN",
    }
    raw, headers = signed_headers(payload)

    try:
        with patch.dict(os.environ, {"RAZORPAY_WEBHOOK_SECRET": SECRET}):
            client = TestClient(app)
            response = client.post(
                "/api/v1/webhooks/razorpay",
                content=raw,
                headers=headers,
            )

        assert response.status_code == 200
        assert response.json()["status"] == "duplicate_ignored"
        assert response.json()["event_id"] == "evt_duplicate_1"
        db.rollback.assert_called_once()
    finally:
        app.dependency_overrides.clear()
def test_retry_webhook_event_not_found():
    db = Mock()
    db.scalar.return_value = None

    app.dependency_overrides[get_db] = lambda: db

    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/webhooks/events/missing-event/retry"
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Webhook event not found"
        db.commit.assert_not_called()
    finally:
        app.dependency_overrides.clear()
def test_retry_webhook_event_rejects_non_retryable_status():
    db = Mock()
    db.scalar.return_value = Mock(
        status="COMPLETED",
        event_id="evt_completed",
    )

    app.dependency_overrides[get_db] = lambda: db

    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/webhooks/events/evt_completed/retry"
        )

        assert response.status_code == 409
        assert "Only FAILED/REJECTED events can be retried" in response.json()["detail"]
        db.commit.assert_not_called()
    finally:
        app.dependency_overrides.clear()