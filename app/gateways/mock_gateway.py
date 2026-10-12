
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
            message=f"Simulated authorization: {self.outcome.value}",
        )

    def capture(
        self,
        gateway_reference: str,
        amount: Decimal,
        idempotency_key: str,
    ) -> GatewayResult:
        return self._success(gateway_reference, "Capture")

    def void(
        self,
        gateway_reference: str,
        idempotency_key: str,
    ) -> GatewayResult:
        return self._success(gateway_reference, "Void")

    def refund(
        self,
        gateway_reference: str,
        amount: Decimal,
        idempotency_key: str,
    ) -> GatewayResult:
        return self._success(gateway_reference, "Refund")

    def get_status(
        self,
        gateway_reference: str,
    ) -> GatewayResult:
        return GatewayResult(
            outcome=self.outcome,
            gateway_name=self.name,
            gateway_reference=gateway_reference,
            message=f"Simulated status: {self.outcome.value}",
        )

    def _success(
        self,
        gateway_reference: str,
        operation: str,
    ) -> GatewayResult:
        return GatewayResult(
            outcome=GatewayOutcome.AUTHORISED,
            gateway_name=self.name,
            gateway_reference=gateway_reference,
            message=f"Simulated {operation.lower()} succeeded",
        )
