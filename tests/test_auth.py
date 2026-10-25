"""Feature 1: secure authentication."""
import logging

import pytest

from app import GENERIC_LOGIN_ERROR, create_app
from helpers import STRONG_PASSWORD, csrf_from, login, logout, register


def test_register_creates_user_with_hashed_password(client, query):
    resp = register(client, "New.User@Example.com")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/dashboard")
    rows = query("SELECT email, password_hash FROM users")
    assert rows[0]["email"] == "new.user@example.com"
    assert rows[0]["password_hash"] != STRONG_PASSWORD
    assert rows[0]["password_hash"].startswith(("scrypt:", "pbkdf2:"))


@pytest.mark.parametrize("password,message", [
    ("short1", "8–128 characters"),
    ("lettersonly", "letter and one number"),
    ("12345678", "letter and one number"),
])
def test_register_rejects_weak_passwords(client, password, message):
    resp = register(client, "weak@example.com", password)
    assert resp.status_code == 400
    assert message in resp.get_data(as_text=True)


def test_register_rejects_bad_email_and_mismatch(client):
    resp = register(client, "not-an-email", STRONG_PASSWORD, confirm="Different1")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 400
    assert "valid email" in body and "do not match" in body


def test_duplicate_registration_is_rejected(client, alice):
    resp = register(client, "ALICE@example.com")
    assert resp.status_code == 400
    assert "Registration failed" in resp.get_data(as_text=True)


def test_login_success_and_logout(client, alice):
    resp = login(client, "alice@example.com")
    assert resp.status_code == 302
    assert client.get("/dashboard").status_code == 200
    resp = logout(client)
    assert resp.status_code == 302
    assert client.get("/dashboard").status_code == 302  # back to login


def test_login_error_is_generic(client, alice):
    wrong_pw = login(client, "alice@example.com", "WrongPass1")
    no_user = login(client, "nobody@example.com", "WrongPass1")
    assert wrong_pw.status_code == no_user.status_code == 401
    for resp in (wrong_pw, no_user):
        body = resp.get_data(as_text=True)
        assert GENERIC_LOGIN_ERROR in body
        assert "not found" not in body.lower() and "incorrect password" not in body.lower()


def test_failed_login_is_logged(client, alice, caplog):
    with caplog.at_level(logging.WARNING, logger="finpulse.security"):
        login(client, "alice@example.com", "WrongPass1")
    assert any("Failed login attempt" in r.getMessage() and "alice@example.com" in r.getMessage()
               for r in caplog.records)


def test_failed_login_log_cannot_be_injected(client, caplog):
    with caplog.at_level(logging.WARNING, logger="finpulse.security"):
        login(client, "evil@example.com\nINFO Successful login user_id=1", "x")
    messages = [r.getMessage() for r in caplog.records if "Failed login" in r.getMessage()]
    assert messages and "\n" not in messages[0]


def test_protected_pages_require_login(client):
    for path in ("/dashboard", "/transactions", "/goals", "/health", "/insights", "/time-machine"):
        resp = client.get(path)
        assert resp.status_code == 302 and "/login" in resp.headers["Location"], path


def test_logout_requires_post(alice):
    assert alice.get("/logout").status_code == 405


def test_session_is_regenerated_on_login(client, alice):
    csrf_from(client, "/login")
    login(client, "alice@example.com")
    with client.session_transaction() as sess:
        assert sess.get("user_id") is not None


def test_secret_key_comes_from_environment(monkeypatch, tmp_path):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setattr("app.load_dotenv", None)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app({"DATABASE": str(tmp_path / "x.db")})
    monkeypatch.setenv("SECRET_KEY", "from-env-123")
    app = create_app({"DATABASE": str(tmp_path / "y.db"), "TESTING": True})
    assert app.config["SECRET_KEY"] == "from-env-123"
