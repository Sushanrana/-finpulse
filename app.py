"""FinPulse: personal finance and investment dashboard (Flask application).

Run locally:  flask --app app run --debug   (see README.md)
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
from datetime import date, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   send_from_directory, session, url_for)
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

import db
from services import analytics, csv_import, health_score, projection, recommendations
from services.validation import (CATEGORIES, ValidationError, clean_category, clean_text,
                                 parse_amount, parse_date, parse_type, validate_email,
                                 validate_password)

try:  # python-dotenv is optional; env vars can also be exported in the shell
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent
SAMPLE_DIR = BASE_DIR / "sample_data"
GENERIC_LOGIN_ERROR = "Invalid email or password."
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

csrf = CSRFProtect()
security_log = logging.getLogger("finpulse.security")
# Used to keep login timing similar whether or not the email exists.
_DUMMY_HASH = generate_password_hash("finpulse-timing-equaliser")


# --------------------------------------------------------------------------- helpers
def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _log_safe(value: object, limit: int = 80) -> str:
    """Neutralise CR/LF and control characters to prevent log injection."""
    return "".join(ch if ch.isprintable() else "?" for ch in str(value))[:limit]


def _configure_security_log(app: Flask) -> None:
    if getattr(security_log, "_finpulse_configured", False):
        return
    security_log.setLevel(logging.INFO)
    log_path = Path(app.config["SECURITY_LOG"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    security_log.addHandler(handler)
    stream = logging.StreamHandler()
    stream.setFormatter(handler.formatter)
    security_log.addHandler(stream)
    security_log._finpulse_configured = True  # type: ignore[attr-defined]


def login_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        if g.get("user") is None:
            flash("Please log in to continue.", "info")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def current_user_id() -> int:
    return int(g.user["id"])


# --------------------------------------------------------------------------- data access (always scoped by user_id)
def fetch_transactions(user_id: int, tx_type: str | None = None, category: str | None = None,
                       month: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT id, date, description, category, amount, type FROM transactions WHERE user_id = ?"
    params: list[Any] = [user_id]
    if tx_type:
        sql += " AND type = ?"
        params.append(tx_type)
    if category:
        sql += " AND category = ?"
        params.append(category)
    if month:
        sql += " AND substr(date, 1, 7) = ?"
        params.append(month)
    sql += " ORDER BY date DESC, id DESC"
    return db.query_all(sql, params)


def fetch_goals(user_id: int) -> list[dict[str, Any]]:
    return db.query_all("SELECT id, name, target, saved FROM goals WHERE user_id = ? ORDER BY id", (user_id,))


def fetch_goal(user_id: int, goal_id: int) -> dict[str, Any]:
    goal = db.query_one("SELECT id, name, target, saved FROM goals WHERE id = ? AND user_id = ?",
                        (goal_id, user_id))
    if goal is None:
        abort(404)
    return goal


def validate_transaction_form(form: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    checks: list[tuple[str, Callable[[str], Any]]] = [
        ("date", parse_date),
        ("description", lambda v: clean_text(v, "Description", 120)),
        ("category", clean_category),
        ("amount", parse_amount),
        ("type", parse_type),
    ]
    clean: dict[str, Any] = {}
    errors: list[str] = []
    for key, fn in checks:
        try:
            clean[key] = fn(form.get(key, ""))
        except ValidationError as exc:
            errors.append(str(exc))
    return clean, errors


def validate_goal_form(form: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    clean: dict[str, Any] = {}
    errors: list[str] = []
    try:
        clean["name"] = clean_text(form.get("name"), "Goal name", 60)
    except ValidationError as exc:
        errors.append(str(exc))
    try:
        clean["target"] = parse_amount(form.get("target"), label="Target")
    except ValidationError as exc:
        errors.append(str(exc))
    try:
        clean["saved"] = parse_amount(form.get("saved") or "0", allow_zero=True, label="Saved")
    except ValidationError as exc:
        errors.append(str(exc))
    return clean, errors


# --------------------------------------------------------------------------- app factory
def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    if load_dotenv is not None:
        load_dotenv(BASE_DIR / ".env")

    app = Flask(__name__, instance_path=str(BASE_DIR / "instance"))
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        DATABASE=os.environ.get("FINPULSE_DB", str(BASE_DIR / "instance" / "finpulse.db")),
        SECURITY_LOG=os.environ.get("FINPULSE_SECURITY_LOG", str(BASE_DIR / "instance" / "security.log")),
        MAX_CONTENT_LENGTH=csv_import.MAX_BYTES + 512 * 1024,
        SESSION_COOKIE_NAME="finpulse_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=_flag("SESSION_COOKIE_SECURE"),
        SESSION_COOKIE_SAMESITE=os.environ.get("SESSION_COOKIE_SAMESITE", "Lax"),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
        WTF_CSRF_TIME_LIMIT=7200,
        FRAME_ANCESTORS=os.environ.get("FINPULSE_FRAME_ANCESTORS", "'none'"),
    )
    if test_config:
        app.config.update(test_config)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY is not set. Copy .env.example to .env and set SECRET_KEY "
            "(python -c \"import secrets; print(secrets.token_hex(32))\")."
        )
    if app.config["SESSION_COOKIE_SAMESITE"] == "None" and not app.config["SESSION_COOKIE_SECURE"]:
        raise RuntimeError("SESSION_COOKIE_SAMESITE=None requires SESSION_COOKIE_SECURE=1.")

    if _flag("FINPULSE_TRUST_PROXY"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)  # type: ignore[method-assign]

    csrf.init_app(app)
    db.init_app(app)
    if not app.testing:
        _configure_security_log(app)

    _register_template_helpers(app)
    _register_hooks(app)
    _register_routes(app)
    return app


def _register_template_helpers(app: Flask) -> None:
    app.add_template_filter(analytics.format_aud, "aud")

    @app.template_filter("au_date")
    def au_date(value: str) -> str:
        try:
            y, m, d = str(value).split("-")
            return f"{d}/{m}/{y}"
        except ValueError:
            return str(value)

    @app.template_filter("pct")
    def pct(value: float | None, digits: int = 0) -> str:
        return "n/a" if value is None else f"{value * 100:.{digits}f}%"

    @app.context_processor
    def inject_globals() -> dict[str, Any]:
        return {"CATEGORIES": CATEGORIES}


def _register_hooks(app: Flask) -> None:
    @app.before_request
    def load_user() -> None:
        g.user = None
        user_id = session.get("user_id")
        if user_id is not None:
            user = db.query_one("SELECT id, email FROM users WHERE id = ?", (user_id,))
            if user is None:
                session.clear()
            else:
                g.user = user

    @app.after_request
    def security_headers(response):
        frame = app.config["FRAME_ANCESTORS"]
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; "
            f"form-action 'self'; frame-ancestors {frame}"
        )
        if frame == "'none'":
            response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=(), payment=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        if app.config["SESSION_COOKIE_SECURE"]:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if g.get("user") is not None and not request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(CSRFError)
    def csrf_error(exc: CSRFError):
        security_log.warning("CSRF validation failed path=%s ip=%s reason=%s",
                             _log_safe(request.path), request.remote_addr, _log_safe(exc.description))
        return render_template("error.html", code=400, title="Security check failed",
                               message="Your form session expired or the request was not sent from FinPulse. "
                                       "Go back, refresh the page and try again."), 400

    @app.errorhandler(404)
    def not_found(_exc):
        return render_template("error.html", code=404, title="Not found",
                               message="That page or record doesn't exist (or isn't yours)."), 404

    @app.errorhandler(405)
    def not_allowed(_exc):
        return render_template("error.html", code=405, title="Method not allowed",
                               message="That action isn't allowed this way."), 405

    @app.errorhandler(413)
    def too_large(_exc):
        return render_template("error.html", code=413, title="File too large",
                               message=f"Uploads are limited to {csv_import.MAX_BYTES // (1024 * 1024)} MB."), 413

    @app.errorhandler(500)
    def server_error(_exc):
        return render_template("error.html", code=500, title="Something went wrong",
                               message="An unexpected error occurred. Please try again."), 500


def _register_routes(app: Flask) -> None:
    # ------------------------------------------------------------------ auth
    @app.get("/")
    def index():
        return redirect(url_for("dashboard" if g.user else "login"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if g.user:
            return redirect(url_for("dashboard"))
        errors: list[str] = []
        email_value = ""
        if request.method == "POST":
            email_value = request.form.get("email", "")[:254]
            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")
            try:
                email = validate_email(email_value)
            except ValidationError as exc:
                errors.append(str(exc))
                email = ""
            try:
                validate_password(password)
            except ValidationError as exc:
                errors.append(str(exc))
            if password != confirm:
                errors.append("Passwords do not match.")
            if not errors:
                try:
                    cur = db.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)",
                                     (email, generate_password_hash(password)))
                except sqlite3.IntegrityError:
                    errors.append("Registration failed. Try a different email, or log in if you already have an account.")
                else:
                    session.clear()
                    session["user_id"] = cur.lastrowid
                    session.permanent = True
                    security_log.info("New account registered user_id=%s ip=%s", cur.lastrowid, request.remote_addr)
                    flash("Account created. Welcome to FinPulse!", "success")
                    return redirect(url_for("dashboard"))
        return render_template("register.html", errors=errors, email=email_value), (400 if errors else 200)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.user:
            return redirect(url_for("dashboard"))
        error = None
        email_value = ""
        if request.method == "POST":
            email_value = request.form.get("email", "")[:254]
            password = request.form.get("password", "")
            user = None
            try:
                email = validate_email(email_value)
                user = db.query_one("SELECT id, email, password_hash FROM users WHERE email = ?", (email,))
            except ValidationError:
                pass
            if user is not None and check_password_hash(user["password_hash"], password):
                session.clear()  # prevent session fixation
                session["user_id"] = user["id"]
                session.permanent = True
                security_log.info("Successful login user_id=%s ip=%s", user["id"], request.remote_addr)
                return redirect(url_for("dashboard"))
            if user is None:
                check_password_hash(_DUMMY_HASH, password)  # equalise timing
            security_log.warning("Failed login attempt email=%s ip=%s", _log_safe(email_value), request.remote_addr)
            error = GENERIC_LOGIN_ERROR
        return render_template("login.html", error=error, email=email_value), (401 if error else 200)

    @app.post("/logout")
    def logout():
        if g.user:
            security_log.info("Logout user_id=%s", g.user["id"])
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for("login"))

    # ------------------------------------------------------------------ dashboard
    @app.get("/dashboard")
    @login_required
    def dashboard():
        uid = current_user_id()
        txs = fetch_transactions(uid)
        goals = fetch_goals(uid)
        return render_template(
            "dashboard.html",
            summary=analytics.summary(txs),
            charts=analytics.chart_data(txs),
            health=health_score.calculate(txs, goals),
            recs=recommendations.generate(txs, goals)[:3],
            recent=txs[:5],
        )

    # ------------------------------------------------------------------ transactions
    def render_transactions(form: dict[str, str] | None = None, form_errors: list[str] | None = None,
                            import_report: dict[str, Any] | None = None, status: int = 200):
        uid = current_user_id()
        f_type = request.args.get("type", "")
        f_type = f_type if f_type in ("income", "expense") else ""
        f_category = request.args.get("category", "").strip()[:40]
        f_month = request.args.get("month", "").strip()
        f_month = f_month if MONTH_RE.match(f_month) else ""
        txs = fetch_transactions(uid, f_type or None, f_category or None, f_month or None)
        categories = [r["category"] for r in db.query_all(
            "SELECT DISTINCT category FROM transactions WHERE user_id = ? ORDER BY category", (uid,))]
        filtered = analytics.summary(txs)
        return render_template(
            "transactions.html",
            transactions=txs,
            totals=filtered,
            categories=categories,
            filters={"type": f_type, "category": f_category, "month": f_month},
            form=form or {"date": date.today().isoformat(), "type": "expense", "description": "",
                          "category": "", "amount": ""},
            form_errors=form_errors or [],
            import_report=import_report,
            max_rows=csv_import.MAX_ROWS,
        ), status

    @app.route("/transactions", methods=["GET", "POST"])
    @login_required
    def transactions():
        if request.method == "POST":
            form = {k: request.form.get(k, "") for k in ("date", "description", "category", "amount", "type")}
            clean, errors = validate_transaction_form(form)
            if errors:
                return render_transactions(form=form, form_errors=errors, status=400)
            db.execute(
                "INSERT INTO transactions (user_id, date, description, category, amount, type) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (current_user_id(), clean["date"], clean["description"], clean["category"],
                 clean["amount"], clean["type"]),
            )
            flash(f"{clean['type'].title()} of {analytics.format_aud(clean['amount'])} added.", "success")
            return redirect(url_for("transactions"), code=303)
        return render_transactions()

    @app.post("/transactions/<int:tx_id>/delete")
    @login_required
    def delete_transaction(tx_id: int):
        cur = db.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (tx_id, current_user_id()))
        if cur.rowcount == 0:
            abort(404)
        flash("Transaction deleted.", "success")
        next_url = request.form.get("next_url", "")
        # Only allow redirects back to our own transactions page (no open redirect).
        if not next_url.startswith("/transactions"):
            next_url = url_for("transactions")
        return redirect(next_url, code=303)

    @app.post("/transactions/import")
    @login_required
    def import_transactions():
        uid = current_user_id()
        upload = request.files.get("csv_file")
        if upload is None or not upload.filename:
            return render_transactions(import_report={"file_error": "Choose a CSV file to upload."}, status=400)
        data = upload.stream.read(csv_import.MAX_BYTES + 1)
        existing = {csv_import.dedupe_key(r) for r in fetch_transactions(uid)}
        try:
            result = csv_import.parse_csv(data, upload.filename, existing, mimetype=upload.mimetype)
        except csv_import.CSVImportError as exc:
            security_log.info("CSV import rejected user_id=%s reason=%s", uid, _log_safe(exc, 160))
            return render_transactions(import_report={"file_error": str(exc)}, status=400)
        if result.rows:
            db.execute_many(
                "INSERT INTO transactions (user_id, date, description, category, amount, type) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(uid, r["date"], r["description"], r["category"], r["amount"], r["type"]) for r in result.rows],
            )
        report = {
            "file_error": None,
            "imported": len(result.rows),
            "total_rows": result.total_rows,
            "skipped": result.total_rows - len(result.rows),
            "duplicates": result.duplicates,
            "errors": result.errors[:100],
            "more_errors": max(0, len(result.errors) - 100),
        }
        return render_transactions(import_report=report)

    @app.get("/sample/<string:name>")
    @login_required
    def sample_csv(name: str):
        allowed = {"transactions_sample.csv", "transactions_with_errors.csv", "bank_export_signed.csv"}
        if name not in allowed:
            abort(404)
        return send_from_directory(SAMPLE_DIR, name, mimetype="text/csv", as_attachment=True)

    # ------------------------------------------------------------------ goals
    @app.route("/goals", methods=["GET", "POST"])
    @login_required
    def goals():
        uid = current_user_id()
        errors: list[str] = []
        form = {"name": "", "target": "", "saved": "0"}
        if request.method == "POST":
            form = {k: request.form.get(k, "") for k in ("name", "target", "saved")}
            clean, errors = validate_goal_form(form)
            if not errors:
                db.execute("INSERT INTO goals (user_id, name, target, saved) VALUES (?, ?, ?, ?)",
                           (uid, clean["name"], clean["target"], clean["saved"]))
                flash(f"Goal '{clean['name']}' created.", "success")
                return redirect(url_for("goals"), code=303)
        txs = fetch_transactions(uid)
        goal_list = fetch_goals(uid)
        monthly = analytics.summary(txs)["avg_monthly_net"]
        for goal in goal_list:
            goal["progress"] = min(goal["saved"] / goal["target"], 1.0) if goal["target"] else 0
            goal["remaining"] = max(goal["target"] - goal["saved"], 0)
            goal["months_left"] = (-(-goal["remaining"] // monthly) if monthly > 0 and goal["remaining"] > 0 else None)
        return render_template("goals.html", goals=goal_list, form=form, errors=errors,
                               monthly_savings=monthly), (400 if errors else 200)

    @app.post("/goals/<int:goal_id>/deposit")
    @login_required
    def deposit_goal(goal_id: int):
        uid = current_user_id()
        goal = fetch_goal(uid, goal_id)
        try:
            amount = parse_amount(request.form.get("amount"), allow_negative=True, label="Amount")
        except ValidationError as exc:
            flash(str(exc), "error")
            return redirect(url_for("goals"), code=303)
        new_saved = round(max(goal["saved"] + amount, 0), 2)
        db.execute("UPDATE goals SET saved = ? WHERE id = ? AND user_id = ?", (new_saved, goal_id, uid))
        verb = "Added" if amount >= 0 else "Withdrew"
        flash(f"{verb} {analytics.format_aud(abs(amount))} {'to' if amount >= 0 else 'from'} '{goal['name']}'.", "success")
        return redirect(url_for("goals"), code=303)

    @app.post("/goals/<int:goal_id>/delete")
    @login_required
    def delete_goal(goal_id: int):
        cur = db.execute("DELETE FROM goals WHERE id = ? AND user_id = ?", (goal_id, current_user_id()))
        if cur.rowcount == 0:
            abort(404)
        flash("Goal deleted.", "success")
        return redirect(url_for("goals"), code=303)

    # ------------------------------------------------------------------ health score + insights
    @app.get("/health")
    @login_required
    def health():
        uid = current_user_id()
        txs = fetch_transactions(uid)
        goals_ = fetch_goals(uid)
        return render_template("health.html", health=health_score.calculate(txs, goals_),
                               summary=analytics.summary(txs))

    @app.get("/insights")
    @login_required
    def insights():
        uid = current_user_id()
        txs = fetch_transactions(uid)
        goals_ = fetch_goals(uid)
        return render_template("insights.html", recs=recommendations.generate(txs, goals_),
                               summary=analytics.summary(txs))

    # ------------------------------------------------------------------ time machine
    @app.get("/time-machine")
    @login_required
    def time_machine():
        uid = current_user_id()
        s = analytics.summary(fetch_transactions(uid))
        wants = [c for c in s["categories"] if c["category"].lower() in {"dining", "entertainment", "shopping", "subscriptions"}]
        suggestion = None
        if wants and s["months"]:
            suggestion = {"category": wants[0]["category"], "monthly": round(wants[0]["total"] / s["months"], 2)}
        default_monthly = f"{suggestion['monthly']:.2f}" if suggestion else "100"
        monthly_raw = request.args.get("monthly", default_monthly)
        rate_raw = request.args.get("rate", "7")
        errors: list[str] = []
        try:
            monthly, rate = projection.validate_inputs(monthly_raw, rate_raw)
        except ValidationError as exc:
            errors.append(str(exc))
            monthly, rate = 100.0, 7.0
        result = projection.compare(monthly, rate)
        return render_template("time_machine.html", result=result, errors=errors,
                               monthly_raw=str(monthly_raw)[:20], rate_raw=str(rate_raw)[:10],
                               suggestion=suggestion), (400 if errors else 200)


# `flask --app app run` auto-discovers the create_app() factory above.

if __name__ == "__main__":  # pragma: no cover
    create_app().run(debug=_flag("FLASK_DEBUG"))
