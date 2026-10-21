
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.state_machine.states import PaymentState


class TransactionStateChangeRequest(BaseModel):
    transaction_id: UUID
    new_state: PaymentState
    reason: str | None = None
    correlation_id: str | None = None


class TransactionCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    merchant_id: str = Field(min_length=1, max_length=100)
    merchant_order_id: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(gt=Decimal("0"), max_digits=15, decimal_places=2)
    currency: str = Field(default="INR", min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        value = value.upper()

        if not value.isalpha():
            raise ValueError("Currency must contain only letters")

        return value
