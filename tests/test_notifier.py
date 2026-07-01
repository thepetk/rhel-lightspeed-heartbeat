import httpx
import pytest
import respx

from heartbeat.models import AlertPayload, AlertState, HealthResult, HealthStatus, ServiceConfig
from heartbeat.notifier import SlackNotifier, _build_message


@pytest.fixture
def service() -> ServiceConfig:
    return ServiceConfig(name="rlsapi", url="https://api.example.com", health_path="/healthz")


@pytest.fixture
def unhealthy_result(service: ServiceConfig) -> HealthResult:
    return HealthResult(service=service, status=HealthStatus.UNHEALTHY, status_code=503, response_time_ms=80.0)


@pytest.fixture
def healthy_result(service: ServiceConfig) -> HealthResult:
    return HealthResult(service=service, status=HealthStatus.HEALTHY, status_code=200, response_time_ms=42.0)


@pytest.fixture
def degraded_result() -> HealthResult:
    svc = ServiceConfig(name="okp-mcp", url="https://mcp.example.com", response_time_threshold_ms=500.0)
    return HealthResult(service=svc, status=HealthStatus.DEGRADED, status_code=200, response_time_ms=1200.0)


@respx.mock
async def test_send_success(webhook_url, firing_payload):
    respx.post(webhook_url).mock(return_value=httpx.Response(200, text="ok"))
    notifier = SlackNotifier(webhook_url)
    result = await notifier.send(firing_payload)
    assert result is True


@respx.mock
async def test_send_failure_bad_status(webhook_url, firing_payload):
    respx.post(webhook_url).mock(return_value=httpx.Response(500, text="error"))
    notifier = SlackNotifier(webhook_url)
    result = await notifier.send(firing_payload)
    assert result is False


@respx.mock
async def test_send_failure_wrong_body(webhook_url, firing_payload):
    respx.post(webhook_url).mock(return_value=httpx.Response(200, text="not-ok"))
    notifier = SlackNotifier(webhook_url)
    result = await notifier.send(firing_payload)
    assert result is False


@respx.mock
async def test_send_network_error(webhook_url, firing_payload):
    respx.post(webhook_url).mock(side_effect=httpx.ConnectError("refused"))
    notifier = SlackNotifier(webhook_url)
    result = await notifier.send(firing_payload)
    assert result is False


@respx.mock
async def test_send_with_injected_client(webhook_url, firing_payload):
    respx.post(webhook_url).mock(return_value=httpx.Response(200, text="ok"))
    async with httpx.AsyncClient() as client:
        notifier = SlackNotifier(webhook_url, client=client)
        result = await notifier.send(firing_payload)
    assert result is True


def test_build_message_firing(unhealthy_result):
    payload = AlertPayload(
        state=AlertState.FIRING,
        results=(unhealthy_result,),
        summary="1 down out of 1 services",
    )
    msg = _build_message(payload)
    assert "attachments" in msg
    attachment = msg["attachments"][0]
    assert attachment["color"] == "#EE0000"
    blocks_text = str(attachment["blocks"])
    assert "FIRING:1" in blocks_text
    assert "rlsapi" in blocks_text


def test_build_message_resolved(healthy_result):
    payload = AlertPayload(
        state=AlertState.RESOLVED,
        results=(healthy_result,),
        summary="all services recovered",
    )
    msg = _build_message(payload)
    attachment = msg["attachments"][0]
    assert attachment["color"] == "#36A64F"
    assert "RESOLVED" in str(attachment["blocks"])


def test_build_message_degraded_included(degraded_result):
    payload = AlertPayload(
        state=AlertState.FIRING,
        results=(degraded_result,),
        summary="1 degraded out of 1 services",
    )
    msg = _build_message(payload)
    blocks_text = str(msg["attachments"][0]["blocks"])
    assert "okp-mcp" in blocks_text
    assert "1200" in blocks_text  # response time
    assert "500" in blocks_text  # threshold


def test_build_message_footer_timestamp_only(unhealthy_result):
    payload = AlertPayload(
        state=AlertState.FIRING,
        results=(unhealthy_result,),
        summary="1 down",
    )
    msg = _build_message(payload)
    blocks_text = str(msg["attachments"][0]["blocks"])
    assert "clock1" in blocks_text
    assert "github.com" not in blocks_text


def test_build_message_with_error_message(service):
    result = HealthResult(
        service=service,
        status=HealthStatus.ERROR,
        error_message="connection refused",
    )
    payload = AlertPayload(state=AlertState.FIRING, results=(result,), summary="1 down")
    msg = _build_message(payload)
    assert "connection refused" in str(msg["attachments"][0]["blocks"])
