"""Fixed CLI adapters with process-group timeouts and a macOS write boundary."""

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from .errors import BridgeError

MAX_OUTPUT = 2 * 1024 * 1024


def project_path(value):
    if not isinstance(value, str) or not value.startswith("/"):
        raise BridgeError("INVALID_PROJECT", "Project must be an absolute directory path.")
    try:
        path = Path(value).resolve(strict=True)
    except OSError:
        raise BridgeError(
            "INVALID_PROJECT", "Project directory does not exist or is inaccessible."
        ) from None
    if not path.is_dir() or path in {Path("/"), Path.home(), Path.home() / "Documents"}:
        raise BridgeError("INVALID_PROJECT", "Select an individual project directory.")
    if any(
        path == p or p in path.parents
        for p in (
            Path.home() / ".codex",
            Path.home() / ".claude",
            Path.home() / ".ssh",
            Path.home() / ".aws",
            Path.home() / "Library",
        )
    ):
        raise BridgeError(
            "INVALID_PROJECT", "Credential and application-state directories are not projects."
        )
    markers = (".git", "pyproject.toml", "package.json", "Cargo.toml", "Package.swift", "go.mod")
    if not any((path / marker).exists() for marker in markers) and not any(
        path.glob("*.xcodeproj")
    ):
        raise BridgeError("INVALID_PROJECT", "Directory has no recognized project marker.")
    return path


def binary(agent):
    if agent not in {"codex", "claude"}:
        raise BridgeError("INVALID_AGENT", "Agent must be codex or claude.")
    found = shutil.which(agent)
    if not found and agent == "codex":
        candidate = Path(
            "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"
        )
        if candidate.is_file():
            found = str(candidate)
    if not found:
        raise BridgeError("AGENT_MISSING", f"{agent} CLI was not found.")
    return str(Path(found).resolve())


def environment(temp):
    # Authentication remains in each agent's own storage, not in relay payloads.
    allowed = ("HOME", "PATH", "USER", "LOGNAME", "LANG", "LC_ALL", "SHELL")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env["TMPDIR"] = str(temp)
    env["NO_COLOR"] = "1"
    return env


def seatbelt(project, temp, mode):
    if not Path("/usr/bin/sandbox-exec").is_file():
        raise BridgeError("SANDBOX_UNAVAILABLE", "This task runner requires macOS Seatbelt.")
    # Agent runtime state is writable; the rest of the disk is not. This is a WRITE
    # boundary, not a read isolation boundary. No claim is made that secrets cannot
    # be read by an agent with shell access.
    paths = [
        temp,
        Path.home() / ".claude",
        Path.home() / ".codex",
        Path.home() / ".cache",
    ]
    if mode == "write":
        paths.append(project)
    rules = ["(version 1)", "(allow default)", "(deny file-write*)"]
    rules += [
        f"(allow file-write* (subpath {json.dumps(str(p), ensure_ascii=False)}))" for p in paths
    ]
    rules += [
        f"(allow file-write* (literal {json.dumps(str(Path.home() / '.claude.json'))}))",
        '(allow file-write* (literal "/dev/null"))',
    ]
    metadata_pattern = re.escape(str(Path.home() / ".claude.json")) + r"(\..*)?$"
    rules.append(f"(allow file-write* (regex {json.dumps(metadata_pattern)}))")
    for name in ("config.toml", "auth.json", "skills", "rules", "hooks", "memories"):
        rules.append(
            f"(deny file-write* (subpath {json.dumps(str(Path.home() / '.codex' / name))}))"
        )
    # Keep task agents from replacing global Claude permission/hooks configuration.
    for name in (
        "settings.json",
        "settings.local.json",
        "commands",
        "skills",
        "agents",
        "plugins",
        "hooks",
    ):
        rules.append(
            f"(deny file-write* (subpath {json.dumps(str(Path.home() / '.claude' / name))}))"
        )
    return "\n".join(rules)


def command(agent, project, temp, mode):
    if mode not in {"read", "write"}:
        raise BridgeError("INVALID_MODE", "Mode must be read or write.")
    if agent == "codex":
        args = [
            binary(agent),
            "exec",
            "--ignore-user-config",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "danger-full-access",
            "-c",
            'approval_policy="never"',
            "-C",
            str(project),
            "--output-last-message",
            str(temp / "answer.txt"),
            "-",
        ]
    else:
        settings = {
            "disableAllHooks": True,
            "sandbox": {
                "enabled": True,
                "allowUnsandboxedCommands": False,
                "failIfUnavailable": True,
                "autoAllowBashIfSandboxed": True,
            },
        }
        tools = "Read,Grep,Glob,Bash" + (",Edit,Write" if mode == "write" else "")
        args = [
            binary(agent),
            "-p",
            "--output-format",
            "json",
            "--no-session-persistence",
            "--permission-mode",
            "acceptEdits" if mode == "write" else "dontAsk",
            "--tools",
            tools,
            "--allowedTools",
            tools,
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--mcp-config",
            '{"mcpServers":{}}',
            "--settings",
            json.dumps(settings),
        ]
    return ["/usr/bin/sandbox-exec", "-p", seatbelt(project, temp, mode), *args]


def scrub(text):
    text = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}", "[REDACTED_API_KEY]", text)
    return text[:20000]


def execute_task(task):
    project = project_path(task["project"])
    timeout = task.get("timeout", 300)
    mode = task.get("mode", "read")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="muse-task-") as directory:
        temp = Path(directory).resolve()
        prompt = (
            f"You are executing a user-authorized Muse Bridge task. Project: {project}. "
            f"Mode: {mode}. Operate only in that project; do not access credentials, private "
            "account data, or other projects. Do not publish, deploy, send messages, modify "
            "global settings, or disable boundaries. Do not delegate to other agents. "
            "Return a concise result stating what you did and what you verified.\n\n"
            + task["prompt"]
        )
        stdout_file = temp / "stdout"
        stderr_file = temp / "stderr"
        prompt_file = temp / "prompt.txt"
        prompt_file.write_text(prompt)
        os.chmod(prompt_file, 0o600)
        with (
            prompt_file.open("rb") as input_file,
            stdout_file.open("wb") as out,
            stderr_file.open("wb") as err,
        ):
            process = subprocess.Popen(
                command(task["agent"], project, temp, mode),
                cwd=project,
                env=environment(temp),
                stdin=input_file,
                stdout=out,
                stderr=err,
                start_new_session=True,
            )
            try:
                while process.poll() is None:
                    if time.monotonic() - started > timeout:
                        raise BridgeError("TASK_TIMEOUT", "Agent exceeded the task deadline.")
                    if stdout_file.stat().st_size + stderr_file.stat().st_size > MAX_OUTPUT:
                        raise BridgeError("OUTPUT_LIMIT", "Agent output exceeded the limit.")
                    time.sleep(0.2)
            except BaseException:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                raise
        if stdout_file.stat().st_size + stderr_file.stat().st_size > MAX_OUTPUT:
            raise BridgeError("OUTPUT_LIMIT", "Agent output exceeded the limit.")
        if process.returncode and task["agent"] == "claude":
            try:
                reported = json.loads(stdout_file.read_text())
                if reported.get("api_error_status") == 401:
                    raise BridgeError(
                        "AGENT_LOGIN_REQUIRED",
                        "Claude login has expired.",
                        "Run claude auth login in Terminal.",
                    )
            except (ValueError, TypeError):
                pass
        if process.returncode:
            # Local stderr is not forwarded: auth/config errors may contain private details.
            raise BridgeError(
                "AGENT_FAILED",
                f"{task['agent']} exited with code {process.returncode}.",
                "Check that agent's local login and configuration.",
            )
        if task["agent"] == "codex":
            answer = temp / "answer.txt"
            if not answer.is_file():
                raise BridgeError("AGENT_PROTOCOL", "Codex did not produce a final answer.")
            result = answer.read_text()
        else:
            try:
                response = json.loads(stdout_file.read_text())
                if response.get("is_error") is True:
                    raise BridgeError("AGENT_FAILED", "Claude reported a failed task.")
                result = response["result"]
            except (ValueError, TypeError, KeyError):
                raise BridgeError(
                    "AGENT_PROTOCOL", "Claude did not produce a final answer."
                ) from None
        if not isinstance(result, str) or not result.strip():
            raise BridgeError("AGENT_PROTOCOL", "Agent returned no answer.")
        return {
            "status": "completed",
            "agent": task["agent"],
            "mode": mode,
            "elapsed_seconds": round(time.monotonic() - started, 1),
            "answer": scrub(result),
        }
