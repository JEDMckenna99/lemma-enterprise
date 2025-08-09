# 🔄 LEMMA IDENTITY VERIFICATION - STEP-BY-STEP FLOW

## Detailed Sequence Diagram

```mermaid
sequenceDiagram
    participant User as 👤 User
    participant Browser as 🌐 Browser
    participant SiteA as 🏢 lemma.id
    participant Shield as 🛡️ Bot Shield
    participant Wallet as 📱 Federated Wallet
    participant Stripe as 💳 Stripe KYC
    participant Rust as 🦀 Rust Engine
    participant Network as 🌐 Network Sync
    participant SiteB as 🏢 lemma-identity-network
    
    Note over User,SiteB: INITIAL VERIFICATION FLOW (First Time)
    
    User->>Browser: Visit lemma.id
    Browser->>SiteA: Load page
    SiteA->>Shield: Initialize Bot Shield
    Shield->>Wallet: Check for identity credentials
    Wallet-->>Shield: No credentials found
    Shield-->>User: Show "Verify Identity" prompt
    
    User->>Shield: Click "Verify with Stripe"
    Shield->>Stripe: Redirect to Stripe Identity KYC
    
    Note over Stripe: User completes KYC:<br/>1. Document upload<br/>2. Liveness check<br/>3. Identity verification
    
    Stripe-->>SiteA: KYC completion callback
    SiteA->>Rust: create_federated_identity_credential_from_stripe()
    
    Note over Rust: Cryptographic Processing:<br/>• Generate Ed25519 keypair<br/>• Create identity claims<br/>• Sign with network authority<br/>• Generate ZKP proofs
    
    Rust-->>SiteA: Identity Lemma JSON<br/>{id, packageType: "identity",<br/>isHuman: true, verificationMethod: "stripe_identity"}
    
    SiteA->>Network: add_shared_identity_lemma()
    Network->>Network: Store in shared registry<br/>Index by user_id
    
    SiteA-->>Wallet: Return credential to browser
    Wallet->>Wallet: Store in IndexedDB + localStorage
    Wallet->>Network: POST /add-identity-lemma<br/>(Network sync)
    Network-->>Wallet: Confirmation
    
    Shield->>Rust: verify_credential() [~5 microseconds]
    Rust-->>Shield: Verification success
    Shield-->>User: Show protected content
    
    Note over User,SiteB: CROSS-SITE RECOGNITION FLOW (Subsequent Sites)
    
    User->>Browser: Visit lemma-identity-network
    Browser->>SiteB: Load page  
    SiteB->>Shield: Initialize Bot Shield
    Shield->>Wallet: Check for identity credentials
    
    alt Local credentials found
        Wallet-->>Shield: Return cached identity lemma
    else No local credentials
        Wallet->>Network: POST /check-shared-identity<br/>Auth: "Network lemma_network_federated_sync_2024"
        Network->>Network: Lookup user_id in shared registry
        Network-->>Wallet: {has_valid_identity: true, lemma_id, ...}
    end
    
    Shield->>Rust: verify_credential() [~5 microseconds]
    Rust-->>Shield: Verification success  
    Shield-->>User: Show protected content (NO RE-VERIFICATION!)
    
    Note over User,SiteB: REVOCATION FLOW (Network-wide)
    
    SiteA->>Network: revoke_credentials_network_wide()
    Network->>Network: Add to shared OPRF+Bloom filter
    Network->>SiteB: Broadcast revocation update
    Network->>SiteA: Update local bloom filter
    
    Note over Shield: Next verification check
    Shield->>Rust: verify_credential()
    Rust->>Network: Check revocation bloom filter
    Network-->>Rust: Credential revoked
    Rust-->>Shield: Verification failed
    Shield-->>User: Access denied
```

## 🔍 DETAILED FLOW BREAKDOWN

### Phase 1: Initial Identity Verification

#### Step 1-3: User Entry & Shield Check
- User navigates to any Lemma-protected site
- Bot Shield automatically initializes and queries the Federated Wallet
- Wallet performs multi-layer check: memory cache → sessionStorage → localStorage → IndexedDB

#### Step 4-6: Stripe KYC Process
- If no valid credentials found, user is prompted for identity verification
- Redirect to Stripe Identity with secure session management
- User completes comprehensive KYC: document upload, liveness detection, identity verification

#### Step 7-9: Rust Engine Credential Creation
- **Cryptographic Processing**: Ed25519 keypair generation, identity claim creation, network authority signing
- **Identity Lemma Structure**: Minimal 3-claim design for maximum privacy
- **Performance**: Sub-millisecond credential generation

#### Step 10-12: Network Distribution
- Credential automatically shared to federated network registry
- Multi-layer local storage for reliability and speed
- Network sync ensures cross-site availability

### Phase 2: Cross-Site Recognition

#### Step 13-15: Seamless Access
- User visits partner site in the network
- Federated Wallet automatically provides cached or network-retrieved credentials
- **No re-verification required** - instant access

#### Step 16-17: Microsecond Verification
- Rust engine performs cryptographic verification in ~5 microseconds
- User gains immediate access to protected content

### Phase 3: Network-Wide Revocation

#### Step 18-20: Instant Propagation
- Any site can trigger credential revocation
- OPRF+Bloom filter update propagates across entire network
- Real-time sync ensures immediate effectiveness

#### Step 21-23: Verification Failure
- Next verification check queries updated bloom filter
- Revoked credentials automatically fail verification
- User access denied across all network sites

## 🔐 SECURITY FEATURES

### Multi-Layer Verification
1. **Local Storage Check** - Instant access for returning users
2. **Network Registry Query** - Cross-site credential discovery
3. **Cryptographic Verification** - Ed25519 signature validation
4. **Revocation Check** - OPRF+Bloom filter query
5. **Background Validation** - Continuous security monitoring

### Privacy Protection
- **Minimal Data Storage** - Only essential claims (packageType, isHuman, verificationMethod)
- **Zero-Knowledge Proofs** - Prove claims without revealing underlying data
- **Unlinkable Revocation** - OPRF prevents correlation of revocation checks
- **Local-First Storage** - Credentials stored client-side, not on servers

### Performance Optimization
- **Microsecond Verification** - Rust-powered cryptographic operations
- **Multi-Layer Caching** - Memory → Session → Local → IndexedDB fallback
- **Offline Operation** - 99.9% verification works without network
- **Background Sync** - Network updates happen asynchronously

## 🌐 NETWORK ARCHITECTURE

### Federated Design
- **No Central Authority** - Peer-to-peer network of independent deployments
- **Shared Cryptographic Parameters** - Common OPRF keys and bloom filter settings
- **Consensus-Based Revocation** - Network agreement on credential invalidation
- **SDK Integration** - Any site can join using the Lemma SDK

### Scalability Features
- **Horizontal Scaling** - Add more network nodes without central coordination
- **Regional Distribution** - Network sync works globally with regional optimization
- **Load Distribution** - Verification load distributed across all network participants
- **Graceful Degradation** - System continues operating even if some nodes are offline

This architecture creates a **robust, privacy-preserving, and high-performance identity verification system** that scales globally while maintaining cryptographic security and user privacy.
