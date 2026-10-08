import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from noise.connection import Keypair, NoiseConnection

from musebridge import gateway, wire
from musebridge.errors import BridgeError


def cipher(initiator):
    c = NoiseConnection.from_name(b"Noise_XX_25519_AESGCM_SHA256")
    (c.set_as_initiator if initiator else c.set_as_responder)()
    private = X25519PrivateKey.generate().private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    c.set_keypair_from_private_bytes(Keypair.STATIC, private)
    c.start_handshake()
    return c


class Peer:
    """Simulated Noise responder; inspect semantic requests and return split responses."""

    def __init__(self, attested=False, standard_bundle=False):
        self.cipher = cipher(False)
        self.stage = 0
        self.queue = []
        self.requests = []
        self.closed = False
        self.attested = attested
        self.standard_bundle = standard_bundle
        self.assembler = wire.Reassembly()

    def connect(self, url, **kwargs):
        assert url.startswith("wss://hatch.metaaivm.com/v1/noise?")
        assert kwargs["verify"] is True

    def send(self, data):
        if self.stage == 0:
            self.cipher.read_message(data)
            self.queue.append(
                bytes(
                    self.cipher.write_message(
                        (
                            wire.blob(
                                2,
                                wire.blob(
                                    1, self.cipher.noise_protocol.handshake_state.s.public_bytes
                                ),
                            )
                            if self.standard_bundle
                            else b"attested"
                            if self.attested
                            else b""
                        )
                    )
                )
            )
            self.stage = 1
        elif self.stage == 1:
            self.cipher.read_message(data)
            self.stage = 2
        else:
            assembled = self.assembler.accept(bytes(self.cipher.decrypt(data)))
            if assembled is None:
                return
            envelope = wire.fields(assembled)
            frame = wire.fields(wire.last(envelope, 2))
            application = wire.fields(wire.last(frame, 2))
            self.requests.append(application)
            stream = wire.last(frame, 1)
            body = b'{"result":{"entries":[1,2]}}'
            start = wire.integer(1, 200) + wire.blob(3, body[:8])
            frame1 = wire.integer(1, stream) + wire.blob(3, start)
            end = wire.blob(1, body[8:]) + wire.integer(2, 1)
            frame2 = wire.integer(1, stream) + wire.blob(4, end)
            for index, frame in enumerate((frame1, frame2)):
                for chunk in wire.chunks(wire.blob(1, frame), index + 10):
                    self.queue.append(bytes(self.cipher.encrypt(chunk)))

    def recv(self):
        return self.queue.pop(0), 2

    def close(self):
        self.closed = True


class HTTP:
    timeout = 5

    def access_token(self):
        return "test-access"

    def gateway_token(self, *args):
        return "test-gateway"


def test_noise_interoperability_and_split_gateway_response(monkeypatch):
    peer = Peer()
    monkeypatch.setattr(gateway.requests, "WebSocket", lambda: peer)
    client = gateway.Gateway(HTTP(), "test-vm")
    assert client.call("history", {"limit": 2, "session_id": "a&b"}) == {"entries": [1, 2]}
    assert wire.last(peer.requests[0], 2) == b"/chat/history?limit=2&session_id=a%26b"
    client.close()
    assert peer.closed


def test_attested_vm_rejected_and_socket_closed(monkeypatch):
    peer = Peer(attested=True)
    monkeypatch.setattr(gateway.requests, "WebSocket", lambda: peer)
    with pytest.raises(BridgeError) as error:
        gateway.Gateway(HTTP(), "test-vm")
    assert error.value.code == "UNSUPPORTED_VM_MODE"
    assert peer.closed


def test_truncated_reply_is_not_reported_as_success(monkeypatch):
    peer = Peer()
    monkeypatch.setattr(gateway.requests, "WebSocket", lambda: peer)
    client = gateway.Gateway(HTTP(), "test-vm")
    original = peer.send

    def send(data):
        original(data)
        peer.queue.pop()

    peer.send = send
    with pytest.raises(IndexError):
        client.call("history")
    client.close()


def test_http_errors_do_not_echo_private_body(monkeypatch):
    class Response:
        status_code = 403
        content = b"Bearer PRIVATE"

    class Session:
        def request(self, *args, **kwargs):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(gateway.requests, "Session", lambda **kw: Session())
    http = gateway.MuseHTTP([{"name": "hatch_sess", "value": "test", "domain": "muse.ai"}], 5)
    with pytest.raises(BridgeError) as error:
        http.assignment()
    assert error.value.code == "LOGIN_REQUIRED"
    assert "PRIVATE" not in str(error.value)


def test_vm_unavailable_is_a_defined_error(monkeypatch):
    monkeypatch.setattr(
        gateway.MuseHTTP,
        "call",
        lambda *a, **k: {"status": "unavailable", "vm_resolution_issue": {"kind": "retryable"}},
    )
    http = gateway.MuseHTTP([{"name": "hatch_sess", "value": "test", "domain": "muse.ai"}], 5)
    try:
        with pytest.raises(BridgeError) as error:
            http.assignment()
        assert error.value.code == "VM_UNAVAILABLE"
    finally:
        http.close()


def test_gateway_token_uses_vm_hostname(monkeypatch):
    seen = []

    def call(self, path, method="GET", body=None, bearer=None):
        seen.append((path, method, body, bearer))
        return {"token": "test"}

    monkeypatch.setattr(gateway.MuseHTTP, "call", call)
    http = gateway.MuseHTTP([{"name": "hatch_sess", "value": "test", "domain": "muse.ai"}], 5)
    assert http.gateway_token("vm-123", "test-access") == "test"
    assert seen == [
        (
            "/api/hatch/token",
            "POST",
            {"vmAddress": "wss://vm-123.metaaivm.com/", "vmName": "vm-123"},
            "test-access",
        )
    ]
    http.close()


def test_send_returns_acknowledgement_without_claiming_assistant_completion(monkeypatch):
    import json

    peer = Peer()
    monkeypatch.setattr(gateway.requests, "WebSocket", lambda: peer)
    client = gateway.Gateway(HTTP(), "test-vm")
    result = client.call("send", {"items": [{"type": "text", "text": "test-message"}]})
    assert result["delivery"] == "acknowledged"
    assert result["assistant_reply_verified"] is False
    assert len(peer.requests) == 1
    body = json.loads(wire.last(peer.requests[0], 4))
    assert body["items"][0]["text"] == "test-message"
    client.close()


def test_non_tee_payload_completes_handshake_and_query(monkeypatch):
    peer = Peer(standard_bundle=True)
    monkeypatch.setattr(gateway.requests, "WebSocket", lambda: peer)
    client = gateway.Gateway(HTTP(), "test-vm")
    assert client.mode == "standard_non_tee"
    assert client.call("history") == {"entries": [1, 2]}
    client.close()
