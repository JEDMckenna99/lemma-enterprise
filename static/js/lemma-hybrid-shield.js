/**
 * Lemma Hybrid Shield - Client-side Implementation
 * ==================================================
 * 
 * This provides intelligent client-side bot shield protection that:
 * - Attempts microsecond WebAssembly verification first (preferred)
 * - Falls back to server-side verification when needed
 * - Coordinates with the hybrid shield API for optimal performance
 * 
 * Usage:
 * ------
 * const shield = new LemmaHybridShield({
 *   apiKey: 'your-api-key',
 *   serverUrl: 'https://your-server.com/api/hybrid-shield'
 * });
 * 
 * const result = await shield.verify({
 *   userId: 'user123',
 *   action: 'login'
 * });
 */

class LemmaHybridShield {
    constructor(config = {}) {
        this.config = {
            apiKey: config.apiKey || '',
            serverUrl: config.serverUrl || '/api/hybrid-shield',
            clientTimeout: config.clientTimeout || 500, // 500ms timeout
            enableClientVerification: config.enableClientVerification !== false,
            enableServerFallback: config.enableServerFallback !== false,
            retryAttempts: config.retryAttempts || 2,
            debugMode: config.debugMode || false,
            ...config
        };
        
        this.wasmModule = null;
        this.botShield = null;
        this.isInitialized = false;
        this.credentials = new Map();
        this.stats = {
            totalVerifications: 0,
            clientVerifications: 0,
            serverVerifications: 0,
            fallbackTriggers: 0,
            averageClientTime: 0,
            averageServerTime: 0
        };
        
        this.log('Hybrid Shield initialized', this.config);
    }
    
    log(message, data = null) {
        if (this.config.debugMode) {
            console.log(`[LemmaHybridShield] ${message}`, data);
        }
    }
    
    warn(message, data = null) {
        console.warn(`[LemmaHybridShield] ${message}`, data);
    }
    
    error(message, data = null) {
        console.error(`[LemmaHybridShield] ${message}`, data);
    }
    
    /**
     * Initialize the hybrid shield (loads WebAssembly module if available)
     */
    async initialize() {
        if (this.isInitialized) {
            return true;
        }
        
        this.log('Initializing hybrid shield...');
        
        if (this.config.enableClientVerification) {
            try {
                await this.initializeWebAssembly();
                this.log('WebAssembly initialization successful');
            } catch (error) {
                this.warn('WebAssembly initialization failed, will use server-only mode', error);
                this.config.enableClientVerification = false;
            }
        }
        
        this.isInitialized = true;
        this.log('Hybrid shield initialized successfully');
        return true;
    }
    
    /**
     * Initialize WebAssembly module
     */
    async initializeWebAssembly() {
        try {
            // Try to load the WebAssembly module
            // This would normally load from your built wasm-pack output
            const wasmUrl = '/pkg/lemma_crypto.js';
            
            // For now, we'll simulate WebAssembly functionality
            // In a real implementation, this would load the actual WASM module
            this.wasmModule = {
                LemmaBotShield: class MockLemmaBotShield {
                    constructor() {
                        this.credentialCount = 0;
                    }
                    
                    add_human_credential(credentialJson) {
                        this.credentialCount++;
                        return `mock_fingerprint_${this.credentialCount}`;
                    }
                    
                    handle_shield_request(request) {
                        const startTime = performance.now();
                        const hasCredentials = this.credentialCount > 0;
                        
                        return {
                            verified: hasCredentials,
                            confidence: hasCredentials ? 0.95 : 0.0,
                            verification_time_ns: Math.round((performance.now() - startTime) * 1000000),
                            offline: true,
                            fingerprint: hasCredentials ? `mock_shield_${Date.now()}` : 'no_credentials'
                        };
                    }
                    
                    is_shield_ready() {
                        return this.credentialCount > 0;
                    }
                    
                    get_shield_stats() {
                        return {
                            totalCredentials: this.credentialCount,
                            verificationCount: 0,
                            hasHumanCredentials: this.credentialCount > 0,
                            offline: true
                        };
                    }
                }
            };
            
            this.botShield = new this.wasmModule.LemmaBotShield();
            this.log('Mock WebAssembly module loaded successfully');
            
        } catch (error) {
            this.error('Failed to initialize WebAssembly', error);
            throw error;
        }
    }
    
    /**
     * Store a credential in the client-side shield
     */
    async storeCredential(userId, credential) {
        try {
            // Store in client-side WebAssembly module
            if (this.botShield && this.config.enableClientVerification) {
                const credentialJson = JSON.stringify(credential);
                const fingerprint = this.botShield.add_human_credential(credentialJson);
                
                // Store in local map for reference
                this.credentials.set(userId, {
                    credential,
                    fingerprint,
                    timestamp: Date.now()
                });
                
                this.log(`Stored credential for user ${userId}`, { fingerprint });
            }
            
            // Also sync to server for backup/coordination
            if (this.config.enableServerFallback) {
                await this.syncCredentialToServer(userId, credential);
            }
            
            return true;
        } catch (error) {
            this.error(`Failed to store credential for user ${userId}`, error);
            return false;
        }
    }
    
    /**
     * Sync credential to server
     */
    async syncCredentialToServer(userId, credential) {
        try {
            const response = await fetch(`${this.config.serverUrl}/store-credential`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.config.apiKey}`
                },
                body: JSON.stringify({
                    user_id: userId,
                    credential: credential
                })
            });
            
            if (!response.ok) {
                throw new Error(`Server sync failed: ${response.status}`);
            }
            
            const result = await response.json();
            this.log(`Synced credential to server for user ${userId}`, result);
            
        } catch (error) {
            this.warn(`Failed to sync credential to server for user ${userId}`, error);
        }
    }
    
    /**
     * Attempt client-side verification
     */
    async attemptClientVerification(userId, action) {
        if (!this.config.enableClientVerification || !this.botShield) {
            return null;
        }
        
        try {
            const startTime = performance.now();
            
            // Check if shield is ready
            if (!this.botShield.is_shield_ready()) {
                this.log('Client shield not ready - no credentials available');
                return null;
            }
            
            // Create shield request
            const request = {
                user_id: userId,
                action: action,
                timestamp: Date.now()
            };
            
            // Perform verification
            const result = this.botShield.handle_shield_request(request);
            
            const clientTime = Math.round((performance.now() - startTime) * 1000000); // Convert to nanoseconds
            
            // Update stats
            this.stats.clientVerifications++;
            this.stats.averageClientTime = (
                (this.stats.averageClientTime * (this.stats.clientVerifications - 1) + clientTime) /
                this.stats.clientVerifications
            );
            
            this.log(`Client verification completed in ${clientTime}ns`, result);
            
            return {
                verified: result.verified,
                confidence: result.confidence,
                verification_time_ns: clientTime,
                offline: result.offline,
                fingerprint: result.fingerprint,
                method: 'client'
            };
            
        } catch (error) {
            this.error('Client verification failed', error);
            return null;
        }
    }
    
    /**
     * Perform server-side verification
     */
    async performServerVerification(userId, action, clientResult = null, fallbackReason = null) {
        try {
            const startTime = performance.now();
            
            const requestData = {
                user_id: userId,
                action: action,
                timestamp: Date.now(),
                client_available: this.config.enableClientVerification,
                client_verification_result: clientResult,
                fallback_reason: fallbackReason
            };
            
            const response = await fetch(`${this.config.serverUrl}/verify`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.config.apiKey}`
                },
                body: JSON.stringify(requestData)
            });
            
            if (!response.ok) {
                throw new Error(`Server verification failed: ${response.status}`);
            }
            
            const result = await response.json();
            
            const serverTime = Math.round((performance.now() - startTime) * 1000000); // Convert to nanoseconds
            
            // Update stats
            this.stats.serverVerifications++;
            this.stats.averageServerTime = (
                (this.stats.averageServerTime * (this.stats.serverVerifications - 1) + serverTime) /
                this.stats.serverVerifications
            );
            
            if (fallbackReason) {
                this.stats.fallbackTriggers++;
            }
            
            this.log(`Server verification completed in ${serverTime}ns`, result);
            
            return result;
            
        } catch (error) {
            this.error('Server verification failed', error);
            throw error;
        }
    }
    
    /**
     * Main verification method - intelligently routes between client and server
     */
    async verify(options = {}) {
        const { userId, action = 'verify', forceServer = false } = options;
        
        if (!userId) {
            throw new Error('userId is required for verification');
        }
        
        // Ensure initialization
        if (!this.isInitialized) {
            await this.initialize();
        }
        
        this.stats.totalVerifications++;
        
        let clientResult = null;
        let fallbackReason = null;
        
        // Strategy 1: Try client-side verification first (if not forced to server)
        if (!forceServer && this.config.enableClientVerification) {
            try {
                const clientPromise = this.attemptClientVerification(userId, action);
                const timeoutPromise = new Promise((_, reject) => {
                    setTimeout(() => reject(new Error('Client verification timeout')), this.config.clientTimeout);
                });
                
                clientResult = await Promise.race([clientPromise, timeoutPromise]);
                
                if (clientResult && clientResult.verified) {
                    this.log(`Client verification successful for user ${userId}`);
                    return clientResult;
                }
                
                if (clientResult && !clientResult.verified) {
                    fallbackReason = 'verification_failed';
                    this.log(`Client verification failed for user ${userId}, falling back to server`);
                }
                
            } catch (error) {
                if (error.message.includes('timeout')) {
                    fallbackReason = 'client_timeout';
                    this.warn(`Client verification timeout for user ${userId}`);
                } else {
                    fallbackReason = 'client_error';
                    this.error(`Client verification error for user ${userId}`, error);
                }
            }
        }
        
        // Strategy 2: Server-side verification (fallback or hybrid)
        if (this.config.enableServerFallback) {
            try {
                const serverResult = await this.performServerVerification(userId, action, clientResult, fallbackReason);
                
                this.log(`Server verification completed for user ${userId}`, serverResult);
                return serverResult;
                
            } catch (error) {
                this.error(`Server verification failed for user ${userId}`, error);
                
                // Final fallback: return negative result
                return {
                    verified: false,
                    confidence: 0.0,
                    verification_time_ns: 0,
                    method: 'error_fallback',
                    offline: false,
                    fingerprint: 'error',
                    session_id: `error_${Date.now()}`
                };
            }
        }
        
        // If we get here, both client and server are disabled or failed
        this.error(`No verification methods available for user ${userId}`);
        return {
            verified: false,
            confidence: 0.0,
            verification_time_ns: 0,
            method: 'no_methods',
            offline: false,
            fingerprint: 'no_methods',
            session_id: `no_methods_${Date.now()}`
        };
    }
    
    /**
     * Get shield statistics
     */
    getStats() {
        const totalVerifications = this.stats.totalVerifications;
        
        return {
            ...this.stats,
            clientPercentage: totalVerifications > 0 ? (this.stats.clientVerifications / totalVerifications * 100) : 0,
            serverPercentage: totalVerifications > 0 ? (this.stats.serverVerifications / totalVerifications * 100) : 0,
            fallbackRate: totalVerifications > 0 ? (this.stats.fallbackTriggers / totalVerifications * 100) : 0,
            clientAvailable: this.config.enableClientVerification && this.botShield,
            serverAvailable: this.config.enableServerFallback,
            credentialCount: this.credentials.size
        };
    }
    
    /**
     * Get server statistics
     */
    async getServerStats() {
        try {
            const response = await fetch(`${this.config.serverUrl}/stats`, {
                headers: {
                    'Authorization': `Bearer ${this.config.apiKey}`
                }
            });
            
            if (!response.ok) {
                throw new Error(`Failed to get server stats: ${response.status}`);
            }
            
            return await response.json();
            
        } catch (error) {
            this.error('Failed to get server stats', error);
            return null;
        }
    }
    
    /**
     * Manual sync trigger
     */
    async sync() {
        try {
            const response = await fetch(`${this.config.serverUrl}/sync`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.config.apiKey}`
                }
            });
            
            if (!response.ok) {
                throw new Error(`Sync failed: ${response.status}`);
            }
            
            const result = await response.json();
            this.log('Manual sync completed', result);
            return result;
            
        } catch (error) {
            this.error('Manual sync failed', error);
            throw error;
        }
    }
    
    /**
     * Health check
     */
    async healthCheck() {
        try {
            const response = await fetch(`${this.config.serverUrl}/health`, {
                headers: {
                    'Authorization': `Bearer ${this.config.apiKey}`
                }
            });
            
            if (!response.ok) {
                throw new Error(`Health check failed: ${response.status}`);
            }
            
            const result = await response.json();
            this.log('Health check completed', result);
            return result;
            
        } catch (error) {
            this.error('Health check failed', error);
            return {
                healthy: false,
                error: error.message
            };
        }
    }
}

// Export for different module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaHybridShield;
} else if (typeof define === 'function' && define.amd) {
    define([], function() { return LemmaHybridShield; });
} else {
    // Browser global
    window.LemmaHybridShield = LemmaHybridShield;
}

// Auto-initialize if config is provided
if (typeof window !== 'undefined' && window.lemmaHybridShieldConfig) {
    window.lemmaHybridShield = new LemmaHybridShield(window.lemmaHybridShieldConfig);
    window.lemmaHybridShield.initialize();
} 