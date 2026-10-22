"""Deterministic mock adapters; no real gateway credentials or network calls."""
from decimal import Decimal

from app.gateways.mock_gateway import MockGateway
from app.gateways.schemas import GatewayOutcome, GatewayResult


class ScenarioMockGateway(MockGateway):
    def __init__(self, gateway_name: str, outcome: GatewayOutcome = GatewayOutcome.AUTHORISED):
        super().__init__(gateway_name, outcome)
        self.calls = {"authorize": 0, "capture": 0, "void": 0, "refund": 0, "status": 0}
        self.next_scenario: str | None = None
        # Demo baselines used by the five-factor router; replace with rolling
        # production telemetry when real provider adapters are configured.
        self.routing_metrics = {"success_rate": 0.98, "p95_latency_ms": 250.0, "cost_bps": 25.0}
        self.supported_payment_methods = {"card", "upi", "netbanking", "wallet"}

    def set_scenario(self, scenario: str | None):
        allowed = {None, "success", "timeout", "server-error", "decline", "rate-limit", "unknown", "partial",
                   "connection-reset", "gateway-down", "authentication-error", "insufficient-funds",
                   "invalid-response", "provider-5xx", "duplicate-response", "stale-status"}
        if scenario not in allowed:
            raise ValueError(f"Unsupported mock scenario: {scenario}")
        self.next_scenario = scenario

    def _scenario_result(self, operation: str, reference: str | None = None):
        self.calls[operation] += 1
        scenario, self.next_scenario = self.next_scenario, None
        if scenario in {"timeout", "server-error", "rate-limit", "unknown", "connection-reset", "gateway-down", "authentication-error", "invalid-response", "provider-5xx", "stale-status"}:
            return GatewayResult(outcome=GatewayOutcome.UNKNOWN, gateway_name=self.name, gateway_reference=reference,
                                 message=f"Simulated {scenario}; outcome must be treated as uncertain")
        if scenario in {"decline", "insufficient-funds"}:
            return GatewayResult(outcome=GatewayOutcome.DECLINED, gateway_name=self.name, gateway_reference=reference,
                                 message=f"Simulated {scenario}")
        if scenario == "partial":
            return GatewayResult(outcome=GatewayOutcome.PARTIALLY_CAPTURED, gateway_name=self.name,
                                 gateway_reference=reference or f"{self.name}-ref-001", message="Simulated partial operation")
        if scenario == "duplicate-response":
            return GatewayResult(outcome=GatewayOutcome.AUTHORISED, gateway_name=self.name,
                                 gateway_reference=f"{self.name}-ref-001", message="Simulated repeated stable response")
        return None

    def authorize(self, amount: Decimal, currency: str, idempotency_key: str):
        result=self._scenario_result("authorize")
        return result or super().authorize(amount,currency,idempotency_key)
    def capture(self, gateway_reference: str, amount: Decimal, idempotency_key: str):
        result=self._scenario_result("capture",gateway_reference)
        return result or GatewayResult(outcome=GatewayOutcome.CAPTURED,gateway_name=self.name,gateway_reference=gateway_reference,message="Simulated capture")
    def void(self, gateway_reference: str, idempotency_key: str):
        result=self._scenario_result("void",gateway_reference)
        return result or GatewayResult(outcome=GatewayOutcome.VOIDED,gateway_name=self.name,gateway_reference=gateway_reference,message="Simulated void")
    def refund(self, gateway_reference: str, amount: Decimal, idempotency_key: str):
        result=self._scenario_result("refund",gateway_reference)
        return result or GatewayResult(outcome=GatewayOutcome.REFUNDED,gateway_name=self.name,gateway_reference=gateway_reference,message="Simulated refund")
    def get_status(self, gateway_reference: str):
        self.calls["status"] += 1
        return super().get_status(gateway_reference)

class RazorpayAdapter(ScenarioMockGateway):
    def __init__(self): super().__init__("razorpay")
class StripeAdapter(ScenarioMockGateway):
    def __init__(self): super().__init__("stripe")
class PayUAdapter(ScenarioMockGateway):
    def __init__(self): super().__init__("payu")
class UPIAdapter(ScenarioMockGateway):
    def __init__(self):
        super().__init__("upi")
        self.supported_payment_methods = {"upi"}
