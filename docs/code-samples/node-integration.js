/**
 * Lemma Enterprise Node.js Integration Examples
 * Human Verification Protocol for Node.js/Express Applications
 */

const express = require('express');
const axios = require('axios');
const crypto = require('crypto');

// ============================================================================
// CONFIGURATION
// ============================================================================

const LEMMA_BASE_URL = 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com';
const LEMMA_API_KEY = process.env.LEMMA_API_KEY; // Your API key from onboarding

if (!LEMMA_API_KEY) {
  console.error('❌ LEMMA_API_KEY environment variable is required');
  process.exit(1);
}

// ============================================================================
// LEMMA CLIENT CLASS
// ============================================================================

class LemmaClient {
  constructor(apiKey, baseUrl = LEMMA_BASE_URL) {
    this.apiKey = apiKey;
    this.baseUrl = baseUrl;
    this.axios = axios.create({
      baseURL: baseUrl,
      headers: {
        'X-API-Key': apiKey,
        'Content-Type': 'application/json'
      }
    });
  }

  /**
   * Generate a verification challenge
   */
  async generateChallenge() {
    try {
      const response = await this.axios.get('/api/generate-challenge');
      return response.data.data;
    } catch (error) {
      throw new Error(`Failed to generate challenge: ${error.response?.data?.error || error.message}`);
    }
  }

  /**
   * Verify human credential
   */
  async verifyHuman(presentation, challenge, domain) {
    try {
      const response = await this.axios.post('/api/verify-human', {
        presentation,
        challenge,
        domain
      });
      return response.data;
    } catch (error) {
      throw new Error(`Human verification failed: ${error.response?.data?.error || error.message}`);
    }
  }

  /**
   * Get monthly usage metrics
   */
  async getMonthlyUsage(year, month) {
    try {
      const response = await this.axios.get('/api/billing/usage/monthly', {
        params: { year, month }
      });
      return response.data.data;
    } catch (error) {
      throw new Error(`Failed to get usage: ${error.response?.data?.error || error.message}`);
    }
  }

  /**
   * Health check
   */
  async healthCheck() {
    try {
      const response = await axios.get(`${this.baseUrl}/api/health`);
      return response.data;
    } catch (error) {
      throw new Error(`Health check failed: ${error.message}`);
    }
  }
}

// ============================================================================
// EXPRESS MIDDLEWARE
// ============================================================================

/**
 * Lemma verification middleware for Express
 * Protects routes by requiring human verification
 */
function lemmaMiddleware(options = {}) {
  const { 
    domain = 'localhost',
    skipVerification = false,
    onVerificationFailed = null 
  } = options;

  const lemma = new LemmaClient(LEMMA_API_KEY);

  return async (req, res, next) => {
    if (skipVerification) {
      return next();
    }

    try {
      // Check for Lemma verification in session
      if (req.session?.lemmaVerified) {
        req.lemmaUser = req.session.lemmaUser;
        return next();
      }

      // Check for Lemma credential in request
      const { presentation, challenge } = req.body || {};
      
      if (!presentation || !challenge) {
        return res.status(401).json({
          success: false,
          error: 'Human verification required',
          required: {
            presentation: 'Verifiable presentation from user\'s Lemma credential',
            challenge: 'Challenge from /api/generate-challenge'
          }
        });
      }

      // Verify with Lemma
      const verification = await lemma.verifyHuman(presentation, challenge, domain);
      
      if (verification.success && verification.data.verified) {
        // Store verification in session
        req.session.lemmaVerified = true;
        req.session.lemmaUser = verification.data.user_id;
        req.lemmaUser = verification.data.user_id;
        
        next();
      } else {
        const error = 'Human verification failed';
        if (onVerificationFailed) {
          return onVerificationFailed(req, res, error);
        }
        
        return res.status(403).json({
          success: false,
          error: error
        });
      }
      
    } catch (error) {
      console.error('Lemma middleware error:', error);
      return res.status(500).json({
        success: false,
        error: 'Verification service temporarily unavailable'
      });
    }
  };
}

// ============================================================================
// EXPRESS ROUTES EXAMPLES
// ============================================================================

const app = express();
app.use(express.json());
app.use(require('express-session')({
  secret: process.env.SESSION_SECRET || 'change-me-in-production',
  resave: false,
  saveUninitialized: false
}));

const lemma = new LemmaClient(LEMMA_API_KEY);

// Health check route
app.get('/health', async (req, res) => {
  try {
    const health = await lemma.healthCheck();
    res.json({ 
      status: 'ok', 
      lemma_service: health.status,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    res.status(503).json({ 
      status: 'error', 
      error: error.message 
    });
  }
});

// Generate challenge for frontend
app.get('/api/challenge', async (req, res) => {
  try {
    const challenge = await lemma.generateChallenge();
    res.json({
      success: true,
      data: challenge
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// Public endpoint - no verification required
app.get('/api/public', (req, res) => {
  res.json({
    message: 'This is a public endpoint accessible to everyone',
    timestamp: new Date().toISOString()
  });
});

// Protected endpoint - requires human verification
app.post('/api/protected', lemmaMiddleware(), (req, res) => {
  res.json({
    message: 'This content is only accessible to verified humans',
    user_id: req.lemmaUser,
    timestamp: new Date().toISOString(),
    data: {
      secret: 'Human-only content here',
      user_privileges: ['view_premium_content', 'post_comments', 'access_api']
    }
  });
});

// Admin endpoint with custom verification handling
app.get('/api/admin', lemmaMiddleware({
  domain: 'admin.yourdomain.com',
  onVerificationFailed: (req, res, error) => {
    res.status(403).json({
      success: false,
      error: 'Admin access requires human verification',
      redirect: '/admin/verify'
    });
  }
}), (req, res) => {
  res.json({
    message: 'Admin dashboard data',
    user_id: req.lemmaUser,
    admin_data: {
      total_users: 1250,
      verified_humans: 950,
      bot_prevention_rate: '76%'
    }
  });
});

// Usage analytics endpoint
app.get('/api/usage', async (req, res) => {
  try {
    const now = new Date();
    const usage = await lemma.getMonthlyUsage(now.getFullYear(), now.getMonth() + 1);
    res.json({
      success: true,
      data: usage
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// ============================================================================
// REACT INTEGRATION EXAMPLES
// ============================================================================

/**
 * React Hook for Lemma verification
 * Copy this into your React application
 */
const useLemmaVerification = () => {
  const [isVerified, setIsVerified] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [challenge, setChallenge] = useState(null);

  // Generate challenge
  const generateChallenge = async () => {
    try {
      setIsLoading(true);
      const response = await fetch('/api/challenge');
      const data = await response.json();
      
      if (data.success) {
        setChallenge(data.data.challenge);
        return data.data.challenge;
      } else {
        throw new Error(data.error);
      }
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setIsLoading(false);
    }
  };

  // Verify with Lemma credential
  const verifyWithLemma = async (presentation) => {
    try {
      setIsLoading(true);
      setError(null);

      // Get fresh challenge if needed
      const currentChallenge = challenge || await generateChallenge();
      if (!currentChallenge) return false;

      const response = await fetch('/api/protected', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          presentation,
          challenge: currentChallenge
        })
      });

      const data = await response.json();

      if (data.success) {
        setIsVerified(true);
        return true;
      } else {
        setError(data.error);
        return false;
      }
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      setIsLoading(false);
    }
  };

  return {
    isVerified,
    isLoading,
    error,
    challenge,
    generateChallenge,
    verifyWithLemma
  };
};

/**
 * React Component for Lemma verification gate
 */
const LemmaGate = ({ children, fallback = null }) => {
  const { isVerified, isLoading, error, verifyWithLemma } = useLemmaVerification();

  useEffect(() => {
    // Check for existing Lemma credential in browser
    const checkExistingCredential = async () => {
      if (window.lemmaWallet) {
        const credential = await window.lemmaWallet.getFirstCredential();
        if (credential) {
          await verifyWithLemma(credential);
        }
      }
    };

    checkExistingCredential();
  }, []);

  if (isLoading) {
    return <div className="lemma-loading">Verifying human status...</div>;
  }

  if (error) {
    return (
      <div className="lemma-error">
        <p>Verification Error: {error}</p>
        <button onClick={() => window.location.href = 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/verify'}>
          Get Verified
        </button>
      </div>
    );
  }

  if (!isVerified) {
    return fallback || (
      <div className="lemma-verification-required">
        <h3>Human Verification Required</h3>
        <p>This content is only accessible to verified humans.</p>
        <a 
          href="https://lemma-enterprise-0f6ba17076c1.herokuapp.com/verify" 
          className="lemma-verify-button"
        >
          Verify with Lemma
        </a>
      </div>
    );
  }

  return children;
};

// ============================================================================
// TESTING UTILITIES
// ============================================================================

/**
 * Test the Lemma integration
 */
async function testLemmaIntegration() {
  console.log('🧪 Testing Lemma Integration...');
  
  try {
    // Test health check
    const health = await lemma.healthCheck();
    console.log('✅ Health check:', health.status);

    // Test challenge generation
    const challenge = await lemma.generateChallenge();
    console.log('✅ Challenge generated:', challenge.challenge.substring(0, 10) + '...');

    // Test usage metrics (if available)
    try {
      const usage = await lemma.getMonthlyUsage(2025, 6);
      console.log('✅ Usage metrics retrieved:', usage.total_verifications, 'verifications');
    } catch (err) {
      console.log('ℹ️ Usage metrics not available (normal for new accounts)');
    }

    console.log('🎉 All tests passed! Lemma integration is ready.');
    
  } catch (error) {
    console.error('❌ Integration test failed:', error.message);
  }
}

// ============================================================================
// EXPORTS
// ============================================================================

module.exports = {
  LemmaClient,
  lemmaMiddleware,
  testLemmaIntegration,
  // React components for copy-paste (as strings for documentation)
  reactHook: useLemmaVerification.toString(),
  reactComponent: LemmaGate.toString()
};

// ============================================================================
// USAGE EXAMPLES
// ============================================================================

/*

// 1. Basic Express Setup
const express = require('express');
const { lemmaMiddleware } = require('./lemma-integration');

const app = express();
app.use('/protected', lemmaMiddleware(), (req, res) => {
  res.json({ message: 'Human-only content', user: req.lemmaUser });
});

// 2. React Integration
import React from 'react';

const ProtectedPage = () => (
  <LemmaGate fallback={<div>Please verify you're human</div>}>
    <h1>Welcome, verified human!</h1>
    <p>This content is bot-free.</p>
  </LemmaGate>
);

// 3. Manual Verification
const lemma = new LemmaClient(process.env.LEMMA_API_KEY);

async function verifyUser(presentation, challenge) {
  const result = await lemma.verifyHuman(presentation, challenge, 'yourdomain.com');
  return result.success && result.data.verified;
}

// 4. Environment Variables Required
// LEMMA_API_KEY=your_api_key_here
// SESSION_SECRET=your_session_secret_here

*/

// Start server if this file is run directly
if (require.main === module) {
  const PORT = process.env.PORT || 3000;
  
  app.listen(PORT, () => {
    console.log(`🚀 Server running on port ${PORT}`);
    console.log(`📖 API docs: http://localhost:${PORT}/api/health`);
    console.log(`🔒 Protected endpoint: http://localhost:${PORT}/api/protected`);
    
    // Run integration test
    testLemmaIntegration();
  });
} 