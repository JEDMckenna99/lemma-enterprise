# isHuman Relying-Site Demo Apps

These tiny Flask apps simulate real third-party relying sites for the isHuman demo.

Each app serves one page that loads:

```html
<script src="https://lemma.id/sdk/ishuman-verifier.js"></script>
```

## Expected Heroku Apps

- `lemma-demo-tickets` — **unique presale code reference (Laylo RealFan-style)**
  - `LEMMA_DEMO_SITE_ID=tickets-demo.lemma.id`
  - `LEMMA_DEMO_SITE_NAME=Lemma Ticketing Demo`
  - `LEMMA_DEMO_SITE_KIND=ticketing`
  - `LEMMA_PRESALE_DROP_ID=artist-presale-2026` (optional)
  - `LEMMA_PRESALE_CODE_CLAIM_ASSURANCE=passkey` (default; optional)
  - `LEMMA_PRESALE_ESCALATED_ASSURANCE=ishuman` (optional — IDV penalty on site doubt)
- `lemma-demo-trials`
  - `LEMMA_DEMO_SITE_ID=trials-demo.lemma.id`
  - `LEMMA_DEMO_SITE_NAME=Lemma Free Trial Demo`
  - `LEMMA_DEMO_SITE_KIND=free trial`

## Presale reference flow (tickets demo)

Mirrors Laylo RealFan: low-friction passkey proof by default; fresh IDV only when the site flags a fan.

**Step 1 — Join presale**

1. Fan enters email and phone on the relying site (site-local only).
2. Browser calls `verifyForBackend({ requiredAssurance: 'passkey' })`.
3. Server verifies the presentation and stores `(drop_id, ppid)` registration.

**Step 2 — Unlock unique code**

1. Browser calls `stampAction({ drop_id, email, phone }, { action: 'claim_presale_code', requiredAssurance: 'passkey' })`.
2. Server verifies the action stamp, enforces site block/doubt policy, requires prior registration, then claims against the site-local ledger keyed by `(drop_id, ppid)`.
3. First claim returns an 8-digit code; a second claim with the same PPID is denied with `allocation_already_claimed`.

**Risk flag escalation (demo penalty path)**

1. Site flags PPID (`POST /api/demo/policy/doubt`) — simulates Laylo velocity/IP review.
2. Passkey claim returns `doubt_required` with `escalation: fresh_idv`.
3. Browser runs `verifyFreshForBackend({ requiredAssurance: 'ishuman' })`, then retries claim at `ishuman` assurance.
4. Successful escalated claim clears the doubt flag for that PPID.

Copy-paste modules:

- [`presale_allocation.py`](presale_allocation.py) — registration store + in-memory `(drop_id, ppid)` ledger
- [`relying_site_app.py`](relying_site_app.py) — `POST /api/presale/register` and `POST /api/presale/claim-code`

## Deploy

From the repository root:

```powershell
git subtree push --prefix demo-sites https://git.heroku.com/lemma-demo-tickets.git main
git subtree push --prefix demo-sites https://git.heroku.com/lemma-demo-trials.git main
```
