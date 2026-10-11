from app.state_machine.states import PaymentState


ALLOWED_TRANSITIONS = {
    PaymentState.CREATED: {
        PaymentState.ROUTE_SELECTED,
        PaymentState.FAILED,
    },
    PaymentState.ROUTE_SELECTED: {
        PaymentState.AUTH_INITIATED,
        PaymentState.FAILED,
    },
    PaymentState.AUTH_INITIATED: {
        PaymentState.AUTHORISED,
        PaymentState.AUTH_FAILED,
        PaymentState.AUTH_UNKNOWN,
    },
    PaymentState.AUTHORISED: {
        PaymentState.CAPTURE_INITIATED,
        PaymentState.FAILED,
    },
    PaymentState.AUTH_FAILED: {
        PaymentState.ROUTE_SELECTED,
        PaymentState.FAILED,
    },  
    PaymentState.CAPTURE_INITIATED: {
        PaymentState.CAPTURED,
        PaymentState.CAPTURE_FAILED,
    },
    PaymentState.CAPTURE_FAILED: {
        PaymentState.FAILED,
    },
    PaymentState.CAPTURED: set(),
    PaymentState.FAILED: set(),
    PaymentState.AUTH_UNKNOWN: set(),
}