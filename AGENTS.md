# AI agent instructions — lemma.id isHuman

You are helping a developer integrate **lemma.id proof of humanity** into their web platform.

## Read this first

**Canonical integration guide (follow it):**

https://lemma.id/docs/integration/ISHUMAN_AGENT_INTEGRATION.md

Or locally: `docs/integration/ISHUMAN_AGENT_INTEGRATION.md`

**Human-readable docs:** https://lemma.id/docs

**Pointer file:** https://lemma.id/llms.txt

## Product scope

- **In scope:** Browser SDK (`ishuman-verifier.js`), site-private PPIDs, local backend verification, optional site API keys for abuse controls.
- **Out of scope:** Agent Ops (lemma-cli, Lemma Firewall, runtime control plane) — operator-only, not for relying-site integration.

## Hard rules

1. `siteId` = canonical hostname (`app.example.com`), not internal `site_...` IDs.
2. Fail closed when `human` is false.
3. For signup/account creation, verify a signed `presentation` on the server — never trust a bare client `ppid`.
4. No customer webhooks, no wallet secret on the developer's backend, no KYC field storage.

## Quick integration

```html
<script src="https://lemma.id/sdk/ishuman-verifier.js"></script>
<script>
  const verifier = new IsHumanVerifier({ siteId: 'app.example.com' });
  const { ok, presentation } = await verifier.verifyForBackend({ autoProvision: true });
  if (!ok) throw new Error('not_verified');
  await fetch('/api/signup', { method: 'POST', body: JSON.stringify({ presentation }) });
</script>
```

Verify on the server with `@lemma/ishuman-verify` or `lemma_ishuman_verify.py`.

See the full guide for trust tiers, abuse APIs, anti-patterns, and framework notes.
