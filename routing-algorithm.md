# Gateway Routing Algorithm

## Overview
The payment orchestration layer uses five-factor gateway scoring with circuit-breaker-aware weighted selection to choose a payment gateway.

## 1. Routing Factors

| Factor | Weight | Scoring approach |
|---|---:|---|
| Success rate | 35% | Gateway's observed success rate, clamped to 0–1 |
| Latency | 20% | `min(1, 1000 / p95_latency_ms)` |
| Cost | 20% | `1 - cost_bps / 1000` |
| Health | 15% | 0 when the circuit breaker is OPEN; otherwise 1 |
| Payment method compatibility | 10% | 1 if supported; otherwise 0 |

The weighted score is the sum of each factor score multiplied by its configured factor weight. The final score is rounded to six decimal places.

## 2. Default Metrics

When gateway adapters do not provide routing metrics, the router uses these demo baselines:

- Success rate: `0.98`
- P95 latency: `250 ms`
- Cost: `25 basis points`

These are fallback values for the demo, not verified real-provider performance figures.

## 3. Gateway Eligibility

A gateway is eligible only when all of the following are true:

- It has not been explicitly excluded for the current selection.
- Its configured routing weight is greater than zero.
- Its circuit breaker is not OPEN.
- It supports the requested payment method.

If no eligible gateway remains, `select_gateway()` raises a `RuntimeError`.

## 4. Weighted Selection

For each eligible gateway, the router calculates:

`selection_weight = max(0.001, score * configured_gateway_weight)`

It then selects a gateway using weighted random selection. The circuit breaker must also allow the request. If it does not, that gateway is removed from the current candidate list and selection is attempted again.

## 5. Circuit Breakers

Each configured gateway receives its own circuit breaker. The router supports configurable failure thresholds and recovery timeouts. The defaults are five failures and 30 seconds.

- **OPEN:** The gateway is excluded from routing.
- **Other states:** The gateway can be considered eligible, subject to the circuit breaker's `allow_request()` decision.

Exact HALF_OPEN transition behavior is implemented in `app/gateways/circuit_breaker.py`.

## 6. Observed Metrics

`record_observation()` updates success rate and latency using an exponentially weighted moving average (EWMA):

`new_metric = 0.8 * old_metric + 0.2 * new_observation`

The outcome is treated as a technical success unless its value is `UNKNOWN`. Latency observations are bounded below by 1 ms.

## 7. Operational Methods

- `routing_scores(payment_method)`: returns gateways ordered by score, highest first.
- `select_gateway(excluded_gateways, payment_method)`: selects an eligible gateway.
- `record_observation(gateway_name, outcome, latency_ms)`: updates routing metrics.
- `record_success(gateway_name)`: records circuit-breaker success.
- `record_failure(gateway_name)`: records circuit-breaker failure.
- `get_circuit_state(gateway_name)`: returns the gateway's circuit-breaker state.

## 8. Configuration Validation

Router initialization rejects:

- An empty gateway list.
- Duplicate gateway names.
- Missing or extra gateway-weight entries.
- Negative, non-integer, or Boolean gateway weights.
- A configuration in which every gateway weight is zero.

## 9. Implementation Notes

- The router uses weighted random selection, so repeated selections can differ for the same metrics.
- Payment method compatibility is checked before selection.
- The cost metric is represented in basis points (`cost_bps`).
- The router's metrics are in-memory attributes; persistence and rolling-window aggregation are not implemented by this class itself.
- Gateway failover orchestration and transaction-state updates should be documented from their respective service implementations, not inferred from this router alone.

## Source
Implementation: `app/gateways/router.py`
