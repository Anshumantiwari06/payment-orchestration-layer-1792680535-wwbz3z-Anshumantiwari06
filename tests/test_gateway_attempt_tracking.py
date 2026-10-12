from decimal import Decimal

from app.gateways.mock_gateway import MockGateway
from app.gateways.orchestrator import PaymentOrchestrator
from app.gateways.router import GatewayRouter
from app.gateways.schemas import GatewayOutcome


def test_attempted_gateways_are_recorded_in_order():
    primary = MockGateway("primary", GatewayOutcome.DECLINED)
    secondary = MockGateway("secondary", GatewayOutcome.AUTHORISED)

    router = GatewayRouter(
        [primary, secondary],
        weights={"primary": 100, "secondary": 100},
    )

    # Force deterministic gateway selection.
    router.select_gateway = lambda excluded_gateways=None: (
        primary if "primary" not in (excluded_gateways or set()) else secondary
    )

    orchestrator = PaymentOrchestrator(router)

    result = orchestrator.authorize(
        Decimal("100.00"),
        "INR",
        "tracking_001",
    )

    assert result.outcome == GatewayOutcome.AUTHORISED
    assert orchestrator.last_attempted_gateways == ["primary", "secondary"]
