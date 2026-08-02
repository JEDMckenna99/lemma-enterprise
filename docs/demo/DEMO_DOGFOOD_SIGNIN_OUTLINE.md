# Demo v3: Dogfooded Sign-in — lemma.id is its own first relying site

**Status:** Approved direction, not started
**Owner intent (verbatim):** "the main demo should be on lemma.id not a redirect to a separate site. the main demo on lemma.id should create a lemma.id and that ppid + presentation is what opens the lemma.id manager."
**Supersedes:** the "Try it" lane of `docs/demo/DEMO_REDESIGN_OUTLINE.md` (the plain-language work and builder lane from that effort are kept).

---

## 1. Problem statement

The current demo at `lemma.id/demo` is a *demo artifact*: a parallel surface that simulates the product next to the product. Symptoms:

- The main user path redirects to a separate site (`tickets-demo.lemma.id`) — a domain hop that loses people and makes lemma.id a spectator of its own product.
- The payoff for signing in is a status pill turning green, not anything a normal person recognizes as a reward.
- The demo needs its own state machine ("Clear demo data", wizard panels), which breaks independently of the product and feels clunky.

## 2. The fix: the demo is the product's own front door

lemma.id dogfoods **Sign in with lemma.id**. The demo becomes a single-column page with exactly three states, and the state is simply the user's real session:

| State | What the user sees | Primary action |
|---|---|---|
| A. No lemma.id yet | "Create your lemma.id" — one sentence of copy, one button | Real passkey ceremony creates the credential |
| B. Has lemma.id, not signed in | "Now use it to sign in to lemma.id" | The real `<lemma-signin site-id="lemma.id">` drop-in from the docs quickstart |
| C. Signed in | **The lemma.id manager opens** (`/app`) | Explore the manager |

The PPID + verified presentation from state B is literally the key that opens the manager. No simulation anywhere: the same SDK element, the same server-side presentation verification we tell customers to do, a real HttpOnly session.

Inside the manager, two new narration panels tell the privacy story with the user's own real data:

1. **"Here is everything lemma.id learned about you when you signed in"** — one random PPID, proof level (passkey / isHuman), credential created date. No email, no name, no password.
2. **"Here's what other sites would see"** — inline derivation of the PPIDs the demo relying sites would receive (the current hub JS already does dual-site `verifyForBackend` derivation; reuse it, do NOT redirect). Three different opaque strings side by side → "sites can't compare notes about you."
3. Optional proof links: "Try it on a real third-party site →" pointing at the live demo sites. Links, not the main path.

"Reset the demo" becomes "Sign out". No more clear-demo-data plumbing on the main path.

The existing hub (wizard, Enforce beat, presale tour, dev views) is preserved as the **"See how it works" builder lane**, reachable from the demo page and the end of the manager tour.

## 3. Hard rules (do not violate)

From `AGENTS.md` — these are product-security invariants:

1. Verify a **signed presentation on the server**; never trust a bare client `ppid`. The session must only be minted from a server-verified presentation.
2. **Fail closed** on any verification failure.
3. `siteId` for the platform is the canonical hostname **`lemma.id`** (never an internal `site_...` id).
4. No new user-facing "wallet" language. The user-held object is a **lemma.id**; the page at `/app` is the **lemma.id manager**. Internal `wallet_*` identifiers in code are fine.
5. Default `requiredAssurance: 'passkey'` for sign-in. `'ishuman'` only for explicit step-up beats.

## 4. How to work — process contract (this section is mandatory, not advisory)

Previous demo builds failed on look-and-feel, not plumbing. These rules exist to prevent that. Do not skip them to "save time" — a demo that works but looks bad is a failed delivery.

1. **Screens before plumbing.** Phase 0 (static mock) comes before any backend work. Do not write a session endpoint, route, or test until the mock is approved.
2. **You must look at what you build.** After every UI change, render the page in a real browser and take a screenshot. Never mark a UI task done without a screenshot of it. "Tests pass" is not evidence that a screen is acceptable.
3. **Deliver screenshots at every gate.** Each phase below ends with a gate: present screenshots of every state/screen touched (desktop ~1280px AND mobile ~390px) and wait for owner approval before starting the next phase. Do not batch phases.
4. **Click through the whole flow yourself.** Before calling the main path done, drive it end to end in the browser: fresh profile → create → sign in → manager opens → sign out → gate reappears. If any step needs a manual passkey ceremony you cannot automate, screenshot up to that boundary and state exactly where the human needs to take over.
5. **One vertical slice first.** The main path (three states + `/app` gate + manager panels) is the entire first delivery. Homepage CTA, builder-lane cleanup, docs, and presenter scripts come only after the slice is approved.
6. **When in doubt, cut.** Fewer elements, fewer words, fewer states. Anything you are tempted to add "for completeness" goes in the builder lane or gets cut.

## 5. Design spec — the quality bar

The visual source of truth is the existing marketing site, **not** the current demo hub. Match `templates/modern/` (see `templates/modern/layout.html`): brand purple `#4E3D8F` (`--primary`), IBM Plex Sans, white background, generous whitespace. If a screen would look out of place next to `lemma.id/about`, it's wrong.

Layout and rhythm:

- Single centered column, max-width ~560px for the flow states. One headline (~32–40px), at most two sentences of supporting copy (~17–18px, `--gray-700`), one primary button. Nothing else competes.
- Primary button: brand purple, large (≥ 48px tall), full-width within the column on mobile. Exactly one per state.
- State transitions animate (150–250ms fade/slide). The state change is the product moment — it must feel instant and smooth, never a full-page reload between A→B→C.
- The sign-in moment (B→C) should visibly celebrate speed: show elapsed time ("Signed in — 0.9s. No password. No email code.") in the success beat.
- Status/errors: one plain sentence via `plain-language.js`, styled as quiet inline text — no red alert boxes, no raw reason codes, no JSON, no monospace dumps anywhere on the main path.
- PPIDs render as short truncated badges (`a3f8…9c21` style, monospace inside a pill) with a copy affordance — never full-width raw strings.
- Manager narration panels: card style consistent with `modern/` pages, light border (`--gray-200`), 12–16px radius, clear panel title, one sentence of narration per panel. Not collapsible accordions, not tables.
- Mobile (390px) is a first-class target: every gate screenshot set includes it.

Anti-patterns (all of these have shipped before and are why we're redoing this): wizard step indicators, status pills as the payoff, "Clear demo data" buttons on the main path, developer JSON visible by default, three columns of cards, walls of explanatory text.

## 6. Map of existing code (read these before writing anything)

| Concern | Where it lives today |
|---|---|
| Demo hub route `/demo` | `api/ishuman_demo.py` (blueprint `ishuman_demo_bp`), renders `templates/demo/lemma.html` |
| Demo hub JS/CSS | `static/js/demo/ishuman-demo.js`, `static/js/demo/plain-language.js`, `static/css/demo/ishuman-demo.css` |
| The lemma.id manager | `/app` route in `app.py` (~line 700) → `templates/wallet_simple.html`. Currently served unconditionally; unlock is local (passkey-gated credential store in the page itself). |
| Server-side presentation verification | `POST /api/ishuman/verify-presentation` in `api/ishuman.py` (~line 3500) |
| Platform-as-site identity model | `AGENTS.md` "Platform operator identity", `docs/product/LEMMA_ID_PRESENTATION_MODEL.md`, `api/authz_engine.extract_user_lemma_principal`, `api/lemma_auth_endpoint.py` (issuance bound to `siteId: lemma.id`) |
| Browser SDK | `static/js/` proof-verifier + `lemma-signin` element (served at `/sdk/proof-verifier.js`, `/sdk/lemma-signin.js`; see `api/sdk_serving.py`) |
| lemma.id creation flow | `templates/wallet_popup.html` / `wallet_simple.html` creation path; the SDK's `autoProvision: true` path |
| Dual-site PPID derivation (for the compare panel) | existing hub JS in `static/js/demo/ishuman-demo.js` (per-site `verifyForBackend` calls) |
| Demo relying sites (become optional links) | `demo-sites/relying_site_app.py`, deployed at `tickets-demo.lemma.id` / `trials-demo.lemma.id` |
| Tests to update | `tests/test_ishuman_demo.py`, `tests/test_demo_assurance_hub.py`, `tests/test_demo_relying_site_app.py`; add new session-gate tests |

Investigate before building: exactly how `wallet_simple.html` decides "you have a lemma.id on this device" vs "create one" — the demo page states A/B must reuse the same detection (SDK-side local credential presence), not invent a new one.

## 7. Implementation phases

Every phase ends with a **gate**: screenshots (desktop + mobile) of everything touched, presented for owner approval before the next phase begins.

### Phase 0 — Static mock of every screen (no backend, no SDK)

Goal: the owner approves exactly what the demo will look like before any wiring exists.

- Build a temporary route (e.g. `/demo/mock`) rendering static versions of: state A, state B, state B's success beat, the `/app` sign-in gate, and the manager with both narration panels — all with hardcoded data and working fake transitions (a button click advances the state with the real animation).
- Follow the design spec (section 5) exactly. Iterate on this page with screenshots until it looks like it belongs on lemma.id.
- **Gate:** full screenshot set of all five screens, desktop + mobile. Do not proceed until approved. The mock route is deleted in Phase 4.

### Phase 1 — Presentation-based session for lemma.id itself (backend)

Goal: a real "Sign in with lemma.id" session on lemma.id, minted only from a server-verified presentation.

- New endpoint `POST /api/auth/session` (name flexible; keep it product-shaped, not demo-shaped):
  - Body: `{ "presentation": ... }`.
  - Verify via the same code path as `POST /api/ishuman/verify-presentation`, with expected site binding `lemma.id` and `requiredAssurance` at least `passkey`.
  - On success: set an HttpOnly, Secure, SameSite=Lax session (Flask session is fine) containing `{ ppid, assurance, issued_at }`. Return `{ ok: true, ppid, assurance }`.
  - On any failure: **401, session untouched** (fail closed). Map failure reasons through the existing plain-language reason codes.
- `POST /api/auth/session/logout` — clears the session.
- `GET /api/auth/session` — returns current session state `{ signed_in, ppid, assurance }` for page-state detection.
- Notes:
  - Do not reuse the operator/admin permission path (`extract_user_lemma_principal` / `admin_access`) for this — that is a *permission proof* layer. This is plain user sign-in: identity presentation only, no permission claims.
  - Rate-limit like other auth endpoints; check CSP and the Auth Launch Gate workflow won't be tripped (see `.github/workflows/auth-launch-gate.yml`).

### Phase 2 — The three-state demo page (default lane of `/demo`)

Goal: replace the current default "Try it" lane in `templates/demo/lemma.html` with the single-column three-state flow.

- On load, resolve state:
  - `GET /api/auth/session` says signed in → **state C**: show a short "You're in" beat and a single button "Open your lemma.id manager" → `/app`. (Optionally auto-redirect after a beat; start with an explicit button.)
  - Else, SDK detects a local lemma.id credential → **state B**.
  - Else → **state A**.
- **State A:** headline ("See what signing in is like without an account, an email, or a password"), one button "Create your lemma.id". Triggers the real creation ceremony (same path `wallet_simple.html` / the SDK popup uses). On completion, advance to state B without reload.
- **State B:** one sentence ("You just made a lemma.id. Now use it to sign in to this very site.") + the real drop-in: `<lemma-signin site-id="lemma.id">` (or `ProofVerifier.verifyForBackend({ requiredAssurance: 'passkey' })` if the element needs a custom success handler). On success, POST the presentation to `/api/auth/session`; on `ok` advance to state C.
- Each state: one headline, ≤ 2 sentences of copy, one primary button. Use `plain-language.js` for any status/error text. Show elapsed time on the sign-in ("0.9s — no password, no email code") since speed is a core claim.
- Keep the existing hub as the **builder lane**: the current lane-chooser stays, but "Try it" now means this flow and "See how it works" opens the existing wizard/Enforce/presale content unchanged.
- Errors: if passkey ceremony is cancelled/unsupported, show one plain sentence and the retry button — never a raw reason code.

### Phase 3 — Gate `/app` and add narration panels to the manager

Goal: PPID + presentation is what opens the manager; the manager tells the privacy story.

- `/app` route in `app.py`: if no valid lemma.id session (Phase 1), render the sign-in gate instead of the manager. The gate is visually the same three-state component as `/demo` (share the markup/JS; do not fork it). If session exists, render `wallet_simple.html` as today (local unlock flow inside the manager is unchanged — the session gates the *page*, the local credential store still does its own unlock for sensitive operations).
- Add to the manager (top of page or a first-run panel, dismissible, shown when arriving with a fresh session):
  1. **"What lemma.id learned about you"** — PPID (truncated with a copy control), proof level via `plain-language.js` assurance labels, created/sign-in time. Explicit line: "No email. No name. No password. This random ID is everything this site gets."
  2. **"What other sites would see"** — inline PPID compare reusing the hub's per-site derivation (`tickets-demo.lemma.id`, `trials-demo.lemma.id`). Three badges, three different strings, one sentence: "Every site gets a different ID. Sites can't compare notes about you."
  3. **Next steps row:** "Try it on a real third-party site →" (links to live demo sites), "See how to add this to your site →" (builder lane / docs quickstart).
- "Sign out" control in the manager clears the Phase-1 session (and returns you to state A/B on `/demo`).

**Gate after Phase 3:** this completes the vertical slice. Drive the full flow in a browser (fresh profile → create → sign in → manager → sign out → gate) and present the screenshot walkthrough. Phases 4–5 start only after approval.

### Phase 4 — Entry points and cleanup

- Homepage (`templates/modern/index.html`): point the primary CTA at `/demo` (the new flow). Do not otherwise redesign the homepage in this effort.
- The old redirect-to-tickets user lane in the hub: remove it from the default path (the tickets tour remains reachable from the builder lane and the manager's "next steps" links).
- Delete the Phase 0 mock route.
- Verify `/demo/firewall` (legacy deep link) still works untouched.

### Phase 5 — Tests and docs

- Backend tests (new file, e.g. `tests/test_lemma_session_auth.py`):
  - Valid presentation bound to `lemma.id` → session set, `GET /api/auth/session` reflects it.
  - Invalid/expired/wrong-site presentation → 401, no session (fail closed).
  - Bare `ppid` without presentation → rejected.
  - Logout clears session; `/app` without session serves the gate, with session serves the manager.
  - Use the dev-issuer pattern from `AGENTS.md` (`lemma_crypto.PyMinimalIssuer.from_seed` + `TRUSTED_ISSUER_DIDS`) so tests don't need KMS.
- Update `tests/test_ishuman_demo.py` / `tests/test_demo_assurance_hub.py` for the new default-lane markup and any script version bumps.
- Docs: update `docs/demo/ISHUMAN_PRESENTER_SCRIPT.md` and `docs/demo/DEMO_HANDOFF_ONEPAGER.md` to the new beats (create → sign in → manager opens → privacy panels → optional third-party site). The presenter script should be ≤ 90 seconds for the main path.
- Run the standard suite (`python scripts/ci_regression_suite.py` or pytest with `DATABASE_URL=sqlite:///:memory:` + `LEMMA_*` test secrets per `.github/workflows/ci-regression.yml`).

## 8. Acceptance criteria

1. A first-time visitor on `lemma.id/demo` can: create a lemma.id → sign in to lemma.id with it → land in the lemma.id manager, without ever leaving the `lemma.id` origin and without seeing a raw reason code, wizard, or redirect.
2. The session that opens `/app` was minted **only** from a server-verified presentation bound to `siteId: lemma.id`. Deleting the session cookie and hitting `/app` shows the gate.
3. The manager shows the "what lemma.id learned" and "what other sites would see" panels with real derived values; the three PPIDs differ.
4. Every screen matches the design spec (section 5) and has been verified with desktop + mobile screenshots in a real browser.
5. The builder lane (wizard, Enforce, presale tour) still works exactly as before.
6. All tests green locally; Auth Launch Gate passes on push.

## 9. Out of scope

- Redesigning `wallet_simple.html` internals or its local unlock flow.
- Changing the demo relying sites (`demo-sites/`) beyond copy that references the old redirect flow.
- Making `/demo` the homepage / removing the marketing homepage (possible follow-up: "lemma.id has no other front door").
- isHuman step-up in the main path (stays in builder lane / presale tour).
- Agent Ops / Lemma Firewall surfaces.
