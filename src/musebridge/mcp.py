"""Read-only MCP stdio server using newline-delimited JSON-RPC 2.0.

MCP deliberately exposes neither sending nor credential-management commands.
"""

import json

from . import __version__
from .client import run
from .errors import BridgeError, failure

TOOLS = {
    "muse_status": (
        "status",
        "Check login and VM assignment; does not verify gateway connectivity.",
    ),
    "muse_identity": ("identity", "Read the Muse agent identity."),
    "muse_threads": ("threads", "List Muse chats."),
    "muse_history": ("history", "Read recent messages; optional thread identifier."),
    "muse_goals": ("goals", "Read goals."),
    "muse_ideas": ("ideas", "Read ideas."),
    "muse_feed": ("feed", "Read the feed."),
}
PROTOCOLS = {"2024-11-05", "2025-03-26", "2025-06-18"}


def schema(name):
    properties = {"timeout": {"type": "integer", "minimum": 1, "maximum": 300}}
    if name in {"muse_history", "muse_feed"}:
        properties["limit"] = {"type": "integer", "minimum": 1, "maximum": 100}
    if name == "muse_history":
        properties["thread"] = {"type": "string", "minLength": 1, "maxLength": 256}
    return {"type": "object", "properties": properties, "additionalProperties": False}


def params_for(name, args):
    if not isinstance(args, dict) or set(args) - set(schema(name)["properties"]):
        raise BridgeError("INVALID_ARGUMENT", "Unknown or invalid tool arguments.")
    timeout = args.get("timeout", 30)
    if type(timeout) is not int or not 1 <= timeout <= 300:
        raise BridgeError("INVALID_ARGUMENT", "Timeout must be an integer between 1 and 300.")
    params = {}
    if "limit" in schema(name)["properties"]:
        limit = args.get("limit", 20)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise BridgeError("INVALID_ARGUMENT", "Limit must be an integer between 1 and 100.")
        params["limit"] = limit
    if "thread" in args:
        thread = args["thread"]
        if not isinstance(thread, str) or not 1 <= len(thread) <= 256:
            raise BridgeError("INVALID_ARGUMENT", "Invalid thread identifier.")
        params["session_id"] = thread
    return params, timeout


def handle(message):
    ident = message.get("id")
    method = message.get("method")
    if ident is None:
        return None
    result = None
    error = None
    if method == "initialize":
        proposed = message.get("params", {}).get("protocolVersion")
        result = {
            "protocolVersion": proposed if proposed in PROTOCOLS else "2025-03-26",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "muse-bridge", "version": __version__},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {
            "tools": [
                {
                    "name": name,
                    "description": description,
                    "inputSchema": schema(name),
                    "annotations": {
                        "readOnlyHint": True,
                        "destructiveHint": False,
                        "idempotentHint": True,
                        "openWorldHint": True,
                    },
                }
                for name, (_, description) in TOOLS.items()
            ]
        }
    elif method == "tools/call":
        request = message.get("params", {})
        name = request.get("name")
        if name not in TOOLS:
            error = {"code": -32602, "message": "Unknown tool."}
        else:
            try:
                params, timeout = params_for(name, request.get("arguments", {}))
                data = run(TOOLS[name][0], params=params, timeout=timeout)
            except BridgeError as exception:
                data = failure(exception)
            result = {
                "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                "isError": not data["ok"],
            }
    else:
        error = {"code": -32601, "message": "Method not found."}
    response = {"jsonrpc": "2.0", "id": ident}
    response["error" if error else "result"] = error or result
    return response


def serve(source, destination):
    while True:
        line = source.readline(1024 * 1024 + 1)
        if not line:
            return
        try:
            if len(line) > 1024 * 1024:
                # Drain the rest without allocating the full request.
                while line and not line.endswith("\n"):
                    line = source.readline(1024 * 1024 + 1)
                raise ValueError()
            message = json.loads(line)
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                raise ValueError()
            response = handle(message)
        except (ValueError, TypeError, AttributeError):
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Invalid JSON-RPC request."},
            }
        except Exception:
            response = {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32603, "message": "Internal server error."},
            }
        if response:
            destination.write(json.dumps(response, ensure_ascii=False) + "\n")
            destination.flush()
