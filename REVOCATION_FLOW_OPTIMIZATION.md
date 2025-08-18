# 🚫 Lemma Revocation Flow Optimization - Hybrid Push-Pull Architecture

## 🎯 **Problem Statement**

Current revocation flow has potential delays between:
1. **Revocation Event** → Network registry update
2. **Registry Update** → Client-side detection
3. **Client Detection** → Access control enforcement

**Goal**: Achieve **sub-5-second** revocation propagation across the entire federated network.

---

## 🏗️ **Recommended Architecture: Hybrid Push-Pull**

### 🚀 **Tier 1: Critical Push Updates** (0-5 seconds)
**Use Case**: Security incidents, fraud detection, immediate threats
**Mechanism**: Server-initiated push notifications to all active clients

```javascript
// Server-side: Force immediate revocation check
POST /api/network/force-revocation-check
{
  "revocation_id": "security_incident_2024_001",
  "priority": "critical",           // critical, high, medium, low
  "force_immediate_check": true,
  "affected_credentials": ["cred_abc123", "cred_def456"],
  "witness_registry_hash": "sha256_new_registry_hash",
  "propagation_deadline": 5000,    // 5 seconds max
  "requires_acknowledgment": true
}

// Client-side: Immediate response to push
window.lemmaWallet.on('force_revocation_check', async (event) => {
  console.log('🚨 Critical revocation update received');
  
  // Immediate check without waiting for background interval
  await this.performImmediateRevocationCheck(event.affected_credentials);
  
  // Acknowledge receipt to server
  await this.acknowledgeRevocationUpdate(event.revocation_id);
});
```

### ⚡ **Tier 2: Enhanced Background Sync** (5-30 seconds)
**Use Case**: Regular revocations, expired credentials, policy updates
**Mechanism**: SDK-initiated checks with witness registry optimization

```javascript
// Enhanced background sync with registry change detection
class LemmaFederatedWallet {
  async syncRevocationLists() {
    // Get current witness registry hash
    const currentHash = await this.getWitnessRegistryHash();
    
    if (currentHash !== this.lastKnownRegistryHash) {
      console.log('📋 Witness registry updated, performing full revocation sync');
      
      // Full sync when registry changes
      await this.performFullRevocationSync();
      this.lastKnownRegistryHash = currentHash;
      
      // Trigger immediate re-validation of all stored credentials
      await this.revalidateAllCredentials();
      
      // Notify all protected elements
      this.notifyRevocationUpdate();
    }
  }
}
```

### 🔄 **Tier 3: Periodic Fallback Sync** (1-5 minutes)
**Use Case**: Network resilience, missed updates, offline recovery
**Mechanism**: Regular polling with exponential backoff

---

## 🛠️ **Implementation Plan**

### **Phase 1: Server-Side Push Infrastructure**

#### **A. Network Push API** (`api/network_push.py`)
```python
@network_push_bp.route('/api/network/force-revocation-check', methods=['POST'])
@require_network_auth
def force_revocation_check():
    """
    Force immediate revocation check across all network clients
    
    Priority Levels:
    - critical: 0-5 seconds (security incidents)
    - high: 5-15 seconds (fraud detection)
    - medium: 15-60 seconds (policy updates)
    - low: 1-5 minutes (routine maintenance)
    """
    try:
        data = request.get_json() or {}
        
        revocation_data = {
            'revocation_id': data.get('revocation_id'),
            'priority': data.get('priority', 'medium'),
            'affected_credentials': data.get('affected_credentials', []),
            'witness_registry_hash': data.get('witness_registry_hash'),
            'timestamp': time.time(),
            'requires_acknowledgment': data.get('requires_acknowledgment', False)
        }
        
        # Push to all active network nodes
        push_results = sync_manager.push_revocation_update(revocation_data)
        
        return jsonify({
            'success': True,
            'revocation_id': revocation_data['revocation_id'],
            'pushed_to_nodes': len(push_results),
            'propagation_time_ms': push_results.get('avg_propagation_time', 0)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
```

#### **B. WebSocket Push Mechanism**
```python
class NetworkSyncManager:
    def push_revocation_update(self, revocation_data):
        """Push revocation update to all active clients"""
        
        push_results = []
        
        for node_endpoint in self.get_active_network_nodes():
            try:
                # WebSocket push (preferred)
                if self.has_websocket_connection(node_endpoint):
                    result = self.websocket_push(node_endpoint, revocation_data)
                    push_results.append(result)
                
                # HTTP fallback
                else:
                    result = self.http_push(node_endpoint, revocation_data)
                    push_results.append(result)
                    
            except Exception as e:
                logger.warning(f"Failed to push to {node_endpoint}: {e}")
        
        return {
            'successful_pushes': len([r for r in push_results if r.get('success')]),
            'avg_propagation_time': sum(r.get('time_ms', 0) for r in push_results) / len(push_results)
        }
```

### **Phase 2: Client-Side Enhanced Checking**

#### **A. Immediate Response Handler**
```javascript
class LemmaFederatedWallet {
  setupRevocationPushHandlers() {
    // WebSocket listener for push updates
    if (this.websocket) {
      this.websocket.on('revocation_update', async (data) => {
        await this.handleRevocationPush(data);
      });
    }
    
    // HTTP polling fallback with registry hash checking
    setInterval(async () => {
      await this.checkForRevocationUpdates();
    }, this.getPollingInterval());
  }
  
  async handleRevocationPush(revocationData) {
    const { priority, affected_credentials, revocation_id } = revocationData;
    
    console.log(`🚨 Revocation push received (${priority}):`, revocation_id);
    
    // Immediate validation for affected credentials
    if (affected_credentials && affected_credentials.length > 0) {
      await this.validateSpecificCredentials(affected_credentials);
    } else {
      // Full credential validation for critical updates
      if (priority === 'critical') {
        await this.revalidateAllCredentials();
      }
    }
    
    // Update UI immediately
    this.notifyRevocationUpdate({
      type: 'push_update',
      priority: priority,
      affected_count: affected_credentials?.length || 0
    });
    
    // Acknowledge receipt if required
    if (revocationData.requires_acknowledgment) {
      await this.acknowledgeRevocationUpdate(revocation_id);
    }
  }
}
```

#### **B. Registry Change Detection**
```javascript
async checkForRevocationUpdates() {
  try {
    // Get current witness registry metadata
    const registryInfo = await fetch(`${this.networkConfig.registryUrl}/api/network/registry-info`, {
      headers: { 'Authorization': `Network ${this.networkConfig.authKey}` }
    }).then(r => r.json());
    
    const currentHash = registryInfo.witness_registry_hash;
    const currentRevocationCount = registryInfo.total_revocations;
    
    // Check if registry has changed
    if (currentHash !== this.lastKnownRegistryHash || 
        currentRevocationCount > this.lastKnownRevocationCount) {
      
      console.log('📋 Witness registry changed, syncing revocations');
      
      // Sync new revocations only (efficient)
      await this.syncIncrementalRevocations(this.lastKnownRevocationCount);
      
      // Update tracking
      this.lastKnownRegistryHash = currentHash;
      this.lastKnownRevocationCount = currentRevocationCount;
      
      // Trigger immediate re-validation
      await this.revalidateAllCredentials();
      
      return true;
    }
    
    return false;
    
  } catch (error) {
    console.error('Failed to check registry updates:', error);
    return false;
  }
}
```

---

## ⚡ **Performance Optimization**

### **Incremental Sync** (Instead of Full Registry Downloads)
```javascript
async syncIncrementalRevocations(since_count) {
  const response = await fetch(`${this.networkConfig.registryUrl}/api/network/revocations-since?count=${since_count}`, {
    headers: { 'Authorization': `Network ${this.networkConfig.authKey}` }
  });
  
  const newRevocations = await response.json();
  
  // Add only new revocations to bloom filter
  for (const revocation of newRevocations.revocations) {
    this.revocationBloomFilter.add(revocation.credential_id);
    this.revocationBloomFilter.add(revocation.oprf_evaluation);
  }
  
  console.log(`🔄 Synced ${newRevocations.revocations.length} new revocations`);
}
```

### **Batch Credential Validation**
```javascript
async revalidateAllCredentials() {
  const allCredentials = await this.getAllStoredCredentials();
  
  // Batch check for efficiency
  const validationPromises = allCredentials.map(async (cred) => {
    const isRevoked = await this.isCredentialRevoked(cred);
    if (isRevoked) {
      await this.removeCredential(cred.id);
      return { id: cred.id, status: 'revoked' };
    }
    return { id: cred.id, status: 'valid' };
  });
  
  const results = await Promise.all(validationPromises);
  const revokedCount = results.filter(r => r.status === 'revoked').length;
  
  if (revokedCount > 0) {
    console.log(`🚫 Found and removed ${revokedCount} revoked credentials`);
    this.notifyRevocationUpdate({ revoked_count: revokedCount });
  }
}
```

---

## 🎯 **Implementation Priority**

### **High Priority** (Implement First)
1. ✅ **Registry Change Detection** - Efficient polling with hash comparison
2. ✅ **Enhanced Background Sync** - Immediate revalidation on registry updates
3. ✅ **Incremental Revocation Sync** - Only download new revocations

### **Medium Priority** (Next Phase)
4. 🔄 **WebSocket Push Infrastructure** - Real-time push for critical updates
5. 🔄 **Priority-Based Handling** - Different response times based on severity
6. 🔄 **Acknowledgment System** - Ensure critical updates are received

### **Low Priority** (Future Enhancement)
7. ⏳ **Advanced Analytics** - Revocation propagation metrics
8. ⏳ **Fallback Strategies** - Multiple redundant communication channels

---

## 🔍 **Testing Strategy**

### **Revocation Propagation Test**
```javascript
// Test script for measuring revocation propagation time
async function testRevocationPropagation() {
  const startTime = Date.now();
  
  // 1. Trigger revocation on server
  await fetch('/api/sdk/revoke-credential', {
    method: 'POST',
    headers: { 'Authorization': 'Bearer test-key' },
    body: JSON.stringify({ credential_ids: ['test_credential_123'] })
  });
  
  // 2. Poll client until revocation is detected
  let detected = false;
  while (!detected && (Date.now() - startTime) < 30000) { // 30 second timeout
    detected = await lemmaWallet.isCredentialRevoked({ id: 'test_credential_123' });
    if (!detected) {
      await new Promise(resolve => setTimeout(resolve, 100)); // 100ms polling
    }
  }
  
  const propagationTime = Date.now() - startTime;
  console.log(`🕒 Revocation propagation time: ${propagationTime}ms`);
  
  return propagationTime;
}
```

---

## 📊 **Success Metrics**

### **Target Performance**
- **Critical Revocations**: < 5 seconds propagation
- **High Priority**: < 15 seconds propagation  
- **Medium Priority**: < 60 seconds propagation
- **Network Efficiency**: < 100KB data transfer per sync
- **Battery Impact**: < 1% additional battery drain per hour

### **Monitoring**
```javascript
// Client-side performance tracking
window.lemmaMetrics = {
  revocation_checks: {
    total_checks: 0,
    avg_check_time_ms: 0,
    last_registry_sync: 0,
    propagation_times: []
  }
};
```

---

## ✅ **Conclusion**

**Recommended Implementation**: **Hybrid Push-Pull with Registry Change Detection**

This approach provides:
- ⚡ **Immediate response** for critical security incidents (push)
- 🔄 **Efficient regular updates** with registry change detection (pull)
- 🛡️ **Redundancy** through multiple communication channels
- 📈 **Scalability** with incremental sync and batch processing
- 🔋 **Battery efficiency** with intelligent polling intervals

The system will achieve **sub-5-second** revocation propagation for critical incidents while maintaining efficient background sync for regular updates.
