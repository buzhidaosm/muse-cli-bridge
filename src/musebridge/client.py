import hashlib
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

from .errors import BridgeError

READ_ACTIONS = {"status", "identity", "threads", "history", "goals", "ideas", "feed"}


def node_id():
    directory = Path.home() / "Library" / "Application Support" / "Muse Bridge"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    file = directory / "device-id"
    try:
        with file.open("x") as handle:
            os.chmod(file, 0o600)
            handle.write(secrets.token_hex(16))
    except FileExistsError:
        pass
    value = file.read_text().strip()
    if len(value) != 32 or any(c not in "0123456789abcdef" for c in value):
        raise BridgeError("CONFIG_ERROR", "Device identifier is invalid.")
    return value


def run(action, params=None, timeout=30, allow_write=False):
    if action not in READ_ACTIONS | {"send"}:
        raise BridgeError("INVALID_COMMAND", "Unsupported operation.")
    if action == "send" and not allow_write:
        raise BridgeError("WRITE_DISABLED", "Sending requires an explicit --allow-write flag.")
    if not 1 <= timeout <= 300:
        raise BridgeError("INVALID_ARGUMENT", "Timeout must be between 1 and 300 seconds.")
    request = {"action": action, "params": params or {}, "timeout": timeout}
    if action == "send":
        request["node_id"] = node_id()
    try:
        process = subprocess.run(
            [sys.executable, "-m", "musebridge.worker"],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            timeout=timeout,
            env=os.environ.copy(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise BridgeError(
            "DEADLINE_EXCEEDED",
            f"Operation exceeded {timeout} seconds.",
            "For sends, inspect history before trying again; delivery may have occurred."
            if action == "send"
            else "Retry the query when Muse is ready.",
            "unknown" if action == "send" else None,
        ) from None
    except OSError:
        raise BridgeError("WORKER_FAILED", "Unable to start the connection worker.") from None
    if process.returncode != 0:
        raise BridgeError(
            "WORKER_FAILED",
            "The connection worker stopped unexpectedly.",
            delivery="unknown" if action == "send" else None,
        )
    try:
        result = json.loads(process.stdout)
        if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
            raise ValueError()
    except (ValueError, TypeError):
        # stderr and raw responses are intentionally not echoed; they can contain credentials.
        raise BridgeError(
            "WORKER_FAILED",
            "The worker returned an invalid result.",
            delivery="unknown" if action == "send" else None,
        ) from None
    return result


def doctor():
    import importlib.metadata

    from . import __version__, auth

    report = {
        "version": __version__,
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "checks": {},
        "online_checked": False,
    }
    for package in ("curl-cffi", "noiseprotocol", "keyring", "playwright"):
        try:
            report["checks"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            report["checks"][package] = "missing"
    report["checks"]["chrome"] = Path(
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    ).is_file()
    try:
        credentials = auth.read()
        report["checks"]["keychain_session"] = "present"
        # No hashes of secrets are retained or emitted.
        del credentials
    except BridgeError as error:
        report["checks"]["keychain_session"] = error.code
    return report


def fingerprint():
    # Fingerprints are only for public protocol facts, never credentials.
    from .gateway import ROUTES

    return hashlib.sha256(json.dumps(ROUTES, sort_keys=True).encode()).hexdigest()[:16]
