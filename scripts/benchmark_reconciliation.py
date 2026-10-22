import time
from decimal import Decimal
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from app.main import app, GATEWAYS
from app.db.session import SessionLocal
from app.models.transaction import Transaction
from app.state_machine.states import PaymentState
from app.gateways.schemas import GatewayOutcome

N = 10_000
merchant = "reconciliation_benchmark_only"
db = SessionLocal()
ids = []

try:
    existing = db.query(Transaction).filter(
        Transaction.merchant_id == merchant
    ).count()
    if existing:
        raise RuntimeError(
            f"Benchmark merchant already has {existing} rows; refusing to reuse them."
        )
    if not GATEWAYS:
        raise RuntimeError("No configured gateways found.")

    gateway_names = [g.name for g in GATEWAYS]
    gateway_name = gateway_names[0]

    rows = [
        Transaction(
            merchant_id=merchant,
            merchant_order_id=f"recon_bench_{i}",
            amount=Decimal("100.00"),
            currency="INR",
            status=PaymentState.AUTH_UNKNOWN.value,
            selected_gateway=gateway_name,
            gateway_reference=f"recon_bench_ref_{i}",
        )
        for i in range(N)
    ]
    db.add_all(rows)
    db.commit()
    ids = [row.id for row in rows]
    print(f"Seeded transactions: {len(ids)}")

    mocks = []
    for name in gateway_names:
        g = Mock()
        g.name = name
        g.get_status.return_value = Mock(
            outcome=GatewayOutcome.AUTHORISED,
            message="Synthetic benchmark response",
        )
        mocks.append(g)

    start = time.perf_counter()
    with patch("app.main.GATEWAYS", mocks):
        with TestClient(app) as client:
            response = client.post("/api/v1/reconciliation/trigger")
    elapsed = time.perf_counter() - start

    print(f"HTTP status: {response.status_code}")
    print(f"Elapsed: {elapsed:.2f} seconds")
    print(f"Target (<30 sec): {'PASS' if elapsed < 30 else 'FAIL'}")
    print(f"Response: {response.text[:1500]}")

finally:
    if ids:
        try:
            from app.models.transaction_state_log import TransactionStateLog
            from app.models.reconciliation_anomaly import ReconciliationAnomaly

            db.query(ReconciliationAnomaly).filter(
                ReconciliationAnomaly.transaction_id.in_([str(x) for x in ids])
            ).delete(synchronize_session=False)
            db.query(TransactionStateLog).filter(
                TransactionStateLog.transaction_id.in_(ids)
            ).delete(synchronize_session=False)
            db.query(Transaction).filter(Transaction.id.in_(ids)).delete(
                synchronize_session=False
            )
            db.commit()
            print(f"Cleaned up synthetic transactions: {len(ids)}")
        except Exception as cleanup_error:
            db.rollback()
            print(f"WARNING: cleanup needs attention: {cleanup_error}")
    db.close()
