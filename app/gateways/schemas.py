
from enum import StrEnum

from pydantic import BaseModel


class GatewayOutcome(StrEnum):
    AUTHORISED = "AUTHORISED"
    DECLINED = "DECLINED"
    UNKNOWN = "UNKNOWN"


class GatewayResult(BaseModel):
    outcome: GatewayOutcome
    gateway_name: str
    gateway_reference: str | None = None
    message: str | None = None
