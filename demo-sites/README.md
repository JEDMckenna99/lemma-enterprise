# isHuman Relying-Site Demo Apps

These tiny Flask apps simulate real third-party relying sites for the isHuman demo.

Each app serves one page that loads:

```html
<script src="https://lemma.id/sdk/ishuman-verifier.js"></script>
```

## Expected Heroku Apps

- `lemma-demo-tickets` — **unique presale code reference**
  - `LEMMA_DEMO_SITE_ID=tickets-demo.lemma.id`
  - `LEMMA_DEMO_SITE_NAME=Lemma Ticketing Demo`
  - `LEMMA_DEMO_SITE_KIND=ticketing`
  - `LEMMA_PRESALE_DROP_ID=artist-presale-2026` (optional)
  - `LEMMA_PRESALE_CODE_CLAIM_ASSURANCE=ishuman` (optional)
- `lemma-demo-trials`
  - `LEMMA_DEMO_SITE_ID=trials-demo.lemma.id`
  - `LEMMA_DEMO_SITE_NAME=Lemma Free Trial Demo`
  - `LEMMA_DEMO_SITE_KIND=free trial`

## Presale reference flow (tickets demo)

RealFan-style integration: one verified person receives at most one unique code per drop.

1. Fan enters email and phone on the relying site (site-local only).
2. Browser calls `stampAction({ drop_id, email, phone }, { action: 'claim_presale_code', requiredAssurance: 'ishuman' })`.
3. Server verifies the action stamp locally (`verify_action_stamp`), enforces site block/doubt policy, then claims against the site-local ledger keyed by `(drop_id, ppid)`.
4. First claim returns an 8-digit code; a second claim with the same PPID is denied with `allocation_already_claimed`.

Copy-paste modules:

- [`presale_allocation.py`](presale_allocation.py) — in-memory `(drop_id, ppid)` ledger
- [`relying_site_app.py`](relying_site_app.py) — `POST /api/presale/claim-code` reference endpoint

## Deploy

From the repository root:

```powershell
git subtree push --prefix demo-sites https://git.heroku.com/lemma-demo-tickets.git main
git subtree push --prefix demo-sites https://git.heroku.com/lemma-demo-trials.git main
```
