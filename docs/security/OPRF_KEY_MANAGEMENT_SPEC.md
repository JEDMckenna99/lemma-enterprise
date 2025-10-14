# OPRF Key Management Specification

## Overview

This document specifies the OPRF (Oblivious Pseudorandom Function) key management system implemented in Lemma v878, which provides secure, rotatable, versioned key management for privacy-preserving revocation.

---

## 1. Key Lifecycle

### 1.1 Key States

```
┌──────────┐  generate_new_version()  ┌──────────┐
│ No Keys  │ ──────────────────────> │ Pending  │
└──────────┘                          └──────────┘
                                           │
                                  activate_key()
                                           │
                                           ▼
                                      ┌──────────┐
                            ┌────────>│  Active  │
                            │         └──────────┘
                            │              │
                            │     activate_key(new_version)
                            │              │
                  revoke_key()             ▼
                            │         ┌──────────┐
                            │         │ Rotating │
                            │         └──────────┘
                            │              │
                            │     complete_rotation()
                            │              │
                            │              ▼
                            │         ┌──────────┐
                            └────────>│Deprecated│
                                      └──────────┘
                                           │
                                    (expires after
                                     grace period)
```

### 1.2 State Descriptions

**Pending**
- Key generated but not yet active
- Cannot be used for signing new credentials
- 7-day waiting period before activation
- Purpose: Allow time for key distribution

**Active**
- Currently signing new credentials
- Used for verification
- Only ONE key can be Active at a time
- Validity: 1 year from activation

**Rotating**
- Previously Active, now being phased out
- Still valid for verification
- Cannot sign new credentials
- Grace period: 90 days
- Purpose: Allow old credentials to remain valid

**Deprecated**
- Rotation complete
- Still valid for verification until expiration
- Cannot sign new credentials
- Eventually expires based on valid_until timestamp

**Revoked**
- Emergency revocation (key compromise suspected)
- Cannot be used for signing OR verification
- Immediate effect (valid_until set to current time)
- Auto-triggers generation of new Active key

---

## 2. Key Versioning

### 2.1 Version Numbering

```rust
pub struct OPRFKeyVersion {
    pub version: u32,              // Monotonically increasing (1, 2, 3...)
    pub key_material: [u8; 32],    // 256-bit Ristretto255 scalar
    pub created_at: i64,           // Unix timestamp
    pub valid_from: i64,           // When key becomes valid
    pub valid_until: i64,          // When key expires
    pub status: KeyStatus,         // Current lifecycle state
    pub key_type: KeyType,         // Network or Site(site_id)
}
```

### 2.2 Version Assignment

- First key: version = 1
- Each new key: version = previous + 1
- Versions are globally unique per KeyType
- Network keys: 1, 2, 3...
- Site keys: Each site has independent versioning

### 2.3 Credential Versioning

All credentials must include the OPRF key version used for revocation:

```json
{
  "id": "cred_abc123",
  "oprf_key_version": 2,
  // ... other fields
}
```

Verifiers use this to:
1. Select correct OPRF key for evaluation
2. Check appropriate bloom filter
3. Support mixed-version credentials during rotation

---

## 3. Key Rotation

### 3.1 Scheduled Rotation

**Frequency**: Every 365 days  
**Grace Period**: 90 days  
**Total Window**: 455 days of key validity

**Timeline:**
```
Day 0:    Generate new key v2 (Pending)
Day 7:    Activate key v2 (Active)
          Old key v1 → Rotating
Day 97:   Complete rotation
          Old key v1 → Deprecated
Day 365:  Key v1 expires
          Generate new key v3 (Pending)
```

### 3.2 Rotation Procedure

```rust
// 1. Generate new version (7 days before scheduled rotation)
let new_version = key_manager.generate_new_version()?;

// 2. Activate new version (on rotation day)
let plan = key_manager.activate_key(new_version)?;
// Returns: RotationPlan {
//   old_version: 1,
//   new_version: 2,
//   grace_period_days: 90,
//   estimated_completion: timestamp + 90 days
// }

// 3. Monitor transition (automated)
// - New credentials use v2
// - Old credentials remain valid with v1
// - Both bloom filters maintained

// 4. Complete rotation (after 90 days)
key_manager.complete_rotation(old_version)?;
// Old key → Deprecated (but still valid for verification)

// 5. Key expires naturally (after valid_until)
// - Credentials using old key must be re-issued
// - Automatic cleanup of expired keys
```

### 3.3 Multi-Version Verification

During rotation, verifiers support multiple key versions:

```rust
// Get supported versions
let versions = key_manager.get_supported_versions();
// Example during rotation: [1, 2]

// Verify credential
let oprf_key = key_manager.get_key_for_verification(credential.oprf_key_version)?;
let oprf_eval = compute_oprf(credential.id, oprf_key);
let filter = get_bloom_filter_for_version(credential.oprf_key_version);
let revoked = filter.contains(oprf_eval);
```

---

## 4. Emergency Key Revocation

### 4.1 Revocation Triggers

Immediate revocation required if:
- Key compromise confirmed (leaked, stolen, exposed)
- Key compromise suspected (unusual activity, security incident)
- Regulatory requirement (compliance order)
- Mathematical breakthrough (cryptographic weakness discovered)

### 4.2 Revocation Procedure

```rust
// Emergency revocation
key_manager.revoke_key(compromised_version, "Key compromise detected")?;

// Automatic actions:
// 1. Mark key as Revoked (immediate)
// 2. Set valid_until to current time
// 3. Generate new key version
// 4. Activate new key immediately
// 5. Log to audit trail

// Result:
// - Compromised key cannot be used
// - New key active within seconds
// - Old credentials must be re-issued
```

### 4.3 Impact Assessment

**Immediate Impact:**
- All credentials using revoked key become INVALID
- Users must obtain new credentials with new key version
- Re-issuance workflow must be triggered

**Grace Period:**
- NO grace period for revoked keys (security first)
- Immediate cutoff is intentional
- Better to deny access than allow compromised verification

**Recovery Steps:**
1. Revoke compromised key
2. Identify affected credentials
3. Re-issue all affected credentials
4. Notify users of required action
5. Monitor for suspicious activity

---

## 5. Key Distribution

### 5.1 Key Metadata Distribution

**Endpoint**: `GET /api/v1/oprf/key-metadata`

**Response**:
```json
{
  "success": true,
  "current_version": 2,
  "supported_versions": [1, 2],
  "rotation_schedule": {
    "next_rotation": "2026-01-15T00:00:00Z",
    "rotation_frequency_days": 365,
    "grace_period_days": 90
  },
  "timestamp": 1234567890
}
```

**Purpose:**
- Clients know which versions are currently valid
- Clients can check if they need to sync new keys
- Provides rotation schedule for planning

**Security**:
- Does NOT include actual key material
- Requires API key authentication
- Rate limited (100 requests/minute)

### 5.2 Actual Key Material

**Key material is NEVER distributed via API.**

Keys are:
- Stored server-side in secure storage (HSM or encrypted database)
- Used server-side for OPRF evaluation
- Never sent to clients
- Never logged or exposed

Clients receive:
- OPRF evaluations (server computes with key)
- Bloom filters (built from OPRF evaluations)
- Never the OPRF key itself

---

## 6. Security Properties

### 6.1 Cryptographic Guarantees

**Key Generation:**
- 256-bit entropy from `ring::rand::SystemRandom`
- Cryptographically secure random number generation
- Passed to Ristretto255 scalar space

**Key Storage:**
- Server-side only (never distributed)
- Encrypted at rest (application-level encryption)
- HSM storage recommended for production

**Key Usage:**
- Server-side OPRF evaluation only
- Never logged or transmitted
- Constant-time operations (timing attack resistance)

### 6.2 Attack Resistance

**Key Compromise:**
- Emergency revocation procedure
- Automatic new key generation
- All affected credentials invalidated
- Audit trail for incident response

**Downgrade Attack:**
- Version monotonicity enforced
- Clients reject lower versions
- Hash chain validation

**Replay Attack:**
- Time-bound key validity
- Keys expire after valid_until
- No infinite key lifetime

---

## 7. Operational Procedures

### 7.1 Scheduled Rotation (Annual)

**T-7 days**: Generate new key version (Pending state)
```bash
curl -X POST https://lemma.id/api/v1/oprf/initiate-rotation \
  -H "X-API-Key: admin_key" \
  -H "Content-Type: application/json" \
  -d '{"reason": "scheduled_annual_rotation"}'
```

**T-0 days**: Activation happens automatically after 7-day pending
- Old key → Rotating
- New key → Active
- Both valid during grace period

**T+90 days**: Complete rotation
- Old key → Deprecated
- Still valid until expiration
- New credentials use new key only

**T+365 days**: Old key expires
- Old key no longer valid
- Credentials using old key must be re-issued

### 7.2 Emergency Revocation

**Immediate Action:**
```bash
curl -X POST https://lemma.id/api/v1/oprf/revoke-key \
  -H "X-API-Key: admin_key" \
  -H "Content-Type: application/json" \
  -d '{
    "version": 2,
    "reason": "Key compromise confirmed - incident #12345"
  }'
```

**Automatic Response:**
- Key v2 → Revoked (immediate)
- New key v3 generated → Active
- All credentials using v2 become invalid
- Audit log entry created
- Alert notifications sent

**Follow-up Actions:**
1. Investigate compromise source
2. Re-issue all affected credentials
3. Notify affected users
4. Review security procedures
5. Update incident response documentation

### 7.3 Monitoring

**Key Age Monitoring:**
```python
# Check key age
current_version = key_manager.get_active_version()
key_metadata = key_manager.get_key_metadata(current_version)
age_days = (now() - key_metadata.created_at) / (24 * 3600)

if age_days > 350:
    alert("Key rotation due within 15 days")
```

**Version Support Monitoring:**
```python
# Check how many versions currently supported
supported = key_manager.get_supported_versions()

if len(supported) > 3:
    warn("Multiple key versions active - rotation may be overdue")
```

---

## 8. API Reference

### 8.1 Get Key Metadata

**Endpoint**: `GET /api/v1/oprf/key-metadata`

**Authentication**: Required (X-API-Key header)

**Rate Limit**: 100 requests/minute

**Response**:
```json
{
  "success": true,
  "current_version": 2,
  "supported_versions": [1, 2],
  "rotation_schedule": {
    "next_rotation": "2026-01-15T00:00:00Z",
    "rotation_frequency_days": 365,
    "grace_period_days": 90
  },
  "timestamp": 1697248490
}
```

### 8.2 Initiate Key Rotation

**Endpoint**: `POST /api/v1/oprf/initiate-rotation`

**Authentication**: Required (Admin-level API key)

**Rate Limit**: 5 requests/hour

**Request**:
```json
{
  "reason": "scheduled_annual_rotation"
}
```

**Response**:
```json
{
  "success": true,
  "rotation_plan": {
    "old_version": 1,
    "new_version": 2,
    "grace_period_days": 90,
    "estimated_completion": 1704960490
  },
  "message": "Key rotation initiated successfully",
  "next_steps": [
    "Old key will remain valid for 90 days",
    "New credentials will use new key",
    "Old credentials remain verifiable during grace period",
    "Rebuild bloom filters with new key"
  ]
}
```

### 8.3 Emergency Key Revocation

**Endpoint**: `POST /api/v1/oprf/revoke-key`

**Authentication**: Required (Admin-level API key)

**Rate Limit**: 2 requests/hour (emergency use only)

**Request**:
```json
{
  "version": 2,
  "reason": "Key compromise confirmed - incident #12345"
}
```

**Response**:
```json
{
  "success": true,
  "revoked_version": 2,
  "reason": "Key compromise confirmed - incident #12345",
  "new_active_version": 3,
  "message": "Key revoked and new key activated",
  "impact": "All credentials using revoked key are now invalid",
  "action_required": "Re-issue all credentials with new key version"
}
```

---

## 9. Security Considerations

### 9.1 Key Storage

**Production Requirements:**
- Store keys in Hardware Security Module (HSM) or encrypted database
- Never log key material
- Never transmit keys over network
- Use separate encryption keys for key-at-rest encryption

### 9.2 Access Control

**Who Can Rotate Keys:**
- System administrators only
- Requires elevated API key with rotation permission
- All rotation actions logged to audit trail
- Multi-factor authentication recommended

### 9.3 Audit Logging

All key operations must be logged:
```
- Key generation (version, timestamp, operator)
- Key activation (old version, new version, operator)
- Key revocation (version, reason, operator, incident reference)
- Key access (version, operation type, timestamp)
```

---

## 10. Implementation Details

### 10.1 Rust Implementation

**File**: `lemma-crypto/src/oprf_key_manager.rs`

**Key Components:**
```rust
pub struct OPRFKeyManager {
    keys: HashMap<u32, OPRFKeyVersion>,
    current_active_version: u32,
    key_type: KeyType,
}

impl OPRFKeyManager {
    pub fn generate_new_version(&mut self) -> Result<u32>;
    pub fn activate_key(&mut self, version: u32) -> Result<RotationPlan>;
    pub fn get_active_key(&self) -> Result<[u8; 32]>;
    pub fn get_key_for_verification(&self, version: u32) -> Result<[u8; 32]>;
    pub fn revoke_key(&mut self, version: u32, reason: &str) -> Result<()>;
    pub fn get_supported_versions(&self) -> Vec<u32>;
}
```

### 10.2 Python Integration

**File**: `lemma-crypto/src/minimal_python.rs`

**PyO3 Bindings:**
```python
from lemma_crypto import PyOPRFKeyManager

# Initialize
manager = PyOPRFKeyManager('network')

# Generate new version
new_version = manager.generate_new_version()

# Activate
plan = manager.activate_key(new_version)

# Get metadata
current = manager.get_active_version()
supported = manager.get_supported_versions()
```

### 10.3 API Integration

**File**: `api/oprf_key_api.py`

Flask blueprint with endpoints for key management operations.

---

## 11. Testing

### 11.1 Unit Tests

**File**: `lemma-crypto/src/oprf_key_manager.rs` (bottom of file)

Tests included:
- Key generation
- Key rotation with grace periods
- Emergency revocation
- Multi-version verification support

### 11.2 Integration Tests

```python
def test_key_rotation_workflow():
    manager = PyOPRFKeyManager('network')
    
    # Generate and activate first key
    v1 = manager.generate_new_version()
    manager.activate_key(v1)
    assert manager.get_active_version() == 1
    
    # Initiate rotation
    v2 = manager.generate_new_version()
    plan = manager.activate_key(v2)
    assert manager.get_active_version() == 2
    
    # Both keys should be supported during grace
    supported = manager.get_supported_versions()
    assert 1 in supported and 2 in supported
```

---

## 12. Migration Guide

### 12.1 Upgrading from v867 to v878

**Step 1**: Deploy v878 (includes key manager)

**Step 2**: Generate initial key on first startup
```python
# Automatic on app startup
manager = init_oprf_key_manager()
# If no keys exist, generates v1 and activates
```

**Step 3**: Existing credentials
- Old credentials don't have oprf_key_version field
- Default to version 1 for backward compatibility
- Re-issue gradually with versioned credentials

**Step 4**: Monitor
- Check key age periodically
- Plan rotation before 350 days
- Set up alerts for key expiration

---

## 13. Best Practices

### 13.1 Production Deployment

✅ **DO:**
- Store keys in HSM or encrypted database
- Set up automated rotation schedule
- Monitor key age and rotation status
- Maintain audit logs of all key operations
- Test rotation in staging first

❌ **DON'T:**
- Hardcode keys in source code
- Log key material
- Transmit keys over network
- Skip grace periods
- Delete old keys immediately

### 13.2 Monitoring

**Key Metrics to Track:**
- Current active key version
- Number of supported versions
- Days until next rotation
- Number of credentials per key version
- Failed verification rate (may indicate key issues)

### 13.3 Incident Response

**If Key Compromise Suspected:**
1. Immediately revoke key
2. Document incident
3. Analyze compromise vector
4. Re-issue all affected credentials
5. Review and update security procedures
6. Consider additional security measures

---

## 14. Performance Impact

### 14.1 Verification Performance

**Single-Version (no rotation):**
- OPRF evaluation: 3.4μs
- Bloom check: <1μs

**Multi-Version (during rotation):**
- Version lookup: <0.1μs (HashMap)
- OPRF evaluation: 3.4μs (same)
- Bloom check: <1μs (same)

**Total Overhead**: <0.1μs (~3% impact)

### 14.2 Storage Overhead

**Per Key Version:**
- Key material: 32 bytes
- Metadata: ~200 bytes
- Total: ~232 bytes per version

**During Rotation:**
- 2 keys active: ~464 bytes
- Negligible storage impact

### 14.3 Memory Overhead

**Runtime:**
- HashMap storage: O(n) where n = number of versions
- Typical: 2-3 versions active = <1KB memory
- Maximum: 10 versions (extreme) = ~2.5KB

**Negligible impact on overall system**

---

## 15. Future Enhancements

### 15.1 Planned Improvements

**Multi-Signature Key Generation**
- Threshold signatures for key generation
- Requires m-of-n administrators to generate keys
- Higher security for critical operations

**Automated Rotation**
- Cron job triggers rotation automatically
- No manual intervention required
- Email notifications to administrators

**Key Backup and Recovery**
- Encrypted key backups
- Multi-party recovery procedures
- Disaster recovery documentation

### 15.2 Advanced Features

**Hardware Security Module (HSM) Integration**
- Generate keys in HSM
- Never expose key material to software
- FIPS 140-2 Level 3 compliance

**Geographic Key Distribution**
- Different keys per region for compliance
- Faster OPRF evaluation (local keys)
- Regional key rotation

---

## ✅ Summary

The OPRF key management system provides:

- ✅ Versioned keys with lifecycle management
- ✅ Graceful rotation without downtime
- ✅ Emergency revocation capability
- ✅ Multi-version support during transitions
- ✅ Cryptographically secure key generation
- ✅ Comprehensive audit logging
- ✅ Minimal performance overhead

This addresses a critical gap in stateless verification systems and provides production-ready key management for the Lemma protocol.

