from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class HealthStatus(Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    # up but response time exceeded threshold
    DEGRADED = "degraded"
    TIMEOUT = "timeout"
    ERROR = "error"


class AlertState(Enum):
    FIRING = "firing"
    RESOLVED = "resolved"


@dataclass(frozen=True)
class ServiceConfig:
    name: "str"
    url: "str"
    health_path: "str" = "/healthz"
    timeout_seconds: "float" = 10.0
    expected_status_codes: "tuple[int, ...]" = (200,)
    response_time_threshold_ms: "float | None" = None


@dataclass(frozen=True)
class HealthResult:
    service: "ServiceConfig"
    status: "HealthStatus"
    status_code: "int | None" = None
    response_time_ms: "float | None" = None
    error_message: "str | None" = None
    timestamp: "datetime" = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_healthy(self) -> "bool":
        return self.status == HealthStatus.HEALTHY

    @property
    def is_ok(self) -> "bool":
        """
        True if the service is reachable, even if degraded.
        """
        return self.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)


@dataclass(frozen=True)
class AlertPayload:
    state: "AlertState"
    results: "tuple[HealthResult, ...]"
    summary: "str"
    timestamp: "datetime" = field(default_factory=lambda: datetime.now(UTC))
