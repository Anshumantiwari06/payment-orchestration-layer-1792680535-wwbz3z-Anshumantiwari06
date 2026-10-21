
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.gateways.orchestrator import PaymentOrchestrator
from app.gateways.schemas import GatewayOutcome
from app.models.idempotency_record import IdempotencyRecord
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreateRequest
from app.services.idempotency_service import (
    IdempotencyConflictError,
    calculate_request_hash,
    get_idempotency_record,
    validate_existing_request,
)
from app.state_machine.engine import transition_transaction
from app.state_machine.states import PaymentState


def change_transaction_state(
    db: Session,
    transaction_id: UUID,
    new_state: PaymentState,
    reason: str | None = None,
    correlation_id: str | None = None,
) -> Transaction:
    transaction = db.scalar(
        select(Transaction).where(Transaction.id == transaction_id)
    )

    if transaction is None:
        raise ValueError(f"Transaction {transaction_id} was not found")

    state_log = transition_transaction(
        transaction=transaction,
        new_state=new_state,
        reason=reason,
        correlation_id=correlation_id,
    )
    db.add(state_log)

    try:
        db.commit()
        db.refresh(transaction)
    except Exception:
        db.rollback()
        raise

    return transaction


def create_transaction(
    db: Session,
    request: TransactionCreateRequest,
) -> Transaction:
    transaction = Transaction(
        merchant_id=request.merchant_id,
        merchant_order_id=request.merchant_order_id,
        amount=request.amount,
        currency=request.currency,
        status=PaymentState.CREATED.value,
    )

    db.add(transaction)

    try:
        db.commit()
        db.refresh(transaction)
    except Exception:
        db.rollback()
        raise

    return transaction


def _get_existing_response(
    record: IdempotencyRecord,
    request_hash: str,
) -> dict:
    validate_existing_request(record, request_hash)

    if record.status == "COMPLETED":
        response = record.response_data

        required_fields = {
            "transaction_id",
            "status",
            "selected_gateway",
            "gateway_reference",
        }

        if not isinstance(response, dict) or not required_fields.issubset(
            response.keys()
        ):
            raise IdempotencyConflictError(
                "Completed idempotency record has an invalid stored response"
            )

        return {
            "transaction_id": response["transaction_id"],
            "status": response["status"],
            "selected_gateway": response["selected_gateway"],
            "gateway_reference": response["gateway_reference"],
        }

    if record.status == "IN_PROGRESS":
        raise IdempotencyConflictError(
            "This payment request is already being processed"
        )

    if record.status == "UNKNOWN":
        raise IdempotencyConflictError(
            "Payment outcome is unknown; reconciliation is required"
        )

    raise IdempotencyConflictError(
        f"Unsupported idempotency record status: {record.status}"
    )


def _mark_authorization_unknown(
    db: Session,
    transaction_id: UUID,
    merchant_id: str,
    idempotency_key: str,
    reason: str,
    correlation_id: str | None,
) -> None:
    """
    Persist an uncertain authorization outcome where possible.

    Never automatically retry a gateway authorization whose outcome
    cannot be established safely.
    """
    try:
        transaction = db.scalar(
            select(Transaction).where(Transaction.id == transaction_id)
        )
        record = get_idempotency_record(
            db,
            merchant_id,
            idempotency_key,
        )

        if record is not None:
            record.status = "UNKNOWN"

        if transaction is not None:
            if transaction.status == PaymentState.AUTH_INITIATED.value:
                state_log = transition_transaction(
                    transaction=transaction,
                    new_state=PaymentState.AUTH_UNKNOWN,
                    reason=reason,
                    correlation_id=correlation_id,
                )
                db.add(state_log)

            if (
                transaction.status == PaymentState.AUTH_UNKNOWN.value
                and record is not None
            ):
                record.response_data = {
                    "transaction_id": str(transaction.id),
                    "status": transaction.status,
                    "selected_gateway": transaction.selected_gateway,
                    "gateway_reference": transaction.gateway_reference,
                }

        db.commit()

    except Exception:
        db.rollback()


def authorize_transaction(
    db: Session,
    transaction_id: UUID,
    orchestrator: PaymentOrchestrator,
    idempotency_key: str,
    correlation_id: str | None = None,
    payment_method: str = "card",
) -> Transaction | dict:
    transaction = db.scalar(
        select(Transaction).where(Transaction.id == transaction_id)
    )

    if transaction is None:
        raise ValueError(f"Transaction {transaction_id} was not found")

    # Capture scalar values before commits, gateway calls, or rollbacks.
    # SQLAlchemy may expire ORM attributes after a rollback.
    merchant_id = transaction.merchant_id
    amount = transaction.amount
    currency = transaction.currency

    request_hash = calculate_request_hash(
        merchant_id=merchant_id,
        transaction_id=str(transaction.id),
        amount=amount,
        currency=currency,
        payment_method=payment_method,
    )

    existing_record = get_idempotency_record(
        db,
        merchant_id,
        idempotency_key,
    )

    if existing_record is not None:
        return _get_existing_response(existing_record, request_hash)

    if transaction.status != PaymentState.CREATED.value:
        raise ValueError(
            f"Cannot authorize transaction in state {transaction.status}"
        )

    record = IdempotencyRecord(
        merchant_id=merchant_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        status="IN_PROGRESS",
    )

    # Reserve the idempotency key and claim the transaction before
    # calling the external gateway.
    try:
        db.add(record)

        route_log = transition_transaction(
            transaction=transaction,
            new_state=PaymentState.ROUTE_SELECTED,
            reason="Gateway routing started",
            correlation_id=correlation_id,
        )
        db.add(route_log)

        auth_log = transition_transaction(
            transaction=transaction,
            new_state=PaymentState.AUTH_INITIATED,
            reason="Authorization attempt started",
            correlation_id=correlation_id,
        )
        db.add(auth_log)

        db.commit()

    except IntegrityError as exc:
        db.rollback()

        existing_record = get_idempotency_record(
            db,
            merchant_id,
            idempotency_key,
        )

        if existing_record is not None:
            validate_existing_request(existing_record, request_hash)
            raise IdempotencyConflictError(
                "This payment request is already being processed"
            ) from exc

        raise

    except StaleDataError as exc:
        db.rollback()
        raise IdempotencyConflictError(
            "This transaction is already being authorized or has changed state"
        ) from exc

    except Exception:
        db.rollback()
        raise

    # Do not keep a database transaction open while waiting for the gateway.
    try:
        result = orchestrator.authorize(
            amount=amount,
            currency=currency,
            idempotency_key=idempotency_key,
            payment_method=payment_method,
        )

    except Exception:
        _mark_authorization_unknown(
            db=db,
            transaction_id=transaction_id,
            merchant_id=merchant_id,
            idempotency_key=idempotency_key,
            reason=(
                "Gateway authorization raised an exception; "
                "the outcome is uncertain"
            ),
            correlation_id=correlation_id,
        )
        raise

    try:
        transaction = db.scalar(
            select(Transaction).where(Transaction.id == transaction_id)
        )

        if transaction is None:
            raise ValueError(
                f"Transaction {transaction_id} was not found"
            )

        record = get_idempotency_record(
            db,
            merchant_id,
            idempotency_key,
        )

        if record is None:
            raise IdempotencyConflictError(
                "Idempotency reservation disappeared during authorization"
            )

        transaction.selected_gateway = result.gateway_name
        transaction.gateway_reference = result.gateway_reference

        if result.outcome == GatewayOutcome.AUTHORISED:
            final_state = PaymentState.AUTHORISED
            record.status = "COMPLETED"

        elif result.outcome == GatewayOutcome.DECLINED:
            final_state = PaymentState.AUTH_FAILED
            record.status = "COMPLETED"

        else:
            final_state = PaymentState.AUTH_UNKNOWN
            record.status = "UNKNOWN"

        state_log = transition_transaction(
            transaction=transaction,
            new_state=final_state,
            reason=result.message,
            correlation_id=correlation_id,
        )
        db.add(state_log)

        record.response_data = {
            "transaction_id": str(transaction.id),
            "status": final_state.value,
            "selected_gateway": transaction.selected_gateway,
            "gateway_reference": transaction.gateway_reference,
        }

        db.commit()
        db.refresh(transaction)
        return transaction

    except Exception:
        db.rollback()

        # The gateway may already have processed the payment. Never
        # automatically retry when its result could not be persisted.
        _mark_authorization_unknown(
            db=db,
            transaction_id=transaction_id,
            merchant_id=merchant_id,
            idempotency_key=idempotency_key,
            reason=(
                "Could not safely persist the gateway authorization result"
            ),
            correlation_id=correlation_id,
        )
        raise
