#!/usr/bin/env node
/**
 * Production Endpoint Test Suite
 * Tests all Shopify app endpoints for production readiness
 */

const fetch = import('node-fetch').then(module => module.default);
const { spawn } = require('child_process');

// Configuration
const APP_PORT = 3000;
const LEMMA_BASE_URL = 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com';
const TEST_TIMEOUT = 10000;

let server;

async function startServer() {
  console.log('🚀 Starting test server...');
  return new Promise((resolve, reject) => {
    server = spawn('node', ['simple-app.js'], {
      env: { ...process.env, LEMMA_BASE_URL },
      stdio: 'pipe'
    });

    server.stdout.on('data', (data) => {
      const output = data.toString();
      console.log(`Server: ${output.trim()}`);
      if (output.includes('running on port')) {
        setTimeout(() => resolve(), 2000); // Give server time to fully start
      }
    });

    server.stderr.on('data', (data) => {
      console.error(`Server Error: ${data}`);
    });

    server.on('error', reject);
    
    // Timeout fallback
    setTimeout(() => resolve(), 5000);
  });
}

function stopServer() {
  if (server) {
    console.log('🛑 Stopping test server...');
    server.kill('SIGTERM');
  }
}

async function testEndpoint(name, url, expectedStatus = 200, method = 'GET') {
  console.log(`\n🧪 Testing ${name}...`);
  
  try {
    const startTime = Date.now();
    const response = await fetch(url, { 
      method,
      timeout: TEST_TIMEOUT,
      headers: {
        'User-Agent': 'Lemma-Production-Test'
      }
    });
    
    const endTime = Date.now();
    const responseTime = endTime - startTime;
    
    const success = response.status === expectedStatus || 
                   (Array.isArray(expectedStatus) && expectedStatus.includes(response.status));
    
    console.log(`  Status: ${response.status} ${success ? '✅' : '❌'}`);
    console.log(`  Response Time: ${responseTime}ms`);
    
    if (success && response.headers.get('content-type')?.includes('application/json')) {
      try {
        const data = await response.json();
        console.log(`  Response Sample: ${JSON.stringify(data).substring(0, 100)}...`);
      } catch (e) {
        console.log(`  Response: JSON parse error (${e.message})`);
      }
    }
    
    return {
      name,
      success,
      status: response.status,
      responseTime,
      url
    };
    
  } catch (error) {
    console.log(`  ❌ Error: ${error.message}`);
    return {
      name,
      success: false,
      error: error.message,
      url
    };
  }
}

async function runProductionTests() {
  console.log('🛡️ LEMMA SHOPIFY APP - PRODUCTION READINESS TEST');
  console.log('='.repeat(60));
  console.log(`Test Time: ${new Date().toISOString()}`);
  console.log(`Lemma API: ${LEMMA_BASE_URL}`);
  console.log(`App Port: ${APP_PORT}`);
  console.log();

  const results = [];
  const baseUrl = `http://localhost:${APP_PORT}`;

  try {
    // Start the server
    await startServer();

    console.log('\n📋 TESTING CORE APP ENDPOINTS');
    console.log('-'.repeat(40));

    // Test core endpoints
    const tests = [
      ['Health Check', `${baseUrl}/health`],
      ['Main Dashboard', `${baseUrl}/`],
      ['Verification Widget', `${baseUrl}/widget`],
      ['API Status Check', `${baseUrl}/api/status`],
      ['Customer Webhook (POST)', `${baseUrl}/webhook/customers/create`, 200, 'POST']
    ];

    for (const [name, url, expectedStatus, method] of tests) {
      const result = await testEndpoint(name, url, expectedStatus, method);
      results.push(result);
    }

    console.log('\n📡 TESTING LEMMA API CONNECTIVITY');
    console.log('-'.repeat(40));

    // Test Lemma API endpoints
    const lemmaTests = [
      ['Lemma Health', `${LEMMA_BASE_URL}/api/health`],
      ['Generate Challenge', `${LEMMA_BASE_URL}/api/generate-challenge`],
      ['Verify Human Endpoint', `${LEMMA_BASE_URL}/api/verify-human`, [400, 200]] // 400 is OK for missing data
    ];

    for (const [name, url, expectedStatus] of lemmaTests) {
      const result = await testEndpoint(name, url, expectedStatus);
      results.push(result);
    }

  } finally {
    stopServer();
  }

  // Generate report
  console.log('\n📊 PRODUCTION READINESS REPORT');
  console.log('='.repeat(60));

  const successful = results.filter(r => r.success);
  const failed = results.filter(r => !r.success);

  console.log(`✅ Successful Tests: ${successful.length}/${results.length}`);
  console.log(`❌ Failed Tests: ${failed.length}/${results.length}`);

  if (failed.length > 0) {
    console.log('\n❌ FAILED TESTS:');
    failed.forEach(test => {
      console.log(`  • ${test.name}: ${test.error || `Status ${test.status}`}`);
    });
  }

  // Performance Analysis
  const responseTimes = successful.filter(r => r.responseTime).map(r => r.responseTime);
  if (responseTimes.length > 0) {
    const avgResponseTime = responseTimes.reduce((a, b) => a + b, 0) / responseTimes.length;
    const maxResponseTime = Math.max(...responseTimes);
    
    console.log('\n📈 PERFORMANCE METRICS:');
    console.log(`  Average Response Time: ${avgResponseTime.toFixed(0)}ms`);
    console.log(`  Maximum Response Time: ${maxResponseTime}ms`);
    console.log(`  Performance Target: <2000ms ${maxResponseTime < 2000 ? '✅' : '❌'}`);
  }

  // Final Assessment
  const readinessScore = (successful.length / results.length) * 100;
  console.log('\n🎯 PRODUCTION READINESS ASSESSMENT:');
  console.log(`  Readiness Score: ${readinessScore.toFixed(1)}%`);
  
  if (readinessScore >= 90) {
    console.log('  Status: ✅ READY FOR PRODUCTION');
  } else if (readinessScore >= 75) {
    console.log('  Status: ⚠️  MOSTLY READY - Address failed tests');
  } else {
    console.log('  Status: ❌ NOT READY - Critical issues need fixing');
  }

  console.log('\n🚀 NEXT STEPS:');
  if (readinessScore >= 90) {
    console.log('  1. Deploy to production environment');
    console.log('  2. Update Shopify app configuration');
    console.log('  3. Set up monitoring and alerts');
    console.log('  4. Begin merchant onboarding');
  } else {
    console.log('  1. Fix failed tests');
    console.log('  2. Re-run production tests');
    console.log('  3. Optimize performance if needed');
    console.log('  4. Consider additional testing');
  }

  process.exit(failed.length > 0 ? 1 : 0);
}

// Handle graceful shutdown
process.on('SIGINT', () => {
  console.log('\n\n🛑 Test interrupted by user');
  stopServer();
  process.exit(1);
});

process.on('SIGTERM', () => {
  console.log('\n\n🛑 Test terminated');
  stopServer();
  process.exit(1);
});

// Run the tests
if (require.main === module) {
  runProductionTests().catch((error) => {
    console.error('\n❌ Test suite failed:', error);
    stopServer();
    process.exit(1);
  });
}

module.exports = { runProductionTests }; 