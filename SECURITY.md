# Security Policy — Vulnerability Disclosure Program

Lemma.id operates a coordinated vulnerability disclosure program (VDP) for
security issues affecting lemma.id production services, SDKs, and documented
integration surfaces.

## Supported versions

Security fixes are provided for the `main` branch and the currently deployed
production release on `https://lemma.id`.

## Scope (in scope)

- lemma.id wallet ceremonies (passkey enroll, unlock, device transfer, recovery)
- isHuman IDV, credential issuance, and presentation verification APIs
- Site-scoped tenant controls (blocks, doubts, API keys, domain ownership)
- Revocation, replay protection, and billing integrity paths
- Published SDK packages (`@lemma.id/proof-verifier`, `lemma-proof-verifier`)
- Browser SDK assets served from `https://lemma.id/sdk/`

## Out of scope

- Social engineering or phishing against Lemma employees or customers
- Denial-of-service requiring unrealistic traffic or resources
- Issues in third-party infrastructure without a Lemma-specific exploit path
  (e.g., generic Stripe, AWS, or IDV provider bugs)
- Customer relying-site application code not operated by Lemma
- Theoretical issues without a practical proof of concept on deployed behavior

## How to report

Email **security@lemma.id** with **SECURITY** in the subject line. Include:

1. Summary and estimated impact
2. Affected URL, endpoint, or package version
3. Reproduction steps or proof-of-concept
4. Suggested remediation (optional)

Do **not** open public GitHub issues with exploit details.

## Response targets

| Stage | Target |
|---|---|
| Initial acknowledgement | 3 business days |
| Triage decision | 7 business days |
| Critical/high fix | Best effort; coordinated disclosure |
| Medium/low fix | Next scheduled release or documented acceptance |

## Safe harbor

We will not pursue legal action against researchers who:

- Make a good-faith effort to avoid privacy violations, service degradation, and
  data destruction
- Report through this channel before public disclosure
- Allow reasonable time for investigation and remediation

Safe harbor does not apply to extortion, data exfiltration beyond what is
necessary to demonstrate impact, or access to customer data you do not own.

## Severity guidance

| Severity | Examples |
|---|---|
| Critical | Cross-tenant data access, wallet takeover without passkey, forged presentation accepted, signing key compromise |
| High | CSRF bypass on wallet mutations, recovery without IDV binding, API key bypass |
| Medium | Information disclosure without direct account compromise, rate-limit bypass |
| Low | Best-practice hardening, non-exploitable informational findings |

## Bug bounty

A paid bug-bounty platform is **planned** but not yet live. This VDP is the
active channel until a bounty program is announced.

## Recognition

We coordinate release notes and credit researchers who report valid issues and
work with us on responsible disclosure, when requested.

## Related documents

- Threat model: `docs/security/THREAT_MODEL.md`
- Security contract: `docs/security/HUMAN_AUTH_SECURITY_CONTRACT.md`
- Findings tracker: `ops/evidence/launch/section11-findings-tracker.md`

## Contact

**security@lemma.id**
