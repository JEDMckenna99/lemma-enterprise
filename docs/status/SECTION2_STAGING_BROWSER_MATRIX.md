# Section 2 Staging Browser Matrix

Manual evidence gate for wallet authority ceremonies after deploying
`cursor/human-auth-production-checklist-1658` to staging.

Pair with the API smoke:

```bash
export LEMMA_STAGING_BASE_URL=https://<staging-app>.herokuapp.com
LEMMA_DEPLOY_WAIT=1 python scripts/run_section2_staging_matrix.py
```

## Deploy the branch to staging

Staging app: **`lemma-staging`**.

From a machine with Heroku auth (or a Cloud Agent with `HEROKU_API_KEY` set):

```bash
git fetch origin cursor/human-auth-production-checklist-1658
git checkout cursor/human-auth-production-checklist-1658

# one-time remote
heroku git:remote -a lemma-staging -r staging

# deploy feature branch tip to staging
git push staging HEAD:main --force

export LEMMA_STAGING_BASE_URL=https://lemma-staging.herokuapp.com
LEMMA_BASE_URL="$LEMMA_STAGING_BASE_URL" python scripts/wait_for_deploy_health.py
LEMMA_DEPLOY_WAIT=1 python scripts/run_section2_staging_matrix.py
```

If the app uses a custom domain, set `LEMMA_STAGING_BASE_URL` to that HTTPS origin instead.

Confirm staging is **not** production:

- `ENVIRONMENT=staging`
- demo/test verify may be enabled
- Didit sandbox credentials

Do **not** force-push this branch to the production Heroku app.

## Browser matrix

Record pass/fail, browser + OS, staging URL, commit SHA, and screenshots/logs
for each row.

| # | Ceremony | Steps | Chrome | Safari | Firefox | Notes |
|---|---|---|---|---|---|---|
| 1 | First-device enroll | Open staging unlock/wallet → create new wallet → passkey create succeeds → server `device-enroll` completes → session cookie issued |  |  |  | Confirm network: `/api/wallet/device-enroll/begin` + `/complete`, then `/session-unlock/*` |
| 2 | Daily unlock | Reload / return next day or clear local unlock bundle → passkey get → `/session-unlock` issues session |  |  |  | Knowing only `wallet_id` must not unlock |
| 3 | CSRF refresh | With valid session, call refresh/clear without `X-Lemma-CSRF` → denied; with matching CSRF → ok |  |  |  | Use DevTools or SDK paths for signal-unlock / clear-session |
| 4 | Additional device | From enrolled device, create QR/link transfer → claim on second browser/profile → enroll new signing key with grant |  |  |  | Second device without grant must fail |
| 5 | Cross-device revoke | From device A, revoke device B → WebAuthn prompt required → B can no longer assert |  |  |  | Self-revoke of current device does not require the cross-device challenge |
| 6 | Lost-device recovery | Established wallet, no usable device → start IDV with `purpose=lost_device_recovery` → authorize → enroll replacement passkey → prior devices revoked |  |  |  | Staging may use Didit sandbox / demo test-complete |
| 7 | Relying-site session | From a third-party origin allowed in staging CORS, credentialed session-sync/read paths behave; mutations still CSRF-gated on lemma origin |  |  |  | One demo relying site is enough |

## Negative checks (any one browser)

- [ ] `POST /api/wallet/register-signing-key` without ceremony → `first_device_webauthn_enrollment_required`
- [ ] `POST /api/wallet/init-first-session` → HTTP 410
- [ ] Stolen/forged Origin on lemma-bound enroll/unlock → 403
- [ ] Replayed enroll/unlock/recovery challenge → denied
- [ ] Lost-device authorize with unknown/unverified IDV session → 403

## Evidence to attach

- Staging app name + base URL
- Deployed commit SHA (`git rev-parse HEAD` at deploy time)
- API matrix transcript from `run_section2_staging_matrix.py`
- Filled table above with dates
- Optional screenshots of enroll, unlock, transfer, revoke, recovery

When the API matrix and browser table are complete, update Section 2 evidence in
`docs/status/HUMAN_BACKED_AUTHENTICATOR_PRODUCTION_READINESS.md` and keep Section 1
blocked until independent threat-model sign-off.
