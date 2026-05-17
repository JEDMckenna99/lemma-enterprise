# Local/Staging DevOps Workflow

This workflow keeps local development, Heroku staging, and production consistent without copying live secrets into local files.

## Environment Tiers

Use three separate tiers:

- **Local**: `.env.local`, local database/Redis, Stripe test keys, optional tunnel for Stripe webhooks.
- **Staging Heroku**: dedicated Heroku app, Heroku Postgres/Redis, Stripe test keys, public HTTPS webhooks.
- **Production Heroku**: production Heroku app, production Postgres/Redis, Stripe live keys, test helpers disabled.

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
- `STRIPE_SECRET_KEY=sk_test_...`
- `STRIPE_IDENTITY_WEBHOOK_SECRET=whsec_...`
- `LEMMA_ISHUMAN_DEMO_TEST_TOKEN`
- `LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN`

3. Validate local config:

```powershell
python scripts/check_env_parity.py --environment local --env-file .env.local
```

## Stripe Test Webhooks

For local webhook testing, expose the local app through a tunnel and point Stripe test-mode webhooks at:

```text
https://<tunnel-host>/api/webhooks/stripe-identity
```

Subscribe to:

- `identity.verification_session.verified`
- `identity.verification_session.requires_input`
- `identity.verification_session.canceled`

For staging, point Stripe test-mode webhooks at:

```text
https://<staging-app>.herokuapp.com/api/webhooks/stripe-identity
```

Keep production webhooks separate and live-mode only:

```text
https://lemma.id/api/webhooks/stripe-identity
```

## Heroku Staging Setup

Create or use a staging Heroku app, then set config from `.env.staging.example` using real staging/test values:

```powershell
heroku config:set ENVIRONMENT=staging -a <staging-app>
heroku config:set FLASK_ENV=production -a <staging-app>
heroku config:set STRIPE_SECRET_KEY=sk_test_... -a <staging-app>
heroku config:set STRIPE_IDENTITY_WEBHOOK_SECRET=whsec_... -a <staging-app>
heroku config:set LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY=true -a <staging-app>
heroku config:set LEMMA_ISHUMAN_DEMO_TEST_TOKEN=<random-token> -a <staging-app>
```

Validate staging config:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_heroku_env_parity.ps1 -AppName <staging-app> -Environment staging -LocalEnvFile .env.local
```

## Production Guardrails

Production must use live Stripe keys and must not enable automated demo completion:

```text
STRIPE_SECRET_KEY=sk_live_...
ENVIRONMENT=production
LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY=false
```

Validate production config before deployment:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_heroku_env_parity.ps1 -AppName <production-app> -Environment production
```

The validator fails production if:

- Stripe key is not `sk_live_...`
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

1. Open `/demo/ishuman`.
2. Create or unlock the wallet.
3. Start the Stripe Identity demo rail.
4. In test mode, enter `LEMMA_ISHUMAN_DEMO_TEST_TOKEN` and click **Test mode: complete verification**.
5. Poll and store the master proof.
6. Verify the ticketing and free-trial demo sites.
7. Block the ticketing PPID and confirm free trial still passes.
8. Optional: enter `LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN` and approve network revocation.

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
