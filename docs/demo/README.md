# isHuman Demo Playground

## What this proves

The public **`/demo`** route (alias `/demo/ishuman`) demonstrates the Lemma
isHuman integration flow in three concepts: **Create**, **Verify**, **Enforce**: not Agent Ops.

When one-PPID assurance flags are enabled on staging:

- **Create**: passkey wallet + provisional person root (no IDV required to start).
- **Verify**: hub derives distinct site PPIDs via `verifyForBackend`; Heroku demo sites use **Sign in with lemma.id** → `POST /api/login` → site session cookie; soft actions verify locally until fresh passkey step-up (presale claim).
- **Enforce**: set assurance (`passkey` → `ishuman`), site doubt, and site ban via `/api/demo/ishuman/*`. Hub Enforce attaches the last verified site `presentation`; mutations are allowed when the presentation PPID matches the target (**self-scoped**) or the caller is **SiteAdmin / platform operator** for `site_demo_*`. After Didit IDV, re-verify with `requiredAssurance: 'ishuman'`: **same PPID**, assurance flips to `ishuman`.

Legacy IDV-first copy remains when `assurance_demo_mode` is false (flags off).

## URLs

| Surface | URL |
| ------- | --- |
| Demo hub | https://lemma.id/demo |
| Demo hub (alias) | https://lemma.id/demo/ishuman |
| Staging hub | https://demo.lemma.id/demo |
| Ticketing relying site | https://lemma-demo-tickets-1d3d7411af33.herokuapp.com |
| Free-trial relying site | https://lemma-demo-trials-7090f46cae0d.herokuapp.com |
| Custom domains (when configured) | `tickets-demo.lemma.id`, `trials-demo.lemma.id` |

Both relying sites load the hosted verifier from your configured `LEMMA_ORIGIN`.
Sign-in uses `verifyForBackend` once, then the site issues an HttpOnly session cookie.
High-value presale claim still uses `requireFreshPasskey: true`. Site policy defaults
from `LEMMA_DEMO_REQUIRED_ASSURANCE` (default `passkey`).

> **Agent Ops demo** (proof-constrained authorization with runtime kill/revoke)
> lives separately at `/demo/firewall` and is operator-only, not the public
> isHuman integration demo.

## Required environment variables

- `LEMMA_ONE_PPID_ASSURANCE_MODEL=1` and `LEMMA_PASSKEY_ASSURANCE_ENABLED=1`, enable assurance demo on staging.
- `LEMMA_ISHUMAN_DIDIT_ENABLED=true`, enable Didit as the IDV rail.
- `DIDIT_API_KEY`, `DIDIT_WORKFLOW_ID`, Didit session creation.
- `DIDIT_WEBHOOK_SECRET`, webhook verification for `/api/webhooks/didit-identity`.
- `ISHUMAN_RETURN_URL`: optional default return URL.
- `LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY=true`: optional staging helper to complete human proof without live IDV.
- `LEMMA_ISHUMAN_DEMO_TEST_TOKEN`: optional; required when test-mode completion is enabled.
- `LEMMA_DEMO_TICKETS_URL` / `LEMMA_DEMO_TRIALS_URL`: override Heroku demo site URLs in hub config.

Demo Heroku apps:

- `LEMMA_ORIGIN`, lemma.id or staging hub origin (must serve SDK + API).
- `LEMMA_DEMO_REQUIRED_ASSURANCE=passkey`, site policy (ticketing can require human proof via hub Enforce chapter).

Legacy Stripe Identity keys (`STRIPE_SECRET_KEY`, `STRIPE_IDENTITY_WEBHOOK_SECRET`)
are migration-only for document-root recovery; do not provision them for new demos.

## Recording checklist (Create · Verify · Enforce)

1. Load `/demo` on staging (`assurance_demo_mode: true` in config).
2. **Create**: Create passkey wallet (no IDV popup). Note: continuity only, not unique humanness.
3. **Verify**: Verify both sites; show different PPIDs and `assurance: passkey`. Optional: open Developer view for signed presentations; open ticketing + trials Heroku demos.
4. **Enforce: set assurance**: Require human proof on ticketing → show valid-but-insufficient denial → complete Didit IDV (or staging test-verify) → re-verify with **same PPID** at `ishuman`.
5. **Enforce: doubt**: Mark ticketing doubtful (`doubt_required`); resolve with `verifyFreshForBackend()`. Works whether the user only has passkey presence or already has a human proof.
6. **Enforce: ban**: Ban ticketing PPID (`site_blocked`); confirm fresh verification does not clear the ban. Trials stays verified throughout.

## Legacy recording checklist (flags off)

1. Load `/demo`.
2. Create lemma.id via Didit IDV popup.
3. Verify both demo sites (IDV-first flow).
4. Ban ticketing; confirm trials still valid.

## Demo language guardrail

Use: "This demo uses Didit as the IDV rail."

Prefer: **create**, **verify**, **set assurance** / **require human proof**, **doubt**, **ban** (site block).

Avoid: **escalate**, five-act chapter names, stamps as the hub spine.

Do not use: "Stripe-approved", "Stripe-backed network", or "Stripe partnership" unless a provider agreement is in place.

## Automated test-mode path (staging only)

For a fully automated test-mode recording on non-production, configure:

```bash
LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY=true
LEMMA_ISHUMAN_DEMO_TEST_TOKEN=<random local/demo secret>
```

Then:

1. Start the Didit IDV flow (or skeleton IDV when Didit is unavailable locally).
2. Enter the test token and click **Test mode: complete verification**.
3. The demo marks the matching internal session verified, issues the real signed master `isHuman` credential, stores it in the wallet, and continues through the same verifier/PPID/site-ban flow.

This helper is guarded by an explicit demo token and non-production `ENVIRONMENT`. Do not enable test-verify on production.

## Site enforcement note

Network-wide revocation is **retired**. Demo and production endpoints for
network-revoke return HTTP 410 `network_revocation_retired`. Use site-block for
persistent per-site enforcement drills.

## Presale deep link (Enforce in the wild)

The presale tour at `?tour=presale` demonstrates **presence stamps** and action-level enforcement on a relying site, not a separate hub story. See `PRESALE_DEMO_SCRIPT.md`.
