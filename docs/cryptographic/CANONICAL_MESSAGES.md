# Lemma isHuman Canonical Message Specification

> The exact byte-level format of every signed/derived payload in the isHuman
> system. Third-party SDKs (Go, Rust) MUST produce these bytes exactly to
> generate verifiable signatures. The test vectors below are pinned in
> [tests/test_cryptographic_invariants.py](../../tests/test_cryptographic_invariants.py)
> — a diff there is a protocol-breaking change.

All multi-byte hashes are SHA-256. All signatures are Ed25519. All JSON uses
compact separators (`,` and `:`) with no insignificant whitespace.

---

## 1. Pairwise PPID

- **Inputs:** `person_root` (32 bytes), `rp_id` (site domain string).
- **Canonicalization:**
  1. `site = canonicalize_rp_id(rp_id)` (lowercase, strip scheme/path/port, strip `www.`).
  2. `message = ("lemma.id/site-ppid/v1" + site).encode("utf-8")`.
  3. `ppid_hex = HMAC_SHA256(key=person_root, msg=message).hexdigest()`.
  4. Result: `did:lemma:ppid_<ppid_hex>`.
- **Reference:** `api/ppid.py::derive_ppid_from_person_root` ->
  `api/identity_roots.py::derive_ppid_from_person_root_bytes`.
- **Test vector:**
  - `person_root = bytes.fromhex("aa"*32)`, `rp_id = "example.com"`
  - => `did:lemma:ppid_9d361fce9d528a34ccc86f1f83882743068855fe517f7cbe0c995ecdbfeed20c`

## 2. Document root hash

- **Inputs:** `StripeIdentityRootMaterial` (country, document_type, document_number,
  date_of_birth, optional id_number_type/last4).
- **Canonicalization:**
  1. Build claim dict (normalize country/type/number; fixed `schema` + `provider`).
  2. `canonical_json_bytes(claims)` = JSON with **sorted keys**, compact separators.
  3. `digest = HMAC_SHA256(key=pepper, msg=canonical_json).hexdigest()`.
- **Reference:** `api/identity_roots.py::build_document_root_claims` +
  `derive_document_root_hash`.
- **Test vector** (pepper = `b"invariant_test_pepper_0123456789"`):
  - material `US / driving_license / D1234567 / 1985-03-12`
  - claims => `{"country":"US","date_of_birth":"1985-03-12","document_number":"D1234567","document_type":"driving_license","provider":"stripe_identity","schema":"lemma.identity.document-root.v1"}`
  - digest => `f8ee8a3db8d5c71eecf17096d8133dfe5c9a2927a885817d15c3c755a1209321`

## 3. Person root (server-only, never leaves)

- **Inputs:** `document_root_hash` (64 hex chars).
- **Canonicalization:** `HKDF(SHA256, length=32, salt=person_root_salt, info=b"lemma.id/person-root/v1").derive(bytes.fromhex(document_root_hash))`.
- **Reference:** `api/identity_roots.py::derive_person_root_bytes`.

## 4. isHuman credential `signatureValueWeb` (browser-canonical message)

- **Inputs:** credential dict (`issuer`, `subject`, `claims`, optional `issuedAt`/`expiresAt`).
- **Canonicalization** (mirrors `static/js/ishuman-verifier.js::canonicalMessage`):
  1. Sort `claims` by key.
  2. Booleans become the **strings** `"true"`/`"false"`; arrays/objects become compact JSON strings; other scalars pass through.
  3. `payload = {issuer, subject, claims: sorted_claims}` (+ `issuedAt`/`expiresAt` only when present).
  4. `message = JSON.stringify(payload)` with compact separators, UTF-8 encoded.
  5. Signature is Ed25519 over `SHA256(message)`.
- **Reference:** `api/ishuman.py::_browser_canonical_message` + `_sign_with_issuer_for_browser`;
  Python verifier `packages/ishuman-verify-py/lemma_ishuman_verify.py::browser_canonical_message`.
- **Test vector:**
  - input `{issuer:"did:lemma:issuer:test", subject:"did:lemma:ppid_abc", claims:{isHuman:true, siteId:"example.com", expiresAt:"4102444800"}}`
  - => `{"issuer":"did:lemma:issuer:test","subject":"did:lemma:ppid_abc","claims":{"expiresAt":"4102444800","isHuman":"true","siteId":"example.com"}}`

## 5. Session presentation payload

- **Inputs:** assertion with `session_id`, `site_id`, `credential_id`, `subject`,
  `session_nonce`, `bloom_sequence`, `issued_at_unix`, `expires_at_unix`.
- **Canonicalization:** newline-joined (`\n`) lines, in this exact order, prefixed by
  `lemma:site-session-presentation:v1`; each value `.strip()`-ed (numbers stringified). Ed25519-signed by the per-site signing key.
- **Reference:** `static/js/ishuman-verifier.js::buildSessionPresentationPayload`;
  server `api/ishuman.py::_verify_session_assertion_server`;
  Python verifier `_build_session_message`.
- **Test vector:**
  ```
  lemma:site-session-presentation:v1
  sess_1
  example.com
  ishuman_site_1
  did:lemma:ppid_abc
  nonce_1
  7
  1700000000
  1700086400
  ```

## 6. Wallet assertion payload

- **Inputs:** `wallet_id`, `nonce_b64`, ordered `field_names` + `field_values`.
- **Canonicalization:** `api/wallet_authn.py::build_assertion_payload` (deterministic
  ordering of bound fields; missing field values bind as the empty string). Ed25519-signed
  by the wallet signing key (HKDF-derived from `wallet_secret`).
- **Note (Phase 1.2):** for `derive-site-proof`, `master_credential_id` is included in
  `field_names` **only when supplied**; the wallet and server must agree on the conditional
  field set. See `api/ishuman.py::derive_site_proof` and `lemma-wallet.js::deriveAndStoreSiteProof`.

## 7. Wallet master secret derivation

- **Inputs:** `wallet_secret` (64-hex or raw string).
- **Canonicalization:** `HMAC_SHA256(key=LEMMA_PPID_ROOT_KEY, msg=wallet_secret_bytes)`.
- **Reference:** `api/ppid.py::derive_master_secret_from_wallet_secret`.
- **Test vector** (root key = `b"invariant_root_ppid_key_01234567"`, wallet_secret = `"ab"*32`):
  - => `c060ff2951a71f8ba8094bdef0329e2bc83e9445ff5a0bcd9b486148c3fce24d`

## 8. Bloom snapshot + trust list envelopes

- **Bloom snapshot:** `api/bloom_snapshot.py::build_signature_message` — prefix
  `lemma:bloom-snapshot:v1`, includes the monotonic `sequence_number`. SDK rejects
  sessions whose `bloom_sequence` does not match the current snapshot sequence.
- **Trust list:** `api/issuer_trust_list.py` — signed multi-issuer list; clients pin
  trusted issuer DIDs and refetch on rotation.

## 9. PPID convergence artifact (`ppid_convergence.v1`)

- **When issued:** only when a provisional wallet rebinds to a known document-anchored
  person and the site-scoped legacy PPID differs from the canonical PPID.
- **Inputs:** `site_id`, `legacy_ppid`, `canonical_ppid`, `convergence_id`, `nonce`,
  `issued_at_unix`, `expires_at_unix`.
- **Canonicalization:** newline-joined (`\n`) lines, in this exact order, prefixed by
  `lemma:ppid-convergence:v1`; each value `.strip()`-ed (numbers stringified). SHA-256
  digest is Ed25519-signed by the Lemma isHuman issuer key.
- **Reference:** `api/ppid_convergence.py::build_convergence_canonical_message`;
  Python verifier `verify_ppid_convergence_artifact`; JS verifier
  `verifyPpidConvergenceArtifact`.
- **Test vector:**
  ```
  lemma:ppid-convergence:v1
  example.com
  did:lemma:ppid_legacy0123456789abcdef0123456789abcdef0123456789abcdef01234567
  did:lemma:ppid_canon0123456789abcdef0123456789abcdef0123456789abcdef012345678
  conv_test_vector_001
  nonce_test_001
  1700000000
  1700003600
  ```

> Third-party SDKs that only need to verify (not issue) must implement sections
> 1, 4, 5, 8, 9, and 10 when handling provisional-to-known-person convergence
> or fresh-passkey action policies.

## 10. Fresh-passkey attestation (`fresh_passkey_attestation.v1`)

- **When issued:** only after lemma.id verifies a new WebAuthn assertion for a
  wallet/device passkey registered server-side.
- **Inputs:** `site_id`, `credential_id`, `subject` (PPID), opaque
  `action_commitment`, `attestation_id`, `issued_at_unix`, `expires_at_unix`.
- **Action commitment (site-local, privacy-preserving):** SHA-256 hex digest of
  newline-joined (`\n`) lines prefixed by `lemma:action-commitment:v1` over
  `server_nonce`, `site_id`, `action`, `method`, `path`, `body_hash`. lemma.id
  never receives the raw action name or body — only the commitment hash.
- **Canonicalization:** newline-joined lines prefixed by
  `lemma:fresh-passkey-attestation:v1`; each value `.strip()`-ed (numbers
  stringified). SHA-256 digest is Ed25519-signed by the Lemma isHuman issuer key.
- **Reference:** `api/fresh_passkey_attestation.py`; Python verifier
  `verify_fresh_passkey_attestation`; JS verifier `verifyFreshPasskeyAttestation`.
