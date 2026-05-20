# isHuman Demo — Implementation Outline (New Thread Handoff)

Use this document as the single checklist for implementing demo improvements. Backend revocation hardening is **already live on prod** (v2064+); this outline focuses on **making the demo show that story clearly**.

**Demo URL:** `https://lemma.id/demo/ishuman`  
**Customer sites:** `lemma-demo-tickets-*.herokuapp.com`, `lemma-demo-trials-*.herokuapp.com`

---

## Goals (what “done” looks like)

A non-technical presenter can, in **under 3 minutes**:

1. Show **verify once** (wallet + human proof).
2. Show **two businesses, two private IDs** (tickets HUMAN, trials HUMAN, different PPIDs).
3. Show **site block** on abusive ticketing user (tickets DENY, trials still HUMAN).
4. Show **network revoke** (both sites DENY, `revoked`).
5. Never type API keys or tokens on stage.

---

## Phase map


| Phase | Priority | Theme                       | Est. effort |
| ----- | -------- | --------------------------- | ----------- |
| 1     | P1       | Guided presenter mode       | 1–2 days    |
| 2     | P2       | Revocation hero panel       | 1–2 days    |
| 3     | P3       | Customer site reliability   | 1 day       |
| 4     | P4       | One-click test verify       | 0.5–1 day   |
| 5     | P5       | Privacy + integration cards | 0.5 day     |
| 6     | P6       | Fresh IDV / reverify flow   | 2–3 days    |
| 7     | P7       | Polish + presenter script   | 0.5 day     |


Implement **in order** — later phases depend on earlier UI structure.

---

## Progress tracker


| Phase | Status   | Last updated | Notes                                     |
| ----- | -------- | ------------ | ----------------------------------------- |
| 1     | complete | 2026-05-20   | Wizard + operator console collapse        |
| 2     | complete | 2026-05-20   | Abuse panel + probe-derive + PPID compare |
| 3     | complete | 2026-05-20   | Deep links + smoke script + workflow      |
| 4     | complete | 2026-05-20   | verify-once-test-mode endpoint            |
| 5     | complete | 2026-05-20   | Buyer cards + stats                       |
| 6     | complete | 2026-05-20   | force-reverify (demo-minimum)             |
| 7     | complete | 2026-05-20   | Server token inject + presenter script    |


---

## Phase 1 — Guided presenter mode (P1)

**Status:** complete

### 1.1 UI: “Run 3-minute demo” wizard

**Files:**

- `templates/demo/ishuman.html` — add wizard strip + step indicator
- `static/js/demo/ishuman-demo.js` — `runGuidedDemo()` orchestration
- Optional: `static/css/demo/ishuman-demo.css` if styles grow

**Steps to automate (in order):**

1. `initWallet()` — show “Wallet unlocked”
2. `verifyOnceTestMode()` — Phase 4 endpoint or chained calls (see Phase 4)
3. `verifyBothSites()` — tickets + trials pills HUMAN, display both PPIDs
4. `blockTickets()` — tickets DENY, trials HUMAN
5. Pause 2s — narrative beat
6. `requestNetworkReview()` — optional, pill PENDING
7. `approveNetworkRevocation()` — both sites DENY, reason `revoked`
8. Final summary panel

**UX rules:**

- Disable all other buttons while wizard runs; show progress `Step 2/7`.
- On failure: stop wizard, log to `#ih-log`, show recovery hint.
- Default page load: **wizard visible**, advanced controls collapsed.

### 1.2 Collapse “advanced / operator” UI

**Move behind `<details>` or tab “Operator console”:**

- Test token / admin token inputs
- `Complete test verification`, `Poll`, raw JSON
- `Approve network revocation` (keep in wizard, hide from main)

**Keep visible on main surface:**

- Run guided demo
- Open customer sites (deep links — Phase 3)
- Abuse response panel (Phase 2)

### 1.3 Acceptance criteria

- One button runs full arc without manual token entry (tokens from server env on demo routes only).
- Presenter never needs to open “Technical details” for a standard pitch.
- Wizard survives refresh if `localStorage` has `session_id` + `master_credential_id`.

---

## Phase 2 — Revocation hero panel (P2)

**Status:** complete

### 2.1 New “Abuse response” section (above the fold)

**Files:** `templates/demo/ishuman.html`, `ishuman-demo.js`

**Three cards (always visible):**


| Card             | Action                              | Expected UI outcome                                                                          |
| ---------------- | ----------------------------------- | -------------------------------------------------------------------------------------------- |
| Site block       | `POST /api/demo/ishuman/site-block` | tickets `DENY`, `reason: site_blocked` or `revoked`; show `revocation_synced: true` from API |
| Site-scoped only | Verify trials after block           | trials `HUMAN`                                                                               |
| Network revoke   | request + approve                   | both `DENY`, `reason: revoked`                                                               |


**Display after block:**

- Call `GET /api/ishuman/check?ppid=...&site_id=site_demo_tickets` — show `site_block`
- Call without `site_id` — show `site_ppid_revoked` (validates canonical DB path)

### 2.2 Show “derive denied” (proves enforcement, not UI-only)

**Option A (preferred):** New demo endpoint  
`POST /api/demo/ishuman/probe-derive`  

- Body: `site_slug`, uses server-side fixture env (`LEMMA_ISHUMAN_PROD_TEST_`*) or caller’s wallet from demo session  
- Returns `{ allowed, http_status, error }` without exposing secrets to browser

**Option B:** Call public `POST /api/ishuman/derive-site-proof` from demo JS with `wallet_secret` from unlocked wallet (only if secret available client-side).

**UI:** Small line under Site block card:  
`Server derive: blocked (site_ppid_blocked)` in red.

**Files:** `api/ishuman_demo.py`, `ishuman-demo.js`

### 2.3 Side-by-side PPID comparison

**UI element:** “Same human, different site IDs”  

- `ih-tickets-ppid` vs `ih-trials-ppid` — show full or truncated with “copy” tooltip  
- Highlight they differ (not equal)

### 2.4 Acceptance criteria

- After block, ticketing verify shows DENY without manual refresh.
- Trials still HUMAN after ticketing block.
- Derive probe returns 403 when fixture PPID blocked (prod smoke already passes; demo must surface it).
- Network approve sets both sites to DENY.

---

## Phase 3 — Customer site reliability (P3)

**Status:** complete

### 3.1 Inventory external apps

**Locate repos / Heroku apps:**

- Ticketing: `https://lemma-demo-tickets-1d3d7411af33.herokuapp.com`
- Trials: `https://lemma-demo-trials-7090f46cae0d.herokuapp.com`

**Verify each uses:**

```html
<script src="https://lemma.id/sdk/ishuman-verifier.js"></script>
```

```js
new IsHumanVerifier({ siteId: '<correct-hostname>' }).verify()
```

- `siteId` must match `tickets-demo.lemma.id` / `trials-demo.lemma.id` (not internal `site_...`).

### 3.2 Deep links from demo page

**Update `templates/demo/ishuman.html` links:**

- Ticketing: `.../reserve` or whatever route triggers verifier (not homepage only)
- Trials: `.../start-trial` or equivalent

### 3.3 CI / smoke script

**New file:** `scripts/smoke_ishuman_customer_sites.py` (or extend `run_ishuman_prod_revocation_smoke.py`)

**Checks:**

- HTTP 200 on customer app URLs
- Page contains `ishuman-verifier.js` or bridge
- Optional: headless check that protected button exists

**Wire:** `.github/workflows/ishuman-issuance-tests.yml` or new `ishuman-demo-smoke.yml` (manual `workflow_dispatch` OK).

### 3.4 Fallback (if external apps break often)

**Option:** Host minimal mock pages on `lemma.id`:

- `/demo/ishuman/tickets` and `/demo/ishuman/trials`  
- Each page: one CTA → `IsHumanVerifier.verify()` → show result

### 3.5 Acceptance criteria

- Both customer links work from demo page on prod.
- Protected action fails closed without credential; succeeds after demo wallet verify.
- Smoke script fails CI/deploy gate when customer sites regress.

---

## Phase 4 — One-click test verify (P4)

**Status:** complete

### 4.1 Chained demo endpoint

**New route:** `POST /api/demo/ishuman/verify-once-test-mode`

**Server-side (token from env only):**

1. `start-verification` logic (wallet_id + wallet_secret from body or fixture env)
2. `test-complete-verification` logic (uses `LEMMA_ISHUMAN_DEMO_TEST_TOKEN` server-side — **not** from browser)
3. Return `{ session_id, credential_id, credential, ppid }`

**Files:** `api/ishuman_demo.py`

**Guards:** Same as existing test-complete (`ALLOW_TEST_VERIFY`, `sk_test`_).

### 4.2 Wire into wizard

Replace separate “Start IDV” + “Complete test” in guided flow with single call.

**Optional:** Keep “Show real Stripe UI” as advanced path (redirect to `payload.url`).

### 4.3 “Demo ready” banner

After success:

- Green banner: “Human proof ready — open customer sites or continue demo”
- Store `ishuman_demo_master_id`, `ishuman_demo_session_id` in `localStorage`

### 4.4 Acceptance criteria

- One click from cold start → master credential stored → both sites verify HUMAN.
- No password fields required on demo page for test mode.

---

## Phase 5 — Privacy + integration cards (P5)

**Status:** complete

### 5.1 Buyer-facing cards (main page, not `<details>`)

**Card: What sites never see**

- No government ID stored by customer site
- No cross-site user ID (PPID is site-specific)
- Only: `human: true`, expiry, issuer trust

**Card: Integration**

- 2-line snippet (from existing code block)
- Live latency: pull from last `verify()` `timeMs` on tickets/trials cards

**Card: Network stats (optional)**

- `GET /api/ishuman/stats` — verifications, active blocks (public)

**Files:** `ishuman.html`, `ishuman-demo.js` (`loadStats()`)

### 5.2 Acceptance criteria

- Engineer story lives in `<details>`; buyer story is visible without expanding.

---

## Phase 6 — Fresh IDV / reverify flow (P6)

**Status:** complete (demo-minimum)

### 6.1 Product definition (decide before coding)

**States for a site-bound PPID:**


| State               | User experience                         | Backend                           |
| ------------------- | --------------------------------------- | --------------------------------- |
| `active`            | verify() → HUMAN                        | normal                            |
| `site_blocked`      | verify() → DENY                         | SiteBlock + RevocationList        |
| `reverify_required` | verify() → DENY + action “Verify again” | new flag or metadata on SiteBlock |


**Open question for thread:** Is `reverify_required` separate from `site_block`, or block + clear site credential + force new derive?

### 6.2 Minimum demo implementation

**Demo button:** “Force fresh IDV (ticketing)”  

1. Block or mark PPID reverify
2. Clear derived credential for site in wallet (bridge API if exists)
3. `start-verification` again → test-complete → re-verify tickets HUMAN

**Files (likely):**

- `api/ishuman_demo.py` — `POST /api/demo/ishuman/force-reverify`
- `ishuman-demo.js`
- Possibly `api/ishuman.py` if productizing beyond demo

### 6.3 Acceptance criteria

- Narrative: “cheaper than network ban; attacker must pass IDV again.”
- Ticketing flows: block → deny → reverify → human again.

---

## Phase 7 — Polish + presenter script (P7)

**Status:** complete

### 7.1 Remove friction

- Server injects demo tokens for `/demo/ishuman` only (remove visible token inputs from default UI).
- Consistent pill colors: ok / warn / deny.
- Empty states (“Create wallet first”) on every action.

### 7.2 Presenter script

**New file:** `docs/demo/ISHUMAN_PRESENTER_SCRIPT.md`

**Sections:**

- 30-second opening (IP ban problem)
- 90-second guided demo click path
- 30-second revocation climax lines
- Backup if Stripe fails (test-complete only)
- FAQ: privacy, cost ($2 IDV), integration time

### 7.3 Recorded fallback

- 60–90s screen capture of guided demo on prod (optional asset in repo or Notion).

### 7.4 Acceptance criteria

- Two different people can run demo from script with same outcomes.

---

## Shared backend / env reference (already on prod)

Set on `lemma-enterprise` Heroku:


| Variable                                       | Purpose                   |
| ---------------------------------------------- | ------------------------- |
| `LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY`         | `true`                    |
| `LEMMA_ISHUMAN_DEMO_TEST_TOKEN`                | server-only test complete |
| `LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN`               | network approve in demo   |
| `LEMMA_ISHUMAN_PROD_TEST_WALLET_ID`            | fixture wallet            |
| `LEMMA_ISHUMAN_PROD_TEST_WALLET_SECRET`        | fixture secret            |
| `LEMMA_ISHUMAN_PROD_TEST_SITE_PPID`            | for probe/smoke           |
| `LEMMA_ISHUMAN_PROD_TEST_MASTER_CREDENTIAL_ID` | after provision           |
| `LEMMA_ISHUMAN_PROD_TEST_SITE_API_KEY`         | optional smoke            |


**Scripts:**

- `scripts/provision_ishuman_prod_test_wallet.py`
- `scripts/run_ishuman_prod_revocation_smoke.py`
- `docs/testing/ISHUMAN_PROD_REVOCATION_SMOKE.md`

**Run smoke after each demo deploy:**

```bash
python scripts/run_ishuman_prod_revocation_smoke.py --base-url https://lemma.id
```

---

## Suggested new-thread prompt (copy/paste)

```
Implement the isHuman demo improvements from docs/demo/ISHUMAN_DEMO_IMPLEMENTATION_OUTLINE.md.

Work phase by phase (1 → 7). After each phase:
- run pytest for touched tests
- run scripts/run_ishuman_prod_revocation_smoke.py if backend changed
- briefly note what to click on https://lemma.id/demo/ishuman to verify

Constraints:
- Do not edit ISHUMAN_DEMO_IMPLEMENTATION_OUTLINE.md unless fixing errors
- Keep buyer story on main page; engineer details in collapsed sections
- Demo tokens must not be required in browser inputs for standard flow
- Preserve site-bound PPID guardrails (hostname binding, no cross-site ID leakage)
```

---

## Testing checklist (end of project)

- Guided demo completes on prod without token fields (run after deploy)
- Ticketing block → trials still human → network revoke → both denied (run after deploy)
- Customer site links work (run `scripts/smoke_ishuman_customer_sites.py`)
- `run_ishuman_prod_revocation_smoke.py` → 8/8 (run after deploy)
- Presenter script read-through < 3 minutes (`docs/demo/ISHUMAN_PRESENTER_SCRIPT.md`)

---

## Out of scope (do not block demo v1)

- Full production `reverify_required` for all customer sites (demo-only OK first)
- Bloom filter internals in UI
- Live Stripe document upload in every presentation (test-complete path is default)
- GitHub sync for `deploy-heroku-deep-claims` (separate ops task)

---

## File index (quick reference)


| Area               | Primary files                                   |
| ------------------ | ----------------------------------------------- |
| Demo page          | `templates/demo/ishuman.html`                   |
| Demo logic         | `static/js/demo/ishuman-demo.js`                |
| Demo API           | `api/ishuman_demo.py`                           |
| Production isHuman | `api/ishuman.py`, `api/site_ppid_revocation.py` |
| Verifier SDK       | `static/js/ishuman-verifier.js`                 |
| Revocation smoke   | `scripts/run_ishuman_prod_revocation_smoke.py`  |
| Presenter script   | `docs/demo/ISHUMAN_PRESENTER_SCRIPT.md`         |
| Demo CSS           | `static/css/demo/ishuman-demo.css`              |
| Customer smoke     | `scripts/smoke_ishuman_customer_sites.py`       |
| Demo CI smoke      | `.github/workflows/ishuman-demo-smoke.yml`      |


