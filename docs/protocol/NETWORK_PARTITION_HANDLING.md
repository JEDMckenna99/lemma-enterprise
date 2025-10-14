# Network Partition Handling Specification

## Overview

This document specifies how the Lemma stateless verification protocol handles network partitions, extended offline periods, and graceful degradation scenarios.

---

## 1. Network Partition Scenarios

### 1.1 Client Offline Scenarios

**Scenario A: Short Offline Period (< 7 days)**
```
User goes offline: Day 0
Bloom filter age: 0 days
Bloom filter expires: Day 7
User comes back online: Day 3

Result: ✅ NO ISSUES
- Filter still valid
- All verifications work normally
- No sync required
```

**Scenario B: Medium Offline Period (7-30 days)**
```
User goes offline: Day 0
Bloom filter age: 0 days
Bloom filter expires: Day 7
User comes back online: Day 20

Result: ⚠️ FILTER EXPIRED
- Filter verification fails (expired)
- Client must sync new filter
- Credentials still valid
- Brief sync period required
```

**Scenario C: Long Offline Period (> 90 days)**
```
User goes offline: Day 0
OPRF key version: v1
OPRF key grace period ends: Day 90
User comes back online: Day 100

Result: 🔴 KEY EXPIRED
- OPRF key v1 deprecated or expired
- Credentials using v1 may be invalid
- Must re-issue credentials with new key
```

### 1.2 Server Offline Scenarios

**Scenario D: Revocation Service Down**
```
Client has: Valid filter (age 3 days)
Server: Revocation API unavailable
User: Attempts verification

Result: ✅ DEGRADED BUT WORKING
- Client continues using cached filter
- Verification completes offline
- No immediate impact on users
- Missing: New revocations since last sync
```

**Scenario E: Complete Network Partition**
```
Client has: Valid filter (age 5 days)
Network: Complete partition (no internet)
User: Attempts verification

Result: ✅ FULLY OFFLINE
- All verification completes locally
- Ed25519 signature check: ✅
- OPRF evaluation: ✅ (cached)
- Bloom filter check: ✅
- Total time: ~31μs
```

---

## 2. Grace Period Configuration

### 2.1 Risk-Based Grace Periods

Different use cases require different security/availability trade-offs:

**Low-Risk Applications** (blogs, public content)
```rust
pub struct GraceConfig {
    max_filter_age: i64,           // 30 days
    max_key_age: i64,              // 120 days
    allow_expired_verification: true,
    warn_on_stale: true,
}
```

**Medium-Risk Applications** (e-commerce, SaaS)
```rust
pub struct GraceConfig {
    max_filter_age: i64,           // 7 days
    max_key_age: i64,              // 90 days
    allow_expired_verification: false,
    warn_on_stale: true,
}
```

**High-Risk Applications** (banking, healthcare)
```rust
pub struct GraceConfig {
    max_filter_age: i64,           // 24 hours
    max_key_age: i64,              // 7 days
    allow_expired_verification: false,
    require_strict_sync: true,
}
```

### 2.2 Implementation

```rust
pub struct NetworkPartitionHandler {
    config: GraceConfig,
    last_sync: i64,
    current_filter_age: i64,
}

impl NetworkPartitionHandler {
    pub fn check_verification_allowed(&self, credential: &Credential) -> Result<VerificationDecision> {
        let now = current_timestamp();
        let filter_age = now - self.last_sync;
        
        // Check filter age
        if filter_age > self.config.max_filter_age {
            if self.config.allow_expired_verification {
                return Ok(VerificationDecision::AllowWithWarning {
                    warning: "Filter expired but verification allowed",
                    filter_age_days: filter_age / 86400,
                });
            } else {
                return Ok(VerificationDecision::Deny {
                    reason: "Filter too old, sync required",
                    required_action: "Sync bloom filter",
                });
            }
        }
        
        // Check key version age
        let key_age = self.get_key_age(credential.oprf_key_version)?;
        if key_age > self.config.max_key_age {
            return Ok(VerificationDecision::Deny {
                reason: "OPRF key too old, credential re-issuance required",
                required_action: "Obtain new credential",
            });
        }
        
        Ok(VerificationDecision::Allow)
    }
}

pub enum VerificationDecision {
    Allow,
    AllowWithWarning { warning: String, filter_age_days: i64 },
    Deny { reason: String, required_action: String },
}
```

---

## 3. Sync Strategies

### 3.1 Opportunistic Sync

**Trigger Conditions:**
- App startup (check for updates)
- Every 24 hours (background sync)
- When filter age > 5 days (proactive refresh)
- After verification failure (emergency sync)

**Implementation:**
```javascript
class OpportunisticSyncer {
    constructor() {
        this.syncInterval = 24 * 3600 * 1000; // 24 hours
        this.lastSync = 0;
    }
    
    async backgroundSync() {
        const now = Date.now();
        
        // Check if sync needed
        if (now - this.lastSync > this.syncInterval) {
            try {
                await this.syncBloomFilter();
                await this.syncOPRFMetadata();
                this.lastSync = now;
            } catch (error) {
                console.warn('Background sync failed:', error);
                // Continue with cached data
            }
        }
    }
    
    async onAppStart() {
        // Always try to sync on startup
        try {
            await this.syncBloomFilter();
            this.lastSync = Date.now();
        } catch (error) {
            // Fall back to cached filter
            this.loadCachedFilter();
        }
    }
}
```

### 3.2 Lazy Sync

**Trigger:** Only when absolutely necessary

```javascript
async function verifyCredential(credential) {
    // Try verification with current filter
    try {
        const filter = getCurrentFilter();
        
        // Check if filter is stale
        if (filter.age() > 7 * 24 * 3600) {
            // Stale - try to sync
            await syncFilter();
        }
        
        // Verify with (possibly updated) filter
        return filter.checkRevocation(credential);
        
    } catch (syncError) {
        // Sync failed, use cached filter anyway
        console.warn('Using stale filter:', syncError);
        return cachedFilter.checkRevocation(credential);
    }
}
```

### 3.3 Aggressive Sync

**For High-Security Applications:**

```javascript
async function verifyCredentialStrict(credential) {
    // ALWAYS sync before verification
    await syncFilter(); // Throws if network unavailable
    
    const filter = getCurrentFilter();
    
    // Strict checks
    if (filter.age() > 3600) { // > 1 hour old
        throw new Error('Filter too stale for high-security verification');
    }
    
    return filter.checkRevocation(credential);
}
```

---

## 4. Revocation During Offline Period

### 4.1 The Problem

```
Timeline:
Day 0:  User goes offline (filter v100, has credential X)
Day 2:  Admin revokes credential X (added to filter v101)
Day 5:  User comes back online (still has filter v100)
        User's credential X still verifies (wrong!)
Day 5+: User syncs filter v101
        User's credential X now shows as revoked (correct)
```

**Exposure Window**: 3 days (Day 2 to Day 5)

### 4.2 Solution: Time-to-Revocation Guarantees

**For Different Risk Levels:**

**Low-Risk (blogs):**
- Max exposure: 30 days
- Acceptable for public content
- Availability prioritized

**Medium-Risk (e-commerce):**
- Max exposure: 7 days
- Filters expire after 7 days
- Security/availability balanced

**High-Risk (banking):**
- Max exposure: 24 hours
- Require daily sync
- Security prioritized

### 4.3 Timestamp-Based Mitigation

**Add sync timestamp to verifications:**

```rust
pub struct VerificationContext {
    credential: Credential,
    filter_version: u64,
    filter_age: i64,
    last_sync: i64,
}

pub fn verify_with_freshness_check(ctx: &VerificationContext) -> Result<bool> {
    // Check how old the filter is
    let now = current_timestamp();
    let filter_age = now - ctx.last_sync;
    
    // For high-risk operations, require fresh filter
    if ctx.is_high_risk && filter_age > 3600 {
        return Err(FilterTooStale);
    }
    
    // Normal verification
    verify_credential(&ctx.credential, ctx.filter_version)
}
```

---

## 5. Byzantine Fault Tolerance

### 5.1 Multiple Authority Scenario

**Problem**: What if network authority is compromised or malicious?

**Solution (Future)**: Multi-authority signing

```rust
pub struct MultiAuthorityEnvelope {
    filter_data: Vec<u8>,
    version: u64,
    // ... other fields
    
    // Require k-of-n signatures
    required_signatures: usize,  // k = 2
    total_authorities: usize,    // n = 3
    signatures: Vec<AuthoritySignature>,
}

pub struct AuthoritySignature {
    authority_did: String,
    signature: [u8; 64],
}

impl MultiAuthorityEnvelope {
    pub fn verify(&self, authority_keys: &[VerifyingKey]) -> Result<()> {
        let mut valid_sigs = 0;
        
        for auth_sig in &self.signatures {
            if let Some(key) = find_authority_key(&auth_sig.authority_did, authority_keys) {
                if self.verify_signature(key, &auth_sig.signature).is_ok() {
                    valid_sigs += 1;
                }
            }
        }
        
        if valid_sigs >= self.required_signatures {
            Ok(())
        } else {
            Err(InsufficientSignatures)
        }
    }
}
```

### 5.2 Client-Side Consensus

**If multiple conflicting filters exist:**

```javascript
async function resolveConflictingFilters(filters) {
    // Choose filter with:
    // 1. Highest version number
    // 2. Most recent timestamp
    // 3. Most authority signatures
    
    const sorted = filters.sort((a, b) => {
        if (a.version !== b.version) return b.version - a.version;
        if (a.created_at !== b.created_at) return b.created_at - a.created_at;
        return b.signatures.length - a.signatures.length;
    });
    
    return sorted[0];
}
```

---

## 6. Client Implementation Guide

### 6.1 Filter Storage

```javascript
class BloomFilterStorage {
    constructor() {
        this.storageKey = 'lemma_bloom_filter_envelope';
    }
    
    storeEnvelope(envelope) {
        // Store in IndexedDB for persistence
        const db = await openDB('lemma-filters');
        await db.put('envelopes', envelope, envelope.version);
        
        // Also cache in memory
        this.currentEnvelope = envelope;
        
        // Track sync time
        localStorage.setItem('last_filter_sync', Date.now());
    }
    
    async loadEnvelope() {
        // Try memory first
        if (this.currentEnvelope) return this.currentEnvelope;
        
        // Load from IndexedDB
        const db = await openDB('lemma-filters');
        const latestVersion = await db.getKey('envelopes');
        return await db.get('envelopes', latestVersion);
    }
}
```

### 6.2 Sync Decision Logic

```javascript
function shouldSync() {
    const lastSync = parseInt(localStorage.getItem('last_filter_sync') || '0');
    const filterAge = Date.now() - lastSync;
    
    // Sync if:
    return (
        filterAge > 24 * 3600 * 1000 ||  // > 24 hours
        !this.currentEnvelope ||          // No filter
        this.currentEnvelope.should_refresh() // Expiring soon
    );
}
```

---

## 7. Monitoring & Alerts

### 7.1 Server-Side Monitoring

```python
def monitor_filter_distribution():
    metrics = {
        'current_version': get_current_filter_version(),
        'filter_age_hours': get_filter_age() / 3600,
        'clients_synced_24h': count_recent_syncs(24 * 3600),
        'clients_using_old_filter': count_clients_with_old_filter(),
        'filter_size_kb': get_current_filter_size() / 1024,
    }
    
    # Alert conditions
    if metrics['filter_age_hours'] > 168:  # > 7 days
        alert("Bloom filter not updated in 7 days")
    
    if metrics['clients_using_old_filter'] > 0.1 * total_clients:
        warn("10%+ clients using outdated filters")
    
    return metrics
```

### 7.2 Client-Side Metrics

```javascript
function reportFilterMetrics() {
    const metrics = {
        filter_version: currentEnvelope.version,
        filter_age_seconds: Date.now() / 1000 - currentEnvelope.created_at,
        last_sync_seconds_ago: Date.now() - lastSync,
        sync_failures_24h: getSyncFailureCount(),
        offline_verifications: getOfflineVerificationCount(),
    };
    
    // Send to analytics (if online)
    if (navigator.onLine) {
        sendMetrics(metrics);
    }
}
```

---

## 8. Graceful Degradation Strategies

### 8.1 Stale Filter Handling

```rust
pub enum FilterFreshness {
    Fresh,      // < 24 hours old
    Acceptable, // 24 hours - 7 days
    Stale,      // 7 days - 30 days
    Expired,    // > 30 days
}

pub fn determine_verification_strategy(filter_freshness: FilterFreshness, risk_level: RiskLevel) -> Strategy {
    match (filter_freshness, risk_level) {
        (Fresh, _) => Strategy::Standard,
        (Acceptable, Low) => Strategy::Standard,
        (Acceptable, Medium | High) => Strategy::WarnUser,
        (Stale, Low) => Strategy::WarnUser,
        (Stale, Medium) => Strategy::RequireSync,
        (Stale, High) => Strategy::DenyUntilSync,
        (Expired, _) => Strategy::DenyUntilSync,
    }
}
```

### 8.2 Fallback Verification Paths

```javascript
async function verifyWithFallback(credential) {
    try {
        // Path 1: Standard offline verification
        return await verifyOffline(credential);
    } catch (error) {
        if (error.message.includes('filter expired')) {
            try {
                // Path 2: Sync and retry
                await syncFilter();
                return await verifyOffline(credential);
            } catch (syncError) {
                // Path 3: Online verification fallback
                console.warn('Falling back to online verification');
                return await verifyOnline(credential);
            }
        }
        throw error;
    }
}
```

---

## 9. Configuration Recommendations

### 9.1 By Application Type

**Public Websites (Low Risk)**
```javascript
const config = {
    max_filter_age_days: 30,
    sync_frequency_hours: 72,      // Sync every 3 days
    allow_stale_verification: true,
    require_sync_for_high_value: false,
};
```

**SaaS Applications (Medium Risk)**
```javascript
const config = {
    max_filter_age_days: 7,
    sync_frequency_hours: 24,      // Daily sync
    allow_stale_verification: false,
    require_sync_for_high_value: true,
};
```

**Financial Applications (High Risk)**
```javascript
const config = {
    max_filter_age_hours: 24,
    sync_frequency_hours: 1,       // Hourly sync
    allow_stale_verification: false,
    require_online_for_critical: true,
};
```

### 9.2 User Experience Considerations

**Balance Security vs. UX:**

```javascript
function getVerificationPolicy(operation) {
    if (operation.type === 'read_public_content') {
        // Favor availability
        return {
            max_filter_age: 30 * 24 * 3600,
            allow_offline: true,
            require_fresh_sync: false,
        };
    }
    
    if (operation.type === 'modify_data' || operation.value > 1000) {
        // Favor security
        return {
            max_filter_age: 3600,
            allow_offline: false,
            require_fresh_sync: true,
        };
    }
    
    // Default: balanced
    return {
        max_filter_age: 7 * 24 * 3600,
        allow_offline: true,
        require_fresh_sync: false,
    };
}
```

---

## 10. Best Practices

### 10.1 Client Implementation

✅ **DO:**
- Store filters persistently (IndexedDB)
- Track last sync timestamp
- Implement exponential backoff for failed syncs
- Cache multiple recent filter versions
- Log sync failures for debugging

❌ **DON'T:**
- Silently use expired filters without warning
- Retry sync indefinitely (resource waste)
- Block user operations during sync
- Delete old filters immediately (keep for chain validation)

### 10.2 Server Implementation

✅ **DO:**
- Maintain recent filter history (last 10 versions)
- Log filter distribution metrics
- Monitor sync failure rates
- Provide metadata about filter freshness
- Support conditional GET (If-Modified-Since)

❌ **DON'T:**
- Delete old filter versions immediately
- Rate limit sync requests too aggressively
- Return unsigned filters
- Allow version gaps

---

## 11. Testing Scenarios

### 11.1 Network Partition Tests

```python
def test_extended_offline():
    """Test verification during extended offline period"""
    
    # 1. Establish baseline
    credential = issue_credential()
    filter = sync_bloom_filter()
    assert verify_offline(credential, filter) == True
    
    # 2. Simulate offline period
    disconnect_network()
    time.sleep(10 * 24 * 3600)  # 10 days offline
    
    # 3. Attempt verification
    result = verify_offline(credential, filter)
    
    # 4. Check expected behavior
    assert result == FilterExpired or result == AllowWithWarning
    
    # 5. Reconnect and sync
    reconnect_network()
    new_filter = sync_bloom_filter()
    
    # 6. Verification should work again
    assert verify_offline(credential, new_filter) == True
```

### 11.2 Revocation During Offline Tests

```python
def test_revocation_during_offline():
    """Test that revocations made while offline take effect on sync"""
    
    # 1. User goes offline
    credential = issue_credential()
    filter_v100 = sync_bloom_filter()
    disconnect_network()
    
    # 2. Admin revokes credential (server-side)
    revoke_credential(credential.id)  # Added to filter v101
    
    # 3. User still offline, verification succeeds (using v100)
    assert verify_offline(credential, filter_v100) == True
    
    # 4. User comes back online
    reconnect_network()
    filter_v101 = sync_bloom_filter()
    
    # 5. Verification now fails (using v101)
    assert verify_offline(credential, filter_v101) == False
```

---

## ✅ Summary

Network partition handling provides:

- ✅ **Configurable grace periods** based on risk level
- ✅ **Graceful degradation** when network unavailable  
- ✅ **Opportunistic syncing** for optimal freshness
- ✅ **Fallback strategies** for extended offline
- ✅ **Clear time-to-revocation guarantees**
- ✅ **Appropriate security/availability trade-offs**

**Default Configuration** (Medium Risk):
- Filter max age: 7 days
- Sync frequency: 24 hours
- Allow offline verification: Yes
- Warn on stale filters: Yes

This ensures Lemma's >99.9% offline operation while maintaining security properties appropriate for each use case.

