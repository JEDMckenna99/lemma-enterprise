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
        this.init();
    }
    
    async init() {
        console.log('🛡️ Initializing Lemma Shield Widget');
        
        // Wait for wallet to be available
        await this.waitForWallet();
        
        // Check if we're returning from Stripe verification
        await this.checkForReturnFromVerification();
        
        // Check initial status
        await this.checkStatus();
    }
    
    async waitForWallet() {
        return new Promise((resolve) => {
            const checkWallet = () => {
                if (window.LemmaWallet) {
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
            // Use Shield API to check status
            const response = await fetch(`${this.options.apiBase}/api/shield/status?security_level=${this.options.securityLevel}`, {
                method: 'GET',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (!response.ok) {
                throw new Error(`Shield status check failed: ${response.status}`);
            }
            
            const result = await response.json();
            if (!result.success) {
                throw new Error(result.error || 'Shield status check failed');
            }
            
            await this.handleShieldAction(result);
            
        } catch (error) {
            console.error('❌ Shield status check failed:', error);
            this.showVerificationWidget();
        }
    }
    
    async handleShieldAction(result) {
        const action = result.shield_action;
        console.log(`🛡️ Shield action: ${action}`);
        
        switch (action) {
            case 'allow_access':
                console.log('✅ Shield verification successful - allowing access');
                this.grantAccess();
                this.options.onVerified(result.data);
                break;
                
            case 'check_credentials':
            case 'show_shield':
                console.log('🔍 Shield needs verification - showing widget');
                this.showVerificationWidget();
                break;
                
            case 'require_reverification':
                console.log('⚠️ Shield requires re-verification');
                this.showVerificationWidget();
                break;
                
            case 'credential_revoked':
                console.log('❌ Shield detected revoked credential');
                this.showVerificationWidget();
                break;
                
            default:
                console.warn(`Unknown shield action: ${action}`);
                this.showVerificationWidget();
        }
        
        this.options.onStepChange(action);
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
            
            // Use redirect flow instead of inline for better UX and no CSS conflicts
            if (verificationData.verification_url) {
                console.log('🔄 Redirecting to Stripe Identity verification...');
                
                // Set a small delay to show the transition UI
                setTimeout(() => {
                    window.location.href = verificationData.verification_url;
                }, 1500);
            } else {
                console.error('❌ No verification URL provided');
                this.options.onError(new Error('No verification URL available'));
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
            
            // Wait a moment for Stripe to process
            await new Promise(resolve => setTimeout(resolve, 2000));
            
            // Check if verification was successful and get credential
            const result = await this.checkVerificationStatus();
            
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
                
                this.options.onVerified(result);
                this.hideShield();
            } else {
                const errorMessage = (result && result.error) ? result.error : 'Verification incomplete';
                console.error('❌ Verification not completed:', errorMessage);
                this.options.onError(new Error(errorMessage));
            }
            
        } catch (error) {
            console.error('❌ Failed to complete inline verification:', error);
            this.options.onError(error);
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
            
            const response = await fetch(`${this.options.apiBase}/api/shield/verify-credentials`, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    user_id: this.state.userId,
                    session_id: this.state.verificationSessionId || this.state.sessionId,
                    check_inline_verification: true
                })
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

    showVerificationWidget() {
        console.log('🛡️ Showing verification widget');
        
        // Hide protected content
        const protectedEl = document.querySelector(this.options.protectedContent);
        if (protectedEl) {
            protectedEl.style.display = 'none';
        }
        
        // Create widget container if it doesn't exist
        let widgetEl = document.querySelector(this.options.widgetContainer);
        if (!widgetEl) {
            widgetEl = document.createElement('div');
            widgetEl.id = this.options.widgetContainer.replace('#', '');
            document.body.appendChild(widgetEl);
        }
        
        // Show initial verification button
        this.showInitialStep(widgetEl);
        this.state.currentStep = 'initial';
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
        
        // Check if we have URL parameters indicating return from verification
        const hasReturnParams = urlParams.has('user_id') || urlParams.has('verified') || urlParams.has('verification_complete');
        
        // Check if current URL matches stored return URL
        const isReturnUrl = returnUrl && window.location.href.includes(returnUrl.split('?')[0]);
        
        if (hasReturnParams || isReturnUrl) {
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
            
            // Check verification status after a short delay
            setTimeout(() => {
                this.checkPostVerificationStatus();
            }, 2000);
            
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
    
    async checkVerificationStatus() {
        try {
            // Get CSRF token first
            const csrfResponse = await fetch(`${this.options.apiBase}/api/generate-csrf`, {
                credentials: 'same-origin'
            });
            const csrfData = await csrfResponse.json();
            const csrfToken = csrfData.csrf_token;
            
            const response = await fetch(`${this.options.apiBase}/api/shield/verify-credentials`, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    check_inline_verification: true,
                    user_id: this.state.userId,
                    session_id: this.state.verificationSessionId
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                
                if (result.success && result.verified) {
                    // Store credential and grant access
                    if (result.credential && this.wallet) {
                        await this.wallet.storeCredential(result.credential);
                    }
                    this.showSuccessAndGrantAccess();
                } else if (result.status === 'processing' || result.message === 'Verification in progress') {
                    // Still processing, try again in a few seconds
                    setTimeout(() => this.checkVerificationStatus(), 3000);
                } else {
                    // Failed
                    this.showError(null, result.message || 'Verification failed');
                }
            } else {
                // Try to get credential directly if verification check failed
                const credentialResponse = await fetch(`${this.options.apiBase}/api/credential-lookup/${this.state.userId}`, {
                    credentials: 'same-origin'
                });
                
                if (credentialResponse.ok) {
                    const credentialResult = await credentialResponse.json();
                    if (credentialResult.success && credentialResult.credential) {
                        await this.wallet.storeCredential(credentialResult.credential);
                        this.showSuccessAndGrantAccess();
                        return;
                    }
                }
                
                this.showError(null, 'Failed to verify credentials');
            }
            
        } catch (error) {
            console.error('❌ Status check failed:', error);
            this.showError(null, 'Failed to check verification status');
        }
    }
    
    async showSuccessAndGrantAccess() {
        this.hideError();
        
        // Show success message with verification animation
        this.ui.shieldContent.innerHTML = `
            <div class="lemma-success">
                <div class="lemma-success-icon">✅</div>
                <h3>Verification Complete!</h3>
                <p>You've been verified as a real human. Welcome to the Lemma Network!</p>
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
        `;
        
        // Automatically run end-to-end verification test
        this.runPostVerificationTest();
        
        // Grant access after showing success message
        setTimeout(() => {
            this.grantAccess();
        }, 3000); // Show success for 3 seconds, then grant access
    }
    
    /**
     * Run automatic end-to-end verification test after successful Shield verification
     */
    async runPostVerificationTest() {
        try {
            const statusElement = document.getElementById('system-check-status');
            if (!statusElement) return;

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
            
            if (testResult.success) {
                statusElement.innerHTML = '✅ <span style="color: #28a745;">All systems operational</span>';
                console.log('🎉 Shield verification chain fully operational');
                
                // Log success metric
                this.options.onStepChange('post_verification_test_success');
                
            } else {
                statusElement.innerHTML = '⚠️ <span style="color: #ffc107;">Verification chain issue detected</span>';
                console.warn('⚠️ Post-Shield verification found issues:', testResult.error);
                
                // Show recommendation if available
                if (testResult.recommendation) {
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
            }
            
        } catch (error) {
            console.error('Post-verification test error:', error);
            
            const statusElement = document.getElementById('system-check-status');
            if (statusElement) {
                statusElement.innerHTML = '❌ <span style="color: #dc3545;">System check failed</span>';
            }
            
            // Log error metric but don't block user access
            this.options.onStepChange('post_verification_test_error');
        }
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
        
        // Notify listeners
        this.options.onVerified();
        this.options.onStepChange('complete');
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
        let container = document.querySelector(this.options.widgetContainer);
        if (!container) {
            container = document.createElement('div');
            container.id = this.options.widgetContainer.replace('#', '');
            document.body.appendChild(container);
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
}

// Auto-initialize if window is loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.LemmaShieldWidget = LemmaShieldWidget;
    });
} else {
    window.LemmaShieldWidget = LemmaShieldWidget;
} 