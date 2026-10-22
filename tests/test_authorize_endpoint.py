
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.services.idempotency_service import calculate_request_hash


def test_completed_idempotency_replay_returns_stored_response():
    transaction_id = uuid4()

    transaction = Mock()
    transaction.id = transaction_id
    transaction.merchant_id = "merchant_001"
    transaction.amount = 1250.50
    transaction.currency = "INR"
    transaction.status = "CREATED"

    request_hash = calculate_request_hash(
        merchant_id="merchant_001",
        transaction_id=str(transaction_id),
        amount=transaction.amount,
        currency="INR",
    )

    stored_response = {
        "transaction_id": str(transaction_id),
        "status": "AUTHORISED",
        "selected_gateway": "stripe_mock",
        "gateway_reference": "stripe-ref-001",
    }

    record = Mock()
    record.request_hash = request_hash
    record.status = "COMPLETED"
    record.response_data = stored_response

    db = Mock()
    db.scalar.return_value = transaction

    app.dependency_overrides[get_db] = lambda: db

    try:
        with patch(
            "app.services.transaction_service.get_idempotency_record",
            return_value=record,
        ), patch("app.main.ORCHESTRATOR") as orchestrator:
            client = TestClient(app)

            response = client.post(
                f"/transactions/{transaction_id}/authorize",
                headers={"Idempotency-Key": "order_003"},
            )

        assert response.status_code == 200
        assert response.json() == stored_response
        orchestrator.authorize.assert_not_called()
        db.add.assert_not_called()
        db.commit.assert_not_called()
    finally:
        app.dependency_overrides.clear()
