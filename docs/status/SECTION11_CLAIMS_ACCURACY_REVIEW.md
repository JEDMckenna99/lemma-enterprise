# Section 11 Product Claims Accuracy Review

**Date:** 2026-07-27  
**Reviewer:** Platform + Security (engineering)  
**Status:** Complete for engineering review; formal sign-off pending Security Lead

Maps public claims to tiers in [`docs/plans/CLAIMS_REWRITE_TIERED.md`](../plans/CLAIMS_REWRITE_TIERED.md).

## Summary

| Claim area | Verdict | Action |
|---|---|---|
| Privacy / data minimization | Mostly Tier A/B | Privacy policy and trust page are qualified; legal pack drafted |
| Zero-knowledge | **Overclaim found** | Fixed in terms.html (see below) |
| Uniqueness / one-human | Tier B (qualified) | Demo and docs correctly distinguish passkey vs isHuman |
| Recovery | Tier A/B | Limits documented; no absolute guarantees |
| Uptime / SLA | Tier B/C | Terms list tier SLAs; status page is best-effort unless contracted |

## Claim inventory

### Privacy

| Claim | Location | Tier | Accurate? |
|---|---|---|---|
| "Local verification" / "local-first" | Privacy §4, trust page | B | Yes — qualified; IDV path involves Lemma servers |
| "PPIDs unlinkable across sites" | Privacy §4 | B | Yes — design intent; sites must not add correlators |
| "No advertising to end users" | Privacy §3.1 | A | Yes — product policy |
| "We do not retain raw IDV documents" | Privacy §4 | A | Yes — per privacy architecture |

### Zero-knowledge

| Claim | Location | Tier | Accurate? |
|---|---|---|---|
| ~~"Zero-Knowledge Verification: Your servers verify locally without contacting us"~~ | ~~terms.html §6~~ | — | **Fixed** — overstated; IDV and optional verify-presentation contact Lemma |
| Replacement | terms.html §6 | B | "Local return-visit verification on your servers without per-request calls to Lemma for routine checks" |

### Uniqueness / human assurance

| Claim | Location | Tier | Accurate? |
|---|---|---|---|
| "not proof of unique humanness" (passkey alone) | demo/lemma.html | A | Yes |
| "requiredAssurance: 'ishuman'" | homepage, docs | A | Yes — explicit tier |
| "Stop the same abuser" | homepage | B | Qualified — isHuman tier when enabled |
| "anyone can create another lemma.id" | homepage, index | A | Yes — honest limitation |

### Recovery

| Claim | Location | Tier | Accurate? |
|---|---|---|---|
| Recovery requires IDV + replacement passkey | wallet docs, Section 6 | A | Yes — deployed |
| Email alone cannot complete recovery | Section 6 tests | A | Yes |
| Recovery-specific admin alerts | — | C | **Not deployed** — deferred in Section 6 |

### Uptime / availability

| Claim | Location | Tier | Accurate? |
|---|---|---|---|
| Tier SLAs (99.5%–99.95%) | terms.html §7 | C/B | Aspirational unless enterprise contract; not independently attested |
| status.lemma.id | ops | B | Measured availability; no public SLA breach credits on free tier |
| Section 9 restore RTO | ops evidence | A | Measured drill — 0.08 min vs 60 min target |

## Remediation applied

- **terms.html:** Replaced absolute "Zero-Knowledge Verification" bullet with
  qualified local return-visit verification language aligned with privacy §4.

## Automated guards

- `tests/test_public_positioning.py` — homepage/trust/docs positioning
- Recommend extending to terms.html zero-knowledge regression (optional follow-up)

## Residual risks for sign-off

1. Terms SLA percentages are not yet backed by published uptime reports
2. "Zero-knowledge" must not appear in marketing without Tier B qualification
3. Recovery notification and emergency suspension remain roadmap (Section 6)

## Sign-off

- Security Lead: __________ Date: __________
- Product: __________ Date: __________
