# isHuman integration guide for AI coding agents

> **Audience:** AI coding agents (Cursor, Copilot, Claude Code, etc.) helping a developer add **isHuman** human assurance and the [lemma.id private proof layer](https://lemma.id/docs) to a web platform.
>
> **Goal:** Give the platform a site-private PPID for account continuity, plus **isHuman** assurance for one-human-per-account enforcement when Sybil resistance matters, without building KYC, without customer webhooks, and without storing government ID data.

## Start here

| Resource | URL |
|----------|-----|
| Human-readable docs | https://lemma.id/docs |
| This guide (machine-oriented) | https://lemma.id/docs/integration/ISHUMAN_AGENT_INTEGRATION.md |
| Browser SDK | https://lemma.id/sdk/proof-verifier.js |
| JS verifier (backend) | https://lemma.id/sdk/lemma-ishuman-verify.mjs |
| Python verifier (backend) | https://lemma.id/sdk/lemma_ishuman_verify.py |
| Live demo | https://lemma.id/demo |
| API key manager (abuse only) | https://lemma.id/developer/external-api-keys |
| Pointer file | https://lemma.id/llms.txt |

**Not public:** Agent Ops (lemma-cli, Lemma Firewall, runtime control plane) is operator-only and out of scope for relying-site integration.

---

## What you are building

1. **Browser:** Load `proof-verifier.js`, create `ProofVerifier({ siteId })`, call `verify({ autoProvision: true })` before protected actions.
2. **Account binding:** Store the returned site-private `ppid` as the platform's durable enforcement handle for that user.
3. **Backend:** Accept a signed presentation or stamp from the client and verify locally with `@lemma/ishuman-verify` or `lemma_ishuman_verify.py`.
4. **Assurance policy:** Use `passkey` for continuity when that is enough (not Sybil-resistant alone). Require `ishuman` when the action needs one verified human behind the account, such as Sybil-resistant signup, trials, ticketing, payouts, or recovery after abuse.
5. **Optional:** Register a site API key only when the developer needs server-side PPID blocks.

lemma.id runs wallet unlock, proof issuance, and IDV step-up (Didit by default) in a Lemma-hosted popup. **The relying site does not configure webhooks, Didit, or Stripe Identity.**

---

## Non-negotiable guardrails

Apply these on every integration. Do not skip or "simplify" them.

### `siteId` = canonical hostname

- Set `siteId` to the hostname users see in the browser (e.g. `app.example.com`).
- Normalize: lowercase, no scheme/path/port; strip `www.` when that matches how users reach the app.
- On customer sites, default to `window.location.hostname`.
- **Do not** use internal `site_...` database IDs as `siteId`. Those are for API keys and ownership, not SDK binding.
- Staging and production hostnames derive **different PPIDs**. Use the exact hostname per environment.

### Fail closed

- If `verify()` returns `human: false`, deny the action. Do not fall back to anonymous access.
- When policy requires IDV-backed humanness, pass `requiredAssurance: 'ishuman'` and verify `assurance === 'ishuman'` on the backend, do not rely on `human: true` alone (passkey success also sets `human: true`).
- On signup/account creation, **never trust a bare `ppid` from the client** without cryptographic verification (see trust tiers below).

### Credential invariants

- Timestamps stay numeric; booleans stay booleans.
- Preserve site binding in issued credentials, do not silently coerce mismatched `siteId` / `site_domain`.
- Store `ppid` on the user record as an opaque site-private identifier, not as KYC data.

### What the developer does **not** need

- No lemma.id webhook URL on their servers.
- No API key for basic human verification.
- No wallet secret on the relying-site backend.
- No storage of legal name, DOB, document images, or selfies.

---

## Integration checklist

Work through these in order. Stop and ask the developer if hostname or trust tier is unclear.

- [ ] **1. Identify protected actions**: signup, posting, checkout, voting, account recovery, etc.
- [ ] **2. Set `siteId`**: canonical hostname for each environment.
- [ ] **3. Add browser SDK**: script tag or bundler import from `https://lemma.id/sdk/proof-verifier.js`.
- [ ] **4. Gate entry points**: `await verifier.verify({ autoProvision: true })` on first-touch flows; fail closed.
- [ ] **5. Choose backend trust tier** (see below), default to **T2 (verifyStamp)** for signup.
- [ ] **6. Bind `ppid` to account**: store on user row after server verification.
- [ ] **7. Optional audit stamps**: `stamp(payload, { includeCredential: true })` on actions the developer logs.
- [ ] **8. Optional abuse controls**: API key + `POST /api/ishuman/site-block` when bans must survive browser clears.

---

## Browser integration

`ProofVerifier` is the primary browser class. The legacy `IsHumanVerifier` class
and `/sdk/ishuman-verifier.js` URL remain supported as compatibility aliases.

### Minimal gate (low-risk UX only)

```html
<script src="https://lemma.id/sdk/proof-verifier.js"></script>
<script>
  const verifier = new ProofVerifier({ siteId: 'app.example.com' });

  async function requireHuman() {
    const result = await verifier.verify({ autoProvision: true });
    if (!result.human) throw new Error(result.reason || 'not_verified');
    return result.ppid;
  }
</script>
```

### Low-friction account-binding flow (T2: passkey continuity, server verify)

Use **passkey assurance** for low-friction signup and continuity. Extract the account
PPID from the **verified server result** (`result.ppid`), never from the parallel client
`ppid` field alone.

```html
<script src="https://lemma.id/sdk/proof-verifier.js"></script>
<script>
  const verifier = new ProofVerifier({
    siteId: 'app.example.com',
    isBlockedLocally: async (ppid) => {
      const res = await fetch('/api/policy/check?ppid=' + encodeURIComponent(ppid));
      const data = await res.json();
      return { blocked: !!data.blocked, doubt_required: !!data.doubt_required };
    },
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const { ok, presentation } = await verifier.verifyForBackend({
      autoProvision: true,
      requiredAssurance: 'passkey',
    });
    if (!ok) { alert('Verification required'); return; }
    await fetch('/api/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, presentation }),
    });
  });
</script>
```

Require `requiredAssurance: 'ishuman'` when Sybil resistance matters (trials, ticketing,
payouts). The PPID stays stable when upgrading from passkey to isHuman on the same wallet.

### Sybil-resistant signup (T2: isHuman)

```html
<script src="https://lemma.id/sdk/proof-verifier.js"></script>
<script>
  const verifier = new ProofVerifier({ siteId: 'app.example.com' });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const { ok, presentation } = await verifier.verifyForBackend({
    autoProvision: true,
    requiredAssurance: 'ishuman',
  });
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
| `siteId` | `window.location.hostname` | **Required**: canonical hostname binding |
| `lemmaOrigin` | `https://lemma.id` | Override only for non-production testing |
| `autoProvision` | `false` | Prefer passing `{ autoProvision: true }` per call on entry points |
| `debug` | `false` | SDK console logging |

### Key methods

| Method | Use |
|--------|-----|
| `verify({ autoProvision, requiredAssurance })` | Primary verification check; may open Lemma popup on first visit |
| `verifyForBackend({ autoProvision, requiredAssurance })` | Returns `{ ok, presentation, ppid, assurance }` for server-side verify |
| `verifyFreshForBackend()` | Deliberate fresh IDV for a site-reported `doubt_required` decision |
| `stamp(payload, { includeCredential: true })` | Attach durable audit evidence to your events |
| `stampAction(payload, { action, method, path })` | Attach action-bound proof for fraud-sensitive server mutations |
| `getPPID()` | Read cached PPID after initial verify (no popup by default) |

### Common `verify()` reasons

| Reason | Meaning |
|--------|---------|
| `valid`, `vc_valid`, `session_valid` | Success |
| `no_credential`, `site_proof_required`, `wallet_locked` | Needs popup, use `autoProvision: true` |
| `expired` | Ordinary 30-day renewal; may open the Lemma popup when auto-provisioning |
| `revoked` | Credential in global revocation bloom, deny now; with `autoProvision: true` the SDK opens fresh-IDV recovery (new credential id, same PPID when wallet/person unchanged) |
| `invalid_signature` | Hard deny, tampered, corrupted, or unverifiable credential; no automatic recovery |
| `site_blocked` | Permanent site ban, deny; never starts recovery automatically (only `POST /api/ishuman/site-unblock` clears it) |
| `doubt_required` | Deny the current action, then deliberately call `verifyFreshForBackend()` |
| `idv_cancelled` | User closed popup, prompt retry / allow popups |

**`isBlockedLocally` errors fail closed:** if your policy callback throws or the fetch fails, the SDK treats the PPID as blocked (`site_blocked` on the next verify path). Implement the callback defensively and keep your policy endpoint highly available.

### `human` vs `assurance`

- `human` is the legacy/general success boolean, `true` when the requested assurance tier passed (including `passkey` or `ishuman`).
- `assurance` tells you which tier passed (`passkey`, `ishuman`, etc.). For Sybil-resistant signup, require `requiredAssurance: 'ishuman'` and verify the backend sees `assurance: ishuman`.
- Passkey success is useful for continuity; it is **not** IDV-backed humanness.

---

## Backend trust tiers

Pick one per endpoint. **Do not default signup to T1.**

### Backend `site_id` must match SDK `siteId`

Pass the same canonical hostname to `VerificationContext(site_id=...)` or `createVerifier({ siteId: ... })` that you set in the browser SDK. Offline verifiers **canonicalize on construction** (lowercase, strip `www.`, no scheme/path/port) and compare credential site binding using the same rules. Mismatches return `site_id_mismatch` even when the raw strings looked equivalent (`WWW.App.Example.com` vs `app.example.com`).

| Tier | Client sends | Server verifies | Use when |
|------|--------------|-----------------|----------|
| **T1** | `{ ppid }` only | None | Low-risk gates only (waitlists, soft limits) |
| **T2** (recommended) | `presentation` from `verifyForBackend()` or `stamp(..., { includeCredential: true })` | Local `verify()` / `verifyStamp()` | **Signup**, account creation, moderate trust |
| **T2+** | `stampAction(...)` envelope with `action_assertion` + `action_signature` | Local `verifyActionStamp()` / `verify_action_stamp()` + nonce replay store | **Mutations only**: checkout, withdrawals, posting, other fraud-sensitive server actions |
| **T3** | Full presentation + session assertion | Local verify with `requireSessionAssertion: true`, or `POST /api/ishuman/verify-presentation` | High-trust / financial actions needing live session proof |

### Install a backend verifier

Node.js, Deno, Bun, and Workers:

```bash
npm install @lemma/ishuman-verify
```

Python:

```bash
pip install lemma-ishuman-verify
# Or use the hosted single-file verifier:
curl -O https://lemma.id/sdk/lemma_ishuman_verify.py
```

Choose assurance independently from the transport tier: T2 means the backend
verifies a signed presentation. Set its policy to `passkey` for continuity or
`ishuman` when the endpoint must enforce one verified human per account.

### Python backend (T2 + site policy)

```python
# pip install lemma-ishuman-verify
from lemma_ishuman_verify import VerificationContext
from lemma_ishuman_site_policy import InMemorySitePolicyStore

ctx = VerificationContext(site_id="app.example.com", required_assurance="passkey")
policy = InMemorySitePolicyStore(blocked={"did:lemma:ppid_banned..."})

@app.post("/api/signup")
def signup():
    body = request.get_json() or {}
    result = ctx.verify_with_policy(body["presentation"], policy_store=policy)
    if not result.ok:
        return {"error": result.reason}, 403
    # create account bound to result.ppid (from verified presentation, not client ppid)
    if result.legacy_ppid:
        merge_provisional_account(result.legacy_ppid, result.ppid)
```

### Node / Workers backend (T2 + site policy)

```javascript
import { createVerifier, createInMemorySitePolicyStore } from "@lemma/ishuman-verify";

const verifier = createVerifier({ siteId: "app.example.com", requiredAssurance: "passkey" });
const policy = createInMemorySitePolicyStore({ blocked: new Set(["did:lemma:ppid_banned..."]) });

app.post("/api/signup", async (req, res) => {
  const result = await verifier.verifyWithPolicy(req.body.presentation, { policyStore: policy });
  if (!result.ok) return res.status(403).json({ error: result.reason });
  // bind account to result.ppid
});
```

### Remote site policy via lemma.id check API

When you register a site API key, prefer the server-only check store (cached `GET /api/ishuman/check`) over mirroring blocks in memory:

```python
from lemma_ishuman_site_policy import LemmaCheckPolicyStore

policy = LemmaCheckPolicyStore(
    site_id="app.example.com",
    api_key=os.environ["LEMMA_SITE_API_KEY"],
)
result = ctx.verify_with_policy(body["presentation"], policy_store=policy)
```

```javascript
import { createVerifier, createLemmaCheckPolicyStore } from "@lemma/ishuman-verify";

const verifier = createVerifier({ siteId: "app.example.com" });
const policy = createLemmaCheckPolicyStore({
  siteId: "app.example.com",
  apiKey: process.env.LEMMA_SITE_API_KEY,
});

const result = await verifier.verifyWithPolicy(req.body.presentation, { policyStore: policy });
```

Both stores fail closed when the check API is unavailable (`site_policy_unavailable`).

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

### Audit log re-verification

```python
check = ctx.verify_stamp(log_row["lemma"])  # from stamp(..., includeCredential=True)
if not check.ok:
    flag_suspicious(log_row, check.reason)

# Old rows: durable=True ignores aged session assertions
audit = ctx.verify_stamp(old_row["lemma"], durable=True)
```

### Action-bound server mutations (T2+)

```javascript
const event = await verifier.stampAction(
  { cartId, amountCents, currency },
  { action: 'checkout', method: 'POST', path: '/api/checkout', requiredAssurance: 'passkey' },
);
await fetch('/api/checkout', { method: 'POST', body: JSON.stringify(event) });
```

```python
from lemma_ishuman_verify import VerificationContext, InMemoryNonceStore

ctx = VerificationContext(site_id="app.example.com", required_assurance="passkey")
nonce_store = InMemoryNonceStore()

@app.post("/api/checkout")
def checkout():
    body = request.get_json() or {}
    result = ctx.verify_action_stamp(
        body,
        action="checkout",
        method=request.method,
        path=request.path,
        body=body,
        nonce_store=nonce_store,
    )
    if not result.ok:
        return {"error": result.reason}, 403
    return process_checkout(result.ppid, body)
```

Verification is **local-first**: one cached fetch to `GET /api/revocation/bloom-filter` every ~15 minutes, not per user request or per action.

### Fresh passkey for sensitive actions (policy, not assurance tier)

Use `requireFreshPasskey` when a passkey-tier user must prove **present** biometric/PIN
control for a specific mutation (code claims, withdrawals). This does **not** change
assurance tier, it adds a server-attested `fresh_passkey_attestation.v1` bound to an
opaque action commitment so lemma.id never receives action names, resource IDs, or bodies.

```javascript
// 1. Your backend issues a server nonce + optional action commitment helper
const challenge = await fetch('/api/presale/challenge', { method: 'POST', body: ... }).then(r => r.json());

// 2. Client stamps with fresh passkey ceremony
const event = await verifier.stampAction(payload, {
  action: 'claim_presale_code',
  method: 'POST',
  path: '/api/presale/claim-code',
  nonce: challenge.server_nonce,
  serverNonce: challenge.server_nonce,
  requireFreshPasskey: true,
  requiredAssurance: 'passkey',
});

// 3. Backend verifies stamp + attestation locally
result = ctx.verify_action_stamp(
  body,
  action='claim_presale_code',
  method='POST',
  path='/api/presale/claim-code',
  body=body,
  nonce_store=nonce_store,
  nonce_store_mode='required',
  require_fresh_passkey=True,
  server_nonce=body['server_nonce'],
)
```

**Replay protection:** configure `nonceStoreMode: 'required'` in production and use
`InMemoryNonceStore` only for tests. For multi-process deployments, inject
`RedisNonceStore` from `lemma_ishuman_nonce_store` and **await**
`nonceStore.consume(...)` — the Redis store is async and uses atomic `SET NX`.

**Live presale reference:** The tickets demo at [tickets-demo.lemma.id/?tour=presale](https://tickets-demo.lemma.id/?tour=presale) walks through challenge → `stampAction` register → fresh-passkey claim with a site-local one-code-per-PPID ledger. See the [public demo walkthrough](https://lemma.id/docs/demo/PRESALE_DEMO_SCRIPT.md).

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
| Gate with `verify()` | **No**: set `siteId` to hostname only |
| `POST /api/ishuman/site-block` | **Yes**: API key from key manager |

When registering for abuse APIs, `site_domain` must match SDK `siteId` after normalization.

---

## Abuse and revocation

Do **not** rely on the abuser's browser to enforce bans.

1. **Immediate app deny**: 403 / sign-out in your app.
2. **Site block (canonical)**: `POST /api/ishuman/site-block` with `X-API-Key`:

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
the SDK through `isBlockedLocally`, **call your own policy endpoint**, never
lemma.id directly from the browser (API keys are server-only). When
`verify()` returns `doubt_required`, invoke `verifyFreshForBackend()`. A
successful fresh IDV clears only the matching doubt when it derives the same
site PPID.

**Enforcement order on your backend:** cryptographic presentation verification →
canonical PPID extraction → convergence verification (if present) → site-policy
lookup for canonical **and** legacy PPIDs → business logic. Stable fail-closed
reasons: `site_blocked`, `doubt_required`, `site_policy_unavailable`,
`site_policy_not_configured`.

**Automatic doubt clear:** when a user completes fresh IDV via `verifyFreshForBackend()` and the derived site PPID matches the doubted PPID, lemma.id clears the active doubt during credential billing (`cleared_by: fresh_idv_same_ppid`). Site blocks are untouched. You may also clear explicitly with `POST /api/ishuman/site-doubt-clear`.

Site blocks are **not** in the global Bloom filter. Mirror blocks locally or use
`GET /api/ishuman/check` (server-only, with API key) via `LemmaCheckPolicyStore` (Python) or `createLemmaCheckPolicyStore` (Node/Workers).

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
| `POST` | `/api/ishuman/verify-presentation` | None | Optional server re-verify (prefer local packages); `required_assurance` defaults to `ishuman` |
| `POST` | `/api/ishuman/site-block` | `X-API-Key` | Site-scoped PPID ban |
| `POST` | `/api/ishuman/site-unblock` | `X-API-Key` | Remove site block |
| `POST` | `/api/ishuman/site-doubt` | `X-API-Key` | Temporary doubt (requires fresh IDV, not a ban) |
| `POST` | `/api/ishuman/site-doubt-clear` | `X-API-Key` | Explicitly clear an active doubt |
| `GET` | `/api/ishuman/site-doubts` | `X-API-Key` | List active doubts for the site |
| `GET` | `/api/ishuman/check` | `X-API-Key` | Block/revocation status for a PPID |
| `GET` | `/api/ishuman/site-blocks` | `X-API-Key` | List active blocks |
| `GET` | `/api/ishuman/site-binding-check` | None | Read-only hostname canonicalization + registration hint for SDK `siteId` alignment |
| `GET` | `/api/revocation/bloom-filter` | None | Signed trust list + bloom (backend verifiers cache this) |

Wallet-assertion endpoints (`start-verification`, `derive-site-proof`, etc.) are used by the Lemma popup, **not** by typical relying-site server code.

---

## Framework notes

Adapt the same pattern; do not change the crypto contract.

| Stack | Client | Server |
|-------|--------|--------|
| React / Next.js | Load SDK in client component or `useEffect`; call `verifyForBackend` before submit | Route handler verifies `presentation` |
| Vue / Nuxt | Same, client-only for SDK | Server middleware or API route |
| Rails | Stimulus/vanilla JS for SDK | Controller action + `lemma_ishuman_verify` |
| Django | Template script or JS bundle | View + `VerificationContext` |
| PHP | Script tag + fetch to your API | Include Python helper or port verify logic |

For SSR frameworks, keep `ProofVerifier` in **client components only**: it uses `window`, popups, and browser crypto.

---

## Assurance tiers and site-local input burn

One **stable PPID** per site subject; proof strength is **assurance**, not a second identifier.

| Policy | SDK | Backend verifier |
|--------|-----|------------------|
| Low-friction signup | `requiredAssurance: 'passkey'` | `required_assurance='passkey'` |
| Sybil-resistant signup / post-burn recovery | `requiredAssurance: 'ishuman'` | `required_assurance='ishuman'` |

```javascript
const { ok, ppid, assurance, presentation } = await verifier.verifyForBackend({
  autoProvision: true,
  requiredAssurance: 'passkey',
});
if (!ok) throw new Error('not_verified');
await fetch('/api/signup', { method: 'POST', body: JSON.stringify({ presentation, ppid, assurance }) });
```

**Site-local burn / re-anchor (Lemma does not store burn graphs):**

| Situation | Site action |
|-----------|-------------|
| Account created with passkey assurance | Store `ppid` + input fingerprints locally |
| Inputs burned; session is passkey-only | Gate restore behind `requiredAssurance: 'ishuman'` |
| User completes IDV step-up | Update the **same** account row; PPID unchanged |
| User recovers on new device after IDV | Match on PPID/presentation; rebind session |

These are lemma.id platform capabilities. A relying site does not configure
platform rollout flags; it explicitly requests the assurance its endpoint
requires and fails closed if that assurance is unavailable.

### PPID convergence (provisional → known person)

When a user already verified on wallet A creates a new provisional wallet B and
completes IDV, lemma.id rebinds B to the known person. The site PPID may change.
lemma.id issues a signed `ppid_convergence.v1` artifact on the next
`derive-site-proof` for that site. Your backend verifies it alongside the
presentation and receives `legacy_ppid` + canonical `ppid`.

**Merge recipe (transactional):**

1. Verify presentation + convergence artifact (`verify_with_policy`).
2. If `legacy_ppid` is present, look up the provisional account by `legacy_ppid`.
3. If found: merge rows to canonical `ppid`, carry forward site blocks/doubts from
   the legacy PPID, then delete or archive the provisional account.
4. If not found: create a new account for canonical `ppid` (user may have never
   visited your site with the provisional wallet).
5. Reject if convergence is invalid, wrong-site, expired, or tampered, fail closed.

Ordinary first IDV on the same wallet preserves PPID and emits **no** convergence artifact.

When convergence is present, the backend verifier validates its signed artifact;
the relying site does not call wallet-internal derivation endpoints directly.
See [One PPID, assurance tiers, and site-local input burn](https://lemma.id/docs/product/PASSKEY_STAMP_INPUT_BURN.md)
for the relying-site contract.

**Reference implementation:** [lemma.id integration demo](https://lemma.id/demo), passkey wallet → distinct site PPIDs → Heroku demo sites with `verifyStamp` → optional isHuman step-up (same PPID) → site-scoped revocation. Enable flags on staging before recording.

---

## Validation before finishing

Confirm with the developer:

- [ ] `siteId` matches production hostname users actually visit.
- [ ] Protected actions fail closed when verification fails.
- [ ] Signup/account paths use **T2** (presentation verified on server); reserve **T2+** (`stampAction`) for fraud-sensitive mutations.
- [ ] `ppid` stored on account; no KYC fields stored.
- [ ] Popup flows work on first visit (`autoProvision: true`).
- [ ] If abuse APIs used, API key `site_domain` matches `siteId`.
- [ ] Test on `/demo` or staging hostname before production.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Different PPIDs across environments | Expected, hostname binding is intentional |
| Persistent `no_credential` | Add `autoProvision: true` on entry-point calls |
| Block not applying | API key `site_domain` must match `siteId` exactly |
| `site_id_mismatch` on backend | Server `site_id` must canonicalize to the same hostname as client `siteId` (offline verifiers lowercase and strip `www.`) |
| `idv_cancelled` | User closed popup; allow popups and retry |
| `revocation_data_untrusted` | Clock skew or stale cache; retry; check system time |

---

## Privacy summary (for developer communication)

- User completes live IDV once in a Lemma popup.
- Relying site receives `{ human, ppid }`, never government ID, selfie, or legal name.
- Each site gets a **pairwise-unlinkable** PPID derived from verified-person root + hostname.
- Audit stamps and action logs stay in **the developer's** systems.

For the full human-readable reference, see https://lemma.id/docs .
