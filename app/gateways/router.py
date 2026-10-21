"""Five-factor gateway scoring with circuit-breaker-aware weighted selection."""
import random
from app.gateways.base import PaymentGateway
from app.gateways.circuit_breaker import CircuitBreaker, CircuitState

FACTOR_WEIGHTS = {
    "success_rate": 0.35,
    "latency": 0.20,
    "cost": 0.20,
    "health": 0.15,
    "payment_method_compatibility": 0.10,
}

class GatewayRouter:
    def __init__(self, gateways: list[PaymentGateway], weights: dict[str, int] | None = None,
                 failure_threshold: int = 5, recovery_timeout: float = 30.0):
        if not gateways:
            raise ValueError("At least one gateway must be configured")
        names = [g.name for g in gateways]
        if len(names) != len(set(names)):
            raise ValueError("Gateway names must be unique")
        weights = weights or {name: 100 for name in names}
        if set(weights) != set(names):
            raise ValueError("Weights must be provided for every configured gateway")
        if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in weights.values()):
            raise ValueError("Gateway weights must be non-negative integers")
        if sum(weights.values()) <= 0:
            raise ValueError("At least one gateway weight must be positive")
        self.gateways = gateways
        self.weights = weights.copy()
        self.circuit_breakers = {g.name: CircuitBreaker(failure_threshold, recovery_timeout) for g in gateways}

    @staticmethod
    def _metric(gateway, name, default):
        metrics = getattr(gateway, "routing_metrics", {}) or {}
        return metrics.get(name, default)

    def score_gateway(self, gateway: PaymentGateway, payment_method: str = "card") -> dict:
        """Return normalized factor scores and a weighted total in [0, 1].

        Metrics can be updated by adapters as real rolling measurements become available.
        Defaults are conservative demo baselines, not claims about real providers.
        """
        success = max(0.0, min(1.0, float(self._metric(gateway, "success_rate", 0.98))))
        latency_ms = max(1.0, float(self._metric(gateway, "p95_latency_ms", 250.0)))
        cost_bps = max(0.0, min(1000.0, float(self._metric(gateway, "cost_bps", 25.0))))
        health = 0.0 if self.circuit_breakers[gateway.name].state == CircuitState.OPEN else 1.0
        supported = set(getattr(gateway, "supported_payment_methods", {"card", "upi", "netbanking", "wallet"}))
        compatibility = 1.0 if payment_method.lower() in supported else 0.0
        factors = {
            "success_rate": success,
            "latency": min(1.0, 1000.0 / latency_ms),
            "cost": 1.0 - cost_bps / 1000.0,
            "health": health,
            "payment_method_compatibility": compatibility,
        }
        total = sum(factors[k] * FACTOR_WEIGHTS[k] for k in FACTOR_WEIGHTS)
        return {"gateway": gateway.name, "factors": factors, "factor_weights": FACTOR_WEIGHTS.copy(), "score": round(total, 6)}

    def routing_scores(self, payment_method: str = "card") -> list[dict]:
        return sorted((self.score_gateway(g, payment_method) for g in self.gateways), key=lambda x: x["score"], reverse=True)

    def select_gateway(self, excluded_gateways: set[str] | None = None, payment_method: str = "card") -> PaymentGateway:
        excluded = set(excluded_gateways or set())
        eligible = [g for g in self.gateways if g.name not in excluded and self.weights[g.name] > 0
                    and self.circuit_breakers[g.name].state != CircuitState.OPEN
                    and self.score_gateway(g, payment_method)["factors"]["payment_method_compatibility"] > 0]
        while eligible:
            scores = [max(0.001, self.score_gateway(g, payment_method)["score"] * self.weights[g.name]) for g in eligible]
            gateway = random.choices(eligible, weights=scores, k=1)[0]
            if self.circuit_breakers[gateway.name].allow_request():
                return gateway
            eligible.remove(gateway)
        raise RuntimeError(f"No eligible payment gateway is available for payment method {payment_method}")

    def record_observation(self, gateway_name: str, outcome, latency_ms: float) -> None:
        gateway = next(g for g in self.gateways if g.name == gateway_name)
        metrics = getattr(gateway, "routing_metrics", None)
        if metrics is None:
            metrics = {"success_rate": 0.98, "p95_latency_ms": 250.0, "cost_bps": 25.0}
            gateway.routing_metrics = metrics
        # EWMA keeps the demo responsive without retaining unbounded samples.
        is_technical_success = getattr(outcome, "value", str(outcome)) != "UNKNOWN"
        old_rate = float(metrics.get("success_rate", 0.98))
        metrics["success_rate"] = round(0.8 * old_rate + 0.2 * float(is_technical_success), 6)
        old_latency = float(metrics.get("p95_latency_ms", 250.0))
        metrics["p95_latency_ms"] = round(0.8 * old_latency + 0.2 * max(1.0, latency_ms), 3)

    def record_success(self, gateway_name: str) -> None:
        self.circuit_breakers[gateway_name].record_success()

    def record_failure(self, gateway_name: str) -> None:
        self.circuit_breakers[gateway_name].record_failure()

    def get_circuit_state(self, gateway_name: str) -> CircuitState:
        return self.circuit_breakers[gateway_name].state
