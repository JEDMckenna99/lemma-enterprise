# Lemma Privacy & Data-Handling Architecture

> **Accurate-to-code statement.** This document describes what the Lemma platform
> actually stores, processes, and transmits, as implemented in `api/`, `billing/`,
> and `static/js/`. It deliberately avoids "no PII" / "zero-knowledge" claims that
> the code does not support. Under GDPR, **pseudonymised data (hashes, PPIDs,
> derived roots) is still personal data** (Recital 26) because it can be
> re-identified by a party holding the keying material. Lemma is therefore a
> **data controller** for the identity-anchoring data it stores, not a neutral pipe.
>
> This is an engineering reference, not legal advice. Map each row below to your
> Didit/Stripe DPAs and Article 30 records before relying on it externally.

## Executive Summary

Lemma issues user-held, locally-verifiable credentials. The design genuinely
minimizes data: **relying sites** receive only a site-private PPID and a boolean
claim, and **return-visit verification happens locally in the browser with no
Lemma server call**. However, Lemma's own backend is in scope for privacy
regulation because it:

- receives IDV **outcomes** from Didit/Stripe Identity (it is not pure pass-through),
- **transiently processes** document number + date of birth to derive identity anchors,
- **persists** derived hashes, PPIDs, wallet↔person bindings, and revocation state,
- can **correlate one person across sites on the admin/revocation plane** (by design, for enforcement),
- **logs** IP address / user agent on some operational paths.

What Lemma deliberately does **not** persist: raw identity documents, face/selfie
images, and (in the isHuman path) legal name.

---

## 1. Data Flow: Who Sees What

```
User's Browser            IDV Provider             Lemma Server           Relying Site
     │                    (Didit/Stripe)                 │                      │
     │  start IDV ───────────────────────────────────────┤                      │
     │  document + liveness ─────►│                       │                      │
     │                            │  webhook / outcome ──►│                      │
     │                            │   (doc #, DOB, etc.)  │ derive roots,        │
     │                            │                       │ store hashes + PPID  │
     │  ◄─── signed credential ───────────────────────────┤                      │
     │  (stored in browser wallet)                        │                      │
     │                                                                           │
     │  credential + signature ─────────────────────────────────────────────────►│
     │                                                     Ed25519.verify() LOCAL │
     │                                                     (no Lemma server call) │
     │  ◄──── { human, ppid } ───────────────────────────────────────────────────┤
```

**Key correction vs. prior versions of this doc:** IDV is **not** entirely
user ↔ provider. The Lemma server receives and processes the IDV **outcome**
(via authenticated webhook for Didit; via expanded session re-fetch for Stripe
Identity, see `billing/stripe_manager.py:retrieve_identity_root_material`).

---

## 2. What the Lemma Server Processes and Stores

### 2.1 Transiently processed (used to derive anchors, not designed to be persisted raw)

| Field | Source | Use |
|-------|--------|-----|
| Document number | Didit `decision` / Stripe `verified_outputs` | HMAC input to `document_root` |
| Date of birth | Same | HMAC input to `document_root` |
| ID number / last4 (Stripe) | `verified_outputs.id_number` | Optional HMAC input |
| Country / document type | IDV outcome | Stored as quasi-identifier metadata |

Legal **name** and **face/selfie** are **not** used in isHuman root derivation
(`api/identity_roots.py:build_document_root_claims` excludes them).

### 2.2 Persisted (this is personal data under GDPR — pseudonymous, re-identifiable with the pepper)

| Store | Content | Form |
|-------|---------|------|
| `lemma_document_roots.document_root_hash` | `HMAC(pepper, canonical_json(document claims))` | 64-char hex digest |
| `lemma_persons.person_root_hash` | `HKDF(document_root_hash, salt, "person-root/v1")` | AES-GCM encrypted at rest when `LEMMA_COLUMN_ENCRYPTION_KEY` is configured (`api/column_crypto.py`, migration `029`) |
| `lemma_document_roots` metadata | provider, country, document type, Stripe session/report IDs | quasi-identifiers |
| `ishuman_verifications` | `ppid`, `wallet_id`, `credential_id`, `lemma_person_id`, status timeline, `metadata_json` | pseudonymous + linkage |
| `lemma_wallet_bindings` | wallet ↔ person mapping | linkage |
| `derived_credentials` | master → per-site mapping incl. `derived_ppid` | **server-side cross-site linkage** (for revocation) |
| Operator/IAM tables | account email, API keys, `user_sessions.ip_address`/`user_agent` (optional) | account PII |

### 2.3 Not persisted

- Raw identity document images
- Face / selfie images (isHuman path)
- Legal name (isHuman path)
- Full IDV report blobs (only metadata + derived hashes)

> **Pepper/salt is the crown jewel.** Because the stored hashes are
> re-identifiable by anyone holding the HMAC pepper, the pepper's key management,
> rotation, and backup scope determine whether stored data is meaningfully
> pseudonymous. Treat it as Article 32 critical material.

---

## 3. Cross-Site Correlation: Honest Scope

**Relying sites cannot correlate users with each other.** Each site receives a
distinct PPID:

```python
# api/identity_roots.py
site_ppid = HMAC(person_root, "lemma.id/site-ppid/v1" || canonical_site)
```

```
Site A sees: did:lemma:ppid_7f3a9b2c1d...
Site B sees: did:lemma:ppid_e4c8f6a2b5...   # not linkable to A by the site
```

**Lemma's admin/revocation plane can correlate**, by design. The
`derived_credentials` table and `lemma_persons` ↔ `lemma_wallet_bindings`
mappings exist precisely so that a network-wide revocation can find every
site-PPID belonging to one verified person. Do **not** claim "Lemma cannot link
users across sites" without this qualification. The accurate claim is:

> Sites cannot correlate users across sites. Lemma can correlate them only on
> the enforcement plane (revocation), and never exposes that linkage to sites.

---

## 4. PPID Derivation: Where It Happens

| Flow | Formula | Computed where |
|------|---------|----------------|
| Post-IDV (canonical) | `HMAC(person_root, "lemma.id/site-ppid/v1"||site)` | **Server** at issuance; client normally reuses the PPID embedded in the issued credential |
| Optional sealed-seed path | same | Client, after opening a server-sealed `person_root_proxy` envelope (flag `LEMMA_ISHUMAN_USE_PERSON_ROOT_SEEDS`) |
| Legacy pre-IDV | `HMAC(HMAC(root_key, wallet_secret), site)` | Server, or client-side `HMAC(wallet_secret, site)` (architectural debt; see `V2_DESIGN_IMPROVEMENTS.md`) |

### Important correction: the server **does** receive `wallet_secret` on some endpoints

Previous versions of this doc claimed "the server never sees `wallet_secret`."
That is not universally true:

- `POST /api/ishuman/start-verification` — request body may include `wallet_secret`
- `POST /api/ishuman/derive-site-proof` — **requires** `wallet_secret`

These travel over TLS and are not persisted as `wallet_secret`, but they are
transmitted. Treat them as in-scope for breach/exposure analysis and prefer
moving derivation client-side where feasible.

---

## 5. Browser Wallet vs. Server

| Location | Holds |
|----------|-------|
| **Browser wallet** (IndexedDB, passkey/PRF-encrypted) | `wallet_secret`, full credential bodies (isHuman, ppidDerivation, site bindings), passkey credential ID, issuer keys, revocation Bloom cache, optional `person_root_proxy` |
| **Lemma server** | Issuer signing keys (site keys may be KMS-encrypted), identity-linkage tables (§2.2), revocation/site-block state, operator/IAM data, application logs |

Normal return-visit verification reads the credential from the wallet and runs
`Ed25519.verify()` locally — **no Lemma server call**. This is the basis for the
"local verification" claim and it is accurate for the verify hot path.

---

## 6. Retention & Erasure

| Item | Status |
|------|--------|
| Credential TTL | `ISHUMAN_CREDENTIAL_TTL_DAYS`, default **365** |
| User erasure | **Implemented**: `POST /api/ishuman/erase` (wallet-authenticated) — network-revokes, scrubs `ishuman_verifications`, deletes wallet bindings, and deletes `LemmaPerson`/`LemmaDocumentRoot` when no other wallet is bound |
| Account/audit log retention | Per `templates/legal/privacy.html` (30d–7y by tier); deletion within 30 days of account deletion |
| Upstream IDV session purge (Didit) | **Implemented.** After a credential is durably issued, Lemma calls `DELETE /v3/session/{id}/` on Didit (process-and-purge) so the document/liveness/decision data is removed from the upstream processor. Best-effort, idempotent, non-fatal to issuance; toggle `LEMMA_ISHUMAN_DIDIT_PURGE`. See `_purge_didit_session_after_issuance` in `api/ishuman.py` and `DiditManager.delete_session`. |
| Upstream IDV session purge (Stripe legacy) | **Not yet automated.** No scheduled redaction of Stripe Identity sessions after root derivation. **Action: implement before relying on the Stripe path; Didit is the default rail.** |

---

## 7. Logging

Application logs in the isHuman path record truncated PPIDs (`[:40]`),
`credential_id`, `lemma_person_id`, webhook `type`/`status`/`session_id`, and
erasure counts. They do **not** log DOB or document number in the isHuman path.

`NetworkActivity` is restricted to administrative grant/revoke actions and does
**not** log routine verification events. However, operator
`user_sessions` may store `ip_address`/`user_agent`, and `templates/legal/privacy.html`
discloses IP/UA logging — so the platform as a whole **does** log IP/UA on some
paths. Sentry runs with `send_default_pii=False`.

---

## 8. GDPR Posture (engineering view, not legal advice)

Lemma is best described as a **data-minimized controller** (likely a joint
controller with Didit/Stripe for the IDV step):

| Principle | How the implementation supports it |
|-----------|-------------------------------------|
| Data minimization (Art. 5) | No raw documents/biometrics/name at rest; only derived hashes + PPIDs |
| Storage limitation (Art. 5) | Credential TTL; erasure endpoint. **Gap:** automate raw-session purge |
| Security (Art. 32) | Column encryption at rest, KMS for site keys, TLS, passkey wallet. **Critical dependency:** pepper/salt key management |
| Right to erasure (Art. 17) | `POST /api/ishuman/erase` + client "Clear my lemma.id" |
| Data portability (Art. 20) | Wallet export |
| Records of processing (Art. 30) | Use §2 tables as the inventory basis |
| DPIA (Art. 35) | Large-scale identity processing — treat as required |

**Outstanding actions before external reliance:**

1. Remove "no PII stored" / "zero-knowledge" claims everywhere (see also `docs/security/SECURITY_CHECKLIST.md`).
2. Implement and schedule the raw IDV-session purge job.
3. Sign/maintain DPAs with Didit and Stripe; publish a sub-processor list.
4. Reconcile the public privacy policy, this doc, and the security checklist so all three match the code.
5. Document pepper/salt key management, rotation, and backup scope.

---

## 9. What Sites Receive (accurate)

```json
{
  "human": true,
  "ppid": "did:lemma:ppid_7f3a9b2c1d...",
  "reason": "valid",
  "timeMs": 1.2
}
```

Sites do **not** receive: name, document, DOB, address, a global identifier, or
the user's activity on other sites.

---

## 10. Summary

Lemma's privacy strength is **real but bounded**: sites see only unlinkable
PPIDs and verify locally, and Lemma stores no raw documents, faces, or names.
Lemma is nonetheless a controller of pseudonymous identity data and must meet
controller obligations. The honest one-line positioning:

> **Relying sites hold no PII; Lemma holds the minimum — encrypted, derived
> identifiers with built-in erasure — and never exposes cross-site linkage to
> sites.**
