
import random

from app.gateways.base import PaymentGateway


class GatewayRouter:
    def __init__(
        self,
        gateways: list[PaymentGateway],
        weights: dict[str, int] | None = None,
    ):
        if not gateways:
            raise ValueError("At least one gateway must be configured")

        gateway_names = [gateway.name for gateway in gateways]
        if len(gateway_names) != len(set(gateway_names)):
            raise ValueError("Gateway names must be unique")

        self.gateways = gateways

        if weights is None:
            weights = {
                gateway.name: 100
                for gateway in gateways
            }

        if set(weights) != set(gateway_names):
            raise ValueError(
                "Weights must be provided for every configured gateway"
            )

        if any(
            not isinstance(weight, int) or isinstance(weight, bool) or weight < 0
            for weight in weights.values()
        ):
            raise ValueError("Gateway weights must be non-negative integers")

        if sum(weights.values()) <= 0:
            raise ValueError("At least one gateway weight must be positive")

        self.weights = weights

    def select_gateway(
        self,
        excluded_gateways: set[str] | None = None,
    ) -> PaymentGateway:
        excluded = excluded_gateways or set()

        eligible = [
            gateway
            for gateway in self.gateways
            if gateway.name not in excluded
            and self.weights[gateway.name] > 0
        ]

        if not eligible:
            raise RuntimeError("No eligible payment gateway is available")

        return random.choices(
            eligible,
            weights=[self.weights[gateway.name] for gateway in eligible],
            k=1,
        )[0]
