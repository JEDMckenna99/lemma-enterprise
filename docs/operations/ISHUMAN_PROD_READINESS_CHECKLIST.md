# isHuman Production Readiness Checklist

Use this checklist to move isHuman from "deployed code" to "operationally live service" on `https://lemma.id`.

## 0) Release Metadata

- [ ] **Release SHA recorded**
  - Value: `________________`
- [ ] **Heroku release recorded**
  - Value: `v_____`
- [ ] **Operator + date recorded**
  - Value: `________________`

## 1) Production Config Integrity

- [ ] **Stripe live key present**
  - Check: `heroku config:get STRIPE_SECRET_KEY -a lemma-enterprise`
- [ ] **Identity webhook secret present**
  - Check: `heroku config:get STRIPE_IDENTITY_WEBHOOK_SECRET -a lemma-enterprise`
- [ ] **isHuman runtime defaults validated**
  - Check:
    - `heroku config:get ISHUMAN_CREDENTIAL_TTL_DAYS -a lemma-enterprise`
    - `heroku config:get ISHUMAN_RETURN_URL -a lemma-enterprise`
- [ ] **Person-root secrets configured**
  - `heroku config:get LEMMA_IDENTITY_ROOT_PEPPER_V1 -a lemma-enterprise`
  - `heroku config:get LEMMA_PERSON_ROOT_SALT_V1 -a lemma-enterprise`
  - `heroku config:get STRIPE_IDENTITY_RESTRICTED_KEY -a lemma-enterprise` (or restricted key with sensitive Identity read)
- [ ] **No accidental local-only overrides in prod**
  - Check key set for suspicious values (`localhost`, dev secrets, etc.)

## 2) Stripe Webhook Wiring

- [ ] **Webhook endpoint configured in Stripe**
  - URL: `https://lemma.id/api/webhooks/stripe-identity`
- [ ] **Required event subscriptions enabled**
  - `identity.verification_session.verified`
  - `identity.verification_session.requires_input`
  - `identity.verification_session.canceled`
- [ ] **Recent deliveries are successful (2xx)**
  - Evidence: screenshot/export from Stripe dashboard
- [ ] **Signature verification succeeds in app logs**
  - Check logs:
    - `heroku logs -a lemma-enterprise --tail`
    - Look for absence of repeated `invalid_signature` on valid deliveries

## 3) Runtime Endpoint Health

- [ ] **Core app healthy**
  - `curl https://lemma.id/api/health`
- [ ] **isHuman stats endpoint healthy**
  - `curl https://lemma.id/api/ishuman/stats`
- [ ] **isHuman check endpoint healthy**
  - `curl "https://lemma.id/api/ishuman/check?ppid=did:lemma:ppid_smoke"`
- [ ] **SDK is served**
  - `curl -I https://lemma.id/sdk/ishuman-verifier.js`

## 4) End-to-End Verification Flow (Live)

- [ ] **Start verification succeeds**
  - Endpoint: `POST /api/ishuman/start-verification`
  - Expect: `success=true`, `session_id`, `stripe_session_id`, `client_secret`
- [ ] **Stripe verification completes**
  - Perform one live verification in production UI
- [ ] **Webhook updates internal session record**
  - Confirm status transitions to `verified`
- [ ] **Verification status poll returns credential payload**
  - Endpoint: `GET /api/ishuman/verification-status/<session_id>`
- [ ] **Wallet stores master isHuman proof**
  - Confirm credential visible in wallet/bridge storage path

## 5) Per-Site Derivation Path

- [ ] **Derived site proof created on first third-party request**
  - Endpoint: `POST /api/ishuman/derive-site-proof`
- [ ] **Derived proof binds to normalized site hostname**
  - Validate claim binding (`siteId`/domain semantics)
- [ ] **Subsequent request returns cached derivation path**
  - Expect id continuity for same master+site tuple

## 6) Revocation Controls Drill

- [ ] **Site block works (tier 1)**
  - `POST /api/ishuman/site-block`
  - `GET /api/ishuman/check` returns `blocked=true`, `reason=site_block`
- [ ] **Network revoke request works (tier 2 request)**
  - `POST /api/ishuman/network-revoke` returns pending state
- [ ] **Admin approval path works**
  - `POST /api/ishuman/approve-revocation` with admin credential
- [ ] **Bloom/revocation propagation confirmed**
  - Client verifier denies revoked identity
  - `reason=revoked` in verifier result path

## 7) Security + Abuse Gates

- [ ] **Rate limiting validated on verification start**
  - Burst test does not permit unbounded requests
- [ ] **No fail-open on verification session persistence**
  - Simulate DB failure in staging; ensure endpoint returns failure
- [ ] **PPID derivation semantics confirmed**
  - Verified isHuman credentials use `ppidDerivation=person_root_v1` (document-root → lemma person root → site PPID)
  - Legacy wallet-secret PPIDs still accepted for pre-migration credentials only
  - Stripe Identity sessions redacted per retention policy after root material is derived (no raw DOB/document number stored server-side)
- [ ] **CORS/origin behavior checked for isHuman endpoints**
  - No credentialed permissive responses for disallowed origins

## 8) Monitoring + Alerting

- [ ] **Alerts configured**
  - Webhook failures / signature failures
  - Verification session persist failures
  - Derivation failures (`derive-site-proof`)
  - Revocation publish/sync failures
- [ ] **Dashboards configured**
  - Total verifications/day
  - Verification success rate
  - Site blocks and network revocations
  - Error-rate by isHuman endpoint
- [ ] **Runbook owner assigned**
  - Owner: `________________`

## 9) Compliance / Legal / Support Readiness

- [ ] **Privacy policy updated for isHuman data handling**
- [ ] **Terms updated for identity verification + enforcement model**
- [ ] **Retention/deletion policy documented**
- [ ] **Support playbook for failed verifications published**

## 10) Customer Launch Enablement

- [ ] **Integration guide published**
  - SDK script usage + callback expectations
- [ ] **Operator integration checklist published**
  - API key provisioning, block/revoke usage, evidence requirements
- [ ] **Known limitations and SLAs documented**

## 11) Evidence Bundle (Required for GA)

Store evidence under `ops/evidence/launch/ishuman/`:

- [ ] `ishuman-health-<timestamp>.txt`
- [ ] `ishuman-e2e-verification-<timestamp>.md`
- [ ] `ishuman-revocation-drill-<timestamp>.md`
- [ ] `ishuman-webhook-deliveries-<timestamp>.png|md`
- [ ] `ishuman-alert-routing-test-<timestamp>.md`

## Exit Criteria

Only mark isHuman "service live" when all sections above are green or have explicit, accepted risk waivers with owner/date.
