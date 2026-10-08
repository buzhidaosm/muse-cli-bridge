import argparse
import json
import sys

from . import __version__, auth
from .client import doctor, fingerprint, run
from .errors import BridgeError, failure, success

EXIT_CODES = {"LOGIN_REQUIRED": 2, "WRITE_DISABLED": 3, "DEADLINE_EXCEEDED": 4}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise BridgeError("INVALID_ARGUMENT", message)


def bounded(low, high):
    def parse(value):
        try:
            number = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError("expected an integer") from None
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"expected a value between {low} and {high}")
        return number

    return parse


def parser():
    root = Parser(description="Independent Muse client; JSON output and macOS Keychain login.")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    login = commands.add_parser("login", help="Open a separate Chrome window for manual login")
    login.add_argument("--stdin", action="store_true", help="Import cookie JSON from stdin")
    login.add_argument("--timeout", type=bounded(30, 600), default=300)
    commands.add_parser(
        "logout", help="Remove the local Keychain session (does not revoke server login)"
    )
    commands.add_parser("doctor", help="Check local prerequisites; never connects to Muse")
    commands.add_parser("mcp", help="Serve read-only MCP tools over stdio")
    bridge = commands.add_parser("bridge", help="Muse-to-local-agent task relay")
    operations = bridge.add_subparsers(dest="bridge_op", required=True)
    init = operations.add_parser("init")
    init.add_argument("--thread")
    scope = init.add_mutually_exclusive_group(required=True)
    scope.add_argument("--project", action="append", help="Authorize one project; repeat for more")
    scope.add_argument(
        "--all-projects", action="store_true", help="Explicitly authorize any project"
    )
    init.add_argument("--allow-write", action="store_true", help="Permit write-mode tasks")
    operations.add_parser("status")
    operations.add_parser("instructions")
    operations.add_parser("stop")
    job = operations.add_parser("job")
    job.add_argument("task_id")
    operations.add_parser("notify", help="Send bridge onboarding instructions to Muse")
    start = operations.add_parser("start")
    start.add_argument("--background", action="store_true")
    start.add_argument("--once", action="store_true")
    start.add_argument("--interval", type=bounded(3, 60), default=5)
    direct = operations.add_parser("run", help="Run a local task without sending it to Muse")
    direct.add_argument("--agent", choices=["codex", "claude"], required=True)
    direct.add_argument("--project", required=True)
    direct.add_argument("--mode", choices=["read", "write"], default="read")
    direct.add_argument("--timeout", type=bounded(10, 900), default=300)
    direct.add_argument("prompt")
    for name in ("status", "identity", "threads", "history", "goals", "ideas", "feed", "send"):
        command = commands.add_parser(name)
        command.add_argument("--timeout", type=bounded(1, 300), default=30)
        if name in {"history", "feed"}:
            command.add_argument("--limit", type=bounded(1, 100), default=20)
        if name in {"history", "send"}:
            command.add_argument("--thread")
        if name == "send":
            command.add_argument(
                "text", help="Message text (use --stdin to keep it out of shell history)", nargs="?"
            )
            command.add_argument("--stdin", action="store_true")
            command.add_argument("--allow-write", action="store_true")
    return root


def execute(args):
    if args.command == "bridge":
        from .bridge_cli import execute

        return success(execute(args))
    if args.command == "doctor":
        result = doctor()
        result["protocol_fingerprint"] = fingerprint()
        return success(result)
    if args.command == "login":
        from .login import browser_login, import_session

        if args.stdin:
            return success(import_session(sys.stdin))
        print(
            "Complete login in the separate Chrome window. Your existing browser is untouched.",
            file=sys.stderr,
        )
        return success(browser_login(args.timeout))
    if args.command == "logout":
        return success(auth.remove())
    params = {}
    if hasattr(args, "limit"):
        params["limit"] = args.limit
    if getattr(args, "thread", None):
        if len(args.thread) > 256:
            raise BridgeError("INVALID_ARGUMENT", "Thread identifier is too long.")
        params["session_id"] = args.thread
    if args.command == "send":
        if not args.allow_write:
            raise BridgeError("WRITE_DISABLED", "Sending requires --allow-write.")
        if args.stdin and args.text is not None:
            raise BridgeError("INVALID_ARGUMENT", "Use either text or --stdin, not both.")
        text = sys.stdin.read(65537) if args.stdin else args.text
        if not text or not text.strip() or len(text.encode()) > 65536:
            raise BridgeError("INVALID_ARGUMENT", "Message must contain 1–65536 UTF-8 bytes.")
        params["items"] = [{"type": "text", "text": text}]
    return run(
        args.command, params, timeout=args.timeout, allow_write=getattr(args, "allow_write", False)
    )


def main():
    try:
        args = parser().parse_args()
        if args.command == "mcp":
            from .mcp import serve

            serve(sys.stdin, sys.stdout)
            return 0
        result = execute(args)
    except BridgeError as error:
        result = failure(error)
    except KeyboardInterrupt:
        result = failure(
            BridgeError(
                "CANCELLED",
                "Operation cancelled.",
                delivery="unknown" if "send" in sys.argv[1:2] else None,
            )
        )
    except Exception:
        result = failure(
            BridgeError(
                "INTERNAL_ERROR",
                "Operation could not complete.",
                "Run muse-bridge doctor to check local prerequisites.",
            )
        )
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result["ok"] else EXIT_CODES.get(result["error"]["code"], 1)


if __name__ == "__main__":
    sys.exit(main())
