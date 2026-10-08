# Provenance — 2026-10-08

## Independently authored implementation

All files under `src/musebridge` and `tests` were written for this project. No fork, vendored `muse_cli` module, descriptor `.bin`, or copied 258-method table is included. There is no dependency on `muse-cli` or `agent-browser`.

## Interoperability references

- Muse's public webpage and JavaScript assets were inspected at `https://muse.ai/` on 2026-10-08. Those assets are outside the deliverable and are not redistributed.
- https://github.com/nikships/muse-cli/blob/main/docs/PROTOCOL.md was consulted for authentication endpoints, standard Noise XX parameters, framing and documented failure modes.
- The reference client's protocol descriptors were decoded during research to learn factual field numbers, types and service identifiers. The source was also consulted to resolve the gateway-token `vmAddress` format. No descriptor data or implementation was copied into this package.
- Seven endpoint paths were recorded as interoperability facts; they are not a copy of the reference's route table.
- https://protobuf.dev/programming-guides/encoding/ describes the standard varint and length-delimited encoding used by the original codec.
- https://noiseprotocol.org/noise.html defines the handshake implemented by the third-party `noiseprotocol` package.
- https://modelcontextprotocol.io/specification/2025-03-26/basic/transports describes stdio JSON-RPC framing.

This is independently written code informed by public protocol research, **not** a clean-room implementation. Naming, architecture, source and tests are new. The project does not claim ownership of Muse's service, APIs, trademarks or the underlying standards.

## Third-party dependencies

Standard third-party libraries handle TLS/browser fingerprinting (`curl-cffi`), Noise and cryptography (`noiseprotocol`, `cryptography`), Keychain access (`keyring`), and dedicated browser login (`playwright`). Dependency licenses remain their own. The versions tested are recorded in `uv.lock`; the package declarations are in `pyproject.toml`.

## v0.1.1 protocol correction

On 2026-10-08 an authenticated live handshake returned an `AttestationBundle` for the `NON_TEE` platform, containing `ReportDataInput.x25519_public_key`. The key matched the public key authenticated by the Noise message-2 exchange. The vendor's public JavaScript assets, including `/_next/static/chunks/1yednwfd38pyt.js`, expose the names and wire fields of `attestation_bundle.proto`; these schema facts were checked to distinguish ordinary public-key binding from AMD SEV-SNP evidence and recovery-key challenges.

The new `trust.py` is independently written: it accepts only the known NON_TEE envelope, verifies key equality, and refuses additional evidence, confidential-platform labels, duplicate/unknown fields, and mismatches. No vendor JavaScript or descriptor bytes are included in the deliverable. Research printed only payload structure, types, lengths, and a boolean key comparison, never credential values or actual private conversation content.

## v0.2.0 task bridge

The relay, SQLite job store, executor adapters, CLI management and tests are independently authored. The bridge uses its already implemented Muse chat transport, standard Python process/SQLite APIs, macOS Seatbelt, and installed Codex/Claude CLIs. Runtime command flags were checked against local CLI help and official documentation: https://developers.openai.com/blog/codex-as-a-platform and https://code.claude.com/docs/en/headless. Claude shell-sandbox scope and its limits were checked at https://code.claude.com/docs/en/sandboxing. No third-party relay implementation was copied or embedded.
