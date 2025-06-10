/**
 * Lemma Gate - Production Human Verification Gateway
 * 
 * Flow:
 * 1. No credential → Show gate → Stripe Identity verification → Store credential → Access content
 * 2. Has credential → Background DID + revocation check → Seamless access
 */

class LemmaGate {
  constructor(options = {}) {
    this.options = {
      // Required elements
      gateContainerId: options.gateContainerId || 'lemma-gate',
      protectedContainerId: options.protectedContainerId || 'protected-content',
      
      // API endpoints
      lemmaApiBase: options.lemmaApiBase || '',
      verifyEndpoint: options.verifyEndpoint || '/api/verify-human',
      startVerificationEndpoint: options.startVerificationEndpoint || '/api/start-verification',
      
      // UI customization
      verifyButtonText: options.verifyButtonText || '🤖 Verify Human Identity',
      loadingText: options.loadingText || 'Verifying your identity...',
      
      // Callbacks
      onVerified: options.onVerified || (() => {}),
      onError: options.onError || (() => {}),
      
      // Debug
      debug: options.debug || false,
      
      ...options
    };
    
    this.wallet = null;
    this.isVerifying = false;
    this.isVerified = false;
    
    this.init();
  }

  log(message, data = null) {
    if (this.options.debug) {
      console.log(`[LemmaGate] ${message}`, data || '');
    }
  }

  async init() {
    this.log('Initializing Lemma Gate...');
    
    try {
      // Wait for wallet to be available
      await this.waitForWallet();
      
      // Set up gate UI
      this.setupGateUI();
      
      // Check verification status
      await this.checkAndVerify();
      
    } catch (error) {
      this.log('Gate initialization failed', error);
      this.showError('Failed to initialize human verification');
    }
  }

  async waitForWallet(timeout = 5000) {
    return new Promise((resolve, reject) => {
      const startTime = Date.now();
      
      const checkWallet = () => {
        if (window.lemmaWallet) {
          this.wallet = window.lemmaWallet;
          this.log('Wallet found');
          resolve();
        } else if (Date.now() - startTime > timeout) {
          this.log('Wallet timeout - proceeding without wallet');
          resolve(); // Proceed without wallet for new users
        } else {
          setTimeout(checkWallet, 100);
        }
      };
      
      checkWallet();
    });
  }

  async checkAndVerify() {
    if (this.isVerifying) return;
    
    this.isVerifying = true;
    this.showLoading();
    
    try {
      // Check if user has Lemma credentials
      const hasCredentials = await this.hasValidCredentials();
      
      if (hasCredentials) {
        this.log('Found credentials - performing background verification');
        await this.performBackgroundVerification();
      } else {
        this.log('No credentials found - showing gate');
        this.showGate();
      }
      
    } catch (error) {
      this.log('Verification check failed', error);
      this.showGate(); // Fallback to gate if check fails
    } finally {
      this.isVerifying = false;
    }
  }

  async hasValidCredentials() {
    if (!this.wallet) return false;
    
    try {
      const credentials = await this.wallet.getAllCredentials();
      return credentials && credentials.length > 0;
    } catch (error) {
      this.log('Error checking credentials', error);
      return false;
    }
  }

  async performBackgroundVerification() {
    try {
      const credentials = await this.wallet.getAllCredentials();
      if (!credentials || credentials.length === 0) {
        throw new Error('No credentials available');
      }
      
      const credential = credentials[0];
      
      // Generate nonce for verification
      const nonce = this.generateNonce();
      
      // Create presentation for server verification
      const presentation = await this.createPresentation(credential, nonce);
      
      // Verify with server (includes DID check and revocation check)
      const verificationResult = await this.verifyWithServer(presentation, nonce);
      
      if (verificationResult.success) {
        this.log('Background verification successful');
        this.grantAccess();
      } else {
        this.log('Background verification failed', verificationResult.error);
        this.showGate();
      }
      
    } catch (error) {
      this.log('Background verification error', error);
      this.showGate();
    }
  }

  async createPresentation(credential, nonce) {
    try {
      // Create a simple presentation with the credential and nonce
      const presentation = {
        "@context": ["https://www.w3.org/2018/credentials/v1"],
        "type": ["VerifiablePresentation"],
        "verifiableCredential": [credential.credential || credential],
        "proof": {
          "type": "Ed25519Signature2020",
          "challenge": nonce,
          "created": new Date().toISOString(),
          "verificationMethod": credential.credential?.issuer || credential.issuer
        }
      };
      
      return presentation;
    } catch (error) {
      this.log('Error creating presentation', error);
      throw error;
    }
  }

  async verifyWithServer(presentation, nonce) {
    try {
      const response = await fetch(this.options.verifyEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          presentation: presentation,
          challenge: nonce,
          domain: window.location.hostname
        })
      });
      
      if (!response.ok) {
        throw new Error(`Server verification failed: ${response.status}`);
      }
      
      return await response.json();
      
    } catch (error) {
      this.log('Server verification error', error);
      throw error;
    }
  }

  async startStripeVerification() {
    if (this.isVerifying) return;
    
    this.isVerifying = true;
    this.showLoading('Starting identity verification...');
    
    try {
      // Generate user ID for verification
      const userId = this.generateUserId();
      
      // Start verification session
      const response = await fetch(this.options.startVerificationEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          user_id: userId,
          return_url: window.location.href
        })
      });
      
      if (!response.ok) {
        throw new Error('Failed to start verification session');
      }
      
      const result = await response.json();
      
      if (result.success && result.url) {
        this.log('Redirecting to Stripe Identity verification');
        // Store user ID for when they return
        sessionStorage.setItem('lemma_verification_user_id', userId);
        // Redirect to Stripe Identity
        window.location.href = result.url;
      } else {
        throw new Error(result.error || 'Failed to create verification session');
      }
      
    } catch (error) {
      this.log('Stripe verification start failed', error);
      this.showError('Failed to start identity verification');
      this.isVerifying = false;
    }
  }

  setupGateUI() {
    const gateContainer = document.getElementById(this.options.gateContainerId);
    if (!gateContainer) {
      this.log('Gate container not found');
      return;
    }
    
    gateContainer.innerHTML = `
      <div class="lemma-gate-overlay">
        <div class="lemma-gate-modal">
          <!-- Loading State -->
          <div id="lemma-gate-loading" class="lemma-gate-state" style="display: none;">
            <div class="lemma-gate-spinner"></div>
            <h3>Verifying Identity</h3>
            <p>${this.options.loadingText}</p>
          </div>
          
          <!-- Gate State -->
          <div id="lemma-gate-verify" class="lemma-gate-state" style="display: none;">
            <div class="lemma-gate-icon">🔒</div>
            <h3>Human Verification Required</h3>
            <p>This content is protected by Lemma human verification.</p>
            <button id="lemma-verify-btn" class="lemma-btn-primary">
              ${this.options.verifyButtonText}
            </button>
            <p class="lemma-gate-privacy">
              <small>🔐 Privacy-first verification • No personal data stored</small>
            </p>
          </div>
          
          <!-- Error State -->
          <div id="lemma-gate-error" class="lemma-gate-state" style="display: none;">
            <div class="lemma-gate-icon">⚠️</div>
            <h3>Verification Error</h3>
            <p id="lemma-error-message">An error occurred during verification.</p>
            <button id="lemma-retry-btn" class="lemma-btn-secondary">Try Again</button>
          </div>
        </div>
      </div>
    `;
    
    // Add event listeners
    const verifyBtn = document.getElementById('lemma-verify-btn');
    const retryBtn = document.getElementById('lemma-retry-btn');
    
    if (verifyBtn) {
      verifyBtn.addEventListener('click', () => this.startStripeVerification());
    }
    
    if (retryBtn) {
      retryBtn.addEventListener('click', () => this.checkAndVerify());
    }
    
    // Add CSS if not already present
    this.addGateStyles();
  }

  addGateStyles() {
    if (document.getElementById('lemma-gate-styles')) return;
    
    const styles = document.createElement('style');
    styles.id = 'lemma-gate-styles';
    styles.textContent = `
      .lemma-gate-overlay {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.8);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10000;
      }
      
      .lemma-gate-modal {
        background: white;
        padding: 2rem;
        border-radius: 12px;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
        text-align: center;
        max-width: 400px;
        width: 90%;
      }
      
      .lemma-gate-icon {
        font-size: 3rem;
        margin-bottom: 1rem;
      }
      
      .lemma-gate-modal h3 {
        margin: 0 0 1rem 0;
        color: #1f2937;
        font-size: 1.5rem;
      }
      
      .lemma-gate-modal p {
        margin: 0 0 1.5rem 0;
        color: #6b7280;
        line-height: 1.5;
      }
      
      .lemma-btn-primary {
        background: #635BFF;
        color: white;
        border: none;
        padding: 0.75rem 1.5rem;
        border-radius: 8px;
        font-size: 1rem;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s;
        margin: 0.5rem;
      }
      
      .lemma-btn-primary:hover {
        background: #4F46E5;
        transform: translateY(-1px);
      }
      
      .lemma-btn-secondary {
        background: #f3f4f6;
        color: #374151;
        border: 1px solid #d1d5db;
        padding: 0.75rem 1.5rem;
        border-radius: 8px;
        font-size: 1rem;
        cursor: pointer;
        transition: all 0.2s;
        margin: 0.5rem;
      }
      
      .lemma-btn-secondary:hover {
        background: #e5e7eb;
      }
      
      .lemma-gate-privacy {
        margin-top: 1rem !important;
        margin-bottom: 0 !important;
      }
      
      .lemma-gate-privacy small {
        color: #9ca3af;
      }
      
      .lemma-gate-spinner {
        width: 40px;
        height: 40px;
        border: 3px solid #f3f4f6;
        border-top: 3px solid #635BFF;
        border-radius: 50%;
        animation: lemma-spin 1s linear infinite;
        margin: 0 auto 1rem auto;
      }
      
      @keyframes lemma-spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
      }
    `;
    
    document.head.appendChild(styles);
  }

  showLoading(message = null) {
    this.hideAllStates();
    const loadingState = document.getElementById('lemma-gate-loading');
    if (loadingState) {
      if (message) {
        const messageEl = loadingState.querySelector('p');
        if (messageEl) messageEl.textContent = message;
      }
      loadingState.style.display = 'block';
    }
    this.showGateContainer();
  }

  showGate() {
    this.hideAllStates();
    const gateState = document.getElementById('lemma-gate-verify');
    if (gateState) {
      gateState.style.display = 'block';
    }
    this.showGateContainer();
  }

  showError(message) {
    this.hideAllStates();
    const errorState = document.getElementById('lemma-gate-error');
    const errorMessage = document.getElementById('lemma-error-message');
    
    if (errorState) {
      errorState.style.display = 'block';
    }
    
    if (errorMessage) {
      errorMessage.textContent = message;
    }
    
    this.showGateContainer();
    this.options.onError(new Error(message));
  }

  grantAccess() {
    this.log('Granting access to protected content');
    this.isVerified = true;
    this.hideGateContainer();
    this.showProtectedContent();
    this.options.onVerified();
  }

  hideAllStates() {
    const states = ['lemma-gate-loading', 'lemma-gate-verify', 'lemma-gate-error'];
    states.forEach(stateId => {
      const element = document.getElementById(stateId);
      if (element) {
        element.style.display = 'none';
      }
    });
  }

  showGateContainer() {
    const gateContainer = document.getElementById(this.options.gateContainerId);
    if (gateContainer) {
      gateContainer.style.display = 'block';
    }
  }

  hideGateContainer() {
    const gateContainer = document.getElementById(this.options.gateContainerId);
    if (gateContainer) {
      gateContainer.style.display = 'none';
    }
  }

  showProtectedContent() {
    const protectedContainer = document.getElementById(this.options.protectedContainerId);
    if (protectedContainer) {
      protectedContainer.style.display = 'block';
    }
  }

  generateNonce() {
    return Array.from(crypto.getRandomValues(new Uint8Array(16)))
      .map(b => b.toString(16).padStart(2, '0')).join('');
  }

  generateUserId() {
    return 'user_' + Array.from(crypto.getRandomValues(new Uint8Array(16)))
      .map(b => b.toString(16).padStart(2, '0')).join('').substring(0, 16);
  }

  // Public API
  async forceRecheck() {
    await this.checkAndVerify();
  }

  getStatus() {
    return {
      isVerified: this.isVerified,
      isVerifying: this.isVerifying,
      hasWallet: !!this.wallet
    };
  }
}

// Auto-initialize if gate elements are present
document.addEventListener('DOMContentLoaded', function() {
  const gateElement = document.getElementById('lemma-gate');
  const protectedElement = document.getElementById('protected-content');
  
  if (gateElement || protectedElement) {
    console.log('[LemmaGate] Auto-initializing...');
    
    // Wait for wallet to potentially load
    setTimeout(() => {
      window.lemmaGate = new LemmaGate({
        debug: true // Enable debug logging
      });
    }, 1000);
  }
});

// Export for module use
if (typeof module !== 'undefined' && module.exports) {
  module.exports = LemmaGate;
} 