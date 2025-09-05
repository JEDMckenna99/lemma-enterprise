# 🔄 Lemma Revocation Architecture - Client-Side Credential Management

## 🎯 **Core Principle: Users Own Their Credentials**

In Lemma's architecture, **users store credentials in their own wallets** (client-side), not on your servers. This creates a unique revocation challenge and opportunity.

## 🏗️ **Two-Layer Revocation System**

### **1. Server-Side Revocation Registry (Your Control)**
```python
# Mark user as revoked in your database
def revoke_customer_access(email, reason):
    """
    Revoke customer access - adds to revocation registry
    Does NOT delete client-side credentials (impossible)
    """
    
    # Add to revocation registry
    revocation_entry = {
        'user_email': email,
        'user_did': f"did:lemma:customer:{customer_id}",
        'revoked_at': datetime.utcnow(),
        'revocation_reason': reason,
        'revoked_by': 'admin',
        'network_propagated': False  # Will be propagated to sites
    }
    
    # Add to bloom filter for fast checking
    revocation_bloom_filter.add(user_did)
    
    # Propagate to all sites using your service
    propagate_revocation_to_sites(revocation_entry)
```

### **2. Client-Side Verification (Automatic)**
```javascript
// User's wallet checks revocation on every verification attempt
class LemmaWallet {
    async verifyCredential(credential) {
        // Step 1: Check local revocation cache
        if (this.localRevocationCache.has(credential.id)) {
            return { verified: false, reason: 'revoked_locally' };
        }
        
        // Step 2: Check with server revocation registry
        const revocationCheck = await fetch('/api/verify/check-revocation', {
            method: 'POST',
            body: JSON.stringify({
                credential_id: credential.id,
                user_did: credential.subject
            })
        });
        
        const revocationResult = await revocationCheck.json();
        
        if (revocationResult.revoked) {
            // Cache revocation locally
            this.localRevocationCache.add(credential.id);
            return { 
                verified: false, 
                reason: 'revoked_by_issuer',
                revoked_at: revocationResult.revoked_at
            };
        }
        
        // Step 3: Proceed with normal verification
        return await this.performCryptographicVerification(credential);
    }
}
```

## 🔐 **Revocation Implementation Strategy**

### **Option A: Soft Revocation (Recommended)**
**How it works**: User keeps credentials, but they fail verification

```python
@app.route('/api/verify/check-revocation', methods=['POST'])
def check_credential_revocation():
    """
    Check if a credential has been revoked
    Called by user's wallet during verification
    """
    data = request.get_json()
    credential_id = data.get('credential_id')
    user_did = data.get('user_did')
    
    # Check revocation registry
    is_revoked = check_revocation_registry(credential_id, user_did)
    
    if is_revoked:
        return jsonify({
            'revoked': True,
            'revoked_at': get_revocation_timestamp(credential_id),
            'reason': get_revocation_reason(credential_id)
        })
    
    return jsonify({
        'revoked': False,
        'verified': True
    })
```

**Benefits**:
- ✅ **Immediate effect**: Revocation works on next verification attempt
- ✅ **User privacy**: User keeps their data, just can't use it
- ✅ **Audit trail**: Complete record of revocations
- ✅ **Reversible**: Can un-revoke if needed

### **Option B: Hard Revocation (Advanced)**
**How it works**: Force credential removal from user's wallet

```python
def force_credential_removal(user_email, credential_id):
    """
    Force removal of specific credential from user's wallet
    Requires user to be online and wallet accessible
    """
    
    # Add to immediate revocation list
    immediate_revocations[credential_id] = {
        'revoked_at': datetime.utcnow(),
        'force_removal': True,
        'reason': 'security_incident'
    }
    
    # Send removal command to user's wallet (if online)
    send_wallet_command(user_email, {
        'action': 'force_remove_credential',
        'credential_id': credential_id,
        'authority': 'did:lemma:platform:lemma.id',
        'reason': 'security_revocation'
    })
```

**Benefits**:
- ✅ **Complete removal**: Credential deleted from user's device
- ✅ **Security incidents**: Immediate response to compromised credentials
- ❌ **Complex**: Requires user to be online
- ❌ **Privacy concerns**: Forces action on user's device

## 🚀 **Recommended Implementation for Your Use Case**

### **For Customer Account Removal:**

```python
# api/customer_revocation.py
@app.route('/api/admin/customers/<email>/revoke', methods=['POST'])
def revoke_customer_account(email):
    """
    Revoke customer account - proper Lemma way
    """
    
    # 1. Mark customer as revoked in database
    db = get_db()
    customer = db.query(Customer).filter(Customer.email == email).first()
    
    if customer:
        customer.status = 'revoked'
        customer.revoked_at = datetime.utcnow()
        customer.revocation_reason = request.json.get('reason', 'admin_revocation')
        db.commit()
    
    # 2. Add all customer's credentials to revocation registry
    user_did = f"did:lemma:customer:{customer.customer_id}"
    
    # Add to global revocation bloom filter
    add_to_revocation_registry(user_did, 'customer_account_revoked')
    
    # 3. Propagate to all sites using your service
    propagate_revocation_to_network({
        'user_did': user_did,
        'revocation_type': 'customer_account',
        'revoked_at': datetime.utcnow().timestamp(),
        'reason': 'admin_revocation'
    })
    
    # 4. User's credentials will fail verification on next use
    # User keeps their data, but it's marked as invalid
    
    return jsonify({
        'success': True,
        'revocation_method': 'soft_revocation',
        'immediate_effect': 'next_verification_attempt',
        'user_data': 'preserved_but_invalid'
    })
```

### **For Your Specific Case (jedmckenna@effitix.com):**

Since this is for testing the secure registration flow, I recommend:

**Option 1: Temporary Revocation (Recommended)**
```python
# Mark as revoked, test new registration, then restore if needed
POST /api/admin/customers/jedmckenna@effitix.com/revoke
{
    "reason": "testing_secure_registration_flow",
    "temporary": true
}
```

**Option 2: Complete Removal (If you want fresh start)**
```python
# Delete completely for clean testing
DELETE /api/admin/customers/jedmckenna@effitix.com/delete
```

## 🔄 **Revocation Propagation Flow**

```
1. Admin revokes customer
   ↓
2. Added to revocation registry
   ↓  
3. Propagated to all sites via trust bundles
   ↓
4. User's wallet checks revocation on next verification
   ↓
5. Credential fails verification (but user keeps the data)
```

## 🎯 **Benefits of Lemma Revocation Model**

### **✅ Advantages:**
- **User privacy**: Users keep their data
- **Immediate effect**: Works on next verification
- **Network propagation**: All sites get revocation updates
- **Audit trail**: Complete revocation history
- **Reversible**: Can restore access if needed

### **🔧 Implementation:**
- **Bloom filters**: Fast revocation checking (microseconds)
- **OPRF integration**: Privacy-preserving revocation
- **Network sync**: Automatic propagation to all sites
- **Client caching**: Reduces server load

Would you like me to implement the customer revocation system and help you revoke the existing account so you can test the secure registration flow?
