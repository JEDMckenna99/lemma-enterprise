const express = require('express');
const { Shopify } = require('@shopify/shopify-api');
const bodyParser = require('body-parser');
const cors = require('cors');
const crypto = require('crypto');
const fetch = require('node-fetch');

// Lemma Integration
const LemmaVerificationService = require('./services/lemma-verification-service');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(bodyParser.json());
app.use(cors());
app.use(express.static('public'));

// Initialize Lemma service
const lemmaService = new LemmaVerificationService({
  apiKey: process.env.LEMMA_API_KEY,
  baseUrl: process.env.LEMMA_BASE_URL || 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com',
  onboardingFee: 2.50 // Updated to $2.50 as requested
});

// Shopify configuration
Shopify.Context.initialize({
  API_KEY: process.env.SHOPIFY_API_KEY,
  API_SECRET_KEY: process.env.SHOPIFY_API_SECRET,
  SCOPES: [
    'read_customers',
    'write_customers',
    'read_orders',
    'write_orders',
    'read_products',
    'write_products',
    'read_script_tags',
    'write_script_tags'
  ],
  HOST_NAME: process.env.SHOPIFY_APP_URL,
  API_VERSION: '2024-01',
  IS_EMBEDDED_APP: true,
  SESSION_STORAGE: new Shopify.Session.MemorySessionStorage()
});

// OAuth routes
app.get('/auth', async (req, res) => {
  const authRoute = await Shopify.Auth.beginAuth(
    req,
    res,
    req.query.shop,
    '/auth/callback',
    false
  );
  return res.redirect(authRoute);
});

app.get('/auth/callback', async (req, res) => {
  try {
    const session = await Shopify.Auth.validateAuthCallback(req, res, req.query);
    
    // Install webhook endpoints
    await installWebhooks(session);
    
    // Install script tags for Lemma Shield
    await installScriptTags(session);
    
    res.redirect(`/?shop=${session.shop}&host=${req.query.host}`);
  } catch (error) {
    console.error('OAuth callback error:', error);
    res.status(500).send('Authentication failed');
  }
});

// Main app route
app.get('/', async (req, res) => {
  const { shop, host } = req.query;
  
  if (!shop || !host) {
    return res.status(400).send('Missing shop or host parameter');
  }

  res.send(`
    <!DOCTYPE html>
    <html>
    <head>
      <title>Lemma Human Verification for Shopify</title>
      <script src="https://unpkg.com/@shopify/app-bridge@3"></script>
      <script src="https://unpkg.com/@shopify/app-bridge-utils@3"></script>
      <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        .header { background: #635bff; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .card { background: white; border: 1px solid #e1e3e5; border-radius: 8px; padding: 20px; margin-bottom: 20px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; }
        .stat-card { background: #f6f8fa; padding: 15px; border-radius: 8px; text-align: center; }
        .stat-number { font-size: 24px; font-weight: bold; color: #635bff; }
        .stat-label { color: #6a737d; font-size: 14px; }
        .btn { background: #635bff; color: white; padding: 12px 24px; border: none; border-radius: 6px; cursor: pointer; }
        .btn:hover { background: #5a52e8; }
        .setup-status { padding: 10px; border-radius: 6px; margin: 10px 0; }
        .setup-complete { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .setup-pending { background: #fff3cd; color: #856404; border: 1px solid #ffeaa7; }
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>🛡️ Lemma Human Verification</h1>
          <p>Protect your store from bots while maintaining excellent user experience</p>
        </div>

        <div class="card">
          <h2>Setup Status</h2>
          <div id="setup-status">
            <div class="setup-status setup-pending">
              ⏳ Checking integration status...
            </div>
          </div>
        </div>

        <div class="card">
          <h2>Verification Statistics</h2>
          <div class="stats">
            <div class="stat-card">
              <div class="stat-number" id="verified-customers">-</div>
              <div class="stat-label">Verified Customers</div>
            </div>
            <div class="stat-card">
              <div class="stat-number" id="blocked-bots">-</div>
              <div class="stat-label">Blocked Bots</div>
            </div>
            <div class="stat-card">
              <div class="stat-number" id="monthly-cost">$-</div>
              <div class="stat-label">Monthly Cost</div>
            </div>
          </div>
        </div>

        <div class="card">
          <h2>Lemma Network Pricing</h2>
          <p><strong>One-time verification fee:</strong> $2.50 per new customer</p>
          <p><strong>Monthly rate:</strong> $0.045-0.10 per verified customer (decreases as network grows)</p>
          <p><strong>Network benefit:</strong> Customers verified once work across all Lemma-integrated stores</p>
        </div>

        <div class="card">
          <h2>Actions</h2>
          <button class="btn" onclick="checkSetup()">Check Setup</button>
          <button class="btn" onclick="testVerification()">Test Verification</button>
          <button class="btn" onclick="viewLogs()">View Logs</button>
        </div>
      </div>

      <script>
        const AppBridge = window['app-bridge'];
        const app = AppBridge.createApp({
          apiKey: '${process.env.SHOPIFY_API_KEY}',
          host: '${host}',
          forceRedirect: true
        });

        // Load dashboard data
        async function loadDashboard() {
          try {
            const response = await fetch('/api/dashboard', {
              headers: { 'X-Shop-Domain': '${shop}' }
            });
            const data = await response.json();
            
            document.getElementById('verified-customers').textContent = data.verifiedCustomers || 0;
            document.getElementById('blocked-bots').textContent = data.blockedBots || 0;
            document.getElementById('monthly-cost').textContent = '$' + (data.monthlyCost || 0).toFixed(2);
            
            updateSetupStatus(data.setupComplete);
          } catch (error) {
            console.error('Failed to load dashboard:', error);
          }
        }

        function updateSetupStatus(isComplete) {
          const statusDiv = document.getElementById('setup-status');
          if (isComplete) {
            statusDiv.innerHTML = '<div class="setup-status setup-complete">✅ Lemma Shield is active and protecting your store</div>';
          } else {
            statusDiv.innerHTML = '<div class="setup-status setup-pending">⚠️ Setup incomplete - some features may not be working</div>';
          }
        }

        async function checkSetup() {
          try {
            const response = await fetch('/api/check-setup', {
              method: 'POST',
              headers: { 
                'Content-Type': 'application/json',
                'X-Shop-Domain': '${shop}'
              }
            });
            const result = await response.json();
            alert(result.message || 'Setup check completed');
            loadDashboard();
          } catch (error) {
            alert('Setup check failed: ' + error.message);
          }
        }

        async function testVerification() {
          try {
            const response = await fetch('/api/test-verification', {
              method: 'POST',
              headers: { 
                'Content-Type': 'application/json',
                'X-Shop-Domain': '${shop}'
              }
            });
            const result = await response.json();
            alert(result.message || 'Test completed');
          } catch (error) {
            alert('Test failed: ' + error.message);
          }
        }

        function viewLogs() {
          window.open('/logs?shop=${shop}', '_blank');
        }

        // Load dashboard on page load
        loadDashboard();
        
        // Refresh every 30 seconds
        setInterval(loadDashboard, 30000);
      </script>
    </body>
    </html>
  `);
});

// API Routes
app.get('/api/dashboard', async (req, res) => {
  try {
    const shop = req.headers['x-shop-domain'];
    if (!shop) {
      return res.status(400).json({ error: 'Missing shop domain' });
    }

    // Get verification stats from Lemma
    const stats = await lemmaService.getShopStats(shop);
    
    res.json({
      verifiedCustomers: stats.verifiedCustomers,
      blockedBots: stats.blockedBots,
      monthlyCost: stats.monthlyCost,
      setupComplete: stats.setupComplete
    });
  } catch (error) {
    console.error('Dashboard API error:', error);
    res.status(500).json({ error: 'Failed to load dashboard data' });
  }
});

app.post('/api/check-setup', async (req, res) => {
  try {
    const shop = req.headers['x-shop-domain'];
    const setupStatus = await lemmaService.checkSetup(shop);
    
    res.json({
      success: true,
      message: setupStatus.message,
      setupComplete: setupStatus.complete,
      issues: setupStatus.issues
    });
  } catch (error) {
    console.error('Setup check error:', error);
    res.status(500).json({ error: 'Setup check failed' });
  }
});

app.post('/api/test-verification', async (req, res) => {
  try {
    const shop = req.headers['x-shop-domain'];
    const testResult = await lemmaService.testVerification(shop);
    
    res.json({
      success: testResult.success,
      message: testResult.message,
      latency: testResult.latency
    });
  } catch (error) {
    console.error('Test verification error:', error);
    res.status(500).json({ error: 'Test failed' });
  }
});

// Webhook endpoints
app.post('/webhooks/customers/create', async (req, res) => {
  try {
    const customer = req.body;
    const shop = req.headers['x-shopify-shop-domain'];
    
    // Check if customer needs Lemma verification
    await lemmaService.handleNewCustomer(customer, shop);
    
    res.status(200).send('OK');
  } catch (error) {
    console.error('Customer create webhook error:', error);
    res.status(500).send('Error processing webhook');
  }
});

app.post('/webhooks/orders/create', async (req, res) => {
  try {
    const order = req.body;
    const shop = req.headers['x-shopify-shop-domain'];
    
    // Verify customer before processing order
    const verificationResult = await lemmaService.verifyOrderCustomer(order, shop);
    
    if (!verificationResult.verified) {
      // Log potential bot order
      console.warn('Unverified order detected:', order.id);
    }
    
    res.status(200).send('OK');
  } catch (error) {
    console.error('Order create webhook error:', error);
    res.status(500).send('Error processing webhook');
  }
});

// Lemma callback endpoint
app.post('/lemma-callback', async (req, res) => {
  try {
    const { userId, verification, shop } = req.body;
    
    // Process completed verification
    await lemmaService.processVerificationCallback(userId, verification, shop);
    
    res.json({ success: true });
  } catch (error) {
    console.error('Lemma callback error:', error);
    res.status(500).json({ error: 'Callback processing failed' });
  }
});

// Utility functions
async function installWebhooks(session) {
  const client = new Shopify.Clients.Rest(session.shop, session.accessToken);
  
  const webhooks = [
    {
      webhook: {
        topic: 'customers/create',
        address: `${process.env.SHOPIFY_APP_URL}/webhooks/customers/create`,
        format: 'json'
      }
    },
    {
      webhook: {
        topic: 'orders/create',
        address: `${process.env.SHOPIFY_APP_URL}/webhooks/orders/create`,
        format: 'json'
      }
    }
  ];

  for (const webhook of webhooks) {
    try {
      await client.post({ path: 'webhooks', data: webhook });
      console.log(`Installed webhook: ${webhook.webhook.topic}`);
    } catch (error) {
      console.error(`Failed to install webhook ${webhook.webhook.topic}:`, error);
    }
  }
}

async function installScriptTags(session) {
  const client = new Shopify.Clients.Rest(session.shop, session.accessToken);
  
  const scriptTag = {
    script_tag: {
      event: 'onload',
      src: `${process.env.SHOPIFY_APP_URL}/scripts/lemma-shield.js`,
      display_scope: 'all'
    }
  };

  try {
    await client.post({ path: 'script_tags', data: scriptTag });
    console.log('Installed Lemma Shield script tag');
  } catch (error) {
    console.error('Failed to install script tag:', error);
  }
}

// Error handling
app.use((error, req, res, next) => {
  console.error('App error:', error);
  res.status(500).json({ error: 'Internal server error' });
});

app.listen(PORT, () => {
  console.log(`🛡️ Lemma Shopify App running on port ${PORT}`);
  console.log(`💰 Onboarding fee set to $${lemmaService.onboardingFee}`);
  console.log(`🌐 Lemma base URL: ${lemmaService.baseUrl}`);
});

module.exports = app; 