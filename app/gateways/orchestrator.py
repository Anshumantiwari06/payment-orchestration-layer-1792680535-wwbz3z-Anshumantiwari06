
from decimal import Decimal

from app.gateways.router import GatewayRouter
from app.gateways.schemas import GatewayOutcome, GatewayResult


class PaymentOrchestrator:
    def __init__(self, router: GatewayRouter):
        self.router = router

    def authorize(
        self,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
    ) -> GatewayResult:
        excluded_gateways: set[str] = set()
        last_result: GatewayResult | None = None

        while True:
            try:
                gateway = self.router.select_gateway(
                    excluded_gateways=excluded_gateways,
                )
            except RuntimeError:
                if last_result is not None:
                    return last_result
                raise

            excluded_gateways.add(gateway.name)

            try:
                result = gateway.authorize(
                    amount=amount,
                    currency=currency,
                    idempotency_key=idempotency_key,
                )
            except Exception as exc:
                return GatewayResult(
                    outcome=GatewayOutcome.UNKNOWN,
                    gateway_name=gateway.name,
                    message=f"Gateway call failed: {type(exc).__name__}",
                )

            last_result = result

            if result.outcome in {
                GatewayOutcome.AUTHORISED,
                GatewayOutcome.UNKNOWN,
            }:
                return result

            # A definitive decline permits trying another gateway.
