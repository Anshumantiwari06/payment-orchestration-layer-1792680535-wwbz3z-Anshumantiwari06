

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.transaction import (
    TransactionCreateRequest,
    TransactionStateChangeRequest,
)
from app.services.transaction_service import (
    authorize_transaction,
    change_transaction_state,
    create_transaction,
)
from app.state_machine.engine import InvalidTransitionError
from app.gateways.mock_gateway import MockGateway
from app.gateways.orchestrator import PaymentOrchestrator
from app.gateways.router import GatewayRouter
from app.gateways.schemas import GatewayOutcome
from uuid import UUID
from app.services.idempotency_service import IdempotencyConflictError

app = FastAPI(
    title="Payment Orchestration Layer",
    description=(
        "A backend system for payment routing, "
        "gateway failover, idempotency, and reconciliation."
    ),
    version="0.1.0",
)



router = GatewayRouter(
    gateways=[
        MockGateway("razorpay_mock", GatewayOutcome.AUTHORISED),
        MockGateway("stripe_mock", GatewayOutcome.AUTHORISED),
        MockGateway("payu_mock", GatewayOutcome.AUTHORISED),
        MockGateway("upi_mock", GatewayOutcome.AUTHORISED),
        MockGateway("fallback_mock", GatewayOutcome.AUTHORISED),
    ],
    weights={
        "razorpay_mock": 35,
        "stripe_mock": 20,
        "payu_mock": 20,
        "upi_mock": 15,
        "fallback_mock": 10,
    },
)

orchestrator = PaymentOrchestrator(router)


@app.get("/")
def root():
    return {
        "message": "Payment Orchestration Layer is running",
        "status": "ok",
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
    }


@app.post("/transactions", status_code=201)
def create_new_transaction(
    request: TransactionCreateRequest,
    db: Session = Depends(get_db),
):
    try:
        transaction = create_transaction(
            db=db,
            request=request,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to create transaction",
        ) from exc

    return {
        "transaction_id": str(transaction.id),
        "merchant_id": transaction.merchant_id,
        "merchant_order_id": transaction.merchant_order_id,
        "amount": str(transaction.amount),
        "currency": transaction.currency,
        "status": transaction.status,
    }


@app.post("/transactions/change-state")
def change_state(
    request: TransactionStateChangeRequest,
    db: Session = Depends(get_db),
):
    try:
        transaction = change_transaction_state(
            db=db,
            transaction_id=request.transaction_id,
            new_state=request.new_state,
            reason=request.reason,
            correlation_id=request.correlation_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return {
        "transaction_id": str(transaction.id),
        "status": transaction.status,
    }





@app.post("/transactions/{transaction_id}/authorize")
def authorize_payment(
    transaction_id: str,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    try:
        parsed_transaction_id = UUID(transaction_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid transaction ID format",
        ) from exc

    try:
        transaction = authorize_transaction(
            db=db,
            transaction_id=parsed_transaction_id,
            orchestrator=orchestrator,
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    return {
        "transaction_id": str(transaction.id),
        "status": transaction.status,
        "selected_gateway": transaction.selected_gateway,
        "gateway_reference": transaction.gateway_reference,
    }
