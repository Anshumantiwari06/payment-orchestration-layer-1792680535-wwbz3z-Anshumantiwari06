
from app.gateways.base import PaymentGateway


class GatewayRouter:
    def __init__(self, gateways: list[PaymentGateway]):
        if not gateways:
            raise ValueError("At least one gateway must be configured")

        self.gateways = gateways

    def select_gateway(
        self,
        excluded_gateways: set[str] | None = None,
    ) -> PaymentGateway:
        excluded = excluded_gateways or set()

        for gateway in self.gateways:
            if gateway.name not in excluded:
                return gateway

        raise RuntimeError("No eligible payment gateway is available")
