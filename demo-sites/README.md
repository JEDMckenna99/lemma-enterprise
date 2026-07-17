# isHuman Relying-Site Demo Apps

These tiny Flask apps simulate real third-party relying sites for the isHuman demo.

Each app serves one page that loads:

```html
<script src="https://lemma.id/sdk/proof-verifier.js"></script>
```

## Expected Heroku Apps

- `lemma-demo-tickets`, **unique presale code distributor reference**
  - `LEMMA_DEMO_SITE_ID=tickets-demo.lemma.id`
  - `LEMMA_DEMO_SITE_NAME=Lemma Ticketing Demo`
  - `LEMMA_DEMO_SITE_KIND=ticketing`
  - `LEMMA_PRESALE_DROP_ID=artist-presale-2026` (optional)
  - `LEMMA_PRESALE_CODE_CLAIM_ASSURANCE=passkey` (default; optional)
  - `LEMMA_PRESALE_ESCALATED_ASSURANCE=ishuman` (optional, IDV penalty on site doubt)
  - `LEMMA_PRESALE_SQLITE_PATH=/tmp/presale.db` (optional, persistent ledger across restarts)
- `lemma-demo-trials`
  - `LEMMA_DEMO_SITE_ID=trials-demo.lemma.id`
  - `LEMMA_DEMO_SITE_NAME=Lemma Free Trial Demo`
  - `LEMMA_DEMO_SITE_KIND=free trial`

## Presale reference flow (tickets demo)

Low-friction passkey proof by default; fresh IDV only when the site flags a fan.

**Guided tour:** `/?tour=presale`

**Step 0, Server challenge**

1. `POST /api/presale/challenge` with action, method, path, and body.
2. Server returns `server_nonce` and `action_commitment`.

**Step 1, Passkey register**

1. Fan enters email and phone on the relying site (site-local only).
2. Browser calls `stampAction(payload, { action: 'register_presale', nonce: server_nonce, requiredAssurance: 'passkey' })`.
3. `POST /api/presale/register` with stamped body + `server_nonce`.
4. Server verifies action stamp (strict nonce), stores `(drop_id, ppid)` registration.

**Step 2, Fresh passkey code unlock**

1. Browser calls `stampAction(payload, { action: 'claim_presale_code', requireFreshPasskey: true, serverNonce, requiredAssurance: 'passkey' })`.
2. `POST /api/presale/claim-code` with stamped body + `server_nonce`.
3. Server verifies action stamp + `fresh_passkey_attestation`, enforces policy, requires prior registration, then claims against the site-local ledger keyed by `(drop_id, ppid)`.
4. First claim returns an 8-digit code; a second claim with the same PPID is denied with `allocation_already_claimed`.

**Status lookup (presentation-protected)**

- `POST /api/presale/status` with signed presentation, no GET leak of codes.

**Risk flag escalation (demo penalty path)**

1. Site flags PPID (`POST /api/demo/policy/doubt`).
2. Passkey claim returns `doubt_required` with `escalation: fresh_idv`.
3. Browser runs `verifyFreshForBackend({ requiredAssurance: 'ishuman' })`, then retries claim at `ishuman` assurance.
4. Successful escalated claim clears the doubt flag for that PPID.

Copy-paste modules:

- [`presale_allocation.py`](presale_allocation.py), registration store + in-memory `(drop_id, ppid)` ledger
- [`relying_site_app.py`](relying_site_app.py), presale challenge, register, claim, and status APIs

Sales script: [`docs/demo/PRESALE_DEMO_SCRIPT.md`](../docs/demo/PRESALE_DEMO_SCRIPT.md)

## Deploy

From the repository root:

```powershell
git subtree push --prefix demo-sites https://git.heroku.com/lemma-demo-tickets.git main
git subtree push --prefix demo-sites https://git.heroku.com/lemma-demo-trials.git main
```

After deploy, verify https://tickets-demo.lemma.id/?tour=presale
