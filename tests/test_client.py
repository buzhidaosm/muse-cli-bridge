import subprocess

import pytest

from musebridge import client
from musebridge.errors import BridgeError


def test_write_denied_before_worker_starts(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Worker must not start without write authorization")

    monkeypatch.setattr(subprocess, "run", unexpected)
    with pytest.raises(BridgeError) as caught:
        client.run("send")
    assert caught.value.code == "WRITE_DISABLED"


def test_deadline_send_delivery_is_unknown_and_not_retried(monkeypatch):
    calls = []
    monkeypatch.setattr(client, "node_id", lambda: "test-device")

    def timeout(*args, **kwargs):
        calls.append(1)
        raise subprocess.TimeoutExpired("worker", kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(BridgeError) as caught:
        client.run("send", {"items": []}, timeout=1, allow_write=True)
    assert caught.value.delivery == "unknown"
    assert calls == [1]


def test_untrusted_worker_output_not_echoed(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, "SECRET", "Bearer SECRET"),
    )
    with pytest.raises(BridgeError) as caught:
        client.run("status")
    assert "SECRET" not in str(caught.value)


def test_protocol_error_result_is_preserved(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            a, 0, '{"ok":false,"error":{"code":"LOGIN_REQUIRED","message":"Login"}}', ""
        ),
    )
    assert client.run("status")["error"]["code"] == "LOGIN_REQUIRED"


def test_real_blocked_process_is_terminated_at_deadline(monkeypatch):
    import sys
    import time

    actual_run = subprocess.run

    def blocked(*args, **kwargs):
        return actual_run([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)

    monkeypatch.setattr(subprocess, "run", blocked)
    start = time.monotonic()
    with pytest.raises(BridgeError) as error:
        client.run("history", timeout=1)
    assert error.value.code == "DEADLINE_EXCEEDED"
    assert time.monotonic() - start < 4
