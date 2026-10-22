
from decimal import Decimal

from app.gateways.mock_gateway import MockGateway
from app.gateways.orchestrator import PaymentOrchestrator
from app.gateways.router import GatewayRouter
from app.gateways.schemas import GatewayOutcome

primary = MockGateway(
    gateway_name="mock_primary",
    outcome=GatewayOutcome.DECLINED,
)

secondary = MockGateway(
    gateway_name="mock_secondary",
    outcome=GatewayOutcome.AUTHORISED,
)

router = GatewayRouter([primary, secondary])
orchestrator = PaymentOrchestrator(router)

result = orchestrator.authorize(
    amount=Decimal("1250.50"),
    currency="INR",
    idempotency_key="order_001",
)

print("Outcome:", result.outcome)
print("Gateway:", result.gateway_name)
print("Reference:", result.gateway_reference)
print("Message:", result.message)
