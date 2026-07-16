# Trust Calculus: A Formal System for Composable, Locally-Verifiable, and Revocable Trust Between Communicating Nodes

**Jed McCaleb**
Lemma Labs, Inc.

**February 2026**

---

## Abstract

We introduce *Trust Calculus*, a formal system for constructing, composing, and revoking cryptographic trust assertions between arbitrary communicating nodes. A Trust Calculus *lemma* is an Ed25519-signed claim that nodes can verify locally without contacting the issuing authority. In the formal model, lemmas compose: if node A trusts B and B trusts C, the chain A→B→C forms a locally-verifiable proof, with effective authority equal to the intersection of all scopes along the path. The current implementation includes revocation distribution primitives (hashed revocation sets and Bloom-filter payloads) that support local revocation checks. Pairwise Pseudonymous Identifiers (PPIDs) derived via HMAC-SHA256 ensure that the same node participating in multiple trust graphs cannot be correlated across contexts.

We present formal arguments for three safety properties: (1) *monotonic attenuation*, composition can only narrow authority, never widen it; (2) *revocation completeness*, revoking any link invalidates all compositions containing it in the model; and (3) *privacy under composition*, no coalition of verifiers can link a node's participation across independent trust graphs under standard assumptions. We also report implementation benchmarks and comparative observations against OAuth 2.0 introspection, mTLS certificate verification, and blockchain-based credential systems; these are measured results under stated conditions, not universal guarantees.

Trust Calculus generalizes beyond human identity to any node that holds a keypair: servers, AI agents, IoT devices, and software processes. We present the formal system, its properties, a reference implementation anchored to WebAuthn passkeys, and applications to agent delegation, service mesh authentication, content provenance, and supply chain attestation.

---

## 1. Introduction

### 1.1 The Trust Verification Bottleneck

Every distributed system must answer a fundamental question at every interaction: *should this node trust what that node claims?* The dominant approaches to this question, OAuth 2.0, SAML, mTLS, and API key validation, share a structural limitation: they require the verifying node to contact a remote authority at verification time, or to rely on opaque tokens whose validity cannot be independently assessed.

This creates three problems:

1. **Latency**: Token introspection adds 5–50ms of network round-trip to every trust decision.
2. **Availability coupling**: If the authority is unreachable, trust decisions cannot be made.
3. **Privacy leakage**: The authority learns who is verifying what, when, and where.

These problems compound as systems become more distributed. A service mesh with 50 microservices making 10,000 requests per second generates 10,000 authority callbacks per second. An AI agent delegating to sub-agents across providers has no standardized mechanism to carry proof of its authorization. An IoT mesh in a disconnected environment cannot validate device identities at all.

### 1.2 The Composition Gap

Existing trust systems are point-to-point. An OAuth token asserts "identity provider P vouches for user U to service S." But it cannot express "P vouches for U, who delegated to agent A, who is now acting on U's behalf at service S, with a budget constraint of $500." Such compositional trust requires chaining assertions, and current systems have no formal mechanism for:

- **Delegation with attenuation**: Granting a subset of one's authority to another node.
- **Transitive verification**: Verifying a chain of delegations without contacting each delegator.
- **Scope intersection**: Computing the effective authority of a composed chain.
- **Cascade revocation**: Revoking one link and having all downstream chains automatically invalidated.

### 1.3 Contribution

We present Trust Calculus, a formal system that treats trust assertions as composable algebraic objects. The system provides:

- **Lemmas**: Atomic, self-verifying trust assertions (Ed25519-signed, W3C Verifiable Credential format).
- **Composition**: A binary operation on lemmas that produces new lemmas, with formally defined scope intersection.
- **Attenuation**: A monotonicity guarantee that composition can only restrict authority.
- **Revocation**: A privacy-preserving mechanism (cascaded Bloom filters) that invalidates lemmas and all their compositions.
- **Pseudonymity**: Pairwise identifiers (HMAC-SHA256-derived PPIDs) that prevent cross-context correlation.

The formal verification procedure evaluates locally once required trust material is present. In deployment, a verifying node uses issuer trust material and periodically-synced revocation data (hashed sets and/or Bloom payloads), avoiding issuer callback round-trips at decision time.

---

## 2. Preliminaries

### 2.1 Notation

| Symbol | Meaning |
|--------|---------|
| $\mathcal{N}$ | The set of all nodes (humans, agents, devices, services) |
| $n_i \in \mathcal{N}$ | A specific node with keypair $(sk_i, pk_i)$ |
| $\text{did}(n_i)$ | Decentralized identifier: `did:lemma:{hex(pk_i)}` |
| $\ell$ | A lemma (atomic trust assertion) |
| $\mathcal{L}$ | The set of all valid lemmas |
| $\sigma_k(m)$ | Ed25519 signature of message $m$ under secret key $k$ |
| $\mathcal{S}$ | A scope (set of authorized actions) |
| $\mathcal{B}$ | A cascaded Bloom filter for revocation |
| $\text{PPID}(n, d)$ | Pairwise pseudonymous identifier for node $n$ in domain $d$ |

### 2.2 Cryptographic Primitives

**Ed25519 Signatures.** We use Ed25519 over Curve25519 (RFC 8032). Key sizes: secret key 32 bytes, public key 32 bytes, signature 64 bytes. Verification requires only the public key and is performed in constant time.

**HMAC-SHA256.** Used for PPID derivation. Given a 256-bit key $k$ and message $m$, $\text{HMAC-SHA256}(k, m)$ produces a 256-bit pseudorandom output. Security reduces to the PRF assumption on SHA-256.

**SHA-256.** Used for deterministic message hashing prior to signing, and for Bloom filter element hashing.

### 2.3 Deterministic Message Serialization

All signed messages are constructed by deterministic serialization: fields are ordered lexicographically by key, serialized to UTF-8 JSON, then hashed with SHA-256 to produce a 32-byte digest. This digest is the message signed by Ed25519. The deterministic ordering ensures that any node reconstructing the message from the same credential fields produces an identical digest.

```
serialize(credential) → sorted_json(credential.fields) → SHA-256 → 32 bytes
```

---

## 3. Formal Definitions

This section defines Trust Calculus semantics. Production conformance is implemented incrementally across verifier and policy paths.

### 3.1 Node

A **node** is any entity capable of holding an Ed25519 keypair and participating in the Trust Calculus. Formally:

$$n = (sk, pk, \mathcal{C})$$

where $sk$ is the 256-bit secret key, $pk$ is the corresponding public key, and $\mathcal{C} \subseteq \mathcal{L}$ is the node's set of held credentials (lemmas issued *to* this node).

Nodes are identified by their Decentralized Identifier (DID):

$$\text{did}(n) = \texttt{did:lemma:} \| \text{hex}(pk)$$

The node abstraction is intentionally general. A node may be:
- A human, authenticated via WebAuthn passkey (hardware-attested)
- An AI agent, holding a software-generated keypair
- A server or microservice, with keys managed by an HSM
- An IoT device, with keys burned into a secure element
- A software process, with ephemeral keys valid for a single session

### 3.2 Lemma

A **lemma** is the atomic unit of the Trust Calculus: a signed assertion from one node about another. Formally:

$$\ell = (id, \iota, \varsigma, t_i, t_x, \mathcal{S}, \mathcal{K}, \pi)$$

where:
- $id \in \{0,1\}^*$ is a unique identifier (UUID)
- $\iota \in \mathcal{N}$ is the **issuer** (the node making the assertion)
- $\varsigma \in \mathcal{N}$ is the **subject** (the node being asserted about)
- $t_i \in \mathbb{Z}^+$ is the issuance timestamp (UNIX seconds)
- $t_x \in \mathbb{Z}^+ \cup \{\bot\}$ is the expiration timestamp (or $\bot$ for no expiry)
- $\mathcal{S} \subseteq \mathcal{A}$ is the **scope**: a set of authorized actions from the action universe $\mathcal{A}$
- $\mathcal{K} \subseteq \{(k, v) : k, v \in \{0,1\}^*\}$ is a set of key-value **claims** (e.g., `isHuman: true`)
- $\pi = \sigma_{sk_\iota}(\text{SHA-256}(\text{serialize}(\ell \setminus \pi)))$ is the Ed25519 proof (signature over all fields except the proof itself)

A lemma is **well-formed** if:
1. $\pi$ is a valid Ed25519 signature under $pk_\iota$ over the deterministic serialization of all other fields.
2. $t_i \leq t_{\text{now}}$ (issued in the past or present).
3. $t_x = \bot$ or $t_x > t_{\text{now}}$ (not yet expired).
4. $id \notin \mathcal{B}$ (not present in the revocation Bloom filter).

### 3.3 Scope

A **scope** is a finite set of authorized actions, where each action is a pair (resource, operation):

$$\mathcal{S} = \{(r_1, o_1), (r_2, o_2), \ldots, (r_n, o_n)\}$$

We define a partial order $\subseteq$ on scopes by set inclusion. The **universal scope** $\mathcal{S}_\top = \mathcal{A}$ (all actions) is the top element. The **empty scope** $\mathcal{S}_\bot = \emptyset$ is the bottom element.

Scopes support a **wildcard** notation: $(r, *)$ matches all operations on resource $r$; $(*, *)$ matches all actions. Formally, we define a **grants** relation:

$$\mathcal{S} \vdash (r, o) \iff \exists (r', o') \in \mathcal{S} : (r' = r \lor r' = *) \land (o' = o \lor o' = *)$$

Scope matching also supports hierarchical resources via prefix wildcards: a scope entry `(r/*, o)` grants action $o$ on any resource with prefix $r/$.

### 3.4 Trust Chain

A **trust chain** is an ordered sequence of lemmas forming a delegation path:

$$\mathcal{T} = [\ell_0, \ell_1, \ldots, \ell_k]$$

A trust chain is **valid** if:
1. **Continuity**: For each consecutive pair $(\ell_i, \ell_{i+1})$, the subject of $\ell_i$ equals the issuer of $\ell_{i+1}$: $\varsigma_i = \iota_{i+1}$.
2. **Well-formedness**: Every $\ell_i$ in the chain is well-formed.
3. **Temporal consistency**: The issuance of each link falls within the validity window of the preceding link: $t_{i,i+1} \leq t_{x,i}$ for all $i$.

The **root** of a trust chain is $\iota_0$ (the issuer of the first lemma). The **terminal subject** is $\varsigma_k$ (the subject of the last lemma). The **effective scope** is the intersection of all scopes along the chain:

$$\mathcal{S}_{\text{eff}}(\mathcal{T}) = \bigcap_{i=0}^{k} \mathcal{S}_i$$

The **depth** of a chain is $|\mathcal{T}| = k + 1$.

---

## 4. The Trust Calculus

### 4.1 Operations

We define four operations on lemmas and trust chains:

#### 4.1.1 Issue ($\text{issue}$)

A node $n_\iota$ creates a new lemma asserting a claim about node $n_\varsigma$ with scope $\mathcal{S}$:

$$\text{issue}(n_\iota, n_\varsigma, \mathcal{S}, \mathcal{K}) \rightarrow \ell$$

The issuer signs the lemma with its secret key, binding the claims and scope cryptographically. The resulting lemma is an unforgeable assertion: only the holder of $sk_\iota$ could have produced $\pi$.

**Precondition**: The issuer must hold a valid keypair. If the issuer's own authority derives from a chain, the issued scope must be a subset of the issuer's effective scope (see §4.2, Monotonic Attenuation).

#### 4.1.2 Compose ($\circ$)

Given two lemmas $\ell_a$ and $\ell_b$ where $\varsigma_a = \iota_b$ (the subject of $a$ is the issuer of $b$), composition produces a trust chain:

$$\ell_a \circ \ell_b = [\ell_a, \ell_b]$$

More generally, composition extends chains:

$$\mathcal{T} \circ \ell = [\ell_0, \ldots, \ell_k, \ell]$$

provided $\varsigma_k = \iota_\ell$ (continuity). Composition is **associative**:

$$(\ell_a \circ \ell_b) \circ \ell_c = \ell_a \circ (\ell_b \circ \ell_c) = [\ell_a, \ell_b, \ell_c]$$

The effective scope of the composed chain is:

$$\mathcal{S}_{\text{eff}}(\ell_a \circ \ell_b) = \mathcal{S}_a \cap \mathcal{S}_b$$

This is the core algebraic property: **composition is scope intersection**. It follows directly that composition is commutative with respect to scope (the order of intersection does not matter), though the chain ordering itself is fixed by the continuity requirement.

#### 4.1.3 Verify ($\text{verify}$)

Verification checks a lemma or chain and returns a trust judgment:

$$\text{verify}(\mathcal{T}, \mathcal{R}, \mathcal{B}) \rightarrow \{(\top, \mathcal{S}_{\text{eff}}), \bot\}$$

where $\mathcal{R}$ is the set of trusted root issuers and $\mathcal{B}$ is the current Bloom filter. The procedure is:

```
VERIFY(T, R, B):
    if T[0].issuer ∉ R: return ⊥              // Untrusted root
    S_eff ← T[0].scope
    for i ← 0 to |T|-1:
        if not Ed25519.verify(T[i].issuer.pk,
               SHA256(serialize(T[i])),
               T[i].proof):
            return ⊥                           // Invalid signature
        if T[i].id ∈ B: return ⊥              // Revoked
        if T[i].expired: return ⊥             // Expired
        if i > 0 and T[i].issuer ≠ T[i-1].subject:
            return ⊥                           // Broken chain
        S_eff ← S_eff ∩ T[i].scope
    return (⊤, S_eff)
```

**Complexity**: $O(k)$ Ed25519 verifications + $O(k)$ Bloom filter lookups, where $k$ is chain depth. Each Ed25519 verification is $< 500\mu s$ (WebCrypto); each Bloom filter lookup is $< 5\mu s$. For a chain of depth 10: $< 5ms$ total on the local verification hot path once required keys/revocation data are already synced.

#### 4.1.4 Revoke ($\text{revoke}$)

An issuer revokes a lemma it previously issued:

$$\text{revoke}(n_\iota, \ell) \rightarrow \mathcal{B}' = \mathcal{B} \cup \{id_\ell\}$$

The credential ID is added to the Bloom filter. Revocation propagates: any chain $\mathcal{T}$ containing $\ell$ will fail verification at the Bloom filter check step.

Revocation operates at three granularities:
- **Credential-level**: A single lemma ID is revoked.
- **Subject-level**: All lemmas issued to a specific PPID are revoked (via PPID insertion into the Bloom filter).
- **Wallet-level**: All lemmas associated with a wallet are revoked (nuclear option).

### 4.2 Properties

We now state and argue the three fundamental safety properties of the Trust Calculus.

#### Property 1 (Model): Monotonic Attenuation

**Statement.** *For any valid trust chain $\mathcal{T} = [\ell_0, \ldots, \ell_k]$ and any extension $\mathcal{T}' = \mathcal{T} \circ \ell_{k+1}$:*

$$\mathcal{S}_{\text{eff}}(\mathcal{T}') \subseteq \mathcal{S}_{\text{eff}}(\mathcal{T})$$

*Composition can only reduce or maintain the effective scope, never increase it.*

**Argument.** By definition:

$$\mathcal{S}_{\text{eff}}(\mathcal{T}') = \mathcal{S}_{\text{eff}}(\mathcal{T}) \cap \mathcal{S}_{k+1}$$

Since for any sets $A$ and $B$, $A \cap B \subseteq A$, the effective scope of the extended chain is a subset of the original. $\square$

**Consequence.** No node in a delegation chain can grant more authority than it was given. An AI agent delegated read-only access cannot delegate write access to a sub-agent. This property holds structurally, it is enforced by the algebra, not by runtime checks.

#### Property 2 (Model): Revocation Completeness

**Statement.** *If lemma $\ell_j$ is revoked (i.e., $id_j \in \mathcal{B}$), then for any trust chain $\mathcal{T}$ containing $\ell_j$:*

$$\text{verify}(\mathcal{T}, \mathcal{R}, \mathcal{B}) = \bot$$

*Revoking any link in a chain invalidates the entire chain.*

**Argument.** The verification procedure iterates over every lemma in the chain and checks $\ell_i.id \in \mathcal{B}$ for each. If any check returns true, verification returns $\bot$ immediately. Since $\ell_j \in \mathcal{T}$ and $id_j \in \mathcal{B}$, the check will return true at step $j$. $\square$

**Consequence.** When a human revokes their delegation to an AI agent, every chain rooted in that delegation, including sub-delegations the agent made to other agents, becomes invalid. Revocation cascades without requiring knowledge of the downstream chains.

**Note on Bloom filter false positives.** The cascaded Bloom filter has a false positive rate of $p \leq 0.001$ at the finest level. A false positive causes a valid credential to appear revoked. This is a conservative failure mode: false positives deny access (safe), while false negatives (missed revocations) are structurally impossible in a Bloom filter with correct insertion. In practice, the $0.1\%$ false positive rate means fewer than 1 in 1,000 valid credentials may require a server-side recheck.

#### Property 3 (Model): Unlinkability Under Composition

**Statement.** *Given a node $n$ participating in two independent trust contexts with domains $d_1$ and $d_2$, no probabilistic polynomial-time adversary $\mathcal{A}$ observing both contexts can determine that the same node is present in both, except with negligible advantage over random guessing.*

Formally, let $\text{PPID}(n, d) = \text{HMAC-SHA256}(s_n, d)$ where $s_n$ is the node's 256-bit wallet secret (a high-entropy random value generated at wallet creation). The adversary's advantage is:

$$\text{Adv}_{\mathcal{A}} = |Pr[\mathcal{A}(\text{PPID}(n, d_1), \text{PPID}(n, d_2)) = 1] - Pr[\mathcal{A}(r_1, r_2) = 1]| \leq \text{negl}(\lambda)$$

where $r_1, r_2$ are uniformly random 256-bit strings and $\lambda$ is the security parameter.

**Argument.** This reduces to the PRF security of HMAC-SHA256. If an adversary could distinguish $\text{PPID}(n, d_1)$ from a random string (or link two PPIDs to the same node), it could distinguish HMAC-SHA256 from a random function, contradicting the PRF assumption. Under the standard model assumption that SHA-256 is a PRF when keyed, the PPIDs are computationally indistinguishable from random. $\square$

**Consequence.** A node (human, agent, or device) can participate in trust chains at thousands of independent sites. No coalition of sites can correlate the node's activity across domains. This is a structural privacy guarantee, not a policy, but a mathematical property of the identifier derivation.

---

## 5. Revocation Model

### 5.1 Cascaded Bloom Filters

In the formal model, revocation status is encoded in a cascaded Bloom filter with three levels, balancing capacity, accuracy, and distribution size:

| Level | Capacity | False Positive Rate | Bit Array Size |
|-------|----------|-------------------|----------------|
| 0 | 1,000 | 0.1% ($10^{-3}$) | ~14.4 Kbit |
| 1 | 10,000 | 0.01% ($10^{-4}$) | ~192 Kbit |
| 2 | 100,000 | 0.001% ($10^{-5}$) | ~2.4 Mbit |

Each level uses $k$ independent hash functions derived from SHA-256 double hashing:

$$h_1(x) = \text{uint32\_le}(\text{SHA-256}(x)[0..4])$$
$$h_2(x) = \text{uint32\_le}(\text{SHA-256}(x)[4..8])$$
$$h_i(x) = (h_1(x) + i \cdot h_2(x)) \mod m$$

where $m$ is the bit array size for the level and $i \in \{0, \ldots, k-1\}$.

Verification checks the appropriate level based on the current total revocation count. The number of hash functions $k$ is computed as:

$$k = \lceil (m / n) \cdot \ln 2 \rceil$$

where $n$ is the capacity.

### 5.2 Revocation Propagation

Revocation events propagate through three mechanisms in the reference design:

1. **Immediate (same process)**: Direct Bloom filter insertion, $< 1\mu s$.
2. **Event-driven (multi-node server)**: Redis pub/sub broadcast, $< 10ms$ typical.
3. **Periodic (client-side)**: revocation data re-download via `GET /api/revocation/bloom-filter`, configurable interval.

In deployment, propagation delay is bounded by the client sync interval and transport characteristics of the configured distribution path.

---

## 6. Pairwise Pseudonymous Identifiers

### 6.1 Construction

A node $n$ with wallet secret $s_n$ derives a unique, unlinkable identifier for each domain $d$:

$$\text{PPID}(n, d) = \texttt{did:lemma:ppid\_} \| \text{hex}(\text{HMAC-SHA256}(s_n, d))$$

where $s_n$ is the node's 256-bit wallet secret (generated randomly at wallet creation, stored encrypted in IndexedDB) and $d = \text{canonicalize}(\text{hostname})$ extracts normalized host input from the domain context. The derivation is performed client-side using the WebCrypto API; the wallet secret never leaves the client.

### 6.2 Properties

1. **Determinism**: The same node at the same domain always produces the same PPID, enabling persistent identity within a context.
2. **Unlinkability**: PPIDs at different domains are computationally indistinguishable from random (see Property 3, §4.2).
3. **Unforgeability**: Without the wallet secret $s_n$, no entity can derive or predict the PPID for any domain.
4. **Unidirectionality**: Given a PPID, recovering $s_n$ requires inverting HMAC-SHA256, which is computationally infeasible.
5. **Independence from issuance authority**: The PPID derivation is performed entirely client-side via the WebCrypto API. The issuance authority never observes $s_n$ or any PPID.

### 6.3 Implications for Trust Chains

When a node presents a trust chain to a verifier in domain $d$, the chain's terminal subject is identified by $\text{PPID}(n, d)$. The verifier sees a consistent pseudonymous identity within its domain but cannot correlate it to the same node's identity at any other domain. This holds even if the same trust chain (e.g., a KYC-backed identity lemma) is presented at both domains, the credential is the same, but the presented identifier differs.

---

## 7. Performance Analysis

### 7.1 Verification Cost Model

Let $k$ be the depth of a trust chain. The verification cost is:

$$C_{\text{verify}}(k) = k \cdot C_{\text{Ed25519}} + k \cdot C_{\text{bloom}} + k \cdot C_{\text{expiry}}$$

where:
- $C_{\text{Ed25519}}$ varies by runtime mode and hardware (WebCrypto, WASM, or JS implementation path)
- $C_{\text{bloom}} \leq 5\mu s$ (SHA-256 double hash + bit lookups)
- $C_{\text{expiry}} < 1\mu s$ (integer comparison)

Example measurements for one WebCrypto configuration:

| Chain Depth | Verification Time | Network Calls |
|-------------|-------------------|---------------|
| 1 (single lemma) | $\leq 506\mu s$ | 0 |
| 3 (human → agent → sub-agent) | $\leq 1.5ms$ | 0 |
| 5 (deep delegation) | $\leq 2.5ms$ | 0 |
| 10 (maximum recommended) | $\leq 5ms$ | 0 |

Example cached measurements:

| Chain Depth | Cached Verification Time |
|-------------|--------------------------|
| 1 | $\leq 250\mu s$ |
| 3 | $\leq 750\mu s$ |
| 10 | $\leq 2.5ms$ |

### 7.2 Comparison With Existing Systems

| System | Verification Latency | Network Required | Composable | Revocable | Private |
|--------|---------------------|-----------------|------------|-----------|---------|
| **Trust Calculus** | **250 $\mu$s – 5 ms** | **No** | **Yes** | **Yes** | **Yes** |
| OAuth 2.0 introspection | 5–50 ms | Yes | No | Yes* | No |
| JWT (local) | 50–500 $\mu$s | No | No | No† | No |
| mTLS (handshake) | 1–10 ms | Partial‡ | No | Yes§ | Partial |
| SAML assertion | 1–5 ms | Yes | No | Limited | No |
| Blockchain VC | 100 ms – 5 s | Yes | Partial | Partial | Partial |
| UCAN | 50–500 $\mu$s | No | Yes | **No** | No |

\* OAuth revocation requires contacting the authorization server.
† JWTs have no native revocation mechanism; revocation requires server-side blacklists.
‡ mTLS requires OCSP/CRL checks for revocation, which are network calls.
§ Certificate revocation via OCSP/CRL has well-documented reliability problems.

These comparisons are directional and depend on benchmark setup, chain depth, cache behavior, and deployment constraints. They should be interpreted as measured scenarios, not universal rankings.

### 7.3 Bandwidth Cost

A single lemma serialized as JSON is approximately 500–800 bytes. A trust chain of depth $k$ is $\leq 800k$ bytes. The Bloom filter for revocation is:

- Level 0 (1K items): ~1.8 KB
- Level 1 (10K items): ~24 KB
- Level 2 (100K items): ~300 KB

The Bloom filter is downloaded periodically (not per-verification), so its cost is amortized across all verifications between syncs. For a 60-second sync interval and 1,000 verifications per second, the per-verification bandwidth overhead of the Bloom filter is $\leq 0.3$ bytes.

---

## 8. Trust Calculus for Agent Systems

### 8.1 The Agent Trust Problem

Autonomous AI agents present a new category of trust challenge. An agent acts on behalf of a human, often delegating to sub-agents, calling external APIs, and making decisions with financial or operational consequences. The trust questions are:

1. **Authorization**: Was this agent authorized by a real human?
2. **Scope**: What is this agent permitted to do?
3. **Delegation**: Did this agent delegate to a sub-agent, and with what constraints?
4. **Provenance**: Can we trace every action back to a human decision?
5. **Revocation**: If the human revokes authorization, does all downstream activity stop?

Few deployed systems answer all five questions in one mechanism. OAuth tokens are typically not composable, API keys do not provide native scope attenuation, and blockchain credential flows often introduce latency tradeoffs for real-time agent interaction.

### 8.2 Agent Delegation Chains

Trust Calculus addresses all five questions through delegation chains:

```
ℓ₀: KYC Provider → Human H
    claims: {isHuman: true, verificationLevel: "high"}
    scope: {*, *}  (universal, root of authority)

ℓ₁: Human H → Agent A
    claims: {role: "research_assistant", model: "claude-opus-4"}
    scope: {(web:read), (api:query), (budget:500)}

ℓ₂: Agent A → Sub-Agent A₁
    claims: {role: "data_fetcher", delegatedBy: "agent_a"}
    scope: {(web:read), (api:query)}
    // Note: budget not delegated, attenuation in action

ℓ₃: Sub-Agent A₁ → Service S
    claims: {action: "query", parameters: {...}}
    scope: {(api:query)}
```

Service S verifies the full chain $[\ell_0, \ell_1, \ell_2, \ell_3]$ in $\leq 2ms$:
- $\ell_0$: A trusted KYC provider vouches for a human. ✓
- $\ell_1$: That human delegated to Agent A with specific constraints. ✓
- $\ell_2$: Agent A sub-delegated to A₁ with *narrower* scope. ✓
- $\ell_3$: A₁ is requesting an API query, which is within its effective scope. ✓

Effective scope: $\{*, *\} \cap \{(\text{web:read}), (\text{api:query}), (\text{budget:500})\} \cap \{(\text{web:read}), (\text{api:query})\} \cap \{(\text{api:query})\} = \{(\text{api:query})\}$

If Human H later revokes $\ell_1$, **all** downstream chains, including ones H has no knowledge of, become invalid at the next Bloom filter sync.

### 8.3 Cross-Platform Agent Mobility

An agent holding a valid trust chain can present it to any service that trusts the chain's root issuer. The chain is self-contained: it carries its own proof of authorization. This enables agents to move across platforms without re-authentication:

```
Agent A holds chain [ℓ₀, ℓ₁] from Platform P₁.
Agent A calls API on Platform P₂.
P₂ verifies the chain locally:
  - Is ℓ₀.issuer in P₂'s trusted issuer set? Yes.
  - Are all signatures valid? Yes.
  - Is the effective scope sufficient for this API call? Yes.
P₂ serves the request. No callback to P₁. No account on P₂.
```

The agent's identity at P₂ is a PPID: $\text{PPID}(A, \text{P₂.domain})$. P₂ cannot correlate this to A's identity at P₁.

---

## 9. Generalized Applications

### 9.1 Service Mesh Authentication

In a microservice architecture, Trust Calculus replaces mTLS and sidecar-based identity with proof-carrying requests:

```
HTTP Header: Authorization: Lemma <base64(chain)>
```

Each service verifies the chain locally. The chain root is the organization's HSM-backed issuer. Delegation lemmas authorize specific services for specific operations. Revocation of a compromised service's lemma instantly invalidates all its inter-service authority.

Advantages over mTLS:
- No certificate authority infrastructure to manage
- Delegation with attenuation (service A can grant service B a *subset* of its authority)
- Revocation in seconds (vs. CRL/OCSP propagation delays)
- No per-connection handshake cost (the chain is verified once per request, not per TCP connection)

### 9.2 IoT Device Mesh

IoT devices in constrained or disconnected environments benefit from local verification:

```
ℓ₀: Manufacturer M → Device D
    claims: {model: "sensor_v2", firmware: "1.4.2", attestation: "tpm_ek_hash"}

ℓ₁: Owner O → Device D
    claims: {zone: "warehouse_3", permissions: "temperature_reporting"}

ℓ₂: Device D → Gateway G
    claims: {reading: 23.5, timestamp: 1707123456}
```

Gateway G verifies the full chain offline. Even in an air-gapped environment, if the Bloom filter was synced before disconnection, revocation checks remain valid for the sync window.

### 9.3 Content Provenance

Trust Calculus provides a lightweight alternative to C2PA and blockchain-based provenance:

```
ℓ₀: KYC Provider → Human Creator C
    claims: {isHuman: true}

ℓ₁: Creator C → Content X
    claims: {contentHash: SHA-256(X), type: "photograph", tool: "camera"}

ℓ₂: Editor Agent E → Content X'
    claims: {contentHash: SHA-256(X'), parentHash: SHA-256(X),
             modifications: ["crop", "resize"], generativeAI: false}
```

Any viewer can verify the provenance chain locally: this content was created by a verified human, modified by an agent that disclosed its modifications, and the content hashes link each version cryptographically.

### 9.4 Supply Chain Attestation

Each handoff in a supply chain creates a new lemma, forming a verifiable provenance record:

```
ℓ₀: Manufacturer → Product batch B
    claims: {product: "widget_a", quantity: 1000, facility: "plant_7"}

ℓ₁: Auditor A → Manufacturer's facility
    claims: {standard: "ISO_9001", auditDate: 1707123456, result: "pass"}

ℓ₂: Logistics L → Shipment S
    claims: {batch: B.id, origin: "plant_7", destination: "warehouse_9",
             temperature_maintained: true}

ℓ₃: Retailer R → Product P
    claims: {batch: B.id, received: 1707200000, condition: "intact"}
```

The retailer or end consumer verifies the entire supply chain locally. Each link is independently verifiable. Revoking the auditor's lemma (e.g., if the audit is found to be fraudulent) invalidates the quality attestation.

### 9.5 Federated Organizational Trust

Organizations can establish mutual trust without a shared identity provider:

```
Org A's root issuer issues: "Employee E has role R"
Org A's root issuer issues: "We trust Org B's root issuer for domain D"

Org B receives a request from Employee E (via trust chain).
Org B verifies:
  1. E's identity lemma is signed by Org A's root (trusted).
  2. E's role includes access to domain D.
  3. No lemmas in the chain are revoked.
Org B serves the request. No federation protocol negotiation.
No shared directory. No SAML metadata exchange.
```

---

## 10. Reference Implementation

### 10.1 Architecture

The reference implementation, Lemma.id, consists of three components:

1. **Issuance Authority** (server-side): Ed25519 key management via AWS KMS (FIPS 140-2 Level 2/3), credential signing, and revocation Bloom filter maintenance. Implemented in Python (Flask) with Rust bindings (PyO3) for cryptographic operations.

2. **Verification Library** (any-side): Cryptographic verification of lemmas and chain structures. Implemented in three forms:
   - JavaScript (browser): WebCrypto API for Ed25519 and HMAC-SHA256, with optional compatibility paths
   - WebAssembly (browser, optional): Compiled from Rust via `wasm-bindgen`, $< 100\mu s$ verification
   - Rust (server-side): `lemma-crypto` crate via PyO3 bindings, no-std compatible

3. **Wallet** (client-side): Credential storage (IndexedDB, AES-256-GCM encrypted), PPID derivation, trust chain assembly, and passkey-based authentication (WebAuthn CTAP2).

### 10.2 Wire Format

Lemmas use the W3C Verifiable Credentials Data Model 1.1 format:

```json
{
  "@context": [
    "https://www.w3.org/2018/credentials/v1",
    "https://lemma.id/contexts/trust-calculus/v1"
  ],
  "id": "cred_550e8400-e29b-41d4-a716-446655440000",
  "issuer": "did:lemma:7a1b2c3d4e5f...64_hex_chars",
  "subject": "did:lemma:ppid_9c22ff5f21c0...64_hex_chars",
  "issuanceDate": 1707123456,
  "expirationDate": 1738659456,
  "credentialSubject": {
    "packageType": "delegation",
    "scope": ["api:query", "web:read"],
    "isHuman": false,
    "delegatedBy": "did:lemma:ppid_abc123..."
  },
  "proof": {
    "type": "Ed25519Signature2020",
    "created": 1707123456,
    "verificationMethod": "did:lemma:7a1b2c3d4e5f...64_hex_chars",
    "proofPurpose": "delegation",
    "signatureValue": "0a1b2c3d...128_hex_chars"
  }
}
```

Trust chains are transmitted as JSON arrays of credentials, ordered from root to terminal.

### 10.3 DID Resolution

Issuer public keys are extracted directly from the DID:

$$\text{did:lemma:} \underbrace{\texttt{7a1b2c3d...}}_{\text{64 hex chars}} \rightarrow \text{32-byte Ed25519 public key}$$

This is a *self-resolving* DID method: no external resolution infrastructure is required. Any node can extract the public key from the DID string and immediately verify signatures. For organizational issuers requiring key rotation, a registry mapping organizational identifiers to current DIDs is maintained, queryable via DNS TXT records or HTTPS well-known endpoints.

### 10.4 Human Anchoring via WebAuthn

The trust root for human nodes is a WebAuthn passkey stored in platform hardware (TPM, Secure Enclave, or FIDO2 security key). The passkey authenticates the human to the wallet, which then manages the cryptographic identity:

```
Hardware Authenticator (Secure Enclave / TPM)
  └─ WebAuthn Passkey (CTAP2, resident key, user verification required)
       └─ Wallet Session (HMAC-SHA256-signed token, 24-hour validity)
            └─ Wallet Secret (256-bit, encrypted at rest with AES-256-GCM)
                 └─ PPID Derivation (HMAC-SHA256, per-domain)
                 └─ Credential Storage (IndexedDB, AES-256-GCM encrypted)
                 └─ Delegation Signing (Ed25519, software key derived from wallet)
```

This architecture ensures that the root of every human trust chain is attested by hardware. The passkey cannot be phished (origin-bound), cannot be replayed (challenge-response), and cannot be extracted (hardware-bound).

---

## 11. Limitations and Future Work

### 11.1 Current Limitations

1. **Root trust is centralized.** The current implementation relies on Lemma.id as the primary issuance authority. While verification is decentralized, issuance of root credentials (KYC-backed human identity) requires trusting the issuance authority's key management and verification processes.

2. **Bloom filter staleness.** Client-side revocation checks depend on periodically-synced Bloom filters. The maximum window of vulnerability equals the sync interval (default 60 seconds).

3. **Chain depth limits.** While verification is $O(k)$, excessively deep chains (depth $> 10$) increase the probability that at least one link has been revoked or expired, and increase the bandwidth cost of transmitting the chain. We recommend a maximum practical depth of 10.

4. **Key compromise recovery.** If a node's secret key is compromised, all lemmas issued by that node must be revoked. For root issuers, this requires HSM-level key protection. For leaf nodes (agents, devices), this is mitigated by short-lived credentials and delegation scope limits.

5. **Conformance rollout in progress.** Endpoint-level policy parity and chain-native enforcement are being unified incrementally; implementation behavior can vary by route family during rollout phases.

### 11.2 Future Directions

1. **Formal verification.** Machine-checked proofs of the safety properties in a proof assistant (Coq or Lean 4) would strengthen the theoretical foundation.

2. **Aggregate signatures.** BLS aggregate signatures could compress a chain of $k$ signatures into a single signature, reducing chain verification to $O(1)$ and bandwidth to constant. This is compatible with the Trust Calculus algebra but requires a different curve (BLS12-381 vs. Curve25519).

3. **Decentralized issuance.** A federated issuance model where multiple organizations serve as root issuers, with a shared trusted issuer registry (possibly anchored in a transparency log), would reduce single-point-of-trust dependency.

4. **Threshold delegation.** Multi-party delegation where $m$-of-$n$ issuers must sign a lemma before it is valid. This enables committee-based authorization without requiring a single point of authority.

5. **Zero-knowledge scope proofs.** A node could prove that its effective scope includes a specific action *without revealing the full chain*. This would enable trust verification with minimal disclosure, using zk-SNARKs or Bulletproofs over the scope intersection.

6. **Hardware-accelerated verification.** Custom silicon or FPGA implementations of Ed25519 verification and Bloom filter checking could push single-verification latency below $1\mu s$, enabling Trust Calculus in hardware interrupt handlers, network packet filters, and real-time control systems.

7. **Privacy-preserving revocation queries via OPRF.** An Oblivious Pseudorandom Function protocol over Ristretto255 could provide real-time, interactive revocation checks for high-value transactions. The server would evaluate a function on the client's blinded credential ID without learning the input; the client would obtain the revocation status without learning the server's key. This would complement the Bloom filter mechanism by providing real-time revocation status at the cost of a single network round-trip, while preserving query privacy.

---

## 12. Conclusion

Trust Calculus provides a formal system for composable trust between arbitrary communicating nodes. Its core insight is that cryptographic signatures can be composed: if each link in a chain is locally verifiable, the chain can be locally evaluated under explicit continuity and policy rules. By combining Ed25519 signatures (for unforgeable assertions), scope intersection (for monotonic attenuation), revocation distribution primitives, and HMAC-SHA256 PPIDs (for cross-context unlinkability), Trust Calculus targets a combination of properties, local verification, composition, attenuation, revocation, and privacy, that is uncommon in mainstream trust deployments.

The practical consequence is a shift in the economics of trust. When verification can be performed with low latency and without issuer callback round-trips, trust evaluation can move closer to each interaction point. Messages can carry reusable proofs, delegations can carry explicit constraints, and chain validation can remain locally explainable.

As computing shifts toward autonomous agents, federated services, and ubiquitous devices, the need for composable machine-to-machine trust will grow substantially. Trust Calculus offers a foundation: lightweight enough for practical verification paths, formal enough for rigorous safety analysis, and general enough to apply wherever nodes must communicate trusted facts.

---

## References

[1] D. J. Bernstein, N. Duif, T. Lange, P. Schwabe, and B.-Y. Yang, "High-speed high-security signatures," *Journal of Cryptographic Engineering*, vol. 2, no. 2, pp. 77–89, 2012. (Ed25519)

[2] M. Bellare, R. Canetti, and H. Krawczyk, "Keying hash functions for message authentication," in *Advances in Cryptology, CRYPTO '96*, pp. 1–15, Springer, 1996. (HMAC)

[3] B. H. Bloom, "Space/time trade-offs in hash coding with allowable errors," *Communications of the ACM*, vol. 13, no. 7, pp. 422–426, 1970. (Bloom filters)

[4] W3C, "Verifiable Credentials Data Model 1.1," W3C Recommendation, March 2022. https://www.w3.org/TR/vc-data-model/

[5] W3C, "Web Authentication: An API for accessing Public Key Credentials," W3C Recommendation, March 2021. https://www.w3.org/TR/webauthn-2/

[6] IETF, "Edwards-Curve Digital Signature Algorithm (EdDSA)," RFC 8032, January 2017.

[7] B. Laurie, A. Langley, and E. Kasper, "Certificate Transparency," RFC 6962, June 2013.

[8] UCAN Working Group, "UCAN Specification v0.10.0," 2023. https://github.com/ucan-wg/spec

---

**Acknowledgments.** The reference implementation, Lemma.id, uses the Web Cryptography API for browser-side Ed25519 verification and HMAC-SHA256 PPID derivation, the Dalek Cryptography library (via Rust/PyO3) for server-side Ed25519 signing and credential issuance, and AWS KMS for HSM-backed key management.

**Availability.** The Lemma verification library and Trust Calculus specification are available at https://lemma.id.

---

*© 2026 Lemma Labs, Inc. All rights reserved.*
