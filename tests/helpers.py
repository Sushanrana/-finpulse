"""Shared test helpers: CSRF-aware form posting (CSRF stays ENABLED in tests)."""
from __future__ import annotations

import re

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
STRONG_PASSWORD = "Str0ngPass!"


def csrf_from(client, url: str = "/login") -> str:
    resp = client.get(url)
    match = CSRF_RE.search(resp.get_data(as_text=True))
    assert match, f"No CSRF token found on {url} (status {resp.status_code})"
    return match.group(1)


def register(client, email: str, password: str = STRONG_PASSWORD, confirm: str | None = None):
    token = csrf_from(client, "/register")
    return client.post("/register", data={
        "email": email, "password": password,
        "confirm_password": password if confirm is None else confirm, "csrf_token": token,
    })


def login(client, email: str, password: str = STRONG_PASSWORD):
    token = csrf_from(client, "/login")
    return client.post("/login", data={"email": email, "password": password, "csrf_token": token})


def logout(client):
    token = csrf_from(client, "/dashboard")
    return client.post("/logout", data={"csrf_token": token})


def add_transaction(client, **overrides):
    data = {"date": "2025-03-01", "description": "Groceries - Aldi", "category": "Groceries",
            "amount": "50.00", "type": "expense"}
    data.update(overrides)
    data["csrf_token"] = csrf_from(client, "/transactions")
    return client.post("/transactions", data=data)


def add_goal(client, **overrides):
    data = {"name": "Emergency fund", "target": "3000", "saved": "500"}
    data.update(overrides)
    data["csrf_token"] = csrf_from(client, "/goals")
    return client.post("/goals", data=data)


def post_with_csrf(client, url: str, data: dict | None = None, token_page: str = "/dashboard", **kwargs):
    payload = dict(data or {})
    payload["csrf_token"] = csrf_from(client, token_page)
    return client.post(url, data=payload, **kwargs)
