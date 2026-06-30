# AI agent instructions — lemma.id isHuman

You are helping a developer integrate **lemma.id proof of humanity** into their web platform.

## Read this first

**Canonical integration guide (follow it):**

https://lemma.id/docs/integration/ISHUMAN_AGENT_INTEGRATION.md

Or locally: `docs/integration/ISHUMAN_AGENT_INTEGRATION.md`

**Human-readable docs:** https://lemma.id/docs

**Pointer file:** https://lemma.id/llms.txt

## Product scope

- **In scope:** Browser SDK (`ishuman-verifier.js`), site-private PPIDs, local backend verification, optional site API keys for abuse controls.
- **Out of scope:** Agent Ops (lemma-cli, Lemma Firewall, runtime control plane) — operator-only, not for relying-site integration.

## Hard rules

1. `siteId` = canonical hostname (`app.example.com`), not internal `site_...` IDs.
2. Fail closed when `human` is false.
3. For signup/account creation, verify a signed `presentation` on the server — never trust a bare client `ppid`.
4. No customer webhooks, no wallet secret on the developer's backend, no KYC field storage.

## Quick integration

```html
<script src="https://lemma.id/sdk/ishuman-verifier.js"></script>
<script>
  const verifier = new IsHumanVerifier({ siteId: 'app.example.com' });
  const { ok, presentation } = await verifier.verifyForBackend({ autoProvision: true });
  if (!ok) throw new Error('not_verified');
  await fetch('/api/signup', { method: 'POST', body: JSON.stringify({ presentation }) });
</script>
```

Verify on the server with `@lemma/ishuman-verify` or `lemma_ishuman_verify.py`.

See the full guide for trust tiers, abuse APIs, anti-patterns, and framework notes.

## Platform operator identity (lemma.id internal)

Platform operators use the **same wallet + isHuman flow** as all users. Admin/operator access is an additional lemma.id-scoped permission proof, not a separate identity path.

- Runtime site binding key: normalized hostname (`lemma.id` for the platform).
- Internal `site_...` ids are ownership/database context only — never the sole runtime credential match key.
- Platform operator = complete lemma.id identity proof + `admin_access` permission bound to `lemma.id`.
- Canonical admin permission id: `admin_access` (preserve requested level separately as `permission_level`).
- Skip empty site fields before strict canonicalization; sparse master credentials are valid.

Contract doc: `docs/product/LEMMA_ID_PRESENTATION_MODEL.md`

## Cursor Cloud specific instructions

Durable, non-obvious notes for running this repo in the Cloud Agent VM. Standard
commands live in `README.md`, `Procfile`, `docker-compose.yml`, and
`scripts/ci_regression_suite.py`; this section only captures the gotchas.

### Services & how to run them
- **Platform API** (`app.py`, the core product: wallet UI + isHuman + IAM + dashboards).
  Run from the venv after starting Postgres/Redis and sourcing env:
  `set -a && . ./.env && set +a && .venv/bin/gunicorn app:app --worker-class gevent --workers 2 --bind 0.0.0.0:5000`
  (or `.venv/bin/python app.py`). Serves on `:5000`. Health: `/health` (needs DB),
  readiness: `/ready` (checks `database` + `crypto`).
- **PostgreSQL** and **Redis** are installed in the VM image, not auto-started. Start them with
  `sudo pg_ctlcluster 16 main start` and `sudo service redis-server start`. DB role/name are `lemma`/`lemma`.

### Non-obvious caveats
- **Use the project venv `.venv` (Python 3.12).** Deps are NOT installed into system Python.
- **The app does NOT auto-load `.env`** (no `load_dotenv` outside Flask CLI). Always
  `set -a && . ./.env && set +a` before running the app, migrations, or scripts. `.env` is
  git-ignored and lives in the repo root.
- **DB schema bootstrap:** the `migrations/` chain assumes a pre-existing `sites` table and
  is NOT standalone-runnable on a fresh Postgres DB; `database_schema.sql` is MySQL-flavored
  (inline `INDEX ...`) and will not apply to Postgres. Bootstrap the schema with the SQLAlchemy
  models instead: `from api.database import create_tables; create_tables()` (creates all ~38 tables).
- **Local Postgres must offer SSL** because `api/database.get_db_connection` connects with
  `sslmode='require'`. Ubuntu's default Postgres has `ssl=on` (snakeoil cert), so it works out of the box.
- **`lemma_crypto` (Rust) needs a modern toolchain.** `Cargo.lock` pins `base64ct 1.8` which
  requires Rust edition2024 (Cargo ≥1.85). The VM uses `rustup default stable` (1.96+); the
  stock 1.83 toolchain fails to build it.
- **External-only flows (cannot complete locally without secrets):** full isHuman *credential
  issuance* hard-requires AWS KMS (`LEMMA_KMS_KEY_ID` + AWS creds) via `api/issuer_management.py`,
  and the standard IDV path requires the Didit provider. The Didit-free "skeleton" demo flow
  creates a pending `ishuman_verifications` row but still fails at KMS when minting the credential.
  KMS-free core flows that DO work end-to-end: wallet signing-key registration, Ed25519
  `wallet_assertion` verification, the cross-device `sync-device` relay, and demo-site provisioning.

### Tests / lint
- Canonical bundle: `.venv/bin/python scripts/ci_regression_suite.py` (it forces
  `DATABASE_URL=sqlite:///:memory:` and dummy identity-root env vars; needs `pytest` installed in the venv).
  This also runs the static "lint" gate (CSP test + auth-scope matrix review). There is no
  separate linter (no ruff/flake8/black config).
- A handful of tests fail on a clean checkout due to pre-existing repo drift (e.g.
  `test_wallet_sdk_static_and_cdn_version_match` — committed SDK version mismatch; a couple of
  `test_ishuman_demo` expectation mismatches). These are unrelated to environment setup.
