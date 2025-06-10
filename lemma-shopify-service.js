// services/lemma-service.js
class LemmaShopifyService {
  constructor(lemmaApiKey, lemmaInstanceUrl) {
    this.apiKey = lemmaApiKey;
    this.baseUrl = lemmaInstanceUrl;
    this.headers = {
      'Content-Type': 'application/json',
      'X-API-Key': lemmaApiKey
    };
  }

  // Check if customer already has Lemma verification
  async checkCustomerVerification(customerEmail, shopDomain) {
    try {
      const response = await fetch(`${this.baseUrl}/api/customer-verification`, {
        method: 'POST',
        headers: this.headers,
        body: JSON.stringify({
          email: customerEmail,
          shop_domain: shopDomain
        })
      });

      const result = await response.json();
      return {
        verified: result.verified,
        isNewUser: !result.verified,
        userId: result.user_id
      };
    } catch (error) {
      console.error('Lemma verification check failed:', error);
      return { verified: false, isNewUser: true };
    }
  }

  // Generate verification URL for new users
  async generateVerificationUrl(customerData, shopDomain) {
    try {
      const response = await fetch(`${this.baseUrl}/api/generate-verification-url`, {
        method: 'POST',
        headers: this.headers,
        body: JSON.stringify({
          customer: customerData,
          shop_domain: shopDomain,
          callback_url: `https://your-shopify-app.com/lemma-callback`
        })
      });

      const result = await response.json();
      return result.verification_url;
    } catch (error) {
      console.error('Failed to generate verification URL:', error);
      throw error;
    }
  }

  // Verify Lemma presentation from checkout
  async verifyPresentation(presentation, challenge) {
    try {
      const response = await fetch(`${this.baseUrl}/api/verify-presentation`, {
        method: 'POST',
        headers: this.headers,
        body: JSON.stringify({
          presentation: presentation,
          challenge: challenge
        })
      });

      const result = await response.json();
      return {
        verified: result.success,
        userData: result.user_data
      };
    } catch (error) {
      console.error('Presentation verification failed:', error);
      return { verified: false };
    }
  }

  // Generate challenge for verification
  generateChallenge() {
    return Array.from(crypto.getRandomValues(new Uint8Array(16)))
      .map(b => b.toString(16).padStart(2, '0')).join('');
  }
}

module.exports = LemmaShopifyService; 