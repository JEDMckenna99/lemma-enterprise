# lemma.id Demo Playground

## What this proves

The public `/demo` route demonstrates proof-constrained authorization with live control-plane effects:

- `POST /api/demo/issue-proof` issues a real delegated credential through the production issuer endpoint.
- `POST /api/demo/verify` validates the presented credential, enforces scope/path bounds, and returns deterministic decision codes.
- `POST /api/demo/revoke` revokes the issued credential through the production revocation endpoint.
- `GET /api/demo/revocation-status` checks revocation status from the production status feed.

## Mapping to paper claims

- **Appendix A flow**: Human intent -> issuer -> runtime -> verifier -> action path is visualized in the hero diagram and updated from each live decision.
- **Appendix B timeline**: The timeline strip records issue, action checks, taint-epoch bump, and revoke events with runtime timestamps.
- **Section 14/15 action examples**: File read/write, workflow write, shell execution, and external egress checks are exposed as explicit action buttons.

## Security model in this route

- Demo endpoints use a backend service principal (`LEMMA_DEMO_SERVICE_AGENT_TOKEN`) and never expose this token to browsers.
- Runtime IDs and actions are hard allowlisted server-side.
- Any upstream control-plane failure returns deny/unavailable responses; the route does not fabricate allows.

## Required environment variables

- `LEMMA_DEMO_SERVICE_AGENT_TOKEN`: privileged service token used by demo proxy routes.
- `LEMMA_DEMO_BASE_URL`: defaults to `https://lemma.id`.
- `LEMMA_DEMO_ALLOWED_RUNTIMES`: comma-separated allowlist (default `openclaw-demo-runtime`).
- `LEMMA_DEMO_ISSUER_ID`: display + metadata issuer identifier for demo issue calls.
- `LEMMA_DEMO_SITE_ID`: demo site binding (default `lemma.id`).

## Manual validation checklist

1. Load `/demo` as anonymous visitor.
2. Click **Issue New Proof** and confirm `jti`, scope, and expiry are returned.
3. Run at least one allowed action and verify decision returns `allow`.
4. Click **Ingest External Docs** then retry with previous proof to observe stale deny behavior.
5. Click **Revoke Proof** and confirm next action attempt is denied.

---

# isHuman Demo

## What this proves

The public `/demo` route demonstrates the **one-PPID assurance model** when feature flags are enabled:

- Passkey wallet + provisional person root (no IDV on step 1).
- `verifyForBackend({ requiredAssurance: 'passkey' })` derives distinct site PPIDs with passkey assurance.
- Heroku demo sites stamp actions and verify with `POST /api/demo/action` + offline `verifyStamp`.
- Demo wrappers under `/api/demo/ishuman/*` apply site-local blocks and `require-ishuman` step-up (SiteDoubt).
- After IDV, re-verify with `requiredAssurance: 'ishuman'` — **same PPID**, assurance flips to `ishuman`.

Legacy IDV-first copy remains when `assurance_demo_mode` is false (flags off).

## Required environment variables

- `LEMMA_ONE_PPID_ASSURANCE_MODEL=1` and `LEMMA_PASSKEY_ASSURANCE_ENABLED=1` — enable assurance demo on staging.
- `STRIPE_SECRET_KEY`: Stripe account key with Identity enabled.
- `STRIPE_IDENTITY_WEBHOOK_SECRET`: webhook secret for `/api/webhooks/stripe-identity`.
- `ISHUMAN_RETURN_URL`: optional default return URL.
- `LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY=true`: optional staging helper for step 5 without live IDV.
- `LEMMA_ISHUMAN_DEMO_TEST_TOKEN`: optional; required when test-mode completion is enabled.
- `LEMMA_DEMO_TICKETS_URL` / `LEMMA_DEMO_TRIALS_URL`: override Heroku demo site URLs in hub config.

Demo Heroku apps:

- `LEMMA_ORIGIN` — lemma.id or staging hub origin (must serve SDK + API).
- `LEMMA_DEMO_REQUIRED_ASSURANCE=passkey` — site policy (ticketing escalates via hub step 5).

## Recording checklist (assurance workflow)

1. Load `/demo` on staging (`assurance_demo_mode: true` in config).
2. **Step 1** — Create passkey wallet (no IDV popup).
3. **Step 2** — Verify both sites; show different PPIDs and `assurance: passkey`.
4. **Step 3** — Open ticketing + trials demo sites; complete an action; show server-verified stamp in action log.
5. **Step 4** — Block ticketing PPID; recheck — ticketing denied, trials still human.
6. **Step 5** — Require isHuman on ticketing → complete IDV (or staging test-verify) → re-verify ticketing with ishuman; highlight **same PPID**.

## Legacy recording checklist (flags off)

1. Load `/demo`.
2. Create lemma.id via IDV popup.
3. Verify both demo sites (IDV-first flow).
4. Block ticketing; confirm trials still valid.

## Demo language guardrail

Use: "This demo uses Stripe Identity as the prototype IDV rail."

Do not use: "Stripe-approved", "Stripe-backed network", or "Stripe partnership" unless a provider agreement is in place.

## Automated Stripe test-mode path

For a fully automated test-mode recording, configure a Stripe test key plus:

```bash
LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY=true
LEMMA_ISHUMAN_DEMO_TEST_TOKEN=<random local/demo secret>
```

Then:

1. Click **Start Stripe Identity demo rail** to create a real Stripe test-mode VerificationSession.
2. Enter the test token and click **Test mode: complete verification**.
3. The demo marks the matching internal session verified, issues the real signed master `isHuman` credential, stores it in the wallet, and continues through the same verifier/PPID/site-block flow.

This helper is guarded by `sk_test_` Stripe keys and an explicit demo token. Do not enable it with live Stripe keys.

## Separate relying-site demo origins

The cross-site demo also has two standalone Heroku apps that act as third-party relying sites:

- Ticketing: `https://lemma-demo-tickets-1d3d7411af33.herokuapp.com`
- Free trial: `https://lemma-demo-trials-7090f46cae0d.herokuapp.com`

Both load the hosted verifier from your configured `LEMMA_ORIGIN` and call `verifyForBackend` with env-driven `LEMMA_DEMO_REQUIRED_ASSURANCE` (default `passkey`). Stamped actions POST to `/api/demo/action` for server-side `verifyStamp`.

- `tickets-demo.lemma.id`
- `trials-demo.lemma.id`

Use these after creating/storing a master proof through `https://lemma.id/demo` to show real separate origins requesting site-private credentials from the Lemma wallet bridge.
