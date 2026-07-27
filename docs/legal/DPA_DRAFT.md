# Data Processing Agreement (Draft)

**Status:** Draft pending counsel review — not for execution without legal approval  
**Last updated:** 2026-07-27  
**Version:** 0.1-draft

## 1. Parties

- **Controller:** The relying site (customer) that determines purposes and means
  of processing end-user personal data.
- **Processor:** Lemma.id ("Lemma") providing human-proof authentication,
  credential issuance, and related platform services.

## 2. Subject matter and duration

Lemma processes personal data on behalf of the Controller for the duration of
the service agreement and as needed to fulfill legal obligations afterward.

## 3. Nature and purpose of processing

Processing supports:

- Passkey-backed wallet authentication
- Optional isHuman identity verification and site-private PPID issuance
- Presentation verification assistance (when invoked by Controller)
- Revocation, blocks, and site-scoped enforcement
- Usage metering and billing

See [`DATA_FLOW_INVENTORY.md`](DATA_FLOW_INVENTORY.md).

## 4. Categories of data subjects

- End users of Controller's application
- Controller administrators and developers

## 5. Categories of personal data

- Pseudonymous identifiers (site-private PPIDs, wallet IDs, credential IDs)
- Transient IDV-derived attributes (document root derivation inputs; not stored
  as raw documents)
- Developer account contact and billing data
- Security and audit metadata (IP, user agent, timestamps)

## 6. Processor obligations

Lemma shall:

- Process personal data only on documented instructions from Controller
- Ensure personnel confidentiality
- Implement appropriate technical and organizational measures (see security
  contract: `docs/security/HUMAN_AUTH_SECURITY_CONTRACT.md`)
- Assist with data subject requests per [`DELETION_EXPORT_PROCEDURES.md`](DELETION_EXPORT_PROCEDURES.md)
- Delete or return data upon termination, subject to legal retention
- Make available information necessary to demonstrate compliance

## 7. Subprocessors

Controller authorizes Lemma to engage subprocessors listed in
[`SUBPROCESSORS.md`](SUBPROCESSORS.md). Lemma will provide notice of material
changes.

## 8. Security measures

Including but not limited to:

- Ed25519 signed credentials and WebAuthn passkeys
- KMS-backed encryption for sensitive roots and secrets
- Tenant isolation (RLS + `authorize_site_access`)
- Fail-closed revocation and replay protection
- Hash-only API key storage

## 9. Personal data breach notification

Lemma will notify Controller without undue delay and in any event within
**72 hours** of becoming aware of a personal data breach affecting Controller
data, consistent with the public privacy policy and
[`INCIDENT_NOTIFICATION_COMMITMENTS.md`](INCIDENT_NOTIFICATION_COMMITMENTS.md).

## 10. International transfers

Where subprocessors process data outside the EEA/UK, Lemma will implement
appropriate transfer mechanisms (e.g., SCCs) as required by applicable law.

## 11. Audits

Controller may request reasonable compliance information. Formal SOC 2 reports
will be provided when available (see [`SOC2_CONTROL_EVIDENCE_MAP.md`](SOC2_CONTROL_EVIDENCE_MAP.md)).

## 12. Liability and governing law

*[Counsel to complete]*

## Contact

- Privacy: privacy@lemma.id  
- DPO: dpo@lemma.id  
- Security: security@lemma.id
