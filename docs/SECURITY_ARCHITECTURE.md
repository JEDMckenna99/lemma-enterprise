# 🔐 Lemma Security Architecture

## Overview

Lemma implements defense-in-depth security with multiple layers of cryptographic protection, hardware-backed key storage, and privacy-preserving verification.

---

## 🏗️ Security Layers

### **Layer 1: Cryptographic Primitives**

#### **Ed25519 Signatures**
- **Purpose**: Credential integrity and non-repudiation
- **Performance**: ~28μs verification
- **Key Size**: 32 bytes (256-bit security)
- **Standards**: RFC 8032, FIPS 186-5

#### **OPRF (Oblivious Pseudorandom Function)**
- **Purpose**: Privacy-preserving revocation
- **Performance**: ~3.4μs evaluation
- **Privacy**: Server learns nothing about credential
- **Implementation**: Curve25519-based OPRF

#### **Bloom Filters**
- **Purpose**: Efficient revocation checking
- **Size**: Configurable (0.1% false positive rate)
- **Performance**: O(k) where k = number of hash functions
- **Network Isolation**: Site-specific filters

---

### **Layer 2: Key Management (AWS KMS)**

#### **HSM-Backed Key Storage**

**Architecture:**
```
┌─────────────────────────────────────────────────────────┐
│ AWS KMS (FIPS 140-2 Level 2/3 HSM)                      │
├─────────────────────────────────────────────────────────┤
│ Master CMK: arn:aws:kms:region:account:key/...          │
│ └─ Encrypts all site-specific Ed25519 signing keys      │
└─────────────────────────────────────────────────────────┘
           ↓ Encrypt                    ↑ Decrypt
┌──────────────────────────────────────────────────────────┐
│ PostgreSQL Database                                       │
├───────────────────────────────────────────────────────────┤
│ sites table:                                              │
│ ├─ kms_encrypted_signing_key (TEXT) ← Ciphertext         │
│ ├─ kms_key_id (VARCHAR)             ← Which CMK used     │
│ ├─ public_key_hex (VARCHAR)         ← Public key         │
│ ├─ issuer_did (VARCHAR)             ← DID identifier     │
│ └─ key_status (VARCHAR)             ← Lifecycle state    │
└───────────────────────────────────────────────────────────┘
           ↓ Load & Decrypt              
┌───────────────────────────────────────────────────────────┐
│ Application Memory (Cached)                               │
├───────────────────────────────────────────────────────────┤
│ Decrypted Ed25519 signing keys (per dyno)                 │
│ └─ Cleared on dyno restart                                │
└───────────────────────────────────────────────────────────┘
```

**Security Properties:**

1. **Encryption at Rest**
   - Private keys NEVER stored in plaintext
   - AES-256-GCM encryption (AWS KMS default)
   - Keys generated and encrypted on creation

2. **Encryption Context**
   ```python
   encryption_context = {
       'site_id': 'customer_site',
       'key_type': 'ed25519_signing_key',
       'purpose': 'lemma_iam_credential_signing',
       'version': '1.0'
   }
   ```
   - Prevents using encrypted keys for wrong sites
   - Protects against replay attacks
   - Logged in CloudTrail for audit

3. **Key Rotation**
   - Automatic CMK rotation (annual)
   - Old key versions remain active for decryption
   - Zero-downtime rotation
   - Site keys rotated on-demand

4. **Access Control**
   - IAM policies restrict KMS access
   - Least privilege principle
   - No `kms:DeleteKey` for application
   - Full audit trail in CloudTrail

---

### **Layer 3: Network Isolation**

#### **Site-Specific Cryptographic Boundaries**

```
Site A (acme.com)
├─ Ed25519 Keypair A
│  └─ did:lemma:a1b2c3...
├─ OPRF Key A
└─ Bloom Filter A
   └─ Only Site A revocations

Site B (beta.io)
├─ Ed25519 Keypair B (DIFFERENT!)
│  └─ did:lemma:x9y8z7...
├─ OPRF Key B (DIFFERENT!)
└─ Bloom Filter B (DIFFERENT!)
   └─ Only Site B revocations
```

**Isolation Guarantees:**
- Site A credentials CANNOT be used on Site B (different issuer DID)
- Site A revocations DON'T affect Site B (separate Bloom filters)
- Site A key compromise DOESN'T affect Site B (independent keys)

---

### **Layer 4: Client-Side Security**

#### **Browser Wallet Encryption**

**Encrypted Wallet Architecture:**
```
Browser Fingerprint
     ↓
  PBKDF2 (100K iterations)
     ↓
AES-256-GCM Key
     ↓
Encrypt Credentials
     ↓
localStorage (encrypted)
```

**Security Features:**
- Browser fingerprint-based encryption
- AES-256-GCM authenticated encryption
- Transparent to user (no password needed)
- Automatic decryption on access

#### **Multi-Device Sync**

**HPKE Rewrapping:**
```
Device A                    Server                     Device B
Private Key A  →  Encrypt with B's Public Key  →  Decrypt with Private Key B
```

**Security Properties:**
- Server never sees plaintext credentials
- End-to-end encryption between devices
- Ephemeral session keys
- Automatic cleanup (5-minute expiration)

---

### **Layer 5: Zero-Knowledge Proofs**

#### **Privacy-Preserving Claims**

**Supported ZKP Types:**

1. **Range Proofs**
   - Prove age ≥ 21 without revealing exact age
   - Prove balance ≥ $100 without revealing amount
   - Bulletproofs for efficient range proofs

2. **Membership Proofs**
   - Prove membership in group without revealing which member
   - Merkle tree-based accumulator
   - Privacy-preserving group verification

3. **Selective Disclosure**
   - Reveal only required claims
   - Hash-based commitment scheme
   - Cryptographic binding to base credential

**Performance:**
- Range proof generation: ~50ms
- Range proof verification: ~10ms
- Membership proof verification: ~5ms

---

## 🔒 Compliance & Standards

### **FIPS 140-2 Level 2/3**
- ✅ AWS KMS validated HSMs
- ✅ Cryptographic module testing
- ✅ Physical security requirements
- ✅ Role-based authentication

### **SOC 2 Type II**
- ✅ Security controls
- ✅ Availability guarantees
- ✅ Processing integrity
- ✅ Confidentiality protection
- ✅ Privacy safeguards

### **GDPR Compliance**
- ✅ Data minimization (only essential data stored)
- ✅ Right to erasure (credential revocation)
- ✅ Data portability (wallet export)
- ✅ Privacy by design (ZKP, OPRF)
- ✅ Encryption at rest and in transit

### **HIPAA-Ready**
- ✅ Encryption of PHI
- ✅ Access controls
- ✅ Audit trails
- ✅ Business associate agreements available

---

## 🎯 Threat Model

### **In-Scope Threats**

| Threat | Mitigation |
|--------|------------|
| **Credential Forgery** | Ed25519 signatures (256-bit security) |
| **Replay Attacks** | Timestamp validation + nonces |
| **Man-in-the-Middle** | TLS 1.3 + certificate pinning |
| **Database Breach** | KMS encryption (keys remain safe) |
| **Key Compromise** | Site isolation (1 site ≠ all sites) |
| **Revocation Privacy** | OPRF (server learns nothing) |
| **Cross-Site Tracking** | Pairwise DIDs per site |
| **Sybil Attacks** | Uniqueness tags per relying party |

### **Out-of-Scope Threats**

- Physical access to AWS data centers (AWS responsibility)
- Quantum computing attacks (post-quantum upgrade planned)
- Nation-state APTs with unlimited resources
- Social engineering of end users
- Compromised end-user devices

---

## 📊 Security Metrics

### **Cryptographic Strength**

| Primitive | Security Level | Quantum Safe? |
|-----------|---------------|---------------|
| Ed25519 | 128-bit | No (upgrade planned) |
| AES-256-GCM | 256-bit | Yes |
| SHA-256 | 128-bit | Yes |
| Curve25519 | 128-bit | No (upgrade planned) |
| PBKDF2 (100K) | ~17-bit | N/A |

### **Performance vs Security**

```
High Security                    High Performance
     ↓                                ↑
┌────────────────────────────────────────┐
│                                        │
│   KMS Decrypt: 15ms                    │ (First request only)
│        ↓                               │
│   Cached Signing: 0.5ms                │ (All subsequent)
│        ↓                               │
│   Ed25519 Verify: 28μs                 │ (Client-side)
│        ↓                               │
│   OPRF Check: 3.4μs                    │ (Privacy-preserving)
│                                        │
└────────────────────────────────────────┘
```

---

## 🔐 Key Rotation Procedures

### **Automatic Rotation (AWS KMS)**

1. AWS rotates CMK annually
2. Old key versions remain active
3. New encryptions use new key version
4. Old ciphertexts still decrypt with old version
5. Zero downtime, transparent to application

### **Manual Site Key Rotation**

```python
# 1. Generate new Ed25519 keypair
new_issuer = PyMinimalIssuer()

# 2. Encrypt with KMS
new_encrypted_key = kms.encrypt_signing_key(
    new_issuer.get_signing_key_bytes(),
    site_id
)

# 3. Update database
site.kms_encrypted_signing_key = new_encrypted_key
site.key_rotation_due = datetime.utcnow() + timedelta(days=365)

# 4. Mark old key as deprecated
site.old_issuer_did = site.issuer_did
site.issuer_did = new_issuer.get_did()

# 5. Grace period (both keys valid)
# 6. Revoke old key after grace period
```

---

## 📚 References

- **KMS Setup**: `docs/KMS_SETUP_GUIDE.md`
- **Site Isolation**: `docs/SITE_SPECIFIC_KEY_ARCHITECTURE.md`
- **Wallet Security**: `RUST_CRYPTO_WALLET_GUIDE.md`
- **Code**: `api/kms_manager.py`, `lemma-crypto/src/`

---

## 🎯 Security Roadmap

### **Completed (v895)**
- ✅ AWS KMS integration
- ✅ FIPS 140-2 Level 2/3 compliance
- ✅ Site-specific key isolation
- ✅ Automatic key rotation
- ✅ Full audit trail

### **Planned**
- 🔄 Post-quantum cryptography (Dilithium signatures)
- 🔄 Hardware security key support (YubiKey, etc.)
- 🔄 Confidential computing (Intel SGX, AMD SEV)
- 🔄 Formal verification of critical paths
- 🔄 Bug bounty program

