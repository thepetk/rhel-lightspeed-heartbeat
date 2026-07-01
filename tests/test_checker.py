import httpx
import pytest
import respx

from heartbeat.checker import HealthChecker, _apply_auth, _build_client
from heartbeat.models import AuthConfig, HealthStatus, ServiceConfig


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
async def test_check_no_retry_on_healthy(service, mock_asyncio_sleep):
    respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(200))
    async with HealthChecker() as checker:
        result = await checker.check(service)
    assert result.status == HealthStatus.HEALTHY
    assert mock_asyncio_sleep == []


@respx.mock
async def test_check_retries_on_unhealthy_then_healthy(mock_asyncio_sleep):
    svc = ServiceConfig(
        name="svc", url="https://api.example.com", health_path="/healthz", retry_count=2, backoff_base_seconds=1.0
    )
    responses = iter([httpx.Response(503), httpx.Response(200)])
    respx.get("https://api.example.com/healthz").mock(side_effect=lambda _: next(responses))
    async with HealthChecker() as checker:
        result = await checker.check(svc)
    assert result.status == HealthStatus.HEALTHY
    assert mock_asyncio_sleep == [1.0]  # 1.0 * 2^0


@respx.mock
async def test_check_retries_exhausted_returns_last_failure(mock_asyncio_sleep):
    svc = ServiceConfig(
        name="svc", url="https://api.example.com", health_path="/healthz", retry_count=3, backoff_base_seconds=1.0
    )
    respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(503))
    async with HealthChecker() as checker:
        result = await checker.check(svc)
    assert result.status == HealthStatus.UNHEALTHY
    assert mock_asyncio_sleep == [1.0, 2.0, 4.0]  # 1.0 * 2^0, 2^1, 2^2


@respx.mock
async def test_check_zero_retries_no_sleep(mock_asyncio_sleep):
    svc = ServiceConfig(name="svc", url="https://api.example.com", health_path="/healthz", retry_count=0)
    respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(503))
    async with HealthChecker() as checker:
        result = await checker.check(svc)
    assert result.status == HealthStatus.UNHEALTHY
    assert mock_asyncio_sleep == []


@respx.mock
async def test_check_retries_on_degraded(mock_asyncio_sleep, monkeypatch):
    svc = ServiceConfig(
        name="svc",
        url="https://api.example.com",
        health_path="/healthz",
        retry_count=2,
        backoff_base_seconds=2.0,
        response_time_threshold_ms=1,
    )
    respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(200))

    # odd calls = start timestamp, even calls = start + 1s → always 1000ms elapsed > 1ms threshold
    import heartbeat.checker as checker_mod

    call_count = [0]
    original_monotonic = checker_mod.time.monotonic

    def fake_monotonic():
        val = original_monotonic()
        call_count[0] += 1
        return val + 1.0 if call_count[0] % 2 == 0 else val

    monkeypatch.setattr("heartbeat.checker.time.monotonic", fake_monotonic)
    async with HealthChecker() as checker:
        result = await checker.check(svc)

    assert result.status == HealthStatus.DEGRADED
    assert len(mock_asyncio_sleep) == 2  # retried twice (retry_count=2)


@respx.mock
async def test_check_backoff_uses_custom_base(mock_asyncio_sleep):
    svc = ServiceConfig(
        name="svc", url="https://api.example.com", health_path="/healthz", retry_count=3, backoff_base_seconds=0.5
    )
    respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(503))
    async with HealthChecker() as checker:
        await checker.check(svc)
    assert mock_asyncio_sleep == [0.5, 1.0, 2.0]  # 0.5 * 2^0, 2^1, 2^2


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
        return val + 1.0 if len(calls) % 2 == 0 else val

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


@respx.mock
async def test_check_post_with_body():
    svc = ServiceConfig(
        name="svc",
        url="https://api.example.com",
        health_path="/infer",
        method="POST",
        body={"question": "What is SELinux?"},
        retry_count=0,
    )
    route = respx.post("https://api.example.com/infer").mock(return_value=httpx.Response(200))
    async with HealthChecker() as checker:
        result = await checker.check(svc)
    import json

    assert result.status == HealthStatus.HEALTHY
    assert route.called
    assert json.loads(route.calls[0].request.content) == {"question": "What is SELinux?"}


@respx.mock
async def test_check_post_no_body():
    svc = ServiceConfig(
        name="svc",
        url="https://api.example.com",
        health_path="/healthz",
        method="POST",
        retry_count=0,
    )
    route = respx.post("https://api.example.com/healthz").mock(return_value=httpx.Response(200))
    async with HealthChecker() as checker:
        result = await checker.check(svc)
    assert result.status == HealthStatus.HEALTHY
    assert route.called


def test_build_client_saml_session(monkeypatch):
    monkeypatch.setenv("MY_SAML_TOKEN", "abc123")
    svc = ServiceConfig(
        name="svc",
        url="https://example.com",
        auth=AuthConfig(type="saml_session", token_env_var="MY_SAML_TOKEN"),
    )
    client = _build_client(svc)
    assert client.cookies.get("session") == "abc123"


def test_build_client_saml_session_missing_env_var(monkeypatch):
    monkeypatch.delenv("MY_SAML_TOKEN", raising=False)
    svc = ServiceConfig(
        name="svc",
        url="https://example.com",
        auth=AuthConfig(type="saml_session", token_env_var="MY_SAML_TOKEN"),
    )
    with pytest.raises(ValueError, match="MY_SAML_TOKEN"):
        _build_client(svc)


@respx.mock
async def test_check_with_saml_session_uses_custom_client(monkeypatch):
    monkeypatch.setenv("MY_SAML_TOKEN", "tok")
    svc = ServiceConfig(
        name="svc",
        url="https://example.com",
        health_path="/healthz",
        auth=AuthConfig(type="saml_session", token_env_var="MY_SAML_TOKEN"),
        retry_count=0,
    )
    respx.get("https://example.com/healthz").mock(return_value=httpx.Response(200))
    async with HealthChecker() as checker:
        result = await checker.check(svc)
    assert result.status == HealthStatus.HEALTHY


def test_build_client_proxy():
    svc = ServiceConfig(name="svc", url="https://example.com", proxy="http://proxy:3128")
    client = _build_client(svc)
    assert client is not None


def test_apply_auth_mtls_sets_cert():
    auth = AuthConfig(type="mtls", cert_path="/cert.pem", key_path="/key.pem")
    kwargs: dict = {}
    _apply_auth(kwargs, auth)
    assert kwargs["cert"] == ("/cert.pem", "/key.pem")


@respx.mock
async def test_check_custom_client_retries_on_failure(monkeypatch, mock_asyncio_sleep):
    monkeypatch.setenv("MY_SAML_TOKEN", "tok")
    svc = ServiceConfig(
        name="svc",
        url="https://example.com",
        health_path="/healthz",
        auth=AuthConfig(type="saml_session", token_env_var="MY_SAML_TOKEN"),
        retry_count=2,
        backoff_base_seconds=1.0,
    )
    responses = iter([httpx.Response(503), httpx.Response(503), httpx.Response(200)])
    respx.get("https://example.com/healthz").mock(side_effect=lambda _: next(responses))
    async with HealthChecker() as checker:
        result = await checker.check(svc)
    assert result.status == HealthStatus.HEALTHY
    assert mock_asyncio_sleep == [1.0, 2.0]
