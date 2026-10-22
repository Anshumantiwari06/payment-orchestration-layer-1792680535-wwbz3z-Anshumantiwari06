from enum import StrEnum

from pydantic import BaseModel


class GatewayOutcome(StrEnum):
    AUTHORISED = "AUTHORISED"
    DECLINED = "DECLINED"
    UNKNOWN = "UNKNOWN"
    CAPTURED = "CAPTURED"
    PARTIALLY_CAPTURED = "PARTIALLY_CAPTURED"
    VOIDED = "VOIDED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"

class GatewayResult(BaseModel):
    outcome: GatewayOutcome
    gateway_name: str
    gateway_reference: str | None = None
    message: str | None = None
