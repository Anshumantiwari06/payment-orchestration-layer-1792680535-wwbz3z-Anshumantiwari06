# Changelog

## Unreleased — assignment completion pass

- Expanded the payment state enum and valid transition graph.
- Added four named simulated gateway adapters and scenario controls.
- Added payment retrieval, capture, void, refund, timeline, gateway health/metrics/configuration, routing config, analytics, webhook, and reconciliation API routes.
- Added persistent webhook event deduplication and reconciliation anomaly models/migration.
- Added optional API-key middleware and HMAC-SHA256 mock webhook verification.
- Added OpenAPI specification, state-machine and routing docs, README, and PDF review notes.
- Corrected Dockerfile shell continuation and pinned Compose PostgreSQL to version 15 for the assignment harness.

### Known limitations

- Mock-only adapters; no live gateway integrations.
- Weighted selection and circuit breakers exist, but live per-factor metrics and database-persisted dynamic scoring are not complete.
- Webhooks are stored/deduplicated, but a durable queue/DLQ, exponential retry worker, provider-specific signature formats, and out-of-order event buffering are not complete.
- Reconciliation is manual/on-demand against mock status, not a scheduled settlement-report import; run IDs are anomaly IDs rather than persisted reconciliation-run IDs.
- Partial amounts are accepted by the API but aggregate captured/refunded balances are not persisted, so partial-capture/refund accounting is not yet financially complete.
- No load benchmark or all-15-scenario pass claim is made.


## Completion pass — 2026-10-21

- Implemented weighted five-factor gateway scoring and runtime EWMA success/latency observations, plus payment-method compatibility filtering.
- Added 15 deterministic mock failure scenarios and table-driven scenario tests.
- Added explicit webhook retry API and bounded database polling worker; wired worker into Docker Compose.
- Persisted reconciliation run summaries and associated anomaly records.
- Added a PostgreSQL trigger preventing UPDATE/DELETE on the transaction state audit log.
- Included valid/invalid state-transition coverage tests and expanded project documentation.
- Validation in the current environment: Python compilation and 110 unit tests pass; the gateway/state-machine-focused test subset reports 83% coverage. Full API/database integration tests and live PostgreSQL migration execution remain unverified here because the `psycopg` driver is unavailable in this environment.
