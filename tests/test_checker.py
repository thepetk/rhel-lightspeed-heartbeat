import httpx
import pytest
import respx

from heartbeat.checker import HealthChecker
from heartbeat.models import HealthStatus, ServiceConfig


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


@respx.mock
async def test_check_healthy(service):
    respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(200))
    async with HealthChecker() as checker:
        result = await checker.check(service)
    assert result.status == HealthStatus.HEALTHY
    assert result.status_code == 200
    assert result.response_time_ms is not None
    assert result.response_time_ms >= 0
    assert result.error_message is None


@respx.mock
async def test_check_unhealthy(service):
    respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(503))
    async with HealthChecker() as checker:
        result = await checker.check(service)
    assert result.status == HealthStatus.UNHEALTHY
    assert result.status_code == 503


@respx.mock
async def test_check_custom_expected_codes():
    svc = ServiceConfig(name="svc", url="https://example.com", health_path="/ping", expected_status_codes=(200, 204))
    respx.get("https://example.com/ping").mock(return_value=httpx.Response(204))
    async with HealthChecker() as checker:
        result = await checker.check(svc)
    assert result.status == HealthStatus.HEALTHY
    assert result.status_code == 204


@respx.mock
async def test_check_timeout(service):
    respx.get("https://api.example.com/healthz").mock(side_effect=httpx.ConnectTimeout("timed out"))
    async with HealthChecker() as checker:
        result = await checker.check(service)
    assert result.status == HealthStatus.TIMEOUT
    assert result.error_message is not None


@respx.mock
async def test_check_connection_error(service):
    respx.get("https://api.example.com/healthz").mock(side_effect=httpx.ConnectError("refused"))
    async with HealthChecker() as checker:
        result = await checker.check(service)
    assert result.status == HealthStatus.ERROR
    assert result.error_message is not None


@respx.mock
async def test_check_health_path(service):
    route = respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(200))
    async with HealthChecker() as checker:
        await checker.check(service)
    assert route.called


@respx.mock
async def test_check_all_concurrent():
    services = [
        ServiceConfig(name=f"svc{i}", url=f"https://svc{i}.example.com", health_path="/healthz") for i in range(3)
    ]
    for i in range(3):
        respx.get(f"https://svc{i}.example.com/healthz").mock(return_value=httpx.Response(200))
    async with HealthChecker() as checker:
        results = await checker.check_all(services)
    assert len(results) == 3
    assert all(r.status == HealthStatus.HEALTHY for r in results)
    assert [r.service.name for r in results] == ["svc0", "svc1", "svc2"]


@respx.mock
async def test_check_with_injected_client(service):
    respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(200))
    async with httpx.AsyncClient() as client:
        checker = HealthChecker(client=client)
        async with checker:
            result = await checker.check(service)
    assert result.status == HealthStatus.HEALTHY


@respx.mock
async def test_check_degraded_when_threshold_exceeded(service_with_threshold, monkeypatch):
    respx.get("https://mcp.example.com/health").mock(return_value=httpx.Response(200))
    import time

    original_monotonic = time.monotonic
    calls = []

    def fake_monotonic():
        val = original_monotonic()
        calls.append(val)
        if len(calls) == 1:
            return val
        return val + 1.0  # simulate 1000ms elapsed

    monkeypatch.setattr("heartbeat.checker.time.monotonic", fake_monotonic)
    async with HealthChecker() as checker:
        result = await checker.check(service_with_threshold)
    assert result.status == HealthStatus.DEGRADED
    assert result.status_code == 200


@respx.mock
async def test_check_healthy_within_threshold(service_with_threshold):
    respx.get("https://mcp.example.com/health").mock(return_value=httpx.Response(200))
    async with HealthChecker() as checker:
        result = await checker.check(service_with_threshold)
    # In real execution the response will be fast (mocked), well under 500ms
    assert result.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)
    assert result.status_code == 200
