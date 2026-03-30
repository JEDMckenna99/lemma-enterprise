# Trust Calculus Paper Accuracy Redline (Current Lemma.id State)

Date: 2026-02-26  
Target: `docs/trust-calculus-paper.md`  
Purpose: Separate implementation-confirmed statements from theory/roadmap claims.

## How to Use This Redline

- Treat this as an editorial companion, not a replacement for the paper.
- For each section, keep claims in one of two buckets:
  - **Current implementation fact**: directly supported by repo/runtime evidence.
  - **Roadmap/theory**: formal model, design intent, or future-state behavior.
- If a claim is not directly test-backed, reword to bounded language.

## Section-by-Section Classification

## 0) Title and Positioning

Current title is acceptable if the document is framed as a formal proposal.  
If positioned as production status, add a subtitle:

`Formal Model and Reference Architecture (with current implementation notes)`

## 1) Abstract

Status: **Partially accurate, needs softening**

### Keep as implementation fact
- Ed25519-signed credentials exist.
- Local verification exists.
- PPID derivation exists and is HMAC-SHA256-based.
- Revocation endpoints and Bloom payload exist.

### Move to roadmap/theory (or qualify)
- "chain A->B->C is itself a locally-verifiable proof" as a universal production claim.
- "Revocation of any lemma in a chain cryptographically invalidates all downstream compositions" as a proven runtime invariant.
- "We prove three safety properties" as a completed proof claim.
- "1-3 orders of magnitude improvement" unless benchmark methodology and reproducible artifacts are published.

### Suggested replacement text (abstract-safe)
"We present Trust Calculus, a formal model for composing signed trust assertions.  
The current Lemma.id implementation supports signed lemma issuance, local verification, PPID-based pairwise identity, and revocation distribution primitives.  
We provide formal arguments for attenuation, revocation propagation, and unlinkability, and describe the implementation path toward full chain-native enforcement."

## 2) Introduction (Sections 1.1-1.3)

Status: **Mostly acceptable with bounded claims**

### Edits
- Replace absolute ecosystem claims ("no standardized mechanism") with "limited deployment-standard support across common stacks."
- Keep contribution bullets, but mark composition/revocation properties as model-level when not yet uniformly enforced in all endpoint paths.

## 3) Formal Definitions (Section 3)

Status: **Accurate as formal model**

### Edits
- Add one line at section start:
  "This section defines the calculus semantics; implementation conformance is tracked incrementally."
- Keep mathematical definitions unchanged.

## 4) The Trust Calculus Operations (Section 4.1)

Status: **Model accurate, implementation partial**

### Needed qualifiers
- `issue`: implemented.
- `verify`: implemented for signed credential + trust + expiry + revocation checks.
- `compose`: formalized; not uniformly represented as first-class chain objects across all current authz paths.
- `revoke`: implemented as revocation data update with distributed checks; chain-complete invalidation requires explicit chain verification path.

### Suggested insertion after 4.1
"Implementation note: current production enforcement verifies credential validity and policy constraints on protected routes. Full first-class chain continuity checks are being unified under the authz verifier contract."

## 5) Safety Properties (Section 4.2)

Status: **Needs wording change from proof to argument**

### Replace headings
- "Property 1: Monotonic Attenuation" -> "Property 1 (Model): Monotonic Attenuation"
- "Property 2: Revocation Completeness" -> "Property 2 (Model): Revocation Completeness"
- "Property 3: Unlinkability Under Composition" -> "Property 3 (Model): Unlinkability Under Composition"

### Replace "We prove" wording
- Use "We provide formal arguments/sketches under stated assumptions."
- If kept as "proof," point to machine-checked artifacts or peer-reviewed appendix.

## 6) Revocation Model (Section 5)

Status: **Partially accurate, update to current serving behavior**

### Current-state correction
- Current API includes a hashed revoked-id set and optional Bloom payload.
- Avoid describing cascaded Bloom as the only runtime distribution mechanism.

### Suggested replacement text
"The revocation API currently serves SHA-256-hashed revocation identifiers for compatibility and may include compact Bloom payload metadata for scalable clients. Cascaded Bloom operation remains part of the formal design direction."

## 7) PPID (Section 6)

Status: **Mostly accurate, tighten normalization statement**

### Edit
- Replace strict canonicalization language with implementation-bounded wording:
  "PPID derives from normalized relying-party host input; normalization hardening is tracked as a conformance guardrail."

## 8) Performance Analysis (Section 7)

Status: **High-risk claims; needs evidence-bound rewrite**

### Required changes
- Convert deterministic microsecond numbers to measured ranges by mode/environment.
- Replace direct cross-system superiority table language with:
  "Indicative comparison; methodology and assumptions documented separately."
- Remove "exceeds all other systems" style statements.

### Safer wording
"Observed verification latency depends on mode (WASM/WebCrypto/native), chain depth, and runtime environment. Reported values should be treated as benchmark observations under stated conditions, not universal guarantees."

## 9) Agent Systems and Generalized Applications (Sections 8-9)

Status: **Conceptually valid, should be labeled as patterns**

### Edit
- Add prefix sentence:
  "The following are reference patterns demonstrating how the calculus can be applied."
- Avoid implying all scenarios are production-hardened today.

## 10) Reference Implementation (Section 10)

Status: **Partially accurate**

### Keep
- Flask + Rust (PyO3) architecture.
- Browser verification modes including WebCrypto/WASM.
- Wallet/passkey architecture direction.

### Update
- Remove/qualify references to fallback paths that are no longer intended policy if Rust-only verification is required for server enforcement.
- Clarify that client modes differ from server enforcement contract.

## 11) Limitations and Future Work (Section 11)

Status: **Good section; should be expanded**

### Additions
- Endpoint policy parity is still being unified.
- Chain-native conformance tests are in progress.
- Revocation distribution behavior and propagation semantics depend on deployment sync characteristics.

## 12) Conclusion (Section 12)

Status: **Needs de-hyperbolization**

### Edit examples
- "formal system ... no existing system provides" -> "formal system targeting a combination of properties that is uncommon in mainstream deployments."
- "trust ceases to be a gate" -> "trust evaluation can shift toward local, low-latency checks where conformance is enforced."

## Claim Risk Register (Top Priority Fixes)

1. **"We prove three safety properties"**  
   Risk: interpreted as machine-checked or peer-reviewed proof.  
   Fix: "formal arguments" unless proof artifacts are published.

2. **"1-3 orders of magnitude improvement"**  
   Risk: benchmark challenge without full reproducibility and comparable setup.  
   Fix: include benchmark protocol and soften to measured scenarios.

3. **"Revoking any link invalidates all downstream compositions" (runtime universal)**  
   Risk: overstates current enforcement if chain continuity is not uniformly enforced at all auth boundaries.  
   Fix: mark as calculus property and implementation target.

4. **"No network dependency at point of trust evaluation" (absolute)**  
   Risk: stale revocation sync and deployment topology caveats.  
   Fix: "no online issuer callback required for local cryptographic verification; revocation freshness depends on sync model."

## Minimal Edit Pass Order (Low-Risk First)

1. Abstract claim softening
2. Property wording ("arguments" vs "prove")
3. Revocation section runtime clarification
4. Performance section evidence-bounded rewrite
5. Conclusion tone correction

## Suggested Document Footer

"Accuracy note: This paper contains formal system definitions and implementation guidance.  
Sections marked as model properties describe calculus semantics; production conformance is tracked via the Lemma.id authz and verification rollout artifacts."
