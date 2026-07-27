# SOC 2 Control Evidence Map (Draft)

**Status:** Control evidence scaffolding — not a SOC 2 Type I/II report  
**Last updated:** 2026-07-27

This map links common AICPA Trust Services Criteria themes to existing Lemma.id
evidence from production-readiness Sections 3–9. Use for enterprise security
questionnaires until formal SOC 2 attestation is available.

## Disclaimer

Lemma.id has **not** completed SOC 2 Type I or Type II attestation as of this
date. `docs/security/SECURITY_CHECKLIST.md` notes SOC 2 is in progress (server
infrastructure only).

## CC — Common Criteria (Security)

| Control theme | Evidence | Section |
|---|---|---|
| Logical access / tenant isolation | `api/site_access.py`, RLS migration 042, `tests/test_tenant_isolation_section3.py` | §3 PASS |
| Authentication / wallet authority | `api/wallet_authn.py`, adversarial wallet tests | §2 IN_PROGRESS |
| Cryptographic controls | Network root pins, canonical messages, cross-verifier fixtures | §4 PASS |
| Revocation / replay fail-closed | `tests/test_revocation_fail_closed_section5.py`, prod smoke | §5 PASS |
| Secrets management | Hash-only API keys, KMS policy script, Section 7 prod smoke | §7 PASS |
| Vulnerability management | `.github/workflows/section11-security.yml`, Dependabot, `SECURITY.md` VDP | §11 IN_PROGRESS |

## A — Availability

| Control theme | Evidence | Section |
|---|---|---|
| Health / readiness separation | `GET /health`, `GET /ready` gates | §9 PASS |
| Backup / restore | Section 9 restore drill, Continuous Protection | §9 PASS |
| Status page | `https://status.lemma.id` | §9 PASS |
| Incident response | `docs/operations/INCIDENT_DRILL_RUNBOOK.md` | §9 PASS |
| Dependency outage playbook | `docs/operations/DEPENDENCY_OUTAGE_PLAYBOOK.md` | §9 PASS |

## PI — Processing Integrity

| Control theme | Evidence | Section |
|---|---|---|
| Billing idempotency | Stripe webhook idempotency, outbox worker, reconcile script | §8 PASS |
| Migration integrity | Checksum migrations, release phase | §9 PASS |
| Protocol registry | `scripts/check_ishuman_protocol_registry.py` | §1 |

## C — Confidentiality

| Control theme | Evidence | Section |
|---|---|---|
| KMS encryption | Person roots, OAuth secrets, `scripts/verify_kms_policy.py` | §7 PASS |
| Privacy-minimized issuance | `docs/architecture/PRIVACY_ARCHITECTURE.md` | Product |
| Tenant DB isolation | `SET LOCAL app.current_site_id` RLS | §3 PASS |

## P — Privacy

| Control theme | Evidence | Section |
|---|---|---|
| Data flow documentation | `docs/legal/DATA_FLOW_INVENTORY.md` | §11 |
| Retention automation | `retention/retention_worker.py` | §9 PASS |
| Erasure API | `POST /api/ishuman/erase` | Product |
| Subprocessor list | `docs/legal/SUBPROCESSORS.md` | §11 |

## Change management

| Control theme | Evidence |
|---|---|
| CI regression | `.github/workflows/ci-regression.yml` |
| Auth launch gate | `.github/workflows/auth-launch-gate.yml` |
| Release provenance | `.github/workflows/proof-verifier-release.yml` (SBOM + attestation) |

## Gaps for formal SOC 2

- [ ] Independent auditor engagement
- [ ] Control owner attestations over observation period
- [ ] HR / background check policies (if in scope)
- [ ] Formal risk assessment register
- [ ] Vendor SOC reports collection (Stripe, AWS, etc.)

## Contact

Enterprise compliance requests: **privacy@lemma.id**
