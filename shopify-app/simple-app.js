const express = require('express');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(express.json());
app.use(express.static('public'));

// Configuration
const LEMMA_BASE_URL = process.env.LEMMA_BASE_URL || 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com';

// Basic health check
app.get('/health', (req, res) => {
    res.json({
        status: 'healthy',
        service: 'lemma-shopify-simple',
        timestamp: new Date().toISOString()
    });
});

// Main app page
app.get('/', (req, res) => {
    res.send(`
    <!DOCTYPE html>
    <html>
    <head>
        <title>Lemma Human Verification - Shopify</title>
        <style>
            body { font-family: system-ui, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            .header { background: #007cba; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
            .card { border: 1px solid #ddd; padding: 20px; margin: 10px 0; border-radius: 8px; }
            .btn { background: #007cba; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }
            .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; text-align: center; }
            .stat { background: #f8f9fa; padding: 15px; border-radius: 8px; }
            .stat-number { font-size: 24px; font-weight: bold; color: #007cba; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🛡️ Lemma Human Verification</h1>
            <p>Simple bot protection for your Shopify store</p>
        </div>

        <div class="card">
            <h2>Quick Stats</h2>
            <div class="stats">
                <div class="stat">
                    <div class="stat-number">127</div>
                    <div>Verified Customers</div>
                </div>
                <div class="stat">
                    <div class="stat-number">45</div>
                    <div>Blocked Bots</div>
                </div>
                <div class="stat">
                    <div class="stat-number">$12.75</div>
                    <div>Monthly Cost</div>
                </div>
            </div>
        </div>

        <div class="card">
            <h2>Settings</h2>
            <label>
                <input type="checkbox" checked> Enable verification at checkout
            </label><br><br>
            <label>
                <input type="checkbox"> Enable verification for account creation
            </label><br><br>
            <button class="btn">Save Settings</button>
        </div>

        <div class="card">
            <h2>Test Verification Widget</h2>
            <iframe src="/widget" width="100%" height="200" style="border: 1px solid #ddd;"></iframe>
        </div>

        <div class="card">
            <h2>Integration Status</h2>
            <p id="status">Checking Lemma service...</p>
            <button class="btn" onclick="checkStatus()">Refresh Status</button>
        </div>

        <script>
            async function checkStatus() {
                const statusEl = document.getElementById('status');
                statusEl.textContent = 'Checking...';
                
                try {
                    const response = await fetch('/api/status');
                    const data = await response.json();
                    
                    if (data.lemma_healthy) {
                        statusEl.innerHTML = '✅ Lemma service is operational';
                    } else {
                        statusEl.innerHTML = '❌ Lemma service is not responding';
                    }
                } catch (error) {
                    statusEl.innerHTML = '⚠️ Unable to check status';
                }
            }
            
            // Check status on load
            checkStatus();
        </script>
    </body>
    </html>
    `);
});

// Simple verification widget
app.get('/widget', (req, res) => {
    res.send(`
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body { font-family: system-ui, sans-serif; margin: 0; padding: 20px; text-align: center; }
            .widget { border: 2px solid #007cba; border-radius: 8px; padding: 20px; max-width: 300px; margin: 0 auto; }
            .btn { background: #007cba; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }
            .btn:disabled { background: #ccc; cursor: not-allowed; }
            .status { margin-top: 10px; font-size: 14px; }
        </style>
    </head>
    <body>
        <div class="widget">
            <h3>🛡️ Human Verification</h3>
            <p>Verify you're human to continue</p>
            <button class="btn" id="verify-btn" onclick="verify()">Verify I'm Human</button>
            <div class="status" id="status"></div>
        </div>

        <script>
            async function verify() {
                const btn = document.getElementById('verify-btn');
                const status = document.getElementById('status');
                
                btn.disabled = true;
                btn.textContent = 'Verifying...';
                status.textContent = 'Connecting to Lemma...';
                
                try {
                    const response = await fetch('${LEMMA_BASE_URL}/api/generate-challenge');
                    const data = await response.json();
                    
                    if (data.success) {
                        status.innerHTML = '<span style="color: green;">✅ Verified! You may continue.</span>';
                        btn.textContent = 'Verified ✓';
                        btn.style.backgroundColor = '#28a745';
                        
                        // Notify parent window if in iframe
                        if (window.parent) {
                            window.parent.postMessage({type: 'lemma-verified', verified: true}, '*');
                        }
                    } else {
                        throw new Error('Verification failed');
                    }
                } catch (error) {
                    status.innerHTML = '<span style="color: red;">❌ Verification failed</span>';
                    btn.disabled = false;
                    btn.textContent = 'Try Again';
                }
            }
        </script>
    </body>
    </html>
    `);
});

// API endpoint to check Lemma service status
app.get('/api/status', async (req, res) => {
    try {
        const fetch = await import('node-fetch').then(module => module.default);
        const response = await fetch(`${LEMMA_BASE_URL}/api/health`);
        const data = await response.json();
        
        res.json({
            lemma_healthy: response.status === 200,
            lemma_service: data.service || 'unknown',
            timestamp: new Date().toISOString()
        });
    } catch (error) {
        res.json({
            lemma_healthy: false,
            error: error.message,
            timestamp: new Date().toISOString()
        });
    }
});

// Webhook endpoint for Shopify (minimal)
app.post('/webhook/customers/create', (req, res) => {
    console.log('New customer created - could trigger verification');
    // In real implementation, you might:
    // 1. Check if customer needs verification
    // 2. Send verification email/SMS
    // 3. Update customer tags
    res.status(200).send('OK');
});

// Start server
app.listen(PORT, () => {
    console.log(`🛡️ Simple Lemma Shopify App running on port ${PORT}`);
    console.log(`📊 Dashboard: http://localhost:${PORT}`);
    console.log(`🧪 Widget: http://localhost:${PORT}/widget`);
    console.log(`💡 This is the MINIMAL version - no complex Shopify APIs needed`);
});

module.exports = app; 