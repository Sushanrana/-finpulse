"""Seed (or reset) the FinPulse demo account with ~6 months of realistic student data.

Usage:  python seed.py
Login:  demo@finpulse.app / Demo@1234
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

import db
from app import create_app

DEMO_EMAIL = "demo@finpulse.app"
DEMO_PASSWORD = "Demo@1234"


def _month_start(today: date, months_back: int) -> date:
    year, month = today.year, today.month - months_back
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def build_demo_transactions(today: date | None = None) -> list[tuple[str, str, str, float, str]]:
    today = today or date.today()
    rng = random.Random(42)
    rows: list[tuple[str, str, str, float, str]] = []

    for back in range(5, -1, -1):
        start = _month_start(today, back)

        def day(n: int) -> str:
            return min(start + timedelta(days=n - 1), today).isoformat()

        rows += [
            (day(1), "Part-time wage, Woolworths", "Salary", 1450.00, "income"),
            (day(15), "Part-time wage, Woolworths", "Salary", 1450.00, "income"),
            (day(2), "Share-house rent", "Rent", 1040.00, "expense"),
            (day(5), "Spotify Premium", "Subscriptions", 13.99, "expense"),
            (day(9), "Netflix", "Subscriptions", 18.99, "expense"),
            (day(12), "Phone plan", "Utilities", 35.00, "expense"),
            (day(3), "Opal card top-up", "Transport", 40.00, "expense"),
            (day(17), "Opal card top-up", "Transport", 40.00, "expense"),
        ]
        if back % 2 == 0:
            rows.append((day(20), "Freelance website job", "Freelance", float(rng.choice([300, 450, 600])), "income"))
        for n, d in enumerate((4, 11, 18, 25)):
            rows.append((day(d), f"Groceries, Aldi (week {n + 1})", "Groceries", round(rng.uniform(80, 120), 2), "expense"))
        for d in (6, 8, 13, 16, 19, 22, 24, 27):
            place = rng.choice(["Uber Eats", "Campus café", "Sushi train", "Pizza night", "Brunch with friends"])
            rows.append((day(d), place, "Dining", round(rng.uniform(28, 72), 2), "expense"))
        rows.append((day(14), rng.choice(["Cinema tickets", "Concert ticket", "Bowling"]), "Entertainment",
                     round(rng.uniform(30, 85), 2), "expense"))
        rows.append((day(21), rng.choice(["Sneakers", "Hoodie", "Phone case", "Jeans"]), "Shopping",
                     round(rng.uniform(40, 160), 2), "expense"))
        if back in (5, 2):
            rows.append((day(7), "Textbooks", "Education", round(rng.uniform(90, 180), 2), "expense"))
    return rows


DEMO_GOALS = [
    ("Emergency fund", 3000.00, 1250.00),
    ("New laptop", 2200.00, 1600.00),
    ("Japan trip", 4500.00, 700.00),
]


def seed_demo() -> int:
    app = create_app()
    with app.app_context():
        user = db.query_one("SELECT id FROM users WHERE email = ?", (DEMO_EMAIL,))
        if user is None:
            cur = db.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)",
                             (DEMO_EMAIL, generate_password_hash(DEMO_PASSWORD)))
            user_id = int(cur.lastrowid)
        else:
            user_id = int(user["id"])
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                       (generate_password_hash(DEMO_PASSWORD), user_id))
            db.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
            db.execute("DELETE FROM goals WHERE user_id = ?", (user_id,))
        rows = build_demo_transactions()
        db.execute_many(
            "INSERT INTO transactions (user_id, date, description, category, amount, type) VALUES (?, ?, ?, ?, ?, ?)",
            [(user_id, *r) for r in rows],
        )
        db.execute_many("INSERT INTO goals (user_id, name, target, saved) VALUES (?, ?, ?, ?)",
                        [(user_id, *g) for g in DEMO_GOALS])
        print(f"Seeded {DEMO_EMAIL} (user_id={user_id}) with {len(rows)} transactions and {len(DEMO_GOALS)} goals.")
        return user_id


if __name__ == "__main__":
    seed_demo()
