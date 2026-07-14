# Local/Staging DevOps Workflow

This workflow keeps local development, Heroku staging, and production consistent without copying live secrets into local files.

## Environment Tiers

Use three separate tiers:

- **Local**: `.env.local`, local database/Redis, Didit sandbox credentials (or skeleton IDV), optional tunnel for Didit webhooks.
- **Staging Heroku**: dedicated Heroku app, Heroku Postgres/Redis, Didit sandbox, public HTTPS webhooks.
- **Production Heroku**: production Heroku app, production Postgres/Redis, Didit production workflow, test helpers disabled.

Do not commit real `.env` files. The tracked examples are:

- `.env.local.example`
- `.env.staging.example`
- `.env.production.example`

## Local Setup

1. Copy the local template:

```powershell
Copy-Item .env.local.example .env.local
```

2. Fill in local values:

- `SECRET_KEY`
- `LEMMA_PPID_ROOT_KEY`
- `DATABASE_URL`
- `REDIS_URL`
- `LEMMA_ISHUMAN_DIDIT_ENABLED=true`
- `DIDIT_API_KEY`
- `DIDIT_WORKFLOW_ID`
- `DIDIT_WEBHOOK_SECRET`
- `LEMMA_ISHUMAN_DEMO_TEST_TOKEN`
- `LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN`

Optional legacy Stripe keys (migration recovery only):

- `STRIPE_SECRET_KEY=sk_test_...`
- `STRIPE_IDENTITY_WEBHOOK_SECRET=whsec_...`

3. Validate local config:

```powershell
python scripts/check_env_parity.py --environment local --env-file .env.local
```

## Didit Webhooks

For local webhook testing, expose the local app through a tunnel and point Didit webhooks at:

```text
https://<tunnel-host>/api/webhooks/didit-identity
```

For staging, point Didit webhooks at:

```text
https://<staging-app>.herokuapp.com/api/webhooks/didit-identity
```

Production webhooks:

```text
https://lemma.id/api/webhooks/didit-identity
```

### Legacy Stripe webhooks (migration only)

If you still need Stripe document-root recovery on a staging app, optionally point Stripe test-mode webhooks at `/api/webhooks/stripe-identity`. Do not use Stripe as the primary IDV rail for new demos.

## Heroku Staging Setup

Create or use a staging Heroku app, then set config from `.env.staging.example` using real staging/test values:

```powershell
heroku config:set ENVIRONMENT=staging -a <staging-app>
heroku config:set FLASK_ENV=production -a <staging-app>
heroku config:set LEMMA_ISHUMAN_DIDIT_ENABLED=true -a <staging-app>
heroku config:set DIDIT_API_KEY=... -a <staging-app>
heroku config:set DIDIT_WORKFLOW_ID=... -a <staging-app>
heroku config:set DIDIT_WEBHOOK_SECRET=... -a <staging-app>
heroku config:set LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY=true -a <staging-app>
heroku config:set LEMMA_ISHUMAN_DEMO_TEST_TOKEN=<random-token> -a <staging-app>
```

Validate staging config:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_heroku_env_parity.ps1 -AppName <staging-app> -Environment staging -LocalEnvFile .env.local
```

## Production Guardrails

Production must use live Didit credentials and must not enable automated demo completion:

```text
ENVIRONMENT=production
LEMMA_ISHUMAN_DIDIT_ENABLED=true
DIDIT_API_KEY=...
DIDIT_WORKFLOW_ID=...
LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY=false
```

Validate production config before deployment:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_heroku_env_parity.ps1 -AppName <production-app> -Environment production
```

The validator fails production if:

- `LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY` is enabled
- `ENVIRONMENT` is not `production`
- HTTPS URLs are missing
- deployed config contains placeholder values

To sanity-check tracked templates without treating placeholders as deployable values:

```powershell
python scripts/check_env_parity.py --environment staging --env-file .env.staging.example --allow-placeholders
python scripts/check_env_parity.py --environment production --env-file .env.production.example --allow-placeholders
```

## isHuman Demo Validation

Run locally or on staging:

1. Open `https://lemma.id/demo` (alias: `/demo/ishuman` on staging).
2. Create or unlock the wallet.
3. Start the Didit IDV flow (or use skeleton/test-verify on non-production).
4. In test mode on staging, enter `LEMMA_ISHUMAN_DEMO_TEST_TOKEN` and click **Test mode: complete verification**.
5. Poll and store the master proof.
6. Verify the ticketing and free-trial demo sites.
7. Block the ticketing PPID and confirm free trial still passes.

Site-block is the supported enforcement drill. Network-wide revocation is retired (HTTP 410 `network_revocation_retired`).

## Recommended Pre-Demo Checks

```powershell
python scripts/check_env_parity.py --environment local --env-file .env.local
python -m pytest tests/test_ishuman_demo.py -q
python -m pytest tests/test_ishuman_network_regressions.py tests/test_ishuman_ppid_normalization.py tests/test_ishuman_issuance_branching.py tests/test_ishuman_issuance_integration.py tests/test_wallet_bridge_ishuman_flow.py tests/test_ishuman_demo.py -m "unit or integration or browser or not live_stripe" -q
```

For staging:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_heroku_env_parity.ps1 -AppName <staging-app> -Environment staging -LocalEnvFile .env.local
powershell -ExecutionPolicy Bypass -File scripts/post_deploy_launch_gate.ps1 -BaseUrl https://<staging-app>.herokuapp.com
```
