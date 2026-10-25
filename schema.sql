-- FinPulse database schema (SQLite).
-- Safe to run repeatedly: every statement is idempotent.
-- Security notes:
--   * No raw card / bank account numbers are ever stored.
--   * Every user-owned row carries user_id and every query filters on it.
--   * KNOWN GAP: SQLite has no built-in encryption at rest (see README "Future work").

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date        TEXT    NOT NULL,                       -- ISO 8601 YYYY-MM-DD
    description TEXT    NOT NULL,
    category    TEXT    NOT NULL,
    amount      REAL    NOT NULL CHECK (amount > 0),    -- always positive; sign comes from type
    type        TEXT    NOT NULL CHECK (type IN ('income', 'expense'))
);

CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions (user_id, date);

CREATE TABLE IF NOT EXISTS goals (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name    TEXT    NOT NULL,
    target  REAL    NOT NULL CHECK (target > 0),
    saved   REAL    NOT NULL DEFAULT 0 CHECK (saved >= 0)
);

CREATE INDEX IF NOT EXISTS idx_goals_user ON goals (user_id);
