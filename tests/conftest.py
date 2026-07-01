import pytest

from heartbeat.models import AlertPayload, AlertState, HealthResult, HealthStatus, ServiceConfig


@pytest.fixture(autouse=True)
def mock_asyncio_sleep(monkeypatch):
    sleep_calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr("heartbeat.checker.asyncio.sleep", fake_sleep)
    return sleep_calls


@pytest.fixture
def service() -> "ServiceConfig":
    return ServiceConfig(name="rlsapi", url="https://api.example.com", health_path="/healthz")


@pytest.fixture
def service_with_threshold() -> "ServiceConfig":
    return ServiceConfig(
        name="okp-mcp",
        url="https://mcp.example.com",
        health_path="/health",
        response_time_threshold_ms=500.0,
    )


@pytest.fixture
def healthy_result(service: "ServiceConfig") -> "HealthResult":
    return HealthResult(service=service, status=HealthStatus.HEALTHY, status_code=200, response_time_ms=42.0)


@pytest.fixture
def unhealthy_result(service: "ServiceConfig") -> "HealthResult":
    return HealthResult(service=service, status=HealthStatus.UNHEALTHY, status_code=503, response_time_ms=80.0)


@pytest.fixture
def degraded_result(service_with_threshold: "ServiceConfig") -> "HealthResult":
    return HealthResult(
        service=service_with_threshold,
        status=HealthStatus.DEGRADED,
        status_code=200,
        response_time_ms=1200.0,
    )


@pytest.fixture
def webhook_url() -> "str":
    return "https://hooks.slack.com/services/TEST/WEBHOOK"


@pytest.fixture
def firing_payload(unhealthy_result: "HealthResult") -> "AlertPayload":
    return AlertPayload(
        state=AlertState.FIRING,
        results=(unhealthy_result,),
        summary="1 down out of 1 services",
    )


@pytest.fixture
def resolved_payload(healthy_result: "HealthResult") -> "AlertPayload":
    return AlertPayload(
        state=AlertState.RESOLVED,
        results=(healthy_result,),
        summary="all services recovered",
    )
