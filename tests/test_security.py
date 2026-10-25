"""Cross-cutting security tests: SQL injection, CSRF, access control, headers."""
from helpers import add_goal, add_transaction, csrf_from, login, post_with_csrf


# ---------------------------------------------------------------- SQL injection
def test_sql_injection_in_login_fails(client, alice):
    for payload in ("' OR '1'='1", "alice@example.com' --", "' OR 1=1; --"):
        resp = login(client, payload, "anything' OR '1'='1")
        assert resp.status_code == 401
        assert client.get("/dashboard").status_code == 302


def test_sql_injection_in_transaction_fields_is_stored_as_text(alice, query):
    payload = "x'); DROP TABLE transactions; --"
    resp = add_transaction(alice, description=payload)
    assert resp.status_code == 303
    rows = query("SELECT description FROM transactions")
    assert rows[0]["description"] == payload  # stored literally, table still exists
    assert query("SELECT COUNT(*) AS n FROM users")[0]["n"] == 1


def test_sql_injection_in_filters_returns_nothing_extra(alice, bob, query):
    add_transaction(bob, description="Bob secret")
    add_transaction(alice, description="Alice item")
    for qs in ("category=' OR '1'='1", "type=income' OR 1=1 --", "month=2025-01' OR '1'='1"):
        body = alice.get(f"/transactions?{qs}").get_data(as_text=True)
        assert "Bob secret" not in body


def test_sql_injection_in_goal_name(alice, query):
    add_goal(alice, name="Goal'); DELETE FROM goals; --")
    assert query("SELECT name FROM goals")[0]["name"] == "Goal'); DELETE FROM goals; --"


# ---------------------------------------------------------------- CSRF
def test_csrf_required_on_login(client, alice):
    resp = client.post("/login", data={"email": "alice@example.com", "password": "Str0ngPass!"})
    assert resp.status_code == 400 and "Security check failed" in resp.get_data(as_text=True)


def test_csrf_required_on_register(client):
    resp = client.post("/register", data={"email": "x@example.com", "password": "Str0ngPass!",
                                          "confirm_password": "Str0ngPass!"})
    assert resp.status_code == 400


def test_csrf_required_on_state_changes(alice, query):
    add_transaction(alice)
    add_goal(alice)
    tx_id = query("SELECT id FROM transactions")[0]["id"]
    goal_id = query("SELECT id FROM goals")[0]["id"]
    attempts = [
        ("/transactions", {"date": "2025-01-01", "description": "x", "category": "Other", "amount": "1", "type": "expense"}),
        (f"/transactions/{tx_id}/delete", {}),
        ("/goals", {"name": "x", "target": "10", "saved": "0"}),
        (f"/goals/{goal_id}/deposit", {"amount": "10"}),
        (f"/goals/{goal_id}/delete", {}),
        ("/logout", {}),
    ]
    for url, data in attempts:
        assert alice.post(url, data=data).status_code == 400, url
        assert alice.post(url, data={**data, "csrf_token": "forged-token"}).status_code == 400, url
    assert query("SELECT COUNT(*) AS n FROM transactions")[0]["n"] == 1
    assert query("SELECT saved FROM goals")[0]["saved"] == 500


def test_csrf_token_from_another_session_is_rejected(app, alice, bob, query):
    bob_token = csrf_from(bob, "/transactions")
    resp = alice.post("/transactions", data={"date": "2025-01-01", "description": "x", "category": "Other",
                                             "amount": "1", "type": "expense", "csrf_token": bob_token})
    assert resp.status_code == 400


# ---------------------------------------------------------------- access control (IDOR)
def test_users_cannot_see_each_others_transactions(alice, bob):
    add_transaction(alice, description="Alice private rent")
    body = bob.get("/transactions").get_data(as_text=True)
    assert "Alice private rent" not in body
    assert "Alice private rent" not in bob.get("/dashboard").get_data(as_text=True)


def test_user_cannot_delete_another_users_transaction(alice, bob, query):
    add_transaction(alice)
    tx_id = query("SELECT id FROM transactions")[0]["id"]
    resp = post_with_csrf(bob, f"/transactions/{tx_id}/delete", token_page="/transactions")
    assert resp.status_code == 404
    assert query("SELECT COUNT(*) AS n FROM transactions")[0]["n"] == 1


def test_user_cannot_modify_or_delete_another_users_goal(alice, bob, query):
    add_goal(alice, name="Alice secret goal", saved="500")
    goal_id = query("SELECT id FROM goals")[0]["id"]
    assert post_with_csrf(bob, f"/goals/{goal_id}/deposit", {"amount": "999"}, token_page="/goals").status_code == 404
    assert post_with_csrf(bob, f"/goals/{goal_id}/delete", token_page="/goals").status_code == 404
    assert query("SELECT saved FROM goals WHERE id = ?", (goal_id,))[0]["saved"] == 500
    assert "Alice secret goal" not in bob.get("/goals").get_data(as_text=True)


def test_scores_and_insights_are_per_user(alice, bob):
    add_transaction(alice, type="income", category="Salary", amount="5000", description="Pay")
    assert "A$5,000.00" not in bob.get("/dashboard").get_data(as_text=True)
    assert ">0<" in bob.get("/health").get_data(as_text=True)


def test_csv_duplicates_are_scoped_per_user(alice, bob, query):
    import io
    content = b"date,description,category,amount,type\n2025-01-01,Rent,Rent,100,expense\n"
    for c in (alice, bob):
        token = csrf_from(c, "/transactions")
        c.post("/transactions/import", data={"csrf_token": token, "csv_file": (io.BytesIO(content), "a.csv")},
               content_type="multipart/form-data")
    assert query("SELECT COUNT(*) AS n FROM transactions")[0]["n"] == 2


def test_sample_download_rejects_path_traversal(alice):
    assert alice.get("/sample/..%2F.env").status_code == 404
    assert alice.get("/sample/../app.py").status_code == 404
    assert alice.get("/sample/transactions_sample.csv").status_code == 200


# ---------------------------------------------------------------- headers & cookies
def test_security_headers(client):
    resp = client.get("/login")
    h = resp.headers
    assert "default-src 'self'" in h["Content-Security-Policy"]
    assert "script-src 'self'" in h["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]
    assert h["X-Frame-Options"] == "DENY"
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Permissions-Policy" in h


def test_authenticated_pages_not_cached(alice):
    assert alice.get("/dashboard").headers["Cache-Control"] == "no-store"


def test_session_cookie_flags(client, alice):
    resp = login(client, "alice@example.com")
    cookie = resp.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_xss_in_description_is_escaped(alice):
    add_transaction(alice, description="<img src=x onerror=alert(1)>")
    body = alice.get("/transactions").get_data(as_text=True)
    assert "<img src=x onerror=alert(1)>" not in body
    assert "&lt;img src=x onerror=alert(1)&gt;" in body


def test_no_card_or_bank_columns_in_schema(query):
    columns = set()
    for table in ("users", "transactions", "goals"):
        columns |= {r["name"] for r in query(f"PRAGMA table_info({table})")}
    for forbidden in ("card", "card_number", "cvv", "bsb", "account_number", "iban"):
        assert forbidden not in columns
