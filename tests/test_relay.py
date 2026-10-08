import json

import pytest

from musebridge import relay
from musebridge.errors import BridgeError


@pytest.fixture
def store(tmp_path):
    s = relay.Store(tmp_path / "state")
    s.set("bridge_id", "bridge-test")
    s.set("cursor", 10)
    s.set("pending", [])
    s.set("scope", "all_project_directories")
    return s


@pytest.fixture
def task(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nname="example"\nversion="1"\n')
    return {
        "type": "muse_bridge_task",
        "bridge_id": "bridge-test",
        "task_id": "job_12345678",
        "agent": "codex",
        "project": str(project),
        "prompt": "Review the project",
        "mode": "read",
    }


def event(task, seq=11, role="assistant", ready=True):
    return {
        "seq": seq,
        "event_name": "message." + role,
        "display_text_ready": ready,
        "display_text": "```muse-bridge\n" + json.dumps(task) + "\n```",
    }


def test_user_messages_cannot_dispatch_tasks(task):
    assert relay.parse_event(event(task, role="user"), "bridge-test") is None


def test_unpaired_namespace_cannot_dispatch(task):
    assert relay.parse_event(event(task), "another-bridge") is None


def test_incomplete_message_is_not_dispatched(task):
    assert relay.parse_event(event(task, ready=False), "bridge-test") is None


@pytest.mark.parametrize(
    "change",
    [
        {"command": "sh -c anything"},
        {"agent": "shell"},
        {"timeout": True},
        {"timeout": 901},
        {"mode": "unrestricted"},
        {"task_id": "../../escape"},
        {"prompt": ""},
        {"project": "/"},
    ],
)
def test_invalid_envelopes_rejected(task, change):
    with pytest.raises(BridgeError):
        relay.validate_task({**task, **change}, "bridge-test")


def test_task_deduplication_is_durable(store, task):
    assert store.add(task, 11)
    assert not store.add(task, 12)
    reopened = relay.Store(store.directory)
    assert not reopened.add(task, 13)
    assert reopened.info()["jobs"] == {"queued": 1}


def test_old_history_is_not_replayed(store, task):
    relay.ingest(store, {"chat_events": [event(task, 9)], "has_more": True})
    assert store.queued() is None


def test_pending_message_is_revisited_after_cursor_advances(store, task):
    relay.ingest(
        store,
        {"chat_events": [event(task, 11, ready=False), {"seq": 12, "event_name": "message.user"}]},
    )
    assert store.queued() is None
    assert store.get("cursor") == 12
    relay.ingest(store, {"chat_events": [event(task, 11), {"seq": 12}]})
    assert store.queued()[0] == task["task_id"]


def test_history_gap_stops_instead_of_skipping_tasks(store, task):
    with pytest.raises(BridgeError) as error:
        relay.ingest(store, {"chat_events": [event(task, 200)], "has_more": True})
    assert error.value.code == "HISTORY_GAP"
    assert store.queued() is None


def test_lost_incomplete_message_is_a_gap(store, task):
    store.set("pending", [11])
    with pytest.raises(BridgeError):
        relay.ingest(store, {"chat_events": [event(task, 12)]})


def test_restarted_running_task_is_not_retried(store, task):
    store.add(task, 11)
    store.update(task["task_id"], "running")
    store.recover()
    assert store.info(task["task_id"])["status"] == "interrupted"
    assert store.queued() is None


def test_tick_runs_once_and_returns_result(store, task, monkeypatch):
    monkeypatch.setattr(relay, "history", lambda s: {"chat_events": [event(task)]})
    calls = []

    def runner(t):
        calls.append(t)
        return {"status": "completed", "answer": "done"}

    sent = []

    def sender(s):
        sent.extend(s.outbox())
        for ident, _, _ in s.outbox():
            s.db.execute("UPDATE jobs SET delivery='acknowledged' WHERE id=?", (ident,))
        s.db.commit()

    relay.tick(store, runner, sender)
    relay.tick(store, runner, sender)
    assert len(calls) == len(sent) == 1
    assert store.info(task["task_id"])["delivery"] == "acknowledged"


def test_result_send_ambiguity_is_not_auto_retried(store, task, monkeypatch):
    store.add(task, 11)
    store.update(task["task_id"], "completed", {"status": "completed", "answer": "done"})
    calls = []

    def fail(*a, **k):
        calls.append(1)
        raise BridgeError("DEADLINE_EXCEEDED", "timeout")

    monkeypatch.setattr(relay, "run", fail)
    relay.return_results(store)
    relay.return_results(store)
    assert calls == [1]
    assert store.info(task["task_id"])["delivery"] == "unknown"


def test_history_auth_failure_never_executes(store, monkeypatch):
    monkeypatch.setattr(
        relay,
        "run",
        lambda *a, **k: {"ok": False, "error": {"code": "LOGIN_REQUIRED", "message": "Login"}},
    )
    with pytest.raises(BridgeError):
        relay.tick(store, lambda task: pytest.fail("must not execute"))


def test_invalid_paired_task_gets_failure_without_running(store, task):
    task["project"] = "/not-a-real-project"
    relay.ingest(store, {"chat_events": [event(task)]})
    assert store.queued() is None
    result = store.info(task["task_id"])
    assert result["status"] == "failed"
    assert result["result"]["error_code"] == "INVALID_PROJECT"
    assert len(store.outbox()) == 1


def test_selected_project_policy_rejects_other_projects(store, task):
    store.set("scope", "selected_projects")
    store.set("projects", [])
    relay.ingest(store, {"chat_events": [event(task)]})
    assert store.queued() is None
    assert store.info(task["task_id"])["result"]["error_code"] == "PROJECT_NOT_AUTHORIZED"


def test_write_requires_separate_local_opt_in(store, task):
    store.set("scope", "selected_projects")
    store.set("projects", [task["project"]])
    task["mode"] = "write"
    relay.ingest(store, {"chat_events": [event(task)]})
    assert store.queued() is None
    assert store.info(task["task_id"])["result"]["error_code"] == "WRITE_DISABLED"


def test_policy_is_rechecked_before_queued_execution(store, task, monkeypatch):
    valid = relay.validate_task(task, "bridge-test")
    store.add(valid, 11)
    store.set("scope", "selected_projects")
    store.set("projects", [])
    monkeypatch.setattr(relay, "history", lambda s: {"chat_events": []})
    relay.tick(store, lambda t: pytest.fail("revoked task must not execute"), lambda s: None)
    assert store.info(task["task_id"])["status"] == "failed"


def test_legacy_explicit_all_project_policy_is_preserved(store, task):
    task["mode"] = "write"
    assert relay.authorize(store, task) == task
