"""Feature 2: transactions (manual add / list / delete)."""
from helpers import add_transaction, post_with_csrf


def test_add_and_list_transaction(alice, query):
    resp = add_transaction(alice, description="Weekly groceries", amount="85.50")
    assert resp.status_code == 303
    page = alice.get("/transactions").get_data(as_text=True)
    assert "Weekly groceries" in page and "A$85.50" in page
    rows = query("SELECT date, description, category, amount, type FROM transactions")
    assert rows == [{"date": "2025-03-01", "description": "Weekly groceries", "category": "Groceries",
                     "amount": 85.5, "type": "expense"}]


def test_add_income_with_au_date_and_category_normalised(alice, query):
    add_transaction(alice, date="15/03/2025", type="income", category="salary", amount="1,450.00")
    row = query("SELECT date, category, amount, type FROM transactions")[0]
    assert row == {"date": "2025-03-15", "category": "Salary", "amount": 1450.0, "type": "income"}


def test_invalid_transaction_is_rejected_with_messages(alice, query):
    resp = add_transaction(alice, date="2025-02-30", amount="-5", type="transfer", description="")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 400
    assert "Invalid date" in body
    assert "must be positive" in body
    assert "Type must be" in body
    assert "Description is required" in body
    assert query("SELECT COUNT(*) AS n FROM transactions")[0]["n"] == 0


def test_amount_format_validation(alice):
    for bad in ("abc", "12.345", "1e5", "NaN", "0"):
        resp = add_transaction(alice, amount=bad)
        assert resp.status_code == 400, bad


def test_delete_transaction(alice, query):
    add_transaction(alice)
    tx_id = query("SELECT id FROM transactions")[0]["id"]
    resp = post_with_csrf(alice, f"/transactions/{tx_id}/delete", token_page="/transactions")
    assert resp.status_code == 303
    assert query("SELECT COUNT(*) AS n FROM transactions")[0]["n"] == 0


def test_filters(alice):
    add_transaction(alice, description="Pay", type="income", category="Salary", amount="1000")
    add_transaction(alice, description="Pizza", category="Dining", date="2025-04-02")
    body = alice.get("/transactions?type=income").get_data(as_text=True)
    assert "Pay" in body and "Pizza" not in body
    body = alice.get("/transactions?month=2025-04").get_data(as_text=True)
    assert "Pizza" in body and ">Pay<" not in body
    body = alice.get("/transactions?category=Dining").get_data(as_text=True)
    assert "Pizza" in body


def test_delete_redirect_cannot_leave_site(alice, query):
    add_transaction(alice)
    tx_id = query("SELECT id FROM transactions")[0]["id"]
    resp = post_with_csrf(alice, f"/transactions/{tx_id}/delete", {"next_url": "https://evil.example"},
                          token_page="/transactions")
    assert resp.headers["Location"].endswith("/transactions")
