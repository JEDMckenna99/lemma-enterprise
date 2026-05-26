# ISHUMAN Issuance Test Runbook

This runbook covers the test suite that validates ISHUMAN issuance behavior:

- Master proof exists -> derive/store site-specific proof.
- Master proof missing -> create/store master, then derive/store site-specific proof.
- Cross-site bootstrap from any `lemma.id`-integrated customer site.

## Test Modules

- `tests/conftest.py`
  - Shared fixtures, seeded record factories, and fake DB session harness.
- `tests/test_ishuman_network_regressions.py`
  - Existing regressions retained.
- `tests/test_ishuman_ppid_normalization.py`
  - Canonicalization and PPID determinism coverage.
- `tests/test_identity_roots.py`
  - Stripe document-root canonicalization, person-root PPID stability, and DB link reuse.
- `tests/test_ishuman_person_root_derivation.py`
  - `derive-site-proof` uses person-root PPIDs when master is linked to `lemma_person_id`.
- `tests/test_ishuman_issuance_branching.py`
  - Branching behavior (cache hit/miss, master bootstrap path).
- `tests/test_ishuman_issuance_integration.py`
  - Route-level start/webhook/status/derive integration.
- `tests/test_wallet_bridge_ishuman_flow.py`
  - Wallet bridge contract tests for cross-site flow and site binding gates.
- `tests/live/test_ishuman_live_stripe_issue_flow.py`
  - Live Stripe sandbox integration tests.

## Markers

Defined in `pytest.ini`:

- `unit`
- `integration`
- `browser`
- `live_stripe`

## Local Commands

Run non-live suite:

```bash
python -m pytest \
  tests/test_ishuman_network_regressions.py \
  tests/test_identity_roots.py \
  tests/test_ishuman_ppid_normalization.py \
  tests/test_ishuman_person_root_derivation.py \
  tests/test_ishuman_issuance_branching.py \
  tests/test_ishuman_issuance_integration.py \
  tests/test_wallet_bridge_ishuman_flow.py \
  -m "unit or integration or browser" -v
```

Run live Stripe suite:

```bash
python -m pytest tests/live/test_ishuman_live_stripe_issue_flow.py -m live_stripe -v
```

## Live Stripe Environment

Required:

- `ISHUMAN_LIVE_BASE_URL`
- `ISHUMAN_LIVE_WALLET_ID`

Optional but recommended:

- `ISHUMAN_LIVE_WALLET_SECRET`
- `ISHUMAN_LIVE_MASTER_CREDENTIAL_ID`
- `ISHUMAN_LIVE_TARGET_SITE` (default: `customer-live.example`)
- `ISHUMAN_LIVE_VERIFY_TIMEOUT_SECONDS` (default: `300`)
- `ISHUMAN_LIVE_VERIFY_POLL_SECONDS` (default: `5`)

Behavior:

- If `ISHUMAN_LIVE_MASTER_CREDENTIAL_ID` is present, tests skip master issuance bootstrap and directly test derivation.
- If not present, tests start verification and poll `verification-status` until verified.
- If the session does not become verified before timeout, tests skip with guidance rather than fail due to external/manual gating.

## CI Workflows

- `.github/workflows/ishuman-issuance-tests.yml`
  - Runs non-live ISHUMAN suite on PR and push (relevant path filters).
- `.github/workflows/ishuman-live-stripe.yml`
  - Runs live Stripe suite on schedule and manual dispatch.

## Failure Triage

- `master_credential_not_found` in derive tests:
  - Verify webhook completed and persisted `credential_id` in `ishuman_verifications`.
- `wallet_revoked` unexpectedly:
  - Inspect `revocation_list` for wallet-level revocation rows in test fixtures or environment data.
- Live suite times out waiting for `verified`:
  - Confirm sandbox webhook delivery, endpoint reachability, and session completion flow.
- Site mismatch in bridge checks:
  - Confirm `target_site` normalization and binding values (`siteId`, `siteDomain`) are consistent.

## Guardrails Validated

- Site identity is treated separately from internal ownership IDs.
- Per-site derivation uses normalized target site input.
- Issuance flow fails closed when required context is missing or revoked.
