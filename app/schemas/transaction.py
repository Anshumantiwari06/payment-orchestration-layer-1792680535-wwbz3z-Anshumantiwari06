
from uuid import UUID

from pydantic import BaseModel
from decimal import Decimal
from app.state_machine.states import PaymentState


class TransactionStateChangeRequest(BaseModel):
    transaction_id: UUID
    new_state: PaymentState
    reason: str | None = None
    correlation_id: str | None = None
class TransactionCreateRequest(BaseModel):
    merchant_id: str
    merchant_order_id: str
    amount: Decimal
    currency: str = "INR"