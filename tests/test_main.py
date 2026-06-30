import json

import httpx
import pytest
import respx

from heartbeat.__main__ import main

SERVICES_JSON = json.dumps([{"name": "rlsapi", "url": "https://api.example.com"}])


@respx.mock
def test_main_exits_1_on_unhealthy(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_JSON)
    monkeypatch.delenv("INPUT_SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("HEARTBEAT_SLACK_WEBHOOK_URL", raising=False)
    respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(503))
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


@respx.mock
def test_main_no_exit_on_healthy(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_JSON)
    monkeypatch.delenv("INPUT_SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("HEARTBEAT_SLACK_WEBHOOK_URL", raising=False)
    respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(200))
    main()  # should not raise


@respx.mock
def test_main_no_exit_when_fail_disabled(monkeypatch):
    monkeypatch.setenv("INPUT_SERVICES", SERVICES_JSON)
    monkeypatch.setenv("INPUT_FAIL_ON_UNHEALTHY", "false")
    monkeypatch.delenv("INPUT_SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("HEARTBEAT_SLACK_WEBHOOK_URL", raising=False)
    respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(503))
    main()  # should not raise even though service is down


def test_main_raises_on_missing_services(monkeypatch):
    monkeypatch.delenv("INPUT_SERVICES", raising=False)
    monkeypatch.delenv("HEARTBEAT_SERVICES_JSON", raising=False)
    with pytest.raises(ValueError, match="No services configured"):
        main()
