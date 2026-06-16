# Deploy delivery prototype to Heroku

Standalone app (same pattern as `demo-sites/`). Uses **SQLite**, not PostgreSQL.

## SQLite vs PostgreSQL

| Environment | SQLite enough? | Notes |
|-------------|----------------|-------|
| **Local dev** | Yes | Default `data/delivery_prototype.db` persists normally. |
| **Heroku demo** | Yes, with caveats | DB lives on ephemeral disk (`/tmp`). Routes/events are **lost on dyno restart or redeploy**. |
| **Heroku + persistence** | Use Postgres later | Only needed if you want routes/audit history to survive restarts without re-seeding. |

**Field metrics** stay in the phone browser (`localStorage`) — no server DB required.

**Offline driver queue** uses IndexedDB on the device — syncs to server when online; server-side SQLite on Heroku is only for audit/sync after upload.

For prototype testing (create route → scan → sync → audit in one session), **SQLite is sufficient**. Set stable signing keys via config vars so credentials stay valid across restarts even if the DB is empty.

## One-time setup

From repo root (requires [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli)):

```powershell
# Create app (pick a unique name)
heroku create lemma-delivery-prototype

# Stable Ed25519 keys (run once, save output)
cd delivery-prototype
python scripts/generate_heroku_keys.py

heroku config:set DELIVERY_PROTOTYPE_FAKE_DATA_ONLY=1 --app lemma-delivery-prototype
heroku config:set DELIVERY_ISSUER_KEY_HEX=<paste> --app lemma-delivery-prototype
heroku config:set DELIVERY_DEVICE_KEY_HEX=<paste> --app lemma-delivery-prototype
```

## Deploy

Subtree push (keeps app isolated under `delivery-prototype/`):

```powershell
git subtree push --prefix delivery-prototype https://git.heroku.com/lemma-delivery-prototype.git main
```

Or add a git remote once:

```powershell
heroku git:remote -a lemma-delivery-prototype
git subtree push --prefix delivery-prototype heroku main
```

After deploy:

```powershell
heroku run python scripts/seed_demo_route.py --app lemma-delivery-prototype
heroku open --app lemma-delivery-prototype
```

## URLs

- `/dispatch` — create fake route, print QR sheet
- `/driver` — download bundle, scan, queue, benchmark
- `/metrics/log` — **field delay logger** (install to phone home screen; works offline)
- `/audit` — custody chain

For real delivery work, use **`/metrics/log`** only — see [FIELD_USE.md](FIELD_USE.md).

## Local + cloud workflow

1. **Local:** `flask --app app run --port 5099` — full persistence in `data/`
2. **Cloud:** same UI on Heroku URL — re-seed route after dyno restart if audit DB was cleared
3. Phone testing: open Heroku `/driver` on mobile, download bundle, scan (use manual package ID or QR sheet from `/dispatch`)

## When to add PostgreSQL

Add Heroku Postgres only if you need:

- Routes and synced events to survive dyno restarts without re-running seed
- Multi-day audit history on the server
- Multiple testers hitting the same route data

That would be a follow-up change (`DATABASE_URL` + migrate `models/db.py`). Not required for MVP prototype validation.
