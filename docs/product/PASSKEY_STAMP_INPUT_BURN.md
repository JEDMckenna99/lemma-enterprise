# One PPID, Assurance Tiers, and Site-Local Input Burn

**Status:** Active product contract (replaces two-PPID passkey-stamp draft)  
**Date:** 2026-07-02  
**Audience:** Product, platform, privacy reviewers, integrators

## Summary

Relying sites see **one stable site-scoped subject** (`ppid`) per user. Proof strength is expressed as **assurance**, not as a second PPID:

```text
ppid         = stable identifier for this user at this site (from assigned person_root)
assurance    = passkey | ishuman | future tiers
presentation = signed credential bundle satisfying the site's policy
```

Adding `isHuman` after passkey signup **raises assurance** on the **same PPID**. It does not mint a new site subject.

Lemma issues signed credentials and holds wallet ↔ person bindings. **Input burn graphs stay site-local**: Lemma never stores email/phone/card fingerprints or site ban lists.

## Assurance tiers

| Tier | When issued | `claims.assurance` | `claims.isHuman` | Recovery |
|------|-------------|--------------------|------------------|----------|
| **passkey** | Wallet registered; provisional person_root assigned | `passkey` | `false` | Not promised (disposable pre-anchor wallet) |
| **ishuman** | After successful IDV | `ishuman` | `true` | Re-IDV on new device → same person_root → same PPID |

Assurance availability is managed by lemma.id. Relying sites do not configure
platform rollout flags; they request `passkey` or `ishuman` per protected action
and fail closed when the requested assurance is unavailable.

## Lifecycle

```text
1. Create passkey wallet → provisional assigned person_root + wallet binding
2. Derive site PPID from person_root (stable from this point)
3. Issue passkey-assurance site credential when continuity proof is requested
4. Site stores ppid + local input fingerprints
5. On abuse/doubt → site requires ishuman assurance (same ppid after IDV step-up)
6. After first IDV → person promoted to anchored; recovery preserves PPIDs
```

## Site-local input burn (relying-site pattern)

Lemma does **not** implement burn lists. Sites own correlation and escalation:

| Site state | Recommended policy |
|------------|-------------------|
| New signup, low risk | Accept `requiredAssurance: "passkey"` |
| Inputs burned locally, passkey-only session | Require `requiredAssurance: "ishuman"` before restore |
| User completes IDV step-up | Update **same account** in place; do not create a new row keyed by a new PPID |
| Post-IDV recovery on new device | Lookup by stable PPID / presentation; rebind session |

Store locally:

- `ppid`, current site subject (one column, stable across step-up)
- Input fingerprints + burn flags, site-only
- Last seen `assurance`, for policy gates

## SDK integration

```javascript
const verifier = new ProofVerifier({
  siteId: 'app.example.com',
});
const { ok, ppid, assurance, presentation } = await verifier.verifyForBackend({
  autoProvision: true,
  requiredAssurance: 'passkey',
});
```

Backend: verify presentation with `@lemma.id/proof-verifier` / `lemma_proof_verifier.py` and enforce `required_assurance`.

## Non-goals

- Two PPIDs (stamp + identity) at the same site
- Lemma-held person graphs or cross-site revocation for passkey tier
- Recoverable pre-IDV wallets (provisional roots are disposable until anchored)

## Related docs

- [Canonical relying-site integration guide](https://lemma.id/docs/integration/ISHUMAN_AGENT_INTEGRATION.md)
- [Human-readable developer docs](https://lemma.id/docs)
