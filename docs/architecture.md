
# Payment Orchestration Layer — Architecture

## 1. Architectural Style

The initial implementation will use a modular monolith.

FastAPI, business services, gateway adapters, and database access
will run within one Python application.

PostgreSQL will persist transactions, configuration, event-processing
records, and audit history.

Gateway integrations will be simulated.

This design keeps the initial deployment simple while maintaining
clear boundaries between components.

## 2. High-Level Components

### API Layer
Responsibilities:
- Receive HTTP requests.
- Validate request and response schemas.
- Apply authentication and request-level controls.
- Return consistent HTTP responses.

Location: app/api/

### Core Configuration
Responsibilities:
- Load application settings.
- Configure logging and tracing.
- Define shared exceptions and constants.

Location: app/core/

### Database Layer
Responsibilities:
- Manage database sessions and connections.
- Define persistence conventions.
- Support migrations and transaction boundaries.

Locations:
- app/db/
- app/models/

### Service Layer
Responsibilities:
- Coordinate payment operations.
- Enforce transaction lifecycle rules.
- Coordinate idempotency, routing, and reconciliation.
- Keep business logic independent of HTTP handlers.

Location: app/services/

### Gateway Adapters
Responsibilities:
- Implement a common gateway interface.
- Simulate provider-specific request and response behaviour.
- Produce deterministic outcomes for automated tests.

Location: app/gateways/

### Schemas
Responsibilities:
- Validate incoming request data.
- Define API response formats.
- Keep external API contracts separate from database models.

Location: app/schemas/

## 3. Payment Initiation Flow

1. The merchant submits a payment request.
2. The API validates the request.
3. The idempotency service checks for an existing request.
4. A transaction is created and persisted.
5. The router identifies eligible gateways.
6. The router selects a gateway using configured scoring.
7. The orchestration service calls the selected mock adapter.
8. The result is validated and persisted.
9. The transaction state and audit log are updated.
10. The API returns the resulting transaction status.

The implementation must account for requests that time out,
events that arrive early, and concurrent requests.

A gateway timeout does not necessarily prove that the payment failed.

## 4. Gateway Routing

The router considers:
- Historical success rate.
- Latency.
- Cost.
- Gateway health.
- Payment-method compatibility.

The configured weights are:
- Success rate: 35%
- Latency: 20%
- Cost: 20%
- Health: 15%
- Payment-method fit: 10%

Unavailable and incompatible gateways must not be selected.

The scoring implementation must define normalization, missing-data
handling, tie-breaking, and the treatment of unhealthy gateways.

## 5. Transaction State and Audit

Transaction state changes must pass through a centralized
state-transition mechanism.

Each accepted transition must record:
- Transaction identifier.
- Previous state.
- New state.
- Event or reason.
- Timestamp.
- Relevant correlation information.

Invalid transitions must be rejected and tested.

Audit history must not be silently rewritten by ordinary
transaction-update operations.

## 6. Webhook Processing

Webhook handling must:
- Verify the provider-appropriate signature.
- Persist event identity and processing status.
- Prevent duplicate event effects.
- Handle delayed and out-of-order delivery.
- Retry transient processing failures.
- Record events that exhaust the retry policy.

Webhook processing must validate the event against the transaction
and must not blindly overwrite newer or more authoritative state.

## 7. Reconciliation

The reconciliation engine identifies transactions whose internal
state may differ from gateway state.

It must:
- Identify stale transactions.
- Query the relevant mock gateway.
- Compare internal and gateway records.
- Persist reconciliation outcomes.
- Record and report discrepancies.
- Apply state changes only after validation.

A discrepancy must not automatically trigger a refund.

## 8. Database and Concurrency

PostgreSQL is the system of record.

Database constraints and transaction boundaries must protect
against duplicate records and conflicting updates.

Use short database transactions. Do not hold database locks
while waiting for gateway network operations.

Use an appropriate locking or optimistic-concurrency strategy
for state changes.

Store monetary amounts using NUMERIC or integer minor units,
never floating-point types.

## 9. Observability

The application should provide:
- Structured logs.
- Request and transaction correlation IDs.
- Gateway latency and outcome metrics.
- Circuit-breaker state visibility.
- Health checks.
- Reconciliation and webhook processing status.

Sensitive credentials and payment secrets must not appear in logs.

## 10. Testing Strategy

Unit tests:
- State transitions.
- Routing score calculations.
- Idempotency rules.
- Circuit-breaker behaviour.

Integration tests:
- API and database operations.
- Payment lifecycle.
- Webhook ingestion.
- Reconciliation.

Failure tests:
- The 15 scenarios specified by the assignment.
- Concurrent requests.
- Delayed and duplicate events.
- Database and gateway failures.

Performance tests:
- Latency.
- Throughput.
- Failover.
- Idempotency checks.
- Reconciliation duration.

## 11. Initial Deployment

The initial environment will use:
- Python and FastAPI.
- PostgreSQL.
- Docker Compose.
- Automated tests.

Redis or a separate background worker will be introduced only
if needed to meet the assignment's persistence, retry,
concurrency, or performance requirements.
