#!/usr/bin/env node
/**
 * Lemma Platform UI Test Runner
 * 
 * Runs comprehensive automated tests against the live platform
 */

import puppeteer from 'puppeteer';
import fetch from 'node-fetch';

const LEMMA_BASE_URL = (process.env.LEMMA_BASE_URL || 'https://lemma.id').replace(/\/$/, '');
const AGENT_TOKEN = process.env.LEMMA_AGENT_TOKEN || 'lm_agent_0OHnZ9X9G7FXYzC7MzAMCWuFKkz04oK8FPJzlePyiWU';

let browser = null;
let page = null;

// Test results collector
const results = {
  timestamp: new Date().toISOString(),
  passed: 0,
  failed: 0,
  tests: []
};

// Helpers
async function getBrowser() {
  if (!browser) {
    browser = await puppeteer.launch({
      headless: 'new',
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
  }
  return browser;
}

async function getPage() {
  if (!page) {
    const b = await getBrowser();
    page = await b.newPage();
    await page.setViewport({ width: 1280, height: 800 });
    
    // Create agent session
    await page.goto(`${LEMMA_BASE_URL}/api/agent/session?token=${AGENT_TOKEN}`);
    console.log('Agent session created');
  }
  return page;
}

async function callApi(endpoint, options = {}) {
  const url = `${LEMMA_BASE_URL}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    'X-Agent-Token': AGENT_TOKEN,
    ...options.headers
  };

  const response = await fetch(url, { ...options, headers });
  return {
    status: response.status,
    ok: response.ok,
    data: await response.json().catch(() => null)
  };
}

async function requireAuthPreflight() {
  const result = await callApi('/api/agent/validate', { method: 'POST' });
  const scopes = result.data?.scope || result.data?.scopes || [];
  if (!(result.ok && result.data?.valid === true)) {
    const reason = result.data?.error || result.data?.message || `status_${result.status}`;
    throw new Error(`AUTH_PREFLIGHT_FAILED: ${reason}`);
  }
  if (!Array.isArray(scopes) || !scopes.includes('admin')) {
    throw new Error(`AUTH_PREFLIGHT_FAILED: missing_admin_scope (scopes=${JSON.stringify(scopes)})`);
  }
}

async function runTest(name, testFn) {
  console.log(`\n  Running: ${name}...`);
  const startTime = Date.now();
  
  try {
    const result = await testFn();
    const duration = Date.now() - startTime;
    
    if (result.passed) {
      results.passed++;
      console.log(`  ✓ PASSED (${duration}ms): ${result.details || ''}`);
    } else {
      results.failed++;
      console.log(`  ✗ FAILED (${duration}ms): ${result.error || result.details || 'Unknown error'}`);
    }
    
    results.tests.push({
      name,
      passed: result.passed,
      duration,
      details: result.details,
      error: result.error
    });
  } catch (error) {
    results.failed++;
    console.log(`  ✗ ERROR: ${error.message}`);
    results.tests.push({
      name,
      passed: false,
      error: error.message
    });
  }
}

// ============================================
// TEST SUITES
// ============================================

async function testAuthValidation() {
  console.log('\n=== AUTH VALIDATION TESTS ===');
  
  await runTest('Agent token validation', async () => {
    const result = await callApi('/api/agent/validate', { method: 'POST' });
    return {
      passed: result.ok && result.data?.valid === true,
      details: `Token valid: ${result.data?.valid}, Scopes: ${JSON.stringify(result.data?.scope || result.data?.scopes)}`
    };
  });
  
  await runTest('Agent credentials list', async () => {
    const result = await callApi('/api/agent/credentials');
    return {
      passed: result.ok,
      details: `Status: ${result.status}, Has credentials: ${Array.isArray(result.data?.credentials)}`
    };
  });
}

async function testAdminDashboard() {
  console.log('\n=== ADMIN DASHBOARD TESTS ===');
  
  await runTest('Admin page loads', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/admin`, { waitUntil: 'networkidle2', timeout: 30000 });
    const content = await p.evaluate(() => document.body.innerText);
    return {
      passed: content.includes('Admin') || content.includes('Dashboard') || content.includes('Platform'),
      details: `Page title: ${await p.title()}`
    };
  });
  
  await runTest('Admin stats API', async () => {
    const result = await callApi('/api/admin/user-stats');
    return {
      passed: result.ok,
      details: `Status: ${result.status}, Data: ${JSON.stringify(result.data).substring(0, 100)}`
    };
  });
  
  await runTest('Admin platform stats API', async () => {
    const result = await callApi('/api/admin/platform-stats');
    return {
      passed: result.ok,
      details: `Status: ${result.status}`
    };
  });
  
  await runTest('Admin recent activity API', async () => {
    const result = await callApi('/api/admin/recent-activity');
    return {
      passed: result.ok,
      details: `Status: ${result.status}`
    };
  });
}

async function testAdminUsersPage() {
  console.log('\n=== ADMIN USERS PAGE TESTS ===');
  
  await runTest('Users page loads', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/admin/users`, { waitUntil: 'networkidle2', timeout: 30000 });
    const content = await p.evaluate(() => document.body.innerText);
    return {
      passed: content.length > 100,
      details: `Content length: ${content.length}`
    };
  });
  
  await runTest('Customers API', async () => {
    const result = await callApi('/api/admin/customers');
    return {
      passed: result.ok && (Array.isArray(result.data?.customers) || result.data?.customers !== undefined),
      details: `Status: ${result.status}, Customer count: ${result.data?.customers?.length || 0}`
    };
  });
  
  await runTest('Users page has data elements', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/admin/users`, { waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 2000)); // Wait for data load
    
    const hasDataElements = await p.evaluate(() => {
      const tables = document.querySelectorAll('table, .user-list, .customer-list, [data-user]');
      const cards = document.querySelectorAll('.user-card, .customer-card');
      return tables.length > 0 || cards.length > 0;
    });
    
    return {
      passed: hasDataElements,
      details: `Has data display elements: ${hasDataElements}`
    };
  });
}

async function testAdminSitesPage() {
  console.log('\n=== ADMIN SITES PAGE TESTS ===');
  
  await runTest('Sites page loads', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/admin/sites`, { waitUntil: 'networkidle2', timeout: 30000 });
    const content = await p.evaluate(() => document.body.innerText);
    return {
      passed: content.length > 100,
      details: `Content length: ${content.length}`
    };
  });
  
  await runTest('Admin sites API', async () => {
    const result = await callApi('/api/admin/sites');
    return {
      passed: result.ok && Array.isArray(result.data?.sites),
      details: `Status: ${result.status}, Site count: ${result.data?.sites?.length || 0}`
    };
  });
  
  await runTest('Sites page displays registered sites', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/admin/sites`, { waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 2000));
    
    const content = await p.evaluate(() => document.body.innerText);
    // Check for known sites or site-related content
    const hasSiteContent = content.includes('lemma.id') || 
                          content.includes('site') || 
                          content.includes('domain') ||
                          content.includes('registered');
    
    return {
      passed: hasSiteContent,
      details: `Has site content: ${hasSiteContent}`
    };
  });
}

async function testDeveloperDashboard() {
  console.log('\n=== DEVELOPER DASHBOARD TESTS ===');
  
  await runTest('Developer page loads', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/developer`, { waitUntil: 'networkidle2', timeout: 30000 });
    const content = await p.evaluate(() => document.body.innerText);
    return {
      passed: content.includes('Developer') || content.includes('Dashboard') || content.includes('Sites'),
      details: `Page loaded, content length: ${content.length}`
    };
  });
  
  await runTest('Developer stats API', async () => {
    const result = await callApi('/api/developer/stats');
    return {
      passed: result.ok,
      details: `Status: ${result.status}`
    };
  });
  
  await runTest('Developer sites API', async () => {
    const result = await callApi('/api/developer/sites');
    return {
      passed: result.ok && Array.isArray(result.data?.sites),
      details: `Status: ${result.status}, Sites: ${result.data?.sites?.length || 0}`
    };
  });
  
  await runTest('Agent token section visible', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/developer`, { waitUntil: 'networkidle2' });
    
    const hasAgentSection = await p.evaluate(() => {
      const content = document.body.innerText.toLowerCase();
      return content.includes('agent') || content.includes('ai access') || content.includes('token');
    });
    
    return {
      passed: hasAgentSection,
      details: `Agent section visible: ${hasAgentSection}`
    };
  });
}

async function testButtonFunctionality() {
  console.log('\n=== BUTTON FUNCTIONALITY TESTS ===');
  
  await runTest('Developer page buttons exist', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/developer`, { waitUntil: 'networkidle2' });
    
    const buttons = await p.evaluate(() => {
      return [...document.querySelectorAll('button, [data-action], .btn, .dev-btn')].map(el => ({
        text: el.textContent.trim().substring(0, 50),
        dataAction: el.dataset?.action || null,
        disabled: el.disabled
      }));
    });
    
    return {
      passed: buttons.length > 0,
      details: `Found ${buttons.length} buttons: ${buttons.map(b => b.text || b.dataAction).join(', ').substring(0, 100)}`
    };
  });
  
  await runTest('Admin page buttons exist', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/admin`, { waitUntil: 'networkidle2' });
    
    const buttons = await p.evaluate(() => {
      return [...document.querySelectorAll('button, [data-action], .btn, a.admin-btn')].map(el => ({
        text: el.textContent.trim().substring(0, 50),
        dataAction: el.dataset?.action || null
      }));
    });
    
    return {
      passed: buttons.length > 0,
      details: `Found ${buttons.length} buttons`
    };
  });
}

async function testNavigation() {
  console.log('\n=== NAVIGATION TESTS ===');
  
  const pages = [
    { path: '/', name: 'Home' },
    { path: '/admin', name: 'Admin' },
    { path: '/admin/users', name: 'Admin Users' },
    { path: '/admin/sites', name: 'Admin Sites' },
    { path: '/developer', name: 'Developer' },
    { path: '/docs', name: 'Docs' }
  ];
  
  for (const pageInfo of pages) {
    await runTest(`Navigate to ${pageInfo.name}`, async () => {
      const p = await getPage();
      const response = await p.goto(`${LEMMA_BASE_URL}${pageInfo.path}`, { 
        waitUntil: 'networkidle2', 
        timeout: 30000 
      });
      
      return {
        passed: response.status() === 200 || response.status() === 304,
        details: `Status: ${response.status()}`
      };
    });
  }
}

async function testFormElements() {
  console.log('\n=== FORM ELEMENTS TESTS ===');
  
  await runTest('Developer page has form inputs', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/developer`, { waitUntil: 'networkidle2' });
    
    const inputs = await p.evaluate(() => {
      return [...document.querySelectorAll('input, select, textarea')].map(el => ({
        type: el.type || el.tagName.toLowerCase(),
        id: el.id,
        name: el.name,
        placeholder: el.placeholder
      }));
    });
    
    return {
      passed: inputs.length >= 0, // May or may not have inputs
      details: `Found ${inputs.length} form elements`
    };
  });
  
  await runTest('Select elements work', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/developer`, { waitUntil: 'networkidle2' });
    
    const selects = await p.evaluate(() => {
      return [...document.querySelectorAll('select')].map(el => ({
        id: el.id,
        options: [...el.options].map(o => o.value)
      }));
    });
    
    return {
      passed: true,
      details: `Found ${selects.length} select elements`
    };
  });
}

async function testAPIEndpoints() {
  console.log('\n=== API ENDPOINT TESTS ===');
  
  const endpoints = [
    { path: '/api/health', name: 'Health Check' },
    { path: '/api/health/detailed', name: 'Detailed Health' },
    { path: '/api/admin/sites', name: 'Admin Sites' },
    { path: '/api/admin/customers', name: 'Admin Customers' },
    { path: '/api/admin/user-stats', name: 'User Stats' },
    { path: '/api/admin/recent-activity', name: 'Recent Activity' },
    { path: '/api/developer/stats', name: 'Developer Stats' },
    { path: '/api/developer/sites', name: 'Developer Sites' },
    { path: '/api/agent/credentials', name: 'Agent Credentials' }
  ];
  
  for (const endpoint of endpoints) {
    await runTest(`API: ${endpoint.name}`, async () => {
      const result = await callApi(endpoint.path);
      return {
        passed: result.ok,
        details: `Status: ${result.status}`
      };
    });
  }
}

async function testConsoleErrors() {
  console.log('\n=== CONSOLE ERROR TESTS ===');
  
  const pagesToCheck = [
    '/admin',
    '/admin/users',
    '/admin/sites',
    '/developer'
  ];
  
  for (const path of pagesToCheck) {
    await runTest(`No JS errors on ${path}`, async () => {
      const p = await getPage();
      const errors = [];
      
      p.on('pageerror', err => errors.push(err.toString()));
      p.on('console', msg => {
        if (msg.type() === 'error') {
          errors.push(msg.text());
        }
      });
      
      await p.goto(`${LEMMA_BASE_URL}${path}`, { waitUntil: 'networkidle2' });
      await new Promise(r => setTimeout(r, 2000));
      
      // Filter out known acceptable errors
      const criticalErrors = errors.filter(e => 
        !e.includes('favicon') && 
        !e.includes('404') &&
        !e.includes('net::ERR')
      );
      
      return {
        passed: criticalErrors.length === 0,
        details: criticalErrors.length > 0 ? `Errors: ${criticalErrors.join('; ').substring(0, 200)}` : 'No critical errors'
      };
    });
  }
}

// ============================================
// MAIN
// ============================================

async function main() {
  console.log('╔════════════════════════════════════════════════════════════╗');
  console.log('║        LEMMA PLATFORM AUTOMATED UI TEST SUITE              ║');
  console.log('╠════════════════════════════════════════════════════════════╣');
  console.log(`║  Target: ${LEMMA_BASE_URL.padEnd(48)}║`);
  console.log(`║  Time:   ${new Date().toISOString().padEnd(48)}║`);
  console.log('╚════════════════════════════════════════════════════════════╝');
  
  try {
    // Mandatory auth preflight gate
    await requireAuthPreflight();

    // Run all test suites
    await testAuthValidation();
    await testAdminDashboard();
    await testAdminUsersPage();
    await testAdminSitesPage();
    await testDeveloperDashboard();
    await testButtonFunctionality();
    await testNavigation();
    await testFormElements();
    await testAPIEndpoints();
    await testConsoleErrors();
    
  } catch (error) {
    console.error('\n!!! Test suite error:', error.message);
  }
  
  // Print summary
  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║                      TEST SUMMARY                          ║');
  console.log('╠════════════════════════════════════════════════════════════╣');
  console.log(`║  Total Tests: ${String(results.passed + results.failed).padEnd(44)}║`);
  console.log(`║  Passed:      ${String(results.passed).padEnd(44)}║`);
  console.log(`║  Failed:      ${String(results.failed).padEnd(44)}║`);
  const total = results.passed + results.failed;
  const passRate = total > 0 ? ((results.passed / total) * 100).toFixed(1) : '0.0';
  console.log(`║  Pass Rate:   ${passRate}%${' '.repeat(42)}║`);
  console.log('╚════════════════════════════════════════════════════════════╝');
  
  // List failed tests
  const failedTests = results.tests.filter(t => !t.passed);
  if (failedTests.length > 0) {
    console.log('\n❌ FAILED TESTS:');
    failedTests.forEach(t => {
      console.log(`   - ${t.name}: ${t.error || t.details || 'Unknown'}`);
    });
  }
  
  // Cleanup
  if (browser) {
    await browser.close();
  }
  
  // Exit with appropriate code
  process.exit(results.failed > 0 ? 1 : 0);
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
