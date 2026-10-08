"""Original transport implementation using public protocol facts; see PROVENANCE.md."""

import json
import secrets
from urllib.parse import urlencode

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from curl_cffi import requests
from noise.connection import Keypair, NoiseConnection

from . import wire
from .auth import cookie_header
from .errors import BridgeError
from .trust import check_standard_payload

ORIGIN = "https://muse.ai"
ENDPOINT = "wss://hatch.metaaivm.com/v1/noise"
ROUTES = {
    "identity": ("GET", "/identity"),
    "threads": ("GET", "/api/session/list"),
    "history": ("GET", "/chat/history"),
    "goals": ("GET", "/goals"),
    "ideas": ("GET", "/api/idea-cards"),
    "feed": ("GET", "/api/feed"),
    "send": ("POST", "/chat/stream"),
}


class MuseHTTP:
    def __init__(self, cookies, timeout):
        self.timeout = timeout
        self.session = requests.Session(impersonate="chrome")
        self.headers = {
            "Cookie": cookie_header(cookies),
            "Origin": ORIGIN,
            "Referer": ORIGIN + "/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def close(self):
        self.session.close()

    def call(self, path, method="GET", body=None, bearer=None):
        headers = dict(self.headers)
        if bearer:
            headers["Authorization"] = "Bearer " + bearer
        result = self.session.request(
            method,
            ORIGIN + path,
            headers=headers,
            json=body,
            timeout=self.timeout,
            allow_redirects=False,
        )
        if result.status_code in (401, 403) or 300 <= result.status_code < 400:
            raise BridgeError(
                "LOGIN_REQUIRED",
                "Muse rejected the saved session.",
                "Run muse-bridge login again. A checkpoint may require your attention.",
            )
        if result.status_code >= 500:
            raise BridgeError("SERVICE_UNAVAILABLE", "Muse is temporarily unavailable.")
        if result.status_code != 200:
            raise BridgeError("HTTP_ERROR", f"Muse returned HTTP {result.status_code}.")
        if len(result.content) > wire.MAX_MESSAGE:
            raise wire.bad()
        try:
            data = result.json()
        except ValueError:
            raise BridgeError(
                "PROTOCOL_CHANGED", "Muse returned an unexpected response format."
            ) from None
        if not isinstance(data, dict):
            raise BridgeError("PROTOCOL_CHANGED", "Muse returned an unexpected response format.")
        return data

    def access_token(self):
        data = self.call("/api/auth/check", "POST")
        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            raise BridgeError(
                "LOGIN_REQUIRED",
                "Muse did not issue an access token.",
                "Run muse-bridge login again.",
            )
        return token

    def assignment(self):
        data = self.call("/api/session")
        if data.get("status") == "unavailable":
            raise BridgeError(
                "VM_UNAVAILABLE",
                "Your Muse VM is not ready.",
                "Open Muse and wait for it to become ready, then retry the query.",
            )
        vm = data.get("vm_id")
        if not isinstance(vm, str) or not vm or len(vm) > 256:
            raise BridgeError("PROTOCOL_CHANGED", "Muse did not return a VM identifier.")
        return vm

    def gateway_token(self, vm, access):
        data = self.call(
            "/api/hatch/token",
            "POST",
            {"vmAddress": "wss://" + vm + ".metaaivm.com/", "vmName": vm},
            bearer=access,
        )
        token = data.get("token")
        if not isinstance(token, str) or not token:
            raise BridgeError("PROTOCOL_CHANGED", "Muse did not return a gateway token.")
        return token


class Gateway:
    def __init__(self, http: MuseHTTP, vm: str):
        self.http = http
        self.socket = None
        self.cipher = None
        self.sequence = 0
        self.reassembly = wire.Reassembly()
        access = http.access_token()
        token = http.gateway_token(vm, access)
        socket = requests.WebSocket()
        try:
            socket.connect(
                ENDPOINT + "?" + urlencode({"vm_id": vm, "auth_token": token}),
                impersonate="chrome",
                timeout=http.timeout,
                verify=True,
            )
            cipher = NoiseConnection.from_name(b"Noise_XX_25519_AESGCM_SHA256")
            cipher.set_as_initiator()
            private = X25519PrivateKey.generate().private_bytes(
                serialization.Encoding.Raw,
                serialization.PrivateFormat.Raw,
                serialization.NoEncryption(),
            )
            cipher.set_keypair_from_private_bytes(Keypair.STATIC, private)
            cipher.start_handshake()
            socket.send(bytes(cipher.write_message()))
            second, _ = socket.recv()
            handshake_payload = bytes(cipher.read_message(second))
            self.mode = check_standard_payload(
                handshake_payload, cipher.noise_protocol.handshake_state.rs.public_bytes
            )
            socket.send(bytes(cipher.write_message()))
            if not cipher.handshake_finished:
                raise BridgeError("PROTOCOL_ERROR", "Gateway handshake did not finish.")
            self.socket, self.cipher = socket, cipher
        except BaseException:
            socket.close()
            raise

    def close(self):
        if self.socket:
            self.socket.close()
            self.socket = None

    def receive(self):
        while True:
            encrypted, _ = self.socket.recv()
            if len(encrypted) > 65535:
                raise wire.bad()
            plain = bytes(self.cipher.decrypt(encrypted))
            assembled = self.reassembly.accept(plain)
            if assembled is not None:
                return wire.response(assembled)

    def call(self, action, params=None):
        verb, path = ROUTES[action]
        params = params or {}
        body = b""
        if verb == "GET" and params:
            path += "?" + urlencode(params)
        elif verb != "GET":
            body = json.dumps(params, ensure_ascii=False, separators=(",", ":")).encode()
        self.sequence += 1
        stream = self.sequence
        request = wire.request(stream, verb, path, body)
        for chunk in wire.chunks(request, secrets.randbits(63)):
            self.socket.send(bytes(self.cipher.encrypt(chunk)))
        status = None
        payload = bytearray()
        # Exactly one receiver. Parent process enforces the entire operation deadline.
        while True:
            target, incoming_status, data, complete = self.receive()
            if target != stream:
                continue
            if incoming_status is not None:
                status = incoming_status
            if not isinstance(data, bytes):
                raise wire.bad()
            payload.extend(data)
            if len(payload) > wire.MAX_MESSAGE:
                raise wire.bad()
            if complete:
                break
        if status is None:
            raise BridgeError("PROTOCOL_ERROR", "Gateway response has no status.")
        if not 200 <= status < 300:
            code = "VM_UNAVAILABLE" if status in (502, 503, 504) else "GATEWAY_ERROR"
            raise BridgeError(code, f"Gateway returned HTTP {status}.")
        try:
            if action == "send":
                # Return the actual stream records; do not guess reply correlation from history.
                records = [json.loads(line) for line in payload.splitlines() if line.strip()]
                return {
                    "delivery": "acknowledged",
                    "records": records,
                    "assistant_reply_verified": False,
                }
            data = json.loads(payload) if payload else {}
        except ValueError:
            raise BridgeError(
                "PROTOCOL_CHANGED", "Gateway response could not be decoded."
            ) from None
        if isinstance(data, dict) and data.get("ok") is False:
            raise BridgeError("GATEWAY_ERROR", "Muse rejected the query.")
        return data.get("result", data) if isinstance(data, dict) else data
