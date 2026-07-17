# AI agent instructions: lemma.id

You are helping a developer integrate **lemma.id human proofs** into their web platform. **isHuman** is an optional assurance tier sites can require, not the product name.

## Read this first

**Canonical integration guide (follow it):**

https://lemma.id/docs/integration/ISHUMAN_AGENT_INTEGRATION.md

Or locally: `docs/integration/ISHUMAN_AGENT_INTEGRATION.md`

**Human-readable docs:** https://lemma.id/docs

**Pointer file:** https://lemma.id/llms.txt

Or locally: `llms.txt`

## Product scope

- **In scope:** Browser SDK (`proof-verifier.js`), site-private PPIDs, local backend verification, optional site API keys for abuse controls.
- **Out of scope:** Agent Ops (lemma-cli, Lemma Firewall, runtime control plane), operator-only, not for relying-site integration.

## Hard rules

1. `siteId` = canonical hostname (`app.example.com`), not internal `site_...` IDs.
2. Fail closed when `human` is false.
3. For signup/account creation, verify a signed `presentation` on the server, never trust a bare client `ppid`.
4. No customer webhooks, no wallet secret on the developer's backend, no KYC field storage.

## Quick integration

```html
<script src="https://lemma.id/sdk/proof-verifier.js"></script>
<script>
  const verifier = new ProofVerifier({ siteId: 'app.example.com' });
  const { ok, presentation } = await verifier.verifyForBackend({ autoProvision: true });
  if (!ok) throw new Error('not_verified');
  await fetch('/api/signup', { method: 'POST', body: JSON.stringify({ presentation }) });
</script>
```

The legacy `ishuman-verifier.js` URL and `IsHumanVerifier` class remain supported
as compatibility aliases.

Verify on the server with `@lemma/ishuman-verify` or `lemma_ishuman_verify.py`.

See the full guide for trust tiers, abuse APIs, anti-patterns, and framework notes.

## Platform operator identity (lemma.id internal)

Platform operators use the **same wallet + isHuman flow** as all users. Admin/operator access is an additional lemma.id-scoped permission proof, not a separate identity path.

- Runtime site binding key: normalized hostname (`lemma.id` for the platform).
- Internal `site_...` ids are ownership/database context only, never the sole runtime credential match key.
- Platform operator = complete lemma.id identity proof + `admin_access` permission bound to `lemma.id`.
- Canonical admin permission id: `admin_access` (preserve requested level separately as `permission_level`).
- Skip empty site fields before strict canonicalization; sparse master credentials are valid.

Contract doc: `docs/product/LEMMA_ID_PRESENTATION_MODEL.md`
