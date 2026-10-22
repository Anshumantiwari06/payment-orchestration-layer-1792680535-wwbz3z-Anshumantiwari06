from decimal import Decimal

from pydantic import BaseModel, Field


class AmountRequest(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0, max_digits=15, decimal_places=2)

class WebhookRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=255)
    event_type: str = Field(min_length=1, max_length=100)
    transaction_id: str | None = None
    gateway_reference: str | None = None
    status: str = "UNKNOWN"
    amount: Decimal | None = None
    payload: dict = Field(default_factory=dict)
