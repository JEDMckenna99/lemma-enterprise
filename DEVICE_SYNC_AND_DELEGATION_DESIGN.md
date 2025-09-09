# 🔄 Device Sync & Permission Delegation Design

## 🎯 **Challenge: Cross-Device Credential Management**

### **User Scenarios:**
1. **Device Sync**: User gets new phone, needs to sync their lemma credentials
2. **Browser Sync**: User uses different browsers, needs consistent access
3. **Temporary Access**: User wants to grant limited access to shared device
4. **Permission Delegation**: Mobile user grants temporary access to desktop

## 🏗️ **Lemma-Native Solution Design**

### **🔑 Method 1: Cryptographic Device Pairing (RECOMMENDED)**

#### **Core Concept:**
Instead of copying credentials, create **device-specific lemmas** that are cryptographically linked to the original.

```
Primary Device (Mobile):
├── Original Lemma: did:lemma:{mobile_public_key}
├── Creates Device Pair Lemma: Links new device cryptographically  
├── Signs delegation: "I authorize device X for Y duration"
└── No credential copying - maintains atomic structure

New Device (Browser/Desktop):
├── Receives Device Pair Lemma: did:lemma:{new_device_public_key}
├── Linked to primary via cryptographic delegation proof
├── Can verify independently using real crypto
└── Expires automatically - no revocation needed
```

#### **🔐 Cryptographic Implementation:**
```rust
// Device pairing lemma structure
pub struct DevicePairLemma {
    id: String,
    issuer: String,                    // Primary device DID
    subject: String,                   // New device DID  
    credentialSubject: {
        packageType: "device_delegation",
        primaryDevice: String,         // Primary device DID
        delegatedDevice: String,       // New device DID
        delegationScope: Vec<String>,  // What permissions are delegated
        validFrom: u64,               // Start time
        validUntil: u64,              // Expiration time
        delegationType: String,       // "full_sync" | "temporary_access" | "limited_scope"
    },
    proof: Ed25519Signature           // Signed by primary device
}
```

### **🔄 Method 2: OPRF-Based Sync Protocol**

#### **Privacy-Preserving Credential Sync:**
```
Sync Protocol (No Server Storage):
1. Primary Device: Encrypts credentials with OPRF-derived key
2. Sync Service: Stores only encrypted blobs (can't read content)
3. New Device: Uses OPRF to derive same key and decrypt
4. Zero-Knowledge: Sync service never sees credential content

OPRF Sync Key Derivation:
sync_key = OPRF(user_master_secret + device_fingerprint)
encrypted_credentials = AES-GCM(credentials, sync_key)
```

#### **🎯 Benefits:**
- **Privacy**: Lemma never sees credential content
- **Security**: Each device derives unique keys
- **Minimal Storage**: Only encrypted blobs, not credential data
- **Atomic Integrity**: Original lemmas remain unchanged

## 🚀 **Recommended Implementation**

### **📱 Primary: Device Delegation Lemmas**

```javascript
// Mobile device creates delegation for new browser
class LemmaDeviceSync {
    async createDeviceDelegation(newDevicePublicKey, scope, duration) {
        // Create device-specific lemma (not credential copy)
        const delegationLemma = {
            "@context": ["https://www.w3.org/2018/credentials/v1"],
            "id": `device_delegation_${Date.now()}`,
            "issuer": this.mobileDeviceDID,           // Mobile device DID
            "subject": newDevicePublicKey,            // New device DID
            "issuanceDate": Date.now(),
            "expirationDate": Date.now() + duration,
            "credentialSubject": {
                "packageType": "device_delegation",
                "primaryDevice": this.mobileDeviceDID,
                "delegatedDevice": newDevicePublicKey,
                "scope": scope,                       // ["federated_identity", "iam_permissions"]
                "delegationType": "temporary_access"
            },
            "proof": {
                "type": "Ed25519Signature2020",
                "signatureValue": await this.signDelegation(/* ... */)
            }
        };
        
        return delegationLemma;
    }
    
    async syncToNewDevice(newDevicePublicKey) {
        // Create full sync delegation
        const syncLemma = await this.createDeviceDelegation(
            newDevicePublicKey,
            ["full_credential_access"],
            7 * 24 * 60 * 60 * 1000  // 7 days
        );
        
        // Use OPRF for privacy-preserving transfer
        const syncKey = await this.deriveOPRFSyncKey(newDevicePublicKey);
        const encryptedPackage = await this.encryptCredentialsForSync(syncKey);
        
        return {
            delegationLemma: syncLemma,
            encryptedPackage: encryptedPackage,
            transferMethod: "oprf_encrypted_sync"
        };
    }
}
```

### **🌐 Secondary: OPRF Sync Service**

```python
# Lemma sync service (minimal storage, maximum privacy)
class LemmaPrivacySyncService:
    def __init__(self):
        self.oprf_server = OPRFServer()  # Privacy-preserving key derivation
        self.encrypted_storage = {}     # Only encrypted blobs
        
    def store_encrypted_sync_package(self, user_oprf_id, encrypted_package):
        # Store only encrypted data - can't read content
        sync_id = self.oprf_server.evaluate(user_oprf_id)
        self.encrypted_storage[sync_id] = {
            'encrypted_data': encrypted_package,
            'created_at': time.time(),
            'expires_at': time.time() + (7 * 24 * 60 * 60),  # 7 days
            'size_bytes': len(encrypted_package)
        }
        
        # Minimal storage overhead - just encrypted blobs
        return sync_id
    
    def retrieve_encrypted_sync_package(self, user_oprf_id):
        sync_id = self.oprf_server.evaluate(user_oprf_id)
        package = self.encrypted_storage.get(sync_id)
        
        if package and package['expires_at'] > time.time():
            return package['encrypted_data']
        
        return None  # Expired or not found
```

## 🔐 **Implementation Strategy**

### **✅ Phase 1: Device Delegation Lemmas**
```rust
// Add to lemma-crypto
pub struct DeviceDelegationVerifier {
    base_verifier: OptimizedVerifier,
}

impl DeviceDelegationVerifier {
    pub fn verify_device_delegation(&mut self, delegation_lemma: &MinimalCredential, original_credentials: &[MinimalCredential]) -> Result<bool> {
        // 1. Verify delegation lemma signature (primary device signed it)
        let delegation_valid = self.base_verifier.verify_optimized(delegation_lemma)?;
        
        if !delegation_valid.verified {
            return Ok(false);
        }
        
        // 2. Check delegation hasn't expired
        let current_time = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs();
        if delegation_lemma.expires_at.unwrap_or(0) < current_time {
            return Ok(false);
        }
        
        // 3. Verify each original credential
        for credential in original_credentials {
            let result = self.base_verifier.verify_optimized(credential)?;
            if !result.verified {
                return Ok(false);
            }
        }
        
        // 4. Check delegation scope covers the credentials
        let delegation_scope = delegation_lemma.claims.get("scope").unwrap();
        // Validate scope covers the credential types...
        
        Ok(true)
    }
}
```

### **📱 Phase 2: Mobile-to-Browser Flow**

```javascript
// Mobile app (primary device)
class LemmaMobileSync {
    async grantBrowserAccess(browserPublicKey, duration = 24 * 60 * 60 * 1000) {
        // Create temporary delegation lemma
        const delegation = await this.createDeviceDelegation(
            browserPublicKey,
            ["federated_identity", "iam_permissions"],
            duration
        );
        
        // Generate QR code for browser scanning
        const qrData = {
            delegationLemma: delegation,
            syncEndpoint: "https://sync.lemma.id/device-pair",
            expiresAt: Date.now() + duration
        };
        
        return this.generateQRCode(qrData);
    }
}

// Browser (new device)
class LemmaBrowserSync {
    async scanMobileQR(qrData) {
        // 1. Receive delegation lemma from mobile
        const delegation = qrData.delegationLemma;
        
        // 2. Verify delegation is valid and not expired
        const isValid = await this.verifyDelegation(delegation);
        
        if (isValid) {
            // 3. Store delegation lemma (enables temporary access)
            await this.storeDelegationLemma(delegation);
            
            // 4. Can now act on behalf of mobile device
            return {
                success: true,
                accessLevel: delegation.credentialSubject.scope,
                expiresAt: delegation.expirationDate,
                primaryDevice: delegation.credentialSubject.primaryDevice
            };
        }
        
        return { success: false, reason: 'Invalid delegation' };
    }
}
```

## 🎯 **Storage Overhead Minimization**

### **✅ Lemma Platform Storage: ZERO**
```
User Credential Storage:
├── User's Device: Stores their own credentials
├── Lemma Platform: Stores NOTHING (zero storage overhead)
├── Sync Service: Only encrypted blobs (can't read content)
└── Delegation: Temporary lemmas (auto-expire)

Storage Comparison:
Traditional IAM: Store all user data on servers
Lemma Approach: Users store their own data
Lemma Overhead: Zero credential storage
```

### **🔒 Privacy Benefits:**
- **Zero Knowledge**: Lemma never sees credential content
- **User Controlled**: Users own and control their data
- **Minimal Attack Surface**: No central credential database
- **GDPR Compliant**: No personal data stored by Lemma

## 🚀 **Implementation Priority**

### **✅ Ready to Implement:**
1. **Device Delegation Lemmas**: Extend current crypto engine
2. **QR Code Pairing**: Mobile-to-browser delegation
3. **OPRF Sync Service**: Privacy-preserving credential sync
4. **Automatic Expiration**: Time-based access control

### **🎯 User Experience:**
```
Mobile User Workflow:
1. Open Lemma app on mobile
2. Scan "Add Device" QR from browser
3. Choose delegation scope and duration
4. Approve delegation (biometric/PIN)
5. Browser instantly gets temporary access

Browser User Workflow:
1. Visit site requiring Lemma
2. Click "Sync from Mobile"
3. Show QR code
4. Scan with mobile app
5. Instant access (5-15μs WASM verification)
```

**This solution maintains the fundamental lemma atomic structure, provides excellent UX, minimizes storage overhead, and preserves cryptographic integrity!** 🎉

Would you like me to implement the device delegation system?
