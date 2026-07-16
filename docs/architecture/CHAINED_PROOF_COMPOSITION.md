# Chained Proof Composition for Agent Delegation

**Author:** Jed McKenna  
**Date:** 2026-01-24  
**Status:** Technical Analysis

## Abstract

This document presents a formal treatment of **chained proof composition** as applied to AI agent delegation. We define a model where heterogeneous cryptographic proofs, issued by different authorities, using different trust assumptions, can be composed into a single presentation that enables an autonomous agent to act on behalf of a human principal without triggering bot detection mechanisms or revealing the principal's identity.

The key insight is that each proof in the chain answers a different trust question, and the composition preserves privacy at each layer while providing the verifier with sufficient assurance to authorize the action.

## 1. Problem Statement

### 1.1 The Agent Authentication Problem

AI agents require authorization to act autonomously across web services. Current approaches have significant limitations:

| Approach | Privacy | Security | Practicality |
|----------|---------|----------|--------------|
| API keys passed to agent | None | Poor (key exposure) | High |
| OAuth tokens to agent | User identified | Medium (token scope) | Medium |
| Agent impersonates user | None | Very poor | High |
| Per-action human approval | N/A | High | Very low |

None of these approaches solve the core problem: **proving that an authorized human delegated a specific action to an agent, without revealing which human**.

### 1.2 Requirements for Agent Delegation

A complete agent delegation solution must satisfy:

1. **Human Authorization**: Proof that a real human authorized the delegation
2. **Account Binding**: Proof that the human has an account with the target service
3. **Delegation Scope**: Specification of what actions are delegated
4. **Non-Correlation**: The delegation should not create a linkable identifier across services
5. **Revocability**: The delegation can be revoked without revoking the underlying credentials
6. **Bot Bypass**: Services can distinguish delegated agent actions from unauthorized bots
7. **Performance**: Authorization should not dominate agent inference time

### 1.3 Existing Work

**Anonymous Credentials** (Idemix, U-Prove, BBS+):
- Support selective disclosure and unlinkability
- Typically single-issuer systems
- Limited support for credential composition

**Verifiable Credentials (W3C VC)**:
- Support multi-credential presentation
- No native privacy preservation in composition
- Correlation possible through subject identifiers

**OAuth 2.0 / OIDC**:
- Designed for direct human-service interaction
- Token reveals user identity to relying party
- No native delegation composition

**SPIFFE/SPIRE**:
- Workload identity, not human delegation
- Does not address agent authorization problem

## 2. Chained Proof Model

### 2.1 Definitions

**Definition 1 (Lemma)**: A lemma \( L \) is a tuple:
\[
L = (id, issuer, subject, claims, expires\_at, \sigma)
\]
where \( \sigma \) is an Ed25519 signature over the canonical encoding of the preceding fields.

**Definition 2 (Proof Chain)**: A proof chain \( C \) is an ordered sequence of lemmas:
\[
C = (L_1, L_2, \ldots, L_n)
\]
where each lemma addresses a distinct trust question.

**Definition 3 (Chain Validity)**: A chain \( C \) is valid if and only if:
1. Each \( L_i \) has a valid signature under its issuer's public key
2. Each \( L_i \) is not expired
3. Each \( L_i \) is not revoked (per the issuer's revocation set)
4. The chain satisfies the policy requirements of the verifier

**Definition 4 (Heterogeneous Composition)**: Composition is heterogeneous if the lemmas in the chain:
- Have different issuers
- Use different subject identifiers (PPIDs)
- Answer different trust questions

### 2.2 The Agent Delegation Chain

For agent delegation, we define a four-layer chain:

```
Layer 1: Site Credential
┌─────────────────────────────────────────────────────────────┐
│ L_site = (id, site_issuer, ppid_site, {account: true}, ...)│
│                                                             │
│ Trust Question: Does this entity have an account here?      │
│ Issuer: The target service                                  │
│ Subject: Site-specific PPID                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
Layer 2: Human Verification
┌─────────────────────────────────────────────────────────────┐
│ L_human = (id, lemma.id, ppid_lemma, {isHuman: true}, ...) │
│                                                             │
│ Trust Question: Is this a unique human (not a bot farm)?    │
│ Issuer: Lemma.id (Proof-of-Human authority)                 │
│ Subject: Lemma-specific PPID                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
Layer 3: Agent Delegation
┌─────────────────────────────────────────────────────────────┐
│ L_delegate = (id, wallet, agent_id, {scope: [...]}, ...)   │
│                                                             │
│ Trust Question: Has the human authorized this agent?        │
│ Issuer: User's wallet (self-issued)                         │
│ Subject: Agent identifier                                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
Layer 4: Wallet Authentication
┌─────────────────────────────────────────────────────────────┐
│ L_auth = (id, device, wallet_id, {passkey: verified}, ...) │
│                                                             │
│ Trust Question: Did the wallet holder consent recently?     │
│ Issuer: Device secure enclave (passkey)                     │
│ Subject: Wallet identifier                                  │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 Trust Questions and Issuers

| Layer | Trust Question | Issuer | Frequency |
|-------|---------------|--------|-----------|
| Site Credential | "Does this entity have an account?" | Target service | Once per service |
| Human Verification | "Is this a unique human?" | Lemma.id | Once globally |
| Agent Delegation | "Has the human authorized this agent?" | User wallet | Per agent |
| Wallet Auth | "Did the holder consent?" | Device TPM | Per session |

Each layer is issued by the entity best positioned to answer that specific question.

## 3. Privacy Analysis

### 3.1 Pairwise Subject Identifiers

Each lemma uses a different subject identifier derived for its specific context:

\[
ppid_{site} = HMAC(master\_secret, site\_domain)
\]
\[
ppid_{lemma} = HMAC(master\_secret, "lemma.id")
\]
\[
agent\_id = Hash(agent\_public\_key)
\]
\[
wallet\_id = Hash(passkey\_credential\_id)
\]

**Property 1 (Cross-Layer Unlinkability)**: Given only the proof chain, a verifier cannot link:
- \( ppid_{site} \) to \( ppid_{lemma} \) (different derivation domains)
- The user's identity across different services
- Multiple chains from the same user

**Proof Sketch**: Each PPID is derived using a domain-separated HMAC. Without the master secret, the verifier cannot compute the correlation. The only entity that can link all PPIDs is the wallet holder.

### 3.2 Verifier Knowledge

After validating a chain, the verifier learns:

| Fact | Learned | Not Learned |
|------|---------|-------------|
| Account exists | Yes (site credential valid) | Which human |
| Human authorized | Yes (isHuman valid) | Human's identity |
| Agent delegated | Yes (delegation valid) | Other delegations |
| Recent consent | Yes (passkey timestamp) | Passkey details |

The verifier gains sufficient trust to authorize the action without learning the user's identity.

### 3.3 Correlation Resistance

**Threat**: A malicious verifier collects chains and attempts to correlate users.

**Mitigation**: 
- Different PPIDs per service prevent direct correlation
- Agent delegation lemmas can be rotated per session
- Passkey authentication produces fresh signatures

**Residual Risk**: If the same agent ID is used across services, the agent's actions are correlatable (not the human's).

## 4. Security Analysis

### 4.1 Threat Model

| Threat | Mitigation | Residual Risk |
|--------|------------|---------------|
| Forged chain | Ed25519 signature verification | Key compromise |
| Stolen chain | Passkey binding, expiration | Device compromise |
| Replay attack | Timestamps, nonces, revocation | Timing window |
| Collusion (issuer + verifier) | Different issuers per layer | Multi-party collusion |
| Delegation abuse | Scoped permissions, revocation | Overly broad scope |

### 4.2 Chain Integrity

**Theorem 1 (Chain Unforgeability)**: Under the EUF-CMA security of Ed25519, an adversary cannot produce a valid chain \( C' \) without:
1. Obtaining valid lemmas from each issuer, OR
2. Compromising at least one issuer's signing key

**Proof Sketch**: Each lemma is independently signed. Forging any single lemma requires breaking Ed25519. The chain is valid only if all lemmas are valid.

### 4.3 Delegation Revocation

The chain supports granular revocation:

| Revoke | Effect | Other Chains Affected |
|--------|--------|----------------------|
| Site credential | Agent loses service access | Only this service |
| Human verification | All delegations invalidated | All services |
| Agent delegation | Specific agent loses access | Only this agent |
| Wallet auth | Session ends | Current session only |

This granularity is a key advantage over single-credential systems.

## 5. Performance Analysis

### 5.1 Verification Cost

For a chain of \( n \) lemmas, verification requires:
- \( n \) Ed25519 signature verifications
- \( n \) revocation set lookups
- \( n \) expiration checks

**Measured Performance** (reference: Lemma whitepaper):

| Operation | Time (Native) | Time (Browser) |
|-----------|---------------|----------------|
| Ed25519 verify | ~35 μs | ~1 ms |
| SHA-256 hash | ~1 μs | ~0.1 ms |
| Revocation lookup | ~5 μs | ~0.5 ms |

For a 4-layer chain:
- Native: ~160 μs total
- Browser: ~6 ms total

### 5.2 Comparison with Current Agent Auth

| Approach | Latency | Network Calls | Privacy |
|----------|---------|---------------|---------|
| OAuth + bot check | 200-800 ms | 2-4 | None |
| API key validation | 50-150 ms | 1 | None |
| **Chained lemmas** | **6-10 ms** | **0** | **Preserved** |

### 5.3 Agent Inference Cost Savings

For an agent performing 100 actions per task:

| Auth Method | Overhead per Task | At $0.05/sec inference |
|-------------|-------------------|------------------------|
| OAuth flow | 20-80 seconds | $1.00-4.00 wasted |
| Chained lemmas | 0.6-1 second | $0.03-0.05 wasted |

The performance advantage is **20-80x** reduction in auth overhead.

## 6. Composition Properties

### 6.1 What Makes This Composition Novel

**Established techniques**:
- ZK proof composition (recursive SNARKs)
- Anonymous credential presentation
- Multi-credential VCs

**Novel aspects of this model**:

1. **Heterogeneous Trust Anchors**: Each layer has a different issuer with different trust assumptions. Unlike recursive ZK proofs (same proof system) or standard VC presentation (same credential format), this composes across trust domains.

2. **Hardware-Rooted Consent**: The passkey layer binds the entire chain to a hardware root of trust (TPM/Secure Enclave). This is not common in credential composition schemes.

3. **Privacy-Preserving Delegation**: Most delegation systems (OAuth, capability tokens) reveal the delegator. This model proves delegation occurred without identifying the delegator.

4. **Agent-Specific Application**: The specific use case of agent delegation with bot bypass is underexplored. Most identity systems assume direct human interaction.

### 6.2 Formal Properties

**Property 2 (Composability)**: Any subset of the chain can be verified independently. A verifier requiring only human verification can validate \( L_{human} \) without the other layers.

**Property 3 (Selective Disclosure)**: The holder can present:
- Full chain (maximum trust)
- Partial chain (minimum disclosure)
- Different chains to different verifiers

**Property 4 (Revocation Independence)**: Revoking \( L_i \) does not invalidate \( L_j \) for \( j \neq i \). The user retains valid credentials at unaffected layers.

## 7. Protocol Specification

### 7.1 Chain Construction (Agent Side)

```
ConstructDelegationChain(wallet, agent, target_service):
  
  // Layer 1: Retrieve site credential
  L_site ← wallet.getCredential(target_service.domain)
  if L_site is None: fail("No account with service")
  
  // Layer 2: Retrieve human verification
  L_human ← wallet.getCredential("lemma.id", "isHuman")
  if L_human is None: fail("Human verification required")
  
  // Layer 3: Create or retrieve agent delegation
  L_delegate ← wallet.getDelegation(agent.id)
  if L_delegate is None:
    L_delegate ← wallet.createDelegation(agent.id, scope)
  
  // Layer 4: Authenticate wallet
  L_auth ← wallet.authenticate(passkey)
  
  // Compose chain
  chain ← (L_site, L_human, L_delegate, L_auth)
  return chain
```

### 7.2 Chain Verification (Service Side)

```
VerifyDelegationChain(chain, policy):
  
  (L_site, L_human, L_delegate, L_auth) ← chain
  
  // Verify each layer
  for L in chain:
    issuer_pk ← IssuerRegistry.getPublicKey(L.issuer)
    if not Ed25519Verify(issuer_pk, Canon(L), L.sigma):
      return (false, "Invalid signature")
    if now > L.expires_at:
      return (false, "Expired credential")
    if RevocationSet.contains(SHA256(L.id)):
      return (false, "Revoked credential")
  
  // Check policy requirements
  if policy.requiresHuman and not L_human.claims.isHuman:
    return (false, "Human verification required")
  if policy.requiresAccount and not L_site.claims.account:
    return (false, "Account required")
  if not policy.allowedScopes.contains(L_delegate.claims.scope):
    return (false, "Scope not allowed")
  if now - L_auth.claims.timestamp > policy.maxAuthAge:
    return (false, "Authentication too old")
  
  return (true, "Chain valid")
```

### 7.3 Agent Action Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Agent     │     │   Wallet    │     │   Service   │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │ RequestChain()    │                   │
       │──────────────────>│                   │
       │                   │                   │
       │                   │ PasskeyAuth()     │
       │                   │<─────────────────>│ (local)
       │                   │                   │
       │     Chain         │                   │
       │<──────────────────│                   │
       │                   │                   │
       │           Action + Chain              │
       │──────────────────────────────────────>│
       │                   │                   │
       │                   │    VerifyChain()  │
       │                   │                   │ (local)
       │                   │                   │
       │           Result                      │
       │<──────────────────────────────────────│
       │                   │                   │
```

## 8. Implementation Considerations

### 8.1 Wallet Requirements

The wallet must support:
- Secure storage of multiple credential types
- Passkey authentication for session management
- Delegation lemma issuance (self-signing)
- Chain composition for presentation

### 8.2 Service Integration

Services must:
- Register as issuers (for site-specific credentials)
- Implement chain verification
- Define policy for required chain layers
- Cache issuer public keys and revocation sets

### 8.3 Agent Integration

Agents must:
- Request chains from the wallet before actions
- Present chains with each service request
- Handle chain expiration and renewal
- Respect delegation scope limits

## 9. Related Work

### 9.1 Anonymous Credentials

**Idemix** (IBM): Supports multi-show unlinkability and selective disclosure. Single-issuer focus; composition requires all credentials from same issuer.

**U-Prove** (Microsoft): Token-based anonymous credentials. Limited multi-credential support.

**BBS+ Signatures**: Enable efficient selective disclosure. Used in some VC implementations. Does not address cross-issuer composition.

### 9.2 Delegation Systems

**OAuth 2.0**: Token-based delegation, but reveals user identity. No composition model.

**Macaroons**: Capability tokens with caveats. Can be chained, but not privacy-preserving.

**SPIFFE**: Workload identity for service-to-service auth. Does not address human delegation.

### 9.3 Proof Composition

**Recursive SNARKs**: Compose proofs within same proof system. High computational cost.

**Proof-Carrying Data**: General framework for proof composition. Requires compatible proof systems.

**This Work**: Composes across heterogeneous trust domains without requiring proof system compatibility.

## 10. Open Questions

### 10.1 Formal Security Proof

A complete security proof would require:
- Formal model of multi-issuer credential composition
- Analysis of cross-layer information leakage
- Reduction to standard cryptographic assumptions

### 10.2 Revocation Synchronization

How should agents handle revocation during long-running tasks?
- Periodic re-validation?
- Push-based revocation notifications?
- Graceful degradation on revocation?

### 10.3 Delegation Scope Granularity

What is the right level of granularity for delegation scopes?
- Per-action vs per-session vs per-service
- Temporal bounds
- Resource-specific limitations

### 10.4 Multi-Agent Delegation

Can a user delegate to multiple agents simultaneously?
- Separate delegation lemmas per agent
- Potential for delegation lemma reuse attacks
- Agent identity management

## 11. Conclusion

Chained proof composition provides a principled approach to agent delegation that:

1. **Separates concerns**: Each layer answers a distinct trust question
2. **Preserves privacy**: Pairwise identifiers prevent cross-service correlation
3. **Enables revocation**: Granular revocation at each layer
4. **Improves performance**: 20-80x reduction in auth latency vs current approaches
5. **Supports heterogeneous issuers**: No single point of trust or failure

The model extends the Lemma architecture to address the emerging problem of AI agent authorization, where current solutions (API keys, OAuth tokens) are inadequate for privacy and security requirements.

The technical novelty lies not in the individual cryptographic primitives (which are well-established) but in:
- The specific composition pattern for agent delegation
- Privacy-preserving delegation without identity revelation
- Hardware-rooted consent binding
- Application to the agent authorization use case

Further work is needed on formal security proofs, optimal revocation strategies, and practical deployment considerations.

## References

[1] J. Camenisch, A. Lysyanskaya, "Signature Schemes and Anonymous Credentials from Bilinear Maps," CRYPTO 2004.

[2] S. Brands, "Rethinking Public Key Infrastructure and Digital Certificates," MIT Press, 2000.

[3] D. Boneh, X. Boyen, H. Shacham, "Short Group Signatures," CRYPTO 2004.

[4] M. Sporny et al., "Verifiable Credentials Data Model 1.1," W3C Recommendation, 2022.

[5] B. Parno, J. Howell, C. Gentry, M. Raykova, "Pinocchio: Nearly Practical Verifiable Computation," IEEE S&P, 2013.

[6] A. Biryukov, D. Khovratovich, "Equihash: Asymmetric Proof-of-Work Based on the Generalized Birthday Problem," NDSS, 2016.

[7] FIDO Alliance, "FIDO2: Web Authentication (WebAuthn)," W3C Recommendation, 2021.

[8] E. Rescorla, "The Transport Layer Security (TLS) Protocol Version 1.3," RFC 8446, 2018.

[9] C. A. Wood, R. Barnes, "Oblivious Pseudorandom Functions (OPRFs)," RFC 9497, 2023.

[10] J. McKenna, "Digital Lemmas: An Edge-Verifiable Layer for Internet Identity," Lemma.id Whitepaper, 2025.
