
from decimal import Decimal

from app.gateways.base import PaymentGateway
from app.gateways.schemas import GatewayOutcome, GatewayResult


class MockGateway(PaymentGateway):
    def __init__(
        self,
        gateway_name: str,
        outcome: GatewayOutcome = GatewayOutcome.AUTHORISED,
    ):
        self._name = gateway_name
        self.outcome = outcome

    @property
    def name(self) -> str:
        return self._name

    def authorize(
        self,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
    ) -> GatewayResult:
        return GatewayResult(
            outcome=self.outcome,
            gateway_name=self.name,
            gateway_reference=f"{self.name}-ref-001",
            message=f"Simulated result: {self.outcome.value}",
        )
