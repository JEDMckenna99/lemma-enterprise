# Deletion and Export Procedures (Draft)

**Status:** Draft pending counsel review  
**Last updated:** 2026-07-27  
**Intake:** privacy@lemma.id

## 1. Request intake

All deletion and export requests are submitted to **privacy@lemma.id**. Include:

- Request type (access / correction / deletion / export)
- Account email or site domain
- For end-user requests routed via a relying site: site name and approximate
  account identifier the site holds (PPID is site-private; Lemma may need site
  cooperation)

**Response target:** Acknowledge within 5 business days; fulfill within 30 days
unless legal retention applies.

## 2. Identity verification

| Requestor | Verification |
|---|---|
| Developer / site admin | Authenticated lemma.id session + email confirmation |
| End user (direct) | Passkey/wallet session or IDV re-verification where applicable |
| End user (via relying site) | Relying site confirms request; Lemma processes per DPA |
| Law enforcement | Valid legal process to legal@lemma.id (counsel review) |

## 3. End-user erasure (lemma.id wallet)

**API:** `POST /api/ishuman/erase` (authenticated wallet session)

Erases or anonymizes:

- Wallet bindings and person-root associations for the caller
- Associated verification records where applicable

Does **not** automatically erase relying-site account data held by integrators.
Integrators remain responsible for their controller obligations.

## 4. Site / developer deletion

1. Verify site ownership via authenticated admin session
2. Revoke API keys
3. Delete or anonymize site rows, billing subjects, blocks, doubts per retention
   policy
4. Cancel Stripe subscription
5. Confirm completion via email

Legal holds may delay deletion where required.

## 5. Export procedures

| Data type | Export path | Format |
|---|---|---|
| Audit logs (site-scoped) | `GET /api/v1/audit/export?site_id=...` | CSV / JSON |
| Site users | `GET /api/developer/sites/<site_id>/users/export` | JSON |
| Billing / MAU | `GET /api/mau/export/<customer_id>` | JSON |
| Developer account metadata | Manual request to privacy@lemma.id | JSON |

Exports require authenticated site ownership (`authorize_site_access`).

## 6. Retained after deletion

Lemma may retain:

- Aggregated billing records required for tax/accounting
- Security logs under tier retention for fraud investigation
- Data subject to legal hold or regulatory requirement

See [`DATA_RETENTION_INVENTORY.md`](DATA_RETENTION_INVENTORY.md).

## 7. Relying-site responsibilities

Integrators that act as controllers must:

- Honor end-user deletion requests for data they store
- Call Lemma APIs or contact privacy@lemma.id for processor-side erasure
- Not treat PPIDs as deletion secrets (they are identifiers, not auth secrets)

## Related documents

- [`DPA_DRAFT.md`](DPA_DRAFT.md)
- [`DATA_FLOW_INVENTORY.md`](DATA_FLOW_INVENTORY.md)
- Privacy policy §§7–10: `https://lemma.id/privacy`
