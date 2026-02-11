# Code Remediation Evidence (2026-02-11)

This record captures launch-blocker code fixes completed in the repository and local validation results.

## Remediations Applied

### 1) Revocation data-path update (`P0-4`)

- File: `api/wallet_revocation.py`
- Change:
  - Removed deferred/TODO-only bloom update behavior in site revocation flow.
  - Added immediate local `sync_single_revocation(credential_id)` call after storing revocation.
  - Persist `bloom_filter_updated=True` when immediate sync succeeds.
- Intent:
  - Keep revocation data path current immediately after revocation write.

### 2) Passkey algorithm placeholder removal (`P0-5`)

- File: `api/passkey_auth.py`
- Change:
  - Added `_extract_passkey_algorithm()` to derive `credential.response.publicKeyAlgorithm` from registration payload.
  - Removed hardcoded `algorithm: -7` placeholder from registration complete response.
  - `wallet_storage.algorithm` is now derived value (or `null` if unavailable).
- Supporting client serialization updates:
  - `static/js/lemma-passkey.js`
  - `static/js/lemma-wallet.js`
  - `cdn/dist/js/lemma-wallet.js`
  - Added `response.publicKeyAlgorithm` to serialized attestation payload when supported by browser API.

### 3) Dynamic `innerHTML` risk reduction

- Files updated:
  - `templates/wallet_simple.html`
  - `templates/modern/docs_setup.html`
  - `templates/modern/index.html`
  - `templates/admin/sites.html`
  - `templates/admin/dashboard.html`
  - `static/js/lemma-wallet.js`
  - `cdn/dist/js/lemma-wallet.js`
- Change:
  - Replaced several dynamic HTML interpolations with DOM node creation and `textContent`.
  - Preserved UI behavior while reducing HTML injection surface.

## Validation

- Python syntax check passed:
  - `python -m py_compile api/passkey_auth.py api/wallet_revocation.py`
- TODO gap patterns no longer found:
  - `TODO: detect actual algorithm`
  - `TODO: Update bloom filter`
  - `Will be updated by background job`
- Production smoke check (current deployment) still passing:
  - `docs/launch-evidence/2026-02-11-post-fix-smoke-current-prod.txt`

## Remaining Limitation

- These code changes are repository-side until deployed.
- Production behavior for these specific fixes must be re-validated after deployment.

