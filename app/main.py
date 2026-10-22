import hashlib, hmac, json, os
from decimal import Decimal
from uuid import UUID
from fastapi import FastAPI, Depends, HTTPException, Header, Request, Query
from sqlalchemy import text, select
from datetime import datetime, timezone
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.transaction import (
    TransactionCreateRequest,
    TransactionStateChangeRequest,
)
from app.schemas.operations import AmountRequest, WebhookRequest
from app.services.transaction_service import (
    create_transaction,
    change_transaction_state,
    authorize_transaction,
)
from app.services.idempotency_service import IdempotencyConflictError
from app.models.transaction import Transaction
from app.models.transaction_state_log import TransactionStateLog
from app.models.webhook_event import WebhookEvent
from app.models.reconciliation_anomaly import ReconciliationAnomaly
from app.models.reconciliation_run import ReconciliationRun
from app.services.webhook_retry_service import apply_webhook_event
from app.gateways.adapters import (
    RazorpayAdapter,
    StripeAdapter,
    PayUAdapter,
    UPIAdapter,
)
from app.gateways.router import GatewayRouter
from app.gateways.orchestrator import PaymentOrchestrator
from app.gateways.schemas import GatewayOutcome
from app.state_machine.states import PaymentState
from app.state_machine.engine import transition_transaction, InvalidTransitionError

app = FastAPI(
    title="Payment Orchestration Layer",
    version="2.0.0",
    description="Mock-gateway payment orchestration backend; no real payments are processed.",
)


@app.middleware("http")
async def optional_api_key_auth(request: Request, call_next):
    """Enable merchant API-key protection when API_KEY is configured."""
    configured_key = os.getenv("API_KEY")
    public_paths = {
        "/",
        "/health",
        "/api/v1/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
    if (
        configured_key
        and request.url.path not in public_paths
        and not request.url.path.startswith("/docs/")
    ):
        supplied = request.headers.get("X-API-Key", "")
        if not hmac.compare_digest(configured_key, supplied):
            from starlette.responses import JSONResponse

            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Missing or invalid API key",
                    }
                },
            )
    return await call_next(request)


GATEWAYS = [RazorpayAdapter(), StripeAdapter(), PayUAdapter(), UPIAdapter()]
ROUTER = GatewayRouter(
    GATEWAYS, weights={g.name: w for g, w in zip(GATEWAYS, [35, 25, 25, 15])}
)
ORCHESTRATOR = PaymentOrchestrator(ROUTER)


@app.get("/")
def root():
    return {
        "service": "Payment Orchestration Layer",
        "status": "running",
        "mode": "mock-gateways",
    }


@app.get("/health")
@app.get("/api/v1/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except SQLAlchemyError:
        raise HTTPException(
            503, detail={"status": "unhealthy", "database": "unavailable"}
        )


@app.post("/transactions", status_code=201)
@app.post("/api/v1/payments", status_code=201)
def create_new_transaction(
    request: TransactionCreateRequest, db: Session = Depends(get_db)
):
    try:
        t = create_transaction(db, request)
        return {
            "id": str(t.id),
            "transaction_id": str(t.id),
            "merchant_id": t.merchant_id,
            "merchant_order_id": t.merchant_order_id,
            "amount": str(t.amount),
            "currency": t.currency,
            "status": t.status,
        }
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500, detail="Database error while creating transaction")


@app.post("/transactions/change-state", status_code=201)
def change_state(request: TransactionStateChangeRequest, db: Session = Depends(get_db)):
    try:
        t = change_transaction_state(
            db,
            request.transaction_id,
            request.new_state,
            request.reason,
            request.correlation_id,
        )
        return {"id": str(t.id), "status": t.status}
    except ValueError as e:
        raise HTTPException(
            404 if "not found" in str(e).lower() else 409, detail=str(e)
        )
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            500, detail="Database error while changing transaction state"
        )


@app.post("/transactions/{transaction_id}/authorize")
@app.post("/api/v1/payments/{transaction_id}/authorize")
def authorize_existing_transaction(
    transaction_id: UUID,
    idempotency_key: str | None = Query(default=None),
    payment_method: str = Query(default="card", min_length=1, max_length=30),
    idempotency_header: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    idempotency_key = idempotency_header or idempotency_key
    if not idempotency_key:
        raise HTTPException(
            400,
            detail="Idempotency-Key header or idempotency_key query parameter is required",
        )
    try:
        t = db.get(Transaction, transaction_id)
        if t is None:
            raise HTTPException(404, detail="Transaction not found")

        result = authorize_transaction(
            db,
            transaction_id,
            ORCHESTRATOR,
            idempotency_key,
            payment_method=payment_method.lower(),
        )

        # Completed idempotency requests must replay the stored response unchanged.
        if isinstance(result, dict):
            return result

        return {
            "transaction_id": str(result.id),
            "status": result.status,
            "gateway": result.selected_gateway,
            "gateway_reference": result.gateway_reference,
        }

    except HTTPException:
        raise
    except IdempotencyConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        status_code = 404 if "not found" in str(e).lower() else 409
        raise HTTPException(status_code=status_code, detail=str(e)) from e
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Database error while authorizing transaction",
        )


@app.get("/api/v1/payments")
def find_payment(
    merchant_order_id: str = Query(...),
    merchant_id: str = Query(...),
    db: Session = Depends(get_db),
):
    t = db.scalar(
        select(Transaction).where(
            Transaction.merchant_order_id == merchant_order_id,
            Transaction.merchant_id == merchant_id,
        )
    )
    if t is None:
        raise HTTPException(404, detail="Payment not found")
    return payment_json(t)


def payment_json(t):
    return {
        "id": str(t.id),
        "merchant_id": t.merchant_id,
        "merchant_order_id": t.merchant_order_id,
        "amount": str(t.amount),
        "currency": t.currency,
        "status": t.status,
        "gateway": t.selected_gateway,
        "gateway_reference": t.gateway_reference,
        "captured_amount": str(t.captured_amount or 0),
        "refunded_amount": str(t.refunded_amount or 0),
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


@app.get("/api/v1/payments/{transaction_id}")
def get_payment(transaction_id: UUID, db: Session = Depends(get_db)):
    t = db.get(Transaction, transaction_id)
    if not t:
        raise HTTPException(404, detail="Payment not found")
    return payment_json(t)


@app.get("/api/v1/payments/{transaction_id}/timeline")
def payment_timeline(transaction_id: UUID, db: Session = Depends(get_db)):
    if not db.get(Transaction, transaction_id):
        raise HTTPException(404, detail="Payment not found")
    rows = db.scalars(
        select(TransactionStateLog)
        .where(TransactionStateLog.transaction_id == transaction_id)
        .order_by(TransactionStateLog.created_at)
    ).all()
    return [
        {
            "previous_state": r.previous_state,
            "new_state": r.new_state,
            "event_type": r.event_type,
            "reason": r.reason,
            "correlation_id": r.correlation_id,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


def operate(transaction_id: UUID, operation: str, request: AmountRequest, db: Session):
    """Run a simulated financial operation while enforcing local balance limits.

    The DB state and amount counters are committed only after a definitive mock
    gateway response. An UNKNOWN response is intentionally not treated as failure.
    """
    t = db.scalar(
        select(Transaction).where(Transaction.id == transaction_id).with_for_update()
    )
    if not t:
        raise HTTPException(404, detail="Payment not found")
    if not t.selected_gateway or not t.gateway_reference:
        raise HTTPException(409, detail="Payment has no confirmed gateway reference")
    gateway = next((g for g in GATEWAYS if g.name == t.selected_gateway), None)
    if not gateway:
        raise HTTPException(503, detail="Selected gateway is unavailable")

    total = Decimal(t.amount)
    captured = Decimal(t.captured_amount or 0)
    refunded = Decimal(t.refunded_amount or 0)
    if operation == "capture":
        if t.status not in {
            PaymentState.AUTHORISED.value,
            PaymentState.PARTIALLY_CAPTURED.value,
            PaymentState.CAPTURE_FAILED.value,
        }:
            raise HTTPException(
                409, detail=f"Cannot capture payment in state {t.status}"
            )
        remaining = total - captured
        amount = Decimal(request.amount) if request.amount is not None else remaining
        if amount <= 0 or amount > remaining:
            raise HTTPException(
                409,
                detail=f"Capture amount must be greater than zero and no more than remaining authorized amount {remaining}",
            )
        start = PaymentState.CAPTURE_INITIATED
        result = gateway.capture(
            t.gateway_reference, amount, f"capture:{t.id}:{captured}:{amount}"
        )
        if result.outcome == GatewayOutcome.UNKNOWN:
            # Persist initiated/unknown status; do not repeat an uncertain operation.
            log = transition_transaction(
                t,
                start,
                reason="Capture outcome uncertain; reconcile before retry",
                correlation_id=str(t.id),
            )
            db.add(log)
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise
            raise HTTPException(
                202,
                detail={
                    "message": "Capture outcome unknown; reconciliation required",
                    "transaction_id": str(t.id),
                },
            )
        if result.outcome not in {
            GatewayOutcome.CAPTURED,
            GatewayOutcome.PARTIALLY_CAPTURED,
        }:
            final = PaymentState.CAPTURE_FAILED
        else:
            t.captured_amount = captured + amount
            final = (
                PaymentState.CAPTURED
                if t.captured_amount >= total
                else PaymentState.PARTIALLY_CAPTURED
            )
    elif operation == "void":
        if t.status not in {
            PaymentState.AUTHORISED.value,
            PaymentState.CAPTURE_FAILED.value,
        }:
            raise HTTPException(409, detail=f"Cannot void payment in state {t.status}")
        if captured > 0:
            raise HTTPException(
                409, detail="Cannot void a payment after any amount has been captured"
            )
        amount = total
        start = PaymentState.VOID_INITIATED
        result = gateway.void(t.gateway_reference, f"void:{t.id}")
        if result.outcome == GatewayOutcome.UNKNOWN:
            log = transition_transaction(
                t,
                start,
                reason="Void outcome uncertain; reconcile before retry",
                correlation_id=str(t.id),
            )
            db.add(log)
            db.commit()
            raise HTTPException(
                202,
                detail={
                    "message": "Void outcome unknown; reconciliation required",
                    "transaction_id": str(t.id),
                },
            )
        final = (
            PaymentState.VOIDED
            if result.outcome == GatewayOutcome.VOIDED
            else PaymentState.FAILED
        )
    else:
        if t.status not in {
            PaymentState.CAPTURED.value,
            PaymentState.SETTLED.value,
            PaymentState.PARTIALLY_CAPTURED.value,
            PaymentState.PARTIALLY_REFUNDED.value,
            PaymentState.REFUND_FAILED.value,
        }:
            raise HTTPException(
                409, detail=f"Cannot refund payment in state {t.status}"
            )
        refundable = captured - refunded
        amount = Decimal(request.amount) if request.amount is not None else refundable
        if amount <= 0 or amount > refundable:
            raise HTTPException(
                409,
                detail=f"Refund amount must be greater than zero and no more than refundable balance {refundable}",
            )
        start = PaymentState.REFUND_INITIATED
        result = gateway.refund(
            t.gateway_reference, amount, f"refund:{t.id}:{refunded}:{amount}"
        )
        if result.outcome == GatewayOutcome.UNKNOWN:
            log = transition_transaction(
                t,
                start,
                reason="Refund outcome uncertain; reconcile before retry",
                correlation_id=str(t.id),
            )
            db.add(log)
            db.commit()
            raise HTTPException(
                202,
                detail={
                    "message": "Refund outcome unknown; reconciliation required",
                    "transaction_id": str(t.id),
                },
            )
        if result.outcome in {
            GatewayOutcome.REFUNDED,
            GatewayOutcome.PARTIALLY_REFUNDED,
        }:
            t.refunded_amount = refunded + amount
            final = (
                PaymentState.REFUNDED
                if t.refunded_amount >= captured
                else PaymentState.PARTIALLY_REFUNDED
            )
        else:
            final = PaymentState.REFUND_FAILED
    try:
        log = transition_transaction(
            t, start, reason=f"{operation} initiated", correlation_id=str(t.id)
        )
        db.add(log)
        log = transition_transaction(
            t,
            final,
            reason=result.message or f"{operation} result",
            correlation_id=str(t.id),
        )
        db.add(log)
        db.commit()
        db.refresh(t)
    except Exception as e:
        db.rollback()
        raise HTTPException(409, detail=f"State transition failed: {e}")
    return {
        "transaction": payment_json(t),
        "operation": operation,
        "amount": str(amount),
        "captured_amount": str(t.captured_amount),
        "refunded_amount": str(t.refunded_amount),
        "gateway_outcome": result.outcome.value,
    }


@app.post("/api/v1/payments/{transaction_id}/capture")
def capture_payment(
    transaction_id: UUID,
    request: AmountRequest = AmountRequest(),
    db: Session = Depends(get_db),
):
    return operate(transaction_id, "capture", request, db)


@app.post("/api/v1/payments/{transaction_id}/void")
def void_payment(transaction_id: UUID, db: Session = Depends(get_db)):
    return operate(transaction_id, "void", AmountRequest(), db)


@app.post("/api/v1/payments/{transaction_id}/refund")
def refund_payment(
    transaction_id: UUID,
    request: AmountRequest = AmountRequest(),
    db: Session = Depends(get_db),
):
    return operate(transaction_id, "refund", request, db)


@app.get("/api/v1/payments/{transaction_id}/refunds")
def list_refunds(transaction_id: UUID, db: Session = Depends(get_db)):
    t = db.get(Transaction, transaction_id)
    if not t:
        raise HTTPException(404, detail="Payment not found")
    rows = db.scalars(
        select(TransactionStateLog)
        .where(
            TransactionStateLog.transaction_id == transaction_id,
            TransactionStateLog.event_type == "STATE_TRANSITION",
        )
        .order_by(TransactionStateLog.created_at)
    ).all()
    return [
        {
            "state": r.new_state,
            "reason": r.reason,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
        if "REFUND" in r.new_state
    ]


# Demo webhook signature: HMAC-SHA256 over the exact raw body using gateway-specific env secret.
@app.post("/api/v1/webhooks/{gateway_name}")
async def receive_webhook(
    request: Request,
    gateway_name: str,
    x_webhook_signature: str = Header(default=""),
    db: Session = Depends(get_db),
):
    if gateway_name not in {"razorpay", "stripe", "payu", "upi"}:
        raise HTTPException(404, detail="Unknown gateway")
    raw = await request.body()
    secret = os.getenv(f"{gateway_name.upper()}_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(503, detail="Webhook secret is not configured")
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    supplied = x_webhook_signature.removeprefix("sha256=")
    if not hmac.compare_digest(expected, supplied):
        raise HTTPException(401, detail="Invalid webhook signature")
    try:
        body = WebhookRequest.model_validate_json(raw)
    except Exception:
        raise HTTPException(400, detail="Invalid webhook payload")
    event = WebhookEvent(
        gateway=gateway_name,
        event_id=body.event_id,
        transaction_id=body.transaction_id,
        event_type=body.event_type,
        payload=body.model_dump(mode="json"),
        status="RECEIVED",
    )
    event.attempt_count = 1
    event.last_attempt_at = datetime.now(timezone.utc)
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"status": "duplicate_ignored", "event_id": body.event_id}
    if body.transaction_id:
        try:
            tid = UUID(body.transaction_id)
        except ValueError:
            event.status = "REJECTED"
            event.error_message = "Invalid transaction UUID"
            db.commit()
            raise HTTPException(400, detail="Invalid transaction_id")
        t = db.get(Transaction, tid)
        if t is None:
            event.status = "FAILED"
            event.error_message = "Transaction not found; event retained for retry"
            db.commit()
            raise HTTPException(404, detail=event.error_message)
        try:
            apply_webhook_event(db, event, t)
            db.commit()
        except Exception as e:
            db.rollback()
            saved = db.scalar(
                select(WebhookEvent).where(
                    WebhookEvent.gateway == gateway_name,
                    WebhookEvent.event_id == body.event_id,
                )
            )
            if saved:
                saved.status = "FAILED"
                saved.error_message = str(e)[:1000]
                saved.attempt_count = (saved.attempt_count or 0) + 1
                saved.last_attempt_at = datetime.now(timezone.utc)
                db.commit()
            raise HTTPException(
                409,
                detail=f"Webhook state transition rejected; event retained for retry: {e}",
            )
    else:
        event.status = "IGNORED"
        event.error_message = "No transaction_id supplied; event stored but not applied"
        db.commit()
    return {"status": event.status.lower(), "event_id": body.event_id}


@app.get("/api/v1/webhooks/events/{event_id}")
def get_webhook_event(event_id: str, db: Session = Depends(get_db)):
    event = db.scalar(select(WebhookEvent).where(WebhookEvent.event_id == event_id))
    if not event:
        raise HTTPException(404, detail="Webhook event not found")
    return {
        "event_id": event.event_id,
        "gateway": event.gateway,
        "status": event.status,
        "attempt_count": event.attempt_count,
        "last_attempt_at": (
            event.last_attempt_at.isoformat() if event.last_attempt_at else None
        ),
        "error_message": event.error_message,
    }


@app.post("/api/v1/webhooks/events/{event_id}/retry")
def retry_webhook_event(event_id: str, db: Session = Depends(get_db)):
    """Explicitly retry a previously failed webhook from its persisted payload."""
    event = db.scalar(select(WebhookEvent).where(WebhookEvent.event_id == event_id))
    if event is None:
        raise HTTPException(404, detail="Webhook event not found")
    if event.status not in {"FAILED", "REJECTED"}:
        raise HTTPException(
            409,
            detail=f"Only FAILED/REJECTED events can be retried (current status: {event.status})",
        )
    event.attempt_count = (event.attempt_count or 0) + 1
    event.last_attempt_at = datetime.now(timezone.utc)
    event.status = "RECEIVED"
    event.error_message = None
    db.commit()
    if not event.transaction_id:
        event.status = "IGNORED"
        event.error_message = "No transaction_id supplied; cannot apply event"
        db.commit()
        return {
            "event_id": event.event_id,
            "status": "ignored",
            "attempt_count": event.attempt_count,
        }
    try:
        tid = UUID(event.transaction_id)
    except ValueError:
        event.status = "REJECTED"
        event.error_message = "Persisted transaction UUID is invalid"
        db.commit()
        raise HTTPException(400, detail=event.error_message)
    t = db.get(Transaction, tid)
    if t is None:
        event.status = "FAILED"
        event.error_message = (
            "Transaction not found; retry after transaction is available"
        )
        db.commit()
        raise HTTPException(404, detail=event.error_message)
    try:
        apply_webhook_event(db, event, t)
        db.commit()
    except Exception as exc:
        db.rollback()
        saved = db.scalar(
            select(WebhookEvent).where(
                WebhookEvent.gateway == event.gateway, WebhookEvent.event_id == event_id
            )
        )
        if saved:
            saved.status = "FAILED"
            saved.error_message = str(exc)[:1000]
            db.commit()
        raise HTTPException(
            409,
            detail="Webhook retry failed; event remains available for another retry",
        )
    return {
        "event_id": event.event_id,
        "status": event.status.lower(),
        "attempt_count": event.attempt_count,
    }


@app.get("/api/v1/gateways")
def list_gateways():
    return [
        {
            "name": g.name,
            "circuit_state": ROUTER.get_circuit_state(g.name).value,
            "mock": True,
        }
        for g in GATEWAYS
    ]


@app.get("/api/v1/gateways/{name}/health")
def gateway_health(name: str):
    if name not in [g.name for g in GATEWAYS]:
        raise HTTPException(404, detail="Gateway not found")
    return {
        "name": name,
        "state": ROUTER.get_circuit_state(name).value,
        "healthy": ROUTER.get_circuit_state(name).value != "OPEN",
    }


@app.post("/api/v1/gateways/{name}/scenarios/{scenario}")
def configure_mock_scenario(name: str, scenario: str):
    gateway = next((g for g in GATEWAYS if g.name == name), None)
    if gateway is None:
        raise HTTPException(404, detail="Gateway not found")
    try:
        gateway.set_scenario(scenario)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    return {
        "gateway": name,
        "next_scenario": scenario,
        "note": "Scenario affects the next matching mock gateway operation only",
    }


@app.get("/api/v1/gateways/{name}/metrics")
def gateway_metrics(name: str):
    g = next((g for g in GATEWAYS if g.name == name), None)
    if not g:
        raise HTTPException(404, detail="Gateway not found")
    return {
        "name": name,
        "calls": getattr(g, "calls", {}),
        "circuit_state": ROUTER.get_circuit_state(name).value,
    }


@app.put("/api/v1/gateways/{name}/config")
def update_gateway_config(name: str, enabled: bool, weight: int = Query(1, ge=0)):
    if name not in ROUTER.weights:
        raise HTTPException(404, detail="Gateway not found")
    new_weight = weight if enabled else 0
    if (
        sum(value for key, value in ROUTER.weights.items() if key != name) + new_weight
        == 0
    ):
        raise HTTPException(400, detail="At least one gateway must remain enabled")
    ROUTER.weights[name] = new_weight
    return {"name": name, "enabled": enabled, "weight": ROUTER.weights[name]}


@app.get("/api/v1/routing/config")
def get_routing_config():
    from app.gateways.router import FACTOR_WEIGHTS

    return {
        "weights": ROUTER.weights,
        "scoring_factors": FACTOR_WEIGHTS,
        "metrics_source": "adapter demo baselines; not real provider telemetry",
    }


@app.get("/api/v1/routing/scores")
def routing_scores(
    payment_method: str = Query(default="card", min_length=1, max_length=30)
):
    return {
        "payment_method": payment_method,
        "scores": ROUTER.routing_scores(payment_method),
        "selection_policy": "five-factor score multiplied by configured gateway weight; circuit-open and incompatible gateways excluded",
    }


@app.put("/api/v1/routing/config")
def set_routing_config(weights: dict[str, int]):
    if (
        set(weights) != set(ROUTER.weights)
        or any(
            not isinstance(v, int) or isinstance(v, bool) or v < 0
            for v in weights.values()
        )
        or sum(weights.values()) == 0
    ):
        raise HTTPException(
            400,
            detail="Provide non-negative integer weights for every configured gateway, with positive total",
        )
    ROUTER.weights.update(weights)
    return {"weights": ROUTER.weights}


@app.get("/api/v1/analytics/success-rate")
def analytics_success_rate(db: Session = Depends(get_db)):
    rows = (
        db.execute(
            text(
                "SELECT selected_gateway, COUNT(*) total, COUNT(*) FILTER (WHERE status IN ('CAPTURED','SETTLED')) successful FROM transactions GROUP BY selected_gateway"
            )
        )
        .mappings()
        .all()
    )
    return [
        {
            "gateway": r["selected_gateway"],
            "total": r["total"],
            "successful": r["successful"],
            "success_rate": float(r["successful"] / r["total"]) if r["total"] else 0,
        }
        for r in rows
    ]


@app.get("/api/v1/analytics/volume")
def analytics_volume(db: Session = Depends(get_db)):
    return {
        "transactions": db.scalar(select(text("count(*)")).select_from(Transaction)),
        "volume_by_currency": [
            dict(r)
            for r in db.execute(
                text(
                    "SELECT currency, COUNT(*) AS transactions, SUM(amount) AS amount FROM transactions GROUP BY currency"
                )
            )
            .mappings()
            .all()
        ],
    }


@app.post("/api/v1/reconciliation/trigger", status_code=202)
def trigger_reconciliation(db: Session = Depends(get_db)):
    run = ReconciliationRun(
        status="RUNNING", details={"mode": "mock gateway status lookup"}
    )
    db.add(run)
    db.flush()
    checked = 0
    created_ids = []
    errors = []
    rows = db.scalars(
        select(Transaction).where(
            Transaction.status.in_(
                [
                    PaymentState.CAPTURED.value,
                    PaymentState.SETTLED.value,
                    PaymentState.AUTH_UNKNOWN.value,
                    PaymentState.CAPTURE_INITIATED.value,
                    PaymentState.REFUND_INITIATED.value,
                    PaymentState.VOID_INITIATED.value,
                ]
            )
        )
    ).all()
    for t in rows:
        checked += 1
        g = next(
            (gateway for gateway in GATEWAYS if gateway.name == t.selected_gateway),
            None,
        )
        if not g or not t.gateway_reference:
            errors.append(
                {
                    "transaction_id": str(t.id),
                    "error": "original gateway/reference unavailable",
                }
            )
            continue
        try:
            result = g.get_status(t.gateway_reference)
        except Exception as exc:
            errors.append({"transaction_id": str(t.id), "error": type(exc).__name__})
            continue
        expected = {
            PaymentState.CAPTURED.value: {
                GatewayOutcome.CAPTURED,
                GatewayOutcome.AUTHORISED,
            },
            PaymentState.SETTLED.value: {
                GatewayOutcome.CAPTURED,
                GatewayOutcome.AUTHORISED,
            },
            PaymentState.AUTH_UNKNOWN.value: {
                GatewayOutcome.AUTHORISED,
                GatewayOutcome.DECLINED,
            },
            PaymentState.CAPTURE_INITIATED.value: {GatewayOutcome.CAPTURED},
            PaymentState.REFUND_INITIATED.value: {
                GatewayOutcome.REFUNDED,
                GatewayOutcome.PARTIALLY_REFUNDED,
            },
            PaymentState.VOID_INITIATED.value: {GatewayOutcome.VOIDED},
        }.get(t.status, set())
        if result.outcome == GatewayOutcome.UNKNOWN:
            errors.append(
                {"transaction_id": str(t.id), "error": "gateway status remains unknown"}
            )
            continue
        if result.outcome not in expected:
            anomaly = ReconciliationAnomaly(
                transaction_id=str(t.id),
                gateway=g.name,
                internal_status=t.status,
                gateway_status=result.outcome.value,
                amount=t.amount,
                details={
                    "run_id": str(run.id),
                    "message": result.message,
                    "manual_review_required": True,
                    "automatic_refund": False,
                },
            )
            db.add(anomaly)
            created_ids.append(str(anomaly.id))
            if t.status not in {PaymentState.RECONCILIATION_MISMATCH.value}:
                try:
                    db.add(
                        transition_transaction(
                            t,
                            PaymentState.RECONCILIATION_MISMATCH,
                            reason="Gateway/internal status mismatch; manual review required",
                            correlation_id=str(run.id),
                        )
                    )
                except InvalidTransitionError:
                    # Preserve the anomaly even where the state graph forbids a transition.
                    pass
    run.checked_count = checked
    run.anomaly_count = len(created_ids)
    run.status = "COMPLETED_WITH_ERRORS" if errors else "COMPLETED"
    run.details = {
        "anomaly_ids": created_ids,
        "errors": errors,
        "automatic_refunds_triggered": False,
        "note": "Mock gateway status only; verify with a real provider before financial action",
    }
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "run_id": str(run.id),
        "status": run.status,
        "checked": checked,
        "anomalies_created": len(created_ids),
        "anomaly_ids": created_ids,
        "errors": errors,
        "automatic_refunds_triggered": False,
    }


@app.get("/api/v1/reconciliation/reports/{run_id}")
def reconciliation_report(run_id: str, db: Session = Depends(get_db)):
    try:
        uid = UUID(run_id)
    except ValueError:
        raise HTTPException(400, detail="run_id must be a reconciliation run UUID")
    run = db.get(ReconciliationRun, uid)
    if run:
        anomalies = db.scalars(
            select(ReconciliationAnomaly).where(
                ReconciliationAnomaly.details["run_id"].as_string() == str(run.id)
            )
        ).all()
        return {
            "run_id": str(run.id),
            "status": run.status,
            "checked_count": run.checked_count,
            "anomaly_count": run.anomaly_count,
            "details": run.details,
            "anomalies": [
                {
                    "id": str(a.id),
                    "transaction_id": a.transaction_id,
                    "gateway": a.gateway,
                    "internal_status": a.internal_status,
                    "gateway_status": a.gateway_status,
                    "amount": str(a.amount),
                    "status": a.status,
                    "details": a.details,
                }
                for a in anomalies
            ],
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }
    anomaly = db.get(ReconciliationAnomaly, uid)
    if anomaly:
        return {
            "id": str(anomaly.id),
            "transaction_id": anomaly.transaction_id,
            "gateway": anomaly.gateway,
            "internal_status": anomaly.internal_status,
            "gateway_status": anomaly.gateway_status,
            "amount": str(anomaly.amount),
            "status": anomaly.status,
            "details": anomaly.details,
            "created_at": anomaly.created_at.isoformat(),
        }
    raise HTTPException(404, detail="Reconciliation run or anomaly not found")
