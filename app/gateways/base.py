
from abc import ABC, abstractmethod
from decimal import Decimal

from app.gateways.schemas import GatewayResult


class PaymentGateway(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the gateway's unique name."""
        raise NotImplementedError

    @abstractmethod
    def authorize(
        self,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
    ) -> GatewayResult:
        """Authorize a payment and return a normalized result."""
        raise NotImplementedError
