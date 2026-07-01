import pytest

from heartbeat.config import HeartbeatConfig, _parse_services

SERVICES_YAML = """
- name: api
  url: https://api.example.com
- name: gateway
  url: https://gateway.example.com
  health_path: /health
  response_time_threshold_ms: 500
"""


def test_from_env_basic(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_YAML)
    config = HeartbeatConfig.from_env()
    assert len(config.services) == 2
    assert config.services[0].name == "api"
    assert config.services[1].name == "gateway"
    assert config.services[1].response_time_threshold_ms == 500.0


def test_from_env_fallback_env_var(monkeypatch):
    monkeypatch.delenv("INPUT_SERVICES", raising=False)
    monkeypatch.setenv("HEARTBEAT_SERVICES", SERVICES_YAML)
    config = HeartbeatConfig.from_env()
    assert len(config.services) == 2


def test_from_env_missing_services(monkeypatch):
    monkeypatch.delenv("INPUT_SERVICES", raising=False)
    monkeypatch.delenv("HEARTBEAT_SERVICES", raising=False)
    with pytest.raises(ValueError, match="No services configured"):
        HeartbeatConfig.from_env()


def test_from_env_slack_webhook(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_YAML)
    monkeypatch.setenv("INPUT_SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
    config = HeartbeatConfig.from_env()
    assert config.slack_webhook_url == "https://hooks.slack.com/test"


def test_from_env_slack_webhook_fallback(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_YAML)
    monkeypatch.delenv("INPUT_SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("HEARTBEAT_SLACK_WEBHOOK_URL", "https://hooks.slack.com/fallback")
    config = HeartbeatConfig.from_env()
    assert config.slack_webhook_url == "https://hooks.slack.com/fallback"


def test_from_env_no_slack(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_YAML)
    monkeypatch.delenv("INPUT_SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("HEARTBEAT_SLACK_WEBHOOK_URL", raising=False)
    config = HeartbeatConfig.from_env()
    assert config.slack_webhook_url is None


def test_from_env_custom_timeout(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_YAML)
    monkeypatch.setenv("INPUT_TIMEOUT", "30")
    config = HeartbeatConfig.from_env()
    assert config.default_timeout == 30.0


def test_from_env_fail_on_unhealthy_false(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_YAML)
    monkeypatch.setenv("INPUT_FAIL_ON_UNHEALTHY", "false")
    config = HeartbeatConfig.from_env()
    assert config.fail_on_unhealthy is False


def test_from_env_fail_on_unhealthy_default(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_YAML)
    monkeypatch.delenv("INPUT_FAIL_ON_UNHEALTHY", raising=False)
    monkeypatch.delenv("HEARTBEAT_FAIL_ON_UNHEALTHY", raising=False)
    config = HeartbeatConfig.from_env()
    assert config.fail_on_unhealthy is True


def test_parse_services_defaults():
    services = _parse_services("- name: svc\n  url: https://example.com\n")
    assert services[0].health_path == "/healthz"
    assert services[0].timeout_seconds == 10.0
    assert services[0].expected_status_codes == (200,)
    assert services[0].response_time_threshold_ms is None


def test_parse_services_custom_expected_codes():
    services = _parse_services(
        "- name: svc\n  url: https://example.com\n  expected_status_codes: [200, 204]\n"
    )
    assert services[0].expected_status_codes == (200, 204)


def test_parse_services_invalid_yaml():
    with pytest.raises(ValueError, match="Invalid YAML"):
        _parse_services("key: [unclosed")


def test_parse_services_not_a_list():
    with pytest.raises(ValueError, match="must be a YAML sequence"):
        _parse_services("name: svc")


def test_parse_services_missing_name():
    with pytest.raises(ValueError, match="missing required field 'name'"):
        _parse_services("- url: https://example.com\n")


def test_parse_services_missing_url():
    with pytest.raises(ValueError, match="missing required field 'url'"):
        _parse_services("- name: svc\n")


def test_parse_services_item_not_a_dict():
    with pytest.raises(ValueError, match="must be a YAML mapping"):
        _parse_services("- not-a-dict\n")


def test_from_env_retry_defaults(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_YAML)
    monkeypatch.delenv("INPUT_RETRY_COUNT", raising=False)
    monkeypatch.delenv("HEARTBEAT_RETRY_COUNT", raising=False)
    monkeypatch.delenv("INPUT_BACKOFF_BASE_SECONDS", raising=False)
    monkeypatch.delenv("HEARTBEAT_BACKOFF_BASE_SECONDS", raising=False)
    config = HeartbeatConfig.from_env()
    assert config.default_retry_count == 5
    assert config.default_backoff_base_seconds == 1.0


def test_from_env_custom_retry_count(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_YAML)
    monkeypatch.setenv("INPUT_RETRY_COUNT", "3")
    config = HeartbeatConfig.from_env()
    assert config.default_retry_count == 3
    assert all(s.retry_count == 3 for s in config.services)


def test_from_env_custom_retry_count_fallback(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_YAML)
    monkeypatch.delenv("INPUT_RETRY_COUNT", raising=False)
    monkeypatch.setenv("HEARTBEAT_RETRY_COUNT", "2")
    config = HeartbeatConfig.from_env()
    assert config.default_retry_count == 2


def test_from_env_custom_backoff_base_seconds(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_YAML)
    monkeypatch.setenv("INPUT_BACKOFF_BASE_SECONDS", "2.5")
    config = HeartbeatConfig.from_env()
    assert config.default_backoff_base_seconds == 2.5
    assert all(s.backoff_base_seconds == 2.5 for s in config.services)


def test_parse_services_per_service_retry_override():
    yaml = "- name: svc\n  url: https://example.com\n  retry_count: 1\n  backoff_base_seconds: 0.5\n"
    services = _parse_services(yaml, default_retry_count=5, default_backoff_base_seconds=1.0)
    assert services[0].retry_count == 1
    assert services[0].backoff_base_seconds == 0.5


def test_parse_services_inherits_global_retry_defaults():
    yaml = "- name: svc\n  url: https://example.com\n"
    services = _parse_services(yaml, default_retry_count=3, default_backoff_base_seconds=2.0)
    assert services[0].retry_count == 3
    assert services[0].backoff_base_seconds == 2.0
