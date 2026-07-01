import httpx
import pytest
import respx

from heartbeat.__main__ import main

SERVICES_YAML = "services:\n  - name: rlsapi\n    url: https://api.example.com\n"


def write_config(tmp_path, content: str):
    p = tmp_path / "config.yaml"
    p.write_text(content)
    return p


@respx.mock
def test_main_exits_1_on_unhealthy(tmp_path, monkeypatch):
    p = write_config(tmp_path, SERVICES_YAML)
    monkeypatch.setattr("sys.argv", ["heartbeat", str(p)])
    monkeypatch.delenv("HEARTBEAT_SLACK_WEBHOOK_URL", raising=False)
    respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(503))
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


@respx.mock
def test_main_no_exit_on_healthy(tmp_path, monkeypatch):
    p = write_config(tmp_path, SERVICES_YAML)
    monkeypatch.setattr("sys.argv", ["heartbeat", str(p)])
    monkeypatch.delenv("HEARTBEAT_SLACK_WEBHOOK_URL", raising=False)
    respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(200))
    main()  # should not raise


@respx.mock
def test_main_no_exit_when_fail_disabled(tmp_path, monkeypatch):
    p = write_config(tmp_path, SERVICES_YAML + "fail_on_unhealthy: false\n")
    monkeypatch.setattr("sys.argv", ["heartbeat", str(p)])
    monkeypatch.delenv("HEARTBEAT_SLACK_WEBHOOK_URL", raising=False)
    respx.get("https://api.example.com/healthz").mock(return_value=httpx.Response(503))
    main()  # should not raise even though service is down


def test_main_raises_on_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["heartbeat", str(tmp_path / "nonexistent.yaml")])
    with pytest.raises(FileNotFoundError):
        main()
