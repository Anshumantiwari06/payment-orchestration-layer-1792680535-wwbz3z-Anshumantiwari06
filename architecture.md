# Payment Orchestration Layer — Architecture

## 1. Overview
The Payment Orchestration Layer is a FastAPI-based backend that coordinates mock payment gateways, maintains transaction state, records audit history, processes webhooks, and reconciles internal transaction records against simulated gateway status.

**Important:** This project uses mock gateways. It does not process real payments.

## 2. Technology Stack
- **API:** Python, FastAPI, Uvicorn
- **Database:** PostgreSQL 15
- **ORM and migrations:** SQLAlchemy, Alembic
- **Gateway integrations:** Razorpay, Stripe, PayU, and UPI mock adapters
- **Testing:** pytest
- **Deployment:** Docker Compose
- **Background processing:** Webhook retry worker

## 3. High-Level Components

### API Layer
`app/main.py` exposes HTTP endpoints for payment creation, authorization, capture, void, refund, transaction lookup, timelines, gateway configuration, analytics, webhooks, and reconciliation.

### Gateway Adapters
`app/gateways/adapters.py` provides mock gateway adapters. The API initializes Razorpay, Stripe, PayU, and UPI adapters.

### Gateway Router
`app/gateways/router.py` scores gateways using success rate, latency, cost, health, and payment-method compatibility. Configured gateway weights influence selection. Gateways with open circuit breakers or unsupported payment methods are excluded.

### Payment Orchestrator
`app/gateways/orchestrator.py` coordinates payment authorization with the gateway router.

### Transaction Service and State Machine
`app/services/transaction_service.py` handles transaction creation, state changes, and authorization. `app/state_machine/` defines payment states and validates permitted transitions.

### Database Layer
`app/db/` manages database access. SQLAlchemy models represent transactions, state-transition logs, webhook events, reconciliation runs, and reconciliation anomalies. Alembic applies schema migrations.

### Webhook Processing
The API verifies webhook signatures using HMAC-SHA256, persists incoming events, deduplicates repeated gateway event IDs, and applies valid events to transactions. Failed events can be retried through the API or the background worker.

### Reconciliation
The reconciliation endpoint checks selected transactions against mock gateway status responses. It records discrepancies as anomalies and flags manual review where necessary. Automatic refunds are not triggered by reconciliation.

## 4. Payment Request Flow

1. A merchant submits a payment creation request.
2. The API validates the request and creates a transaction.
3. The merchant authorizes the transaction with an idempotency key.
4. The transaction service and orchestrator select an eligible mock gateway.
5. The gateway returns a simulated outcome.
6. The transaction state and gateway reference are updated according to the result.
7. State-transition history is stored for auditability.
8. The merchant can query payment details and transaction timelines.

Capture, void, and refund operations use the selected gateway and enforce transaction-state and amount limits.

## 5. Webhook Flow

1. A gateway sends a webhook to `/api/v1/webhooks/{gateway_name}`.
2. The API verifies the HMAC-SHA256 signature against the raw request body.
3. The event is persisted with its gateway event ID.
4. Duplicate events are ignored using database uniqueness constraints.
5. Valid events are applied to the related transaction.
6. Failed events retain status and error information for retry.
7. The retry worker processes eligible persisted webhook events.

## 6. Reconciliation Flow

1. A reconciliation run is created.
2. Eligible transactions with a gateway reference are selected.
3. The original mock gateway is queried for status.
4. Unknown responses and lookup errors are recorded.
5. Status mismatches create reconciliation anomalies and may trigger a permitted state transition to `RECONCILIATION_MISMATCH`.
6. The run records its outcome, checked count, anomaly count, and details.
7. Reports are available through the reconciliation report endpoint.

## 7. Database and State Integrity

- Transaction records persist payment amounts, status, and gateway details.
- State-transition logs retain previous state, new state, reason, event type, and correlation ID.
- Capture and refund operations enforce remaining-balance constraints.
- Idempotency prevents unintended duplicate authorization processing.
- Database transactions and rollback handling protect updates when errors occur.

## 8. Runtime Deployment

Docker Compose defines three services:

- `api`: runs Alembic migrations and starts Uvicorn.
- `db`: runs PostgreSQL 15 with a health check and persistent volume.
- `webhook-retry-worker`: runs the webhook retry worker.

The API and worker connect to PostgreSQL using the Docker service hostname `db`. Environment-specific settings are supplied through `.env`.

## 9. Health and Observability

- `GET /health` and `GET /api/v1/health` check database connectivity.
- Gateway endpoints expose gateway status, circuit state, metrics, and mock scenario configuration.
- Payment timelines expose state-transition history.
- Webhook endpoints expose event status and retry information.
- Reconciliation endpoints expose run reports and anomalies.

## 10. Security and Limitations

- Optional API-key authentication is enabled when `API_KEY` is configured.
- Webhook signatures are compared using constant-time comparison.
- Secrets must be supplied through environment variables and must not be committed to source control.
- Gateway behavior and status lookups are simulated.
- Routing metric defaults are demonstration baselines, not verified live provider telemetry.
- Real provider integration, production credentials, and production payment processing are outside this mock implementation's scope.

## 11. Key Source Locations

| Component | Location |
|---|---|
| HTTP API | `app/main.py` |
| Gateway router | `app/gateways/router.py` |
| Gateway orchestrator | `app/gateways/orchestrator.py` |
| Gateway adapters | `app/gateways/adapters.py` |
| Transaction service | `app/services/transaction_service.py` |
| Idempotency | `app/services/idempotency_service.py` |
| State machine | `app/state_machine/` |
| Database models | `app/models/` |
| Webhook retry service | `app/services/webhook_retry_service.py` |
| Webhook retry worker | `app/workers/webhook_retry_worker.py` |
| Migrations | `migrations/` |
| Tests | `tests/` |
| Container orchestration | `docker-compose.yml` |
