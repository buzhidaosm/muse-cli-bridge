"""Manual login in an ephemeral, dedicated Chrome window; no existing profile access."""

import json
import time
from pathlib import Path

from . import auth
from .errors import BridgeError
from .gateway import MuseHTTP


def validate_and_save(cookies):
    cleaned = auth.normalize_cookies(cookies)
    http = MuseHTTP(cleaned, 15)
    try:
        http.access_token()
    finally:
        http.close()
    auth.save(cleaned)
    return {"authenticated": True, "storage": "macOS Keychain", "gateway_verified": False}


def import_session(stream):
    raw = stream.read(256 * 1024 + 1)
    if len(raw) > 256 * 1024:
        raise BridgeError("INVALID_CREDENTIAL", "Cookie input is too large.")
    try:
        data = json.loads(raw)
    except ValueError:
        raise BridgeError(
            "INVALID_CREDENTIAL", "Expected a JSON browser cookie list on stdin."
        ) from None
    cookies = data.get("cookies") if isinstance(data, dict) else data
    return validate_and_save(cookies)


def browser_login(timeout=300):
    chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not chrome.is_file():
        raise BridgeError(
            "BROWSER_MISSING",
            "Google Chrome was not found in Applications.",
            "Install Chrome or use muse-bridge login --stdin.",
        )
    # Require the secure credential backend before opening a login window.
    auth.backend()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False, executable_path=str(chrome))
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://muse.ai/", wait_until="domcontentloaded", timeout=30_000)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if page.is_closed():
                    raise BridgeError("LOGIN_CANCELLED", "The login window was closed.")
                cookies = context.cookies("https://muse.ai/")
                if any(c.get("name") == "hatch_sess" and c.get("value") for c in cookies):
                    try:
                        return validate_and_save(cookies)
                    except BridgeError as error:
                        if error.code != "LOGIN_REQUIRED":
                            raise
                page.wait_for_timeout(1000)
            raise BridgeError("LOGIN_TIMEOUT", "Login was not completed within the time limit.")
        finally:
            browser.close()
