import os
from dataclasses import dataclass
from typing import Any, cast

import yaml

from heartbeat.models import ServiceConfig


@dataclass
class HeartbeatConfig:
    services: "list[ServiceConfig]"
    slack_webhook_url: "str | None" = None
    default_timeout: "float" = 10.0
    fail_on_unhealthy: "bool" = True

    @classmethod
    def from_env(cls) -> "HeartbeatConfig":
        """
        fetches configuration from environment variables. It looks for the following variables:
        - `INPUT_SERVICES` or `HEARTBEAT_SERVICES`: YAML sequence of service definitions.
        """

        # fetch services configuration from environment variables
        services_yaml = os.environ.get("INPUT_SERVICES") or os.environ.get("HEARTBEAT_SERVICES")
        if not services_yaml:
            raise ValueError(
                "No services configured. Set INPUT_SERVICES or HEARTBEAT_SERVICES "
                "to a YAML sequence of service definitions."
            )

        services = _parse_services(services_yaml)

        # fetch optional slack webhook url from environment variables
        slack_webhook_url = os.environ.get("INPUT_SLACK_WEBHOOK_URL") or os.environ.get("HEARTBEAT_SLACK_WEBHOOK_URL")

        # fetch optional default timeout and fail_on_unhealthy from environment variables
        raw_timeout = os.environ.get("INPUT_TIMEOUT") or os.environ.get("HEARTBEAT_TIMEOUT")
        default_timeout = float(raw_timeout) if raw_timeout else 10.0

        # fetch optional fail_on_unhealthy from environment variables
        raw_fail = os.environ.get("INPUT_FAIL_ON_UNHEALTHY") or os.environ.get("HEARTBEAT_FAIL_ON_UNHEALTHY")
        fail_on_unhealthy = raw_fail.lower() not in ("false", "0", "no") if raw_fail else True

        return cls(
            services=services,
            slack_webhook_url=slack_webhook_url,
            default_timeout=default_timeout,
            fail_on_unhealthy=fail_on_unhealthy,
        )


def _parse_services(services_yaml: "str") -> "list[ServiceConfig]":
    """
    parses the services configuration from a YAML string.
    The expected format is a YAML sequence of mappings, each containing:
    - `name`: The name of the service (string, required).
    - `url`: The base URL of the service (string, required).
    - `health_path`: The path to the health endpoint (string, optional, default: "/healthz").
    - `timeout_seconds`: The timeout for the health check request (float, optional, default: 10.0).
    - `expected_status_codes`: A list of expected HTTP status codes (list of int, optional, default: [200]).
    - `response_time_threshold_ms`: The response time threshold in milliseconds (float, optional).
    """
    try:
        raw = yaml.safe_load(services_yaml)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in services configuration: {e}") from e

    if not isinstance(raw, list):
        raise ValueError("Services configuration must be a YAML sequence.")

    services = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"Service at index {i} must be a YAML mapping.")
        item = cast(dict[str, Any], entry)
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
            )
        )

    return services
