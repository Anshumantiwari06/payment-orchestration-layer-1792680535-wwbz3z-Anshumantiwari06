from decimal import Decimal
from time import perf_counter

from app.gateways.router import GatewayRouter
from app.gateways.schemas import GatewayOutcome, GatewayResult


class PaymentOrchestrator:
    def __init__(self, router: GatewayRouter):
        self.router = router
        self.last_attempted_gateways: list[str] = []

    def authorize(
        self,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
        payment_method: str = "card",
    ) -> GatewayResult:
        excluded_gateways: set[str] = set()
        last_result: GatewayResult | None = None
        self.last_attempted_gateways = []

        while True:
            try:
                gateway = self.router.select_gateway(
                    excluded_gateways=excluded_gateways,
                    payment_method=payment_method,
                )
            except RuntimeError:
                if last_result is not None:
                    return last_result
                raise

            excluded_gateways.add(gateway.name)
            self.last_attempted_gateways.append(gateway.name)

            started = perf_counter()
            try:
                result = gateway.authorize(
                    amount=amount,
                    currency=currency,
                    idempotency_key=idempotency_key,
                )
            except Exception as exc:
                self.router.record_observation(gateway.name, GatewayOutcome.UNKNOWN, (perf_counter() - started) * 1000)
                self.router.record_failure(gateway.name)

                # The payment outcome is uncertain. Never fail over here.
                return GatewayResult(
                    outcome=GatewayOutcome.UNKNOWN,
                    gateway_name=gateway.name,
                    message=f"Gateway call failed: {type(exc).__name__}",
                )

            last_result = result
            self.router.record_observation(gateway.name, result.outcome, (perf_counter() - started) * 1000)

            if result.outcome == GatewayOutcome.UNKNOWN:
                self.router.record_failure(gateway.name)
                # Do not retry an uncertain payment through another gateway.
                return result

            # A definitive response indicates the gateway responded.
            # A business decline is not a gateway infrastructure failure.
            self.router.record_success(gateway.name)

            if result.outcome == GatewayOutcome.AUTHORISED:
                return result

            # Fail over only after a definitive decline.
