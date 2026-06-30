import json

import pytest

from heartbeat.config import HeartbeatConfig, _parse_services

SERVICES_JSON = json.dumps(
    [
        {"name": "rlsapi", "url": "https://api.example.com"},
        {
            "name": "okp-mcp",
            "url": "https://mcp.example.com",
            "health_path": "/health",
            "response_time_threshold_ms": 500,
        },
    ]
)


def test_from_env_basic(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_JSON)
    config = HeartbeatConfig.from_env()
    assert len(config.services) == 2
    assert config.services[0].name == "rlsapi"
    assert config.services[1].name == "okp-mcp"
    assert config.services[1].response_time_threshold_ms == 500.0


def test_from_env_fallback_env_var(monkeypatch):
    monkeypatch.delenv("INPUT_SERVICES", raising=False)
    monkeypatch.setenv("HEARTBEAT_SERVICES_JSON", SERVICES_JSON)
    config = HeartbeatConfig.from_env()
    assert len(config.services) == 2


def test_from_env_missing_services(monkeypatch):
    monkeypatch.delenv("INPUT_SERVICES", raising=False)
    monkeypatch.delenv("HEARTBEAT_SERVICES_JSON", raising=False)
    with pytest.raises(ValueError, match="No services configured"):
        HeartbeatConfig.from_env()


def test_from_env_slack_webhook(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_JSON)
    monkeypatch.setenv("INPUT_SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
    config = HeartbeatConfig.from_env()
    assert config.slack_webhook_url == "https://hooks.slack.com/test"


def test_from_env_slack_webhook_fallback(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_JSON)
    monkeypatch.delenv("INPUT_SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("HEARTBEAT_SLACK_WEBHOOK_URL", "https://hooks.slack.com/fallback")
    config = HeartbeatConfig.from_env()
    assert config.slack_webhook_url == "https://hooks.slack.com/fallback"


def test_from_env_no_slack(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_JSON)
    monkeypatch.delenv("INPUT_SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("HEARTBEAT_SLACK_WEBHOOK_URL", raising=False)
    config = HeartbeatConfig.from_env()
    assert config.slack_webhook_url is None


def test_from_env_custom_timeout(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_JSON)
    monkeypatch.setenv("INPUT_TIMEOUT", "30")
    config = HeartbeatConfig.from_env()
    assert config.default_timeout == 30.0


def test_from_env_fail_on_unhealthy_false(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_JSON)
    monkeypatch.setenv("INPUT_FAIL_ON_UNHEALTHY", "false")
    config = HeartbeatConfig.from_env()
    assert config.fail_on_unhealthy is False


def test_from_env_fail_on_unhealthy_default(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_JSON)
    monkeypatch.delenv("INPUT_FAIL_ON_UNHEALTHY", raising=False)
    monkeypatch.delenv("HEARTBEAT_FAIL_ON_UNHEALTHY", raising=False)
    config = HeartbeatConfig.from_env()
    assert config.fail_on_unhealthy is True


def test_parse_services_defaults():
    services = _parse_services(json.dumps([{"name": "svc", "url": "https://example.com"}]))
    assert services[0].health_path == "/healthz"
    assert services[0].timeout_seconds == 10.0
    assert services[0].expected_status_codes == (200,)
    assert services[0].response_time_threshold_ms is None


def test_parse_services_custom_expected_codes():
    services = _parse_services(
        json.dumps([{"name": "svc", "url": "https://example.com", "expected_status_codes": [200, 204]}])
    )
    assert services[0].expected_status_codes == (200, 204)


def test_parse_services_invalid_json():
    with pytest.raises(ValueError, match="Invalid JSON"):
        _parse_services("not json")


def test_parse_services_not_a_list():
    with pytest.raises(ValueError, match="must be a JSON array"):
        _parse_services(json.dumps({"name": "svc"}))


def test_parse_services_missing_name():
    with pytest.raises(ValueError, match="missing required field 'name'"):
        _parse_services(json.dumps([{"url": "https://example.com"}]))


def test_parse_services_missing_url():
    with pytest.raises(ValueError, match="missing required field 'url'"):
        _parse_services(json.dumps([{"name": "svc"}]))


def test_parse_services_item_not_a_dict():
    with pytest.raises(ValueError, match="must be a JSON object"):
        _parse_services(json.dumps(["not-a-dict"]))
