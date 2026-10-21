# Routing algorithm

The router scores every compatible, non-open gateway using five normalized factors:

| Factor | Weight | Runtime behavior |
|---|---:|---|
| Success rate | 35% | EWMA updated after each authorization response; `UNKNOWN` counts as technical failure, definitive declines count as a valid gateway response |
| P95 latency estimate | 20% | EWMA latency estimate updated from observed authorization call duration |
| Cost | 20% | Adapter baseline in basis points; demo configuration, not provider pricing |
| Health | 15% | Zero for an OPEN circuit breaker, one otherwise |
| Payment-method compatibility | 10% | Zero for an unsupported payment method; incompatible gateways are excluded |

The five-factor score is multiplied by the administrator-configured gateway weight and used as the weighted selection probability. `GET /api/v1/routing/scores?payment_method=card` shows the current score breakdown. Demo metrics are in-memory and reset on process restart; they are not real provider telemetry.

Circuit breakers use CLOSED, OPEN and HALF_OPEN states. Unknown authorization outcomes are never retried through another gateway because doing so could create duplicate charges. The orchestrator only fails over on a definitive decline in this mock contract. A production integration must distinguish issuer declines from retryable provider/transport failures using provider-specific error codes.
