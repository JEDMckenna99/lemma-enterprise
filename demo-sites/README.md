# lemma.id proof continuity — relying-site demo apps

These tiny Flask apps simulate real third-party relying sites for the lemma.id proof-layer demo.

Each app loads the documented drop-in with **siteId = its own hostname** (same contract as any integrator):

```html
<script src="https://lemma.id/sdk/proof-verifier.js"></script>
<script src="https://lemma.id/sdk/lemma-signin.js"></script>
<lemma-signin site-id="lemma-demo-tickets-1d3d7411af33.herokuapp.com" lemma-origin="https://lemma.id"></lemma-signin>
```

Use `lemma-origin` when `LEMMA_ORIGIN` is not production `https://lemma.id` (staging demos).

## Expected Heroku Apps

- `lemma-demo-tickets`, **Sign in shell + optional presale tour**
  - `LEMMA_DEMO_SITE_ID=lemma-demo-tickets-1d3d7411af33.herokuapp.com`
  - `LEMMA_DEMO_SITE_NAME=Lemma Ticketing Demo`
  - `LEMMA_DEMO_SITE_KIND=ticketing`
  - Default `/` — mint a presentation with `<lemma-signin>` → optional session cookie
  - `/?tour=presale` — Sybil-resistant presale enforcement demo
  - `LEMMA_PRESALE_DROP_ID=artist-presale-2026` (optional)
  - `LEMMA_PRESALE_CODE_CLAIM_ASSURANCE=ishuman` (default; optional)
  - `LEMMA_PRESALE_ESCALATED_ASSURANCE=ishuman` (optional, IDV penalty on site doubt)
  - `LEMMA_PRESALE_SQLITE_PATH=/tmp/presale.db` (optional, persistent ledger across restarts)
- `lemma-demo-trials`
  - `LEMMA_DEMO_SITE_ID=lemma-demo-trials-7090f46cae0d.herokuapp.com`
  - `LEMMA_DEMO_SITE_NAME=Lemma Free Trial Demo`
  - `LEMMA_DEMO_SITE_KIND=free trial`
  - `LEMMA_TRIAL_DROP_ID=northstar-free-trial` (optional, trial dedupe ledger key)
  - One free trial per verified person: a successful `start_trial` claims the PPID
    in the site-local ledger; repeats return `403 trial_already_used`.
  - `GET /api/demo/trial/status` (session) and `POST /api/demo/trial/reset`
    (session must own the PPID) support the on-page demo reset.

## Verify + enforce (primary product demo)

Both demo sites use lemma.id proof continuity:

1. User clicks `<lemma-signin>` (passkey ceremony in Lemma popup).
2. Browser sends signed `presentation` to `POST /api/login`.
3. Server verifies locally and sets HttpOnly `lemma_demo_session` cookie.
4. Soft actions (`/api/demo/action`, presale register/status) reuse that cookie until policy requires a fresh passkey ceremony at claim time.

Session endpoints:

- `POST /api/login` — verify presentation, set HttpOnly `lemma_demo_session` cookie
- `GET /api/me` / `POST /api/logout` — session introspection and logout
- `POST /api/demo/action` — soft action via session cookie or presentation

## Demo hub return URL

`LEMMA_DEMO_HUB_URL` defaults to `{LEMMA_ORIGIN}/demo/how-it-works` (the builder
hub). Do not point it at `/demo` — that dogfood front door redirects signed-in
users to `/app` and breaks “Return to demo hub”.

## Hub verify bridge

The lemma.id demo hub cannot mint `/verify` flow-state for these remote siteIds
(opener origin must match the site hostname). Instead the hub opens:

`GET /hub-verify?hub_origin=…&request_id=…&required_assurance=passkey|ishuman&mode=signin|fresh_presence|fresh_idv`

This page runs the ceremony on the demo Origin, optionally establishes a local
session via `POST /api/login`, then `postMessage`s `LEMMA_HUB_VERIFY_RESULT` to
`window.opener` at the validated `hub_origin` and closes.

## Presale reference flow (secondary — tickets `/?tour=presale`)

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

**Status lookup (session or presentation)**

- `POST /api/presale/status` with site session cookie or signed presentation (no GET leak of codes).

**Risk flag escalation (demo penalty path)**

1. Site flags PPID (`POST /api/demo/policy/doubt`).
2. Passkey claim returns `doubt_required` with `escalation: fresh_idv`.
3. Browser runs `verifyFreshForBackend({ requiredAssurance: 'ishuman' })`, then retries claim at `ishuman` assurance.
4. Successful escalated claim clears the doubt flag for that PPID.

Copy-paste modules:

- [`presale_allocation.py`](presale_allocation.py), registration store + in-memory `(drop_id, ppid)` ledger
- [`relying_site_app.py`](relying_site_app.py), sign-in session, presale challenge/register/claim/status APIs

Sales script: [`docs/demo/PRESALE_DEMO_SCRIPT.md`](../docs/demo/PRESALE_DEMO_SCRIPT.md)

## Deploy

From the repository root:

```powershell
git subtree push --prefix demo-sites https://git.heroku.com/lemma-demo-tickets.git main
git subtree push --prefix demo-sites https://git.heroku.com/lemma-demo-trials.git main
```

After deploy, verify:

- https://lemma-demo-tickets-1d3d7411af33.herokuapp.com/ (Sign in shell)
- https://lemma-demo-tickets-1d3d7411af33.herokuapp.com/?tour=presale (presale tour)
- https://lemma-demo-trials-7090f46cae0d.herokuapp.com/
