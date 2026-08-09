# Continuity & abuse: site-private person proofs

lemma.id gives your backend a **verified, site-private `ppid` and assurance
level** so you can enforce one-human policy, stamp sensitive actions, and block
abusers so bans survive new accounts. Users mint presentations with a passkey;
you verify locally. **Keep your existing login** if you want — use lemma on gated
actions only.

Canonical contract: [ISHUMAN Agent Integration Guide](ISHUMAN_AGENT_INTEGRATION.md)

---

## What you get

| Primitive | Job |
|-----------|-----|
| **PPID** | Stable opaque account handle for one person on your hostname |
| **Assurance** | `passkey` = continuity; `ishuman` = IDV-backed one human per account |
| **Presentation** | Short-lived signed proof you verify on your server |
| **Action stamp** | Bind a mutation to PPID + assurance + nonce/time (T2+) |
| **Site-block** | Persistent ban keyed to PPID (survives browser clears) |

Passkey unlock mints presentations — it is the free pipe, not the product you sell.

---

## When to use lemma.id

Use lemma when you need **person continuity under abuse**:

- One trial / one code / one payout per human
- Post-ban enforcement (same person, new browser session)
- Fraud-sensitive mutations with auditable proof
- Pairwise-private account keys (no email from lemma, no cross-site correlation by RPs)

Do **not** need lemma for every page view. Gate specific actions; verify once per
action or per session policy.

---

## Keep your existing login

Many sites keep Google/OAuth/email sessions and add lemma only on T2/T2+ paths:

```
User (already logged in via your auth)
  └─ clicks "Claim trial" / "Get code"
       └─ ProofVerifier.verifyForBackend({ requiredAssurance: 'ishuman' })
            └─ POST presentation → your API
                 └─ verify locally → enforce on ppid → site-block if needed
```

Your session cookie and lemma proofs are independent layers.

---

## Assurance ladder (same PPID)

| Tier | Meaning | Use for |
|------|---------|---------|
| `passkey` | Continuity with lemma.id-bound person root | Low-friction gates, returning-user checks |
| `ishuman` | IDV-backed one verified human | Sybil-sensitive signup, trials, tickets, payouts |

Request `requiredAssurance` on **both** client and backend. PPID does not change when upgrading tiers.

---

## Integration pattern

1. **Identify gated actions** — claim, checkout, post, vote, payout, etc.
2. **Set `siteId`** — canonical hostname (`app.example.com`), not internal `site_...` ids.
3. **Client:** `verifyForBackend({ autoProvision: true, requiredAssurance: 'ishuman' })` from a user gesture.
4. **Server:** verify presentation with `@lemma.id/proof-verifier` or `lemma_proof_verifier.py` — **no per-request call to lemma.id**.
5. **Enforce:** policy on `result.ppid` + `result.assurance`; optional `stampAction` for mutations.
6. **Optional:** `POST /api/ishuman/site-block` when bans must persist across IDV/recovery.

Fail closed when verification fails. Never trust a bare client `ppid`.

---

## Site-block and doubt

Do **not** rely on the abuser's browser to enforce bans.

1. **Immediate deny** — 403 in your app.
2. **Site block (canonical)** — server-side, with API key:

```bash
curl -X POST https://lemma.id/api/ishuman/site-block \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_SITE_API_KEY" \
  -d '{"ppid":"did:lemma:ppid_...","reason":"Terms violation"}'
```

Site blocks persist across fresh IDV and credential rotation. Only
`POST /api/ishuman/site-unblock` clears them.

For a temporary challenge instead of a ban, use `POST /api/ishuman/site-doubt`.
Mirror policy locally or poll `GET /api/ishuman/check` (server-only).

Register a site and API key at [External API keys](https://lemma.id/developer/external-api-keys).
Keys are for **enforcement**, not for basic presentation verify.

---

## Action stamps (T2+)

For fraud-sensitive mutations (checkout, withdrawals, claims), attach an
action-bound proof:

```javascript
const event = await verifier.stampAction(payload, {
  action: 'claim_presale_code',
  method: 'POST',
  path: '/api/presale/claim',
});
// Send event to your backend; verify with verifyActionStamp() + nonce store
```

Stamps prove possession of the site signing key over canonical action fields —
use alongside presentation verify, not instead of it.

---

## Live examples

| Demo | Story |
|------|-------|
| [lemma.id/demo](https://lemma.id/demo) | Create · Enforce · continuity across sites |
| [tickets-demo presale](https://tickets-demo.lemma.id/?tour=presale) | Stamp + fresh passkey + one-code-per-PPID |

See [Presale demo script](../demo/PRESALE_DEMO_SCRIPT.md).

---

## Optional: sessions from the same presentation

If you want passwordless login, verify the same presentation and issue your own
HttpOnly session cookie keyed by `ppid`. See
[Quick start](QUICK_START_SIMPLE_LOGIN.md) and
[Integration guide — sessions appendix](SIMPLE_INTEGRATION_GUIDE.md#4-session-layer-your-responsibility).

---

## Next steps

| Doc | Purpose |
|-----|---------|
| [Quick start: verify a lemma proof](QUICK_START_SIMPLE_LOGIN.md) | Gate an action end-to-end |
| [Integration guide](SIMPLE_INTEGRATION_GUIDE.md) | Assurance, stamps, abuse, sessions |
| [Trust & availability](SIGN_IN_TRUST_AND_RECOVERY.md) | Recovery, outage, honest limits |
| [Assurance tiers + input burn](../product/PASSKEY_STAMP_INPUT_BURN.md) | One PPID, site-local burn policy |
