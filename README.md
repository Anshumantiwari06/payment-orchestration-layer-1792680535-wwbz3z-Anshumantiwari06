# Payment Orchestration Layer with Multi-Gateway Failover

An educational backend project built with FastAPI, SQLAlchemy, PostgreSQL, Alembic, and simulated payment gateways. **No real payment gateway requests are made.** This project is not production-ready or PCI-certified.

## Local Setup (Windows PowerShell)

1. Copy `.env.example` to `.env` and configure your local PostgreSQL credentials.

2. Create and activate a virtual environment, then install dependencies:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. Apply database migrations and start the API:

   ```powershell
   alembic upgrade head
   uvicorn app.main:app --reload
   ```

   Run these commands in the same activated environment. Keep the API running in that terminal.

4. Open `http://127.0.0.1:8000/docs` to explore the generated OpenAPI documentation.

5. Run tests and measure application coverage:

   ```powershell
   pytest -q
   pytest -q --cov=app --cov-report=term-missing
   ```

   Latest verified full test run: **242 tests passed**. Whole-application coverage: **84%**, measured across `app/`.

## Docker

Set `DB_USER`, `DB_PASSWORD`, and `DB_NAME` in your local `.env` file, then run:

```powershell
docker compose up --build
```

Docker Compose uses PostgreSQL 15 to match the assignment's benchmark environment. Ensure host port `5432` is available before starting the services.

## API Overview

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/payments` | Create a transaction |
| POST | `/api/v1/payments/{id}/authorize` | Authorize a payment using an `Idempotency-Key` |
| POST | `/api/v1/payments/{id}/capture` | Capture an authorized payment |
| POST | `/api/v1/payments/{id}/void` | Void a payment authorization |
| POST | `/api/v1/payments/{id}/refund` | Refund a captured payment |
| GET | `/api/v1/payments/{id}` | Retrieve payment details |
| GET | `/api/v1/payments/{id}/timeline` | Retrieve payment history |
| GET | `/api/v1/payments/{id}/refunds` | Retrieve refund records |
| POST | `/api/v1/webhooks/{razorpay\|stripe\|payu\|upi}` | Receive a signed mock webhook |
| POST | `/api/v1/webhooks/events/{event_id}/retry` | Retry a failed webhook event |
| POST | `/api/v1/gateways/{name}/scenarios/{scenario}` | Inject a one-shot simulated gateway failure |
| GET | `/api/v1/gateways` | List configured gateways |
| GET | `/api/v1/gateways/{name}/health` | Retrieve gateway health |
| GET | `/api/v1/gateways/metrics` | Retrieve gateway metrics |
| GET / PUT | `/api/v1/routing/config` | Read or update routing configuration |
| GET | `/api/v1/routing/scores?payment_method=card` | Inspect gateway routing scores |
| POST | `/api/v1/reconciliation/trigger` | Trigger reconciliation |
| GET | `/api/v1/reconciliation/reports/{run_uuid}` | Retrieve a reconciliation report or anomaly |
| GET | `/api/v1/analytics/success-rate` | Retrieve payment success-rate analytics |
| GET | `/api/v1/analytics/volume` | Retrieve payment volume analytics |
| GET | `/health` | Check API health |

Webhook signatures use HMAC-SHA256 over the exact raw request body and a gateway-specific environment variable, such as `RAZORPAY_WEBHOOK_SECRET`. This is a generic training convention, not a substitute for each provider's official signing format. Configure secrets locally and never commit `.env`.

## Performance and Verification

The following results were observed in local test runs:

- **Payment initiation:** A five-minute benchmark against the local Docker deployment completed 30,000 requests at approximately 99.98 requests/second, with zero errors and 81.9 ms P95 latency.
- **Reconciliation:** A synthetic benchmark processed 10,000 seeded transactions through the reconciliation trigger endpoint in 0.77 seconds. The endpoint returned HTTP 202, reported zero anomalies and zero errors, and the synthetic transactions were cleaned up afterward.
- **Webhook processing:** A benchmark of 100 valid, HMAC-signed webhook requests returned HTTP 200 for all requests, with 18.62 ms P95 latency.
- **Test suite:** The latest reported full test run passed 242 tests, with 84% application coverage.

These are environment-specific results for the tested scenarios, not guarantees of production throughput or latency. The reconciliation benchmark used simulated gateway responses and does not measure real payment-provider performance.

## Limitations

### Gateway routing

Routing uses five factors: success rate (35%), P95-latency estimate (20%), cost (20%), circuit health (15%), and payment-method compatibility (10%). The router combines the resulting score with configured gateway weights.

Gateway adapters are deterministic mocks. Success and latency observations use runtime EWMA estimates, while cost is a configurable demo baseline. These are not live provider telemetry or real transaction costs.

### Reconciliation

Reconciliation is an on-demand scan against simulated gateway status responses. Reconciliation runs and anomalies are persisted, but the project does not ingest real settlement reports. The benchmark above measures only the tested local mock-gateway path.

### Financial-operation safety

The mock implementation persists `captured_amount` and `refunded_amount`, rejects captures above the remaining authorized amount, and rejects refunds above the captured-but-not-refunded balance. These counters represent local simulation state and do not replace provider-side reconciliation.

A timeout during capture, void, or refund can leave the actual outcome uncertain. Such operations must not be blindly retried; they should remain subject to reconciliation and appropriate recovery handling.

### Webhook processing

Webhook events are signature-checked, deduplicated by `(gateway, event_id)`, and retained with their processing status, attempt count, last-attempt timestamp, and error text. Failed events can be retried through the API, and the Docker Compose worker polls persisted failed or rejected events with a bounded attempt count.

Retries are at-least-once, so event application must be idempotent. Configure the worker interval and batch size using `WEBHOOK_RETRY_INTERVAL_SECONDS` and `WEBHOOK_RETRY_BATCH_SIZE`.

### Production readiness

The project is an educational implementation with simulated gateways. The reported benchmarks do not prove that every assignment performance target or all 15 failure scenarios have passed. It is not production-ready or PCI-certified.

Before submission, verify that any linked supporting documentation paths exist in the repository, including the routing algorithm, state machine, and API specification documents.