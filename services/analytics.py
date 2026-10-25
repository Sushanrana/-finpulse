"""Pandas aggregations for the dashboard, health score and recommendations."""
from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

from .validation import DISCRETIONARY

COLUMNS = ["date", "description", "category", "amount", "type"]
MAX_CATEGORY_SLICES = 7


def format_aud(value: float | int | None) -> str:
    v = float(value or 0)
    sign = "-" if v < 0 else ""
    return f"{sign}A${abs(v):,.2f}"


def to_frame(transactions: Iterable[dict[str, Any]]) -> pd.DataFrame:
    rows = list(transactions)
    if not rows:
        return pd.DataFrame(columns=COLUMNS + ["month"])
    df = pd.DataFrame(rows)[COLUMNS].copy()
    df["amount"] = df["amount"].astype(float)
    df["month"] = df["date"].astype(str).str.slice(0, 7)
    return df


def summary(transactions: Iterable[dict[str, Any]]) -> dict[str, Any]:
    df = to_frame(transactions)
    income = float(df.loc[df["type"] == "income", "amount"].sum()) if not df.empty else 0.0
    expense = float(df.loc[df["type"] == "expense", "amount"].sum()) if not df.empty else 0.0
    net = income - expense
    months = int(df["month"].nunique()) if not df.empty else 0

    categories: list[dict[str, Any]] = []
    if expense > 0:
        by_cat = (df[df["type"] == "expense"].groupby("category")["amount"].sum()
                  .sort_values(ascending=False))
        categories = [
            {"category": str(cat), "total": round(float(total), 2), "share": float(total) / expense}
            for cat, total in by_cat.items()
        ]
    discretionary_total = sum(c["total"] for c in categories if c["category"].lower() in DISCRETIONARY)

    return {
        "count": int(len(df)),
        "income": round(income, 2),
        "expense": round(expense, 2),
        "net": round(net, 2),
        "savings_rate": (net / income) if income > 0 else None,
        "months": months,
        "avg_monthly_income": income / months if months else 0.0,
        "avg_monthly_expense": expense / months if months else 0.0,
        "avg_monthly_net": net / months if months else 0.0,
        "categories": categories,
        "discretionary_total": round(discretionary_total, 2),
        "discretionary_share": (discretionary_total / expense) if expense > 0 else 0.0,
    }


def chart_data(transactions: Iterable[dict[str, Any]], max_months: int = 12) -> dict[str, Any]:
    df = to_frame(transactions)
    empty = {
        "category": {"labels": [], "values": []},
        "monthly": {"labels": [], "income": [], "expense": []},
        "trend": {"labels": [], "net": [], "cumulative": []},
    }
    if df.empty:
        return empty

    # Spending by category (top N + "Other categories")
    s = summary(df.to_dict("records"))
    cats = s["categories"]
    labels = [c["category"] for c in cats[:MAX_CATEGORY_SLICES]]
    values = [c["total"] for c in cats[:MAX_CATEGORY_SLICES]]
    if len(cats) > MAX_CATEGORY_SLICES:
        labels.append("Other categories")
        values.append(round(sum(c["total"] for c in cats[MAX_CATEGORY_SLICES:]), 2))

    # Monthly income vs expense over a continuous month range
    pivot = df.pivot_table(index="month", columns="type", values="amount", aggfunc="sum", fill_value=0.0)
    for col in ("income", "expense"):
        if col not in pivot.columns:
            pivot[col] = 0.0
    periods = pd.period_range(df["month"].min(), df["month"].max(), freq="M")
    month_keys = [str(p) for p in periods]
    pivot = pivot.reindex(month_keys, fill_value=0.0)
    pivot["net"] = pivot["income"] - pivot["expense"]
    pivot["cumulative"] = pivot["net"].cumsum()
    window = pivot.tail(max_months)
    pretty = [pd.Period(m, freq="M").strftime("%b %Y") for m in window.index]

    return {
        "category": {"labels": labels, "values": values},
        "monthly": {
            "labels": pretty,
            "income": [round(float(v), 2) for v in window["income"]],
            "expense": [round(float(v), 2) for v in window["expense"]],
        },
        "trend": {
            "labels": pretty,
            "net": [round(float(v), 2) for v in window["net"]],
            "cumulative": [round(float(v), 2) for v in window["cumulative"]],
        },
    }
