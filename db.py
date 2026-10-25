"""SQLite access layer.

Every helper takes SQL with `?` placeholders plus a parameter tuple. Values are
never string-formatted into SQL, which is what keeps FinPulse safe from SQL
injection.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable, Sequence

from flask import Flask, current_app, g

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_db() -> sqlite3.Connection:
    """Return one connection per request (stored on flask.g)."""
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_exc: BaseException | None = None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db() -> None:
    conn = get_db()
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def query_all(sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in get_db().execute(sql, tuple(params)).fetchall()]


def query_one(sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
    row = get_db().execute(sql, tuple(params)).fetchone()
    return dict(row) if row is not None else None


def execute(sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
    conn = get_db()
    cur = conn.execute(sql, tuple(params))
    conn.commit()
    return cur


def execute_many(sql: str, rows: Iterable[Sequence[Any]]) -> int:
    conn = get_db()
    cur = conn.executemany(sql, [tuple(r) for r in rows])
    conn.commit()
    return cur.rowcount


def init_app(app: Flask) -> None:
    app.teardown_appcontext(close_db)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    with app.app_context():
        init_db()
