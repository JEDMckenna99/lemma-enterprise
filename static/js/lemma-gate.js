/**
 * Lemma Gate - Automatic Human Verification Gateway
 * Seamlessly manages access to protected content based on Lemma verification status
 */

class LemmaGate {
  constructor(options = {}) {
    this.options = {
      // Gate behavior
      autoVerify: true,
      showGateUI: true,
      blockUnverified: true,
      
      // UI customization
      gateContainer: options.gateContainer || 'lemma-gate',
      protectedContainer: options.protectedContainer || 'protected-content',
      verifyButtonText: options.verifyButtonText || '🤖 Verify You\'re Human',
      loadingText: options.loadingText || 'Verifying your Lemma credential...',
      
      // Network settings
      apiEndpoint: options.apiEndpoint || '/api/verify-human',
      verificationEndpoint: options.verificationEndpoint || '/verify',
      
      // Callbacks
      onVerificationStart: options.onVerificationStart || (() => {}),
      onVerificationSuccess: options.onVerificationSuccess || (() => {}),
      onVerificationFailed: options.onVerificationFailed || (() => {}),
      
      ...options
    };
    
    this.isVerified = false;
    this.isChecking = false;
    this.wallet = null;
    
    this.init();
  }

  async init() {
    console.log('[LemmaGate] Initializing gate...');
    
    // Wait for wallet to be available
    await this.waitForWallet();
    
    // Check current verification status
    await this.checkVerificationStatus();
    
    // Setup the gate UI
    this.setupGateUI();
    
    // Start automatic verification if user has credentials
    if (this.options.autoVerify) {
      await this.performAutoVerification();
    }
  }

  async waitForWallet(timeout = 10000) {
    return new Promise((resolve, reject) => {
      const startTime = Date.now();
      
      const checkWallet = () => {
        if (window.lemmaWallet) {
          this.wallet = window.lemmaWallet;
          console.log('[LemmaGate] Wallet found');
          resolve();
        } else if (Date.now() - startTime > timeout) {
          console.warn('[LemmaGate] Wallet not found within timeout');
          reject(new Error('Wallet initialization timeout'));
        } else {
          setTimeout(checkWallet, 100);
        }
      };
      
      checkWallet();
    });
  }

  async checkVerificationStatus() {
    try {
      // Check if user has any Lemma credentials
      const credentials = await this.wallet.getAllCredentials();
      
      if (credentials && credentials.length > 0) {
        console.log(`[LemmaGate] Found ${credentials.length} credentials`);
        return true;
      } else {
        console.log('[LemmaGate] No credentials found');
        return false;
      }
    } catch (error) {
      console.error('[LemmaGate] Error checking credentials:', error);
      return false;
    }
  }

  async performAutoVerification() {
    if (this.isChecking) return;
    
    this.isChecking = true;
    this.showLoadingState();
    
    try {
      console.log('[LemmaGate] Starting automatic verification...');
      this.options.onVerificationStart();
      
      // Get the first available credential
      const credentials = await this.wallet.getAllCredentials();
      
      if (!credentials || credentials.length === 0) {
        console.log('[LemmaGate] No credentials found - showing gate');
        this.showGate();
        return;
      }

      const credential = credentials[0];
      
      // 1. Check DID resolution
      await this.verifyDID(credential);
      
      // 2. Check revocation status
      await this.checkRevocation(credential);
      
      // 3. Verify with server
      const isValid = await this.verifyWithServer(credential);
      
      if (isValid) {
        console.log('[LemmaGate] Verification successful - granting access');
        this.isVerified = true;
        this.options.onVerificationSuccess(credential);
        this.showProtectedContent();
      } else {
        console.log('[LemmaGate] Verification failed - showing gate');
        this.showGate();
      }
      
    } catch (error) {
      console.error('[LemmaGate] Auto-verification failed:', error);
      this.options.onVerificationFailed(error);
      this.showGate();
    } finally {
      this.isChecking = false;
    }
  }

  async verifyDID(credential) {
    console.log('[LemmaGate] Verifying DID...');
    
    try {
      const credentialData = credential.credential || credential;
      const issuerDID = credentialData.issuer;
      
      // This would integrate with your DID resolver
      // For now, we'll assume DID is valid if it exists
      if (issuerDID && issuerDID.startsWith('did:')) {
        console.log('[LemmaGate] DID verification passed');
        return true;
      } else {
        throw new Error('Invalid DID format');
      }
    } catch (error) {
      console.error('[LemmaGate] DID verification failed:', error);
      throw error;
    }
  }

  async checkRevocation(credential) {
    console.log('[LemmaGate] Checking revocation status...');
    
    try {
      const credentialData = credential.credential || credential;
      const credentialId = credentialData.id;
      
      // Use the wallet's OPRF client for revocation checking
      const revocationResult = await this.wallet.checkRevocationStatus(credentialId);
      
      if (revocationResult.revoked) {
        throw new Error('Credential has been revoked');
      }
      
      console.log('[LemmaGate] Revocation check passed');
      return true;
    } catch (error) {
      console.error('[LemmaGate] Revocation check failed:', error);
      throw error;
    }
  }

  async verifyWithServer(credential) {
    console.log('[LemmaGate] Verifying with server...');
    
    try {
      const credentialData = credential.credential || credential;
      
      // Generate challenge
      const challenge = Array.from(crypto.getRandomValues(new Uint8Array(16)))
        .map(b => b.toString(16).padStart(2, '0')).join('');
      
      // Create presentation
      const presentation = await this.createPresentation(credentialData, challenge);
      
      // Send to server for verification
      const response = await fetch(this.options.apiEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify({
          presentation: presentation,
          challenge: challenge
        })
      });
      
      if (!response.ok) {
        throw new Error(`Server verification failed: ${response.status}`);
      }
      
      const result = await response.json();
      console.log('[LemmaGate] Server verification result:', result);
      
      return result.success === true;
    } catch (error) {
      console.error('[LemmaGate] Server verification failed:', error);
      throw error;
    }
  }

  async createPresentation(credential, challenge) {
    // This would integrate with your presentation creation logic
    return {
      "@context": ["https://www.w3.org/2018/credentials/v1"],
      "type": ["VerifiablePresentation"],
      "verifiableCredential": [credential],
      "proof": {
        "type": "Ed25519Signature2020",
        "created": new Date().toISOString(),
        "challenge": challenge,
        "proofPurpose": "authentication"
      }
    };
  }

  setupGateUI() {
    if (!this.options.showGateUI) return;
    
    const gateContainer = document.getElementById(this.options.gateContainer);
    if (!gateContainer) {
      console.warn('[LemmaGate] Gate container not found');
      return;
    }
    
    gateContainer.innerHTML = `
      <div id="lemma-gate-content" class="lemma-gate-overlay">
        <div class="lemma-gate-modal">
          <div class="lemma-gate-header">
            <h2>🛡️ Human Verification Required</h2>
            <p>This content is protected by Lemma human verification</p>
          </div>
          
          <div id="lemma-gate-body" class="lemma-gate-body">
            <div id="gate-loading" class="gate-state" style="display: none;">
              <div class="loading-spinner"></div>
              <p>${this.options.loadingText}</p>
            </div>
            
            <div id="gate-verify" class="gate-state">
              <p>To access this content, please verify that you're human:</p>
              <button id="lemma-verify-button" class="lemma-verify-btn">
                ${this.options.verifyButtonText}
              </button>
              <p class="gate-description">
                This creates a secure credential that works across the entire Lemma Network
              </p>
            </div>
            
            <div id="gate-error" class="gate-state" style="display: none;">
              <p class="error-message">Verification failed. Please try again.</p>
              <button id="lemma-retry-button" class="lemma-verify-btn">
                🔄 Try Again
              </button>
            </div>
          </div>
        </div>
      </div>
    `;
    
    // Add event listeners
    document.getElementById('lemma-verify-button').addEventListener('click', () => {
      this.initiateVerification();
    });
    
    document.getElementById('lemma-retry-button').addEventListener('click', () => {
      this.performAutoVerification();
    });
  }

  showLoadingState() {
    this.showGateState('gate-loading');
  }

  showGate() {
    this.showGateState('gate-verify');
    const gateContainer = document.getElementById(this.options.gateContainer);
    const protectedContainer = document.getElementById(this.options.protectedContainer);
    
    if (gateContainer) gateContainer.style.display = 'block';
    if (protectedContainer) protectedContainer.style.display = 'none';
  }

  showProtectedContent() {
    const gateContainer = document.getElementById(this.options.gateContainer);
    const protectedContainer = document.getElementById(this.options.protectedContainer);
    
    if (gateContainer) gateContainer.style.display = 'none';
    if (protectedContainer) protectedContainer.style.display = 'block';
  }

  showError(message) {
    const errorElement = document.querySelector('#gate-error .error-message');
    if (errorElement) {
      errorElement.textContent = message;
    }
    this.showGateState('gate-error');
  }

  showGateState(stateId) {
    const states = ['gate-loading', 'gate-verify', 'gate-error'];
    states.forEach(id => {
      const element = document.getElementById(id);
      if (element) {
        element.style.display = id === stateId ? 'block' : 'none';
      }
    });
  }

  initiateVerification() {
    console.log('[LemmaGate] Initiating manual verification...');
    
    // Redirect to verification endpoint
    const currentUrl = encodeURIComponent(window.location.href);
    window.location.href = `${this.options.verificationEndpoint}?redirect=${currentUrl}`;
  }

  // Public API methods
  async forceRecheck() {
    console.log('[LemmaGate] Force rechecking verification status...');
    await this.performAutoVerification();
  }

  getVerificationStatus() {
    return {
      isVerified: this.isVerified,
      isChecking: this.isChecking,
      hasCredentials: this.wallet ? this.wallet.getAllCredentials().length > 0 : false
    };
  }
}

// Auto-initialize on pages with gate elements
document.addEventListener('DOMContentLoaded', function() {
  const gateElement = document.getElementById('lemma-gate');
  const protectedElement = document.getElementById('protected-content');
  
  if (gateElement || protectedElement) {
    console.log('[LemmaGate] Auto-initializing gate...');
    
    // Wait a bit for wallet to initialize
    setTimeout(() => {
      window.lemmaGate = new LemmaGate({
        gateContainer: 'lemma-gate',
        protectedContainer: 'protected-content'
      });
    }, 1000);
  }
});

// CSS for the gate UI
const gateCSS = `
.lemma-gate-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.8);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 10000;
}

.lemma-gate-modal {
  background: white;
  border-radius: 12px;
  padding: 2rem;
  max-width: 500px;
  width: 90%;
  text-align: center;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
}

.lemma-gate-header h2 {
  color: #6B3FA0;
  margin-bottom: 0.5rem;
  font-size: 1.5rem;
}

.lemma-gate-header p {
  color: #666;
  margin-bottom: 1.5rem;
}

.lemma-verify-btn {
  background: linear-gradient(135deg, #6B3FA0 0%, #8F6BC1 100%);
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  margin: 1rem 0;
}

.lemma-verify-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(107, 63, 160, 0.3);
}

.gate-description {
  color: #888;
  font-size: 14px;
  margin-top: 1rem;
  max-width: 400px;
  margin-left: auto;
  margin-right: auto;
}

.loading-spinner {
  border: 3px solid #f3f3f3;
  border-top: 3px solid #6B3FA0;
  border-radius: 50%;
  width: 40px;
  height: 40px;
  animation: spin 1s linear infinite;
  margin: 0 auto 1rem auto;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.error-message {
  color: #DC3545;
  margin-bottom: 1rem;
}

.gate-state {
  padding: 1rem 0;
}
`;

// Inject CSS
if (!document.getElementById('lemma-gate-styles')) {
  const style = document.createElement('style');
  style.id = 'lemma-gate-styles';
  style.textContent = gateCSS;
  document.head.appendChild(style);
}

// Export for use in other scripts
window.LemmaGate = LemmaGate; 