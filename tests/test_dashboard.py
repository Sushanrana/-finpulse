"""Feature 3: dashboard aggregations and page."""
import json
import re

from helpers import add_transaction
from services import analytics

TXS = [
    {"date": "2025-01-01", "description": "Pay", "category": "Salary", "amount": 2000, "type": "income"},
    {"date": "2025-01-05", "description": "Rent", "category": "Rent", "amount": 800, "type": "expense"},
    {"date": "2025-01-09", "description": "Food", "category": "Dining", "amount": 200, "type": "expense"},
    {"date": "2025-03-01", "description": "Pay", "category": "Salary", "amount": 2000, "type": "income"},
    {"date": "2025-03-02", "description": "Rent", "category": "Rent", "amount": 800, "type": "expense"},
]


def test_summary_totals():
    s = analytics.summary(TXS)
    assert s["income"] == 4000 and s["expense"] == 1800 and s["net"] == 2200
    assert abs(s["savings_rate"] - 0.55) < 1e-9
    assert s["months"] == 2
    assert s["categories"][0]["category"] == "Rent"
    assert abs(s["categories"][0]["share"] - 1600 / 1800) < 1e-9


def test_chart_data_fills_missing_months_and_accumulates():
    c = analytics.chart_data(TXS)
    assert c["monthly"]["labels"] == ["Jan 2025", "Feb 2025", "Mar 2025"]
    assert c["monthly"]["income"] == [2000, 0, 2000]
    assert c["monthly"]["expense"] == [1000, 0, 800]
    assert c["trend"]["cumulative"] == [1000, 1000, 2200]
    assert c["category"]["labels"] == ["Rent", "Dining"]


def test_chart_data_empty():
    assert analytics.chart_data([])["monthly"]["labels"] == []
    assert analytics.summary([])["savings_rate"] is None


def test_dashboard_page_embeds_chart_json(alice):
    add_transaction(alice, type="income", category="Salary", amount="1000", description="Pay")
    add_transaction(alice, category="Dining", amount="250", description="Food")
    body = alice.get("/dashboard").get_data(as_text=True)
    for canvas in ("chart-category", "chart-monthly", "chart-trend"):
        assert f'id="{canvas}"' in body
    data = json.loads(re.search(r'id="dashboard-data">(.*?)</script>', body, re.S).group(1))
    assert data["category"]["labels"] == ["Dining"]
    assert "A$1,000.00" in body and "75%" in body


def test_dashboard_empty_state(alice):
    body = alice.get("/dashboard").get_data(as_text=True)
    assert "No transactions yet" in body


def test_chart_json_is_escaped_against_xss(alice):
    add_transaction(alice, category="Dining", description="</script><script>alert(1)</script>")
    body = alice.get("/dashboard").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in body
