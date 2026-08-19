# Human uniqueness bounds (internal)

**Audience:** platform engineering, security, product, launch copy owners  
**Status:** Active — claim source of truth for isHuman uniqueness  
**Related:** [`ASSIGNED_PERSON_ROOT.md`](../architecture/ASSIGNED_PERSON_ROOT.md),
[`HUMAN_AUTH_SECURITY_CONTRACT.md`](HUMAN_AUTH_SECURITY_CONTRACT.md),
[`identity_roots.py`](../../api/identity_roots.py),
[`identity_person.py`](../../api/identity_person.py)

## Claim that is true

isHuman establishes **IDV-backed human assurance** for a subject whose network
identity is anchored by **document-root uniqueness**:

```text
one verified government document attestation → at most one LemmaPerson
```

Same document (and US `id_card` ↔ `driving_license` when number/DOB/subdivision
match) resolves the same `person_root` and therefore the same per-site PPIDs.
A second document presented from an **already-bound** lemma.id attaches to that
person without minting a new root.

## Claim that is false (do not ship)

- Absolute **proof of unique biological human**
- **One human, any government ID, always one lemma.id** on a fresh enrollment
- Biometric uniqueness / face dedup across independent enrollments
- Unlimited Sybil resistance against well-capitalized multi-document farmers

isHuman is **not** a biometric unique-human oracle. It is document-anchored
human assurance that **raises Sybil cost** and gives durable person continuity
under abuse.

## Residual Sybil channel (known)

A person who holds **distinct** government documents with **different**
extracted document numbers (e.g. passport vs driver’s license, or mismatched
OCR of license number vs document discriminator) can complete IDV on a **fresh**
lemma.id and receive a **second** `LemmaPerson`.

US/Canada ID card numbers are **not** reliably identical to driver’s license
numbers across document types. Document-number equality is therefore not a
general cross-document uniqueness rail.

| Path | Outcome |
|------|---------|
| Same document again | Same person |
| US id_card ↔ driving_license, same number + DOB + subdivision | Same person (alias rematch) |
| New document on already-bound lemma.id | Document attaches; person unchanged |
| Fresh lemma.id + different document number | **New person** (residual channel) |
| Document maps to person A; wallet anchored to person B | Fail closed |

## Product and copy rules

1. Prefer **“IDV-backed person”**, **“verified document”**, **“document uniqueness”**,
   or **“Sybil-hardened / Sybil-sensitive”** over absolute **“one human”** /
   **“proof of unique human”** / unqualified **“Sybil-resistant”**.
2. Public docs must state the multi-document residual channel in one short
   paragraph (see Continuity & abuse + agent integration guide).
3. Marketing may say isHuman raises the cost of account rotation and binds
   accounts to IDV-backed persons; it must not imply biometric-grade uniqueness.
4. Ticketing/presale copy may keep “same document → same PPID” examples; keep the
   existing multi-document farming disclosure.

## What still holds for integrators

- Passkey tier alone is not Sybil resistance (anyone can mint another lemma.id)
- Requiring `ishuman` makes extra identities require fresh IDV’d documents
- Site-block, stamps, and same-PPID assurance upgrades remain valid
- No KYC fields, names, or document numbers are disclosed to relying sites

## Follow-ups (not claimed until shipped)

- Vendor face-duplicate / cross-session biometric uniqueness (if product accepts it)
- Client path that refuses minting a second person when an anchored lemma.id
  already exists on-device
- Broader jurisdiction aliases only where document numbers are known equivalent
