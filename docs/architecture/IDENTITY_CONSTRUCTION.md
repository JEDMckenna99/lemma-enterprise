# Identity construction (internal overview)

- **Status:** Active high-level map
- **Audience:** Platform engineering, security, product, and anyone editing
  privacy / trust / uniqueness copy
- **Not public:** Do not add this file to `api/public_docs.py`. Integrators
  verify a signed presentation and enforce `ppid` + assurance. They do not
  implement these derivations.

This page is the single walkthrough of how lemma.id turns an IDV outcome into
a stable site-private PPID and a human proof. Exact bytes, resolution edge
cases, and claim language live in the linked specs.

## End-to-end picture

```text
IDV provider (Didit)
        │  verification outcome
        │  (no document images kept by lemma.id)
        ▼
document root
  HMAC(pepper, canonical JSON of verified claims)
        │
        ▼
assigned person
  random 32-byte person_root  (assigned_v1)
  stored as AWS KMS ciphertext
        │
        ├── document rematch / attach / fail closed
        │
        ▼
site PPID
  HMAC(person_root, "lemma.id/site-ppid/v1" || canonical hostname)
  → did:lemma:ppid_<hex>
        │
        ▼
signed credential + presentation
  assurance = passkey | ishuman
  site verifies locally (issuer sig, binding, expiry, revocation)
```

Passkey continuity uses the same PPID path before IDV (provisional person).
`ishuman` is a stronger assurance on that same PPID, not a second identifier.

## 1. Identity verification

When a site requires a human proof, or the user recovers a lemma.id, the user
completes IDV with **Didit**. Didit hosts the document and liveness check.

Lemma receives a verification **outcome**, not a document vault. It transiently
uses:

- document number
- issuing country / jurisdiction
- document type
- date of birth
- issuing subdivision when the schema requires it (US / CA / AU licences)

Those inputs are used only to derive the document root, then discarded. Lemma
does not persist document images, selfie / liveness images, or legal name.

Details: [`PRIVACY_ARCHITECTURE.md`](PRIVACY_ARCHITECTURE.md).

## 2. Document root

A document root is a keyed attestation of “this verified document,” not the
person itself.

```text
claims = canonical JSON({
  schema, provider, country, document_type,
  document_number, date_of_birth,
  issuing_subdivision?   # v2, required for some licences
})

document_root = HMAC-SHA256(identity_pepper, claims)
```

Current write schema is v2 (`LEMMA_DOCUMENT_ROOT_SCHEMA`). `provider` is part
of the claim set, so the same physical document verified through different IDV
rails (Didit vs a legacy Stripe session) is a distinct document root.

**Alias rematch:** US `id_card` ↔ `driving_license` with the same number, DOB,
and subdivision resolve the same assignment. That is a narrow compatibility
rail, not a general “any two IDs are the same person” rule.

Document expiry changes whether a new credential can be issued. It does not
change the assigned person or any site PPID. A renewed document attaches as a
new attestation on the same person.

Code: [`api/identity_roots.py`](../../api/identity_roots.py).

## 3. Person assignment

The **assigned person root** is the permanent human anchor (`assigned_v1`):

```text
person_root = 32 random bytes
```

It is **not** a hash of the document. Documents can be added or replaced
without moving the person or any PPID.

Resolution (`api/identity_person.py`):

| Situation | Outcome |
|---|---|
| Known document root | Existing person (same `person_root`, same PPIDs) |
| New document on an already-bound lemma.id | Document attaches; person unchanged |
| Document → person A, lemma.id anchored to person B | Fail closed |
| Document → active person, lemma.id only provisional | Adopt the document's person; drop the placeholder |
| Neither document nor lemma.id has an assignment | Create a new assigned person and attach the document |
| US/CA licence ↔ ID card alias match | Same person (see uniqueness bounds) |

**Provisional lifecycle** (one-PPID model): registering a lemma.id assigns a
provisional person immediately so site PPIDs exist before IDV. First successful
IDV promotes that person to `active` and attaches the document. PPIDs do not
change. If IDV finds an existing person while the lemma.id is still an
unanchored provisional, the binding switches to the existing person.

**Legacy:** `document_derived_v1` set `person_root = HKDF(document_root)`. New
assignments use `assigned_v1`. Do not describe the HKDF path as current
behavior.

Assigned roots are stored only as `kms1:` AWS KMS ciphertext. Production fails
closed if KMS is unavailable or a root is plaintext.

Details: [`ASSIGNED_PERSON_ROOT.md`](ASSIGNED_PERSON_ROOT.md).

## 4. PPID construction

A relying site never sees the person root. It sees a site-private PPID:

```text
PPID = HMAC-SHA256(person_root, "lemma.id/site-ppid/v1" || canonical_hostname)
     → did:lemma:ppid_<hex>
```

`siteId` at runtime is the canonical hostname (`app.example.com`), not an
internal `site_...` dashboard id.

Consequences:

- Same assigned person + same hostname → same PPID forever (renewal, recovery,
  credential rotation, passkey → isHuman step-up).
- Different hostnames → different PPIDs. Other sites cannot join them.
- Lemma can re-derive a site PPID from the person root when issuing or
  enforcing. That is an operator capability, not a cross-site identifier for
  relying sites.
- There is no PPID migration API. Conflicts fail closed instead of emitting an
  account-linking token.

After issuance, billing stores a keyed HMAC of the already site-private PPID,
not a person-to-site graph of raw PPIDs and credential IDs. Raw PPIDs are
persisted when a site blocks, doubts, or revokes that identifier.

## 5. Human proof construction

A **proof** is a signed credential the user's lemma.id holds, presented to a
site as a **presentation**.

| Artifact | Role |
|---|---|
| Master credential | Bound to the lemma.id / person; not a site account handle |
| Site credential | Bound to one hostname and that site's PPID; ~30-day TTL |
| Presentation | Site credential (and optional site-session proof) the relying site verifies |
| Assurance `passkey` | Continuity with the lemma.id; not IDV-backed humanity |
| Assurance `ishuman` | IDV-backed person assurance on the **same** PPID |

Issuance signs claims such as `assurance`, `isHuman`, `siteId`, issued/expiry,
and verification method. Admin permission is a **separate** proof
(`admin_access`). It is never implied by a valid human proof.

The relying site verifies locally: issuer signature, site binding, expiry,
revocation, and required assurance. Routine return visits do not call lemma.id.
Signup and account binding must verify the signed presentation; a bare client
`ppid` is not a credential.

What a proof **does not** establish: legal name, unique biological humanity,
that every later action is performed by that person, or site administration.

Semantics: [`HUMAN_AUTH_SECURITY_CONTRACT.md`](../security/HUMAN_AUTH_SECURITY_CONTRACT.md).
Integrator contract: [`ISHUMAN_AGENT_INTEGRATION.md`](../integration/ISHUMAN_AGENT_INTEGRATION.md).

## What each party holds

| Party | Holds | Does not hold |
|---|---|---|
| User's lemma.id | Encrypted credentials, passkey-protected unlock | Server person root |
| lemma.id | KMS-wrapped person root, document-root hashes, device bindings, enforcement PPIDs | Raw ID images, legal name, face |
| Relying site | Site-private PPID + verified presentation / assurance | Other sites' PPIDs, document fields, person root |
| Didit | Document and liveness images (Didit's terms) | lemma.id person root or cross-site PPID map |

## Uniqueness bound (do not skip)

Assigned persons enforce **document uniqueness**, not biometric unique-human:

```text
one verified government document attestation → at most one LemmaPerson
```

Same document rematches. A second document on an **already-bound** lemma.id
attaches. Distinct documents with different extracted numbers, presented on a
**fresh** lemma.id, can still mint a second person.

Do not ship “one human, any ID” or “proof of unique human.” Prefer
IDV-backed person, verified document, document uniqueness.

Source of claim language:
[`HUMAN_UNIQUENESS_BOUNDS.md`](../security/HUMAN_UNIQUENESS_BOUNDS.md).

## Source of truth

| Topic | Document / code |
|---|---|
| Assignment rules, no PPID migration | [`ASSIGNED_PERSON_ROOT.md`](ASSIGNED_PERSON_ROOT.md) |
| What is stored vs discarded | [`PRIVACY_ARCHITECTURE.md`](PRIVACY_ARCHITECTURE.md) |
| Proof / assurance meaning | [`HUMAN_AUTH_SECURITY_CONTRACT.md`](../security/HUMAN_AUTH_SECURITY_CONTRACT.md) |
| Uniqueness copy | [`HUMAN_UNIQUENESS_BOUNDS.md`](../security/HUMAN_UNIQUENESS_BOUNDS.md) |
| Presentation shape | [`LEMMA_ID_PRESENTATION_MODEL.md`](../product/LEMMA_ID_PRESENTATION_MODEL.md) |
| Derivation | [`api/identity_roots.py`](../../api/identity_roots.py) |
| Resolution | [`api/identity_person.py`](../../api/identity_person.py) |
| Issuance | [`api/ishuman.py`](../../api/ishuman.py) |

If this overview and a linked spec disagree, the spec and code win. This page
is a map, not a second implementation.
