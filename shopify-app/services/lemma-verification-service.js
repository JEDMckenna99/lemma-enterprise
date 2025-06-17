const fetch = require('node-fetch');
const crypto = require('crypto');

class LemmaVerificationService {
  constructor(config) {
    this.apiKey = config.apiKey;
    this.baseUrl = config.baseUrl;
    this.onboardingFee = config.onboardingFee || 2.50;
    this.headers = {
      'Content-Type': 'application/json',
      'X-API-Key': this.apiKey
    };
    
    // Storage for shop data (in production, use a proper database)
    this.shopData = new Map();
  }

  // Get shop statistics
  async getShopStats(shop) {
    try {
      const shopStats = this.shopData.get(shop) || {
        verifiedCustomers: 0,
        blockedBots: 0,
        monthlyCost: 0,
        setupComplete: false
      };

      // Get real-time stats from Lemma API
      const response = await fetch(`${this.baseUrl}/api/analytics/customer/${shop}`, {
        headers: this.headers
      });

      if (response.ok) {
        const data = await response.json();
        shopStats.verifiedCustomers = data.verified_customers || 0;
        shopStats.blockedBots = data.blocked_bots || 0;
        shopStats.monthlyCost = this.calculateMonthlyCost(data.verified_customers);
        shopStats.setupComplete = data.setup_complete || false;
      }

      return shopStats;
    } catch (error) {
      console.error('Error getting shop stats:', error);
      return {
        verifiedCustomers: 0,
        blockedBots: 0,
        monthlyCost: 0,
        setupComplete: false
      };
    }
  }

  // Calculate monthly cost based on network pricing
  calculateMonthlyCost(verifiedCustomers) {
    if (!verifiedCustomers) return 0;
    
    // Network pricing: $0.045-0.10 per user/month (decreases as network grows)
    // For simplicity, using $0.08 as baseline
    const monthlyRate = 0.08;
    return verifiedCustomers * monthlyRate;
  }

  // Check setup status
  async checkSetup(shop) {
    try {
      // Check if Lemma Shield is properly configured
      const response = await fetch(`${this.baseUrl}/api/shield/status`, {
        headers: {
          ...this.headers,
          'X-Shop-Domain': shop
        }
      });

      const data = await response.json();
      
      if (response.ok && data.success) {
        return {
          complete: true,
          message: 'Lemma Shield is properly configured and operational',
          issues: []
        };
      } else {
        return {
          complete: false,
          message: 'Setup issues detected',
          issues: data.issues || ['Unknown configuration error']
        };
      }
    } catch (error) {
      console.error('Setup check error:', error);
      return {
        complete: false,
        message: 'Failed to check setup status',
        issues: ['Connection error to Lemma service']
      };
    }
  }

  // Test verification
  async testVerification(shop) {
    try {
      const startTime = Date.now();
      
      // Test the Shield API
      const response = await fetch(`${this.baseUrl}/api/shield/challenge`, {
        headers: this.headers
      });

      const latency = Date.now() - startTime;

      if (response.ok) {
        const data = await response.json();
        return {
          success: true,
          message: `Test successful - Lemma Shield responding in ${latency}ms`,
          latency: latency
        };
      } else {
        return {
          success: false,
          message: 'Test failed - Lemma Shield not responding properly',
          latency: latency
        };
      }
    } catch (error) {
      console.error('Test verification error:', error);
      return {
        success: false,
        message: 'Test failed - ' + error.message,
        latency: 0
      };
    }
  }

  // Handle new customer creation
  async handleNewCustomer(customer, shop) {
    try {
      // Check if customer already has Lemma verification
      const verificationStatus = await this.checkCustomerVerification(customer.email, shop);
      
      if (!verificationStatus.verified) {
        // Customer needs verification - create entry in our system
        await this.createCustomerVerificationEntry(customer, shop);
      }

      // Log the event
      await this.logCustomerEvent('customer_created', {
        customer_id: customer.id,
        email: customer.email,
        shop: shop,
        verified: verificationStatus.verified,
        is_new_user: !verificationStatus.verified
      });

    } catch (error) {
      console.error('Error handling new customer:', error);
    }
  }

  // Check customer verification status
  async checkCustomerVerification(email, shop) {
    try {
      // Create user ID hash from email (privacy-preserving)
      const userId = this.createUserIdFromEmail(email);
      
      // Check with Lemma API
      const response = await fetch(`${this.baseUrl}/api/user-credential/${userId}`, {
        headers: this.headers
      });

      if (response.ok) {
        const data = await response.json();
        return {
          verified: data.verified || false,
          userId: userId,
          credentialId: data.credential_id
        };
      } else {
        return {
          verified: false,
          userId: userId
        };
      }
    } catch (error) {
      console.error('Error checking customer verification:', error);
      return { verified: false };
    }
  }

  // Create user ID from email (privacy-preserving hash)
  createUserIdFromEmail(email) {
    return crypto
      .createHash('sha256')
      .update(email.toLowerCase().trim())
      .digest('hex')
      .substring(0, 16);
  }

  // Create customer verification entry
  async createCustomerVerificationEntry(customer, shop) {
    try {
      const userId = this.createUserIdFromEmail(customer.email);
      
      // Issue credential through Lemma API
      const response = await fetch(`${this.baseUrl}/api/issue-credential`, {
        method: 'POST',
        headers: this.headers,
        body: JSON.stringify({
          user_id: userId,
          customer_email: customer.email,
          shop_domain: shop,
          onboarding_fee: this.onboardingFee
        })
      });

      if (response.ok) {
        const data = await response.json();
        console.log(`Credential issued for customer ${customer.email} in shop ${shop}`);
        return data.credential;
      } else {
        console.error('Failed to issue credential:', await response.text());
      }
    } catch (error) {
      console.error('Error creating customer verification entry:', error);
    }
  }

  // Verify order customer
  async verifyOrderCustomer(order, shop) {
    try {
      if (!order.email) {
        return { verified: false, reason: 'No email provided' };
      }

      const verificationStatus = await this.checkCustomerVerification(order.email, shop);
      
      // If not verified, we might want to flag this order
      if (!verificationStatus.verified) {
        await this.logOrderEvent('unverified_order', {
          order_id: order.id,
          customer_email: order.email,
          shop: shop,
          order_total: order.total_price
        });
      }

      return {
        verified: verificationStatus.verified,
        userId: verificationStatus.userId,
        credentialId: verificationStatus.credentialId
      };
    } catch (error) {
      console.error('Error verifying order customer:', error);
      return { verified: false, reason: 'Verification error' };
    }
  }

  // Process verification callback from Lemma
  async processVerificationCallback(userId, verification, shop) {
    try {
      // Verify the presentation with Lemma API
      const response = await fetch(`${this.baseUrl}/api/verify-presentation`, {
        method: 'POST',
        headers: this.headers,
        body: JSON.stringify({
          presentation: verification.presentation,
          challenge: verification.challenge
        })
      });

      if (response.ok) {
        const data = await response.json();
        
        if (data.success) {
          // Update our records
          await this.updateCustomerVerificationStatus(userId, shop, true);
          
          // Log successful verification
          await this.logVerificationEvent('verification_completed', {
            user_id: userId,
            shop: shop,
            verification_method: verification.method,
            fee_charged: this.onboardingFee
          });

          return { success: true, verified: true };
        }
      }

      return { success: false, verified: false };
    } catch (error) {
      console.error('Error processing verification callback:', error);
      return { success: false, error: error.message };
    }
  }

  // Update customer verification status
  async updateCustomerVerificationStatus(userId, shop, verified) {
    try {
      // Update shop stats
      const shopStats = this.shopData.get(shop) || {
        verifiedCustomers: 0,
        blockedBots: 0,
        monthlyCost: 0,
        setupComplete: true
      };

      if (verified) {
        shopStats.verifiedCustomers += 1;
        shopStats.monthlyCost = this.calculateMonthlyCost(shopStats.verifiedCustomers);
      }

      this.shopData.set(shop, shopStats);
    } catch (error) {
      console.error('Error updating customer verification status:', error);
    }
  }

  // Generate Shield integration code for storefront
  generateShieldIntegrationCode(shop) {
    return `
<!-- Lemma Shield Integration for ${shop} -->
<script>
  window.LemmaConfig = {
    apiKey: '${this.apiKey}',
    baseUrl: '${this.baseUrl}',
    shop: '${shop}',
    onboardingFee: ${this.onboardingFee}
  };
</script>
<script src="${this.baseUrl}/static/js/lemma-shield-widget.js"></script>
<script>
  // Initialize Lemma Shield for Shopify
  document.addEventListener('DOMContentLoaded', function() {
    if (window.LemmaShield) {
      window.LemmaShield.init({
        apiKey: window.LemmaConfig.apiKey,
        baseUrl: window.LemmaConfig.baseUrl,
        onVerified: function(proof) {
          // Customer verified - enable full store functionality
          console.log('Customer verified with Lemma');
          
          // Optional: Send verification to backend
          fetch('/lemma-verification-success', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              proof: proof,
              shop: window.LemmaConfig.shop
            })
          });
        },
        onUnverified: function() {
          // Customer not verified - show verification prompt
          console.log('Customer needs Lemma verification');
        }
      });
    }
  });
</script>
`;
  }

  // Log customer event
  async logCustomerEvent(eventType, data) {
    try {
      await fetch(`${this.baseUrl}/api/analytics/log-event`, {
        method: 'POST',
        headers: this.headers,
        body: JSON.stringify({
          event_type: eventType,
          data: data,
          timestamp: new Date().toISOString()
        })
      });
    } catch (error) {
      console.error('Error logging customer event:', error);
    }
  }

  // Log order event
  async logOrderEvent(eventType, data) {
    try {
      await fetch(`${this.baseUrl}/api/analytics/log-event`, {
        method: 'POST',
        headers: this.headers,
        body: JSON.stringify({
          event_type: eventType,
          data: data,
          timestamp: new Date().toISOString()
        })
      });
    } catch (error) {
      console.error('Error logging order event:', error);
    }
  }

  // Log verification event
  async logVerificationEvent(eventType, data) {
    try {
      await fetch(`${this.baseUrl}/api/analytics/log-event`, {
        method: 'POST',
        headers: this.headers,
        body: JSON.stringify({
          event_type: eventType,
          data: data,
          timestamp: new Date().toISOString()
        })
      });
    } catch (error) {
      console.error('Error logging verification event:', error);
    }
  }

  // Get verification statistics for billing
  async getBillingData(shop, month) {
    try {
      const response = await fetch(`${this.baseUrl}/api/billing/usage/monthly?site_id=${shop}&month=${month}`, {
        headers: this.headers
      });

      if (response.ok) {
        return await response.json();
      } else {
        console.error('Failed to get billing data:', response.statusText);
        return null;
      }
    } catch (error) {
      console.error('Error getting billing data:', error);
      return null;
    }
  }

  // Health check
  async healthCheck() {
    try {
      const response = await fetch(`${this.baseUrl}/api/health`, {
        headers: this.headers
      });

      return {
        healthy: response.ok,
        status: response.status,
        baseUrl: this.baseUrl
      };
    } catch (error) {
      return {
        healthy: false,
        error: error.message,
        baseUrl: this.baseUrl
      };
    }
  }
}

module.exports = LemmaVerificationService; 