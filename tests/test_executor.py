import subprocess
from pathlib import Path

import pytest

from musebridge import executor
from musebridge.errors import BridgeError


def test_environment_does_not_inherit_arbitrary_tokens(monkeypatch, tmp_path):
    monkeypatch.setenv("PRIVATE_API_KEY", "do-not-forward")
    assert "PRIVATE_API_KEY" not in executor.environment(tmp_path)


@pytest.mark.skipif(not Path("/usr/bin/sandbox-exec").exists(), reason="macOS-only executor")
def test_agent_command_has_no_shell_interpolation(tmp_path, monkeypatch):
    monkeypatch.setattr(executor, "binary", lambda name: "/usr/bin/" + name)
    for agent in ("codex", "claude"):
        args = executor.command(agent, tmp_path, tmp_path / "temp", "read")
        assert "--dangerously-bypass-approvals-and-sandbox" not in args
        assert "--dangerously-skip-permissions" not in args
        assert args[:2] == ["/usr/bin/sandbox-exec", "-p"]


@pytest.mark.parametrize("mode", ["read", "write"])
def test_seatbelt_enforces_write_boundary(tmp_path, mode):
    if not Path("/usr/bin/sandbox-exec").exists():
        pytest.skip("macOS only")
    project = tmp_path / "project"
    project.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    project = project.resolve()
    runtime = runtime.resolve()
    outside = (tmp_path / "outside").resolve()
    profile = executor.seatbelt(project, runtime, mode)
    denied = subprocess.run(
        ["/usr/bin/sandbox-exec", "-p", profile, "/usr/bin/touch", str(outside)],
        capture_output=True,
    )
    assert denied.returncode != 0 and not outside.exists()
    inside = project / "allowed"
    wrote = subprocess.run(
        ["/usr/bin/sandbox-exec", "-p", profile, "/usr/bin/touch", str(inside)], capture_output=True
    )
    assert (wrote.returncode == 0) == (mode == "write")


def test_project_requires_marker(tmp_path):
    with pytest.raises(BridgeError):
        executor.project_path(str(tmp_path))


def test_scrub_known_secret_formats():
    assert "secret" not in executor.scrub("Bearer secret")
    assert "sk-123456789012345" not in executor.scrub("sk-123456789012345")


def test_blocked_executor_process_is_terminated(monkeypatch, tmp_path):
    import sys
    import time

    (tmp_path / "pyproject.toml").write_text('[project]\nname="fixture"\nversion="1"\n')
    monkeypatch.setattr(
        executor, "command", lambda *a: [sys.executable, "-c", "import time;time.sleep(60)"]
    )
    start = time.monotonic()
    with pytest.raises(BridgeError) as error:
        executor.execute_task(
            {"agent": "codex", "project": str(tmp_path), "prompt": "test", "timeout": 0.25}
        )
    assert error.value.code == "TASK_TIMEOUT"
    assert time.monotonic() - start < 3


@pytest.mark.skipif(not Path("/usr/bin/sandbox-exec").exists(), reason="macOS-only executor")
def test_symlink_cannot_escape_project_write_boundary(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    outside = tmp_path / "outside"
    for p in (project, runtime, outside):
        p.mkdir()
    (project / "link").symlink_to(outside, target_is_directory=True)
    profile = executor.seatbelt(project.resolve(), runtime.resolve(), "write")
    result = subprocess.run(
        ["/usr/bin/sandbox-exec", "-p", profile, "/usr/bin/touch", str(project / "link" / "probe")],
        capture_output=True,
    )
    assert result.returncode != 0
    assert not (outside / "probe").exists()


@pytest.mark.skipif(not Path("/usr/bin/sandbox-exec").exists(), reason="macOS-only executor")
def test_non_ascii_project_path_is_writable_when_authorized(tmp_path):
    project = tmp_path / "项目"
    runtime = tmp_path / "runtime"
    project.mkdir()
    runtime.mkdir()
    profile = executor.seatbelt(project.resolve(), runtime.resolve(), "write")
    result = subprocess.run(
        ["/usr/bin/sandbox-exec", "-p", profile, "/usr/bin/touch", str(project / "probe")],
        capture_output=True,
    )
    assert result.returncode == 0
    assert (project / "probe").exists()
