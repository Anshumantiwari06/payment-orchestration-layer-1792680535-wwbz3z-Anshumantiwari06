# Payment Orchestration Layer — Requirements

## 1. Project Objective

Build a backend payment orchestration layer that sits between a merchant application and simulated payment gateways.

The system must route payment requests, manage transaction lifecycles, handle gateway failures, prevent duplicate processing, process webhooks, and reconcile transaction records.

All gateway integrations in this assignment are simulated. No real payments will be processed.

## 2. Functional Requirements

### FR-01: Payment Management

- Create and retrieve payment transactions.
- Support authorization, capture, void, and refund operations.
- Track transaction status and payment references.
- Support partial capture and partial refund where required.

### FR-02: Transaction State Machine

- Define transaction states and permitted transitions.
- Reject invalid state transitions.
- Persist a transaction state-transition audit log.
- Handle asynchronous and out-of-order events safely.

### FR-03: Gateway Adapters

- Implement mock adapters for Razorpay, Stripe, PayU, and UPI.
- Use a common interface for gateway operations.
- Simulate successful and failed requests, timeouts, delayed responses, rate limits, and server errors.

### FR-04: Intelligent Gateway Routing

Score eligible gateways using the assignment's weights:

- Success rate: 35%
- Latency: 20%
- Cost: 20%
- Health: 15%
- Payment-method compatibility: 10%

Additional requirements:

- Exclude unavailable or incompatible gateways.
- Record gateway selection and routing information.

### FR-05: Failover and Circuit Breakers

- Implement CLOSED, OPEN, and HALF-OPEN circuit-breaker states.
- Detect gateway failures and recovery.
- Route to an eligible alternative when appropriate.
- Target failover within the specified two-second limit.

### FR-06: Idempotency

- Prevent duplicate payment processing for repeated requests.
- Persist idempotency keys and request hashes.
- Return a conflict for a duplicate request that is still in flight, as specified by the assignment.
- Replay the stored response for a completed duplicate request.
- Reject reuse of a key with a different request payload.
- Protect concurrent requests across multiple server instances.

### FR-07: Webhook Processing

- Provide gateway-specific webhook endpoints.
- Verify provider-appropriate signatures.
- Deduplicate webhook events.
- Handle delayed, duplicated, and out-of-order events.
- Retry failed processing and support dead-letter handling.
- Validate transaction references, amounts, and currencies.

### FR-08: Reconciliation

- Identify stale or inconsistent transactions.
- Query the relevant mock gateway for transaction status.
- Record reconciliation results and discrepancies.
- Support scheduled and manually triggered reconciliation.
- Do not automatically refund a settlement discrepancy.

### FR-09: API and Reporting

- Implement the endpoints required by the assignment.
- Provide gateway health and metrics.
- Support routing and gateway configuration.
- Provide transaction timelines, reconciliation reports, and requested analytics.
- Publish OpenAPI documentation.

## 3. Reliability and Security Requirements

- Use database constraints and appropriate concurrency control.
- Keep transaction state changes consistent and auditable.
- Use exact monetary representations; never use floating-point values for payment amounts.
- Verify webhook signatures before accepting events.
- Avoid holding database transactions or locks during network calls.
- Keep secrets out of source control.
- Apply the authentication and validation requirements specified by the assignment.
- Handle database connection exhaustion safely.
- Use structured logs and correlation/trace IDs.

## 4. Performance Requirements

The following are targets specified in the assignment, not measured results:

- Payment initiation P95 latency: below 500 ms.
- Failover: below 2 seconds.
- Webhook processing P95 latency: below 200 ms.
- Throughput: 100 requests per second for 5 minutes.
- Idempotency check: below 10 ms.
- Reconciliation: below 30 seconds for 10,000 transactions.

Actual benchmark results must be recorded separately. These targets must not be marked as achieved without measurements.

## 5. Testing Requirements

- Unit-test transaction state transitions.
- Test valid and invalid payment operations.
- Test gateway routing and circuit breakers.
- Test idempotency under concurrent requests.
- Test duplicate, invalid, and out-of-order webhooks.
- Test reconciliation discrepancies.
- Execute all 15 failure scenarios in the assignment.
- Verify database integrity after test runs.
- Target at least 80% test coverage, as planned for this project.

### 5.1 Current Verified Test Coverage

The following behavior has been tested during development:

- Gateway failover after a definitive decline.
- No automatic failover after an unknown gateway outcome.
- No automatic failover after a gateway exception or timeout.
- Idempotency conflict for a request that is already in progress.
- Replay of a completed idempotency request without another gateway call.
- API-level replay of a stored response.
- Marking an idempotency record `UNKNOWN` after a gateway timeout.
- Rejecting a retry with the same idempotency key when the previous outcome is `UNKNOWN`.

The latest complete test-suite run reported **31 passed in 2.37 seconds**. The gateway failover test file separately reported 3 passed, and the authorization safety test reported 1 passed.

These results describe the tests executed at that point. The full suite must be rerun after the final dependency and code changes.

The following remain to be verified independently:

- Concurrent idempotency requests.
- All 15 assignment-specified failure scenarios.
- Database integrity after test runs.
- At least 80% test coverage.
- Performance targets under the required workloads.

## 6. Delivery Requirements

- Python backend using FastAPI.
- PostgreSQL persistence.
- Database migrations.
- Automated test suite.
- Docker and Docker Compose environment.
- OpenAPI documentation.
- Architecture and setup documentation.
- Performance and failure-scenario reports.
- Documentation of the five suspected deliberate errors mentioned in the assignment, after independent verification.
- Repository handover according to the assignment instructions.

### 6.1 Current Development Environment and Dependencies

The project currently uses:

- Python 3.13.14.
- FastAPI.
- SQLAlchemy.
- PostgreSQL with Psycopg.
- Alembic.
- Pytest.
- FastAPI `TestClient` with `httpx2`.

The existing `requirements.txt` was reviewed. The installed environment contains `httpx2==2.16.0` and `httpcore2==2.16.0`. These dependencies were identified as missing from the requirements file and proposed for inclusion.

The dependency update must be saved and verified by installing from `requirements.txt` before the final commit.

This section documents the current development setup; it does not claim that all delivery requirements have been completed.

## 7. Scope Boundaries

### In Scope

- Simulated payment gateways.
- Payment orchestration and routing.
- Transaction lifecycle and audit history.
- Idempotency, webhook processing, and reconciliation.
- Testing, monitoring, and containerized execution.

### Out of Scope Unless Explicitly Required

- Processing real customer payments.
- Production credentials or real gateway transactions.
- Unrequested frontend development.
- Deploying a live payment service.

## 8. Requirement Traceability

Each requirement must eventually map to:

1. An implementation component.
2. One or more automated tests.
3. A verification result.

Maintain the exact endpoint list, failure scenarios, and assessment criteria from the