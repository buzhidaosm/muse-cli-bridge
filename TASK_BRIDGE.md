# Bidirectional Muse task bridge

## Start from a known project

Sign in to Muse, and sign in separately to the local Codex or Claude Code CLI. Authorize the project locally:

```bash
muse-bridge bridge init --project /absolute/path/to/project
muse-bridge bridge start --background
muse-bridge bridge notify
```

The last command sends onboarding to the selected Muse chat. Ask for a concrete task in that same chat. The relay consumes one complete `muse-bridge` fenced JSON object emitted by a Muse assistant message. It ignores user messages, historical requests, other bridge namespaces and incomplete message text.

## Local authorization

The selected project must have `.git`, `pyproject.toml`, `package.json`, `Cargo.toml`, `Package.swift`, `go.mod` or an `.xcodeproj` directory. Each task uses one resolved absolute project path. Root, HOME, all of Documents and credential/application-state directories are rejected.

- `--project PATH`: authorize exactly that project; repeat for others.
- No `--allow-write`: only read-mode tasks can execute.
- `--allow-write`: allow explicit write-mode tasks in authorized projects.
- `--all-projects`: explicitly authorize any recognized project. Combine with `--allow-write` only if you intend broad edit access.

Stop before reconfiguring. `bridge init` requires an explicit scope and starts at the current history position. `--thread SESSION_ID` selects a side chat. It does not automatically notify Muse of a policy change; run `bridge notify` afterwards.

Legacy private v0.2 configurations with `scope=all_project_directories` retain their previously broad policy. To narrow one, stop it and reinitialize with `--project`. New installations require explicit authorization.

## Protocol

The bridge id is a namespace, not a cryptographic authorization token. Local project/write policy is the actual execution gate.

```muse-bridge
{
  "type": "muse_bridge_task",
  "bridge_id": "YOUR_INITIALIZED_BRIDGE_ID",
  "task_id": "unique-task-001",
  "agent": "codex",
  "project": "/absolute/path/to/project",
  "mode": "read",
  "timeout": 300,
  "prompt": "Review the README and report unclear installation steps."
}
```

Use `agent: "claude"` for Claude Code. Default mode is read; default timeout is 300 seconds (allowed range 10–900). Unknown fields, arbitrary command fields and malformed paired requests are rejected. A valid paired task id receives a structured failure when project or write policy rejects it.

The local result is posted as JSON with `type: "muse_bridge_result"`, the matching task id, execution status and bounded final answer. An emitted request does not prove execution. `completed` means the agent process returned a final answer; users should inspect the answer's task/validation evidence.

## Management

```bash
muse-bridge bridge status
muse-bridge bridge job TASK_ID
muse-bridge bridge stop
muse-bridge bridge start --background
muse-bridge bridge instructions
```

Background mode survives closing the terminal, not shutdown/logout or a sleeping/offline Mac. No automatic login item is installed. `bridge run` invokes a local agent without sending a result to Muse:

```bash
muse-bridge bridge run --agent codex --project /project/path --mode read 'Review README'
muse-bridge bridge run --agent claude --project /project/path --mode write 'Make a concrete edit and verify it'
```

## Reliability

A SQLite primary key provides durable task deduplication. Running tasks recovered after a restart become `interrupted`, not automatically queued again. An execution deadline kills the entire process group. Standard output/error are bounded; only the final answer is forwarded.

Result dispatch is recorded before sending. Crash, timeout or unknown send status does not trigger an automatic second send. Inspect `bridge job` before manually resending a result. Sends acknowledged by the gateway are still independently distinguishable from assistant completion.

Incomplete assistant text is revisited after completion. If pending text falls outside the 100-event query window, or a history gap is detected, the daemon stops with `HISTORY_GAP`. Login expiry also stops it. Temporary read errors can be retried; task execution and result dispatch are not retried automatically.

Jobs contain prompts/results under `~/Library/Application Support/Muse Bridge/relay`; directory permissions are 700 and the database is 600. Muse session cookies remain in Keychain. See [SECURITY.md](SECURITY.md) for what the write boundary does and does not protect.
