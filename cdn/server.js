/**
 * Lemma Crypto CDN Server
 * 
 * Serves WASM crypto engine for both:
 * - Federated Identity Network (5-15μs human verification)
 * - IAM System (5-15μs permission checking)
 */

const express = require('express');
const path = require('path');
const fs = require('fs');
const compression = require('compression');
const helmet = require('helmet');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 3000;

// Security middleware
app.use(helmet({
  contentSecurityPolicy: false, // Allow WASM execution
  crossOriginEmbedderPolicy: false
}));

// Enable CORS for global CDN access
app.use(cors({
  origin: '*',
  methods: ['GET', 'HEAD', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization']
}));

// Compression for better performance
app.use(compression());

// Serve static crypto assets
app.use('/crypto', express.static(path.join(__dirname, 'dist/crypto'), {
  maxAge: '1y', // Cache for 1 year
  immutable: true,
  setHeaders: (res, filePath) => {
    if (filePath.endsWith('.wasm')) {
      res.set('Content-Type', 'application/wasm');
    } else if (filePath.endsWith('.js')) {
      res.set('Content-Type', 'application/javascript');
    }
  }
}));

// Crypto engine health check
app.get('/crypto/health', (req, res) => {
  res.json({
    status: 'ready',
    crypto_engine: 'lemma_unified_wasm',
    systems: ['federated_identity', 'iam_permissions'],
    performance: '5-15μs browser authentication',
    capabilities: ['Ed25519', 'OPRF', 'Bloom', 'ZKP'],
    offline: true,
    cdn_ready: true,
    timestamp: Date.now()
  });
});

// Performance test endpoint for both systems
app.get('/crypto/test', (req, res) => {
  const systemType = req.query.system || 'auto';
  
  res.json({
    test_available: true,
    system_type: systemType,
    expected_performance: '5-15μs',
    test_endpoints: {
      federated_id: '/crypto/test/federated',
      iam_system: '/crypto/test/iam',
      auto_detect: '/crypto/test/auto'
    },
    documentation: '/crypto/docs'
  });
});

// Federated Identity test endpoint
app.get('/crypto/test/federated', (req, res) => {
  res.send(`
<!DOCTYPE html>
<html>
<head>
    <title>Federated Identity WASM Test</title>
</head>
<body>
    <h1>🌐 Federated Identity Network - WASM Test</h1>
    <p>Target: 5-15μs human verification</p>
    
    <button onclick="testFederatedID()">Test Human Verification</button>
    <div id="federated-results"></div>
    
    <script type="module">
        window.testFederatedID = async function() {
            const results = document.getElementById('federated-results');
            results.innerHTML = '🔄 Testing federated identity...';
            
            try {
                // Load federated ID engine from CDN
                const { LemmaFederatedID } = await import('/crypto/federated-id.js');
                
                // Test credential
                const credential = {
                    claims: {
                        packageType: 'identity',
                        isHuman: true,
                        verificationLevel: 'high'
                    }
                };
                
                // Verify human (5-15μs target)
                const verification = await LemmaFederatedID.verifyHuman(credential);
                
                results.innerHTML = \`
                    <h3>✅ Federated Identity Results:</h3>
                    <p><strong>Is Human:</strong> \${verification.isHuman}</p>
                    <p><strong>Cross-Site Valid:</strong> \${verification.crossSiteValid}</p>
                    <p><strong>Time:</strong> \${verification.verificationTimeUs.toFixed(3)} μs</p>
                    <p><strong>Bot Protection:</strong> \${verification.botProtection}</p>
                    <p><strong>Offline:</strong> \${verification.offline}</p>
                \`;
                
            } catch (error) {
                results.innerHTML = \`❌ Error: \${error.message}\`;
            }
        };
    </script>
</body>
</html>
  `);
});

// IAM System test endpoint
app.get('/crypto/test/iam', (req, res) => {
  res.send(`
<!DOCTYPE html>
<html>
<head>
    <title>IAM System WASM Test</title>
</head>
<body>
    <h1>🔐 IAM Permission System - WASM Test</h1>
    <p>Target: 5-15μs permission verification</p>
    
    <button onclick="testIAMSystem()">Test Permission Check</button>
    <div id="iam-results"></div>
    
    <script type="module">
        window.testIAMSystem = async function() {
            const results = document.getElementById('iam-results');
            results.innerHTML = '🔄 Testing IAM permissions...';
            
            try {
                // Load IAM engine from CDN
                const { LemmaIAM } = await import('/crypto/iam-permissions.js');
                
                // Test permission lemma
                const permissionLemma = {
                    claims: {
                        packageType: 'permission',
                        siteId: 'test-site',
                        permissionId: 'admin_access',
                        scope: 'users:*,sites:*'
                    }
                };
                
                // Verify permission (5-15μs target)
                const verification = await LemmaIAM.verifyPermission(permissionLemma, 'test-site');
                
                results.innerHTML = \`
                    <h3>✅ IAM System Results:</h3>
                    <p><strong>Has Access:</strong> \${verification.hasAccess}</p>
                    <p><strong>Permission Level:</strong> \${verification.permissionLevel}</p>
                    <p><strong>Time:</strong> \${verification.verificationTimeUs.toFixed(3)} μs</p>
                    <p><strong>Site Specific:</strong> \${verification.siteSpecific}</p>
                    <p><strong>Offline:</strong> \${verification.offline}</p>
                \`;
                
            } catch (error) {
                results.innerHTML = \`❌ Error: \${error.message}\`;
            }
        };
    </script>
</body>
</html>
  `);
});

// Main documentation
app.get('/crypto/docs', (req, res) => {
  res.json({
    title: 'Lemma Crypto CDN Documentation',
    description: 'Ultra-fast WASM crypto for Federated Identity + IAM',
    systems: {
      federated_identity: {
        purpose: 'Cross-site human verification',
        performance: '5-15μs',
        endpoint: '/crypto/federated-id.js',
        test: '/crypto/test/federated'
      },
      iam_system: {
        purpose: 'Site-specific permission checking', 
        performance: '5-15μs',
        endpoint: '/crypto/iam-permissions.js',
        test: '/crypto/test/iam'
      }
    },
    integration: {
      auto_detect: '/crypto/auto-detect.js',
      unified_engine: '/crypto/lemma-unified-crypto.js',
      manifest: '/crypto/manifest.json'
    },
    performance: {
      wasm_browser: '5-15μs',
      local_python: '33μs',
      network_api: '93-118μs'
    }
  });
});

// Root redirect
app.get('/', (req, res) => {
  res.redirect('/crypto/docs');
});

// Start server
app.listen(PORT, () => {
  console.log(`🌐 Lemma Crypto CDN Server running on port ${PORT}`);
  console.log(`🔐 Serving crypto assets for Federated Identity + IAM`);
  console.log(`⚡ Target performance: 5-15μs WASM authentication`);
  console.log(`📡 CDN endpoints:`);
  console.log(`   Health: http://localhost:${PORT}/crypto/health`);
  console.log(`   Fed ID Test: http://localhost:${PORT}/crypto/test/federated`);
  console.log(`   IAM Test: http://localhost:${PORT}/crypto/test/iam`);
  console.log(`   Documentation: http://localhost:${PORT}/crypto/docs`);
});

module.exports = app;
