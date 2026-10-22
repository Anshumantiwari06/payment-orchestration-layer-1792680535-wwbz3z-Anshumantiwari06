from decimal import Decimal
from unittest.mock import Mock, patch
from uuid import uuid4
from fastapi.testclient import TestClient
from app.db.session import get_db
from app.gateways.schemas import GatewayOutcome
from app.main import app
from app.models.reconciliation_anomaly import ReconciliationAnomaly
from app.models.transaction_state_log import TransactionStateLog
from app.main import GATEWAYS, ROUTER
import pytest
from fastapi import HTTPException
from app import main

def test_capture_missing_payment_returns_404():
    db = Mock()
    db.scalar.return_value = None
    app.dependency_overrides[get_db] = lambda: db

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/payments/{uuid4()}/capture",
                json={"amount": "100.00"},
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Payment not found"
    finally:
        app.dependency_overrides.clear()


def test_void_missing_payment_returns_404():
    db = Mock()
    db.scalar.return_value = None
    app.dependency_overrides[get_db] = lambda: db

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/payments/{uuid4()}/void"
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Payment not found"
    finally:
        app.dependency_overrides.clear()


def test_refund_missing_payment_returns_404():
    db = Mock()
    db.scalar.return_value = None
    app.dependency_overrides[get_db] = lambda: db

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/payments/{uuid4()}/refund",
                json={"amount": "100.00"},
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Payment not found"
    finally:
        app.dependency_overrides.clear()
def test_capture_without_gateway_reference_returns_409():
    transaction = Mock()
    transaction.selected_gateway = None
    transaction.gateway_reference = None

    db = Mock()
    db.scalar.return_value = transaction
    app.dependency_overrides[get_db] = lambda: db

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/payments/{uuid4()}/capture",
                json={"amount": "100.00"},
            )

        assert response.status_code == 409
        assert response.json()["detail"] == (
            "Payment has no confirmed gateway reference"
        )
    finally:
        app.dependency_overrides.clear()
def test_capture_in_invalid_state_returns_409():
    transaction = Mock()
    transaction.selected_gateway = "mock_primary"
    transaction.gateway_reference = "ref_001"
    transaction.amount = Decimal("500.00")
    transaction.captured_amount = Decimal("0.00")
    transaction.refunded_amount = Decimal("0.00")
    transaction.status = "CREATED"

    gateway = Mock()
    gateway.name = "mock_primary"

    db = Mock()
    db.scalar.return_value = transaction
    app.dependency_overrides[get_db] = lambda: db

    try:
        with patch("app.main.GATEWAYS", [gateway]), TestClient(app) as client:
            response = client.post(
                f"/api/v1/payments/{uuid4()}/capture",
                json={"amount": "100.00"},
            )

        assert response.status_code == 409
        assert "Cannot capture payment in state CREATED" in (
            response.json()["detail"]
        )
        gateway.capture.assert_not_called()
    finally:
        app.dependency_overrides.clear()
def test_capture_exceeding_remaining_amount_returns_409():
    transaction = Mock()
    transaction.selected_gateway = "mock_primary"
    transaction.gateway_reference = "ref_001"
    transaction.amount = Decimal("500.00")
    transaction.captured_amount = Decimal("400.00")
    transaction.refunded_amount = Decimal("0.00")
    transaction.status = "PARTIALLY_CAPTURED"

    gateway = Mock()
    gateway.name = "mock_primary"

    db = Mock()
    db.scalar.return_value = transaction
    app.dependency_overrides[get_db] = lambda: db

    try:
        with patch("app.main.GATEWAYS", [gateway]), TestClient(app) as client:
            response = client.post(
                f"/api/v1/payments/{uuid4()}/capture",
                json={"amount": "200.00"},
            )

        assert response.status_code == 409
        assert "remaining authorized amount" in response.json()["detail"]
        gateway.capture.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_capture_zero_amount_returns_409():
    transaction = Mock()
    transaction.selected_gateway = "mock_primary"
    transaction.gateway_reference = "ref_001"
    transaction.amount = Decimal("500.00")
    transaction.captured_amount = Decimal("0.00")
    transaction.refunded_amount = Decimal("0.00")
    transaction.status = "AUTHORISED"

    gateway = Mock()
    gateway.name = "mock_primary"

    db = Mock()
    db.scalar.return_value = transaction
    app.dependency_overrides[get_db] = lambda: db

    try:
        with patch("app.main.GATEWAYS", [gateway]), TestClient(app) as client:
            response = client.post(
                f"/api/v1/payments/{uuid4()}/capture",
                json={"amount": "0.00"},
            )

        assert response.status_code == 422
       
    finally:
        app.dependency_overrides.clear()
def test_get_payment_missing_returns_404():
    db = Mock()
    db.get.return_value = None
    app.dependency_overrides[get_db] = lambda: db

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/payments/{uuid4()}"
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Payment not found"
    finally:
        app.dependency_overrides.clear()


def test_list_refunds_missing_payment_returns_404():
    db = Mock()
    db.get.return_value = None
    app.dependency_overrides[get_db] = lambda: db

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/payments/{uuid4()}/refunds"
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Payment not found"
    finally:
        app.dependency_overrides.clear()
        




def test_list_gateways_returns_configured_gateways():
    client = TestClient(app)

    response = client.get("/api/v1/gateways")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == len(GATEWAYS)
    assert all("name" in gateway for gateway in data)
    assert all("circuit_state" in gateway for gateway in data)


def test_gateway_health_returns_404_for_unknown_gateway():
    client = TestClient(app)

    response = client.get("/api/v1/gateways/unknown_gateway/health")

    assert response.status_code == 404
    assert response.json()["detail"] == "Gateway not found"


def test_gateway_health_returns_state_for_known_gateway():
    client = TestClient(app)
    gateway_name = GATEWAYS[0].name

    response = client.get(f"/api/v1/gateways/{gateway_name}/health")

    assert response.status_code == 200
    assert response.json()["name"] == gateway_name
    assert "healthy" in response.json()


def test_gateway_metrics_returns_404_for_unknown_gateway():
    client = TestClient(app)

    response = client.get("/api/v1/gateways/unknown_gateway/metrics")

    assert response.status_code == 404


def test_routing_config_returns_weights():
    client = TestClient(app)

    response = client.get("/api/v1/routing/config")

    assert response.status_code == 200
    assert response.json()["weights"] == ROUTER.weights
    assert "scoring_factors" in response.json()


def test_routing_scores_returns_scores():
    client = TestClient(app)

    response = client.get("/api/v1/routing/scores")

    assert response.status_code == 200
    assert response.json()["payment_method"] == "card"
    assert isinstance(response.json()["scores"], list)
    assert len(response.json()["scores"]) > 0
    assert all("gateway" in score and "score" in score
           for score in response.json()["scores"])


def test_routing_config_rejects_invalid_weights():
    client = TestClient(app)

    response = client.put(
        "/api/v1/routing/config",
        json={},
    )

    assert response.status_code == 400

def test_reconciliation_report_rejects_invalid_uuid():
    client = TestClient(app)

    response = client.get("/api/v1/reconciliation/reports/not-a-uuid")

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "run_id must be a reconciliation run UUID"
    )


def test_reconciliation_report_returns_404_when_not_found():
    client = TestClient(app)
    db = Mock()
    db.get.return_value = None
    app.dependency_overrides[get_db] = lambda: db

    try:
        response = client.get(
            f"/api/v1/reconciliation/reports/{uuid4()}"
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Reconciliation run or anomaly not found"
    )


def test_reconciliation_report_returns_existing_run():
    client = TestClient(app)
    run_id = uuid4()
    run = Mock()
    run.id = run_id
    run.status = "COMPLETED"
    run.checked_count = 3
    run.anomaly_count = 0
    run.details = {"errors": []}
    run.started_at = None
    run.completed_at = None

    db = Mock()
    db.get.return_value = run
    db.scalars.return_value.all.return_value = []
    app.dependency_overrides[get_db] = lambda: db

    try:
        response = client.get(
            f"/api/v1/reconciliation/reports/{run_id}"
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == str(run_id)
    assert data["status"] == "COMPLETED"
    assert data["checked_count"] == 3
    assert data["anomalies"] == []



def test_reconciliation_trigger_with_no_transactions():
    client = TestClient(app)
    db = Mock()
    db.scalars.return_value.all.return_value = []

    app.dependency_overrides[get_db] = lambda: db

    try:
        response = client.post("/api/v1/reconciliation/trigger")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert data["checked"] == 0
    assert data["anomalies_created"] == 0
    assert data["errors"] == []
    db.add.assert_called_once()
    db.flush.assert_called_once()
    db.commit.assert_called_once()

def test_reconciliation_trigger_reports_missing_gateway():
    client = TestClient(app)

    transaction = Mock()
    transaction.id = uuid4()
    transaction.status = "CAPTURED"
    transaction.selected_gateway = "unknown_gateway"
    transaction.gateway_reference = "ref_001"

    db = Mock()
    db.scalars.return_value.all.return_value = [transaction]
    app.dependency_overrides[get_db] = lambda: db

    try:
        response = client.post("/api/v1/reconciliation/trigger")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "COMPLETED_WITH_ERRORS"
    assert data["checked"] == 1
    assert data["anomalies_created"] == 0
    assert data["errors"][0]["transaction_id"] == str(transaction.id)
    assert data["errors"][0]["error"] == (
        "original gateway/reference unavailable"
    )
    db.commit.assert_called_once()

def test_reconciliation_trigger_handles_gateway_exception():
    client = TestClient(app)

    transaction = Mock()
    transaction.id = uuid4()
    transaction.status = "CAPTURED"
    transaction.selected_gateway = "razorpay"
    transaction.gateway_reference = "ref_001"

    gateway = Mock()
    gateway.name = "razorpay"
    gateway.get_status.side_effect = TimeoutError("gateway timed out")

    db = Mock()
    db.scalars.return_value.all.return_value = [transaction]
    app.dependency_overrides[get_db] = lambda: db

    try:
        with patch("app.main.GATEWAYS", [gateway]):
            response = client.post("/api/v1/reconciliation/trigger")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "COMPLETED_WITH_ERRORS"
    assert data["checked"] == 1
    assert data["anomalies_created"] == 0
    assert data["errors"][0]["error"] == "TimeoutError"
    gateway.get_status.assert_called_once_with("ref_001")
    db.commit.assert_called_once()

def test_reconciliation_trigger_creates_anomaly_on_status_mismatch():
    client = TestClient(app)

    transaction = Mock()
    transaction.id = uuid4()
    transaction.status = "CAPTURED"
    transaction.selected_gateway = "razorpay"
    transaction.gateway_reference = "ref_001"
    transaction.amount = Decimal("500.00")

    gateway = Mock()
    gateway.name = "razorpay"
    gateway.get_status.return_value = Mock(
        outcome=GatewayOutcome.DECLINED,
        message="Gateway reports declined",
    )

    db = Mock()
    db.scalars.return_value.all.return_value = [transaction]
    app.dependency_overrides[get_db] = lambda: db

    try:
        with patch("app.main.GATEWAYS", [gateway]):
            response = client.post("/api/v1/reconciliation/trigger")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert data["checked"] == 1
    assert data["anomalies_created"] == 1
    assert data["automatic_refunds_triggered"] is False

    added_objects = [call.args[0] for call in db.add.call_args_list]
    assert any(isinstance(obj, ReconciliationAnomaly) for obj in added_objects)
    assert any(isinstance(obj, TransactionStateLog) for obj in added_objects)
    db.commit.assert_called_once()
    

def test_capture_successfully_captures_payment():
    client = TestClient(app)
    transaction_id = uuid4()

    transaction = Mock()
    transaction.id = transaction_id
    transaction.selected_gateway = "mock_primary"
    transaction.gateway_reference = "ref_001"
    transaction.amount = Decimal("500.00")
    transaction.captured_amount = Decimal("0.00")
    transaction.refunded_amount = Decimal("0.00")
    transaction.status = "AUTHORISED"
    transaction.currency = "INR"
    transaction.merchant_id = "merchant_001"
    transaction.merchant_order_id = "order_001"
    transaction.created_at = None

    gateway = Mock()
    gateway.name = "mock_primary"
    gateway.capture.return_value = Mock(
        outcome=GatewayOutcome.CAPTURED,
        message="Capture successful",
        gateway_reference="ref_001",
    )

    db = Mock()
    db.scalar.return_value = transaction
    app.dependency_overrides[get_db] = lambda: db

    try:
        with patch("app.main.GATEWAYS", [gateway]):
            response = client.post(
                f"/api/v1/payments/{transaction_id}/capture",
                json={"amount": "500.00"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200, response.text
    assert response.json()["operation"] == "capture"
    assert response.json()["amount"] == "500.00"
    gateway.capture.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(transaction)

def test_void_successfully_voids_payment():
    client = TestClient(app)
    transaction_id = uuid4()

    transaction = Mock()
    transaction.id = transaction_id
    transaction.selected_gateway = "mock_primary"
    transaction.gateway_reference = "ref_001"
    transaction.amount = Decimal("500.00")
    transaction.captured_amount = Decimal("0.00")
    transaction.refunded_amount = Decimal("0.00")
    transaction.status = "AUTHORISED"
    transaction.currency = "INR"
    transaction.merchant_id = "merchant_001"
    transaction.merchant_order_id = "order_001"
    transaction.created_at = None

    gateway = Mock()
    gateway.name = "mock_primary"
    gateway.void.return_value = Mock(
        outcome=GatewayOutcome.VOIDED,
        message="Void successful",
        gateway_reference="ref_001",
    )

    db = Mock()
    db.scalar.return_value = transaction
    app.dependency_overrides[get_db] = lambda: db

    try:
        with patch("app.main.GATEWAYS", [gateway]):
            response = client.post(
                f"/api/v1/payments/{transaction_id}/void",
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200, response.text
    assert response.json()["operation"] == "void"
    gateway.void.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(transaction)

def test_refund_successfully_refunds_payment():
    client = TestClient(app)
    transaction_id = uuid4()

    transaction = Mock()
    transaction.id = transaction_id
    transaction.selected_gateway = "mock_primary"
    transaction.gateway_reference = "ref_001"
    transaction.amount = Decimal("500.00")
    transaction.captured_amount = Decimal("500.00")
    transaction.refunded_amount = Decimal("0.00")
    transaction.status = "CAPTURED"
    transaction.currency = "INR"
    transaction.merchant_id = "merchant_001"
    transaction.merchant_order_id = "order_001"
    transaction.created_at = None

    gateway = Mock()
    gateway.name = "mock_primary"
    gateway.refund.return_value = Mock(
        outcome=GatewayOutcome.REFUNDED,
        message="Refund successful",
        gateway_reference="ref_001",
    )

    db = Mock()
    db.scalar.return_value = transaction
    app.dependency_overrides[get_db] = lambda: db

    try:
        with patch("app.main.GATEWAYS", [gateway]):
            response = client.post(
                f"/api/v1/payments/{transaction_id}/refund",
                json={"amount": "500.00"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200, response.text
    assert response.json()["operation"] == "refund"
    gateway.refund.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(transaction)

def test_create_payment_database_error_returns_500():

    db = Mock()
    app.dependency_overrides[get_db] = lambda: db

    try:
        with patch(
            "app.main.create_transaction",
            side_effect=__import__(
                "sqlalchemy.exc", fromlist=["SQLAlchemyError"]
            ).SQLAlchemyError("database unavailable"),
        ), TestClient(app) as client:
            response = client.post(
                "/api/v1/payments",
                json={
                    "merchant_id": "merchant_test",
                    "merchant_order_id": "order_db_error",
                    "amount": "100.00",
                    "currency": "INR",
                },
            )

        assert response.status_code == 500
        assert response.json()["detail"] == (
            "Database error while creating transaction"
        )
        db.rollback.assert_called_once()
    finally:
        app.dependency_overrides.clear()

def test_create_payment_invalid_request_returns_400():
    db = Mock()
    app.dependency_overrides[get_db] = lambda: db

    try:
        with patch(
            "app.main.create_transaction",
            side_effect=ValueError("Invalid transaction data"),
        ), TestClient(app) as client:
            response = client.post(
                "/api/v1/payments",
                json={
                    "merchant_id": "merchant_test",
                    "merchant_order_id": "order_invalid",
                    "amount": "100.00",
                    "currency": "INR",
                },
            )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid transaction data"
        db.rollback.assert_not_called()
    finally:
        app.dependency_overrides.clear()

def test_get_payment_returns_serialized_payment():
    transaction_id = uuid4()

    transaction = Mock()
    transaction.id = transaction_id
    transaction.merchant_id = "merchant_test"
    transaction.merchant_order_id = "order_001"
    transaction.amount = Decimal("250.00")
    transaction.currency = "INR"
    transaction.status = "AUTHORISED"
    transaction.selected_gateway = "razorpay"
    transaction.gateway_reference = "pay_ref_001"
    transaction.captured_amount = Decimal("100.00")
    transaction.refunded_amount = Decimal("0.00")
    transaction.created_at = None

    db = Mock()
    db.get.return_value = transaction
    app.dependency_overrides[get_db] = lambda: db

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/payments/{transaction_id}"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(transaction_id)
        assert data["merchant_id"] == "merchant_test"
        assert data["amount"] == "250.00"
        assert data["status"] == "AUTHORISED"
        assert data["gateway"] == "razorpay"
        assert data["gateway_reference"] == "pay_ref_001"
        assert data["captured_amount"] == "100.00"
        assert data["refunded_amount"] == "0"
        assert data["created_at"] is None
    finally:
        app.dependency_overrides.clear()

def test_payment_timeline_returns_state_history():
    transaction_id = uuid4()

    transaction = Mock()
    log = Mock()
    log.previous_state = "CREATED"
    log.new_state = "AUTHORISED"
    log.event_type = "STATE_TRANSITION"
    log.reason = "Payment authorized"
    log.correlation_id = "corr_001"
    log.created_at = __import__("datetime").datetime(
        2026, 10, 22, 10, 0, 0
    )

    db = Mock()
    db.get.return_value = transaction
    db.scalars.return_value.all.return_value = [log]
    app.dependency_overrides[get_db] = lambda: db

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/payments/{transaction_id}/timeline"
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["previous_state"] == "CREATED"
        assert data[0]["new_state"] == "AUTHORISED"
        assert data[0]["event_type"] == "STATE_TRANSITION"
        assert data[0]["reason"] == "Payment authorized"
        assert data[0]["correlation_id"] == "corr_001"
        assert data[0]["created_at"] == "2026-10-22T10:00:00"
    finally:
        app.dependency_overrides.clear()

def test_payment_timeline_missing_payment_returns_404():
    db = Mock()
    db.get.return_value = None
    app.dependency_overrides[get_db] = lambda: db

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/payments/{uuid4()}/timeline"
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Payment not found"
    finally:
        app.dependency_overrides.clear()


def test_payment_timeline_empty_history_returns_empty_list():
    db = Mock()
    db.get.return_value = Mock()
    db.scalars.return_value.all.return_value = []
    app.dependency_overrides[get_db] = lambda: db

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/payments/{uuid4()}/timeline"
            )

        assert response.status_code == 200
        assert response.json() == []
    finally:
        app.dependency_overrides.clear()


def test_get_payment_invalid_uuid_returns_422():
    db = Mock()
    app.dependency_overrides[get_db] = lambda: db

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/payments/not-a-uuid"
            )

        assert response.status_code == 422
        db.get.assert_not_called()
    finally:
        app.dependency_overrides.clear()





def test_root_returns_service_information():
    result = main.root()
    assert result["status"] == "running"
    assert result["mode"] == "mock-gateways"


def test_health_returns_503_on_database_error():
    from sqlalchemy.exc import SQLAlchemyError

    db = Mock()
    db.execute.side_effect = SQLAlchemyError("database unavailable")

    with pytest.raises(HTTPException) as exc:
        main.health(db)

    assert exc.value.status_code == 503


def test_gateway_health_rejects_unknown_gateway():
    with pytest.raises(HTTPException) as exc:
        main.gateway_health("not-a-gateway")

    assert exc.value.status_code == 404


def test_gateway_metrics_rejects_unknown_gateway():
    with pytest.raises(HTTPException) as exc:
        main.gateway_metrics("not-a-gateway")

    assert exc.value.status_code == 404


def test_gateway_scenario_rejects_unknown_gateway():
    with pytest.raises(HTTPException) as exc:
        main.configure_mock_scenario("not-a-gateway", "success")

    assert exc.value.status_code == 404


def test_gateway_scenario_maps_invalid_scenario_to_400(monkeypatch):
    gateway = main.GATEWAYS[0]
    monkeypatch.setattr(
        gateway, "set_scenario",
        Mock(side_effect=ValueError("invalid scenario")),
    )

    with pytest.raises(HTTPException) as exc:
        main.configure_mock_scenario(gateway.name, "invalid")

    assert exc.value.status_code == 400


def test_gateway_config_rejects_unknown_gateway():
    with pytest.raises(HTTPException) as exc:
        main.update_gateway_config("not-a-gateway", True, 1)

    assert exc.value.status_code == 404


def test_gateway_config_prevents_disabling_last_weighted_gateway(monkeypatch):
    original = main.ROUTER.weights.copy()
    try:
        for name in main.ROUTER.weights:
            main.ROUTER.weights[name] = 0

        target = next(iter(main.ROUTER.weights))
        with pytest.raises(HTTPException) as exc:
            main.update_gateway_config(target, False, 0)

        assert exc.value.status_code == 400
    finally:
        main.ROUTER.weights.update(original)


@pytest.mark.parametrize(
    "weights",
    [
        {},
        {"unknown": 100},
        {"razorpay": -1},
        {"razorpay": 0, "stripe": 0, "payu": 0, "upi": 0},
        {"razorpay": True, "stripe": 1, "payu": 1, "upi": 1},
    ],
)
def test_routing_config_service_rejects_invalid_weights(weights):
    with pytest.raises(HTTPException) as exc:
        main.set_routing_config(weights)

    assert exc.value.status_code == 400


def test_routing_config_accepts_valid_weights():
    original = main.ROUTER.weights.copy()
    weights = {name: 1 for name in original}
    try:
        result = main.set_routing_config(weights)
        assert result["weights"] == weights
    finally:
        main.ROUTER.weights.update(original)


def test_routing_config_endpoint_returns_current_weights():
    result = main.get_routing_config()
    assert result["weights"] == main.ROUTER.weights
    assert "scoring_factors" in result


def test_routing_scores_returns_requested_payment_method():
    result = main.routing_scores("card")
    assert result["payment_method"] == "card"
    assert "scores" in result


def test_webhook_event_endpoint_returns_404_when_missing():
    db = Mock()
    db.scalar.return_value = None

    with pytest.raises(HTTPException) as exc:
        main.get_webhook_event("missing-event", db)

    assert exc.value.status_code == 404

