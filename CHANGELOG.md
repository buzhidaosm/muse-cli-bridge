# Changelog

## 0.3.0 — first public release

- Explicit local project authorization for new relay setups.
- Separate write-mode opt-in, checked again before execution.
- Independently implemented Muse CLI, Keychain login and seven read-only MCP tools.
- Bidirectional Muse-chat task relay for Codex and Claude Code on macOS.
- Durable task ids, interrupted-job recovery, process-group deadlines and ambiguous send handling.
- Known NON_TEE key-binding payload support; confidential/unknown payloads remain refused.
- English/Chinese quick starts, boundary documentation and reproducible validation material.

## Private development history

0.2.0 introduced the relay and verified both live agent roundtrips and disposable project edits. 0.1.1 fixed a mistaken rejection of every nonempty handshake payload. 0.1.0 established the independent client and local tests. These internal iterations were not public releases.
