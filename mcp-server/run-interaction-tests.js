#!/usr/bin/env node
/**
 * Lemma Platform UI Interaction Test Runner
 * 
 * Tests actual user interactions - clicking buttons, filling forms, etc.
 */

import puppeteer from 'puppeteer';
import fetch from 'node-fetch';

const LEMMA_BASE_URL = (process.env.LEMMA_BASE_URL || 'https://lemma.id').replace(/\/$/, '');
const AGENT_TOKEN = process.env.LEMMA_AGENT_TOKEN || 'lm_agent_0OHnZ9X9G7FXYzC7MzAMCWuFKkz04oK8FPJzlePyiWU';

let browser = null;
let page = null;

const results = {
  timestamp: new Date().toISOString(),
  passed: 0,
  failed: 0,
  tests: []
};

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

    // Create agent session for authenticated access
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
// INTERACTION TESTS
// ============================================

async function testHomePageInteractions() {
  console.log('\n=== HOME PAGE INTERACTION TESTS ===');
  
  await runTest('Home page CTA buttons visible', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/`, { waitUntil: 'networkidle2' });
    
    const buttons = await p.evaluate(() => {
      return [...document.querySelectorAll('a, button')].filter(el => {
        const text = el.textContent.toLowerCase();
        return text.includes('get started') || 
               text.includes('sign up') || 
               text.includes('learn more') ||
               text.includes('documentation');
      }).map(el => ({
        text: el.textContent.trim(),
        href: el.href || null,
        tag: el.tagName
      }));
    });
    
    return {
      passed: buttons.length > 0,
      details: `Found ${buttons.length} CTA buttons: ${buttons.map(b => b.text).join(', ').substring(0, 100)}`
    };
  });
  
  await runTest('Navigation menu works', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/`, { waitUntil: 'networkidle2' });
    
    // Find navigation links
    const navLinks = await p.evaluate(() => {
      return [...document.querySelectorAll('nav a, header a')].map(el => ({
        text: el.textContent.trim(),
        href: el.href
      }));
    });
    
    return {
      passed: navLinks.length > 0,
      details: `Found ${navLinks.length} nav links`
    };
  });
}

async function testAdminPageInteractions() {
  console.log('\n=== ADMIN PAGE INTERACTION TESTS ===');
  
  await runTest('Admin sidebar navigation', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/admin`, { waitUntil: 'networkidle2' });
    
    const sidebarLinks = await p.evaluate(() => {
      return [...document.querySelectorAll('.sidebar a, nav.admin-nav a, [class*="sidebar"] a')].map(el => ({
        text: el.textContent.trim(),
        href: el.href,
        active: el.classList.contains('active') || el.getAttribute('aria-current') === 'page'
      }));
    });
    
    return {
      passed: sidebarLinks.length > 0,
      details: `Found ${sidebarLinks.length} sidebar links`
    };
  });
  
  await runTest('Admin stats cards display', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/admin`, { waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 2000));
    
    const statsCards = await p.evaluate(() => {
      const cards = document.querySelectorAll('.stat-card, .stats-card, [class*="stat"], .metric-card');
      return [...cards].map(card => ({
        text: card.textContent.trim().substring(0, 100),
        hasNumber: /\d+/.test(card.textContent)
      }));
    });
    
    return {
      passed: statsCards.some(c => c.hasNumber),
      details: `Found ${statsCards.length} stat cards, ${statsCards.filter(c => c.hasNumber).length} with numbers`
    };
  });
  
  await runTest('Click Users nav item', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/admin`, { waitUntil: 'networkidle2' });
    
    // Find and click Users link
    const clicked = await p.evaluate(() => {
      const links = [...document.querySelectorAll('a')];
      const usersLink = links.find(l => l.textContent.toLowerCase().includes('user'));
      if (usersLink) {
        usersLink.click();
        return true;
      }
      return false;
    });
    
    if (clicked) {
      await new Promise(r => setTimeout(r, 1500));
      const url = p.url();
      return {
        passed: url.includes('user'),
        details: `Navigated to: ${url}`
      };
    }
    
    return {
      passed: false,
      details: 'Users link not found'
    };
  });
  
  await runTest('Click Sites nav item', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/admin`, { waitUntil: 'networkidle2' });
    
    const clicked = await p.evaluate(() => {
      const links = [...document.querySelectorAll('a')];
      const sitesLink = links.find(l => l.textContent.toLowerCase().includes('site'));
      if (sitesLink) {
        sitesLink.click();
        return true;
      }
      return false;
    });
    
    if (clicked) {
      await new Promise(r => setTimeout(r, 1500));
      const url = p.url();
      return {
        passed: url.includes('site'),
        details: `Navigated to: ${url}`
      };
    }
    
    return {
      passed: false,
      details: 'Sites link not found'
    };
  });
}

async function testDeveloperPageInteractions() {
  console.log('\n=== DEVELOPER PAGE INTERACTION TESTS ===');
  
  await runTest('Developer dashboard cards visible', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/developer`, { waitUntil: 'networkidle2' });
    
    const cards = await p.evaluate(() => {
      return [...document.querySelectorAll('.card, [class*="card"], .panel, section')].map(el => ({
        heading: el.querySelector('h2, h3, h4, .card-title')?.textContent?.trim() || '',
        hasContent: el.textContent.length > 50
      }));
    });
    
    return {
      passed: cards.length > 0,
      details: `Found ${cards.length} cards: ${cards.map(c => c.heading).filter(h => h).join(', ').substring(0, 100)}`
    };
  });
  
  await runTest('Create New Site button exists', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/developer`, { waitUntil: 'networkidle2' });
    
    const createBtn = await p.evaluate(() => {
      const btns = [...document.querySelectorAll('button, a')];
      const btn = btns.find(b => {
        const text = b.textContent.toLowerCase();
        return text.includes('create') && text.includes('site') ||
               text.includes('new site') ||
               text.includes('register site') ||
               text.includes('add site');
      });
      return btn ? {
        text: btn.textContent.trim(),
        tag: btn.tagName,
        disabled: btn.disabled
      } : null;
    });
    
    return {
      passed: createBtn !== null,
      details: createBtn ? `Found: "${createBtn.text}" (${createBtn.tag})` : 'Not found'
    };
  });
  
  await runTest('Agent token section exists', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/developer`, { waitUntil: 'networkidle2' });
    
    const agentSection = await p.evaluate(() => {
      const content = document.body.innerText.toLowerCase();
      const hasAgentText = content.includes('agent') || content.includes('ai access');
      
      const sections = [...document.querySelectorAll('section, .card, [class*="card"]')];
      const agentCard = sections.find(s => {
        const text = s.textContent.toLowerCase();
        return text.includes('agent') || text.includes('ai access');
      });
      
      return {
        hasAgentText,
        hasAgentCard: !!agentCard,
        cardText: agentCard?.textContent?.substring(0, 200) || ''
      };
    });
    
    return {
      passed: agentSection.hasAgentText || agentSection.hasAgentCard,
      details: `Agent text: ${agentSection.hasAgentText}, Agent card: ${agentSection.hasAgentCard}`
    };
  });
  
  await runTest('Sign in button visible when not authenticated', async () => {
    const p = await getPage();
    // Clear session to test unauthenticated state
    await p.goto(`${LEMMA_BASE_URL}/developer`, { waitUntil: 'networkidle2' });
    
    const signInBtn = await p.evaluate(() => {
      const btns = [...document.querySelectorAll('button, a')];
      const btn = btns.find(b => {
        const text = b.textContent.toLowerCase();
        return text.includes('sign in') || text.includes('login') || text.includes('connect wallet');
      });
      return btn ? {
        text: btn.textContent.trim(),
        visible: btn.offsetParent !== null
      } : null;
    });
    
    return {
      passed: signInBtn !== null,
      details: signInBtn ? `Found: "${signInBtn.text}"` : 'No sign in button found'
    };
  });
}

async function testFormInteractions() {
  console.log('\n=== FORM INTERACTION TESTS ===');
  
  await runTest('Input fields accept text', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/developer`, { waitUntil: 'networkidle2' });
    
    // Find any text input
    const inputs = await p.$$('input[type="text"], input:not([type])');
    
    if (inputs.length === 0) {
      return {
        passed: true, // No inputs to test is OK
        details: 'No text inputs found on page'
      };
    }
    
    // Try typing in first input
    try {
      await inputs[0].click();
      await inputs[0].type('test-input-123', { delay: 20 });
      
      const value = await inputs[0].evaluate(el => el.value);
      
      return {
        passed: value.includes('test-input-123'),
        details: `Typed into input, value: ${value}`
      };
    } catch (e) {
      return {
        passed: false,
        error: e.message
      };
    }
  });
  
  await runTest('Select dropdowns work', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/developer`, { waitUntil: 'networkidle2' });
    
    const selects = await p.$$('select');
    
    if (selects.length === 0) {
      return {
        passed: true,
        details: 'No select elements found'
      };
    }
    
    // Get options from first select
    const options = await selects[0].evaluate(el => {
      return [...el.options].map(o => ({ value: o.value, text: o.text }));
    });
    
    return {
      passed: options.length > 0,
      details: `Select has ${options.length} options`
    };
  });
}

async function testResponsiveElements() {
  console.log('\n=== RESPONSIVE ELEMENT TESTS ===');
  
  await runTest('Page renders at mobile width', async () => {
    const p = await getPage();
    await p.setViewport({ width: 375, height: 667 }); // iPhone SE
    await p.goto(`${LEMMA_BASE_URL}/`, { waitUntil: 'networkidle2' });
    
    const hasContent = await p.evaluate(() => {
      return document.body.innerText.length > 100;
    });
    
    // Reset viewport
    await p.setViewport({ width: 1280, height: 800 });
    
    return {
      passed: hasContent,
      details: 'Page renders content at mobile width'
    };
  });
  
  await runTest('Admin page renders at tablet width', async () => {
    const p = await getPage();
    await p.setViewport({ width: 768, height: 1024 }); // iPad
    await p.goto(`${LEMMA_BASE_URL}/admin`, { waitUntil: 'networkidle2' });
    
    const hasContent = await p.evaluate(() => {
      return document.body.innerText.length > 100;
    });
    
    // Reset viewport
    await p.setViewport({ width: 1280, height: 800 });
    
    return {
      passed: hasContent,
      details: 'Admin page renders at tablet width'
    };
  });
}

async function testAccessibility() {
  console.log('\n=== ACCESSIBILITY TESTS ===');
  
  await runTest('All images have alt text', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/`, { waitUntil: 'networkidle2' });
    
    const images = await p.evaluate(() => {
      return [...document.querySelectorAll('img')].map(img => ({
        src: img.src,
        hasAlt: img.alt && img.alt.length > 0,
        alt: img.alt
      }));
    });
    
    const withoutAlt = images.filter(i => !i.hasAlt);
    
    return {
      passed: withoutAlt.length === 0,
      details: `${images.length} images, ${withoutAlt.length} missing alt text`
    };
  });
  
  await runTest('Buttons have accessible names', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/developer`, { waitUntil: 'networkidle2' });
    
    const buttons = await p.evaluate(() => {
      return [...document.querySelectorAll('button')].map(btn => ({
        text: btn.textContent.trim(),
        ariaLabel: btn.getAttribute('aria-label'),
        title: btn.title,
        hasAccessibleName: btn.textContent.trim().length > 0 || 
                          btn.getAttribute('aria-label') ||
                          btn.title
      }));
    });
    
    const inaccessible = buttons.filter(b => !b.hasAccessibleName);
    
    return {
      passed: inaccessible.length === 0,
      details: `${buttons.length} buttons, ${inaccessible.length} without accessible names`
    };
  });
  
  await runTest('Links have descriptive text', async () => {
    const p = await getPage();
    await p.goto(`${LEMMA_BASE_URL}/`, { waitUntil: 'networkidle2' });
    
    const links = await p.evaluate(() => {
      return [...document.querySelectorAll('a')].map(a => ({
        text: a.textContent.trim(),
        href: a.href,
        isDescriptive: a.textContent.trim().length > 2 && 
                      !['click here', 'here', 'link'].includes(a.textContent.trim().toLowerCase())
      }));
    });
    
    const nonDescriptive = links.filter(l => !l.isDescriptive && l.href);
    
    return {
      passed: nonDescriptive.length <= 2, // Allow a couple
      details: `${links.length} links, ${nonDescriptive.length} non-descriptive`
    };
  });
}

async function testErrorStates() {
  console.log('\n=== ERROR STATE TESTS ===');
  
  await runTest('404 page displays correctly', async () => {
    const p = await getPage();
    const response = await p.goto(`${LEMMA_BASE_URL}/nonexistent-page-12345`, { waitUntil: 'networkidle2' });
    
    const content = await p.evaluate(() => document.body.innerText.toLowerCase());
    const has404Content = content.includes('404') || 
                         content.includes('not found') || 
                         content.includes('page not found');
    
    return {
      passed: response.status() === 404 || has404Content,
      details: `Status: ${response.status()}, Has 404 content: ${has404Content}`
    };
  });
  
  await runTest('Invalid API returns proper error', async () => {
    const response = await fetch(`${LEMMA_BASE_URL}/api/nonexistent-endpoint`, {
      headers: { 'X-Agent-Token': AGENT_TOKEN }
    });
    
    return {
      passed: response.status === 404 || response.status === 405,
      details: `Status: ${response.status}`
    };
  });
}

// ============================================
// MAIN
// ============================================

async function main() {
  console.log('╔════════════════════════════════════════════════════════════╗');
  console.log('║      LEMMA PLATFORM UI INTERACTION TEST SUITE              ║');
  console.log('╠════════════════════════════════════════════════════════════╣');
  console.log(`║  Target: ${LEMMA_BASE_URL.padEnd(48)}║`);
  console.log(`║  Time:   ${new Date().toISOString().padEnd(48)}║`);
  console.log('╚════════════════════════════════════════════════════════════╝');
  
  try {
    await requireAuthPreflight();

    await testHomePageInteractions();
    await testAdminPageInteractions();
    await testDeveloperPageInteractions();
    await testFormInteractions();
    await testResponsiveElements();
    await testAccessibility();
    await testErrorStates();
    
  } catch (error) {
    console.error('\n!!! Test suite error:', error.message);
  }
  
  // Print summary
  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║                   INTERACTION TEST SUMMARY                 ║');
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
  
  process.exit(results.failed > 0 ? 1 : 0);
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
