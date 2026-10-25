"""Rule-based recommendations generated from the user's own data.

Each rule is a small, explainable if/then check. Output is a list of dicts:
{"kind": success|info|warning|danger, "title": str, "message": str, "priority": int}
sorted by priority (1 = most urgent).
"""
from __future__ import annotations

import math
from typing import Any, Iterable

from . import analytics
from .analytics import format_aud
from .validation import DISCRETIONARY

CUT_PERCENT = 0.20
DISCRETIONARY_CATEGORY_THRESHOLD = 0.15
DISCRETIONARY_SHARE_LIMIT = 0.30
HOUSING_INCOME_LIMIT = 0.30


def generate(transactions: Iterable[dict[str, Any]], goals: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    goals = list(goals)
    s = analytics.summary(transactions)
    recs: list[dict[str, Any]] = []
    months = max(s["months"], 1)

    def add(priority: int, kind: str, title: str, message: str) -> None:
        recs.append({"priority": priority, "kind": kind, "title": title, "message": message})

    if s["count"] == 0:
        add(1, "info", "Start tracking",
            "Add your first income and expenses, or import a CSV from your bank, to unlock personalised tips.")
    else:
        rate = s["savings_rate"]
        if rate is None:
            add(1, "warning", "No income recorded",
                "You have expenses but no income. Add your pay, allowance or side-hustle income for an accurate picture.")
        elif rate < 0:
            add(1, "danger", "You're spending more than you earn",
                f"Expenses exceed income by {format_aud(-s['net'])} ({abs(rate):.0%} of income). "
                "Start with your biggest category below.")
        elif rate < 0.10:
            gap = (0.10 * s["income"] - s["net"]) / months
            add(2, "warning", "Build a savings buffer",
                f"You're saving {rate:.0%} of income. Saving an extra {format_aud(gap)} a month would get you to 10%.")
        elif rate < 0.20:
            gap = (0.20 * s["income"] - s["net"]) / months
            add(4, "info", "Good progress, now aim for 20%",
                f"You're saving {rate:.0%} of income. Another {format_aud(gap)} a month would reach the 20% target.")
        else:
            add(5, "success", "Strong savings rate",
                f"You're saving {rate:.0%} of income. Consider investing part of it, and use the Time Machine to see the long-term effect.")

        # Biggest discretionary category, e.g. "Dining is 32% of spending, so try a 20% cut"
        wants = [c for c in s["categories"] if c["category"].lower() in DISCRETIONARY]
        if wants and wants[0]["share"] >= DISCRETIONARY_CATEGORY_THRESHOLD:
            top = wants[0]
            saving = top["total"] / months * CUT_PERCENT
            add(2, "warning", f"Trim {top['category'].lower()}",
                f"{top['category']} is {top['share'] * 100:.0f}% of spending, so try a 20% cut. "
                f"That frees up about {format_aud(saving)} a month ({format_aud(saving * 12)} a year).")

        if s["discretionary_share"] > DISCRETIONARY_SHARE_LIMIT:
            add(3, "info", "Watch your 'wants'",
                f"Wants make up {s['discretionary_share']:.0%} of your spending. "
                "The 50/30/20 guideline suggests keeping them near 30%.")

        rent = next((c for c in s["categories"] if c["category"].lower() == "rent"), None)
        if rent and s["income"] > 0 and rent["total"] / s["income"] > HOUSING_INCOME_LIMIT:
            add(3, "info", "Housing is a big slice",
                f"Rent takes {rent['total'] / s['income']:.0%} of your income. Above 30% is considered housing stress. "
                "A share-house or a cheaper area could help.")

        subs = next((c for c in s["categories"] if c["category"].lower() == "subscriptions"), None)
        if subs:
            add(4, "info", "Review subscriptions",
                f"You spend about {format_aud(subs['total'] / months)} a month on subscriptions. "
                "Cancel anything you haven't used in the last month.")

    if not goals:
        add(3, "info", "Set a savings goal",
            "Goals make saving concrete. Start with an emergency fund worth three months of expenses.")

    monthly_savings = s["avg_monthly_net"]
    for goal in goals:
        remaining = float(goal["target"]) - float(goal["saved"])
        name = goal["name"]
        if remaining <= 0:
            add(6, "success", f"Goal reached: {name}", f"You've fully funded '{name}'. Time to set your next goal!")
        elif monthly_savings > 0:
            n = math.ceil(remaining / monthly_savings)
            add(4 if n <= 12 else 3, "success" if n <= 12 else "info", f"On track: {name}",
                f"You're on track for your goal '{name}' in {n} month{'s' if n != 1 else ''} "
                f"at your current savings of {format_aud(monthly_savings)} a month "
                f"({format_aud(remaining)} to go).")
        else:
            add(2, "warning", f"Off track: {name}",
                f"At your current rate you won't reach '{name}'. Saving {format_aud(remaining / 12)} a month "
                "would get you there in 12 months.")

    recs.sort(key=lambda r: r["priority"])
    return recs
