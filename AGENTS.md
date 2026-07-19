# AI agent instructions: lemma.id

You are helping a developer integrate **lemma.id human proofs** into their web platform. **isHuman** is an optional assurance tier sites can require, not the product name.

## Read this first

**Canonical integration guide (follow it):**

https://lemma.id/docs/integration/ISHUMAN_AGENT_INTEGRATION.md

Or locally: `docs/integration/ISHUMAN_AGENT_INTEGRATION.md`

**Human-readable docs:** https://lemma.id/docs

**Pointer file:** https://lemma.id/llms.txt

Or locally: `llms.txt`

## Product scope

- **In scope:** Browser SDK (`proof-verifier.js`), site-private PPIDs, local backend verification, optional site API keys for abuse controls.
- **Out of scope:** Agent Ops (lemma-cli, Lemma Firewall, runtime control plane), operator-only, not for relying-site integration.

## Hard rules

1. `siteId` = canonical hostname (`app.example.com`), not internal `site_...` IDs.
2. Fail closed when `human` is false.
3. For signup/account creation, verify a signed `presentation` on the server, never trust a bare client `ppid`.
4. No customer webhooks, no wallet secret on the developer's backend, no KYC field storage.

## Quick integration

```html
<script src="https://lemma.id/sdk/proof-verifier.js"></script>
<script>
  const verifier = new ProofVerifier({ siteId: 'app.example.com' });
  const { ok, presentation } = await verifier.verifyForBackend({ autoProvision: true });
  if (!ok) throw new Error('not_verified');
  await fetch('/api/signup', { method: 'POST', body: JSON.stringify({ presentation }) });
</script>
```

The legacy `ishuman-verifier.js` URL and `IsHumanVerifier` class remain supported
as compatibility aliases.

Verify on the server with `@lemma/ishuman-verify` or `lemma_ishuman_verify.py`.

See the full guide for trust tiers, abuse APIs, anti-patterns, and framework notes.

## Platform operator identity (lemma.id internal)

Platform operators use the **same wallet + isHuman flow** as all users. Admin/operator access is an additional lemma.id-scoped permission proof, not a separate identity path.

- Runtime site binding key: normalized hostname (`lemma.id` for the platform).
- Internal `site_...` ids are ownership/database context only, never the sole runtime credential match key.
- Platform operator = complete lemma.id identity proof + `admin_access` permission bound to `lemma.id`.
- Canonical admin permission id: `admin_access` (preserve requested level separately as `permission_level`).
- Skip empty site fields before strict canonicalization; sparse master credentials are valid.

Contract doc: `docs/product/LEMMA_ID_PRESENTATION_MODEL.md`

## Cursor Cloud specific instructions

Python deps live in a venv at `/workspace/venv` (gitignored). Prefix commands with
`./venv/bin/...`. The startup update script keeps this venv installed (see
`requirements.txt` + `pytest`). System deps (PostgreSQL 16, Redis, gcc, Rust
toolchain) are provided by the VM snapshot, not the update script.

- **Rust toolchain**: the native `lemma-crypto` extension pins `base64ct` which
  requires Cargo `edition2024` (Rust >= 1.85). The default `rustup` stable is set
  accordingly; do not downgrade below 1.85 or `pip install -r requirements.txt`
  (which builds the extension) will fail.
- **Services are not auto-started on boot** (no systemd). Start them before
  running the app or the DB-backed tests:
  - Postgres: `sudo pg_ctlcluster 16 main start`
  - Redis: `sudo redis-server --daemonize yes`
  - Dev role/DB (idempotent): role `lemma`/pw `lemma`, database `lemma`
    (`postgresql://lemma:lemma@localhost:5432/lemma`).
- **Env vars are NOT auto-loaded** (the app reads `os.environ` directly; nothing
  calls `load_dotenv`). Export them before running, e.g. `set -a && . ./.env.local
  && set +a`. `.env.local` is a gitignored dev file; in development
  (`FLASK_ENV=development`) `api/config.py` auto-generates all required secrets, so
  only `DATABASE_URL`/`REDIS_URL` really matter.
- **Schema creation**: for a fresh dev DB use SQLAlchemy models, not the numbered
  SQL migrations. Run `python -c "from api.database import init_database;
  init_database()"` (creates all ~45 tables). `migrations/run_migration.py`
  assumes the base `sites` table already exists and fails on an empty DB at
  migration 002.
- **Run the app (dev)**: `python app.py` serves on `0.0.0.0:5000` (`/health`
  returns `{"status":"healthy"}` only when Postgres is reachable). Prod uses
  `gunicorn app:app ...` per `Procfile`.
- **Tests**: designed to run against in-memory SQLite. Use
  `python scripts/ci_regression_suite.py`, or run pytest directly with the CI env
  from `.github/workflows/ci-regression.yml` (`DATABASE_URL=sqlite:///:memory:`
  plus the `LEMMA_*` test secrets). `pytest` is a test-only dep (installed by the
  update script; also listed in `scripts/ci_install_test_deps.sh`), not in
  `requirements.txt`.
- **isHuman credential issuance requires AWS KMS** (`api/issuer_management.py`
  fails closed without it). Provide `LEMMA_KMS_KEY_ID` (KMS key ARN) plus
  `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` as VM secrets to enable it. Gotcha:
  `api/kms_manager.py` defaults `AWS_REGION` to `us-east-1`, so if the key ARN is
  in another region you must set `AWS_REGION` to match (derive it from the ARN,
  e.g. `arn:aws:kms:<region>:...`) or KMS calls fail. With those set, the full
  flow works end to end: `POST /api/demo/ishuman/skeleton-idv-flow`
  (`X-Demo-Test-Token`) issues a real KMS-signed master credential, and
  `POST /api/ishuman/verify-presentation` verifies it (the federated issuer is
  auto-trusted, see `api/trusted_issuers.py`).
- **Verification alone does not need KMS.** To exercise
  `POST /api/ishuman/verify-presentation` without KMS, mint a credential with a
  dev `lemma_crypto.PyMinimalIssuer.from_seed` and trust its DID via
  `TRUSTED_ISSUER_DIDS`.
