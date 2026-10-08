# Security and privacy boundaries

Muse Bridge is a local task executor. Review these boundaries before enabling its relay.

## Authorization

New relay initialization requires selected project paths or an explicit `--all-projects` choice. Write-mode jobs additionally require `--allow-write`. Policy is checked at ingestion and again before execution. A bridge id is only a namespace; knowledge of that id is not itself cryptographic proof of user intent. The trusted/delegated party is the authenticated Muse assistant in the selected chat.

A strict envelope avoids accidentally treating ordinary chat as a command. It does not solve prompt injection in Muse or in coding agents. Only ask Muse to delegate work you intend, inspect returned results, and don't use this bridge for sensitive or privileged workflows.

## OS write boundary

The entire local agent process is launched inside macOS Seatbelt. Read mode denies writing the project; write mode permits writing the resolved selected project. The agent's own runtime directories, a temporary directory and selected caches are additionally writable. Global agent configuration, rules, skills and hooks are write-protected.

This boundary is **not complete read or network isolation**. Agents can read other files allowed by the OS and can access the network. The prompt's instructions to avoid credentials, publishing, other projects and messages are behavioral constraints, not OS-enforced guarantees. Do not expose data you do not want sent to model providers.

Codex is run with `--sandbox danger-full-access` only inside this externally enforced Seatbelt boundary to avoid macOS nested-sandbox failures. The wrapper refuses to run without Seatbelt; the actual write boundary is tested independently. No `--dangerously-bypass-approvals-and-sandbox` flag is used. Claude's full process has the same outer boundary; its Bash sandbox is also enabled and cannot request unsandboxed fallback.

## Credentials and output

A dedicated ephemeral Chrome context is used for manual Muse login; existing browser profiles are not read. Only root-path muse.ai cookies are accepted, validated against Muse, then saved to macOS Keychain. No plaintext cookie fallback is created by the application. Logout removes the local record but does not revoke the server session.

Do not paste passwords, cookies, authorization headers, HAR captures or unredacted conversations into issues. Local relay jobs contain task prompts and results; they are private files, not encrypted databases. Final answers are sent back to Muse. Common Bearer/API-key formats are redacted, but that is not a comprehensive secret detector.

Authentication tokens in transport URLs and raw failure bodies are not logged or echoed by normal error handling. Codex and Claude use their own login storage. Their runtime state and logs have their own provider/privacy behavior.

## Transport and reliability

TLS certificate verification is enabled. Standard NON_TEE bundles are checked against the Noise peer key; unknown, confidential, mismatched and malformed handshake formats are rejected. Hardware attestation is not implemented.

Tasks and result sends are not automatically retried. A killed worker may already have performed changes or posted a message. `unknown` delivery and `interrupted` execution are retained so users can reconcile state.

## Reporting

For non-sensitive compatibility bugs, open a GitHub issue with redacted steps. For a security issue, use the repository's private vulnerability reporting feature if enabled. If it is unavailable, open a minimal issue asking for a private reporting channel; do not disclose exploitable details or secrets publicly.
