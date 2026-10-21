from app.gateways.adapters import RazorpayAdapter, StripeAdapter, PayUAdapter, UPIAdapter
from app.gateways.router import GatewayRouter, FACTOR_WEIGHTS


def test_factor_weights_sum_to_one():
    assert round(sum(FACTOR_WEIGHTS.values()), 8) == 1.0


def test_routing_score_has_all_five_factors():
    gateways = [RazorpayAdapter(), StripeAdapter(), PayUAdapter(), UPIAdapter()]
    router = GatewayRouter(gateways, weights={g.name: 1 for g in gateways})
    score = router.score_gateway(gateways[0], "card")
    assert set(score["factors"]) == set(FACTOR_WEIGHTS)
    assert 0 <= score["score"] <= 1


def test_upi_method_excludes_card_only_incompatible_gateway():
    gateways = [RazorpayAdapter(), UPIAdapter()]
    router = GatewayRouter(gateways, weights={g.name: 1 for g in gateways})
    assert router.score_gateway(gateways[1], "upi")["factors"]["payment_method_compatibility"] == 1
    assert router.score_gateway(gateways[1], "card")["factors"]["payment_method_compatibility"] == 0
    assert router.select_gateway(payment_method="upi").name in {"razorpay", "upi"}


def test_runtime_observation_updates_success_and_latency_metrics():
    from app.gateways.schemas import GatewayOutcome
    gateway = RazorpayAdapter()
    router = GatewayRouter([gateway], weights={gateway.name: 1})
    before_rate = gateway.routing_metrics["success_rate"]
    router.record_observation(gateway.name, GatewayOutcome.UNKNOWN, 800)
    assert gateway.routing_metrics["success_rate"] < before_rate
    assert gateway.routing_metrics["p95_latency_ms"] > 250
