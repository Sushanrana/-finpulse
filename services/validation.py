"""Server-side input validation shared by the web forms and CSV import."""
from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta

MAX_AMOUNT = 1_000_000_000
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
AMOUNT_RE = re.compile(r"^-?\d+(\.\d{1,2})?$")
CATEGORY_RE = re.compile(r"^[A-Za-z0-9 &/'\-]+$")
# Leading characters that make spreadsheets evaluate a cell as a formula (CSV injection).
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

CATEGORIES = [
    "Salary", "Freelance", "Allowance", "Gifts",
    "Rent", "Groceries", "Dining", "Transport", "Utilities",
    "Entertainment", "Shopping", "Subscriptions", "Education",
    "Health", "Travel", "Other",
]
# "Wants" in the 50/30/20 rule. Used by the health score and recommendations.
DISCRETIONARY = {"dining", "entertainment", "shopping", "subscriptions", "travel"}
TRANSACTION_TYPES = ("income", "expense")


class ValidationError(ValueError):
    """Raised with a user-friendly message when input is invalid."""


def validate_email(raw: str | None) -> str:
    email = (raw or "").strip().lower()
    if not email or len(email) > 254 or not EMAIL_RE.match(email):
        raise ValidationError("Enter a valid email address.")
    return email


def validate_password(password: str | None) -> str:
    pw = password or ""
    if len(pw) < 8 or len(pw) > 128:
        raise ValidationError("Password must be 8–128 characters long.")
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        raise ValidationError("Password must contain at least one letter and one number.")
    return pw


def parse_date(raw: str | None) -> str:
    """Accept YYYY-MM-DD or DD/MM/YYYY and return ISO YYYY-MM-DD."""
    text = (raw or "").strip()
    parsed: date | None = None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(text, fmt).date()
            break
        except ValueError:
            continue
    if parsed is None:
        shown = text[:20] or "(empty)"
        raise ValidationError(f"Invalid date '{shown}', so use YYYY-MM-DD or DD/MM/YYYY.")
    if parsed.year < 1970:
        raise ValidationError("Date must be in 1970 or later.")
    if parsed > date.today() + timedelta(days=365):
        raise ValidationError("Date cannot be more than a year in the future.")
    return parsed.isoformat()


def parse_amount(raw: object, *, allow_negative: bool = False, allow_zero: bool = False,
                 maximum: float = MAX_AMOUNT, label: str = "Amount") -> float:
    text = str(raw if raw is not None else "").strip()
    text = text.replace(",", "").replace("A$", "").replace("$", "").replace(" ", "")
    if not AMOUNT_RE.match(text):
        shown = str(raw)[:20] if raw not in (None, "") else "(empty)"
        raise ValidationError(f"Invalid {label.lower()} '{shown}', so use a number with up to 2 decimals.")
    value = float(text)
    if math.isnan(value) or math.isinf(value):
        raise ValidationError(f"{label} must be a real number.")
    if value < 0 and not allow_negative:
        raise ValidationError(f"{label} must be positive.")
    if value == 0 and not allow_zero:
        raise ValidationError(f"{label} cannot be zero.")
    if abs(value) > maximum:
        raise ValidationError(f"{label} is too large (max {maximum:,.0f}).")
    return round(value, 2)


def clean_text(raw: str | None, label: str, max_len: int) -> str:
    text = " ".join((raw or "").split())  # collapses newlines/tabs (log + CSV safety)
    if not text:
        raise ValidationError(f"{label} is required.")
    if len(text) > max_len:
        raise ValidationError(f"{label} must be {max_len} characters or fewer.")
    if text.startswith(FORMULA_PREFIXES):
        raise ValidationError(f"{label} cannot start with =, +, - or @ (spreadsheet formula injection).")
    return text


def clean_category(raw: str | None) -> str:
    text = clean_text(raw, "Category", 40)
    if not CATEGORY_RE.match(text):
        raise ValidationError("Category may only contain letters, numbers, spaces and & / ' -.")
    for known in CATEGORIES:
        if known.lower() == text.lower():
            return known
    return text[0].upper() + text[1:]


def parse_type(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value not in TRANSACTION_TYPES:
        raise ValidationError("Type must be 'income' or 'expense'.")
    return value
