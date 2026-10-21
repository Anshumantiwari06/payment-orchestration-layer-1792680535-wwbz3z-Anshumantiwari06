# Payment Orchestration Layer with Multi-Gateway Failover

Educational backend project using FastAPI, SQLAlchemy, PostgreSQL, Alembic and simulated gateways. **No real payment gateway requests are made.** This is not production-ready or PCI-certified.

## Local setup (Windows PowerShell)

1. Copy `.env.example` to `.env` and set a local PostgreSQL user/password/database.
2. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. Apply migrations and start the server:

   ```powershell
   alembic upgrade head
   uvicorn app.main:app --reload
   ```
4. Open `http://127.0.0.1:8000/docs` for generated OpenAPI docs.
5. Run tests and coverage after PostgreSQL dependencies are installed:

   ```powershell
   pytest -q
   pytest -q --cov=app --cov-report=term-missing
   ```

   The current isolated unit-test run reports 83% coverage across the gateway and state-machine modules only. This is not a whole-application coverage figure.

## Docker

Set `DB_USER`, `DB_PASSWORD`, and `DB_NAME` in a local `.env`, then run `docker compose up --build`. PostgreSQL 15 is used in Compose to match the assignment's benchmark environment. The host port 5432 must be free.

## API overview

- `POST /api/v1/payments` create a transaction
- `POST /api/v1/payments/{id}/authorize` authorize with `Idempotency-Key`
- `POST /api/v1/payments/{id}/capture`, `/void`, `/refund`
- `GET /api/v1/payments/{id}`, `/timeline`, `/refunds`
- `POST /api/v1/webhooks/{razorpay|stripe|payu|upi}` signed mock webhook receiver; `POST /api/v1/webhooks/events/{event_id}/retry`
- `POST /api/v1/gateways/{name}/scenarios/{scenario}` to inject a one-shot mock failure
- `GET /api/v1/gateways`, `/gateways/{name}/health`, `/metrics`
- `GET/PUT /api/v1/routing/config`; `GET /api/v1/routing/scores?payment_method=card`
- `POST /api/v1/reconciliation/trigger`; `GET /api/v1/reconciliation/reports/{run_uuid}` (or an anomaly UUID)
- `GET /api/v1/analytics/success-rate`, `/analytics/volume`, `/health`

Webhook signatures use HMAC-SHA256 over the exact raw request body and a gateway-specific environment variable such as `RAZORPAY_WEBHOOK_SECRET`. This is a generic training convention, not a substitute for each provider's official signing format. Set secrets locally; never commit `.env`.

## Limitations to understand

Routing now computes a five-factor score (success rate 35%, P95-latency estimate 20%, cost 20%, circuit health 15%, payment-method compatibility 10%) and uses the score with configured gateway weights. The bundled adapters are still deterministic mocks: success/latency metrics are runtime EWMA estimates and cost is a configurable demo baseline, not live provider telemetry. Reconciliation runs and anomalies are persisted, but this is an on-demand mock-status scan, not settlement-report ingestion. A bounded webhook retry worker is included and runs in Docker Compose; retries are at-least-once and require idempotent event application. Performance targets and all 15 failure scenarios must still be demonstrated with a real PostgreSQL run and load tests. Review `docs/routing-algorithm.md`, `docs/state-machine.md`, and `docs/api-specification.yaml` before making production-readiness claims.


### Financial-operation safety

The mock implementation persists `captured_amount` and `refunded_amount`, rejects captures above the remaining authorized amount, and rejects refunds above the captured-but-not-refunded balance. These counters are local simulation state, not a substitute for provider-side reconciliation. A gateway timeout during capture, void, or refund is an uncertain outcome and must not be blindly retried; the operation remains in its initiated state for reconciliation.

### Webhook observability

Webhook events are signature-checked, deduplicated by `(gateway, event_id)`, and retained with processing status, attempt count, last-attempt timestamp, and error text. Failed events can be retried explicitly through `POST /api/v1/webhooks/events/{event_id}/retry`; the Docker Compose worker polls persisted failed/rejected events with a bounded attempt count. Configure the worker interval/batch size with `WEBHOOK_RETRY_INTERVAL_SECONDS` and `WEBHOOK_RETRY_BATCH_SIZE`.
