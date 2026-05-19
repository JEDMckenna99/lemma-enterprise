# isHuman Production Revocation Smoke

## One-time: create test wallet secret

Generate a 64-character hex secret locally (do not commit):

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Set on Heroku:

```bash
heroku config:set \
  LEMMA_ISHUMAN_PROD_TEST_WALLET_ID=wallet_ishuman_prod_fixture \
  LEMMA_ISHUMAN_PROD_TEST_WALLET_SECRET=<your_hex_secret> \
  LEMMA_ISHUMAN_PROD_TEST_TARGET_SITE=tickets-demo.lemma.id \
  LEMMA_ISHUMAN_PROD_TEST_SITE_ID=site_demo_tickets \
  -a lemma-enterprise
```

`LEMMA_ISHUMAN_DEMO_TEST_TOKEN` and `LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY=true` must already be set for provisioning.

## Provision verified master + site derivation

```bash
export LEMMA_ISHUMAN_PROD_TEST_WALLET_SECRET=<your_hex_secret>
export LEMMA_ISHUMAN_DEMO_TEST_TOKEN=<from heroku config>
python scripts/provision_ishuman_prod_test_wallet.py --base-url https://lemma.id --print-secret
```

Save manifest values to Heroku (recommended):

```bash
heroku config:set \
  LEMMA_ISHUMAN_PROD_TEST_MASTER_CREDENTIAL_ID=<from manifest> \
  LEMMA_ISHUMAN_PROD_TEST_SITE_PPID=<from manifest> \
  -a lemma-enterprise
```

`SITE_PPID` must come from prod provisioning — do not derive locally unless `LEMMA_PPID_ROOT_KEY` matches production.

## Run revocation smoke

```bash
export LEMMA_ISHUMAN_PROD_TEST_WALLET_SECRET=<your_hex_secret>
python scripts/run_ishuman_prod_revocation_smoke.py --base-url https://lemma.id
```

Requires Heroku CLI logged in (loads `site_demo_tickets` API key from prod DB) unless `LEMMA_ISHUMAN_PROD_TEST_SITE_API_KEY` is set.
