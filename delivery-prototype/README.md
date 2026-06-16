# Delivery Prototype

Self-contained demo for local-first signed delivery custody + privacy-safe field metrics logging.

**Fake data only.** Do not connect to Amazon, real routes, or customer/package identifiers.

## Quick start

```powershell
cd delivery-prototype
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/seed_demo_route.py
flask --app app run --port 5099
```

Open:

- Dispatch: http://127.0.0.1:5099/dispatch
- Driver: http://127.0.0.1:5099/driver
- Field metrics: http://127.0.0.1:5099/metrics/log
- Audit: http://127.0.0.1:5099/audit

**On a real delivery route:** install `/metrics/log` to your phone home screen — works offline. See [docs/FIELD_USE.md](docs/FIELD_USE.md).

## Tests

```powershell
cd delivery-prototype
pytest -q
python scripts/run_benchmark.py --iterations 3 --profiles good,weak,offline
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [OUTLINE.md](OUTLINE.md).

## Lemma.id reuse

This prototype adapts Ed25519 signed-credential patterns from lemma.id (issuance, local verify, stamped events). It does **not** use isHuman, PPID, wallet, or production lemma.id APIs.

## Heroku (cloud testing)

**SQLite is enough** for prototype demos; PostgreSQL is optional and only needed if you want server-side routes/events to survive Heroku dyno restarts.

See [docs/DEPLOY_HEROKU.md](docs/DEPLOY_HEROKU.md) for deploy steps, config vars, and SQLite vs Postgres tradeoffs.
