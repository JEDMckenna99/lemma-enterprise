# isHuman integration guide for AI coding agents

> **Audience:** AI coding agents (Cursor, Copilot, Claude Code, etc.) helping a developer add [lemma.id proof of humanity](https://lemma.id/docs) to a web platform.
>
> **Goal:** Gate sensitive actions behind a cryptographically verified human check using site-private PPIDs — without building KYC, without customer webhooks, and without storing government ID data.

## Start here

| Resource | URL |
|----------|-----|
| Human-readable docs | https://lemma.id/docs |
| This guide (machine-oriented) | https://lemma.id/docs/integration/ISHUMAN_AGENT_INTEGRATION.md |
| Browser SDK | https://lemma.id/sdk/ishuman-verifier.js |
| JS verifier (backend) | https://lemma.id/sdk/lemma-ishuman-verify.mjs |
| Python verifier (backend) | https://lemma.id/sdk/lemma_ishuman_verify.py |
| Live demo | https://lemma.id/demo/ishuman |
| API key manager (abuse only) | https://lemma.id/developer/external-api-keys |
| Pointer file | https://lemma.id/llms.txt |

**Not public:** Agent Ops (lemma-cli, Lemma Firewall, runtime control plane) is operator-only and out of scope for relying-site integration.

---

## What you are building

1. **Browser:** Load `ishuman-verifier.js`, create `IsHumanVerifier({ siteId })`, call `verify({ autoProvision: true })` before protected actions.
2. **Backend:** Accept a signed presentation or stamp from the client and verify locally with `@lemma/ishuman-verify` or `lemma_ishuman_verify.py`.
3. **Optional:** Register a site API key only when the developer needs server-side PPID blocks.

lemma.id runs IDV (Didit by default) in a Lemma-hosted popup. **The relying site does not configure webhooks, Didit, or Stripe Identity.**

---

## Non-negotiable guardrails

Apply these on every integration. Do not skip or "simplify" them.

### `siteId` = canonical hostname

- Set `siteId` to the hostname users see in the browser (e.g. `app.example.com`).
- Normalize: lowercase, no scheme/path/port; strip `www.` when that matches how users reach the app.
- On customer sites, default to `window.location.hostname`.
- **Do not** use internal `site_...` database IDs as `siteId`. Those are for API keys and ownership — not SDK binding.
- Staging and production hostnames derive **different PPIDs**. Use the exact hostname per environment.

### Fail closed

- If `verify()` returns `human: false`, deny the action. Do not fall back to anonymous access.
- On signup/account creation, **never trust a bare `ppid` from the client** without cryptographic verification (see trust tiers below).

### Credential invariants

- Timestamps stay numeric; booleans stay booleans.
- Preserve site binding in issued credentials — do not silently coerce mismatched `siteId` / `site_domain`.
- Store `ppid` on the user record as an opaque site-private identifier, not as KYC data.

### What the developer does **not** need

- No lemma.id webhook URL on their servers.
- No API key for basic human verification.
- No wallet secret on the relying-site backend.
- No storage of legal name, DOB, document images, or selfies.

---

## Integration checklist

Work through these in order. Stop and ask the developer if hostname or trust tier is unclear.

- [ ] **1. Identify protected actions** — signup, posting, checkout, voting, account recovery, etc.
- [ ] **2. Set `siteId`** — canonical hostname for each environment.
- [ ] **3. Add browser SDK** — script tag or bundler import from `https://lemma.id/sdk/ishuman-verifier.js`.
- [ ] **4. Gate entry points** — `await verifier.verify({ autoProvision: true })` on first-touch flows; fail closed.
- [ ] **5. Choose backend trust tier** (see below) — default to **T2 (verifyStamp)** for signup.
- [ ] **6. Bind `ppid` to account** — store on user row after server verification.
- [ ] **7. Optional audit stamps** — `stamp(payload, { includeCredential: true })` on actions the developer logs.
- [ ] **8. Optional abuse controls** — API key + `POST /api/ishuman/site-block` when bans must survive browser clears.

---

## Browser integration

### Minimal gate (low-risk UX only)

```html
<script src="https://lemma.id/sdk/ishuman-verifier.js"></script>
<script>
  const verifier = new IsHumanVerifier({ siteId: 'app.example.com' });

  async function requireHuman() {
    const result = await verifier.verify({ autoProvision: true });
    if (!result.human) throw new Error(result.reason || 'not_verified');
    return result.ppid;
  }
</script>
```

### Recommended signup flow (T2 — server verify)

```html
<script src="https://lemma.id/sdk/ishuman-verifier.js"></script>
<script>
  const verifier = new IsHumanVerifier({ siteId: 'app.example.com' });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const { ok, presentation, ppid } = await verifier.verifyForBackend({ autoProvision: true });
    if (!ok) { alert('Verification required'); return; }
    await fetch('/api/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, presentation }),
    });
  });
</script>
```

### SDK constructor options

| Option | Default | Notes |
|--------|---------|-------|
| `siteId` | `window.location.hostname` | **Required** — canonical hostname binding |
| `lemmaOrigin` | `https://lemma.id` | Override only for non-production testing |
| `autoProvision` | `false` | Prefer passing `{ autoProvision: true }` per call on entry points |
| `debug` | `false` | SDK console logging |

### Key methods

| Method | Use |
|--------|-----|
| `verify({ autoProvision })` | Primary human check; may open Lemma popup on first visit |
| `verifyForBackend({ autoProvision })` | Returns `{ ok, presentation, ppid }` for server-side verify |
| `verifyFreshForBackend()` | Deliberate fresh IDV for a site-reported `doubt_required` decision |
| `stamp(payload, { includeCredential: true })` | Attach durable audit evidence to your events |
| `getPPID()` | Read cached PPID after initial verify (no popup by default) |

### Common `verify()` reasons

| Reason | Meaning |
|--------|---------|
| `valid`, `vc_valid`, `session_valid` | Success |
| `no_credential`, `site_proof_required`, `wallet_locked` | Needs popup — use `autoProvision: true` |
| `expired` | Ordinary 30-day renewal; may open the Lemma popup when auto-provisioning |
| `revoked`, `invalid_signature`, `site_blocked` | Deny; a site block never starts recovery automatically |
| `doubt_required` | Deny the current action, then deliberately call `verifyFreshForBackend()` |
| `idv_cancelled` | User closed popup — prompt retry / allow popups |

---

## Backend trust tiers

Pick one per endpoint. **Do not default signup to T1.**

| Tier | Client sends | Server verifies | Use when |
|------|--------------|-----------------|----------|
| **T1** | `{ ppid }` only | None | Low-risk gates only (waitlists, soft limits) |
| **T2** (recommended) | `presentation` from `verifyForBackend()` or `stamp(..., { includeCredential: true })` | Local `verify()` / `verifyStamp()` | Signup, account creation, moderate trust |
| **T3** | Full presentation + session assertion | Local verify with session required, or `POST /api/ishuman/verify-presentation` | High-trust / financial actions |

### Python backend (T2)

```python
# pip install lemma-ishuman-verify
# or: curl -O https://lemma.id/sdk/lemma_ishuman_verify.py
from lemma_ishuman_verify import VerificationContext

ctx = VerificationContext(site_id="app.example.com")

@app.post("/api/signup")
def signup():
    body = request.get_json() or {}
    result = ctx.verify(body["presentation"])
    if not result.ok:
        return {"error": result.reason}, 403
    # create account bound to result.ppid
```

### Node / Workers backend (T2)

```javascript
import { createVerifier } from "https://lemma.id/sdk/lemma-ishuman-verify.mjs";
// npm: @lemma/ishuman-verify

const verifier = createVerifier({ siteId: "app.example.com" });

app.post("/api/signup", async (req, res) => {
  const result = await verifier.verify(req.body.presentation);
  if (!result.ok) return res.status(403).json({ error: result.reason });
  // create account bound to result.ppid
});
```

### Audit log re-verification

```python
check = ctx.verify_stamp(log_row["lemma"])  # from stamp(..., includeCredential=True)
if not check.ok:
    flag_suspicious(log_row, check.reason)

# Old rows: durable=True ignores aged session assertions
audit = ctx.verify_stamp(old_row["lemma"], durable=True)
```

Backend verification is **local-first**: one cached fetch to `GET /api/revocation/bloom-filter` every ~15 minutes — not per user request.

---

## Integration flow (end-to-end)

```
Developer page                Lemma popup              Developer backend
     |                             |                          |
     | verify({autoProvision})     |                          |
     |--------------------------->| wallet unlock + IDV      |
     |                             | issue site credential    |
     |<---------------------------|                          |
     | { human, ppid, presentation }                          |
     |------------------------------------------------------->|
     |                             |              verify(presentation) locally
     |                             |              store ppid on account
```

Steps:

1. Client calls `verify({ autoProvision: true })` before a protected action.
2. If no proof exists, popup at `/wallet/ishuman-idv` runs wallet unlock + live IDV.
3. lemma.id issues master + site-bound credential for `siteId`.
4. SDK validates signature, expiry, revocation locally.
5. Client sends `presentation` or stamp to **your** backend; backend verifies cryptographically.

---

## Site registration and API keys

| Goal | Registration required? |
|------|------------------------|
| Gate with `verify()` | **No** — set `siteId` to hostname only |
| `POST /api/ishuman/site-block` | **Yes** — API key from key manager |

When registering for abuse APIs, `site_domain` must match SDK `siteId` after normalization.

---

## Abuse and revocation

Do **not** rely on the abuser's browser to enforce bans.

1. **Immediate app deny** — 403 / sign-out in your app.
2. **Site block (canonical)** — `POST /api/ishuman/site-block` with `X-API-Key`:

```bash
curl -X POST https://lemma.id/api/ishuman/site-block \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_SITE_API_KEY" \
  -d '{"ppid":"did:lemma:ppid_...","reason":"Terms violation"}'
```

Site blocks are persistent. Fresh IDV, wallet recovery, document renewal, and
credential rotation do not clear them. Only the authenticated
`POST /api/ishuman/site-unblock` operation removes a site block.

For a temporary challenge instead of a ban, use `POST /api/ishuman/site-doubt`.
Your backend can expose the resulting `{ blocked, doubt_required }` decision to
the SDK through `isBlockedLocally`; when `verify()` returns `doubt_required`,
invoke `verifyFreshForBackend()`. A successful fresh IDV clears only the
matching doubt when it derives the same site PPID.

Network-wide enumeration revocation is retired. The legacy customer, admin,
and demo endpoints return HTTP 410 with `network_revocation_retired`.

Site credentials expire after 30 days. Following wallet/master compromise, an
already-issued credential can remain locally valid until expiry unless its
relying site blocks the PPID.

---

## Anti-patterns (do not implement)

- Trusting `ppid`, `X-Credential-ID`, or email headers without verifying a signed credential.
- Using `site_abc123` internal IDs as `siteId`.
- Mixing `www.example.com` and `example.com` unintentionally across environments.
- Calling lemma.id on every page view for verification (SDK verifies locally after bloom sync).
- Putting `wallet_secret` on the relying-site server.
- Expecting lemma.id webhooks on the developer's origin for IDV completion.
- Skipping `autoProvision: true` on signup/first-touch flows (users get stuck on `no_credential`).

---

## HTTP API reference (relying-site subset)

Most integrations use **only the browser SDK + local backend verify**. These endpoints are optional:

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/api/ishuman/verify-presentation` | None | Optional server re-verify (prefer local packages) |
| `POST` | `/api/ishuman/site-block` | `X-API-Key` | Site-scoped PPID ban |
| `POST` | `/api/ishuman/site-unblock` | `X-API-Key` | Remove site block |
| `GET` | `/api/ishuman/check` | `X-API-Key` | Block/revocation status for a PPID |
| `GET` | `/api/ishuman/site-blocks` | `X-API-Key` | List active blocks |
| `GET` | `/api/revocation/bloom-filter` | None | Signed trust list + bloom (backend verifiers cache this) |

Wallet-assertion endpoints (`start-verification`, `derive-site-proof`, etc.) are used by the Lemma popup — **not** by typical relying-site server code.

---

## Framework notes

Adapt the same pattern; do not change the crypto contract.

| Stack | Client | Server |
|-------|--------|--------|
| React / Next.js | Load SDK in client component or `useEffect`; call `verifyForBackend` before submit | Route handler verifies `presentation` |
| Vue / Nuxt | Same — client-only for SDK | Server middleware or API route |
| Rails | Stimulus/vanilla JS for SDK | Controller action + `lemma_ishuman_verify` |
| Django | Template script or JS bundle | View + `VerificationContext` |
| PHP | Script tag + fetch to your API | Include Python helper or port verify logic |

For SSR frameworks, keep `IsHumanVerifier` in **client components only** — it uses `window`, popups, and browser crypto.

---

## Validation before finishing

Confirm with the developer:

- [ ] `siteId` matches production hostname users actually visit.
- [ ] Protected actions fail closed when verification fails.
- [ ] Signup/account paths use T2+ (presentation verified on server).
- [ ] `ppid` stored on account; no KYC fields stored.
- [ ] Popup flows work on first visit (`autoProvision: true`).
- [ ] If abuse APIs used, API key `site_domain` matches `siteId`.
- [ ] Test on `/demo/ishuman` or staging hostname before production.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Different PPIDs across environments | Expected — hostname binding is intentional |
| Persistent `no_credential` | Add `autoProvision: true` on entry-point calls |
| Block not applying | API key `site_domain` must match `siteId` exactly |
| `site_id_mismatch` on backend | Server `site_id` must equal client `siteId` |
| `idv_cancelled` | User closed popup; allow popups and retry |
| `revocation_data_untrusted` | Clock skew or stale cache; retry; check system time |

---

## Privacy summary (for developer communication)

- User completes live IDV once in a Lemma popup.
- Relying site receives `{ human, ppid }` — never government ID, selfie, or legal name.
- Each site gets a **pairwise-unlinkable** PPID derived from verified-person root + hostname.
- Audit stamps and action logs stay in **the developer's** systems.

For the full human-readable reference, see https://lemma.id/docs .
