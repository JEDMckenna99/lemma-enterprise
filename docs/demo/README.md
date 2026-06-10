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

The public `/demo/ishuman` route demonstrates reusable proof-of-humanity using the actual isHuman stack:

- `POST /api/ishuman/start-verification` starts the Stripe Identity prototype IDV rail.
- `GET /api/ishuman/verification-status/<session_id>` returns the signed master `isHuman` credential after webhook completion.
- The browser wallet stores the master credential locally.
- `IsHumanVerifier` requests site-specific credentials through `/wallet/bridge`.
- `/api/ishuman/derive-site-proof` derives different PPIDs for `tickets-demo.lemma.id` and `trials-demo.lemma.id`.
- Demo wrappers under `/api/demo/ishuman/*` apply site-local blocks. Network revocation drill endpoints require `LEMMA_ISHUMAN_NETWORK_REVOCATION_ENABLED=1`.

## Required environment variables

- `STRIPE_SECRET_KEY`: Stripe account key with Identity enabled.
- `STRIPE_IDENTITY_WEBHOOK_SECRET`: webhook secret for `/api/webhooks/stripe-identity`.
- `ISHUMAN_RETURN_URL`: optional default return URL. The demo passes `/demo/ishuman?verification_return=true` explicitly.
- `LEMMA_ISHUMAN_NETWORK_REVOCATION_ENABLED=1`: optional. Enables tier-2 network revocation endpoints and the demo network drill.
- `LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN`: optional. Required only for the live **Approve network revocation** button when tier 2 is enabled.
- `LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY=true`: optional. Enables the guarded Stripe test-mode completion helper.
- `LEMMA_ISHUMAN_DEMO_TEST_TOKEN`: optional but required when test-mode completion is enabled. Pass this in the demo UI or as `X-Demo-Test-Token`.

## Recording checklist

1. Load `/demo/ishuman`.
2. Click **Create or unlock wallet** and complete the passkey prompt.
3. Click **Start Stripe Identity demo rail** and complete the Stripe Identity flow.
4. Return to the demo and click **Poll and store master proof** if it does not run automatically.
5. Click **Verify both demo sites** and show the two different PPIDs.
6. Click **Block ticketing PPID** and show ticketing denied while free trial remains valid.
7. Optional (tier 2 only): set `LEMMA_ISHUMAN_NETWORK_REVOCATION_ENABLED=1`, click **Request network review**, then approve network revocation to show both sites denied.

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

Both load the hosted verifier from `https://lemma.id/sdk/ishuman-verifier.js` and call `IsHumanVerifier` with distinct site bindings:

- `tickets-demo.lemma.id`
- `trials-demo.lemma.id`

Use these after creating/storing a master proof through `https://lemma.id/demo/ishuman` to show real separate origins requesting site-private credentials from the Lemma wallet bridge.
