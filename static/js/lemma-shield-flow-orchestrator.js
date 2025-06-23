/**
 * Lemma Shield Flow Orchestrator
 * Coordinates the three main flows: Check, Bot Shield, and Revocation
 * Handles credential list updates and cross-site synchronization
 */

class LemmaShieldFlowOrchestrator {
    constructor(options = {}) {
        this.options = {
            apiBase: options.apiBase || '',
            updateInterval: options.updateInterval || 30000, // 30 seconds
            onFlowChange: options.onFlowChange || (() => {}),
            onCredentialUpdate: options.onCredentialUpdate || (() => {}),
            debug: options.debug || false,
            ...options
        };

        this.state = {
            currentFlow: 'check', // check, shield, revocation
            credentialStatus: 'unknown', // valid, invalid, revoked, missing
            lastCheck: 0,
            updateInProgress: false,
            credentialListVersion: 0
        };

        this.wallet = null;
        this.shieldWidget = null;
        this.credentialCache = new Map();
        this.revocationList = new Set();

        this.init();
    }

    async init() {
        this.log('🚀 Initializing Lemma Shield Flow Orchestrator');
        
        // Wait for dependencies
        await this.waitForDependencies();
        
        // Initialize event listeners
        this.setupEventListeners();
        
        // Start the main flow
        await this.executeFlow();
        
        // Start periodic updates
        this.startPeriodicUpdates();
        
        this.log('✅ Flow Orchestrator initialized');
    }

    async waitForDependencies() {
        return new Promise((resolve) => {
            const checkDependencies = () => {
                // Wait for wallet
                if (window.lemmaBackgroundWallet) {
                    this.wallet = window.lemmaBackgroundWallet;
                } else if (window.lemmaWallet) {
                    this.wallet = window.lemmaWallet;
                }

                // Wait for shield widget
                if (window.LemmaShieldWidget?.instance) {
                    this.shieldWidget = window.LemmaShieldWidget.instance;
                }

                if (this.wallet && this.shieldWidget) {
                    resolve();
                } else {
                    setTimeout(checkDependencies, 100);
                }
            };
            checkDependencies();
        });
    }

    setupEventListeners() {
        // Listen for credential events
        window.addEventListener('lemma-credential-revoked', (event) => {
            this.handleCredentialRevoked(event.detail);
        });

        window.addEventListener('lemma-credential-updated', (event) => {
            this.handleCredentialUpdated(event.detail);
        });

        window.addEventListener('lemma-shield-required', (event) => {
            this.handleShieldRequired(event.detail);
        });

        window.addEventListener('lemma-flow-ready', (event) => {
            this.executeFlow();
        });

        // Listen for network updates
        window.addEventListener('lemma-network-update', (event) => {
            this.handleNetworkUpdate(event.detail);
        });
    }

    async executeFlow() {
        this.log('🔄 Executing main flow');

        try {
            // FLOW 1: CHECK - Detect if user has credential and verify
            const checkResult = await this.executeCheckFlow();
            
            if (checkResult.hasValidCredential) {
                this.log('✅ Check flow passed - user has valid credential');
                this.state.currentFlow = 'verified';
                this.state.credentialStatus = 'valid';
                this.hideShield();
                return;
            }

            if (checkResult.hasRevokedCredential) {
                this.log('❌ Check flow detected revoked credential - triggering revocation flow');
                await this.executeRevocationFlow(checkResult.credentialId);
                return;
            }

            // FLOW 2: BOT SHIELD - Show shield for verification
            this.log('🛡️ No valid credential found - triggering bot shield flow');
            await this.executeBotShieldFlow();

        } catch (error) {
            this.log('❌ Flow execution error:', error);
            // Fallback to showing shield
            await this.executeBotShieldFlow();
        }
    }

    async executeCheckFlow() {
        this.log('🔍 Executing CHECK flow');
        this.state.currentFlow = 'check';

        try {
            // Step 1: Check for credentials in wallet
            const credentials = await this.wallet.getCredentials();
            
            if (!credentials || credentials.length === 0) {
                this.log('ℹ️ No credentials found in wallet');
                return { hasValidCredential: false, hasRevokedCredential: false };
            }

            // Step 2: Check each credential
            for (const credential of credentials) {
                const checkResult = await this.checkSingleCredential(credential);
                
                if (checkResult.valid) {
                    this.log(`✅ Valid credential found: ${credential.id}`);
                    return { 
                        hasValidCredential: true, 
                        credentialId: credential.id,
                        credential: credential
                    };
                }

                if (checkResult.revoked) {
                    this.log(`❌ Revoked credential found: ${credential.id}`);
                    return { 
                        hasRevokedCredential: true, 
                        credentialId: credential.id,
                        credential: credential
                    };
                }
            }

            return { hasValidCredential: false, hasRevokedCredential: false };

        } catch (error) {
            this.log('❌ Check flow error:', error);
            return { hasValidCredential: false, hasRevokedCredential: false };
        }
    }

    async checkSingleCredential(credential) {
        try {
            // Step 1: Check offline first (if supported)
            if (credential.offline_capable) {
                this.log(`🔒 Checking credential ${credential.id} offline`);
                const offlineResult = await this.checkCredentialOffline(credential);
                
                if (offlineResult.valid) {
                    this.log('✅ Offline verification successful');
                    return { valid: true, method: 'offline' };
                }

                if (offlineResult.revoked) {
                    this.log('❌ Offline verification detected revocation');
                    return { revoked: true, method: 'offline' };
                }

                if (offlineResult.syncRequired) {
                    this.log('🔄 Offline verification requires sync - falling back to online');
                    // Fall through to online check
                }
            }

            // Step 2: Check online (API call)
            this.log(`🌐 Checking credential ${credential.id} online`);
            const onlineResult = await this.checkCredentialOnline(credential);
            
            return {
                valid: onlineResult.verified && !onlineResult.revoked,
                revoked: onlineResult.revoked,
                method: 'online',
                details: onlineResult
            };

        } catch (error) {
            this.log(`❌ Credential check error for ${credential.id}:`, error);
            return { valid: false, revoked: false, error: error.message };
        }
    }

    async checkCredentialOffline(credential) {
        try {
            const response = await fetch('/api/verify-offline', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    credential: credential,
                    credential_id: credential.id
                })
            });

            const result = await response.json();
            
            return {
                valid: result.success && result.verified && !result.revoked,
                revoked: result.revoked,
                syncRequired: result.sync_required || false,
                details: result
            };

        } catch (error) {
            this.log('❌ Offline check error:', error);
            return { valid: false, revoked: false, syncRequired: true };
        }
    }

    async checkCredentialOnline(credential) {
        try {
            const response = await fetch('/api/shield/status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    credentials: [{ id: credential.id }],
                    check_revocation: true,
                    comprehensive_check: true
                })
            });

            const result = await response.json();
            
            // Also verify the credential directly
            const verifyResponse = await fetch('/api/verify-credential', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    credential: credential,
                    challenge: `check_${Date.now()}`
                })
            });

            const verifyResult = await verifyResponse.json();

            return {
                verified: verifyResult.verified || false,
                revoked: result.revoked_count > 0 || verifyResult.revoked || false,
                shield_action: result.shield_action,
                details: { statusResult: result, verifyResult: verifyResult }
            };

        } catch (error) {
            this.log('❌ Online check error:', error);
            return { verified: false, revoked: false };
        }
    }

    async executeBotShieldFlow() {
        this.log('🛡️ Executing BOT SHIELD flow');
        this.state.currentFlow = 'shield';

        try {
            // Show the shield widget
            if (this.shieldWidget) {
                await this.shieldWidget.showVerificationWidget();
                this.log('✅ Shield widget displayed');
            } else {
                this.log('⚠️ No shield widget available - creating fallback');
                this.createFallbackShield();
            }

            // Listen for verification completion
            const verificationPromise = new Promise((resolve) => {
                const handler = (event) => {
                    if (event.detail.verified) {
                        window.removeEventListener('lemma-verification-complete', handler);
                        resolve(event.detail);
                    }
                };
                window.addEventListener('lemma-verification-complete', handler);
            });

            const verificationResult = await verificationPromise;
            this.log('✅ Bot shield verification completed:', verificationResult);

            // Store the new credential
            if (verificationResult.credential) {
                await this.wallet.storeCredential(verificationResult.credential);
                this.log('✅ New credential stored in wallet');
            }

            // Hide shield and grant access
            this.hideShield();
            this.state.currentFlow = 'verified';
            this.state.credentialStatus = 'valid';

        } catch (error) {
            this.log('❌ Bot shield flow error:', error);
            throw error;
        }
    }

    async executeRevocationFlow(credentialId) {
        this.log('🚫 Executing REVOCATION flow for credential:', credentialId);
        this.state.currentFlow = 'revocation';

        try {
            // Step 1: Mark credential as revoked in OPRF cascade
            await this.markCredentialRevoked(credentialId);

            // Step 2: Clear credential from local wallet
            if (this.wallet) {
                await this.wallet.removeCredential(credentialId);
                this.log('✅ Revoked credential removed from wallet');
            }

            // Step 3: Clear from local storage
            this.addToLocalRevocationList(credentialId);

            // Step 4: Notify network of revocation
            await this.notifyNetworkRevocation(credentialId);

            // Step 5: Force shield to reappear
            await this.executeBotShieldFlow();

            this.log('✅ Revocation flow completed');

        } catch (error) {
            this.log('❌ Revocation flow error:', error);
            // Still try to show shield even if revocation fails
            await this.executeBotShieldFlow();
        }
    }

    async markCredentialRevoked(credentialId) {
        try {
            const response = await fetch('/api/shield/revoke-credential', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    credential_id: credentialId,
                    reason: 'Automatic revocation flow',
                    revoked_by: 'orchestrator'
                })
            });

            const result = await response.json();
            this.log('✅ Credential marked as revoked in system:', result);
            return result;

        } catch (error) {
            this.log('❌ Failed to mark credential as revoked:', error);
            throw error;
        }
    }

    addToLocalRevocationList(credentialId) {
        this.revocationList.add(credentialId);
        
        // Update localStorage
        const revokedCredentials = JSON.parse(localStorage.getItem('lemma_revoked_credentials') || '[]');
        if (!revokedCredentials.includes(credentialId)) {
            revokedCredentials.push(credentialId);
            localStorage.setItem('lemma_revoked_credentials', JSON.stringify(revokedCredentials));
        }

        this.log('✅ Added credential to local revocation list');
    }

    async notifyNetworkRevocation(credentialId) {
        try {
            // Notify other integrated sites about the revocation
            const event = new CustomEvent('lemma-credential-revoked', {
                detail: {
                    credential_id: credentialId,
                    timestamp: new Date().toISOString(),
                    source: 'orchestrator'
                }
            });
            window.dispatchEvent(event);

            // Also try to sync with network
            await this.syncWithNetwork();

            this.log('✅ Network notified of revocation');

        } catch (error) {
            this.log('❌ Failed to notify network:', error);
        }
    }

    async syncWithNetwork() {
        if (this.state.updateInProgress) {
            this.log('⏭️ Update already in progress, skipping');
            return;
        }

        this.state.updateInProgress = true;

        try {
            // Fetch latest credential list from server
            const response = await fetch('/api/network/sync', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    version: this.state.credentialListVersion,
                    force: false
                })
            });

            if (response.ok) {
                const result = await response.json();
                this.log('✅ Network sync completed:', result);
                
                // Update local revocation list if needed
                if (result.revoked_credentials) {
                    this.updateLocalRevocationList(result.revoked_credentials);
                }

                this.state.credentialListVersion = result.version || this.state.credentialListVersion + 1;
            }

        } catch (error) {
            this.log('❌ Network sync error:', error);
        } finally {
            this.state.updateInProgress = false;
        }
    }

    updateLocalRevocationList(revokedCredentials) {
        let updated = false;
        
        for (const credId of revokedCredentials) {
            if (!this.revocationList.has(credId)) {
                this.revocationList.add(credId);
                updated = true;
            }
        }

        if (updated) {
            localStorage.setItem('lemma_revoked_credentials', JSON.stringify([...this.revocationList]));
            this.log('✅ Local revocation list updated');
            
            // Trigger re-check of current credentials
            this.executeFlow();
        }
    }

    hideShield() {
        if (this.shieldWidget) {
            this.shieldWidget.hideShield();
        }

        // Hide any fallback shields
        const fallbackShields = document.querySelectorAll('.lemma-fallback-shield');
        fallbackShields.forEach(shield => shield.remove());

        this.log('✅ Shield hidden');
    }

    createFallbackShield() {
        const shield = document.createElement('div');
        shield.className = 'lemma-fallback-shield';
        shield.innerHTML = `
            <div style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 10000; display: flex; align-items: center; justify-content: center;">
                <div style="background: white; padding: 2rem; border-radius: 8px; max-width: 400px; text-align: center;">
                    <h3>🛡️ Verification Required</h3>
                    <p>Please verify your identity to continue.</p>
                    <button onclick="window.location.href='/join-network'" style="background: #007cba; color: white; border: none; padding: 12px 24px; border-radius: 4px; cursor: pointer;">
                        Verify Identity
                    </button>
                </div>
            </div>
        `;
        document.body.appendChild(shield);
    }

    startPeriodicUpdates() {
        setInterval(() => {
            this.syncWithNetwork();
        }, this.options.updateInterval);

        this.log(`🔄 Started periodic updates (${this.options.updateInterval}ms)`);
    }

    // Event handlers
    handleCredentialRevoked(detail) {
        this.log('🚨 Credential revocation event received:', detail);
        if (detail.credential_id) {
            this.addToLocalRevocationList(detail.credential_id);
            this.executeFlow(); // Re-run flow to handle revocation
        }
    }

    handleCredentialUpdated(detail) {
        this.log('🔄 Credential update event received:', detail);
        this.executeFlow(); // Re-run flow to check new credential
    }

    handleShieldRequired(detail) {
        this.log('🛡️ Shield required event received:', detail);
        this.executeBotShieldFlow();
    }

    handleNetworkUpdate(detail) {
        this.log('🌐 Network update event received:', detail);
        if (detail.revoked_credentials) {
            this.updateLocalRevocationList(detail.revoked_credentials);
        }
    }

    log(message, ...args) {
        if (this.options.debug) {
            console.log(`[ORCHESTRATOR] ${message}`, ...args);
        }
    }

    // Public API methods
    async forceRecheck() {
        this.log('🔄 Force recheck requested');
        await this.executeFlow();
    }

    async forceShield() {
        this.log('🛡️ Force shield requested');
        await this.executeBotShieldFlow();
    }

    getState() {
        return { ...this.state };
    }

    static getInstance(options) {
        if (!window.lemmaFlowOrchestrator) {
            window.lemmaFlowOrchestrator = new LemmaShieldFlowOrchestrator(options);
        }
        return window.lemmaFlowOrchestrator;
    }
}

// Auto-initialize if not in test environment
if (typeof window !== 'undefined' && !window.testMode) {
    document.addEventListener('DOMContentLoaded', () => {
        LemmaShieldFlowOrchestrator.getInstance({ debug: true });
    });
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaShieldFlowOrchestrator;
} 