
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
        raise NotImplementedError

    @abstractmethod
    def capture(
        self,
        gateway_reference: str,
        amount: Decimal,
        idempotency_key: str,
    ) -> GatewayResult:
        raise NotImplementedError

    @abstractmethod
    def void(
        self,
        gateway_reference: str,
        idempotency_key: str,
    ) -> GatewayResult:
        raise NotImplementedError

    @abstractmethod
    def refund(
        self,
        gateway_reference: str,
        amount: Decimal,
        idempotency_key: str,
    ) -> GatewayResult:
        raise NotImplementedError

    @abstractmethod
    def get_status(
        self,
        gateway_reference: str,
    ) -> GatewayResult:
        raise NotImplementedError
