import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from heartbeat.models import AuthConfig, ServiceConfig


@dataclass
class HeartbeatConfig:
    services: "list[ServiceConfig]"
    slack_webhook_url: "str | None" = None
    default_timeout: "float" = 10.0
    fail_on_unhealthy: "bool" = True
    default_retry_count: "int" = 5
    default_backoff_base_seconds: "float" = 1.0

    @classmethod
    def from_file(cls, path: "str | Path") -> "HeartbeatConfig":
        """
        loads configuration from a YAML file. The top-level keys map directly to
        HeartbeatConfig fields. slack_webhook_url can be overridden by the
        HEARTBEAT_SLACK_WEBHOOK_URL environment variable (useful for secrets in containers).
        """
        try:
            with open(path) as f:
                raw = yaml.safe_load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {path}") from None
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in configuration file: {e}") from e

        if not isinstance(raw, dict):
            raise ValueError("Configuration file must be a YAML mapping.")

        if "services" not in raw:
            raise ValueError("Configuration file must contain a 'services' key.")

        default_retry_count = int(raw.get("retry_count", 5))
        default_backoff_base_seconds = float(raw.get("backoff_base_seconds", 1.0))

        services = _parse_services(raw["services"], default_retry_count, default_backoff_base_seconds)

        slack_webhook_url = os.environ.get("HEARTBEAT_SLACK_WEBHOOK_URL") or raw.get("slack_webhook_url") or None

        return cls(
            services=services,
            slack_webhook_url=slack_webhook_url,
            default_timeout=float(raw.get("timeout", 10.0)),
            fail_on_unhealthy=bool(raw.get("fail_on_unhealthy", True)),
            default_retry_count=default_retry_count,
            default_backoff_base_seconds=default_backoff_base_seconds,
        )


def _parse_services(
    services_raw: "list[dict[str, Any]]",
    default_retry_count: "int" = 5,
    default_backoff_base_seconds: "float" = 1.0,
) -> "list[ServiceConfig]":
    """
    parses a list of service definitions into ServiceConfig objects. Each entry must have
    'name' and 'url' fields. Optional fields: 'health_path', 'timeout_seconds',
    'expected_status_codes', 'response_time_threshold_ms', 'retry_count', 'backoff_base_seconds',
    'method', 'body', 'proxy', 'auth'.
    """
    if not isinstance(services_raw, list):
        raise ValueError("'services' must be a YAML sequence.")

    services = []
    for i, entry in enumerate(services_raw):
        if not isinstance(entry, dict):
            raise ValueError(f"Service at index {i} must be a YAML mapping.")
        item = entry
        if "name" not in item:
            raise ValueError(f"Service at index {i} is missing required field 'name'.")
        if "url" not in item:
            raise ValueError(f"Service at index {i} is missing required field 'url'.")

        expected_codes = item.get("expected_status_codes")
        services.append(
            ServiceConfig(
                name=str(item["name"]),
                url=str(item["url"]),
                health_path=str(item.get("health_path", "/healthz")),
                timeout_seconds=float(item.get("timeout_seconds", 10.0)),
                expected_status_codes=tuple(int(c) for c in expected_codes) if expected_codes else (200,),
                response_time_threshold_ms=float(item["response_time_threshold_ms"])
                if item.get("response_time_threshold_ms") is not None
                else None,
                retry_count=int(item.get("retry_count", default_retry_count)),
                backoff_base_seconds=float(item.get("backoff_base_seconds", default_backoff_base_seconds)),
                method=str(item.get("method", "GET")).upper(),
                body=item.get("body") or None,
                proxy=str(item["proxy"]) if item.get("proxy") is not None else None,
                auth=_parse_auth(item["auth"], i) if item.get("auth") is not None else None,
            )
        )

    return services


def _parse_auth(raw: "dict[str, Any]", service_index: "int") -> "AuthConfig":
    auth_type = raw.get("type")
    if auth_type not in ("mtls", "saml_session"):
        raise ValueError(
            f"Service at index {service_index}: auth.type must be 'mtls' or 'saml_session', got {auth_type!r}."
        )

    if auth_type == "mtls":
        cert_path = raw.get("cert_path")
        key_path = raw.get("key_path")
        if not cert_path:
            raise ValueError(f"Service at index {service_index}: mtls auth requires 'cert_path'.")
        if not key_path:
            raise ValueError(f"Service at index {service_index}: mtls auth requires 'key_path'.")
        if not Path(cert_path).is_file():
            raise ValueError(f"Service at index {service_index}: cert_path '{cert_path}' does not exist.")
        if not Path(key_path).is_file():
            raise ValueError(f"Service at index {service_index}: key_path '{key_path}' does not exist.")
        return AuthConfig(type="mtls", cert_path=str(cert_path), key_path=str(key_path))

    # saml_session
    token_env_var = raw.get("token_env_var")
    if not token_env_var:
        raise ValueError(f"Service at index {service_index}: saml_session auth requires 'token_env_var'.")
    return AuthConfig(type="saml_session", token_env_var=str(token_env_var))
