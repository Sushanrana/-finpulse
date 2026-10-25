"""Financial Health Score (0–100), rule-based and fully explainable.

    score = savings rate (40) + expense balance (30) + goal progress (30)

* Savings rate (40 pts): (income − expenses) / income. 20% or more earns full
  points; 0% or below earns none; linear in between.
* Expense balance (30 pts): share of spending on "wants" (dining,
  entertainment, shopping, subscriptions, travel). 30% or less (the 50/30/20
  rule) earns full points; 70% or more earns none; linear in between.
* Goal progress (30 pts): average % funded across savings goals (capped at
  100% per goal). No goals earns no points.

Two users with identical income get different scores when their behaviour
differs, because every part depends on how the money is used.
"""
from __future__ import annotations

from typing import Any, Iterable

from . import analytics

SAVINGS_WEIGHT, BALANCE_WEIGHT, GOALS_WEIGHT = 40, 30, 30
SAVINGS_TARGET = 0.20
DISCRETIONARY_GOOD = 0.30
DISCRETIONARY_BAD = 0.70


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def savings_component(s: dict[str, Any]) -> dict[str, Any]:
    rate = s["savings_rate"]
    if rate is None:
        points, value, why = 0.0, "n/a", "No income recorded yet, so add income to score this part."
    else:
        points = SAVINGS_WEIGHT * _clamp(rate / SAVINGS_TARGET)
        value = f"{rate:.0%}"
        why = (f"You keep {rate:.0%} of your income "
               f"({analytics.format_aud(s['net'])} of {analytics.format_aud(s['income'])}). "
               f"Saving 20% or more earns all {SAVINGS_WEIGHT} points.")
    return {"key": "savings_rate", "label": "Savings rate", "weight": SAVINGS_WEIGHT,
            "points": round(points, 1), "value": value, "explanation": why}


def balance_component(s: dict[str, Any]) -> dict[str, Any]:
    if s["expense"] <= 0:
        if s["income"] > 0:
            points, value, why = float(BALANCE_WEIGHT), "0%", "No expenses recorded, so your spending is perfectly balanced."
        else:
            points, value, why = 0.0, "n/a", "No transactions yet, so add expenses to score this part."
    else:
        share = s["discretionary_share"]
        points = BALANCE_WEIGHT * _clamp((DISCRETIONARY_BAD - share) / (DISCRETIONARY_BAD - DISCRETIONARY_GOOD))
        value = f"{share:.0%}"
        why = (f"{share:.0%} of your spending goes on wants (dining, entertainment, shopping, "
               f"subscriptions, travel). 30% or less earns all {BALANCE_WEIGHT} points; 70% or more earns none.")
    return {"key": "expense_balance", "label": "Expense balance", "weight": BALANCE_WEIGHT,
            "points": round(points, 1), "value": value, "explanation": why}


def goals_component(goals: list[dict[str, Any]]) -> dict[str, Any]:
    if not goals:
        points, value, why = 0.0, "n/a", "No savings goals yet, so create one to earn these points."
    else:
        progress = [_clamp(float(g["saved"]) / float(g["target"])) for g in goals]
        avg = sum(progress) / len(progress)
        points = GOALS_WEIGHT * avg
        value = f"{avg:.0%}"
        why = (f"Your {len(goals)} goal{'s are' if len(goals) != 1 else ' is'} {avg:.0%} funded on average. "
               f"Fully funded goals earn all {GOALS_WEIGHT} points.")
    return {"key": "goal_progress", "label": "Goal progress", "weight": GOALS_WEIGHT,
            "points": round(points, 1), "value": value, "explanation": why}


def grade(score: int) -> str:
    if score >= 80:
        return "Excellent"
    if score >= 60:
        return "Good"
    if score >= 40:
        return "Fair"
    return "Needs attention"


def calculate(transactions: Iterable[dict[str, Any]], goals: Iterable[dict[str, Any]]) -> dict[str, Any]:
    goals = list(goals)
    s = analytics.summary(transactions)
    components = [savings_component(s), balance_component(s), goals_component(goals)]
    raw = sum(c["points"] for c in components)
    score = int(round(_clamp(raw, 0, 100)))
    return {"score": score, "grade": grade(score), "components": components}
