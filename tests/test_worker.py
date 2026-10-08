import pytest

from musebridge import worker
from musebridge.errors import BridgeError


def test_missing_auth_proves_send_was_not_dispatched(monkeypatch):
    def missing():
        raise BridgeError("LOGIN_REQUIRED", "No session")

    monkeypatch.setattr(worker.auth, "read", missing)
    with pytest.raises(BridgeError) as error:
        worker.perform({"action": "send", "timeout": 3})
    assert error.value.delivery == "not_sent"


def test_service_error_after_send_is_ambiguous(monkeypatch):
    class HTTP:
        def __init__(self, *args):
            pass

        def assignment(self):
            return "test-vm"

        def close(self):
            pass

    class Gateway:
        def __init__(self, *args):
            pass

        def call(self, *args):
            raise BridgeError("VM_UNAVAILABLE", "Gateway reset")

        def close(self):
            pass

    monkeypatch.setattr(worker.auth, "read", lambda: [])
    monkeypatch.setattr(worker, "MuseHTTP", HTTP)
    monkeypatch.setattr(worker, "Gateway", Gateway)
    with pytest.raises(BridgeError) as error:
        worker.perform({"action": "send", "timeout": 3, "node_id": "test-node"})
    assert error.value.delivery == "unknown"
