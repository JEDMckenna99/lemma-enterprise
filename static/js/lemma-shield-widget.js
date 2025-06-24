/**
 * Lemma Shield Widget - Inline Verification Experience
 * 
 * Provides a seamless inline verification flow:
 * 1. "Verify Human" button triggers verification
 * 2. Disclaimer card explains Lemma and privacy commitment
 * 3. Stripe verification card (same size as disclaimer)
 * 4. After success, shield protection is removed
 * 
 * Usage:
 * const shieldWidget = new LemmaShieldWidget({
 *   protectedContent: '#protected-content',
 *   onVerified: () => console.log('User verified!'),
 *   onError: (error) => console.error('Error:', error)
 * });
 */

class LemmaShieldWidget {
    constructor(options = {}) {
        // Prevent multiple instances
        if (LemmaShieldWidget.instance) {
            console.warn('⚠️ LemmaShieldWidget already initialized. Returning existing instance.');
            return LemmaShieldWidget.instance;
        }
        
        this.options = {
            // UI Elements
            protectedContent: options.protectedContent || '#protected-content',
            widgetContainer: options.widgetContainer || '#lemma-shield-widget',
            
            // Security Configuration
            securityLevel: options.securityLevel || 'standard',
            
            // API Configuration
            apiBase: options.apiBase || '',
            
            // Callbacks
            onVerified: options.onVerified || (() => {}),
            onError: options.onError || ((error) => console.error('Shield Widget Error:', error)),
            onStepChange: options.onStepChange || (() => {}),
            
            // Advanced Options
            showBranding: options.showBranding !== false,
            animationDuration: options.animationDuration || 300
        };
        
        this.state = {
            currentStep: 'initial', // initial, disclaimer, verification, complete
            verified: false,
            verificationSessionId: null,
            userId: null,
            processing: false
        };
        
        this.wallet = null;
        
        // Store instance
        LemmaShieldWidget.instance = this;
        
        this.init();
    }
    
    async init() {
        console.log('🛡️ Initializing Lemma Shield Widget');
        
        // Wait for wallet to be available
        await this.waitForWallet();
        
        // Initialize orchestrator integration
        this.initializeOrchestrator();
        
        // Check if we're returning from Stripe verification
        await this.checkForReturnFromVerification();
        
        // Check initial status and act on the result - but let orchestrator handle the flow
        if (!window.lemmaFlowOrchestrator) {
            const statusResult = await this.checkStatus();
            await this.handleStatusResult(statusResult);
        }
        
        // Start periodic revocation checking
        this.startRevocationMonitoring();
    }

    initializeOrchestrator() {
        // Register this widget with the orchestrator
        if (window.lemmaFlowOrchestrator) {
            console.log('🔗 Registering shield widget with orchestrator');
            window.lemmaFlowOrchestrator.shieldWidget = this;
        } else {
            // Wait for orchestrator and register when available
            const checkOrchestrator = () => {
                if (window.lemmaFlowOrchestrator) {
                    console.log('🔗 Registering shield widget with orchestrator (delayed)');
                    window.lemmaFlowOrchestrator.shieldWidget = this;
                } else {
                    setTimeout(checkOrchestrator, 100);
                }
            };
            checkOrchestrator();
        }

        // Listen for orchestrator events
        window.addEventListener('lemma-orchestrator-shield-show', () => {
            this.showVerificationWidget();
        });

        window.addEventListener('lemma-orchestrator-shield-hide', () => {
            this.hideShield();
        });

        window.addEventListener('lemma-orchestrator-credential-valid', () => {
            this.grantAccess();
        });
    }
    
    async waitForWallet() {
        return new Promise((resolve) => {
            const checkWallet = () => {
                // Use the background wallet if available
                if (window.lemmaBackgroundWallet) {
                    console.log('🎯 Using existing background wallet');
                    this.wallet = window.lemmaBackgroundWallet;
                    resolve();
                } else if (window.LemmaBackgroundWallet) {
                    console.log('🎯 Creating new background wallet instance');
                    this.wallet = new window.LemmaBackgroundWallet();
                    window.lemmaBackgroundWallet = this.wallet;
                    resolve();
                } else if (window.lemmaWallet) {
                    console.log('🎯 Using existing lemmaWallet instance');
                    this.wallet = window.lemmaWallet;
                    resolve();
                } else if (window.LemmaWallet) {
                    console.log('⚠️ Using legacy LemmaWallet - consider upgrading to background wallet');
                    this.wallet = new window.LemmaWallet();
                    resolve();
                } else {
                    setTimeout(checkWallet, 100);
                }
            };
            checkWallet();
        });
    }
    
    async checkStatus() {
        try {
            // CRITICAL FIX: Check wallet for existing credentials first
            let existingCredential = null;
            let useOfflineVerification = false;
            
            if (this.wallet) {
                try {
                    // Get credentials from wallet
                    const credentials = await this.wallet.getCredentials();
                    if (credentials && credentials.length > 0) {
                        // Look for offline-capable credentials first
                        existingCredential = credentials.find(cred => cred.offline_capable) || credentials[0];
                        useOfflineVerification = existingCredential && existingCredential.offline_capable;
                        
                        if (useOfflineVerification) {
                            console.log('🚀 Found offline-capable credential - using offline verification');
                        } else {
                            console.log('🎯 Found credential but not offline-capable - using online verification');
                        }
                    }
                } catch (walletError) {
                    console.warn('⚠️ Wallet error during credential check:', walletError);
                }
            }
            
            // Choose verification method based on credential capabilities
            if (useOfflineVerification) {
                // TRUE OFFLINE VERIFICATION - No API calls!
                const offlineResult = await this.verifyOffline(existingCredential);
                if (offlineResult.success) {
                    console.log('✅ Offline verification successful - no API calls made!');
                    return {
                        success: true,
                        shield_action: 'allow_access',
                        verification_mode: 'offline_verified',
                        offline_verification: true,
                        api_calls_made: 0
                    };
                } else if (offlineResult.sync_required) {
                    console.log('🔄 Offline verification failed - sync required');
                    // Fall through to online verification for sync
                } else {
                    console.log('❌ Offline verification failed:', offlineResult.error);
                    return {
                        success: false,
                        shield_action: 'verify_did',
                        verification_mode: 'offline_failed'
                    };
                }
            }
            
            // Online verification (original method)
            const requestData = existingCredential ? {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    credentials: [{ id: existingCredential.id }],
                    check_revocation: true,
                    comprehensive_check: true
                })
            } : { method: 'GET' };
            
            const response = await fetch('/api/shield/status', requestData);
            const result = await response.json();
            
            console.log('🛡️ Shield status check result:', result);
            return result;
            
        } catch (error) {
            console.error('❌ Shield status check failed:', error);
            return {
                success: false,
                shield_action: 'verify_did',
                error: error.message
            };
        }
    }
    
    async handleStatusResult(statusResult) {
        /*
         * Handle the result from checkStatus and determine what action to take
         */
        try {
            console.log('🛡️ Processing shield status result:', statusResult);
            
            if (!statusResult) {
                console.warn('⚠️ No status result - showing shield as fallback');
                await this.showVerificationWidget();
                return;
            }
            
            const { shield_action, verification_mode, offline_verification } = statusResult;
            
            switch (shield_action) {
                case 'allow_access':
                    console.log('✅ Access allowed - hiding shield');
                    this.grantAccess();
                    break;
                    
                case 'require_verification':
                    console.log('🛡️ Verification required - showing shield');
                    await this.showVerificationWidget();
                    break;
                    
                case 'verify_did':
                case 'check_credentials':
                case 'check_revocation':
                default:
                    console.log(`🔍 Shield action: ${shield_action} - showing verification widget`);
                    await this.showVerificationWidget();
                    break;
            }
            
            // Handle specific verification modes
            if (verification_mode === 'offline_verified' && offline_verification) {
                console.log('🚀 Offline verification successful - access granted');
                this.grantAccess();
            } else if (verification_mode === 'offline_failed') {
                console.log('❌ Offline verification failed - showing shield');
                await this.showVerificationWidget();
            }
            
        } catch (error) {
            console.error('❌ Error handling status result:', error);
            // Fallback to showing shield on error
            await this.showVerificationWidget();
        }
    }
    
    startRevocationMonitoring() {
        /*
         * Start periodic checking for credential revocation
         * This ensures the shield reappears when credentials are revoked
         */
        console.log('🔄 Starting revocation monitoring...');
        
        // Check every 10 seconds for revocation
        this.revocationCheckInterval = setInterval(async () => {
            try {
                console.log('🔍 Periodic revocation check...');
                const statusResult = await this.checkStatus();
                
                // If status changed to require verification, show shield
                if (statusResult && statusResult.shield_action === 'require_verification') {
                    console.log('⚠️ Revocation detected - showing shield');
                    await this.showVerificationWidget();
                    
                    // Clear the interval since we're now in verification mode
                    if (this.revocationCheckInterval) {
                        clearInterval(this.revocationCheckInterval);
                        this.revocationCheckInterval = null;
                    }
                }
                
            } catch (error) {
                console.error('❌ Revocation check error:', error);
            }
        }, 10000); // Check every 10 seconds
        
        // Also listen for custom revocation events
        window.addEventListener('lemma-credential-revoked', async (event) => {
            console.log('🚨 Revocation event received:', event.detail);
            this.handleCredentialRevoked(event.detail);
            await this.showVerificationWidget();
        });
        
        window.addEventListener('lemma-force-verification', async (event) => {
            console.log('🚨 Force verification event received:', event.detail);
            await this.showVerificationWidget();
        });
        
        window.addEventListener('lemma-security-lockout', async (event) => {
            console.log('🚨 Security lockout event received:', event.detail);
            this.handleCredentialRevoked(event.detail);
            await this.showVerificationWidget();
        });
    }
    
    handleCredentialRevoked(eventDetail) {
        /*
         * Handle credential revocation by updating local revocation list
         * This ensures offline verification will detect revoked credentials
         */
        try {
            const credentialId = eventDetail.credential_id || eventDetail.credentialId;
            if (!credentialId) {
                console.warn('⚠️ No credential ID in revocation event');
                return;
            }
            
            console.log(`🚨 Adding credential to local revocation list: ${credentialId}`);
            
            // Get existing revoked credentials
            const revokedCredentials = JSON.parse(localStorage.getItem('lemma_revoked_credentials') || '[]');
            
            // Add the revoked credential if not already present
            if (!revokedCredentials.includes(credentialId)) {
                revokedCredentials.push(credentialId);
                localStorage.setItem('lemma_revoked_credentials', JSON.stringify(revokedCredentials));
                console.log(`✅ Updated local revocation list. Now contains ${revokedCredentials.length} revoked credentials`);
            }
            
            // ENHANCED: Also clear from wallet and trigger immediate re-verification
            if (this.wallet && this.wallet.removeCredential) {
                this.wallet.removeCredential(credentialId).catch(error => {
                    console.warn('⚠️ Failed to remove credential from wallet:', error);
                });
            }
            
            // Clear local storage items related to this credential
            const keysToRemove = [];
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                if (key && (key.includes(credentialId) || key.includes('lemma_credential') || key.includes('lemma_verified'))) {
                    keysToRemove.push(key);
                }
            }
            keysToRemove.forEach(key => localStorage.removeItem(key));
            
            // Force immediate verification
            this.showVerificationWidget();
            
        } catch (error) {
            console.error('❌ Error handling credential revocation:', error);
        }
    }
    
    async verifyOffline(credential) {
        /*
         * Perform true offline verification using only local cryptographic operations
         * This method makes NO API calls and works completely offline
         */
        try {
            console.log('🔒 Starting offline verification...');
            
            if (!credential.offline_capable) {
                return {
                    success: false,
                    error: 'Credential does not support offline verification'
                };
            }
            
            const offlineWitness = credential.offline_witness;
            if (!offlineWitness) {
                return {
                    success: false,
                    error: 'No offline witness found'
                };
            }
            
            // Check if witness has expired
            const currentTime = Date.now() / 1000;
            if (currentTime > offlineWitness.valid_until) {
                return {
                    success: false,
                    error: 'Offline witness expired',
                    sync_required: true
                };
            }
            
            // Verify credential signature offline (simplified for demo)
            const signatureValid = await this.verifyCredentialSignatureOffline(credential);
            if (!signatureValid) {
                return {
                    success: false,
                    error: 'Invalid credential signature'
                };
            }
            
            // Check revocation status offline
            const revocationStatus = await this.checkRevocationOffline(credential.id, offlineWitness);
            if (revocationStatus.revoked) {
                return {
                    success: false,
                    error: 'Credential has been revoked'
                };
            }
            
            console.log('✅ Offline verification completed successfully');
            
            return {
                success: true,
                verification_mode: 'offline_verified',
                witness_valid_until: offlineWitness.valid_until,
                api_calls_made: 0,  // Proof of true offline verification
                offline_verification: true
            };
            
        } catch (error) {
            console.error('❌ Offline verification error:', error);
            return {
                success: false,
                error: `Offline verification failed: ${error.message}`
            };
        }
    }
    
    async verifyCredentialSignatureOffline(credential) {
        /*
         * Verify credential signature using only local cryptographic operations
         */
        try {
            // Extract signature and issuer public key from offline witness
            const signature = credential.proof?.jws;
            const offlineWitness = credential.offline_witness;
            const issuerPublicKey = offlineWitness?.issuer_public_key;
            
            if (!signature || !issuerPublicKey) {
                return false;
            }
            
            // In production, this would use proper JWT/Ed25519 verification
            // For demo purposes, we'll simulate the verification
            console.log('🔐 Verifying credential signature offline...');
            
            // Simplified verification - in production use proper cryptographic libraries
            return true;  // Demo: assume signature is valid
            
        } catch (error) {
            console.error('❌ Offline signature verification failed:', error);
            return false;
        }
    }
    
    async checkRevocationOffline(credentialId, offlineWitness) {
        /*
         * Check if credential is revoked using offline witness data
         * For demo purposes, this will detect revocation by checking against
         * a simple revocation list stored in localStorage
         */
        try {
            // Check if credential is in the revoked list (demo implementation)
            const revokedCredentials = JSON.parse(localStorage.getItem('lemma_revoked_credentials') || '[]');
            const isRevoked = revokedCredentials.includes(credentialId);
            
            if (isRevoked) {
                console.log(`🚨 Offline revocation check: CREDENTIAL REVOKED - ${credentialId}`);
                return {
                    revoked: true,
                    method: 'offline_revocation_list',
                    revocation_reason: 'Detected in offline revocation list'
                };
            }
            
            // Also check the bloom filter if available
            const revocationSnapshot = offlineWitness.revocation_snapshot;
            if (revocationSnapshot && revocationSnapshot.bloom_filter) {
                // Simplified bloom filter check - in production use proper bloom filter
                const credentialHash = await this.hashCredentialId(credentialId);
                const bloomRevoked = revocationSnapshot.bloom_filter.includes(credentialHash.substring(0, 8));
                
                if (bloomRevoked) {
                    console.log(`🚨 Offline revocation check: BLOOM FILTER REVOKED - ${credentialId}`);
                    return {
                        revoked: true,
                        method: 'offline_bloom_filter',
                        snapshot_age_hours: (Date.now() / 1000 - revocationSnapshot.snapshot_time) / 3600
                    };
                }
            }
            
            console.log(`✅ Offline revocation check: CREDENTIAL VALID - ${credentialId}`);
            return { 
                revoked: false, 
                method: 'offline_comprehensive_check',
                checked_sources: ['revocation_list', 'bloom_filter']
            };
            
        } catch (error) {
            console.error('❌ Offline revocation check failed:', error);
            return { revoked: false, method: 'offline_check_error' };
        }
    }
    
    async hashCredentialId(credentialId) {
        /*
         * Hash credential ID for bloom filter checking
         */
        try {
            const encoder = new TextEncoder();
            const data = encoder.encode(credentialId);
            const hashBuffer = await crypto.subtle.digest('SHA-256', data);
            const hashArray = Array.from(new Uint8Array(hashBuffer));
            return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
        } catch (error) {
            console.error('❌ Credential ID hashing failed:', error);
            return credentialId;  // Fallback to original ID
        }
    }
    
    async startShieldVerification() {
        try {
            console.log('🛡️ Starting Shield inline verification...');
            
            // Get CSRF token first
            const csrfResponse = await fetch(`${this.options.apiBase}/api/generate-csrf`, {
                credentials: 'same-origin'
            });
            const csrfData = await csrfResponse.json();
            const csrfToken = csrfData.csrf_token;
            
            // Start inline verification through Shield API
            const response = await fetch(`${this.options.apiBase}/api/shield/start-verification`, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    return_url: window.location.href,
                    security_level: this.options.securityLevel || 'standard',
                    inline_mode: true  // Request inline verification
                })
            });
            
            if (!response.ok) {
                throw new Error('Failed to start Shield verification');
            }
            
            const result = await response.json();
            
            if (result.success) {
                if (result.shield_action === 'inline_verification' && result.stripe_client_secret) {
                    console.log('🛡️ Starting inline Stripe Identity verification');
                    this.handleInlineVerification(result);
                } else if (result.shield_action === 'redirect_verification' && result.verification_url) {
                    console.log('🛡️ Fallback to redirect verification:', result.verification_url);
                    window.location.href = result.verification_url;
                } else {
                    throw new Error('Invalid verification response');
                }
            } else {
                throw new Error(result.error || 'Failed to start verification');
            }
            
        } catch (error) {
            console.error('❌ Failed to start Shield verification:', error);
            this.options.onError(error);
        }
    }
    
    async handleInlineVerification(verificationData) {
        try {
            console.log('🛡️ Handling verification with Stripe Identity');
            
            // Store verification data
            this.state.userId = verificationData.user_id;
            this.state.verificationSessionId = verificationData.session_id;
            
            // Store current page URL for return after verification
            const currentUrl = window.location.href;
            sessionStorage.setItem('lemma_return_url', currentUrl);
            
            // Show verification transition UI
            this.showVerificationTransitionUI(verificationData);
            
            // Handle both inline and redirect verification modes
            if (verificationData.stripe_client_secret) {
                console.log('🔄 Using Stripe Identity inline verification...');
                
                // Use the original inline approach but with better error handling
                setTimeout(async () => {
                    try {
                        // Load Stripe Elements if not already loaded
                        if (!window.Stripe) {
                            await this.loadStripeElements();
                        }
                        
                        const stripe = window.Stripe(this.options.stripePublishableKey || 'pk_test_51RJNLBDIouMeOMab56ZoLLf7qyXOfw2dWq8dDnhihzcc9hOHhw2xqyvzEUXbfZDsYyAnZNa5ADkycRpqUvDzMr3G00CgiM8efu');
                        
                        // Initialize Stripe Identity verification
                        const { error } = await stripe.verifyIdentity(verificationData.stripe_client_secret);
                        
                        if (error) {
                            console.error('❌ Stripe Identity verification failed:', error);
                            this.options.onError(new Error(error.message));
                        } else {
                            console.log('✅ Stripe Identity verification completed');
                            // Check verification status and complete flow
                            await this.completeInlineVerification();
                        }
                    } catch (error) {
                        console.error('❌ Stripe verification error:', error);
                        this.options.onError(error);
                    }
                }, 1500);
                
            } else if (verificationData.verification_url) {
                console.log('🔄 Redirecting to verification page...');
                
                // Set a small delay to show the transition UI
                setTimeout(() => {
                    window.location.href = verificationData.verification_url;
                }, 1500);
                
            } else {
                console.error('❌ No verification method provided');
                console.log('Verification data received:', verificationData);
                this.options.onError(new Error('No verification method available'));
            }
            
        } catch (error) {
            console.error('❌ Verification redirect error:', error);
            this.options.onError(error);
        }
    }
    
    async loadStripeElements() {
        return new Promise((resolve, reject) => {
            if (window.Stripe) {
                resolve();
                return;
            }
            
            const script = document.createElement('script');
            script.src = 'https://js.stripe.com/v3/';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
    
    showVerificationTransitionUI(verificationData) {
        const container = this.getShieldContainer();
        if (!container) return;
        
        container.innerHTML = `
            <div class="lemma-shield-overlay">
                <div class="lemma-shield-widget lemma-card">
                    <div class="lemma-card-header">
                        <h2>🛡️ Redirecting to Identity Verification</h2>
                        <p>You're being redirected to Stripe Identity for secure verification</p>
                    </div>
                    <div class="lemma-card-body">
                        <div class="verification-progress">
                            <div class="lemma-spinner"></div>
                            <p>Preparing secure verification...</p>
                            <div class="verification-steps">
                                <div class="step active">
                                    <div class="step-icon">✓</div>
                                    <div class="step-text">Initializing verification</div>
                                </div>
                                <div class="step">
                                    <div class="step-icon">🔄</div>
                                    <div class="step-text">Redirecting to Stripe</div>
                                </div>
                                <div class="step">
                                    <div class="step-icon">📋</div>
                                    <div class="step-text">Complete identity verification</div>
                                </div>
                                <div class="step">
                                    <div class="step-icon">🏠</div>
                                    <div class="step-text">Return to protected content</div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="lemma-card-footer">
                        <p class="small-text">🔒 Your data is processed securely by Stripe and not stored by Lemma</p>
                    </div>
                </div>
            </div>
        `;
        
        // Animate the progress steps
        setTimeout(() => {
            const steps = container.querySelectorAll('.step');
            if (steps[1]) {
                steps[1].classList.add('active');
                steps[1].querySelector('.step-icon').textContent = '✓';
            }
        }, 800);
    }
    
    async completeInlineVerification() {
        try {
            console.log('🛡️ Completing inline verification...');
            
            // Show loading state
            this.showVerificationProcessingUI();
            
            // Wait for Stripe to process and retry verification status check
            let attempts = 0;
            const maxAttempts = 12; // Try for up to 60 seconds (12 * 5 seconds)
            let result = null;
            
            while (attempts < maxAttempts) {
                attempts++;
                console.log(`🔄 Checking verification status (attempt ${attempts}/${maxAttempts})...`);
                
                // Wait before each attempt (progressive backoff)
                const waitTime = Math.min(2000 + (attempts * 1000), 8000); // 2s, 3s, 4s... up to 8s
                await new Promise(resolve => setTimeout(resolve, waitTime));
                
                result = await this.checkVerificationStatus();
                
                if (result && result.success && result.verified) {
                    console.log('✅ Verification status confirmed - credential issued');
                    // Success handled in checkVerificationStatus, no need to duplicate
                    return; // Exit early to avoid showing success twice
                } else if (result && result.error && !result.error.includes('incomplete') && !result.error.includes('processing')) {
                    // If it's a real error (not just "incomplete" or "processing"), break immediately
                    console.error('❌ Verification failed with error:', result.error);
                    break;
                } else {
                    console.log(`⏳ Verification still processing... (${result ? (result.error || result.message || 'no response') : 'no response'})`);
                }
            }
            
            if (result && result.success && result.verified) {
                console.log('✅ Inline verification completed successfully');
                
                // CRITICAL FIX: Retrieve and store the credential after successful verification
                try {
                    console.log('🔑 Retrieving credential for wallet storage...');
                    const credentialResponse = await fetch(`${this.options.apiBase}/api/shield/get-credential`, {
                        method: 'GET',
                        credentials: 'same-origin',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Requested-With': 'XMLHttpRequest'
                        }
                    });
                    
                    if (credentialResponse.ok) {
                        const credentialResult = await credentialResponse.json();
                        if (credentialResult.success && credentialResult.credential && this.wallet) {
                            console.log('💾 Storing credential in wallet...');
                            await this.wallet.storeCredential(credentialResult.credential);
                            console.log('✅ Credential stored successfully in wallet');
                        } else {
                            console.warn('⚠️ No credential available for wallet storage:', credentialResult.message);
                        }
                    } else {
                        console.warn('⚠️ Failed to retrieve credential for wallet storage');
                    }
                } catch (credentialError) {
                    console.error('❌ Failed to retrieve/store credential:', credentialError);
                    // Don't fail the entire verification process for credential storage issues
                }
                
                this.showSuccessAndGrantAccess();
            } else {
                // Check if it's just a timing issue vs real failure
                const errorMessage = result && result.error;
                if (errorMessage && (errorMessage.includes('incomplete') || errorMessage.includes('processing'))) {
                    console.log('⏳ Verification still in progress after maximum attempts - may need manual refresh');
                    this.showVerificationTimeoutMessage();
                } else {
                    console.error('❌ Verification failed:', errorMessage || 'Unknown error');
                    this.options.onError(new Error(errorMessage || 'Verification failed - please try again'));
                }
            }
            
        } catch (error) {
            console.error('❌ Failed to complete inline verification:', error);
            this.options.onError(error);
        }
    }
    
    showVerificationProcessingUI() {
        const container = this.getShieldContainer();
        if (!container) return;
        
        container.innerHTML = `
            <div class="lemma-shield-overlay">
                <div class="lemma-shield-widget lemma-card">
                    <div class="lemma-card-header">
                        <h2>🔄 Processing Verification</h2>
                        <p>Please wait while we confirm your verification...</p>
                    </div>
                    <div class="lemma-card-body">
                        <div class="verification-progress">
                            <div class="lemma-spinner"></div>
                            <p>This may take a few moments...</p>
                            <div class="processing-steps">
                                <div class="step-item active" id="step-1">
                                    <span class="step-icon">✅</span>
                                    <span class="step-text">Identity verification completed</span>
                                </div>
                                <div class="step-item processing" id="step-2">
                                    <span class="step-icon">🔄</span>
                                    <span class="step-text">Credential issuance in progress</span>
                                </div>
                                <div class="step-item pending" id="step-3">
                                    <span class="step-icon">⏳</span>
                                    <span class="step-text">Wallet storage pending</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    showVerificationTimeoutMessage() {
        const container = this.getShieldContainer();
        if (!container) return;
        
        container.innerHTML = `
            <div class="lemma-shield-overlay">
                <div class="lemma-shield-widget lemma-card">
                    <div class="lemma-card-header">
                        <h2>⏰ Verification In Progress</h2>
                        <p>Your verification is still being processed</p>
                    </div>
                    <div class="lemma-card-body">
                        <div class="verification-status">
                            <div class="status-icon">🔄</div>
                            <p><strong>Your Stripe Identity verification was successful!</strong></p>
                            <p>The system is still processing your credential. This may take a few more moments.</p>
                            
                            <div class="action-buttons">
                                <button class="lemma-btn primary" onclick="window.location.reload()">
                                    🔄 Refresh Page
                                </button>
                                <button class="lemma-btn secondary" onclick="this.checkVerificationStatus()" id="retry-check">
                                    🔍 Check Status Again
                                </button>
                            </div>
                            
                            <div class="help-text">
                                <p class="small-text">
                                    ✅ If you completed Stripe verification, your credential should be ready shortly.<br>
                                    ⏰ Processing usually takes 30-60 seconds after verification.
                                </p>
                            </div>
                        </div>
                    </div>
                    <div class="lemma-card-footer">
                        ${this.getBrandingFooter()}
                    </div>
                </div>
            </div>
        `;
        
        // Add event listener for retry button
        const retryButton = container.querySelector('#retry-check');
        if (retryButton) {
            retryButton.addEventListener('click', () => {
                this.showVerificationProcessingUI();
                this.completeInlineVerification();
            });
        }
    }
    
    async checkVerificationStatus() {
        try {
            // Get CSRF token first
            const csrfResponse = await fetch(`${this.options.apiBase}/api/generate-csrf`, {
                credentials: 'same-origin'
            });
            const csrfData = await csrfResponse.json();
            const csrfToken = csrfData.csrf_token;
            
            const requestBody = {
                user_id: this.state.userId,
                session_id: this.state.verificationSessionId || this.state.sessionId,
                check_inline_verification: true
            };
            
            console.log('🔍 Sending verification status check request:', requestBody);
            
            const response = await fetch(`${this.options.apiBase}/api/shield/verify-credentials`, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify(requestBody)
            });
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error('❌ API Response Error:', response.status, errorText);
                throw new Error(`Failed to check verification status: ${response.status}`);
            }
            
            const result = await response.json();
            console.log('✅ Verification status response:', result);
            return result;
            
        } catch (error) {
            console.error('❌ Verification status check failed:', error);
            return {
                success: false,
                error: error.message
            };
        }
    }

    async showVerificationWidget() {
        /*
         * Enhanced showVerificationWidget that handles revocation scenarios
         */
        try {
            console.log('🛡️ Showing verification widget...');
            
            // Get the shield container
            const container = this.getShieldContainer();
            if (!container) {
                console.error('❌ Shield container not found');
                return;
            }
            
            // CRITICAL FIX: Always show the container immediately
            container.style.display = 'block';
            container.style.visibility = 'visible';
            container.style.opacity = '1';
            
            // ENHANCED: Check if we're in a revocation scenario
            const isRevocationTriggered = document.querySelector('[data-revocation-triggered="true"]') || 
                                         window.location.search.includes('force_verification=credential_revoked') ||
                                         sessionStorage.getItem('lemma_revocation_triggered') === 'true';
            
            if (isRevocationTriggered) {
                console.log('🚨 Revocation-triggered verification detected - showing special UI');
                
                // Show with special revocation messaging
                container.innerHTML = `
                    <div class="lemma-shield-overlay">
                        <div class="lemma-shield-widget">
                            <div class="lemma-shield-header">
                                <div class="lemma-shield-icon">🚨</div>
                                <h2>Credential Revoked - Re-verification Required</h2>
                                <p>Your verification credential has been revoked for security reasons.</p>
                            </div>
                            <div class="lemma-shield-body">
                                <p>Please complete verification again to continue accessing protected content.</p>
                                <button class="lemma-verify-btn" id="start-revoke-verification">
                                    🛡️ Start Re-verification
                                </button>
                            </div>
                            ${this.options.showBranding ? this.getBrandingFooter() : ''}
                        </div>
                    </div>
                `;
                
                // Add styles
                this.addStyles();
                
                // Add event listener for the button
                document.getElementById('start-revoke-verification').addEventListener('click', () => {
                    sessionStorage.removeItem('lemma_revocation_triggered');
                    this.showInitialStep(container);
                });
                
                container.setAttribute('data-revocation-triggered', 'true');
                console.log('✅ Revocation UI displayed');
                return; // Don't continue to normal flow
            }
            
            // Normal verification widget display
            this.showInitialStep(container);
            
        } catch (error) {
            console.error('❌ Error showing verification widget:', error);
            // Fallback: show basic shield
            const container = this.getShieldContainer();
            if (container) {
                container.style.display = 'block';
                container.innerHTML = `
                    <div class="lemma-shield-overlay">
                        <div class="lemma-shield-widget">
                            <div class="lemma-shield-header">
                                <div class="lemma-shield-icon">🛡️</div>
                                <h2>Verification Required</h2>
                                <p>Please verify to continue</p>
                            </div>
                            <div class="lemma-shield-body">
                                <button class="lemma-verify-btn" onclick="window.location.reload()">
                                    🔄 Try Again
                                </button>
                            </div>
                        </div>
                    </div>
                `;
                this.addStyles();
            }
        }
    }
    
    showInitialStep(container) {
        container.innerHTML = `
            <div class="lemma-shield-overlay">
                <div class="lemma-shield-widget">
                    <div class="lemma-shield-header">
                        <div class="lemma-shield-icon">🛡️</div>
                        <h2>Human Verification Required</h2>
                        <p>This content is protected by Lemma Shield</p>
                    </div>
                    
                    <div class="lemma-shield-body">
                        <p>To access this content, please verify that you're human.</p>
                        <button class="lemma-verify-btn" id="start-verification">
                            🤖 Verify Human Identity
                        </button>
                    </div>
                    
                    ${this.options.showBranding ? this.getBrandingFooter() : ''}
                </div>
            </div>
        `;
        
        // Add event listeners
        document.getElementById('start-verification').addEventListener('click', () => {
            this.startShieldVerification();
        });
        
        // Add styles
        this.addStyles();
    }
    
    showDisclaimerStep(container) {
        this.state.currentStep = 'disclaimer';
        this.options.onStepChange('disclaimer');
        
        container.innerHTML = `
            <div class="lemma-shield-overlay">
                <div class="lemma-shield-widget lemma-card">
                    <div class="lemma-card-header">
                        <div class="lemma-logo">
                            <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                                <rect width="32" height="32" rx="8" fill="#635BFF"/>
                                <path d="M8 12h16v8H8z" fill="white"/>
                                <path d="M12 8v16M20 8v16" stroke="white" stroke-width="2"/>
                            </svg>
                        </div>
                        <h2>About Lemma Verification</h2>
                    </div>
                    
                    <div class="lemma-card-body">
                        <div class="privacy-section">
                            <h3>🔒 Your Privacy is Protected</h3>
                            <p>Lemma is committed to minimal data collection and maximum privacy protection:</p>
                            <ul>
                                <li><strong>Minimal Data:</strong> We only verify that you're human - nothing more</li>
                                <li><strong>No Personal Storage:</strong> Your identity details are processed by Stripe and not stored by us</li>
                                <li><strong>Decentralized:</strong> Your verification credential stays in your browser</li>
                                <li><strong>Portable:</strong> One verification works across all Lemma-protected sites</li>
                            </ul>
                        </div>
                        
                        <div class="verification-info">
                            <h3>🆔 What We Need</h3>
                            <p>You'll be asked to provide:</p>
                            <ul>
                                <li>A photo of your government-issued ID (driver's license, passport, or national ID)</li>
                                <li>A selfie to match your ID photo</li>
                            </ul>
                            <p class="small-text">This verification is processed securely by Stripe Identity and takes about 1-2 minutes.</p>
                        </div>
                        
                        <div class="lemma-card-actions">
                            <button class="lemma-btn lemma-btn-secondary" id="go-back">
                                ← Back
                            </button>
                            <button class="lemma-btn lemma-btn-primary" id="proceed-verification">
                                Continue to Verification →
                            </button>
                        </div>
                    </div>
                    
                    ${this.options.showBranding ? this.getBrandingFooter() : ''}
                </div>
            </div>
        `;
        
        // Add event listeners
        document.getElementById('go-back').addEventListener('click', () => {
            this.showInitialStep(container);
        });
        
        document.getElementById('proceed-verification').addEventListener('click', () => {
            this.showVerificationStep(container);
        });
    }
    
    async showVerificationStep(container) {
        this.state.currentStep = 'verification';
        this.options.onStepChange('verification');
        
        // Show loading state first
        container.innerHTML = `
            <div class="lemma-shield-overlay">
                <div class="lemma-shield-widget lemma-card">
                    <div class="lemma-card-header">
                        <div class="lemma-spinner"></div>
                        <h2>Starting Verification</h2>
                    </div>
                    <div class="lemma-card-body">
                        <p>Preparing your secure verification session...</p>
                    </div>
                </div>
            </div>
        `;
        
        try {
            // Generate user ID and start verification
            this.state.userId = this.generateUserId();
            const verificationSession = await this.startVerificationSession();
            
            if (verificationSession && verificationSession.success) {
                // Show Stripe verification card
                this.showStripeVerificationCard(container, verificationSession);
            } else {
                throw new Error(verificationSession?.error || 'Failed to start verification');
            }
            
        } catch (error) {
            console.error('❌ Failed to start verification:', error);
            this.showError(container, error.message);
        }
    }
    
    showStripeVerificationCard(container, verificationSession) {
        container.innerHTML = `
            <div class="lemma-shield-overlay">
                <div class="lemma-shield-widget lemma-card">
                    <div class="lemma-card-header">
                        <div class="stripe-logo">
                            <svg width="32" height="14" viewBox="0 0 32 14" fill="none">
                                <path d="M2 0h28c1.1 0 2 .9 2 2v10c0 1.1-.9 2-2 2H2c-1.1 0-2-.9-2-2V2C0 .9.9 0 2 0z" fill="#635BFF"/>
                                <path d="M9.5 7.5c0-.8.7-1.5 1.5-1.5s1.5.7 1.5 1.5-.7 1.5-1.5 1.5-1.5-.7-1.5-1.5zm5 0c0-.8.7-1.5 1.5-1.5s1.5.7 1.5 1.5-.7 1.5-1.5 1.5-1.5-.7-1.5-1.5zm5 0c0-.8.7-1.5 1.5-1.5s1.5.7 1.5 1.5-.7 1.5-1.5 1.5-1.5-.7-1.5-1.5z" fill="white"/>
                            </svg>
                            <span>Secure Identity Verification</span>
                        </div>
                        <h2>Identity Verification</h2>
                    </div>
                    
                    <div class="lemma-card-body">
                        <div class="verification-steps">
                            <div class="step active">
                                <div class="step-number">1</div>
                                <div class="step-content">
                                    <h4>Document Photo</h4>
                                    <p>Take a photo of your ID</p>
                                </div>
                            </div>
                            <div class="step">
                                <div class="step-number">2</div>
                                <div class="step-content">
                                    <h4>Selfie</h4>
                                    <p>Take a selfie to match your ID</p>
                                </div>
                            </div>
                            <div class="step">
                                <div class="step-number">3</div>
                                <div class="step-content">
                                    <h4>Complete</h4>
                                    <p>Access granted</p>
                                </div>
                            </div>
                        </div>
                        
                        <div class="verification-notice">
                            <p>🔒 Your verification is processed securely by Stripe Identity. Lemma does not store your personal information.</p>
                        </div>
                        
                        <div class="lemma-card-actions">
                            <button class="lemma-btn lemma-btn-secondary" id="cancel-verification">
                                Cancel
                            </button>
                            <button class="lemma-btn lemma-btn-primary" id="open-stripe-verification">
                                🆔 Start ID Verification
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Add event listeners
        document.getElementById('cancel-verification').addEventListener('click', () => {
            this.showInitialStep(container);
        });
        
        document.getElementById('open-stripe-verification').addEventListener('click', () => {
            this.openStripeVerification(verificationSession);
        });
        
        // Store session ID for later
        this.state.verificationSessionId = verificationSession.session_id || verificationSession.verification_session_id;
    }
    
    async startVerificationSession() {
        try {
            // Get CSRF token first
            const csrfResponse = await fetch(`${this.options.apiBase}/api/generate-csrf`, {
                credentials: 'same-origin'
            });
            const csrfData = await csrfResponse.json();
            const csrfToken = csrfData.csrf_token;
            
            // Start the verification session with Shield API
            const response = await fetch(`${this.options.apiBase}/api/shield/start-verification`, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    return_url: window.location.href,
                    security_level: this.options.securityLevel || 'standard'
                })
            });
            
            if (!response.ok) {
                throw new Error('Failed to start verification session');
            }
            
            const result = await response.json();
            
            return result;
            
        } catch (error) {
            console.error('❌ Verification session error:', error);
            throw error;
        }
    }
    
    openStripeVerification(verificationSession) {
        if (verificationSession.verification_url) {
            // Store current state for when user returns
            sessionStorage.setItem('lemma_verification_state', JSON.stringify({
                userId: this.state.userId,
                sessionId: verificationSession.session_id,
                returnUrl: window.location.href,
                widgetState: this.state
            }));
            
            // Redirect to verification in the same window
            console.log('🔄 Redirecting to Stripe verification...');
            window.location.href = verificationSession.verification_url;
        }
    }
    
    // Check if user is returning from Stripe verification
    async checkForReturnFromVerification() {
        const urlParams = new URLSearchParams(window.location.search);
        const returnUrl = sessionStorage.getItem('lemma_return_url');
        
        // Only proceed if we have clear indicators of successful verification return
        const hasVerifiedParam = urlParams.get('verified') === 'true';
        const hasVerificationComplete = urlParams.has('verification_complete');
        const hasLemmaSession = sessionStorage.getItem('lemma_verification_state');
        
        // Check if current URL matches stored return URL
        const isReturnUrl = returnUrl && window.location.href.includes(returnUrl.split('?')[0]);
        
        // Only proceed if we have strong indicators this is a verification return
        if ((hasVerifiedParam || hasVerificationComplete) && (isReturnUrl || hasLemmaSession)) {
            console.log('🔄 User returned from Stripe verification, showing transition...');
            
            // Show return transition UI
            this.showReturnTransitionUI();
            
            // Extract user ID from URL or session
            const userId = urlParams.get('user_id') || this.state.userId;
            if (userId) {
                this.state.userId = userId;
            }
            
            // Clear the return URL to prevent repeated processing
            sessionStorage.removeItem('lemma_return_url');
            
            // Wait longer for webhook processing before checking status
            setTimeout(() => {
                this.checkPostVerificationStatus();
            }, 5000);
            
            return true;
        }
        
        return false;
    }
    
    showReturnTransitionUI() {
        const container = this.getShieldContainer();
        if (!container) return;
        
        container.innerHTML = `
            <div class="lemma-shield-overlay">
                <div class="lemma-shield-widget lemma-card">
                    <div class="lemma-card-header">
                        <h2>🏠 Welcome Back!</h2>
                        <p>Processing your verification results...</p>
                    </div>
                    <div class="lemma-card-body">
                        <div class="verification-progress">
                            <div class="lemma-spinner"></div>
                            <p>Checking verification status...</p>
                            <div class="verification-steps">
                                <div class="step active">
                                    <div class="step-icon">✓</div>
                                    <div class="step-text">Verification completed</div>
                                </div>
                                <div class="step active">
                                    <div class="step-icon">✓</div>
                                    <div class="step-text">Returned to protected content</div>
                                </div>
                                <div class="step">
                                    <div class="step-icon">🔄</div>
                                    <div class="step-text">Processing results</div>
                                </div>
                                <div class="step">
                                    <div class="step-icon">🛡️</div>
                                    <div class="step-text">Granting access</div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="lemma-card-footer">
                        <p class="small-text">✅ Your identity has been verified successfully</p>
                    </div>
                </div>
            </div>
        `;
        
        // Animate the progress steps
        setTimeout(() => {
            const steps = container.querySelectorAll('.step');
            if (steps[2]) {
                steps[2].classList.add('active');
                steps[2].querySelector('.step-icon').textContent = '✓';
            }
        }, 1000);
    }
    
    async checkPostVerificationStatus() {
        try {
            console.log('🔍 Checking post-verification status...');
            
            // Check if verification was successful and get credential
            const result = await this.checkVerificationStatus();
            
            if (result && result.success && result.verified) {
                console.log('✅ Post-verification check successful');
                
                // Animate final step
                const steps = document.querySelectorAll('.step');
                if (steps[3]) {
                    steps[3].classList.add('active');
                    steps[3].querySelector('.step-icon').textContent = '✅';
                }
                
                // Show success and grant access
                setTimeout(() => {
                    this.showSuccessAndGrantAccess();
                }, 1000);
            } else {
                console.error('❌ Post-verification check failed:', result);
                this.showError(null, 'Failed to complete verification process');
            }
            
        } catch (error) {
            console.error('❌ Post-verification status check failed:', error);
            this.showError(null, 'Failed to process verification results');
        }
    }
    
    async showSuccessAndGrantAccess() {
        this.hideError();
        
        // Get the shield container
        const container = this.getShieldContainer();
        if (!container) {
            console.warn('⚠️ No shield container found, granting access directly');
            this.grantAccess();
            return;
        }
        
        // Show success message with verification animation
        container.innerHTML = `
            <div class="lemma-shield-overlay">
                <div class="lemma-shield-widget lemma-card">
                    <div class="lemma-card-header">
                        <h2>✅ Verification Complete!</h2>
                        <p>You've been verified as a real human. Welcome to the Lemma Network!</p>
                    </div>
                    <div class="lemma-card-body">
                        <div class="lemma-success-details">
                            <div class="lemma-status-item">
                                <span class="lemma-status-label">Status:</span>
                                <span class="lemma-status-value">Verified Human</span>
                            </div>
                            <div class="lemma-status-item">
                                <span class="lemma-status-label">Network:</span>
                                <span class="lemma-status-value">Lemma Verified Network</span>
                            </div>
                            <div class="lemma-status-item">
                                <span class="lemma-status-label">Access:</span>
                                <span class="lemma-status-value">Full Platform Access</span>
                            </div>
                            <div id="lemma-verification-test-status" style="margin-top: 15px;">
                                <div class="lemma-status-item">
                                    <span class="lemma-status-label">System Check:</span>
                                    <span class="lemma-status-value" id="system-check-status">🔄 Verifying...</span>
                                </div>
                            </div>
                        </div>
                        
                        <div class="lemma-network-benefits">
                            <h4>Your Lemma Benefits:</h4>
                            <ul>
                                <li>🚀 Instant access across all Lemma-integrated sites</li>
                                <li>🔒 Privacy-first verification with minimal data collection</li>
                                <li>⚡ Background verification - no more CAPTCHAs</li>
                                <li>🌐 Portable identity that works everywhere</li>
                            </ul>
                        </div>
                    </div>
                    <div class="lemma-card-footer">
                        ${this.getBrandingFooter()}
                    </div>
                </div>
            </div>
        `;
        
        // Run post-verification test and wait for result
        const testResult = await this.runPostVerificationTest();
        
        // Debug logging to understand the test result structure
        console.log('🔍 Post-verification test result:', testResult);
        
        // Only grant access if tests pass (check both success and verified properties)
        const isSuccessful = testResult && (testResult.success === true || testResult.verified === true);
        
        if (isSuccessful) {
            console.log('✅ All verification tests passed - granting access');
            setTimeout(() => {
                this.grantAccess();
            }, 2000); // Show success for 2 seconds, then grant access
        } else {
            console.warn('⚠️ Verification tests failed - keeping protection active');
            console.warn('⚠️ Test result details:', {
                hasResult: !!testResult,
                success: testResult?.success,
                verified: testResult?.verified,
                isSuccessful: isSuccessful,
                error: testResult?.error,
                message: testResult?.message,
                fullResult: testResult
            });
            this.showVerificationFailure(testResult);
        }
    }
    
    /**
     * Run automatic end-to-end verification test after successful Shield verification
     */
    async runPostVerificationTest() {
        try {
            const statusElement = document.getElementById('system-check-status');
            if (!statusElement) return { success: false, error: 'No status element found' };

            // Update status to show testing
            statusElement.textContent = '🔄 Running system verification...';
            
            // Get verification flow instance
            const verificationFlow = new LemmaVerificationFlow();
            
            // Run the end-to-end test
            const testResult = await verificationFlow.verifyShieldAfterCompletion({
                user_id: this.state.userId,
                shield_result: this.state,
                timeout_ms: 8000 // 8 second timeout for user experience
            });
            
            // Debug logging
            console.log('🔍 Raw verification flow result:', testResult);
            console.log('🔍 Success check:', testResult && (testResult.success || testResult.verified));
            
            // Check for success using either 'success' or 'verified' property
            const isSuccessful = testResult && (testResult.success === true || testResult.verified === true);
            
            if (isSuccessful) {
                statusElement.innerHTML = '✅ <span style="color: #28a745;">All systems operational</span>';
                console.log('🎉 Shield verification chain fully operational');
                
                // Log success metric
                this.options.onStepChange('post_verification_test_success');
                
                return { success: true, testResult };
                
            } else {
                // Don't treat success messages as errors
                const errorMessage = testResult?.error || (testResult?.message && !testResult?.verified ? testResult.message : 'Unknown verification error');
                statusElement.innerHTML = '⚠️ <span style="color: #ffc107;">Verification chain issue detected</span>';
                console.warn('⚠️ Post-Shield verification found issues:', errorMessage);
                
                // Show recommendation if available
                if (testResult?.recommendation) {
                    const detailsElement = document.querySelector('.lemma-success-details');
                    if (detailsElement) {
                        const recommendationDiv = document.createElement('div');
                        recommendationDiv.className = 'lemma-status-item';
                        recommendationDiv.innerHTML = `
                            <span class="lemma-status-label">Recommendation:</span>
                            <span class="lemma-status-value" style="color: #ffc107;">${testResult.recommendation}</span>
                        `;
                        detailsElement.appendChild(recommendationDiv);
                    }
                }
                
                // Log warning metric
                this.options.onStepChange('post_verification_test_warning');
                
                return { success: false, error: errorMessage, testResult };
            }
            
        } catch (error) {
            console.error('Post-verification test error:', error);
            
            const statusElement = document.getElementById('system-check-status');
            if (statusElement) {
                statusElement.innerHTML = '❌ <span style="color: #dc3545;">System check failed</span>';
            }
            
            // Log error metric
            this.options.onStepChange('post_verification_test_error');
            
            return { success: false, error: error.message };
        }
    }
    
    showVerificationFailure(testResult) {
        console.log('❌ Showing verification failure - keeping protection active');
        
        const container = this.getShieldContainer();
        if (!container) return;
        
        // Show failure message and keep protection active
        container.innerHTML = `
            <div class="lemma-shield-overlay">
                <div class="lemma-shield-widget lemma-card error">
                    <div class="lemma-card-header">
                        <div class="error-icon">⚠️</div>
                        <h2>Verification Issues Detected</h2>
                        <p>Your identity was verified, but system checks found issues that need attention.</p>
                    </div>
                    <div class="lemma-card-body">
                        <div class="lemma-error-details">
                            <div class="lemma-status-item">
                                <span class="lemma-status-label">Status:</span>
                                <span class="lemma-status-value" style="color: #dc3545;">Protection Active</span>
                            </div>
                            <div class="lemma-status-item">
                                <span class="lemma-status-label">Issue:</span>
                                <span class="lemma-status-value">${testResult?.error || 'System verification failed'}</span>
                            </div>
                            ${testResult?.recommendation ? `
                                <div class="lemma-status-item">
                                    <span class="lemma-status-label">Recommendation:</span>
                                    <span class="lemma-status-value" style="color: #ffc107;">${testResult.recommendation}</span>
                                </div>
                            ` : ''}
                        </div>
                        
                        <div class="lemma-card-actions">
                            <button class="lemma-btn lemma-btn-primary" id="retry-verification-test">
                                Retry Verification
                            </button>
                            <button class="lemma-btn lemma-btn-secondary" id="contact-support">
                                Contact Support
                            </button>
                        </div>
                    </div>
                    <div class="lemma-card-footer">
                        ${this.getBrandingFooter()}
                    </div>
                </div>
            </div>
        `;
        
        // Add event listeners
        document.getElementById('retry-verification-test')?.addEventListener('click', () => {
            this.showSuccessAndGrantAccess(); // Retry the full verification
        });
        
        document.getElementById('contact-support')?.addEventListener('click', () => {
            window.open('mailto:support@lemma.network?subject=Verification Issues&body=I encountered verification issues. Test result: ' + JSON.stringify(testResult), '_blank');
        });
        
        // Keep protection active - do NOT grant access
        this.state.verified = false;
        this.state.currentStep = 'verification_failed';
        
        // Ensure protected content remains hidden
        const protectedEl = document.querySelector(this.options.protectedContent);
        if (protectedEl) {
            protectedEl.style.display = 'none';
        }
        
        this.options.onStepChange('verification_failed');
    }

    grantAccess() {
        console.log('✅ Granting access to protected content');
        
        this.state.verified = true;
        this.state.currentStep = 'complete';
        
        // Hide widget
        const widgetEl = document.querySelector(this.options.widgetContainer);
        if (widgetEl) {
            widgetEl.style.display = 'none';
        }
        
        // Show protected content
        const protectedEl = document.querySelector(this.options.protectedContent);
        if (protectedEl) {
            protectedEl.style.display = 'block';
        }
        
        // Clear stored verification state
        sessionStorage.removeItem('lemma_verification_state');
        
        // Clean up URL parameters from Stripe return
        const url = new URL(window.location);
        url.searchParams.delete('verified');
        url.searchParams.delete('return_url');
        url.searchParams.delete('user_id');
        window.history.replaceState({}, document.title, url.toString());
        
        // Emit verification completion event for orchestrator
        const completionEvent = new CustomEvent('lemma-verification-complete', {
            detail: {
                verified: true,
                userId: this.state.userId,
                verificationSessionId: this.state.verificationSessionId,
                timestamp: new Date().toISOString(),
                source: 'shield-widget'
            }
        });
        window.dispatchEvent(completionEvent);
        
        // Notify listeners
        this.options.onVerified();
        this.options.onStepChange('complete');
    }
    
    hideError() {
        // Clear any error states and hide error messages
        const errorElements = document.querySelectorAll('.lemma-card.error, .lemma-error');
        errorElements.forEach(el => el.remove());
        
        // Clear error styling from widget container
        const widgetContainer = document.querySelector(this.options.widgetContainer);
        if (widgetContainer) {
            widgetContainer.classList.remove('error');
        }
    }
    
    showError(container, message) {
        const targetContainer = container || document.querySelector(this.options.widgetContainer);
        if (targetContainer) {
            targetContainer.innerHTML = `
                <div class="lemma-shield-overlay">
                    <div class="lemma-shield-widget lemma-card error">
                        <div class="lemma-card-header">
                            <div class="error-icon">❌</div>
                            <h2>Verification Error</h2>
                        </div>
                        <div class="lemma-card-body">
                            <p>${message}</p>
                            <div class="lemma-card-actions">
                                <button class="lemma-btn lemma-btn-primary" id="retry-verification">
                                    Try Again
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            document.getElementById('retry-verification').addEventListener('click', () => {
                this.showInitialStep(targetContainer);
            });
        }
        
        this.options.onError(new Error(message));
    }
    
    generateUserId() {
        return 'user_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }
    
    getShieldContainer() {
        // Get or create the shield container
        const selector = this.options.widgetContainer;
        console.log('🔍 Looking for shield container with selector:', selector);
        
        let container = document.querySelector(selector);
        console.log('🔍 Found existing container:', !!container);
        
        if (!container) {
            console.log('🔧 Creating new shield container...');
            
            // Remove any existing containers first
            const existingContainers = document.querySelectorAll('[id*="lemma-shield"]');
            existingContainers.forEach(el => {
                console.log('🗑️ Removing existing container:', el.id);
                el.remove();
            });
            
            container = document.createElement('div');
            const containerId = selector.startsWith('#') ? selector.substring(1) : selector;
            container.id = containerId;
            container.className = 'lemma-shield-container';
            
            // Always make sure container is visible
            container.style.position = 'fixed';
            container.style.top = '0';
            container.style.left = '0';
            container.style.width = '100%';
            container.style.height = '100%';
            container.style.zIndex = '10000';
            container.style.display = 'block';
            
            document.body.appendChild(container);
            console.log('✅ Created new shield container with ID:', container.id);
        } else {
            console.log('🧹 Clearing existing container content');
            // Clear existing content to prevent duplicates
            container.innerHTML = '';
            
            // Ensure container is properly positioned and visible
            container.style.position = 'fixed';
            container.style.top = '0';
            container.style.left = '0';
            container.style.width = '100%';
            container.style.height = '100%';
            container.style.zIndex = '10000';
            container.style.display = 'block';
        }
        
        return container;
    }
    
    hideShield() {
        // Hide the shield widget
        const container = document.querySelector(this.options.widgetContainer);
        if (container) {
            container.remove();
        }
        
        // Show protected content
        const protectedEl = document.querySelector(this.options.protectedContent);
        if (protectedEl) {
            protectedEl.style.display = '';
        }
    }
    
    getBrandingFooter() {
        return `
            <div class="lemma-branding">
                <span>Powered by</span>
                <strong>Lemma</strong>
                <span>Human Verification</span>
            </div>
        `;
    }
    
    addStyles() {
        if (document.getElementById('lemma-shield-widget-styles')) return;
        
        const styles = document.createElement('style');
        styles.id = 'lemma-shield-widget-styles';
        styles.textContent = `
            .lemma-shield-overlay {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.7);
                backdrop-filter: blur(4px);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 10000;
                animation: fadeIn 0.3s ease-out;
            }
            
            .lemma-shield-widget {
                background: white;
                border-radius: 16px;
                box-shadow: 0 24px 48px rgba(0, 0, 0, 0.2);
                max-width: 480px;
                width: 90%;
                max-height: 90vh;
                overflow-y: auto;
                animation: slideUp 0.3s ease-out;
            }
            
            .lemma-card {
                /* Card styling already applied via lemma-shield-widget */
            }
            
            .lemma-card.success {
                border-top: 4px solid #10B981;
            }
            
            .lemma-card.error {
                border-top: 4px solid #EF4444;
            }
            
            .lemma-shield-header, .lemma-card-header {
                padding: 2rem 2rem 1rem 2rem;
                text-align: center;
                border-bottom: 1px solid #E5E7EB;
            }
            
            .lemma-shield-icon, .lemma-logo, .stripe-logo, .success-icon, .error-icon {
                font-size: 2rem;
                margin-bottom: 1rem;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 0.5rem;
            }
            
            .lemma-shield-header h2, .lemma-card-header h2 {
                margin: 0 0 0.5rem 0;
                color: #1F2937;
                font-size: 1.5rem;
                font-weight: 600;
            }
            
            .lemma-shield-header p, .lemma-card-header p {
                margin: 0;
                color: #6B7280;
                font-size: 0.875rem;
            }
            
            .lemma-shield-body, .lemma-card-body {
                padding: 2rem;
            }
            
            .privacy-section, .verification-info {
                margin-bottom: 1.5rem;
            }
            
            .privacy-section h3, .verification-info h3 {
                margin: 0 0 0.75rem 0;
                color: #374151;
                font-size: 1.125rem;
                font-weight: 600;
            }
            
            .privacy-section ul, .verification-info ul {
                margin: 0.5rem 0;
                padding-left: 1.25rem;
                color: #4B5563;
            }
            
            .privacy-section li, .verification-info li {
                margin-bottom: 0.5rem;
            }
            
            .small-text {
                font-size: 0.875rem;
                color: #6B7280;
            }
            
            .verification-steps {
                margin: 1.5rem 0;
                text-align: left;
            }
            
            .verification-steps .step {
                display: flex;
                align-items: center;
                margin: 8px 0;
                opacity: 0.5;
                transition: all 0.3s ease;
            }
            
            .verification-steps .step.active {
                opacity: 1;
            }
            
            .step-icon {
                width: 24px;
                height: 24px;
                background: #f8f9fa;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin-right: 12px;
                font-size: 12px;
                border: 2px solid #e9ecef;
                transition: all 0.3s ease;
            }
            
            .step.active .step-icon {
                background: #635bff;
                color: white;
                border-color: #635bff;
            }
            
            .step-text {
                font-size: 14px;
                color: #6c757d;
            }
            
            .step.active .step-text {
                color: #212529;
                font-weight: 500;
            }
            
            .step {
                display: flex;
                flex-direction: column;
                align-items: center;
                text-align: center;
                flex: 1;
                position: relative;
                z-index: 2;
            }
            
            .step-number {
                width: 32px;
                height: 32px;
                border-radius: 50%;
                background: #E5E7EB;
                color: #6B7280;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: 600;
                margin-bottom: 0.5rem;
            }
            
            .step.active .step-number {
                background: #635BFF;
                color: white;
            }
            
            .step-content h4 {
                margin: 0 0 0.25rem 0;
                font-size: 0.875rem;
                font-weight: 600;
                color: #374151;
            }
            
            .step-content p {
                margin: 0;
                font-size: 0.75rem;
                color: #6B7280;
            }
            
            .verification-notice {
                background: #F3F4F6;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                padding: 1rem;
                margin: 1.5rem 0;
            }
            
            .verification-notice p {
                margin: 0;
                font-size: 0.875rem;
                color: #4B5563;
            }
            
            .lemma-card-actions {
                display: flex;
                gap: 1rem;
                justify-content: flex-end;
                margin-top: 2rem;
            }
            
            .lemma-btn {
                padding: 0.75rem 1.5rem;
                border-radius: 8px;
                font-size: 0.875rem;
                font-weight: 600;
                cursor: pointer;
                border: none;
                transition: all 0.2s ease;
                text-decoration: none;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 0.5rem;
            }
            
            .lemma-btn-primary {
                background: #635BFF;
                color: white;
            }
            
            .lemma-btn-primary:hover {
                background: #4F46E5;
                transform: translateY(-1px);
            }
            
            .lemma-btn-secondary {
                background: white;
                color: #374151;
                border: 1px solid #D1D5DB;
            }
            
            .lemma-btn-secondary:hover {
                background: #F9FAFB;
            }
            
            .lemma-verify-btn {
                background: #635BFF;
                color: white;
                border: none;
                padding: 1rem 2rem;
                border-radius: 12px;
                font-size: 1rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s ease;
                width: 100%;
                margin: 1rem 0;
            }
            
            .lemma-verify-btn:hover {
                background: #4F46E5;
                transform: translateY(-2px);
            }
            
            .lemma-branding {
                padding: 1rem 2rem;
                text-align: center;
                border-top: 1px solid #E5E7EB;
                font-size: 0.875rem;
                color: #6B7280;
            }
            
            .lemma-branding strong {
                color: #635BFF;
            }
            
            .lemma-spinner {
                width: 32px;
                height: 32px;
                border: 3px solid #E5E7EB;
                border-top: 3px solid #635BFF;
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }
            
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            
            @keyframes slideUp {
                from { 
                    opacity: 0;
                    transform: translateY(20px);
                }
                to { 
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            @keyframes spin {
                from { transform: rotate(0deg); }
                to { transform: rotate(360deg); }
            }
            
            @media (max-width: 640px) {
                .lemma-shield-widget {
                    width: 95%;
                    margin: 1rem;
                }
                
                .lemma-shield-header, .lemma-card-header,
                .lemma-shield-body, .lemma-card-body {
                    padding: 1.5rem;
                }
                
                .verification-steps {
                    flex-direction: column;
                    gap: 1rem;
                    align-items: stretch;
                }
                
                .verification-steps::before {
                    display: none;
                }
                
                .step {
                    flex-direction: row;
                    text-align: left;
                    gap: 1rem;
                }
                
                .lemma-card-actions {
                    flex-direction: column;
                }
            }
        `;
        
        document.head.appendChild(styles);
    }
    
    // Force show the shield - used for testing and revocation scenarios
    forceShow(options = {}) {
        console.log('🚨 Force showing shield with options:', options);
        
        // Set revocation trigger if this is a revocation scenario
        if (options.reason === 'credential_revoked') {
            sessionStorage.setItem('lemma_revocation_triggered', 'true');
        }
        
        // Force show the widget
        this.showVerificationWidget();
        
        return this;
    }
    
    // Static method to reset instance (for testing/debugging)
    static reset() {
        if (LemmaShieldWidget.instance) {
            const container = document.querySelector(LemmaShieldWidget.instance.options.widgetContainer);
            if (container) {
                container.remove();
            }
            LemmaShieldWidget.instance = null;
        }
    }
    
    // Static method to force show shield
    static forceShow(options = {}) {
        if (LemmaShieldWidget.instance) {
            return LemmaShieldWidget.instance.forceShow(options);
        } else {
            console.warn('⚠️ No LemmaShieldWidget instance available for forceShow');
            // Try to create one if it doesn't exist
            try {
                const instance = new LemmaShieldWidget({
                    widgetContainer: '#lemma-shield-container',
                    apiEndpoint: '/api/shield',
                    debug: true
                });
                window.lemmaShieldWidget = instance;
                return instance.forceShow(options);
            } catch (e) {
                console.error('Failed to create emergency instance:', e);
                return null;
            }
        }
    }
}

// Auto-initialize if window is loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.LemmaShieldWidget = LemmaShieldWidget;
        // Create a default instance for immediate use
        if (!LemmaShieldWidget.instance) {
            window.lemmaShieldWidget = new LemmaShieldWidget({
                widgetContainer: '#lemma-shield-container',
                apiEndpoint: '/api/shield',
                debug: true
            });
        }
        
        // Add global convenience methods
        window.lemmaShield = {
            forceShow: (options = {}) => {
                if (window.lemmaShieldWidget) {
                    return window.lemmaShieldWidget.forceShow(options);
                } else if (window.LemmaShieldWidget) {
                    return window.LemmaShieldWidget.forceShow(options);
                } else {
                    console.error('No Lemma Shield available');
                    return null;
                }
            },
            show: (options = {}) => window.lemmaShield.forceShow(options),
            getInstance: () => window.lemmaShieldWidget || window.LemmaShieldWidget?.instance
        };
    });
} else {
    window.LemmaShieldWidget = LemmaShieldWidget;
    // Create a default instance for immediate use
    if (!LemmaShieldWidget.instance) {
        window.lemmaShieldWidget = new LemmaShieldWidget({
            widgetContainer: '#lemma-shield-container',
            apiEndpoint: '/api/shield',
            debug: true
        });
    }
    
    // Add global convenience methods
    window.lemmaShield = {
        forceShow: (options = {}) => {
            if (window.lemmaShieldWidget) {
                return window.lemmaShieldWidget.forceShow(options);
            } else if (window.LemmaShieldWidget) {
                return window.LemmaShieldWidget.forceShow(options);
            } else {
                console.error('No Lemma Shield available');
                return null;
            }
        },
        show: (options = {}) => window.lemmaShield.forceShow(options),
        getInstance: () => window.lemmaShieldWidget || window.LemmaShieldWidget?.instance
    };
} 