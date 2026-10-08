import os
import subprocess
import sys
import time

from . import relay
from .client import run
from .errors import BridgeError
from .executor import execute_task


def execute(args):
    op = args.bridge_op
    if op == "init":
        return relay.initialize(args.thread, args.project, args.all_projects, args.allow_write)
    if op == "run":
        return execute_task(
            {
                "agent": args.agent,
                "project": args.project,
                "mode": args.mode,
                "timeout": args.timeout,
                "prompt": args.prompt,
            }
        )
    store = relay.Store()
    if op == "status":
        return store.info()
    if op == "job":
        return store.info(args.task_id)
    if op == "instructions":
        if not store.get("bridge_id"):
            raise BridgeError("BRIDGE_NOT_INITIALIZED", "Run bridge init first.")
        return {"text": relay.onboarding(store)}
    if op == "notify":
        if not store.get("bridge_id"):
            raise BridgeError("BRIDGE_NOT_INITIALIZED", "Run bridge init first.")
        params = {"items": [{"type": "text", "text": relay.onboarding(store)}]}
        if store.get("thread"):
            params["session_id"] = store.get("thread")
        return run("send", params, timeout=30, allow_write=True)
    if op == "stop":
        return relay.stop()
    if op == "start":
        if not args.background:
            relay.daemon(args.interval, args.once)
            return {"finished": True}
        if not store.get("bridge_id"):
            raise BridgeError("BRIDGE_NOT_INITIALIZED", "Run bridge init first.")
        log = store.directory / "daemon.log"
        descriptor = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            command = [
                sys.executable,
                "-m",
                "musebridge.cli",
                "bridge",
                "start",
                "--interval",
                str(args.interval),
            ]
            if args.once:
                command.append("--once")
            child = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=descriptor,
                stderr=descriptor,
                start_new_session=True,
            )
        finally:
            os.close(descriptor)
        # Startup is concrete: wait for the child to acquire its lock and publish state.
        for _ in range(50):
            if child.poll() is not None:
                raise BridgeError("BRIDGE_START_FAILED", "Daemon exited during startup.")
            if store.get("pid") == child.pid and store.get("enabled"):
                return {"started": True, "pid": child.pid, "bridge_id": store.get("bridge_id")}
            time.sleep(0.1)
        raise BridgeError("BRIDGE_START_FAILED", "Daemon did not confirm startup.")
    raise BridgeError("INVALID_COMMAND", "Unknown bridge operation.")
