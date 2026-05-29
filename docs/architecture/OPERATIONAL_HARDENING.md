# isHuman operational hardening (Phase 3)

Corresponds to Phase 3 of
[`V2_DESIGN_IMPROVEMENTS.md`](V2_DESIGN_IMPROVEMENTS.md). Phase 3.1 (pepper/salt
rotation) is implemented; 3.2 (multi-issuer) and 3.3 (Bloom scaling) are designs
plus scaffolding, with full integration deferred.

## 3.1 Versioned pepper/salt rotation (implemented)

`LEMMA_IDENTITY_ROOT_PEPPER_*` and `LEMMA_PERSON_ROOT_SALT_*` are network-root
secrets. A compromise lets an attacker compute `person_root` for any document
they know, so we need a rotation path that does not orphan existing identities
overnight.

### Model

- Peppers and salts are versioned: `LEMMA_IDENTITY_ROOT_PEPPER_V1`,
  `_V2`, ...; `LEMMA_PERSON_ROOT_SALT_V1`, `_V2`, ... — kept concurrently.
- `LEMMA_ACTIVE_ROOT_VERSION` selects the version new IDVs derive under
  (default `v1`).
- Each `lemma_persons` / `lemma_document_roots` / `ishuman_verifications` row
  records its `root_version`.
- Old rows keep working until their credential expires
  (`ISHUMAN_CREDENTIAL_TTL_DAYS`, default ~2 years). A version is retired only
  once no active row references it.

### Code

- [`api/identity_roots.py`](../../api/identity_roots.py):
  - `active_root_version()` reads `LEMMA_ACTIVE_ROOT_VERSION` (default `v1`).
  - `_get_identity_root_pepper(version)` / `_get_person_root_salt(version)` resolve
    `LEMMA_*_{VERSION}`; `V1` preserves legacy resolution (so pinned crypto
    invariants stay byte-stable), and a missing/short secret for any other
    version raises `IdentityRootError` (fail closed).
  - `derive_document_root_hash`, `derive_person_root_bytes`,
    `derive_person_root_hash`, `derive_ppid_from_document_root_hash`,
    `document_root_hash_from_material` all take an optional `version`.
- [`api/identity_person.py`](../../api/identity_person.py) derives new roots under
  `active_root_version()` and stamps the version onto the person + document-root rows.
- [`api/ishuman.py`](../../api/ishuman.py) stamps `IsHumanVerification.root_version`
  with the active version.

### Rotation runbook

1. Generate a new high-entropy pepper and salt (>= 32 bytes each).
2. Provision `LEMMA_IDENTITY_ROOT_PEPPER_V2` and `LEMMA_PERSON_ROOT_SALT_V2`
   alongside the existing V1 values (do not remove V1).
3. Deploy. Verify nothing else changed (V1 rows still verify).
4. Flip `LEMMA_ACTIVE_ROOT_VERSION=V2`. New IDVs now derive under V2.
5. Leave V1 in place until no active credential references it, then retire it.

### Cross-version continuity (UX cost)

A user verified pre-rotation has different PPIDs post-rotation, because PPIDs
derive from `person_root`, which depends on the pepper/salt version. To preserve
identity continuity:

- The post-rotation master VC can carry a `legacy_ppid` claim when a pre-rotation
  record exists for the wallet.
- Opt-in relying sites honor the legacy PPID for migration (treat the user as the
  same identity).

This is an emergency operation, not routine. The default behavior is a clean
discontinuity, which is acceptable for a key-compromise response.

## 3.2 Multi-issuer trust list (design + scaffold)

Today Stripe Identity is the only integrated IDV provider, though the trust-list
architecture already supports multiple issuers.

### Design

1. Add a second issuer (e.g. Persona or Veriff).
2. Each issuer has its own pepper namespace:
   `LEMMA_IDENTITY_ROOT_PEPPER_<ISSUER>_V1`.
3. `ishuman_verifications.issuer_id` records the issuer
   (`stripe_identity`, `persona`, ...).
4. The trust list publishes all active issuers; relying sites accept a signature
   from any listed issuer.
5. Reissuance / reset works regardless of which issuer originally verified.

### Scaffold (this phase)

- `IsHumanVerification.issuer_id` column added
  ([`api/database.py`](../../api/database.py)), defaulted to `stripe_identity`,
  indexed; migration
  [`026_ishuman_issuer_id.sql`](../../migrations/026_ishuman_issuer_id.sql).
- No issuer-routing logic yet — full integration (webhooks, document
  canonicalization, error handling, billing) is ~2-3 weeks per issuer and is
  deferred until the first issuer is stable at production scale.

## 3.3 Bloom filter scaling (design)

The current revocation Bloom is global, sized for ~100K capacity at 1e-6 FPR.
Beyond ~1M revocations, false positives become operationally meaningful.

### Option A — Cascaded Bloom (CRLite-style)

```text
Layer 1: large Bloom of all revoked credential IDs (FPR ~1e-3)
Layer 2: smaller Bloom of layer-1 false positives
         (real credentials that hash-collide with revoked ones)
Layer 3 (if needed): smaller still

Verify: query L1 -> if hit, query L2 -> if hit, NOT REVOKED
        (it is a known false positive of L1); otherwise REVOKED
Net FPR ~1e-6 at ~4x smaller total size than a single Bloom.
```

Construction needs a cascade builder (e.g. Mozilla's `filter-cascade`).

### Option B — Per-issuer partitioned Bloom

Each issuer publishes a Bloom for the credentials it issued; clients fetch only
the Bloom for the issuer of the credential they are verifying. Simpler than the
cascade, but requires multi-issuer (3.2) in production first.

### Decision criteria

Pick a scaling approach when revocation volume exceeds ~500K (well before
operational issues). Both are well-understood patterns; neither is needed yet.
