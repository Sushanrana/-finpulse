# FinPulse: personal finance & investment dashboard

FinPulse helps students and young professionals with irregular income see where their money goes. It brings
**tracking → goals → health score → advice → long-term projection** together in one simple, secure tool.

Stack: **Python 3.11+, Flask, SQLite, Pandas, Jinja/HTML/CSS/JS, Chart.js 4 (bundled locally), pytest**.

```
finpulse/
├── app.py                 # Flask app factory, routes, auth, security headers
├── db.py                  # SQLite helpers (parameterised queries only)
├── schema.sql             # users / transactions / goals
├── seed.py                # demo account with ~6 months of data
├── services/
│   ├── validation.py      # shared server-side input validation
│   ├── analytics.py       # Pandas aggregations for charts
│   ├── csv_import.py      # CSV upload validation
│   ├── health_score.py    # 0–100 explainable score
│   ├── recommendations.py # rule-based tips
│   └── projection.py      # Time Machine (future value)
├── templates/             # Jinja templates (dark, mobile-friendly)
├── static/                # css/style.css, js/app.js, js/charts.js, js/chart.umd.min.js, fonts/
├── tests/                 # pytest suite (91 tests)
└── sample_data/           # CSVs for the import feature
```

## Run it locally (VS Code)

```bash
cd finpulse
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env            # Windows: copy .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # paste the output as SECRET_KEY in .env

python seed.py                  # optional: creates demo@finpulse.app / Demo@1234
flask --app app run --debug     # open http://127.0.0.1:5000
```

Run the tests with `python -m pytest` (or `python -m pytest -v` to see each test name).

> The app **refuses to start without `SECRET_KEY`**. The key is never hard-coded.

---

## Step-by-step build guide (what to run, what you should see)

### Step 1: Secure authentication
* **Run:** `python -m pytest tests/test_auth.py -v`, then `flask --app app run --debug`.
* **You should see:** 14 passing tests. In the browser, `/` redirects to **Log in**. Register with a weak password
  (e.g. `password`) and you get a clear error. A valid registration takes you to the dashboard. A wrong password
  and an unknown email both show the same message: *"Invalid email or password."* Each failed attempt is
  written to `instance/security.log` (`Failed login attempt email=… ip=…`).
* **How:** Werkzeug `generate_password_hash` (scrypt), Flask signed session cookie (HttpOnly, SameSite=Lax,
  2-hour lifetime, regenerated on login), Flask-WTF `CSRFProtect` on every POST, logout is POST-only,
  log-injection-safe logging and constant-ish login timing.

### Step 2: Transactions & CSV import
* **Run:** `python -m pytest tests/test_transactions.py tests/test_csv_import.py -v`
* **You should see:** On **Transactions**, add an expense or income (date, description, category, amount, type).
  It appears in the history table, where you can filter by type, category or month, and delete it.
  Import `sample_data/transactions_sample.csv` → *"30 imported, 0 skipped"*.
  Import `sample_data/transactions_with_errors.csv` → *"4 imported, 8 skipped"* with one message per bad row
  (e.g. `Row 4: Invalid date '2025-13-45', so use YYYY-MM-DD or DD/MM/YYYY.`). Importing a file twice skips every
  duplicate. `bank_export_signed.csv` shows bank-style negative amounts with no `type` column.
* **Validation:** `.csv` extension and MIME type, ≤ 2 MB, UTF-8, ≤ 5,000 rows, required columns
  `date, description, category, amount` (optional `type`), dates `YYYY-MM-DD` or `DD/MM/YYYY`, amounts
  with ≤ 2 decimals, non-zero, duplicates within the file and against existing data, and spreadsheet
  formula injection (`=`, `+`, `-`, `@` at the start of text).

### Step 3: Dashboard
* **Run:** `python -m pytest tests/test_dashboard.py -v`
* **You should see:** KPI cards (income, expenses, net, savings rate) and three Chart.js charts:
  **spending by category** (doughnut), **monthly income vs expense** (bars) and **savings trend**
  (cumulative line). Months with no data show as zero so the trend stays honest.

### Step 4: Savings goals
* **Run:** `python -m pytest tests/test_goals.py -v`
* **You should see:** Create a goal (name, target, saved). The card shows a progress bar, % funded, and an
  ETA based on your average monthly savings. Add or withdraw money (enter a negative amount to withdraw);
  progress is capped at 100%.

### Step 5: Financial Health Score
* **Run:** `python -m pytest tests/test_health_score.py -v`
* **You should see:** A 0–100 ring plus a breakdown:

| Part | Weight | Full points when… | Zero points when… |
|---|---|---|---|
| Savings rate | 40 | you save ≥ 20% of income | you save ≤ 0% |
| Expense balance | 30 | "wants" (dining, entertainment, shopping, subscriptions, travel) ≤ 30% of spending | wants ≥ 70% |
| Goal progress | 30 | goals are 100% funded on average | no goals / nothing saved |

  Each part scales linearly between those limits. Two users on the same A$3,000 income score **97** vs **26**
  depending on behaviour (see `test_same_income_different_behaviour_different_scores`).

### Step 6: Recommendations
* **Run:** `python -m pytest tests/test_recommendations.py -v`
* **You should see:** On **Insights**, tips such as *"Dining is 32% of spending, so try a 20% cut. That frees
  up about A$64.00 a month"* and *"You're on track for your goal 'Japan trip' in 8 months"*, sorted by urgency.
  Rules cover overspending, savings rate bands, the top discretionary category, the 50/30/20 "wants" share,
  rent above 30% of income, subscriptions, and goal ETAs.

### Step 7: Opportunity Cost Time Machine
* **Run:** `python -m pytest tests/test_projection.py -v`
* **You should see:** Enter a monthly amount and expected annual return. You get the 5/10/20-year results, with
  "invest it" vs "spend it" shown on a line chart.
  `FV = P × (((1 + i)^n − 1) / i)`, `i = annual rate / 12`, `n = years × 12`.
  Example: A$100/month at 7% for 10 years = **A$17,308.48** (versus A$12,000 spent).

### Security tests
* **Run:** `python -m pytest tests/test_security.py -v`
* Covers SQL injection (login, form fields, filters), CSRF (missing, forged and cross-session tokens on every
  state-changing route), IDOR (another user's transactions or goals → 404 and untouched), XSS escaping,
  security headers, cookie flags, path traversal on sample downloads, and no card/bank columns in the schema.

---

## Security design

| Requirement | Implementation |
|---|---|
| Password storage | Werkzeug scrypt hashes; plain text never stored or logged |
| Sessions | Flask signed cookie, `SECRET_KEY` from env, HttpOnly, SameSite, 2h expiry, cleared on login/logout |
| CSRF | Flask-WTF `CSRFProtect` on every POST (tokens tied to the session) |
| SQL injection | `?` placeholders only (`db.py`), never string-built SQL values |
| Access control | Every query filters on `user_id`; update/delete use `WHERE id = ? AND user_id = ?` → 404 otherwise |
| Input validation | Server-side in `services/validation.py` (HTML attributes are convenience only) |
| Headers | CSP (`script-src 'self'`, no inline JS), X-Frame-Options/frame-ancestors, nosniff, Referrer-Policy, Permissions-Policy, COOP, HSTS on HTTPS, `no-store` on private pages |
| Logging | Failed logins, CSRF failures and rejected imports → `instance/security.log` (CR/LF stripped) |
| Sensitive data | No card numbers, BSBs or account numbers are collected or stored |
| Uploads | Size cap (Flask `MAX_CONTENT_LENGTH` + 2 MB check), extension + MIME + binary sniffing, formula-injection guard |

### Known gaps / future work
* **Encryption at rest:** SQLite files are not encrypted. Future work: SQLCipher or OS/disk-level encryption,
  plus encrypted backups.
* Rate limiting / account lockout after repeated failed logins (e.g. Flask-Limiter).
* MFA (TOTP) and password reset via email.
* Bank-feed integrations (Open Banking / CDR) instead of CSV.

## Hosted preview notes
In the hosted preview, FinPulse runs inside the platform's FastAPI process (`backend/server.py` mounts the Flask
app via `a2wsgi`) and the platform's dev server proxies all paths to it. The preview sets
`SESSION_COOKIE_SECURE=1`, `SESSION_COOKIE_SAMESITE=None` and `FINPULSE_FRAME_ANCESTORS=*` so the app works
inside the platform's embedded preview frame. Locally, the stricter defaults (`Lax`, `frame-ancestors 'none'`)
apply.

*FinPulse is an educational project, not financial advice.*
