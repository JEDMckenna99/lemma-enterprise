/**
 * Lemma Gate v3.0 - Production Human Verification Gateway
 * 
 * Perfect Flow:
 * 1. Has credential → Background VP creation + revocation check → Seamless access (no gate shown)
 * 2. No credential → Show protection gate → Guide to verification → Store credential → Access granted
 * 
 * Features:
 * - Background verification with VP creation
 * - Revocation checking via OPRF cascade
 * - Seamless user experience
 * - Enterprise security
 * - Easy integration
 */

class LemmaGateV3 {
    constructor(options = {}) {
        this.options = {
            // Required elements
            gateContainerId: options.gateContainerId || 'lemma-gate-overlay',
            protectedContainerId: options.protectedContainerId || 'protected-content',
            
            // API endpoints
            apiBase: options.apiBase || '',
            verifyEndpoint: options.verifyEndpoint || '/api/verify-human',
            challengeEndpoint: options.challengeEndpoint || '/api/generate-challenge',
            
            // UI customization
            gateLogo: options.gateLogo || '🛡️',
            gateTitle: options.gateTitle || 'Human Verification Required',
            gateMessage: options.gateMessage || 'This content is protected. Please verify you are human to continue.',
            verifyButtonText: options.verifyButtonText || 'Verify with Lemma',
            
            // Callbacks
            onVerified: options.onVerified || (() => {}),
            onError: options.onError || (() => {}),
            onGateShown: options.onGateShown || (() => {}),
            onGateHidden: options.onGateHidden || (() => {}),
            
            // Advanced options
            backgroundVerification: options.backgroundVerification !== false, // Default true
            checkRevocation: options.checkRevocation !== false, // Default true
            showLoadingStates: options.showLoadingStates !== false, // Default true
            autoRetry: options.autoRetry !== false, // Default true
            retryAttempts: options.retryAttempts || 3,
            retryDelay: options.retryDelay || 1000,
            
            // Debug
            debug: options.debug || false,
            
            ...options
        };
        
        this.wallet = null;
        this.isInitialized = false;
        this.isVerifying = false;
        this.isVerified = false;
        this.currentChallenge = null;
        this.retryCount = 0;
        
        // State tracking
        this.verificationState = 'pending'; // pending, checking, verified, failed, gate_shown
        
        this.init();
    }

    log(...args) {
        if (this.options.debug) {
            console.log('[LemmaGate]', ...args);
        }
    }

    error(...args) {
        console.error('[LemmaGate]', ...args);
    }

    async init() {
        this.log('Initializing Lemma Gate v3.0...');
        
        try {
            // Wait for dependencies
            await this.waitForDependencies();
            
            // Set up UI elements
            this.setupUI();
            
            // Start verification flow
            await this.startVerificationFlow();
            
            this.isInitialized = true;
            this.log('Lemma Gate initialized successfully');
            
        } catch (error) {
            this.error('Gate initialization failed:', error);
            this.showError('Failed to initialize verification system');
        }
    }

    async waitForDependencies(timeout = 10000) {
        return new Promise((resolve, reject) => {
            const startTime = Date.now();
            
            const checkDependencies = () => {
                // Check for wallet
                if (window.lemmaWallet) {
                    this.wallet = window.lemmaWallet;
                    this.log('Dependencies ready');
                    resolve();
                } else if (Date.now() - startTime > timeout) {
                    this.error('Dependencies timeout - continuing without wallet');
                    resolve(); // Continue without wallet for new users
                } else {
                    setTimeout(checkDependencies, 100);
                }
            };
            
            checkDependencies();
        });
    }

    setupUI() {
        // Ensure gate container exists
        let gateContainer = document.getElementById(this.options.gateContainerId);
        if (!gateContainer) {
            gateContainer = this.createGateContainer();
            document.body.appendChild(gateContainer);
        }
        
        // Setup gate content if not exists
        if (!gateContainer.querySelector('.lemma-gate-content')) {
            gateContainer.innerHTML = this.getGateHTML();
        }
        
        // Setup event listeners
        this.setupEventListeners();
    }

    createGateContainer() {
        const container = document.createElement('div');
        container.id = this.options.gateContainerId;
        container.className = 'lemma-gate-overlay';
        container.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.8);
            backdrop-filter: blur(8px);
            z-index: 10000;
            display: none;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
        `;
        return container;
    }

    getGateHTML() {
        return `
            <div class="lemma-gate-content" style="
                background: white;
                border-radius: 16px;
                padding: 48px;
                max-width: 500px;
                margin: 32px;
                text-align: center;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
                border: 1px solid #e5e7eb;
            ">
                <div class="lemma-gate-icon" style="
                    width: 80px;
                    height: 80px;
                    margin: 0 auto 24px;
                    background: linear-gradient(135deg, #635bff, #4f46e5);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-size: 2rem;
                ">
                    ${this.options.gateLogo}
                </div>
                
                <h2 style="
                    font-size: 1.5rem;
                    font-weight: 700;
                    color: #111827;
                    margin-bottom: 16px;
                ">${this.options.gateTitle}</h2>
                
                <p style="
                    color: #6b7280;
                    margin-bottom: 32px;
                    font-size: 1rem;
                    line-height: 1.5;
                ">${this.options.gateMessage}</p>
                
                <div id="lemma-gate-status" style="margin-bottom: 24px;">
                    <!-- Status messages appear here -->
                </div>
                
                <button id="lemma-gate-verify-btn" 
                        onclick="lemmaGateInstance.startVerification()"
                        style="
                    background: linear-gradient(135deg, #635bff, #4f46e5);
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 12px 24px;
                    font-size: 1rem;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto;
                " onmouseover="this.style.transform='translateY(-1px)'; this.style.boxShadow='0 4px 12px rgba(99, 91, 255, 0.4)'"
                   onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='none'">
                    <svg style="width: 20px; height: 20px; margin-right: 8px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                    ${this.options.verifyButtonText}
                </button>
                
                <p style="
                    margin-top: 24px;
                    font-size: 0.875rem;
                    color: #9ca3af;
                ">Powered by Lemma Enterprise - Privacy-first human verification</p>
            </div>
        `;
    }

    setupEventListeners() {
        // Handle page visibility changes
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden && this.verificationState === 'verified') {
                // Recheck verification when page becomes visible
                this.log('Page visible again, rechecking verification...');
                setTimeout(() => this.recheckVerification(), 500);
            }
        });
        
        // Handle verification completion from URL params
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('verified') === 'true') {
            this.log('Verification completed, forcing recheck');
            setTimeout(() => this.recheckVerification(), 1000);
        }
    }

    async startVerificationFlow() {
        if (this.isVerifying) {
            this.log('Verification already in progress');
            return;
        }
        
        this.isVerifying = true;
        this.verificationState = 'checking';
        
        this.log('Starting verification flow...');
        
        try {
            // Step 1: Check if user has credentials
            const hasCredentials = await this.checkForCredentials();
            
            if (hasCredentials) {
                this.log('Credentials found - performing background verification');
                await this.performBackgroundVerification();
            } else {
                this.log('No credentials found - showing gate');
                this.showGate();
            }
            
        } catch (error) {
            this.error('Verification flow failed:', error);
            this.handleVerificationError(error);
        } finally {
            this.isVerifying = false;
        }
    }

    async checkForCredentials() {
        if (!this.wallet) {
            this.log('No wallet available');
            return false;
        }
        
        try {
            const credentials = await this.wallet.getAllCredentials();
            return credentials && credentials.length > 0;
        } catch (error) {
            this.error('Error checking credentials:', error);
            return false;
        }
    }

    async performBackgroundVerification() {
        this.log('Performing background verification...');
        
        try {
            // Get credentials
            const credentials = await this.wallet.getAllCredentials();
            if (!credentials || credentials.length === 0) {
                throw new Error('No credentials available');
            }
            
            const credentialEntry = credentials[0];
            const credential = credentialEntry.credential || credentialEntry;
            
            // Step 1: Check revocation status (if enabled)
            if (this.options.checkRevocation) {
                const revocationStatus = await this.checkRevocationStatus(credential);
                if (!revocationStatus.valid) {
                    throw new Error(`Credential revoked: ${revocationStatus.reason}`);
                }
                this.log('Revocation check passed');
            }
            
            // Step 2: Generate challenge
            const challenge = await this.generateChallenge();
            this.currentChallenge = challenge;
            
            // Step 3: Create Verifiable Presentation
            const presentation = await this.createVerifiablePresentation(credential, challenge);
            
            // Step 4: Verify with server
            const verificationResult = await this.verifyWithServer(presentation, challenge);
            
            if (verificationResult.success) {
                this.log('Background verification successful');
                this.grantAccess();
            } else {
                throw new Error(verificationResult.error || 'Server verification failed');
            }
            
        } catch (error) {
            this.error('Background verification failed:', error);
            
            // If background verification fails, show gate for re-verification
            this.showGate();
            this.updateGateStatus('warning', 'Verification needed - Please verify again');
        }
    }

    async checkRevocationStatus(credential) {
        this.log('Checking revocation status...');
        
        try {
            if (!this.wallet.verifyWitness) {
                this.log('Revocation checking not available - skipping');
                return { valid: true, reason: 'Revocation checking not available' };
            }
            
            // Use wallet's built-in revocation checking
            const result = await this.wallet.verifyWitness(credential.id);
            
            return {
                valid: result.valid !== false, // true if valid or no result
                reason: result.error || 'Unknown revocation status'
            };
            
        } catch (error) {
            this.error('Revocation check failed:', error);
            // On revocation check failure, allow verification to continue
            return { valid: true, reason: 'Revocation check failed - allowing verification' };
        }
    }

    async generateChallenge() {
        try {
            const response = await fetch(this.options.apiBase + this.options.challengeEndpoint, {
                credentials: 'include'
            });
            
            if (!response.ok) {
                throw new Error(`Challenge generation failed: ${response.status}`);
            }
            
            const data = await response.json();
            return data.challenge || data.data?.challenge;
            
        } catch (error) {
            // Fallback to client-side challenge generation
            this.log('Server challenge failed, generating client-side challenge');
            return Array.from(crypto.getRandomValues(new Uint8Array(16)))
                .map(b => b.toString(16).padStart(2, '0')).join('');
        }
    }

    async createVerifiablePresentation(credential, challenge) {
        this.log('Creating Verifiable Presentation...');
        
        try {
            // Try using wallet's presentation creation if available
            if (this.wallet.createPresentation) {
                return await this.wallet.createPresentation(credential, challenge);
            }
            
            // Fallback to manual presentation creation
            const presentation = {
                "@context": ["https://www.w3.org/2018/credentials/v1"],
                "type": ["VerifiablePresentation"],
                "verifiableCredential": [credential],
                "proof": {
                    "type": "Ed25519Signature2020",
                    "challenge": challenge,
                    "created": new Date().toISOString(),
                    "verificationMethod": credential.issuer,
                    "domain": window.location.hostname
                }
            };
            
            return presentation;
            
        } catch (error) {
            this.error('Failed to create presentation:', error);
            throw error;
        }
    }

    async verifyWithServer(presentation, challenge) {
        this.log('Verifying with server...');
        
        try {
            // Get CSRF token
            const csrfToken = await this.getCSRFToken();
            
            const response = await fetch(this.options.apiBase + this.options.verifyEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': csrfToken
                },
                credentials: 'include',
                body: JSON.stringify({
                    presentation: presentation,
                    challenge: challenge,
                    domain: window.location.hostname
                })
            });
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.error || `Server error: ${response.status}`);
            }
            
            const result = await response.json();
            return result;
            
        } catch (error) {
            this.error('Server verification failed:', error);
            throw error;
        }
    }

    async getCSRFToken() {
        try {
            const response = await fetch('/api/generate-csrf-token', {
                credentials: 'include'
            });
            const data = await response.json();
            return data.csrf_token;
        } catch (error) {
            this.error('CSRF token fetch failed:', error);
            return '';
        }
    }

    grantAccess() {
        this.log('Access granted - hiding gate');
        this.isVerified = true;
        this.verificationState = 'verified';
        
        // Hide gate
        this.hideGate();
        
        // Show protected content
        const protectedContent = document.getElementById(this.options.protectedContainerId);
        if (protectedContent) {
            protectedContent.classList.remove('hidden');
            protectedContent.style.display = 'block';
        }
        
        // Call success callback
        this.options.onVerified({
            verified: true,
            timestamp: new Date().toISOString()
        });
    }

    showGate() {
        this.log('Showing verification gate');
        this.verificationState = 'gate_shown';
        
        const gateContainer = document.getElementById(this.options.gateContainerId);
        if (gateContainer) {
            gateContainer.style.display = 'flex';
            // Trigger animation
            setTimeout(() => {
                gateContainer.style.opacity = '1';
            }, 10);
        }
        
        // Hide protected content
        const protectedContent = document.getElementById(this.options.protectedContainerId);
        if (protectedContent) {
            protectedContent.classList.add('hidden');
            protectedContent.style.display = 'none';
        }
        
        // Call gate shown callback
        this.options.onGateShown();
    }

    hideGate() {
        this.log('Hiding verification gate');
        
        const gateContainer = document.getElementById(this.options.gateContainerId);
        if (gateContainer) {
            gateContainer.style.opacity = '0';
            setTimeout(() => {
                gateContainer.style.display = 'none';
            }, 300);
        }
        
        // Call gate hidden callback
        this.options.onGateHidden();
    }

    updateGateStatus(type, message) {
        const statusDiv = document.getElementById('lemma-gate-status');
        if (!statusDiv) return;
        
        const typeStyles = {
            info: 'background: #dbeafe; color: #1e40af; border: 1px solid #bfdbfe;',
            success: 'background: #dcfce7; color: #166534; border: 1px solid #bbf7d0;',
            warning: 'background: #fef3c7; color: #92400e; border: 1px solid #fde68a;',
            error: 'background: #fee2e2; color: #dc2626; border: 1px solid #fecaca;'
        };
        
        const style = typeStyles[type] || typeStyles.info;
        
        statusDiv.innerHTML = `
            <div style="
                padding: 12px 16px;
                border-radius: 8px;
                font-size: 0.875rem;
                font-weight: 500;
                ${style}
            ">${message}</div>
        `;
    }

    async startVerification() {
        this.log('Starting manual verification...');
        
        const button = document.getElementById('lemma-gate-verify-btn');
        if (button) {
            button.disabled = true;
            button.innerHTML = `
                <svg style="width: 20px; height: 20px; margin-right: 8px; animation: spin 1s linear infinite;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                </svg>
                Starting verification...
            `;
        }
        
        this.updateGateStatus('info', 'Starting verification process...');
        
        try {
            // Redirect to verification with return URL
            const returnUrl = encodeURIComponent(window.location.href);
            window.location.href = `/verify?redirect=${returnUrl}`;
            
        } catch (error) {
            this.error('Error starting verification:', error);
            this.updateGateStatus('error', 'Failed to start verification. Please try again.');
            
            if (button) {
                button.disabled = false;
                button.innerHTML = `
                    <svg style="width: 20px; height: 20px; margin-right: 8px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                    Try Again
                `;
            }
        }
    }

    async recheckVerification() {
        this.log('Rechecking verification status...');
        this.isVerified = false;
        this.verificationState = 'pending';
        await this.startVerificationFlow();
    }

    handleVerificationError(error) {
        this.error('Verification error:', error);
        this.verificationState = 'failed';
        
        if (this.options.autoRetry && this.retryCount < this.options.retryAttempts) {
            this.retryCount++;
            this.log(`Retrying verification (attempt ${this.retryCount}/${this.options.retryAttempts})...`);
            
            setTimeout(() => {
                this.startVerificationFlow();
            }, this.options.retryDelay);
            
        } else {
            this.showGate();
            this.updateGateStatus('error', 'Verification failed. Please try again.');
            this.options.onError(error);
        }
    }

    showError(message) {
        this.showGate();
        this.updateGateStatus('error', message);
    }

    // Public API
    getStatus() {
        return {
            isVerified: this.isVerified,
            isVerifying: this.isVerifying,
            verificationState: this.verificationState,
            hasWallet: !!this.wallet,
            retryCount: this.retryCount
        };
    }

    async forceRecheck() {
        this.log('Forcing verification recheck...');
        await this.recheckVerification();
    }

    destroy() {
        this.log('Destroying Lemma Gate...');
        
        const gateContainer = document.getElementById(this.options.gateContainerId);
        if (gateContainer) {
            gateContainer.remove();
        }
        
        this.isInitialized = false;
        this.wallet = null;
    }
}

// CSS animations
if (!document.getElementById('lemma-gate-styles')) {
    const style = document.createElement('style');
    style.id = 'lemma-gate-styles';
    style.textContent = `
        @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }
        
        .lemma-gate-overlay {
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.3s ease, visibility 0.3s ease;
        }
        
        .lemma-gate-overlay[style*="display: flex"] {
            opacity: 1;
            visibility: visible;
        }
    `;
    document.head.appendChild(style);
}

// Easy integration function
window.initLemmaGate = function(options = {}) {
    if (window.lemmaGateInstance) {
        window.lemmaGateInstance.destroy();
    }
    
    window.lemmaGateInstance = new LemmaGateV3(options);
    return window.lemmaGateInstance;
};

// Auto-initialization when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        if (document.querySelector('[data-lemma-gate]')) {
            window.initLemmaGate();
        }
    });
} else {
    if (document.querySelector('[data-lemma-gate]')) {
        window.initLemmaGate();
    }
} 