/**
 * Lemma Shield for Shopify - Frontend Integration
 * Provides seamless human verification for Shopify stores
 */

(function() {
  'use strict';

  // Configuration
  const LEMMA_CONFIG = window.LemmaConfig || {
    baseUrl: 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com',
    apiKey: null,
    shop: null,
    onboardingFee: 2.50
  };

  // Global state
  let isInitialized = false;
  let verificationInProgress = false;
  let userVerificationStatus = null;

  /**
   * Main Lemma Shield class
   */
  class LemmaShield {
    constructor(config = {}) {
      this.config = { ...LEMMA_CONFIG, ...config };
      this.baseUrl = this.config.baseUrl;
      this.apiKey = this.config.apiKey;
      this.shop = this.config.shop;
      this.onboardingFee = this.config.onboardingFee;
      
      // Callbacks
      this.onVerified = this.config.onVerified || function() {};
      this.onUnverified = this.config.onUnverified || function() {};
      this.onError = this.config.onError || function() {};
    }

    /**
     * Initialize the shield
     */
    async init() {
      if (isInitialized) return;
      
      console.log('🛡️ Initializing Lemma Shield for Shopify');
      
      try {
        // Check if customer is already verified
        await this.checkVerificationStatus();
        
        // Set up background monitoring
        this.setupBackgroundMonitoring();
        
        // Handle checkout protection
        this.setupCheckoutProtection();
        
        // Set up bot detection
        this.setupBotDetection();
        
        isInitialized = true;
        console.log('✅ Lemma Shield initialized successfully');
        
      } catch (error) {
        console.error('❌ Lemma Shield initialization failed:', error);
        this.onError(error);
      }
    }

    /**
     * Check if current user is verified
     */
    async checkVerificationStatus() {
      try {
        // Get customer email from Shopify customer object
        const customerEmail = this.getCustomerEmail();
        
        if (!customerEmail) {
          console.log('👤 No customer email found - guest user');
          userVerificationStatus = { verified: false, guest: true };
          this.onUnverified();
          return;
        }

        // Check verification status via Shield API
        const response = await this.makeRequest('/api/shield/status', {
          method: 'GET',
          headers: {
            'X-Customer-Email': customerEmail,
            'X-Shop-Domain': this.shop
          }
        });

        if (response.success) {
          userVerificationStatus = {
            verified: response.data.verified,
            credentialId: response.data.credential_id,
            email: customerEmail
          };

          if (response.data.verified) {
            console.log('✅ Customer is verified with Lemma');
            this.onVerified(response.data);
          } else {
            console.log('⚠️ Customer needs verification');
            this.onUnverified();
            this.showVerificationPrompt();
          }
        } else {
          console.log('❓ Unable to check verification status');
          userVerificationStatus = { verified: false, error: response.error };
          this.onUnverified();
        }

      } catch (error) {
        console.error('Error checking verification status:', error);
        userVerificationStatus = { verified: false, error: error.message };
        this.onUnverified();
      }
    }

    /**
     * Get customer email from various Shopify contexts
     */
    getCustomerEmail() {
      // Try Shopify customer object
      if (window.Shopify && window.Shopify.customer && window.Shopify.customer.email) {
        return window.Shopify.customer.email;
      }

      // Try checkout object
      if (window.Shopify && window.Shopify.checkout && window.Shopify.checkout.email) {
        return window.Shopify.checkout.email;
      }

      // Try meta tags
      const customerEmailMeta = document.querySelector('meta[name="customer-email"]');
      if (customerEmailMeta) {
        return customerEmailMeta.getAttribute('content');
      }

      // Try local storage (if previously stored)
      return localStorage.getItem('lemma-customer-email');
    }

    /**
     * Show verification prompt
     */
    showVerificationPrompt() {
      if (verificationInProgress) return;

      // Create verification modal
      const modal = this.createVerificationModal();
      document.body.appendChild(modal);
    }

    /**
     * Create verification modal
     */
    createVerificationModal() {
      const modal = document.createElement('div');
      modal.id = 'lemma-verification-modal';
      modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.7);
        z-index: 10000;
        display: flex;
        align-items: center;
        justify-content: center;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      `;

      const content = document.createElement('div');
      content.style.cssText = `
        background: white;
        padding: 40px;
        border-radius: 12px;
        max-width: 500px;
        width: 90%;
        text-align: center;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
      `;

      content.innerHTML = `
        <div style="margin-bottom: 20px;">
          <div style="width: 60px; height: 60px; background: #635bff; border-radius: 50%; margin: 0 auto 16px; display: flex; align-items: center; justify-content: center;">
            <svg width="30" height="30" fill="white" viewBox="0 0 24 24">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
            </svg>
          </div>
          <h2 style="margin: 0 0 8px; color: #1a1a1a; font-size: 24px; font-weight: 600;">Human Verification Required</h2>
          <p style="margin: 0; color: #666; font-size: 16px; line-height: 1.5;">
            To protect against bots and ensure a secure shopping experience, we need to verify that you're human.
          </p>
        </div>

        <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; text-align: left;">
          <h3 style="margin: 0 0 12px; color: #1a1a1a; font-size: 16px; font-weight: 600;">What happens next:</h3>
          <ul style="margin: 0; padding-left: 20px; color: #666; font-size: 14px; line-height: 1.6;">
            <li>One-time verification fee: <strong>$${this.onboardingFee}</strong></li>
            <li>Verification works across all Lemma-integrated stores</li>
            <li>No personal data stored - privacy first</li>
            <li>Complete verification in under 2 minutes</li>
          </ul>
        </div>

        <div>
          <button id="lemma-verify-btn" style="
            background: #635bff;
            color: white;
            border: none;
            padding: 14px 28px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            margin-right: 12px;
            transition: background 0.2s;
          ">Verify Now</button>
          
          <button id="lemma-cancel-btn" style="
            background: transparent;
            color: #666;
            border: 1px solid #ddd;
            padding: 14px 28px;
            border-radius: 8px;
            font-size: 16px;
            cursor: pointer;
            transition: all 0.2s;
          ">Continue as Guest</button>
        </div>

        <p style="margin: 20px 0 0; color: #999; font-size: 12px;">
          Powered by <strong>Lemma</strong> - Privacy-first human verification
        </p>
      `;

      modal.appendChild(content);

      // Add event listeners
      const verifyBtn = content.querySelector('#lemma-verify-btn');
      const cancelBtn = content.querySelector('#lemma-cancel-btn');

      verifyBtn.addEventListener('click', () => {
        this.startVerification();
        modal.remove();
      });

      cancelBtn.addEventListener('click', () => {
        modal.remove();
        console.log('User chose to continue as guest');
      });

      // Hover effects
      verifyBtn.addEventListener('mouseover', () => {
        verifyBtn.style.background = '#5a52e8';
      });
      verifyBtn.addEventListener('mouseout', () => {
        verifyBtn.style.background = '#635bff';
      });

      cancelBtn.addEventListener('mouseover', () => {
        cancelBtn.style.borderColor = '#999';
        cancelBtn.style.color = '#333';
      });
      cancelBtn.addEventListener('mouseout', () => {
        cancelBtn.style.borderColor = '#ddd';
        cancelBtn.style.color = '#666';
      });

      return modal;
    }

    /**
     * Start verification process
     */
    async startVerification() {
      if (verificationInProgress) return;

      verificationInProgress = true;
      console.log('🚀 Starting Lemma verification');

      try {
        const customerEmail = this.getCustomerEmail();
        if (!customerEmail) {
          throw new Error('Customer email required for verification');
        }

        // Generate verification URL
        const response = await this.makeRequest('/api/shield/start-verification', {
          method: 'POST',
          body: JSON.stringify({
            customer_email: customerEmail,
            shop_domain: this.shop,
            return_url: window.location.href
          })
        });

        if (response.success) {
          // Redirect to verification
          window.location.href = response.verification_url;
        } else {
          throw new Error(response.error || 'Failed to start verification');
        }

      } catch (error) {
        console.error('Verification start failed:', error);
        verificationInProgress = false;
        this.onError(error);
      }
    }

    /**
     * Setup background monitoring
     */
    setupBackgroundMonitoring() {
      // Check verification status periodically
      setInterval(() => {
        if (!verificationInProgress) {
          this.checkVerificationStatus();
        }
      }, 30000); // Check every 30 seconds
    }

    /**
     * Setup checkout protection
     */
    setupCheckoutProtection() {
      // Monitor for checkout attempts
      const checkoutButtons = document.querySelectorAll('[name="add"], .btn-checkout, .checkout-button, #checkout-btn');
      
      checkoutButtons.forEach(button => {
        button.addEventListener('click', (e) => {
          if (userVerificationStatus && !userVerificationStatus.verified && !userVerificationStatus.guest) {
            e.preventDefault();
            this.showVerificationPrompt();
          }
        });
      });

      // Monitor form submissions
      document.addEventListener('submit', (e) => {
        const form = e.target;
        if (form.action && form.action.includes('checkout')) {
          if (userVerificationStatus && !userVerificationStatus.verified && !userVerificationStatus.guest) {
            e.preventDefault();
            this.showVerificationPrompt();
          }
        }
      });
    }

    /**
     * Setup bot detection
     */
    setupBotDetection() {
      // Simple bot detection patterns
      const botPatterns = [
        // Rapid clicking
        'rapid-clicks',
        // No mouse movement
        'no-mouse-movement',
        // Suspicious user agent
        'automation'
      ];

      // Track user behavior
      let mouseMovements = 0;
      let clickCount = 0;
      let lastClickTime = 0;

      document.addEventListener('mousemove', () => {
        mouseMovements++;
      });

      document.addEventListener('click', () => {
        const now = Date.now();
        if (now - lastClickTime < 100) {
          clickCount++;
          if (clickCount > 5) {
            console.warn('🤖 Potential bot behavior detected - rapid clicking');
            this.flagSuspiciousActivity('rapid-clicking');
          }
        } else {
          clickCount = 0;
        }
        lastClickTime = now;
      });

      // Check for suspicious patterns after 10 seconds
      setTimeout(() => {
        if (mouseMovements === 0) {
          console.warn('🤖 Potential bot behavior detected - no mouse movement');
          this.flagSuspiciousActivity('no-mouse-movement');
        }
      }, 10000);
    }

    /**
     * Flag suspicious activity
     */
    async flagSuspiciousActivity(type) {
      try {
        await this.makeRequest('/api/analytics/log-event', {
          method: 'POST',
          body: JSON.stringify({
            event_type: 'suspicious_activity',
            data: {
              type: type,
              shop: this.shop,
              url: window.location.href,
              user_agent: navigator.userAgent
            }
          })
        });
      } catch (error) {
        console.error('Failed to log suspicious activity:', error);
      }
    }

    /**
     * Make API request to Lemma
     */
    async makeRequest(endpoint, options = {}) {
      const url = `${this.baseUrl}${endpoint}`;
      const headers = {
        'Content-Type': 'application/json',
        'X-API-Key': this.apiKey,
        ...options.headers
      };

      try {
        const response = await fetch(url, {
          ...options,
          headers
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        return await response.json();
      } catch (error) {
        console.error('API request failed:', error);
        throw error;
      }
    }
  }

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeLemmaShield);
  } else {
    initializeLemmaShield();
  }

  function initializeLemmaShield() {
    // Only initialize if we have shop information
    if (!LEMMA_CONFIG.shop) {
      console.warn('⚠️ Lemma Shield: No shop domain configured');
      return;
    }

    window.LemmaShield = new LemmaShield(LEMMA_CONFIG);
    window.LemmaShield.init();
  }

  // Export for manual initialization
  window.LemmaShieldClass = LemmaShield;

})();

// Add CSS for better styling
const style = document.createElement('style');
style.textContent = `
  @keyframes lemma-fade-in {
    from { opacity: 0; transform: scale(0.9); }
    to { opacity: 1; transform: scale(1); }
  }

  #lemma-verification-modal {
    animation: lemma-fade-in 0.3s ease-out;
  }

  #lemma-verification-modal > div {
    animation: lemma-fade-in 0.4s ease-out 0.1s both;
  }

  .lemma-shield-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: #f0f8ff;
    color: #635bff;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 500;
    border: 1px solid #e6f2ff;
  }

  .lemma-shield-badge::before {
    content: "🛡️";
    font-size: 10px;
  }
`;

if (document.head) {
  document.head.appendChild(style);
} else {
  document.addEventListener('DOMContentLoaded', () => {
    document.head.appendChild(style);
  });
} 