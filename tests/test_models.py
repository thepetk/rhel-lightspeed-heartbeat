from dataclasses import FrozenInstanceError

import pytest

from heartbeat.models import AlertState, HealthResult, HealthStatus, ServiceConfig


def test_service_config_defaults():
    s = ServiceConfig(name="svc", url="https://example.com")
    assert s.health_path == "/healthz"
    assert s.timeout_seconds == 10.0
    assert s.expected_status_codes == (200,)
    assert s.response_time_threshold_ms is None


def test_service_config_custom():
    s = ServiceConfig(
        name="svc",
        url="https://example.com",
        health_path="/health",
        timeout_seconds=5.0,
        expected_status_codes=(200, 204),
        response_time_threshold_ms=1000.0,
    )
    assert s.health_path == "/health"
    assert s.timeout_seconds == 5.0
    assert s.expected_status_codes == (200, 204)
    assert s.response_time_threshold_ms == 1000.0


def test_service_config_is_frozen():
    s = ServiceConfig(name="svc", url="https://example.com")
    with pytest.raises(FrozenInstanceError):
        s.name = "other"  # type: ignore[misc]


def test_health_result_is_healthy(healthy_result):
    assert healthy_result.is_healthy is True
    assert healthy_result.is_ok is True


def test_health_result_unhealthy(unhealthy_result):
    assert unhealthy_result.is_healthy is False
    assert unhealthy_result.is_ok is False


def test_health_result_degraded(degraded_result):
    assert degraded_result.is_healthy is False
    assert degraded_result.is_ok is True


def test_health_result_timeout(service):
    r = HealthResult(service=service, status=HealthStatus.TIMEOUT, error_message="timed out")
    assert r.is_healthy is False
    assert r.is_ok is False


def test_health_result_error(service):
    r = HealthResult(service=service, status=HealthStatus.ERROR, error_message="connection refused")
    assert r.is_healthy is False
    assert r.is_ok is False


def test_health_result_is_frozen(healthy_result):
    with pytest.raises(FrozenInstanceError):
        healthy_result.status = HealthStatus.UNHEALTHY  # type: ignore[misc]


def test_alert_payload_is_frozen(firing_payload):
    with pytest.raises(FrozenInstanceError):
        firing_payload.summary = "changed"  # type: ignore[misc]


def test_alert_payload_state(firing_payload, resolved_payload):
    assert firing_payload.state == AlertState.FIRING
    assert resolved_payload.state == AlertState.RESOLVED
