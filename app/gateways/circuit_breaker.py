import threading
import time
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ):
        if (
            not isinstance(failure_threshold, int)
            or isinstance(failure_threshold, bool)
            or failure_threshold < 1
        ):
            raise ValueError(
                "failure_threshold must be a positive integer"
            )

        if recovery_timeout <= 0:
            raise ValueError(
                "recovery_timeout must be greater than zero"
            )

        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None
        self._half_open_probe_in_flight = False
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._refresh_state()
            return self._state

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failure_count

    def allow_request(self) -> bool:
        with self._lock:
            self._refresh_state()

            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                return False

            # Allow only one probe while HALF_OPEN.
            if self._half_open_probe_in_flight:
                return False

            self._half_open_probe_in_flight = True
            return True

    def record_success(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._opened_at = None
            self._half_open_probe_in_flight = False

    def record_failure(self) -> None:
        with self._lock:
            self._half_open_probe_in_flight = False

            if self._state == CircuitState.HALF_OPEN:
                self._open_circuit()
                return

            self._failure_count += 1

            if self._failure_count >= self.failure_threshold:
                self._open_circuit()

    def _refresh_state(self) -> None:
        if self._state != CircuitState.OPEN:
            return

        if self._opened_at is None:
            return

        elapsed = time.monotonic() - self._opened_at

        if elapsed >= self.recovery_timeout:
            self._state = CircuitState.HALF_OPEN
            self._half_open_probe_in_flight = False

    def _open_circuit(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        self._half_open_probe_in_flight = False
