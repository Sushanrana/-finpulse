"""Opportunity Cost Time Machine.

Future value of a monthly contribution (ordinary annuity):

    FV = P × (((1 + i)^n − 1) / i)
    i  = annual rate / 12
    n  = years × 12
"""
from __future__ import annotations

from typing import Any

from .validation import ValidationError, parse_amount

HORIZONS = (5, 10, 20)
MAX_MONTHLY = 100_000
MAX_RATE = 30.0


def future_value(monthly: float, annual_rate_pct: float, years: int) -> float:
    n = years * 12
    i = annual_rate_pct / 100 / 12
    if i == 0:
        return monthly * n
    return monthly * (((1 + i) ** n - 1) / i)


def validate_inputs(monthly_raw: object, rate_raw: object) -> tuple[float, float]:
    monthly = parse_amount(monthly_raw, maximum=MAX_MONTHLY, label="Monthly amount")
    try:
        rate = parse_amount(rate_raw, allow_zero=True, maximum=MAX_RATE, label="Annual return")
    except ValidationError as exc:
        raise ValidationError(f"{exc} Annual return must be between 0 and {MAX_RATE:.0f}%.") from exc
    return monthly, rate


def compare(monthly: float, annual_rate_pct: float, max_years: int = 20) -> dict[str, Any]:
    horizons = []
    for years in HORIZONS:
        spent = monthly * years * 12
        invested = future_value(monthly, annual_rate_pct, years)
        horizons.append({
            "years": years,
            "spent": round(spent, 2),
            "invested": round(invested, 2),
            "growth": round(invested - spent, 2),
            "multiple": round(invested / spent, 2) if spent else 0,
        })
    years_axis = list(range(0, max_years + 1))
    return {
        "monthly": monthly,
        "rate": annual_rate_pct,
        "horizons": horizons,
        "chart": {
            "labels": [f"Year {y}" for y in years_axis],
            "spent": [round(monthly * y * 12, 2) for y in years_axis],
            "invested": [round(future_value(monthly, annual_rate_pct, y), 2) for y in years_axis],
        },
    }
