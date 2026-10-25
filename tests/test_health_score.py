"""Feature 5: financial health score."""
from helpers import add_goal, add_transaction
from services import health_score


def tx(category, amount, type_="expense", date="2025-01-10"):
    return {"date": date, "description": category, "category": category, "amount": amount, "type": type_}


INCOME = [tx("Salary", 3000, "income")]


def test_weights_sum_to_100():
    assert health_score.SAVINGS_WEIGHT + health_score.BALANCE_WEIGHT + health_score.GOALS_WEIGHT == 100


def test_perfect_behaviour_scores_100():
    txs = INCOME + [tx("Rent", 1500), tx("Groceries", 300)]  # 40% saved, 0% wants
    result = health_score.calculate(txs, [{"name": "G", "target": 100, "saved": 100}])
    assert result["score"] == 100 and result["grade"] == "Excellent"
    assert [c["points"] for c in result["components"]] == [40, 30, 30]


def test_no_data_scores_zero():
    result = health_score.calculate([], [])
    assert result["score"] == 0 and result["grade"] == "Needs attention"
    assert all(c["explanation"] for c in result["components"])


def test_same_income_different_behaviour_different_scores():
    saver = INCOME + [tx("Rent", 1500), tx("Groceries", 300)]
    spender = INCOME + [tx("Rent", 1500), tx("Dining", 900), tx("Shopping", 500)]
    goals_saver = [{"name": "Fund", "target": 1000, "saved": 800}]
    goals_spender = [{"name": "Fund", "target": 1000, "saved": 100}]
    a = health_score.calculate(saver, goals_saver)
    b = health_score.calculate(spender, goals_spender)
    assert a["score"] > b["score"]
    # spender: savings 3.3% -> 6.7 pts; wants 1400/2900=48.3% -> 16.3 pts; goals 10% -> 3 pts
    assert b["components"][0]["points"] == 6.7
    assert b["components"][1]["points"] == 16.3
    assert b["components"][2]["points"] == 3.0
    assert b["score"] == 26


def test_components_are_linear_and_clamped():
    half = INCOME + [tx("Rent", 2700)]  # 10% savings -> 20 pts
    assert health_score.calculate(half, [])["components"][0]["points"] == 20
    overspend = INCOME + [tx("Rent", 4000)]
    assert health_score.calculate(overspend, [])["components"][0]["points"] == 0
    all_wants = INCOME + [tx("Dining", 1000)]
    assert health_score.calculate(all_wants, [])["components"][1]["points"] == 0


def test_health_page_shows_breakdown(alice):
    add_transaction(alice, type="income", category="Salary", amount="3000", description="Pay")
    add_transaction(alice, category="Rent", amount="1500", description="Rent")
    add_goal(alice, target="1000", saved="500")
    body = alice.get("/health").get_data(as_text=True)
    assert 'data-testid="health-score-value"' in body
    assert "Savings rate" in body and "Expense balance" in body and "Goal progress" in body
    assert "40.0 / 40" in body and "30.0 / 30" in body and "15.0 / 30" in body
    assert ">85<" in body
