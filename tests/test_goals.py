"""Feature 4: savings goals."""
from helpers import add_goal, post_with_csrf


def test_create_goal_and_progress(alice, query):
    resp = add_goal(alice, name="New laptop", target="2000", saved="500")
    assert resp.status_code == 303
    body = alice.get("/goals").get_data(as_text=True)
    assert "New laptop" in body and 'data-pct="25.0"' in body and "25%" in body
    assert query("SELECT name, target, saved FROM goals") == [{"name": "New laptop", "target": 2000.0, "saved": 500.0}]


def test_goal_validation(alice, query):
    resp = add_goal(alice, name="", target="0", saved="-5")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 400
    assert "Goal name is required" in body and "Target cannot be zero" in body and "Saved must be positive" in body
    assert query("SELECT COUNT(*) AS n FROM goals")[0]["n"] == 0


def test_deposit_and_withdraw(alice, query):
    add_goal(alice, target="1000", saved="100")
    goal_id = query("SELECT id FROM goals")[0]["id"]
    post_with_csrf(alice, f"/goals/{goal_id}/deposit", {"amount": "250.50"}, token_page="/goals")
    assert query("SELECT saved FROM goals")[0]["saved"] == 350.5
    post_with_csrf(alice, f"/goals/{goal_id}/deposit", {"amount": "-1000"}, token_page="/goals")
    assert query("SELECT saved FROM goals")[0]["saved"] == 0  # never below zero


def test_progress_capped_at_100(alice):
    add_goal(alice, name="Done", target="100", saved="150")
    body = alice.get("/goals").get_data(as_text=True)
    assert 'data-pct="100.0"' in body and "Goal reached!" in body


def test_delete_goal(alice, query):
    add_goal(alice)
    goal_id = query("SELECT id FROM goals")[0]["id"]
    resp = post_with_csrf(alice, f"/goals/{goal_id}/delete", token_page="/goals")
    assert resp.status_code == 303
    assert query("SELECT COUNT(*) AS n FROM goals")[0]["n"] == 0
