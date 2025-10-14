/**
 * Network Partition Handling for Lemma Client
 * 
 * Provides graceful degradation and sync strategies for offline scenarios
 */

class LemmaNetworkPartitionHandler {
    constructor(config = {}) {
        this.config = {
            riskLevel: config.riskLevel || 'medium',
            maxFilterAgeDays: config.maxFilterAgeDays || 7,
            syncFrequencyHours: config.syncFrequencyHours || 24,
            allowStaleVerification: config.allowStaleVerification !== false,
            ...config
        };
        
        this.lastSync = parseInt(localStorage.getItem('lemma_last_sync') || '0');
        this.currentFilterVersion = parseInt(localStorage.getItem('lemma_filter_version') || '0');
        this.syncFailures = 0;
        this.maxSyncFailures = 5;
    }
    
    /**
     * Check filter freshness
     */
    getFilterFreshness() {
        const ageSeconds = (Date.now() - this.lastSync) / 1000;
        const ageDays = ageSeconds / 86400;
        
        if (ageDays < 1) return 'fresh';
        if (ageDays < 7) return 'acceptable';
        if (ageDays < 30) return 'stale';
        return 'expired';
    }
    
    /**
     * Check if verification is allowed
     */
    checkVerificationAllowed() {
        const ageSeconds = (Date.now() - this.lastSync) / 1000;
        const maxAgeSeconds = this.config.maxFilterAgeDays * 86400;
        
        if (ageSeconds > maxAgeSeconds) {
            if (this.config.allowStaleVerification) {
                return {
                    allowed: true,
                    warning: `Bloom filter is ${Math.floor(ageSeconds / 86400)} days old`,
                    filterAgeDays: Math.floor(ageSeconds / 86400)
                };
            } else {
                return {
                    allowed: false,
                    reason: 'Bloom filter too old, sync required',
                    requiredAction: 'Sync bloom filter from server'
                };
            }
        }
        
        return { allowed: true };
    }
    
    /**
     * Check if sync is needed
     */
    shouldSync() {
        const ageHours = (Date.now() - this.lastSync) / (1000 * 3600);
        return ageHours > this.config.syncFrequencyHours;
    }
    
    /**
     * Sync bloom filter with exponential backoff
     */
    async syncBloomFilter() {
        if (this.syncFailures >= this.maxSyncFailures) {
            console.warn(`Too many sync failures (${this.syncFailures}), giving up`);
            throw new Error('Max sync failures exceeded');
        }
        
        try {
            const response = await fetch('/api/v1/oprf/bloom-filter', {
                headers: {
                    'X-API-Key': this.config.apiKey
                }
            });
            
            if (!response.ok) {
                throw new Error(`Sync failed: ${response.status}`);
            }
            
            const envelope = await response.json();
            
            // Validate envelope
            await this.validateEnvelope(envelope);
            
            // Store envelope
            this.storeEnvelope(envelope);
            
            // Update sync time
            this.lastSync = Date.now();
            localStorage.setItem('lemma_last_sync', this.lastSync.toString());
            
            // Reset failure counter
            this.syncFailures = 0;
            
            console.log(`✅ Bloom filter synced: v${envelope.version}`);
            return envelope;
            
        } catch (error) {
            this.syncFailures++;
            
            // Exponential backoff
            const backoffMs = Math.min(1000 * Math.pow(2, this.syncFailures), 60000);
            console.warn(`Sync failed, retry in ${backoffMs}ms:`, error);
            
            throw error;
        }
    }
    
    /**
     * Validate bloom filter envelope
     */
    async validateEnvelope(envelope) {
        // 1. Check signature (simplified - would use real crypto)
        if (!envelope.signature) {
            throw new Error('Missing signature');
        }
        
        // 2. Check temporal bounds
        const now = Date.now() / 1000;
        if (now < envelope.valid_from) {
            throw new Error('Envelope not yet valid');
        }
        if (now > envelope.valid_until) {
            throw new Error('Envelope expired');
        }
        
        // 3. Check version sequence
        if (envelope.version <= this.currentFilterVersion) {
            throw new Error('Downgrade attempt detected');
        }
        
        // 4. Validate chain (if not first)
        if (this.currentFilterVersion > 0) {
            const previousEnvelope = this.loadEnvelope(this.currentFilterVersion);
            if (previousEnvelope) {
                await this.validateChain(envelope, previousEnvelope);
            }
        }
        
        return true;
    }
    
    /**
     * Validate version chain
     */
    async validateChain(newEnvelope, previousEnvelope) {
        // Check version increment
        if (newEnvelope.version !== previousEnvelope.version + 1) {
            throw new Error('Version gap detected');
        }
        
        // Check previous hash matches
        if (newEnvelope.previous_version_hash !== previousEnvelope.content_hash) {
            throw new Error('Chain broken - hash mismatch');
        }
        
        // Check timestamp ordering
        if (newEnvelope.created_at <= previousEnvelope.created_at) {
            throw new Error('Invalid timestamp ordering');
        }
    }
    
    /**
     * Store envelope
     */
    storeEnvelope(envelope) {
        localStorage.setItem(`lemma_envelope_${envelope.version}`, JSON.stringify(envelope));
        localStorage.setItem('lemma_filter_version', envelope.version.toString());
        this.currentFilterVersion = envelope.version;
    }
    
    /**
     * Load envelope by version
     */
    loadEnvelope(version) {
        const stored = localStorage.getItem(`lemma_envelope_${version}`);
        return stored ? JSON.parse(stored) : null;
    }
    
    /**
     * Verify credential with partition handling
     */
    async verifyWithPartitionHandling(credential) {
        // 1. Check if verification allowed
        const decision = this.checkVerificationAllowed();
        
        if (!decision.allowed) {
            // Try to sync
            try {
                await this.syncBloomFilter();
                // Retry verification after sync
                return this.verifyCredential(credential);
            } catch (syncError) {
                // Sync failed, honor the deny decision
                throw new Error(decision.reason);
            }
        }
        
        // 2. Opportunistic sync if needed
        if (this.shouldSync() && navigator.onLine) {
            // Don't block on sync, do it in background
            this.syncBloomFilter().catch(err => {
                console.warn('Background sync failed:', err);
            });
        }
        
        // 3. Perform verification
        const result = await this.verifyCredential(credential);
        
        // 4. Add warning if filter is stale
        if (decision.warning) {
            result.warning = decision.warning;
        }
        
        return result;
    }
    
    /**
     * Verify credential (actual verification logic)
     */
    async verifyCredential(credential) {
        // Placeholder - would integrate with actual verification
        return {
            verified: true,
            timestamp: Date.now()
        };
    }
}

/**
 * Pre-configured handlers for different risk levels
 */
class LemmaPartitionHandlers {
    static lowRisk(apiKey) {
        return new LemmaNetworkPartitionHandler({
            apiKey,
            riskLevel: 'low',
            maxFilterAgeDays: 30,
            syncFrequencyHours: 72,
            allowStaleVerification: true
        });
    }
    
    static mediumRisk(apiKey) {
        return new LemmaNetworkPartitionHandler({
            apiKey,
            riskLevel: 'medium',
            maxFilterAgeDays: 7,
            syncFrequencyHours: 24,
            allowStaleVerification: false
        });
    }
    
    static highRisk(apiKey) {
        return new LemmaNetworkPartitionHandler({
            apiKey,
            riskLevel: 'high',
            maxFilterAgeDays: 1,
            syncFrequencyHours: 1,
            allowStaleVerification: false,
            requireStrictSync: true
        });
    }
}

// Export for use in browser
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { LemmaNetworkPartitionHandler, LemmaPartitionHandlers };
}

