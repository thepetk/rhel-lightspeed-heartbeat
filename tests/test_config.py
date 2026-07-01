import pytest

from heartbeat.config import HeartbeatConfig, _parse_services
from heartbeat.models import AuthConfig

SERVICES_CONFIG = """
services:
  - name: api
    url: https://api.example.com
  - name: gateway
    url: https://gateway.example.com
    health_path: /health
    response_time_threshold_ms: 500
"""

SERVICES_RAW = [
    {"name": "api", "url": "https://api.example.com"},
    {
        "name": "gateway",
        "url": "https://gateway.example.com",
        "health_path": "/health",
        "response_time_threshold_ms": 500,
    },
]


def write_config(tmp_path, content: str):
    p = tmp_path / "config.yaml"
    p.write_text(content)
    return p


def test_from_file_basic(tmp_path):
    p = write_config(tmp_path, SERVICES_CONFIG)
    config = HeartbeatConfig.from_file(p)
    assert len(config.services) == 2
    assert config.services[0].name == "api"
    assert config.services[1].name == "gateway"
    assert config.services[1].response_time_threshold_ms == 500.0


def test_from_file_slack_in_config(tmp_path):
    p = write_config(tmp_path, SERVICES_CONFIG + "slack_webhook_url: https://hooks.slack.com/test\n")
    config = HeartbeatConfig.from_file(p)
    assert config.slack_webhook_url == "https://hooks.slack.com/test"


def test_from_file_slack_env_override(tmp_path, monkeypatch):
    p = write_config(tmp_path, SERVICES_CONFIG + "slack_webhook_url: https://hooks.slack.com/from-file\n")
    monkeypatch.setenv("HEARTBEAT_SLACK_WEBHOOK_URL", "https://hooks.slack.com/from-env")
    config = HeartbeatConfig.from_file(p)
    assert config.slack_webhook_url == "https://hooks.slack.com/from-env"


def test_from_file_no_slack(tmp_path, monkeypatch):
    p = write_config(tmp_path, SERVICES_CONFIG)
    monkeypatch.delenv("HEARTBEAT_SLACK_WEBHOOK_URL", raising=False)
    config = HeartbeatConfig.from_file(p)
    assert config.slack_webhook_url is None


def test_from_file_custom_timeout(tmp_path):
    p = write_config(tmp_path, SERVICES_CONFIG + "timeout: 30\n")
    config = HeartbeatConfig.from_file(p)
    assert config.default_timeout == 30.0


def test_from_file_fail_on_unhealthy_false(tmp_path):
    p = write_config(tmp_path, SERVICES_CONFIG + "fail_on_unhealthy: false\n")
    config = HeartbeatConfig.from_file(p)
    assert config.fail_on_unhealthy is False


def test_from_file_fail_on_unhealthy_default(tmp_path):
    p = write_config(tmp_path, SERVICES_CONFIG)
    config = HeartbeatConfig.from_file(p)
    assert config.fail_on_unhealthy is True


def test_from_file_retry_defaults(tmp_path):
    p = write_config(tmp_path, SERVICES_CONFIG)
    config = HeartbeatConfig.from_file(p)
    assert config.default_retry_count == 5
    assert config.default_backoff_base_seconds == 1.0


def test_from_file_custom_retry_count(tmp_path):
    p = write_config(tmp_path, SERVICES_CONFIG + "retry_count: 3\n")
    config = HeartbeatConfig.from_file(p)
    assert config.default_retry_count == 3
    assert all(s.retry_count == 3 for s in config.services)


def test_from_file_custom_backoff_base_seconds(tmp_path):
    p = write_config(tmp_path, SERVICES_CONFIG + "backoff_base_seconds: 2.5\n")
    config = HeartbeatConfig.from_file(p)
    assert config.default_backoff_base_seconds == 2.5
    assert all(s.backoff_base_seconds == 2.5 for s in config.services)


def test_from_file_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        HeartbeatConfig.from_file(tmp_path / "nonexistent.yaml")


def test_from_file_invalid_yaml(tmp_path):
    p = write_config(tmp_path, "key: [unclosed")
    with pytest.raises(ValueError, match="Invalid YAML"):
        HeartbeatConfig.from_file(p)


def test_from_file_missing_services_key(tmp_path):
    p = write_config(tmp_path, "timeout: 10\n")
    with pytest.raises(ValueError, match="'services'"):
        HeartbeatConfig.from_file(p)


def test_from_file_not_a_mapping(tmp_path):
    p = write_config(tmp_path, "- item1\n- item2\n")
    with pytest.raises(ValueError, match="YAML mapping"):
        HeartbeatConfig.from_file(p)


def test_parse_services_defaults():
    services = _parse_services([{"name": "svc", "url": "https://example.com"}])
    assert services[0].health_path == "/healthz"
    assert services[0].timeout_seconds == 10.0
    assert services[0].expected_status_codes == (200,)
    assert services[0].response_time_threshold_ms is None


def test_parse_services_custom_expected_codes():
    services = _parse_services([{"name": "svc", "url": "https://example.com", "expected_status_codes": [200, 204]}])
    assert services[0].expected_status_codes == (200, 204)


def test_parse_services_not_a_list():
    with pytest.raises(ValueError, match="must be a YAML sequence"):
        _parse_services({"name": "svc"})  # type: ignore[arg-type]


def test_parse_services_missing_name():
    with pytest.raises(ValueError, match="missing required field 'name'"):
        _parse_services([{"url": "https://example.com"}])


def test_parse_services_missing_url():
    with pytest.raises(ValueError, match="missing required field 'url'"):
        _parse_services([{"name": "svc"}])


def test_parse_services_item_not_a_dict():
    with pytest.raises(ValueError, match="must be a YAML mapping"):
        _parse_services(["not-a-dict"])  # type: ignore[list-item]


def test_parse_services_per_service_retry_override():
    services = _parse_services(
        [{"name": "svc", "url": "https://example.com", "retry_count": 1, "backoff_base_seconds": 0.5}],
        default_retry_count=5,
        default_backoff_base_seconds=1.0,
    )
    assert services[0].retry_count == 1
    assert services[0].backoff_base_seconds == 0.5


def test_parse_services_inherits_global_retry_defaults():
    services = _parse_services(
        [{"name": "svc", "url": "https://example.com"}],
        default_retry_count=3,
        default_backoff_base_seconds=2.0,
    )
    assert services[0].retry_count == 3
    assert services[0].backoff_base_seconds == 2.0


def test_parse_services_method_post():
    services = _parse_services([{"name": "svc", "url": "https://example.com", "method": "post"}])
    assert services[0].method == "POST"


def test_parse_services_method_default_get():
    services = _parse_services([{"name": "svc", "url": "https://example.com"}])
    assert services[0].method == "GET"


def test_parse_services_body():
    services = _parse_services(
        [{"name": "svc", "url": "https://example.com", "body": {"question": "What is SELinux?"}}]
    )
    assert services[0].body == {"question": "What is SELinux?"}


def test_parse_services_proxy():
    services = _parse_services([{"name": "svc", "url": "https://example.com", "proxy": "http://proxy:3128"}])
    assert services[0].proxy == "http://proxy:3128"


def test_parse_services_auth_mtls(tmp_path):
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_text("cert")
    key.write_text("key")
    services = _parse_services(
        [
            {
                "name": "svc",
                "url": "https://example.com",
                "auth": {"type": "mtls", "cert_path": str(cert), "key_path": str(key)},
            }
        ]
    )
    assert services[0].auth == AuthConfig(type="mtls", cert_path=str(cert), key_path=str(key))


def test_parse_services_auth_mtls_missing_cert(tmp_path):
    key = tmp_path / "key.pem"
    key.write_text("key")
    with pytest.raises(ValueError, match="cert_path"):
        _parse_services(
            [
                {
                    "name": "svc",
                    "url": "https://example.com",
                    "auth": {"type": "mtls", "cert_path": "/nonexistent/cert.pem", "key_path": str(key)},
                }
            ]
        )


def test_parse_services_auth_mtls_missing_key(tmp_path):
    cert = tmp_path / "cert.pem"
    cert.write_text("cert")
    with pytest.raises(ValueError, match="key_path"):
        _parse_services(
            [
                {
                    "name": "svc",
                    "url": "https://example.com",
                    "auth": {"type": "mtls", "cert_path": str(cert), "key_path": "/nonexistent/key.pem"},
                }
            ]
        )


def test_parse_services_auth_saml_session():
    services = _parse_services(
        [
            {
                "name": "svc",
                "url": "https://example.com",
                "auth": {"type": "saml_session", "token_env_var": "MY_TOKEN"},
            }
        ]
    )
    assert services[0].auth == AuthConfig(type="saml_session", token_env_var="MY_TOKEN")


def test_parse_services_auth_saml_session_missing_token_env_var():
    with pytest.raises(ValueError, match="token_env_var"):
        _parse_services([{"name": "svc", "url": "https://example.com", "auth": {"type": "saml_session"}}])


def test_parse_services_auth_invalid_type():
    with pytest.raises(ValueError, match=r"mtls.*saml_session"):
        _parse_services([{"name": "svc", "url": "https://example.com", "auth": {"type": "oauth"}}])
