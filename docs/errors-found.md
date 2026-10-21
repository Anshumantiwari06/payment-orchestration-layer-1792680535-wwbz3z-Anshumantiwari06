# Deliberate technical errors in the assignment PDF — review notes

The PDF states that the training material contains five deliberate errors but does not identify their locations in this section. These are candidate issues worth flagging for mentor review; they should not be represented as confirmed intended bonus answers without validating the exact source passages.

1. **HMAC algorithm typos in the gateway table:** the extracted PDF text shows malformed algorithm names (e.g. “HMAC-SHA256” split/garbled for Razorpay and “HMAC-SHA512” for PayU). Verify provider documentation; webhook signature schemes are provider-specific and must not be inferred from a damaged table.
2. **State-machine wording:** the document sometimes treats a gateway decline as a failover-worthy infrastructure failure. A definitive issuer decline should not be retried on another gateway; only eligible technical failures may be retried, and uncertain outcomes require reconciliation.
3. **Failover after authorization timeout:** blindly failing over after an ambiguous timeout can create a duplicate charge if the first gateway actually authorized. Query the original gateway or reconcile first unless idempotency guarantees establish a safe retry.
4. **Locking recommendation:** holding a database row lock during a slow external gateway call is unsafe for throughput and connection-pool health. Persist an intermediate state, release the DB transaction, call the gateway, then reacquire/validate before persisting the outcome.
5. **“Immutable” audit trail:** a normal mutable SQL table is not immutable merely because the application appends rows. Enforce append-only permissions/triggers and operational controls if strict immutability is required.

These are engineering review observations, not a claim that these are exactly the five planted errors.
