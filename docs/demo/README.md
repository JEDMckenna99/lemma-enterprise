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
