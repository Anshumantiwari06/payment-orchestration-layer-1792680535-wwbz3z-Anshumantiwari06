
# Architecture Decision Records

## ADR-001: Use a Modular Monolith

Status: Accepted

Decision:
Build the initial system as one FastAPI application with
separate modules for API routes, services, gateway adapters,
database access, schemas, and domain models.

Reason:
This reduces deployment complexity while keeping business logic
organized and testable.

Consequence:
Modules must maintain clear responsibilities and avoid unnecessary
coupling. Separate services can be considered later if justified.

## ADR-002: Use PostgreSQL as the System of Record

Status: Accepted

Decision:
Persist payment transactions, state-transition history, idempotency
records, webhook processing records, and reconciliation outcomes
in PostgreSQL.

Reason:
The project requires durable records, relational constraints,
transactional updates, and concurrency control.

Consequence:
Database schema changes will be managed through migrations.
Critical correctness rules must be enforced through appropriate
database constraints and application logic.

## ADR-003: Use a Common Gateway Adapter Interface

Status: Accepted

Decision:
Implement Razorpay, Stripe, PayU, and UPI as mock adapters behind
a common interface.

Reason:
The routing and orchestration logic should not depend on the
internal implementation of a particular gateway.

Consequence:
Gateway-specific behaviour stays inside the adapter, while
common payment operations are coordinated by the service layer.

## ADR-004: Centralize Transaction State Transitions

Status: Accepted

Decision:
Use a dedicated mechanism to validate and apply state transitions.

Reason:
Payment operations, webhook events, and reconciliation can
otherwise produce inconsistent transaction states.

Consequence:
All state-changing operations must use the centralized transition
mechanism. Invalid transitions must be rejected and tested.

## ADR-005: Make Payment Initiation Idempotent

Status: Accepted

Decision:
Persist idempotency keys, request hashes, processing status,
and completed responses.

Reason:
Clients may retry requests after network failures or timeouts.
Repeated requests must not cause duplicate payment initiation.

Consequence:
The design must handle simultaneous requests, key reuse with
different payloads, and ambiguous gateway outcomes.

## ADR-006: Separate Database Transactions from Gateway Calls

Status: Accepted

Decision:
Do not hold database transactions or row locks open while waiting
for gateway network operations.

Reason:
Slow or unresponsive gateways can otherwise cause lock contention,
long-lived connections, and connection-pool exhaustion.

Consequence:
The application must persist intermediate states and safely
coordinate the gateway result with subsequent database updates.

## ADR-007: Use Automated Tests from the Start

Status: Accepted

Decision:
Add unit and integration tests as features are implemented.

Reason:
Payment correctness depends on handling failure conditions,
not only on successful requests.

Consequence:
Every critical feature must have tests. The final suite must
cover all 15 assignment failure scenarios.

## ADR-008: Use Mock Gateways Only

Status: Accepted

Decision:
Simulate all payment gateway interactions.

Reason:
The assignment specifies a simulated environment rather than
real payment processing.

Consequence:
No real gateway credentials, customer payments, or live
payment transactions are required for the implementation.
