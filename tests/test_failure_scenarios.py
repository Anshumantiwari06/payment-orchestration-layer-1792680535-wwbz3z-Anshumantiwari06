from decimal import Decimal

import pytest

from app.gateways.adapters import RazorpayAdapter
from app.gateways.schemas import GatewayOutcome

SCENARIOS = [
    ("success", GatewayOutcome.AUTHORISED),
    ("timeout", GatewayOutcome.UNKNOWN),
    ("server-error", GatewayOutcome.UNKNOWN),
    ("decline", GatewayOutcome.DECLINED),
    ("rate-limit", GatewayOutcome.UNKNOWN),
    ("unknown", GatewayOutcome.UNKNOWN),
    ("partial", GatewayOutcome.PARTIALLY_CAPTURED),
    ("connection-reset", GatewayOutcome.UNKNOWN),
    ("gateway-down", GatewayOutcome.UNKNOWN),
    ("authentication-error", GatewayOutcome.UNKNOWN),
    ("insufficient-funds", GatewayOutcome.DECLINED),
    ("invalid-response", GatewayOutcome.UNKNOWN),
    ("provider-5xx", GatewayOutcome.UNKNOWN),
    ("duplicate-response", GatewayOutcome.AUTHORISED),
    ("stale-status", GatewayOutcome.UNKNOWN),
]

@pytest.mark.parametrize("scenario, expected", SCENARIOS)
def test_all_fifteen_mock_failure_scenarios(scenario, expected):
    gateway = RazorpayAdapter()
    gateway.set_scenario(scenario)
    result = gateway.authorize(Decimal("100.00"), "INR", f"scenario-{scenario}")
    assert result.outcome == expected
    assert gateway.next_scenario is None
