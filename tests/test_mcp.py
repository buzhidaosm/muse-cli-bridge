import io
import json

from musebridge import mcp


def test_tools_do_not_include_write_or_auth():
    listing = mcp.handle({"id": 1, "method": "tools/list"})["result"]["tools"]
    assert len(listing) == 7
    assert all(t["annotations"]["readOnlyHint"] for t in listing)
    assert not any(x in t["name"] for t in listing for x in ("send", "login", "delete", "raw"))


def test_mcp_rejects_unknown_write_arguments(monkeypatch):
    called = []
    monkeypatch.setattr(mcp, "run", lambda *a, **k: called.append(1))
    output = mcp.handle(
        {
            "id": 2,
            "method": "tools/call",
            "params": {"name": "muse_history", "arguments": {"allow_write": True}},
        }
    )
    assert output["result"]["isError"] is True
    assert not called


def test_mcp_passes_valid_history_parameters(monkeypatch):
    captured = []

    def run(action, **kw):
        captured.append((action, kw))
        return {"ok": True, "data": []}

    monkeypatch.setattr(mcp, "run", run)
    output = mcp.handle(
        {
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "muse_history",
                "arguments": {"limit": 5, "thread": "abc", "timeout": 2},
            },
        }
    )
    assert not output["result"]["isError"]
    assert captured == [("history", {"params": {"limit": 5, "session_id": "abc"}, "timeout": 2})]


def test_parse_error_does_not_kill_stdio_server():
    source = io.StringIO('not json\n{"jsonrpc":"2.0","id":1,"method":"ping"}\n')
    target = io.StringIO()
    mcp.serve(source, target)
    lines = [json.loads(x) for x in target.getvalue().splitlines()]
    assert lines[0]["error"]["code"] == -32700
    assert lines[1]["result"] == {}


def test_notifications_do_not_generate_responses():
    assert mcp.handle({"method": "notifications/initialized"}) is None


def test_negotiates_protocol_version():
    response = mcp.handle(
        {"id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}
    )
    assert response["result"]["protocolVersion"] == "2025-06-18"
