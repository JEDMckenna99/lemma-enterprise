# Demo redesign outline: user-lane-first Sign in with lemma.id demo

Instructions for an agent redesigning the public demo. Follow phases in order;
each phase is independently shippable and has acceptance criteria.

## Goal

Make the demo **clear, understandable to non-devs, and actionable**: a person
with no technical background can be handed the demo (or give it to someone
else) and *feel* the difference of using lemma.id, without a presenter
translating jargon.

**Diagnosis being fixed:** the current demo is a control panel *about* the
product, not an experience *of* it. The hub dashboard (PPIDs, reason codes,
assurance states) is the main stage and the relying sites are side links.
The product is only feelable on a relying site — the moment you tap a passkey
and you're in, with no form. Non-devs currently hit `site_proof_required`,
`did:lemma:••••455a`, and buttons like "Legacy doubt" before they ever feel
anything.

## Non-negotiable guardrails

Carry over every rule from `docs/demo/README.md` and `AGENTS.md`:

- Verbs: **create**, **sign in**, **set assurance** / **require human proof**,
**doubt**, **ban**. Avoid "escalate", five-act chapter names.
- Say "This demo uses Didit as the IDV rail." No Stripe partnership claims.
- No new user-facing "wallet" language — the noun is **lemma.id**.
- Never expose API keys or `wallet_secret`. Test IDV bypass stays
non-production only.
- Network-wide revocation is retired; do not resurrect it in UI or copy.
- Relying sites must keep using the same `<lemma-signin>` drop-in as the docs
quickstart (docs parity is a selling point — don't fork a demo-only SDK path).
- isHuman is framed as an **optional per-action step-up tier**, not the
product. Default assurance stays `passkey`.

## File map (current implementation)


| Surface                                      | Files                                                                                                                                                                       |
| -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Demo hub `/demo`                             | `api/ishuman_demo.py` (route + context), `templates/demo/lemma.html`, `static/js/demo/ishuman-demo.js`, `static/css/demo/ishuman-demo.css`                                  |
| Relying sites (tickets + trials Heroku apps) | `demo-sites/relying_site_app.py` (single app, both variants; inline HTML/JS), `demo-sites/presale_allocation.py`, `demo-sites/lemma_proof_verifier*.py`                     |
| Demo API                                     | `api/demo_api.py`, `/api/demo/ishuman/`* endpoints in `api/ishuman_demo.py`                                                                                                 |
| Docs / scripts                               | `docs/demo/README.md`, `docs/demo/ISHUMAN_PRESENTER_SCRIPT.md`, `docs/demo/PRESALE_DEMO_SCRIPT.md`, `docs/demo/ISHUMAN_DEMO_IMPLEMENTATION_OUTLINE.md`                      |
| Tests                                        | `tests/test_ishuman_demo.py`, `tests/test_demo_assurance_hub.py`, `tests/test_demo_relying_site_app.py`, `tests/test_ishuman_demo_smoke_lifecycle.py`                       |
| CI / deploy                                  | `.github/workflows/ishuman-demo-smoke.yml`; deploy demo sites via `git subtree push --prefix demo-sites https://git.heroku.com/lemma-demo-tickets.git main` (and `-trials`) |


## Target design

Two lanes, user lane is the default:

1. **User lane ("Try it")** — guided story lived on the relying sites.
  The hub is reduced to a launcher + optional narrator overlay.
2. **Builder lane ("See how it works")** — the existing hub panels, dev view,
  Enforce controls, raw reason codes. Nothing is deleted; it's demoted behind
   an explicit lane switch.

### User lane story beats (canonical order)

1. **Contrast (20s).** The bad old way: a mock email/password/verify-inbox
  signup on the tickets site, clearly labeled as a mock ("what signing up
   usually feels like"). Then: "Now the lemma.id way."
2. **Form-free sign-in.** Tap "Sign in with lemma.id" on the tickets site →
  passkey → signed in. No form. Plain-language confirmation: "You're in.
   No email, no password, nothing to breach."
3. **Claim the scarce thing.** Claim a presale code. Success screen states the
  guarantee in human terms: "One code per person, and this site never saw
   your ID documents."
4. **The denial (centerpiece).** One obvious button: "Try to grab a second
  code" → denied. Copy: "You already got yours — one per person." Raw code
   `allocation_already_claimed` moves to the dev overlay.
5. **Privacy reveal.** Open the trials site, sign in with the same lemma.id.
  Side-by-side badges: "Tickets sees •••455a / Trials sees •••76e5 —
   different IDs. These sites can't compare notes about you."
6. **Returning user.** Prompt: "Close this tab, come back." Session persists;
  re-sign-in yields the same private ID. Copy: "Still you. No 'forgot
   password.'"
7. **End card, per audience.**
  - Developer: copy-paste `<lemma-signin>` snippet + link to
   `docs/integration/ISHUMAN_AGENT_INTEGRATION.md` quickstart.
  - Buyer/operator: link to Enforce chapter (builder lane) + contact.
  - User: "Create your lemma.id" CTA.

### Builder lane changes (smaller)

- Keep Create · Sign in · Enforce structure and all existing controls.
- Label the Enforce chapter as an explicit perspective shift: "Put on the
site-owner hat." Reduce primary verbs to three a non-dev can say:
**require human proof**, **doubt**, **ban**. Keep "Legacy doubt",
"Recheck", assurance sliders behind a collapsed advanced section.
- Dev view (signed presentations, proof receipt, latency) stays — latency
column proves offline verification; keep it visible in this lane.

## Phases

### Phase 1 — Plain-language layer (highest leverage, no structural change)

Add a single translation map (one source of truth, shared by hub and demo
sites — implement in JS consumed by both, e.g. a small module served from the
hub origin) from machine states to human sentences. Raw codes remain visible
only in dev view. Minimum entries:


| Code / state                 | Human copy                                                     |
| ---------------------------- | -------------------------------------------------------------- |
| `site_proof_required`        | "This site wants proof it's really you before letting you in." |
| `session_valid`              | "You're signed in."                                            |
| `allocation_already_claimed` | "You already got your code — it's one per person."             |
| `idv_cancelled`              | "Identity check was cancelled — nothing was shared."           |
| `doubt_required`             | "This site wants a fresh check that it's still you."           |
| `site_blocked`               | "This site has banned this account."                           |
| `action_nonce_reused`        | "Blocked: someone tried to reuse an old approval."             |
| `registration_required`      | "Sign up for the drop first."                                  |
| `assurance: passkey`         | "Signed in with a passkey."                                    |
| `assurance: ishuman`         | "Verified human — one account per person."                     |


Also rename raw badge labels in the default view: "PRIVATE SITE ID" →
"What this site sees", "ASSURANCE" → "Proof level", "REASON" → status
sentence.

**Acceptance:** every state a visitor can reach in the default view renders a
plain sentence; no raw snake_case code visible outside dev view; existing
tests updated, hub smoke test green.

### Phase 2 — Resequence the tickets presale form

Email/phone currently open Step 1 (contradicts the "no email" promise as the
first felt experience). Change `demo-sites/relying_site_app.py` presale flow:

1. Step 1 = passkey register only (no contact fields).
2. Contact fields appear **after** a successful code claim, framed as
  delivery: "Where should we send your code? (Stays on this site — lemma.id
   never sees it.)" Optional/skippable.
3. Ledger and stamp logic unchanged (`(drop_id, ppid)` keying, fresh passkey
  at claim).

**Acceptance:** first presale interaction shows no contact form;
`tests/test_demo_relying_site_app.py` updated; claim + retry-denial flow still
passes; presale attack-lab behavior unchanged.

### Phase 3 — User lane on the tickets site

Build the guided story (beats 1–4, 6 above) as the tickets site default
experience (`/` or `/?tour=welcome`; keep `/?tour=presale` working as the
deeper enforcement tour). Reuse the existing tour framework
(`TOUR_SEQUENCE` machinery in `relying_site_app.py`).

- Beat 1 contrast mock: purely client-side, clearly labeled, never submits.
- Beat 4 denial: promote "Try again with same lemma.id" from tour step 3 to a
primary post-claim button.
- Progress indicator with the beats in plain words.
- Every beat has a one-line "why this matters" caption.

**Acceptance:** a visitor who only clicks the single highlighted next-action
button on each screen traverses beats 1→4→6 without seeing a raw code, an
admin control, or the hub; existing presale tour unaffected.

### Phase 4 — Privacy reveal across both sites (beat 5)

- From the tickets success screen, CTA: "Now try the other site." Trials
sign-in, then a compare view: two colored badges, the sentence "These sites
can't compare notes about you."
- Implementation choice: simplest is the compare living on the hub (it already
computes dual-site PPIDs via `verifyForBackend`); restyle the hub compare
block to the badge treatment and deep-link back into the user lane flow.

**Acceptance:** compare view reachable in ≤2 clicks from tickets success
screen; shows truncated distinct PPIDs + plain sentence; dev view still shows
full presentations.

### Phase 5 — Hub restructure into two lanes

- `/demo` opens with a lane chooser (default-highlighted: "Try it" → tickets
user lane; secondary: "See how it works" → current hub).
- Builder lane keeps everything, with the Enforce hat-switch labeling and the
advanced-controls collapse described above.
- End card (beat 7) appended to both lanes.
- Update `templates/demo/lemma.html`, `static/js/demo/ishuman-demo.js`,
`static/css/demo/ishuman-demo.css`, and hub context in
`api/ishuman_demo.py` (may need new config for tour deep links).

**Acceptance:** non-dev path never requires the hub dashboard; builder lane
retains 100% of current functionality; `tests/test_demo_assurance_hub.py` and
`tests/test_ishuman_demo.py` updated and green.

### Phase 6 — Docs and scripts

- Rewrite `docs/demo/ISHUMAN_PRESENTER_SCRIPT.md` around the user-lane beats,
with a talk track a non-technical presenter can read verbatim (plain
sentences from the Phase 1 table, no reason codes).
- Update `docs/demo/README.md` recording checklist to the new beat order;
keep the Enforce/builder checklist as a separate section.
- Update `docs/demo/PRESALE_DEMO_SCRIPT.md` only where Phase 2 changed step
order.
- Add a "hand-the-laptop-over" one-pager: the 7 beats as bullets, one
sentence each, so anyone can give the demo.

**Acceptance:** presenter script contains zero snake_case codes; README URLs
and env vars unchanged unless a phase added one.

## Testing and deploy checklist (every phase)

1. Run demo-related tests with the CI env
  (`DATABASE_URL=sqlite:///:memory:` + `LEMMA_`* test secrets):
   `tests/test_ishuman_demo.py tests/test_demo_assurance_hub.py tests/test_demo_relying_site_app.py`.
2. Run `tests/test_ishuman_demo_smoke_lifecycle.py`; keep
  `.github/workflows/ishuman-demo-smoke.yml` green.
3. Manual pass on staging (`demo.lemma.id/demo`) with
  `LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY=true` for the IDV beat.
4. Demo-site changes deploy via subtree push (see file map); confirm SDK
  still loads from `LEMMA_ORIGIN` and `?tour=presale` still works.
5. Mobile check: the user lane must work on a phone (screenshots
  `demo-12`/`demo-13` are the current mobile baseline).

## Explicitly out of scope

- Agent Ops / `/demo/firewall` (operator-only, separate demo).
- Any change to verification, ledger, or session security logic beyond
resequencing when contact fields are collected (Phase 2).
- New SDK surface. The demo must keep exercising the public quickstart path.

