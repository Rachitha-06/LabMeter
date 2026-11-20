# LabMeter Suite

AI-powered computer lab energy monitoring, forecasting, and wastage-alert system (academic project).

**Status: Phase 9 complete.** Every phase of the brief is built: data, API with sign-in and roles, CSV import, forecasting with held-out comparison, wastage screening with a review workflow, cost and emissions estimates, reports, backups, and documentation.
The known gaps (real data, screenshots, a container image) are listed in `docs/PROJECT_REPORT.md`.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # edit if you use PostgreSQL later
```

## Requirements

- **Python 3.11 to 3.14.** Python 3.13 is recommended. The full test suite passed on 3.11, 3.12, 3.13 and 3.14.
- **Node.js 22** (or any version that can run Vite 5) to build the interface.
- Dependency ranges are in `requirements.txt`. For an exact reproduction of the tested environment, use `pip install -r requirements-lock.txt`.

## Run the API

```bash
export DATABASE_URL=sqlite:///./labmeter.db
alembic upgrade head                                   # create tables
LABMETER_ADMIN_PASSWORD='choose-a-long-password' \
  python scripts/create_admin.py --email you@college.example   # first administrator
python scripts/generate_synthetic_data.py --days 90    # writes data/synthetic/
python scripts/seed_db.py --data data/synthetic        # loads an empty database
python scripts/ml/train_models.py --out models         # trains and compares the models
python scripts/evaluate_alerts.py                      # runs wastage screening and scores it on the labels
uvicorn app.main:app --reload --port 8000              # API at /api, docs at /docs
pytest                                                 # 278 tests
```

Every endpoint except health and sign-in needs a bearer token. See `docs/API.md` for the role table.

See `docs/API.md` for endpoints, error format, and the CSV import rules.

To regenerate from scratch: delete `labmeter.db`, then repeat the commands above.

## Layout

```
app/config.py              environment-based configuration
app/api/                   FastAPI routers, error envelope, response models
app/main.py               application factory (create_app)
app/db/models.py           SQLAlchemy models (all tables from the Phase 1 schema)
app/db/session.py          engine factory (enables SQLite foreign keys)
app/validation/schemas.py  Pydantic input rules: timestamps, units, ranges, schedules
app/services/readings.py   cumulative-to-interval conversion (resets, gaps, baselines)
app/services/readings_store.py   duplicate-safe storage and CSV import pipeline
app/services/schedules.py  schedule overlap rules
app/services/analytics.py  lab-local day, week, and month totals
migrations/                Alembic migrations (initial schema)
scripts/generate_synthetic_data.py   labelled synthetic dataset generator
scripts/seed_db.py         loads the dataset into an empty database
tests/                     validation, conversion, model constraints, generator, migrations
tests/api/                 endpoint tests for labs, readings, imports, analytics, auth, forecasts
tests/ml/                  metrics, chronological split, baseline, leakage checks
tests/alerts/              wastage rule behaviour
reports/                   evaluation reports for the alert rule (sample and fresh seed)
app/ml/                    features, metrics, split, baseline, models, training, registry
models/                    trained artifacts and evaluation.json (regenerate with scripts/ml/train_models.py)
scripts/ml/train_models.py training and comparison command
app/services/forecasting.py   hourly series, forecast orchestration, evaluation
app/services/alert_rules.py   wastage-screening rule (pure functions)
app/services/alerts.py       alert storage, duplicate protection, review workflow
app/services/alert_evaluation.py   scoring against labelled anomalies
docs/API.md                endpoint reference and import rules
data/synthetic/            generated dataset with PROVENANCE.md
```

## Design decisions

- **Interval kWh is canonical.** Cumulative readings are converted to intervals before storage. The uniqueness rule and checks guard the stored intervals.
- **Timestamps are stored in UTC.** Each lab has its own timezone for display.
- **Missing meter IDs become `default`.** A nullable meter ID would let duplicate rows slip past the unique constraint, because SQL treats NULLs as distinct.
- **Gaps are not filled.** When a gap is longer than 1.5 intervals, the energy is not spread across the missing periods.
- **Meter resets are flagged.** The new cumulative value is used as the interval, marked `reset_assumed`, because a faulty meter can look the same.
- **Overnight schedules are rejected for now.** Supporting them needs a day-boundary rule that will be added with alerts in Phase 7.
- **No tariff or emission factor is seeded.** Official values must come with a source and effective date. The `tariffs` and `emission_factors` tables are empty until Phase 8.

## Synthetic data

Everything in `data/synthetic/` is generated. Readings are marked `reading_type='simulated'`.
`anomalies.csv` holds ground-truth labels for later evaluation. `suspected_wastage` means
"a rule should flag this for review", not "confirmed wastage". See `PROVENANCE.md` for assumptions.

## Continuous integration

`.github/workflows/ci.yml` runs the backend tests on Python 3.11, 3.12, 3.13 and 3.14, the frontend tests and production build, and a dependency audit on every push.

## Container image

A `Dockerfile` is included. Build the interface first (`cd frontend && npm ci && npm run build`), then `docker build -t labmeter .` and run it with a `DATABASE_URL` environment variable. The container has not been built in the development environment, so run it once before relying on it.

## Documentation

- `docs/ARCHITECTURE.md`: system diagram, request path, data flow, entity relationships, directory layout.
- `docs/DEPLOYMENT.md`: installation, configuration, PostgreSQL setup, first administrator, serving, backups and restore, upgrades, and which steps were verified.
- `docs/API.md`: every endpoint, the role table, error codes, CSV import rules, and the method behind each feature.
- `docs/PROJECT_REPORT.md`: method, results with their limits, and future work.
- `docs/VIVA_GUIDE.md`: the design decisions and the likely questions about them.

## Before you see any cost or emissions figure

The system ships with no tariff and no emission factor. Enter them yourself on the **Tariffs & factors** page or with the API:

- the rate bands from your electricity tariff order, with its name and date as the source;
- the emission factor for your grid, with its publisher, version or year, and source.

Until then the dashboard says that estimates are not available yet, and no figure is shown.

## Security notes and limitations

- **Passwords** are hashed with scrypt (random salt per password). Bearer tokens are random and only their SHA-256 hashes are stored, so a database leak does not reveal sessions.
- **Tokens live in `sessionStorage`** in the browser. They are cleared when the tab closes, but any script running on the page could read them. An httpOnly cookie with CSRF protection is the stronger option and is planned as hardening.
- **Failed sign-in limits** are kept in memory, per process. A deployment with several server processes needs a shared store such as Redis.
- **No password reset by email, no two-factor sign-in.** An administrator sets a new password.
- **Transport security** is not enforced by the application. Deploy behind HTTPS.
- **Audit trail** covers corrections (who made them) and imports (who uploaded them). Individual manual reading entries are not attributed to a user yet.
- SQLite only. The models are written to be portable to PostgreSQL, but PostgreSQL has not been tested yet.
- SQLite returns timestamps without a timezone. The code treats stored values as UTC (`app/utils/time.py`). PostgreSQL would return them with an offset.
- Duplicate protection relies on the database unique constraint plus a check before insert. Two simultaneous uploads of the same readings could still race; a production deployment would need row locks or a retry.
- Academic calendar has a model but no endpoint yet.
- **Forecasts use only the readings stored.** The baseline ignores holidays and exam periods, so they can shift an average. The models use them as features.
- **The models do not beat the baseline here.** Linear regression is clearly worse on the sample data, and the forest is no different on either metric. That may change with real data, more history, or features the sample data does not contain (occupancy above all).
- **Wastage alerts are suspicions, not findings.** On the labelled synthetic data the rule reached full precision and recall on the hours it can assess, with no false positives on legitimate or data-gap periods. The labelled anomalies are large and obvious by construction, so this shows the rule finds those patterns, not that it finds realistic waste.
- **Alert coverage is limited to hours with history.** The first two weeks of each weekday cannot be judged, and on the sample data that covers 62% of the labelled wastage hours.
- **Cost and emissions are estimates.** They exclude taxes, fixed and demand charges, and surcharges. Savings are not calculated, because that needs before-and-after measurements.
- **Missing readings are not flagged.** A data gap produces no alert. Data-quality reporting for gaps is not built yet.
- **Holidays and exam periods come from a synthetic calendar,** and the equipment ratings are assumptions. Real calendars and measured ratings are needed before drawing conclusions about the real labs.
- **Forecasts cannot be made for days inside a model's training period,** and every hour needs its lags. A day after a data outage is refused, which is intended.
- **The random forest artifact is about 8.5 MB.** Reducing the tree count or depth makes it smaller at some cost in accuracy.
- **Evaluation k is capped at 8**, the largest value the API accepts. On the sample data the chosen window sat at that cap, so a wider window may do better.
- Analytics groups rows in Python, which is fine for this project's data volumes but would need SQL-side grouping at larger scale.

## Frontend (Phase 4)

The interface is a React single-page app in `frontend/`. It calls the API through `/api`, and Vite
forwards those requests to `http://127.0.0.1:8000` during development.

```bash
# terminal 1: API
export DATABASE_URL=sqlite:///./labmeter.db
uvicorn app.main:app --reload --port 8000

# terminal 2: interface
cd frontend
npm install
npm run dev          # http://localhost:5173
npm test             # 53 tests
npm run build        # production build in frontend/dist
```

To run the API tests against PostgreSQL as well:

```bash
TEST_DATABASE_URL='postgresql+psycopg://user:password@127.0.0.1:5432/labmeter_test' pytest tests/api
```

The PostgreSQL database is emptied and rebuilt on every test, so never point this at a database you care about.

Sign in with an account created by an administrator. Pages you have no permission for are hidden,
and controls you cannot use are disabled.

Pages: **Tariffs & factors** (enter your own values; nothing is shipped), **Alerts** (screening, explanations, and the review workflow), **Forecasts** (baseline forecast, held-out accuracy, saved forecasts), **Dashboard** (measured, imported, and simulated totals with charts and a lab-local table),
**Laboratories** (create, edit, equipment, operating hours), **Readings** (filter, add, correct with a
reason, view history), and **CSV import** (dry run first, then confirm).

The dashboard lists alerts, model comparison, and cost and emissions as "Not built yet" until Phases 6–8.

## Licence, security and contact

- Licence: MIT (see `LICENSE`).
- Security issues: see `SECURITY.md`. Please report privately rather than in a public issue.
- Author and contact: **[Your Name]**, **[your.email@example.com]**. Replace both placeholders in `LICENSE`, `SECURITY.md` and this section before publishing.
- Audit: `FINAL_AUDIT.md` compares the project's state before and after the security and quality work, and lists what remains open.
