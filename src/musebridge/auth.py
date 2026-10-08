"""Credential storage restricted to the macOS Keychain, never plaintext files."""

import json
import sys

from .errors import BridgeError

SERVICE = "muse-bridge-cli"
ACCOUNT = "muse.ai/session"


def backend():
    if sys.platform != "darwin":
        raise BridgeError("KEYCHAIN_UNAVAILABLE", "This version requires the macOS Keychain.")
    from keyring.backends.macOS import Keyring

    return Keyring()


def normalize_cookies(cookies):
    if not isinstance(cookies, list) or len(cookies) > 100:
        raise BridgeError("INVALID_CREDENTIAL", "Expected a browser cookie list.")
    accepted = {}
    for cookie in cookies:
        if not isinstance(cookie, dict):
            raise BridgeError("INVALID_CREDENTIAL", "Invalid cookie entry.")
        domain = str(cookie.get("domain", "")).lstrip(".").lower()
        # Subdomain and unrelated-domain cookies are not forwarded to muse.ai.
        if domain != "muse.ai" or cookie.get("path", "/") != "/":
            continue
        name, value = cookie.get("name"), cookie.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            raise BridgeError("INVALID_CREDENTIAL", "Invalid cookie entry.")
        if not name or any(c in name for c in "=;\r\n\x00 \t"):
            raise BridgeError("INVALID_CREDENTIAL", "Invalid cookie name.")
        if any(c in value for c in ";\r\n\x00") or len(value) > 16384:
            raise BridgeError("INVALID_CREDENTIAL", "Invalid cookie value.")
        if name in accepted and accepted[name] != value:
            raise BridgeError("INVALID_CREDENTIAL", "Conflicting cookie values.")
        accepted[name] = value
    if not accepted.get("hatch_sess"):
        raise BridgeError(
            "LOGIN_REQUIRED", "Muse session cookie is missing.", "Run muse-bridge login."
        )
    return [
        {"domain": "muse.ai", "path": "/", "name": k, "value": v}
        for k, v in sorted(accepted.items())
    ]


def cookie_header(cookies):
    return "; ".join(f"{c['name']}={c['value']}" for c in normalize_cookies(cookies))


def read():
    try:
        value = backend().get_password(SERVICE, ACCOUNT)
    except BridgeError:
        raise
    except Exception:
        raise BridgeError(
            "KEYCHAIN_ERROR", "Unable to read the Muse session from Keychain."
        ) from None
    if not value:
        raise BridgeError("LOGIN_REQUIRED", "No saved Muse login.", "Run muse-bridge login.")
    try:
        return normalize_cookies(json.loads(value))
    except (ValueError, TypeError):
        raise BridgeError("INVALID_CREDENTIAL", "Saved session has an invalid format.") from None


def save(cookies):
    value = json.dumps(normalize_cookies(cookies), separators=(",", ":"))
    try:
        backend().set_password(SERVICE, ACCOUNT, value)
    except BridgeError:
        raise
    except Exception:
        raise BridgeError(
            "KEYCHAIN_ERROR", "Unable to save the Muse session to Keychain."
        ) from None


def remove():
    try:
        store = backend()
        if store.get_password(SERVICE, ACCOUNT) is not None:
            store.delete_password(SERVICE, ACCOUNT)
    except BridgeError:
        raise
    except Exception:
        raise BridgeError("KEYCHAIN_ERROR", "Unable to remove the saved Muse session.") from None
    return {"removed_local_session": True, "server_session_revoked": False}
