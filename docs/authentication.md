# Muse CLI authentication

`muse-bridge login` opens a separate temporary Chrome window. Sign in manually. A detected Muse session is validated before it replaces the saved Keychain record. The window then closes.

If the website refuses the automated browser, a manually exported Playwright-style cookie list can be imported through stdin:

```bash
muse-bridge login --stdin < /path/to/private/cookies.json
```

A `{ "cookies": [...] }` object is also accepted. The tool does not create or delete the manually exported file. Keep it private and remove it yourself when no longer needed; never put cookies in command-line arguments, a repository or a bug report.

Only root-path `muse.ai` / `.muse.ai` cookies are forwarded, and `hatch_sess` is required. Failed validation does not overwrite a working saved session.

`status` validates HTTPS authentication and VM assignment, but returns `gateway_verified: false`. `identity` or another read query establishes the gateway. A successful login-status flag from Codex or Claude likewise does not prove its next inference call will succeed; expired OAuth can still yield 401.
