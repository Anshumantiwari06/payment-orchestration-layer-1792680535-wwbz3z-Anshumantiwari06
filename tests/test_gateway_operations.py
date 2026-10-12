
from decimal import Decimal

from app.gateways.mock_gateway import MockGateway
from app.gateways.schemas import GatewayOutcome


def test_mock_gateway_capture_succeeds():
    gateway = MockGateway("mock_primary")

    result = gateway.capture(
        gateway_reference="ref_001",
        amount=Decimal("500.00"),
        idempotency_key="capture_001",
    )

    assert result.outcome == GatewayOutcome.AUTHORISED
    assert result.gateway_reference == "ref_001"


def test_mock_gateway_void_succeeds():
    gateway = MockGateway("mock_primary")

    result = gateway.void(
        gateway_reference="ref_001",
        idempotency_key="void_001",
    )

    assert result.outcome == GatewayOutcome.AUTHORISED


def test_mock_gateway_refund_succeeds():
    gateway = MockGateway("mock_primary")

    result = gateway.refund(
        gateway_reference="ref_001",
        amount=Decimal("200.00"),
        idempotency_key="refund_001",
    )

    assert result.outcome == GatewayOutcome.AUTHORISED


def test_mock_gateway_get_status_returns_reference():
    gateway = MockGateway("mock_primary")

    result = gateway.get_status("ref_001")

    assert result.gateway_reference == "ref_001"
    assert result.gateway_name == "mock_primary"
