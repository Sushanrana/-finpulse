"""Feature 6: rule-based recommendations."""
from helpers import add_transaction
from services import recommendations


def tx(category, amount, type_="expense", date="2025-01-10"):
    return {"date": date, "description": category, "category": category, "amount": amount, "type": type_}


def messages(recs):
    return " | ".join(r["message"] for r in recs)


def test_dining_share_triggers_cut_tip():
    # Dining = 320 of 1000 spending = 32%
    txs = [tx("Salary", 2000, "income"), tx("Rent", 600), tx("Dining", 320), tx("Groceries", 80)]
    recs = recommendations.generate(txs, [])
    assert "Dining is 32% of spending, so try a 20% cut" in messages(recs)
    assert "A$64.00 a month" in messages(recs)


def test_goal_on_track_months():
    # net savings 500/month over 1 month; goal needs 4000 more -> 8 months
    txs = [tx("Salary", 2000, "income"), tx("Rent", 1500)]
    goals = [{"name": "Japan trip", "target": 5000, "saved": 1000}]
    recs = recommendations.generate(txs, goals)
    assert "You're on track for your goal 'Japan trip' in 8 months" in messages(recs)


def test_overspending_is_top_priority():
    txs = [tx("Salary", 1000, "income"), tx("Rent", 1200)]
    recs = recommendations.generate(txs, [{"name": "Car", "target": 5000, "saved": 0}])
    assert recs[0]["kind"] == "danger"
    assert "spending more than you earn" in recs[0]["title"]
    assert "won't reach 'Car'" in messages(recs)


def test_empty_data_prompts_to_start():
    recs = recommendations.generate([], [])
    assert recs[0]["title"] == "Start tracking"
    assert any(r["title"] == "Set a savings goal" for r in recs)


def test_goal_reached_and_subscriptions():
    txs = [tx("Salary", 2000, "income"), tx("Subscriptions", 30)]
    recs = recommendations.generate(txs, [{"name": "Laptop", "target": 100, "saved": 100}])
    titles = [r["title"] for r in recs]
    assert "Goal reached: Laptop" in titles and "Review subscriptions" in titles


def test_insights_page(alice):
    add_transaction(alice, type="income", category="Salary", amount="2000", description="Pay")
    add_transaction(alice, category="Dining", amount="320", description="Food")
    add_transaction(alice, category="Rent", amount="680", description="Rent")
    body = alice.get("/insights").get_data(as_text=True)
    assert "Dining is 32% of spending, so try a 20% cut" in body
