
from decimal import Decimal
from unittest.mock import Mock

from app.gateways.mock_gateway import MockGateway
from app.gateways.orchestrator import PaymentOrchestrator
from app.gateways.router import GatewayRouter
from app.gateways.schemas import GatewayOutcome


def test_definitive_decline_fails_over_to_another_gateway():
    primary = MockGateway("primary", GatewayOutcome.DECLINED)
    secondary = MockGateway("secondary", GatewayOutcome.AUTHORISED)

    primary.authorize = Mock(wraps=primary.authorize)
    secondary.authorize = Mock(wraps=secondary.authorize)

    router = GatewayRouter(
        [primary, secondary],
        weights={"primary": 100, "secondary": 100},
    )

    # Deterministically select primary first, then secondary after a decline.
    router.select_gateway = lambda excluded_gateways=None, payment_method="card": (
        primary
        if "primary" not in (excluded_gateways or set())
        else secondary
    )

    orchestrator = PaymentOrchestrator(router)

    result = orchestrator.authorize(
        Decimal("100.00"), "INR", "failover_001"
    )

    assert result.outcome == GatewayOutcome.AUTHORISED
    assert result.gateway_name == "secondary"
    primary.authorize.assert_called_once()
    secondary.authorize.assert_called_once()


def test_unknown_outcome_does_not_fail_over():
    primary = MockGateway("primary", GatewayOutcome.UNKNOWN)
    secondary = MockGateway("secondary", GatewayOutcome.AUTHORISED)

    primary.authorize = Mock(wraps=primary.authorize)
    secondary.authorize = Mock(wraps=secondary.authorize)

    router = GatewayRouter(
        [primary, secondary],
        weights={"primary": 100, "secondary": 100},
    )
    router.select_gateway = lambda excluded_gateways=None, payment_method="card": (
        primary
        if "primary" not in (excluded_gateways or set())
        else secondary
    )

    orchestrator = PaymentOrchestrator(router)

    result = orchestrator.authorize(
        Decimal("100.00"), "INR", "unknown_001"
    )

    assert result.outcome == GatewayOutcome.UNKNOWN
    assert result.gateway_name == "primary"
    primary.authorize.assert_called_once()
    secondary.authorize.assert_not_called()


def test_gateway_exception_returns_unknown_without_failover():
    class BrokenGateway(MockGateway):
        def authorize(self, amount, currency, idempotency_key):
            raise TimeoutError("Simulated timeout")

    primary = BrokenGateway("primary")
    secondary = MockGateway("secondary", GatewayOutcome.AUTHORISED)

    primary.authorize = Mock(wraps=primary.authorize)
    secondary.authorize = Mock(wraps=secondary.authorize)

    router = GatewayRouter(
        [primary, secondary],
        weights={"primary": 100, "secondary": 100},
    )
    router.select_gateway = lambda excluded_gateways=None, payment_method="card": (
        primary
        if "primary" not in (excluded_gateways or set())
        else secondary
    )

    orchestrator = PaymentOrchestrator(router)

    result = orchestrator.authorize(
        Decimal("100.00"), "INR", "timeout_001"
    )

    assert result.outcome == GatewayOutcome.UNKNOWN
    assert result.gateway_name == "primary"
    primary.authorize.assert_called_once()
    secondary.authorize.assert_not_called()
