"""Single-operation worker: its parent can terminate a blocked WebSocket receive."""

import json
import sys

from . import auth
from .errors import BridgeError, failure, success
from .gateway import ROUTES, Gateway, MuseHTTP


def perform(request):
    action = request.get("action")
    if action not in {"status", *ROUTES}:
        raise BridgeError("INVALID_COMMAND", "Unsupported operation.")
    http = None
    gateway = None
    dispatched = False
    try:
        http = MuseHTTP(auth.read(), request["timeout"])
        vm = http.assignment()
        if action == "status":
            http.access_token()
            return {"authenticated": True, "vm_id": vm, "gateway_verified": False}
        gateway = Gateway(http, vm)
        params = dict(request.get("params", {}))
        if action == "send":
            params["node_id"] = request["node_id"]
            params["capabilities"] = {}
        dispatched = True
        return gateway.call(action, params)
    except BridgeError as error:
        if action == "send":
            error.delivery = "unknown" if dispatched else "not_sent"
        raise
    finally:
        if gateway:
            gateway.close()
        if http:
            http.close()


def main():
    action = None
    try:
        request = json.loads(sys.stdin.read(1024 * 1024))
        action = request.get("action")
        result = success(perform(request))
    except BridgeError as error:
        result = failure(error)
    except Exception:
        result = failure(
            BridgeError(
                "CONNECTION_FAILED",
                "Could not complete the Muse connection.",
                "Run muse-bridge doctor, then check your connection.",
                "unknown" if action == "send" else None,
            )
        )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
