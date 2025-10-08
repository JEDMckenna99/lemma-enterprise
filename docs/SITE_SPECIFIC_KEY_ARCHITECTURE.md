# 🔐 Site-Specific Key Architecture - IAM System

## 🎯 **Critical Design Principle**

**Each site gets its OWN unique cryptographic keys and revocation list.**

**NO SHARING between sites!**

---

## 🏗️ **Architecture Overview**

### **What Each Site Gets**

When a site registers (`POST /api/v1/sites/register`), the system creates:

```
Site: "company-a.com" (site_abc123)
├── 🔑 Unique Ed25519 Keypair
│   ├── Private Key: Used to sign permission lemmas
│   └── Public Key: Embedded in DID (did:lemma:a1b2c3d4e5f6...)
├── 🔒 Unique OPRF Key
│   └── Used for privacy-preserving revocation
└── 🌸 Unique Bloom Filter
    └── Stores THIS site's revoked credentials only

Site: "company-b.com" (site_xyz789)
├── 🔑 DIFFERENT Ed25519 Keypair
│   ├── Private Key: DIFFERENT from company-a
│   └── Public Key: DIFFERENT DID (did:lemma:9f8e7d6c5b4a...)
├── 🔒 DIFFERENT OPRF Key
│   └── DIFFERENT from company-a
└── 🌸 DIFFERENT Bloom Filter
    └── Stores ONLY company-b's revoked credentials
```

---

## 🔐 **Why Site-Specific Keys Matter**

### **Security Isolation**

```
❌ BAD (Shared Keys):
Company A issues credential → Signed with shared key
Company B verifies → Accepts Company A's credential!
Result: Company A can grant access to Company B's resources!

✅ GOOD (Site-Specific Keys):
Company A issues credential → Signed with Company A's key
Company B verifies → Rejects! (Wrong issuer DID)
Result: Perfect isolation between sites
```

### **Revocation Isolation**

```
❌ BAD (Shared Revocation List):
Company A revokes user@a.com → Added to shared Bloom filter
Company B checks user@b.com → False positive! (Bloom filter collision)
Result: Company B's users affected by Company A's revocations!

✅ GOOD (Site-Specific Revocation):
Company A revokes user@a.com → Added to Company A's Bloom filter
Company B checks user@b.com → Uses Company B's Bloom filter
Result: Perfect isolation, no cross-contamination
```

---

## 🔧 **Implementation Details**

### **Site Registration Flow**

```python
# api/permission_management_api.py

@permission_api.route('/api/v1/sites/register', methods=['POST'])
def register_site():
    # 1. Create site in database
    site = db.create_site(data)
    
    # 2. Create REAL IAM manager with UNIQUE keys
    manager = get_or_create_site_manager(site.site_id, site.site_domain)
    
    # This creates:
    # - NEW Ed25519 keypair (site-specific)
    # - NEW OPRF key (site-specific)
    # - NEW Bloom filter (site-specific)
    
    return {
        'site_id': site.site_id,
        'issuer_did': manager.issuer_did,  # Unique DID with site's public key
        'site_isolation': 'unique_keys_and_revocation_per_site'
    }
```

### **Permission Lemma Issuance**

```python
# api/real_iam_manager.py

class RealIAMSubnetManager:
    def __init__(self, site_id: str, site_domain: str):
        # Get or create SITE-SPECIFIC issuer
        self.issuer = self._get_or_create_site_issuer(site_id)
        self.issuer_did = self.issuer.get_did()  # Unique DID
        
        # Create SITE-SPECIFIC verifier
        self.verifier = PyOptimizedVerifier()
    
    def issue_permission_lemma(self, user_did, permission_id, ...):
        # Issue credential using THIS site's private key
        credential_json = self.issuer.issue_credential(
            user_did,
            json.dumps(claims),
            expiry_seconds
        )
        
        # Result: Credential signed with THIS site's key
        # Can ONLY be verified by THIS site
        return credential
```

### **Access Verification**

```python
# api/real_iam_manager.py

def verify_permission_lemma(self, credential: Dict):
    # Verify using Rust engine
    # This checks:
    # 1. Ed25519 signature matches THIS site's public key
    # 2. OPRF revocation check against THIS site's Bloom filter
    
    result = self.verifier.verify_credential(credential_json)
    
    # If credential was issued by DIFFERENT site:
    # - Signature verification FAILS (wrong public key)
    # - Access DENIED
    
    return is_valid, verification_time_us
```

---

## 📊 **Comparison: Shared vs Site-Specific**

| Aspect | Shared Keys (❌ BAD) | Site-Specific Keys (✅ GOOD) |
|--------|---------------------|---------------------------|
| **Security** | One compromised site = all sites compromised | One compromised site = only that site affected |
| **Isolation** | Credentials work across sites | Credentials ONLY work for issuing site |
| **Revocation** | Shared Bloom filter (cross-contamination) | Separate Bloom filters (perfect isolation) |
| **Privacy** | All sites see all revocations | Sites only see their own revocations |
| **Compliance** | Fails data isolation requirements | Meets data isolation requirements |
| **Trust Model** | Must trust all sites in network | Each site is independent |

---

## 🎯 **Real-World Example**

### **Scenario: Two Companies Using Lemma IAM**

**Company A (Healthcare):**
```
Site ID: site_health_123
Issuer DID: did:lemma:a1b2c3d4e5f6...
OPRF Key: oprf_key_health_abc
Bloom Filter: bloom_health_123

User: doctor@hospital.com
Permission: "medical_records:read"
Credential: Signed with Company A's private key
```

**Company B (Finance):**
```
Site ID: site_finance_456
Issuer DID: did:lemma:9f8e7d6c5b4a...  (DIFFERENT!)
OPRF Key: oprf_key_finance_xyz  (DIFFERENT!)
Bloom Filter: bloom_finance_456  (DIFFERENT!)

User: trader@bank.com
Permission: "trading:execute"
Credential: Signed with Company B's private key
```

### **What Happens If...**

**1. Doctor tries to access Finance system:**
```
Doctor presents credential to Company B
→ Company B extracts issuer DID: did:lemma:a1b2c3d4e5f6...
→ Company B's public key: did:lemma:9f8e7d6c5b4a...
→ MISMATCH! Signature verification FAILS
→ Access DENIED ✅
```

**2. Company A revokes doctor's credential:**
```
Company A adds to its Bloom filter: bloom_health_123
→ Doctor's credential now revoked for Company A
→ Company B's Bloom filter: bloom_finance_456 (unchanged)
→ Trader's credentials unaffected ✅
```

**3. Company A's private key is compromised:**
```
Attacker can issue credentials for Company A
→ But CANNOT issue credentials for Company B
→ Company B's system unaffected ✅
→ Only Company A needs to rotate keys
```

---

## 🔒 **Security Properties**

### **1. Perfect Isolation**
- Credentials from Site A cannot be used on Site B
- Revocations on Site A don't affect Site B
- Key compromise on Site A doesn't affect Site B

### **2. Cryptographic Guarantees**
- Ed25519 signatures: 256-bit security
- OPRF: Privacy-preserving revocation
- Bloom filters: Efficient membership testing

### **3. Compliance Benefits**
- GDPR: Data isolation between sites
- SOC 2: Separate security boundaries
- HIPAA: Healthcare data stays isolated
- PCI DSS: Financial data stays isolated

---

## 🚀 **Implementation Status**

### **✅ Completed**

```python
# api/real_iam_manager.py
class RealIAMSubnetManager:
    def __init__(self, site_id: str, site_domain: str):
        # ✅ Creates unique Ed25519 keypair per site
        self.issuer = self._get_or_create_site_issuer(site_id)
        
        # ✅ Creates unique verifier per site
        self.verifier = PyOptimizedVerifier()
        
        # ✅ Site-specific permission registry
        self.permissions: Dict[str, Dict] = {}
```

### **✅ API Endpoints Updated**

- `POST /api/v1/sites/register` → Creates unique keys
- `POST /api/v1/sites/{site_id}/permissions` → Uses site-specific issuer
- `POST /api/v1/sites/{site_id}/users/{user_did}/permissions` → Signs with site key
- `POST /api/v1/auth/verify` → Verifies with site key

---

## 📋 **Verification Checklist**

When testing, verify:

- [ ] Each site has different issuer DID
- [ ] Credentials from Site A fail verification on Site B
- [ ] Revocations on Site A don't affect Site B
- [ ] Performance is 31-94µs per site
- [ ] Logs show "site-specific" messages

---

## 🎯 **Key Takeaways**

1. **Each site = Unique Ed25519 keypair**
2. **Each site = Unique OPRF key**
3. **Each site = Unique Bloom filter**
4. **NO SHARING between sites**
5. **Perfect security isolation**
6. **Compliance-friendly architecture**

**This is NOT a federated identity network. This is site-specific IAM.**
