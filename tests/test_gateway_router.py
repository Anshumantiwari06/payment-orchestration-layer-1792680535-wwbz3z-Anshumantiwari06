
import pytest

from app.gateways.mock_gateway import MockGateway
from app.gateways.router import GatewayRouter


def test_router_selects_gateway_with_positive_weight():
    primary = MockGateway("primary")
    secondary = MockGateway("secondary")

    router = GatewayRouter(
        gateways=[primary, secondary],
        weights={"primary": 70, "secondary": 30},
    )

    selected = router.select_gateway()

    assert selected.name in {"primary", "secondary"}


def test_router_excludes_failed_gateway():
    primary = MockGateway("primary")
    secondary = MockGateway("secondary")

    router = GatewayRouter(
        gateways=[primary, secondary],
        weights={"primary": 70, "secondary": 30},
    )

    selected = router.select_gateway(excluded_gateways={"primary"})

    assert selected.name == "secondary"


def test_router_rejects_all_zero_weights():
    primary = MockGateway("primary")
    secondary = MockGateway("secondary")

    with pytest.raises(ValueError):
        GatewayRouter(
            gateways=[primary, secondary],
            weights={"primary": 0, "secondary": 0},
        )


def test_router_rejects_missing_gateway_weight():
    primary = MockGateway("primary")
    secondary = MockGateway("secondary")

    with pytest.raises(ValueError):
        GatewayRouter(
            gateways=[primary, secondary],
            weights={"primary": 100},
        )


def test_router_rejects_negative_weight():
    primary = MockGateway("primary")
    secondary = MockGateway("secondary")

    with pytest.raises(ValueError):
        GatewayRouter(
            gateways=[primary, secondary],
            weights={"primary": -10, "secondary": 110},
        )


def test_router_raises_when_no_gateway_is_eligible():
    primary = MockGateway("primary")
    secondary = MockGateway("secondary")

    router = GatewayRouter(
        gateways=[primary, secondary],
        weights={"primary": 70, "secondary": 30},
    )

    with pytest.raises(RuntimeError):
        router.select_gateway(excluded_gateways={"primary", "secondary"})
