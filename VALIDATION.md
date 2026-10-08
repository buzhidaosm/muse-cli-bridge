# Validation record

Source date: **2026-10-08**. Live host: macOS arm64; Python 3.12.11. Public release: **0.3.0**.

## What was actually observed

- Muse browser login completed and validated credentials were stored in Keychain.
- Authenticated identity, threads, history, goals, ideas and feed queries succeeded.
- An official Python MCP client initialized the stdio service and listed seven read-only tools.
- Both installed local executors completed real read-only prompt tests.
- Codex and Claude Code each edited a file in a separate disposable test project; a separate host read verified the exact expected content.
- The Muse assistant emitted one test task per agent. The relay executed them and returned the expected answer. Matching structured results were independently found in actual Muse history; a transport acknowledgment alone was not used as completion evidence.
- Common startup failures were reproduced and fixed: a normal NON_TEE key-binding payload is not a confidential challenge; a logged-in Claude status can coexist with an invalid OAuth token; nested macOS sandboxes can block Codex tool calls.

[Sanitized evidence](examples/verified-roundtrips.json) contains only test tokens and success facts. No account names, cookie values, private chat contents or local machine paths are redistributed.

The live roundtrips were first exercised during private 0.2 development. Release 0.3 adds explicit new-installation project/write authorization. Those gates are covered by tests; live validation is specific to the tested account, OS and installed CLIs.

## Automated checks

The suite covers protobuf golden vectors, malformed/truncated frames, bounded reassembly, duplicate chunks, complete-response requirements, simulated Noise interoperability, cookie-domain and injection restrictions, no overwrite after failed login, secret-bearing error suppression, command write gating, network deadlines, ambiguous send handling, MCP validation, relay policy/deduplication/recovery, incomplete text, history gaps and real process termination.

macOS tests separately verify that the OS rejects project writes in read mode, rejects outside writes in write mode, prevents a symlink escape, and permits a non-ASCII project path when authorized. Non-macOS hosts skip platform-specific probes; their passing tests do not imply a portable task executor.

```bash
uv sync --no-editable --group dev
uv run --no-editable pytest -q
uv run --no-editable ruff check src tests
uv build
```

Use the CI run and commit associated with a release to inspect its exact automated test result. Live authenticated validation is not run by CI.

## Not established

- Universal compatibility with every Muse account or future internal API version.
- Confidential/attested VM support, Linux/Windows execution, desktop clicking, or injection into an existing desktop conversation.
- Complete read/network isolation or comprehensive secret detection.
- Successful completion of arbitrary tasks merely because an agent process returned text.
- Automatic startup after shutdown/logout, or operation while the Mac is asleep.

## Reproduce a live check deliberately

Use a disposable, recognized project. Sign in to Muse and your selected agent, initialize scope, start the relay and send onboarding. Ask Muse to issue a simple read task with a unique id. Confirm the local job's result and independently find the matching structured result in Muse history. For write testing, opt in locally and independently inspect the actual changed fixture file. Do not publish raw credentials, identity output or private conversations.
