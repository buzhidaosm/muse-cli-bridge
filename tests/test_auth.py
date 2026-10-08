import pytest

from musebridge import auth, login
from musebridge.errors import BridgeError


def jar(value="test-only", domain=".muse.ai"):
    return [{"name": "hatch_sess", "value": value, "domain": domain, "path": "/"}]


def test_only_exact_muse_domain_is_forwarded():
    cookies = jar() + [{"name": "private", "value": "no", "domain": "example.com"}]
    cookies += [{"name": "auth", "value": "no", "domain": "auth.muse.ai"}]
    assert auth.cookie_header(cookies) == "hatch_sess=test-only"


@pytest.mark.parametrize("value", ["x\r\nInjected: yes", "x;y", "x\x00y"])
def test_header_injection_rejected(value):
    with pytest.raises(BridgeError):
        auth.cookie_header(jar(value))


def test_lookalike_domain_rejected():
    with pytest.raises(BridgeError):
        auth.cookie_header(jar(domain="muse.ai.attacker.test"))


def test_conflicting_cookies_rejected():
    with pytest.raises(BridgeError):
        auth.cookie_header(jar("a") + jar("b"))


def test_invalid_login_does_not_overwrite_keychain(monkeypatch):
    saved = []
    monkeypatch.setattr(auth, "save", lambda cookies: saved.append(cookies))

    class FailedHTTP:
        def __init__(self, *args):
            pass

        def access_token(self):
            raise BridgeError("LOGIN_REQUIRED", "Rejected")

        def close(self):
            pass

    monkeypatch.setattr(login, "MuseHTTP", FailedHTTP)
    with pytest.raises(BridgeError):
        login.validate_and_save(jar())
    assert saved == []


def test_keychain_failures_do_not_leak_exception(monkeypatch):
    class FailedKeychain:
        def get_password(self, *args):
            raise RuntimeError("SECRET")

    monkeypatch.setattr(auth, "backend", lambda: FailedKeychain())
    with pytest.raises(BridgeError) as caught:
        auth.read()
    assert "SECRET" not in str(caught.value)
