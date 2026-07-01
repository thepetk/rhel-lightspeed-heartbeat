import json
import os
import tempfile
from unittest.mock import AsyncMock, patch

import httpx
import respx

from heartbeat.config import HeartbeatConfig
from heartbeat.models import HealthStatus, ServiceConfig
from heartbeat.runner import HeartbeatRunner


def make_config(slack_url: str | None = None, fail_on_unhealthy: bool = True) -> HeartbeatConfig:
    return HeartbeatConfig(
        services=[ServiceConfig(name="rlsapi", url="https://api.example.com", health_path="/healthz", retry_count=0)],
        slack_webhook_url=slack_url,
        fail_on_unhealthy=fail_on_unhealthy,
    )


@respx.mock
async def test_run_all_healthy_no_slack():
    respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(200))
    config = make_config(slack_url=None)
    runner = HeartbeatRunner(config)
    with patch.object(runner, "_notify", new_callable=AsyncMock) as mock_notify:
        results = await runner.run()
    assert all(r.status == HealthStatus.HEALTHY for r in results)
    mock_notify.assert_not_called()


@respx.mock
async def test_run_unhealthy_triggers_slack():
    respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(503))
    config = make_config(slack_url="https://hooks.slack.com/test")
    runner = HeartbeatRunner(config)
    with patch.object(runner, "_notify", new_callable=AsyncMock) as mock_notify:
        results = await runner.run()
    assert results[0].status == HealthStatus.UNHEALTHY
    mock_notify.assert_awaited_once()


@respx.mock
async def test_run_sets_github_output():
    respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(200))
    config = make_config()
    runner = HeartbeatRunner(config)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        output_path = f.name
    try:
        with patch.dict(os.environ, {"GITHUB_OUTPUT": output_path}):
            await runner.run()
        with open(output_path) as fh:
            content = fh.read()
        assert "healthy=true" in content
        data = json.loads(content.split("results=")[1].strip())
        assert data[0]["name"] == "rlsapi"
        assert data[0]["status"] == "healthy"
    finally:
        os.unlink(output_path)


@respx.mock
async def test_run_no_github_output_env():
    respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(200))
    config = make_config()
    runner = HeartbeatRunner(config)
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_OUTPUT"}
    with patch.dict(os.environ, env, clear=True):
        results = await runner.run()
    assert len(results) == 1


@respx.mock
async def test_notify_skipped_when_no_webhook():
    respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(503))
    config = make_config(slack_url=None)
    runner = HeartbeatRunner(config)
    # should not raise even with no webhook and unhealthy services
    results = await runner.run()
    assert results[0].status == HealthStatus.UNHEALTHY


@respx.mock
async def test_run_multiple_services():
    config = HeartbeatConfig(
        services=[
            ServiceConfig(name="svc1", url="https://svc1.example.com", health_path="/healthz"),
            ServiceConfig(name="svc2", url="https://svc2.example.com", health_path="/healthz"),
        ],
        slack_webhook_url=None,
    )
    respx.get("https://svc1.example.com/healthz").mock(return_value=httpx.Response(200))
    respx.get("https://svc2.example.com/healthz").mock(return_value=httpx.Response(503))
    runner = HeartbeatRunner(config)
    with patch.object(runner, "_notify", new_callable=AsyncMock) as mock_notify:
        results = await runner.run()
    assert results[0].status == HealthStatus.HEALTHY
    assert results[1].status == HealthStatus.UNHEALTHY
    mock_notify.assert_awaited_once()


@respx.mock
async def test_notify_sends_slack_with_correct_summary():
    """Exercises _notify body directly with a real SlackNotifier (mocked webhook)."""
    webhook = "https://hooks.slack.com/services/TEST"
    respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(503))
    respx.post(webhook).mock(return_value=httpx.Response(200, text="ok"))
    config = make_config(slack_url=webhook)
    runner = HeartbeatRunner(config)
    results = await runner.run()
    assert results[0].status == HealthStatus.UNHEALTHY
    assert respx.calls.call_count == 2  # one health check + one slack post


@respx.mock
async def test_notify_summary_degraded_only():
    """Exercises the 'degraded' branch in _notify summary building."""
    webhook = "https://hooks.slack.com/services/TEST2"
    respx.post(webhook).mock(return_value=httpx.Response(200, text="ok"))
    svc = ServiceConfig(name="okp-mcp", url="https://mcp.example.com", response_time_threshold_ms=500.0)
    from heartbeat.models import HealthResult, HealthStatus

    degraded = HealthResult(service=svc, status=HealthStatus.DEGRADED, status_code=200, response_time_ms=1200.0)
    config = HeartbeatConfig(services=[svc], slack_webhook_url=webhook)
    runner = HeartbeatRunner(config)
    await runner._notify([degraded])
    assert respx.calls.call_count == 1


@respx.mock
async def test_print_results_shows_error_message():
    """Exercises the error_message branch in _print_results."""
    respx.get("https://api.example.com/healthz").mock(side_effect=httpx.ConnectError("refused"))
    config = make_config(slack_url=None, fail_on_unhealthy=False)
    runner = HeartbeatRunner(config)
    results = await runner.run()
    assert results[0].status == HealthStatus.ERROR
    assert results[0].error_message is not None


def test_print_results_degraded_warning(capsys):
    """Exercises the DEGRADED ::warning:: path in _print_results."""
    from heartbeat.models import HealthResult, HealthStatus

    svc = ServiceConfig(name="slow-svc", url="https://slow.example.com", response_time_threshold_ms=500.0)
    degraded = HealthResult(service=svc, status=HealthStatus.DEGRADED, status_code=200, response_time_ms=1200.0)
    config = HeartbeatConfig(services=[svc], slack_webhook_url=None)
    runner = HeartbeatRunner(config)
    runner._print_results([degraded])
    captured = capsys.readouterr()
    assert "DEGRADED" in captured.err
