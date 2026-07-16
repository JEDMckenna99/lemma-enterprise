## Digital Lemmas: An Edge-Verifiable Layer for Internet Identity
**Author:** Jed McKenna  
**Issuer:** Lemma ID (`lemma.id`)  
**Date:** 2025-12-21 (revised v2 - Federated Architecture)

## Abstract
Internet identity relies on trusted institutions to mediate verification. In common deployments, a relying party depends on an online registry, session store, or identity provider to validate users and permissions. This architecture increases latency and availability coupling, concentrates breach risk, and creates a natural correlation point where identity presentations can be observed.

We propose **digital lemmas**: user-held, self-verifying proof objects signed using Ed25519. The system supports a **federated issuer model** where:
- **User wallets** are the foundation, unlocked locally via passkey (free, no PoH required)
- **Any participating site** can issue its own lemmas for site-specific claims (roles, permissions, memberships)
- **Lemma.id** provides optional Proof-of-Human credentials for sites requiring anti-bot protection
- The **passkey is the root of trust**, not PoH - wallets work without human verification

Unlike registry-dependent systems, lemmas enable **direct holder-verifier validation**: lemmas are presented directly by a holder to a verifier, and verification can be performed locally by validating the signature and consulting cached revocation data. The **verification hot-path** is designed to run at the verifier (including edge deployments) and/or the user device, reducing online lookup dependency.

Implementation note: the current deployed system distributes revocation data as a **SHA-256-hashed revocation set** that can be checked locally after syncing. Bloom filters and OPRF-based revocation are compatible extensions, but are not required for basic offline revocation enforcement.

## 1. Introduction
On the Internet, authentication and authorization are commonly implemented as online lookups against centralized services:
1) the user is authenticated, producing a server-managed session or token;  
2) subsequent requests are validated via session lookup, token introspection, or refresh workflows.

This structure has two persistent problems:
- **Availability and latency coupling**: each verifier depends on online service availability and round-trip latency.
- **Correlation and data gravity**: central intermediaries can observe (and therefore log and aggregate) identity presentations at scale.

We propose moving the core verification step to the edges of the network: between the holder and the verifier, using self-verifying proofs. Unlike registry-dependent approaches, the verifier does not need to ask a third party “is this still valid?” on each decision; instead, the verifier validates a signed proof locally and consults locally cached revocation data.

## 2. Overview
A digital lemma is a signed proof of a small set of claims. The issuer is contacted to issue or revoke lemmas, but not to verify them. The steps are:
1) **Issuance**: the issuer verifies a prerequisite (email verification now, Proof-of-Human verification later) and signs a lemma.  
2) **Storage**: the holder stores the lemma locally (encrypted at rest).  
3) **Presentation**: the holder presents the lemma to a verifier as needed.  
4) **Verification**: the verifier validates the signature and checks local revocation data.  

The result is issuer-free verification at runtime: the verifier can accept or reject the proof locally.

## 2.1 Central issuance, edge verification
Digital lemmas are not “peer-to-peer issuance.” In the current design, `lemma.id` is a single issuer that:
- issues lemmas (online),
- revokes lemmas (online),
- publishes revocation and issuer metadata for verifiers to cache (out-of-band).

The peer-to-peer-like property is narrower and specific:
- **presentation and verification** are performed directly between holder and verifier without an issuer callback. This supports **edge-verifiable** operation: verification can be colocated with the relying party (including edge networks) and does not require a round-trip to the issuer or an identity registry during the access decision.

### 2.2 Current deployment status (what is live vs what is planned)
To keep claims precise, we distinguish:
- **Deployed today (lemma.id)**: email-based IAM issuance; revocation synchronization via `/api/revocation/bloom-filter` (currently a SHA-256-hashed revocation set); many flows also offer server-side verification endpoints for convenience.
- **Designed / available in codebase**: client-side signature verification via the browser's native Web Crypto API (`crypto.subtle.verify()` with Ed25519 support) with optional WASM fallback; more advanced revocation mechanisms (Bloom filter compression and OPRF-based privacy hardening).
- **Planned / not currently deployed**: Proof-of-Human (PoH) as a production root step at `lemma.id` (used to issue "isHuman=true" at scale).

## 3. Digital lemmas
We model a lemma as a tuple:
\[
L = (id, issuer, subject, claims, expires\_at, \sigma)
\]
where:
- \(id\) is a unique lemma identifier,
- \(issuer\) identifies the signing authority (currently `lemma.id`),
- \(subject\) is a pairwise identifier derived for a specific relying party,
- \(claims\) is a map of asserted properties,
- \(expires\_at\) is an optional expiration time,
- \(\sigma\) is an Ed25519 signature over a canonical encoding of \((id, issuer, subject, claims, expires\_at)\).

Digital lemmas are influenced by verifiable credential designs, but the system is not defined by a specific VC profile. The defining properties are: **self-verification**, **offline-capable revocation enforcement**, and **issuer-free verification at presentation time**.

### 3.1 Naming rationale
We call these proofs “lemmas” by analogy to mathematical lemmas: once a lemma is established, it can be reused as a building block without re-deriving it each time. Similarly, a verifier can reuse a digital lemma as a building block for higher-level decisions without re-running the original issuance verification process. If a required lemma is **revoked, expired, or out-of-policy**, then downstream decisions that depend on it can be rejected immediately, even though the underlying signature may remain cryptographically valid.

## 4. Pairwise subject identifiers
To avoid embedding a stable cross-site identifier, we derive a pairwise subject per relying party:
\[
subject = \texttt{did:lemma:ppid\_}\mathrm{HMAC}(\text{master\_user\_secret}, \text{rp\_id})
\]

Properties:
- **Pairwise unlinkability**: the same holder yields different subjects at different relying parties.
- **Continuity**: the same holder and same relying party yield the same subject, enabling stable accounts without global identifiers.

This parallels the operational privacy property of using different identifiers per counterparty: it limits passive correlation from proof contents.

## 5. Issuance and presentation
### 5.1 Issuance (issuer online)
Issuance requires the issuer:
1) the holder requests a lemma,
2) the issuer verifies an issuance prerequisite (email verification in the initial deployment; Proof-of-Human verification in later deployments),
3) the issuer signs and returns the lemma.

Pseudocode (high level):
```
IssueLemma(rp_id, claims, prerequisite_proof):
  assert VerifyPrerequisite(prerequisite_proof) = true
  subject <- PPID(master_user_secret, rp_id)
  id <- FreshIdentifier()
  expires_at <- PolicyExpiry(claims)
  sigma <- Ed25519Sign(issuer_sk, Canon(id, issuer, subject, claims, expires_at))
  return (id, issuer, subject, claims, expires_at, sigma)
```

### 5.2 Presentation (issuer-free)
Presentation does not involve the issuer. The verifier:
1) parses lemma fields,
2) reconstructs the signed message,
3) verifies the Ed25519 signature under the issuer public key,
4) checks expiration and local policy constraints,
5) checks revocation against locally cached revocation data.

## 6. Revocation
Revocation is a requirement for long-lived, user-held proofs. A system that cannot revoke proofs typically resorts to very short-lived tokens, shifting verification back into online refresh and introspection.

### 6.1 Deployed mechanism: SHA-256-hashed revocation set
In the current deployment, the issuer publishes a list/set of SHA-256 hashes of revoked lemma identifiers. The verifier (or wallet) hashes the presented lemma identifier locally (via WebCrypto) and checks set membership locally after syncing the list.

Properties:
- **No issuer callback per verification**: membership tests are local.
- **No false positives**: exact set membership (unlike Bloom filters).
- **Trade-off**: larger distribution artifact than a compact Bloom filter representation at high scale.

### 6.2 Optional optimization: Bloom filter compression
Bloom filters can reduce distribution size by trading storage for a tunable false positive probability \(p\). For a Bloom filter \(B\) of size \(m\) bits with \(k\) hash functions containing \(n\) revoked elements, the false positive probability is:
\[
p \approx \left(1 - e^{-kn/m}\right)^k
\]

### 6.3 Distribution model
Revocation publication is out-of-band:
1) issuer revokes lemma \(id\), producing revocation token \(r\),
2) issuer updates the published revocation artifact (currently a hashed revocation set; optionally a Bloom filter),
3) verifiers synchronize updates periodically and/or event-driven,
4) verification-time checks use the local cache.

## 7. The verification network
### 7.1 Roles
- **Issuer**: `lemma.id` issues and revokes lemmas and publishes issuer metadata and revocation data.
- **Holder**: stores lemmas locally and presents them.
- **Verifier / relying party**: validates lemmas locally and enforces revocation via cached filters.

### 7.2 Operational steps
The steps to operate the verification layer are:
1) distribute issuer verification keys and revocation filters to verifiers (cacheable, broadly shared artifacts),
2) issue lemmas to holders as needed,
3) verify lemmas locally at the relying party,
4) propagate revocation updates as filters evolve.

## 8. Network Defense Properties

Unlike per-site identity verification, Lemma credentials create a **shared defense network** where sites benefit from each other's detection without sharing user data.

### 8.1 Single-site verification vs network verification

**Traditional single-site verification:**
- Each site independently verifies users (e.g., $1.50 per ID verification)
- If a user is banned on Site A, Sites B, C, D have no knowledge
- Bad actors can attack sites sequentially, paying re-verification costs per site
- No shared threat intelligence across sites

**Lemma network verification:**
- User verifies once; credential works across all participating sites
- If any site revokes a credential, it is revoked **everywhere**
- Relying sites can persistently block their own site-private PPID
- Revocation set **is** the shared threat intelligence

### 8.2 Economic comparison

| Metric | Single-site verification | Lemma network |
|--------|-------------------------|---------------|
| Verification cost per site | $1.50/user | $0/user (after first) |
| Cost for 10 sites | $15/user | $1.50/user total |
| Sites protected per detection | 1 | All participating sites |
| Re-attack cost for bad actor | $1.50 per site | $1.50 per credential |
| Threat intelligence | Siloed | Shared via revocation |

For verifiers: joining the network provides defense at zero per-verification cost.

For attackers: the cost-benefit calculation changes fundamentally. Getting caught **once** burns the credential everywhere, requiring re-verification to continue attacking.

### 8.3 User-initiated revocation

Users can revoke their own credentials if compromised. This protects **all** participating sites simultaneously, analogous to canceling a stolen credit card rather than notifying each merchant individually.

### 8.4 Network effects and defense flywheel

The network creates a positive feedback loop for defense:

```
More sites join the network
         ↓
More detection coverage (more eyes)
         ↓
Faster revocation of bad actors
         ↓
Better defense for all participating sites
         ↓
More sites want to join
         ↓
(repeat)
```

This network effect is the primary structural advantage over isolated verification systems.

### 8.5 Threat model implications

| Scenario | Single-site | Lemma network |
|----------|-------------|---------------|
| Bad actor caught botting | Banned from 1 site | Banned from all sites |
| User credential stolen | User contacts each site | User revokes once, protected everywhere |
| New site joins | No historical defense | Inherits network's revocation history |
| Detection time | Site-dependent | Network-wide (faster aggregate detection) |

The revocation set functions as implicit threat intelligence: sites do not share user data, but they do share the fact that specific credentials have been revoked.

## 9. Incentives
Digital lemmas change the cost and privacy profile of verification by moving the runtime decision to local/edge computation.

- **Holders (users)**: reduced password exposure; fewer repeated identity disclosures; fewer centralized correlation points.
- **Verifiers / relying parties**: lower latency and fewer online dependencies; reduced centralized session infrastructure; narrower data collection for many decisions.
- **Issuer (`lemma.id`)**: concentrates responsibility on issuance/revocation quality and key management, while reducing the need to operate per-verification online lookups.

## 10. Diagrams
### Figure 1: Roles and trust boundaries
```
┌──────────────────────────────────────────────────────────────┐
│                         Issuer (lemma.id)                    │
│ - Issues lemmas (Ed25519 signatures)                         │
│ - Revokes lemmas (updates revocation set)                    │
│ - Publishes revocation Bloom filter(s) + issuer metadata     │
└───────────────┬───────────────────────────────┬──────────────┘
                │                               │
                │ issuance / revocation         │ revocation + issuer metadata sync
                │ (online)                      │ (out-of-band)
                │                               │
        ┌───────▼─────────┐             ┌───────▼────────────────┐
        │ Holder (wallet) │             │ Verifier / Relying Party│
        │ - Stores lemmas  │             │ - Verifies signature     │
        │   encrypted local│             │ - Checks Bloom revocation│
        │ - Presents lemmas│             │ - Applies policy         │
        └───────┬─────────┘             └────────┬────────────────┘
                │ presentation (issuer-free)      │
                └──────────────►──────────────────┘
```

### Figure 2: Lemma structure (conceptual)
```
Lemma L:
  id         : unique identifier
  issuer     : issuer identifier (DID/public key binding)
  subject    : pairwise subject for this RP (PPID)
  claims     : small set of asserted facts
  expires_at : optional expiry
  sigma      : Ed25519 signature over canonical encoding of fields above
```

#### Figure 3: Verification algorithm (high level)
```
Verify(L, issuer_pk, RevocationSet):
  if now > L.expires_at: reject
  if not Ed25519Verify(issuer_pk, Canon(L fields), L.sigma): reject
  if RevocationSet.contains(SHA256(L.id)): reject
  accept
```

Note: In the deployed system, `RevocationSet` is currently a SHA-256-hashed set (exact membership). Bloom filter compression is an optional optimization. Browser implementations use the Web Crypto API for both `Ed25519Verify` and `SHA256` operations.

## 11. Performance and resource requirements
### 11.1 Cryptographic verification speed (measured)

The cryptographic verification hot path is **local** and can run without a per-check issuer callback when keys/revocation data are already synced. Full authentication lifecycles can still include network calls for issuance, session management, and revocation synchronization.

**Measured performance (December 2024):**

| Environment | Verification Time | Network Required |
|-------------|-------------------|------------------|
| Rust/Native (server-side) | ~**31–47 µs** | No |
| Browser (Web Crypto API) | ~**0.5–1 ms** | No |
| Auth0/Okta token validation | ~**200–500 ms** | Yes |

**Browser verification (Web Crypto API):**
- Average: ~**1 ms** (sub-millisecond in many runs)
- Throughput: ~**1,000–2,000 verifications/second**
- Network calls: **zero**
- Cost per verification: **$0**

**Comparison with centralized identity providers:**
- vs Auth0 (200-500ms): **200–500x faster**
- vs custom session lookup (20-100ms): **20–100x faster**

The performance advantage comes from eliminating network round-trips, not from faster cryptographic operations. A 1ms local verification is dramatically faster than a 50ms database lookup that requires crossing the internet.

### 11.2 Optional calculations: Bloom filter sizing example
For \(n\) revoked lemmas and target false positive probability \(p\), an approximately optimal Bloom filter size is:
\[
m \approx -\frac{n \ln p}{(\ln 2)^2}
\]
and the approximately optimal number of hash functions is:
\[
k \approx \frac{m}{n}\ln 2
\]

Example: \(n = 10^6\) revocations and \(p = 10^{-6}\) yields:
- \(m \approx 2.88 \times 10^7\) bits \(\approx 3.6\) MiB
- \(k \approx 20\)

This illustrates that very low false-positive targets can be achieved with modest, cacheable artifacts if Bloom filter compression is used. The deployed system can also use an exact hashed revocation set (no false positives) at the cost of larger distribution artifacts.

### 11.3 Why local verification is the differentiator
The performance advantage is **not** about faster cryptographic operations, Ed25519 verification takes roughly the same time everywhere. The advantage is **eliminating the network call**.

| Factor | Local Verification | Centralized Lookup |
|--------|-------------------|-------------------|
| **Latency** | ~1 ms | ~50–500 ms |
| **Availability** | Works offline | Requires connectivity |
| **Cost per check** | $0 | $0.001–0.01 |
| **Scales with** | Device CPU | Server infrastructure |

Operational implications:
- **Latency**: 100–500x faster than network round-trips to identity providers.
- **Availability**: verification continues through network partitions as long as issuer keys and revocation data are cached.
- **Cost**: zero per-verification cost after initial SDK/filter sync. At scale (millions of verifications), this eliminates significant infrastructure spend.
- **Privacy**: no per-verification data sent to centralized services.

### 11.4 Storage and distribution
Bloom filter size depends on \(m\) and expected \(n\). The distribution overhead is moved from per-verification calls to periodic/event-driven filter synchronization.

## 12. Security and privacy analysis
### 12.1 Signature security (Ed25519)
Lemma authenticity and tamper resistance reduce to the unforgeability of Ed25519 signatures under standard assumptions. In short:
- issuer computes \(\sigma \leftarrow Sign(sk, m)\)
- verifier accepts only if \(Verify(pk, m, \sigma) = 1\)

If Ed25519 is EUF-CMA secure, forging a valid lemma signature without the issuer signing key is computationally infeasible at the target security level (approximately 128-bit).

### 12.2 Threat model summary table
| Threat | Assumptions | Mitigations | Notes / probabilities |
|-------|-------------|-------------|------------------------|
| Signature forgery | Ed25519 EUF-CMA security; issuer key not compromised | Ed25519 verification; issuer key management | Forgery probability is negligible under the security level absent key compromise |
| Tampering with claims | Canonical message covers all fields | Sign/verify over canonical encoding | Any change to signed fields invalidates verification |
| Cross-site correlation from identifiers | RP IDs are correctly canonicalized; PPID secret remains secret | Pairwise subject derivation (PPID) | Prevents a stable global identifier from being embedded in proofs |
| Issuer observation of presentations | Verifiers do not perform per-check issuer callbacks | Local verification + cached issuer metadata + cached revocation filters | Issuance/revocation are still observed by issuer; presentation is not protocol-required to be |
| Replay / reuse of stolen lemma | Attacker obtains lemma from device | Expiry; revocation; wallet encryption at rest; optional nonce/challenge binding by verifiers | If an attacker controls the device/runtime, offline verification cannot prevent misuse without additional mechanisms |
| Revocation bypass | Verifier uses stale revocation filters | Event-driven and/or periodic filter sync; short validity windows for higher-risk lemmas | Window of exposure depends on sync policy and offline duration |
| Bloom filter false positives (optional) | Bloom filters used for compression | Tune \(m,k\); re-issuance; optional higher-assurance handling path | Not applicable if using an exact hashed revocation set; configurable if Bloom compression is used |

### 12.3 Privacy properties
The system does not attempt to hide that a user accessed a relying party. Instead it targets:
- **Issuer-free presentation**: the issuer does not need to observe verification events because verification can occur locally.
- **Pairwise identifiers**: proofs do not carry stable cross-site identifiers by default.

Additionally, lemmas are intended to carry small claims to minimize disclosure. A relying party can rely on “isHuman=true” without receiving identity documents.

## 13. Utility and applications
The verification layer supports any claim that can be represented as a signed statement with expiry and revocation semantics, including:
- login/IAM (“role=admin for rp_id=X”),
- human verification (“isHuman=true”),
- membership/entitlement proofs,
- anti-bot and anti-sybil constraints (when rooted in human verification).

Claims that require real-time state (e.g., balances, live risk scores) may still require online policy evaluation, but lemma verification can still reduce the frequency and scope of online lookups.

### 13.1 Proof-of-Human as an Optional Claim (Not Required)
Human verification (“PoH”) is a stronger issuance prerequisite intended to anchor lemmas to a verified human uniqueness process. At a high level:
1) the user completes a human verification step with the issuer,
2) the issuer derives (or enables derivation of) a human-rooted master secret,
3) pairwise subjects are derived per relying party from that secret,
4) the issuer can issue narrow claims such as “isHuman=true” without requiring repeated disclosure of identity documents to each relying party.

This rooting supports anti-sybil and “real person” assurance while preserving issuer-free presentation and minimal disclosure at verification time.

## 14. Federated Permission System (v2 Architecture)

The v2 architecture introduces a **federated issuer model** where multiple parties can issue lemmas, while maintaining edge-verifiable properties.

### 14.1 Federated Model Overview

**Key insight:** The **passkey is the root of trust**, not Proof-of-Human. Users can create wallets and receive lemmas without any PoH verification. The federated model separates **identity verification** from **permissions and roles**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FEDERATED ISSUER MODEL                              │
└─────────────────────────────────────────────────────────────────────────────┘

                    LEMMA.ID (Root of Trust)
                    ┌─────────────────────┐
                    │  Issues:            │
                    │  • isHuman=true     │  ← Proof of Human
                    │  • passkey verified │  ← Device binding
                    │                     │
                    │  Maintains:         │
                    │  • Issuer registry  │  ← Site public keys
                    │  • Revocation set   │  ← Network-wide bans
                    └──────────┬──────────┘
                               │
                    User stores in wallet
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
    ┌───────────┐        ┌───────────┐        ┌───────────┐
    │  SITE A   │        │  SITE B   │        │  SITE C   │
    │           │        │           │        │           │
    │ Issues:   │        │ Issues:   │        │ Issues:   │
    │ • role    │        │ • member  │        │ • access  │
    │ • admin   │        │ • premium │        │ • api_key │
    │           │        │           │        │           │
    │ Verifies: │        │ Verifies: │        │ Verifies: │
    │ Any lemma │        │ Any lemma │        │ Any lemma │
    │ locally   │        │ locally   │        │ locally   │
    └───────────┘        └───────────┘        └───────────┘
```

### 14.2 Role Separation

| Lemma.id Issues | Sites Issue |
|-----------------|-------------|
| **Human verification** (expensive, one-time) | **Roles/permissions** (free, frequent changes) |
| **Device binding** (passkey proof) | **Membership tiers** (site-specific) |
| **KYC level** (regulatory compliance) | **Access tokens** (resource-specific) |
| Universal across all sites | Only valid for issuing site |

### 14.3 Issuer Registry

The issuer registry is a public directory of participating issuers:

```
IssuerRegistry:
  - did: "did:web:lemma.id"
    publicKey: "ed25519:abc123..."
    name: "Lemma"
    verified: true
    type: "poh"  // Proof of Human issuer
    
  - did: "did:web:site-a.com"
    publicKey: "ed25519:def456..."
    name: "Site A"
    verified: true
    type: "site"
```

Any verifier can:
1. Fetch issuer public keys from the registry
2. Cache them locally
3. Verify lemmas from any registered issuer without contacting that issuer

### 14.4 Wallet-Based Authentication

The wallet introduces **passkey unlock = authentication**:

| Traditional Flow (Email) | Wallet Flow (Passkey) |
|--------------------------|----------------------|
| 1. Enter email | 1. Click "Sign In" |
| 2. Check inbox | 2. Face ID / Touch ID |
| 3. Click verify link | **Done** |
| 4. Get session token | |
| **Time: 30-60 seconds** | **Time: 1-2 seconds** |

The passkey provides stronger authentication than email:
- **Phishing-resistant**: cryptographically bound to the specific origin
- **Hardware-backed**: stored in device secure enclave
- **Biometric-verified**: requires user physical presence
- **Replay-proof**: each authentication produces a unique signature

### 14.5 Local Wallet Storage

The wallet stores credentials from multiple issuers:

```javascript
Wallet:
  passkey:
    credentialId: "base64..."
    publicKey: "base64..."  // For local unlock verification
    
  session:
    isUnlocked: true
    unlockedAt: 1734820000000
    expiresAt: 1734848800000  // 8 hours
    
  lemmas:
    - id: "lemma_abc"
      issuer: "did:web:lemma.id"
      claims: { isHuman: true }
      
    - id: "lemma_def"
      issuer: "did:web:site-a.com"
      claims: { role: "admin" }
      
  issuers:
    "did:web:lemma.id": { publicKey: "...", verified: true }
    "did:web:site-a.com": { publicKey: "...", verified: true }
```

### 14.6 Site Issuer Flow

Any site can issue lemmas:

```javascript
// 1. Site generates keypair (browser-side)
const issuer = new LemmaSiteIssuer({ domain: 'mysite.com' });
await issuer.init();

// 2. Site registers with Lemma (once)
await issuer.registerWithLemma();

// 3. Site issues lemmas to users
const lemma = await issuer.issueLemma(userId, {
    role: 'premium',
    permissions: ['api:full']
});

// 4. User stores in wallet
await wallet.storeLemma(lemma, issuer.getPublicKeyInfo());
```

### 14.7 Cross-Site Verification

Any site can verify any issuer's lemmas:

```javascript
// Site B verifies a lemma from Site A
const verifier = new LemmaVerifier();
const result = await verifier.verify(lemma);

// result.valid = true
// result.issuer = "Site A"
// result.claims = { role: "premium" }
```

### 14.8 API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/issuers/register` | POST | Site registers as issuer |
| `/api/issuers/{did}` | GET | Get issuer's public key |
| `/api/issuers` | GET | List all registered issuers |
| `/api/issuers/lemma` | GET | Get Lemma's issuer info (trust bootstrap) |
| `/api/wallet/auth` | POST | Verify wallet auth proof |
| `/api/wallet/status` | GET | Check wallet auth status |

### 14.9 Security Properties

The federated model preserves all security properties:

| Property | How Preserved |
|----------|---------------|
| **Edge verification** | All lemmas verified locally, regardless of issuer |
| **Revocation** | Network-wide revocation still applies |
| **Pairwise identifiers** | Sites generate their own PPIDs |
| **Signature security** | Ed25519 for all issuers |
| **Wallet encryption** | Passkey-derived key encrypts local storage |

### 14.10 Benefits of Federation

| Before (Single Issuer) | After (Federated) |
|------------------------|-------------------|
| All credentials from Lemma.id | Credentials from many sources |
| Central bottleneck | Distributed issuance |
| Limited to PoH claims | Any claim type |
| Server-dependent session | Local wallet session |

## 15. Conclusion
We have proposed an edge-verifiable identity layer based on user-held, self-verifying proofs. Digital lemmas enable issuer-free verification at presentation time, enforce revocation via distributed revocation sets, and reduce cross-site correlation by default through pairwise subject identifiers.

The v2 federated architecture extends this foundation with:
- **Multiple issuers**: sites can issue their own lemmas
- **Wallet-based auth**: passkey unlock replaces email sessions
- **Issuer registry**: enables cross-site trust without coordination
- **Local-first design**: no server calls for unlock, storage, or presentation

The result is a practical path to faster verification, reduced centralized breach concentration, minimal-disclosure proofs, and a scalable federated permission system.

We invite collaboration and external review, including pilot deployments and independent evaluation of the revocation distribution model and privacy properties.

## References
[1] S. Josefsson, I. Liusvaara, “Edwards-Curve Digital Signature Algorithm (EdDSA),” RFC 8032, 2017.  
[2] D. J. Bernstein et al., “High-speed high-security signatures,” Journal of Cryptographic Engineering, 2012.  
[3] B. H. Bloom, “Space/time trade-offs in hash coding with allowable errors,” Communications of the ACM, 1970.  
[4] M. Sporny et al., “Verifiable Credentials Data Model 1.1,” W3C Recommendation, 2022.  
[5] M. Sporny et al., “Decentralized Identifiers (DIDs) v1.0,” W3C Recommendation, 2022.  
[6] M. Jones et al., “JSON Web Token (JWT),” RFC 7519, 2015.  
[7] C. A. Wood, R. Barnes, “Oblivious Pseudorandom Functions (OPRFs),” RFC 9497, 2023.  
[8] W3C WebAuthn Working Group, “Web Authentication: An API for accessing Public Key Credentials,” W3C Recommendation, 2021.  

