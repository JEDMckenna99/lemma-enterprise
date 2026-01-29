#!/usr/bin/env node
/**
 * Lemma.id MCP Server
 * 
 * Enables AI agents to interact with the Lemma platform using agent delegation tokens.
 * Provides tools for:
 * - Viewing page content and screenshots
 * - Calling API endpoints
 * - Checking platform health
 * - Debugging UI issues
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ListResourcesRequestSchema,
  ReadResourceRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import fetch from 'node-fetch';
import puppeteer from 'puppeteer';

// Configuration
const LEMMA_BASE_URL = process.env.LEMMA_URL || 'https://lemma.id';
const AGENT_TOKEN = process.env.LEMMA_AGENT_TOKEN || '';

let browser = null;
let page = null;

// Initialize browser
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
    if (AGENT_TOKEN) {
      await page.goto(`${LEMMA_BASE_URL}/api/agent/session?token=${AGENT_TOKEN}`);
      console.error('Agent session created');
    }
  }
  return page;
}

// API helper
async function callApi(endpoint, options = {}) {
  const url = `${LEMMA_BASE_URL}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...(AGENT_TOKEN ? { 'X-Agent-Token': AGENT_TOKEN } : {}),
    ...options.headers
  };
  
  const response = await fetch(url, {
    ...options,
    headers
  });
  
  return {
    status: response.status,
    ok: response.ok,
    data: await response.json().catch(() => null)
  };
}

// Create MCP Server
const server = new Server(
  {
    name: 'lemma-mcp-server',
    version: '1.0.0',
  },
  {
    capabilities: {
      tools: {},
      resources: {},
    },
  }
);

// Define available tools
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      // === OBSERVATION TOOLS ===
      {
        name: 'lemma_view_page',
        description: 'Navigate to a Lemma.id page and get its content. Returns page title, text content, and any console errors.',
        inputSchema: {
          type: 'object',
          properties: {
            path: {
              type: 'string',
              description: 'Page path to navigate to (e.g., "/admin", "/developer", "/admin/debug")'
            }
          },
          required: ['path']
        }
      },
      {
        name: 'lemma_screenshot',
        description: 'Take a screenshot of a Lemma.id page. Returns base64 encoded image.',
        inputSchema: {
          type: 'object',
          properties: {
            path: {
              type: 'string',
              description: 'Page path to screenshot'
            }
          },
          required: ['path']
        }
      },
      {
        name: 'lemma_api_call',
        description: 'Call a Lemma.id API endpoint with agent token authentication.',
        inputSchema: {
          type: 'object',
          properties: {
            endpoint: {
              type: 'string',
              description: 'API endpoint (e.g., "/api/admin/sites", "/api/admin/customers")'
            },
            method: {
              type: 'string',
              description: 'HTTP method (GET, POST, etc.)',
              default: 'GET'
            },
            body: {
              type: 'object',
              description: 'Request body for POST/PUT requests'
            }
          },
          required: ['endpoint']
        }
      },
      {
        name: 'lemma_debug_dashboard',
        description: 'Get the full debug dashboard data - all API endpoints tested at once.',
        inputSchema: {
          type: 'object',
          properties: {}
        }
      },
      {
        name: 'lemma_check_auth',
        description: 'Verify the agent token is valid and check its permissions.',
        inputSchema: {
          type: 'object',
          properties: {}
        }
      },
      {
        name: 'lemma_get_console_logs',
        description: 'Get JavaScript console logs from the current page (errors, warnings, logs).',
        inputSchema: {
          type: 'object',
          properties: {
            path: {
              type: 'string',
              description: 'Page path to check console logs'
            }
          },
          required: ['path']
        }
      },
      
      // === INTERACTION TOOLS ===
      {
        name: 'lemma_click',
        description: 'Click on an element on the current page. Use CSS selector or text content to identify the element.',
        inputSchema: {
          type: 'object',
          properties: {
            selector: {
              type: 'string',
              description: 'CSS selector for the element (e.g., "#submit-btn", ".dev-btn-primary", "button[data-action=generate-token]")'
            },
            text: {
              type: 'string',
              description: 'Alternative: find element by its text content (e.g., "Generate Token", "Submit")'
            },
            waitAfter: {
              type: 'number',
              description: 'Milliseconds to wait after click for page to update (default: 1000)'
            }
          }
        }
      },
      {
        name: 'lemma_type',
        description: 'Type text into an input field.',
        inputSchema: {
          type: 'object',
          properties: {
            selector: {
              type: 'string',
              description: 'CSS selector for the input field'
            },
            text: {
              type: 'string',
              description: 'Text to type into the field'
            },
            clear: {
              type: 'boolean',
              description: 'Clear existing content before typing (default: true)'
            }
          },
          required: ['selector', 'text']
        }
      },
      {
        name: 'lemma_select',
        description: 'Select an option from a dropdown/select element.',
        inputSchema: {
          type: 'object',
          properties: {
            selector: {
              type: 'string',
              description: 'CSS selector for the select element'
            },
            value: {
              type: 'string',
              description: 'Value to select'
            }
          },
          required: ['selector', 'value']
        }
      },
      {
        name: 'lemma_checkbox',
        description: 'Check or uncheck a checkbox.',
        inputSchema: {
          type: 'object',
          properties: {
            selector: {
              type: 'string',
              description: 'CSS selector for the checkbox'
            },
            checked: {
              type: 'boolean',
              description: 'Whether to check (true) or uncheck (false)'
            }
          },
          required: ['selector', 'checked']
        }
      },
      {
        name: 'lemma_get_elements',
        description: 'Get a list of elements matching a selector, with their text and attributes. Useful for understanding page structure.',
        inputSchema: {
          type: 'object',
          properties: {
            selector: {
              type: 'string',
              description: 'CSS selector (e.g., "button", ".admin-btn", "input")'
            },
            path: {
              type: 'string',
              description: 'Optional: navigate to this path first'
            }
          },
          required: ['selector']
        }
      },
      {
        name: 'lemma_wait_for',
        description: 'Wait for an element to appear or a condition to be met.',
        inputSchema: {
          type: 'object',
          properties: {
            selector: {
              type: 'string',
              description: 'CSS selector to wait for'
            },
            timeout: {
              type: 'number',
              description: 'Maximum time to wait in milliseconds (default: 10000)'
            },
            visible: {
              type: 'boolean',
              description: 'Wait for element to be visible (default: true)'
            }
          },
          required: ['selector']
        }
      },
      {
        name: 'lemma_fill_form',
        description: 'Fill out a form with multiple fields at once.',
        inputSchema: {
          type: 'object',
          properties: {
            fields: {
              type: 'object',
              description: 'Object mapping selectors to values (e.g., {"#email": "test@example.com", "#name": "Test User"})'
            },
            submit: {
              type: 'boolean',
              description: 'Whether to submit the form after filling (default: false)'
            },
            submitSelector: {
              type: 'string',
              description: 'Selector for submit button (default: "button[type=submit]")'
            }
          },
          required: ['fields']
        }
      },
      
      // === WORKFLOW TESTING TOOLS ===
      {
        name: 'lemma_test_site_registration',
        description: 'Test the complete site registration flow for developers.',
        inputSchema: {
          type: 'object',
          properties: {
            siteDomain: {
              type: 'string',
              description: 'Domain to register (e.g., "test-site.example.com")'
            },
            companyName: {
              type: 'string',
              description: 'Company name'
            }
          },
          required: ['siteDomain']
        }
      },
      {
        name: 'lemma_test_api_key_generation',
        description: 'Test generating an API key for a site.',
        inputSchema: {
          type: 'object',
          properties: {
            siteId: {
              type: 'string',
              description: 'Site ID to generate key for'
            }
          },
          required: ['siteId']
        }
      },
      {
        name: 'lemma_test_agent_token_flow',
        description: 'Test the agent token generation flow from the developer dashboard.',
        inputSchema: {
          type: 'object',
          properties: {
            scope: {
              type: 'array',
              description: 'Scopes to request (e.g., ["read", "write", "admin"])'
            },
            ttlHours: {
              type: 'number',
              description: 'Token lifetime in hours (1, 4, 8, or 24)'
            }
          }
        }
      },
      {
        name: 'lemma_run_ui_test',
        description: 'Run a predefined UI test suite.',
        inputSchema: {
          type: 'object',
          properties: {
            suite: {
              type: 'string',
              description: 'Test suite to run: "admin_dashboard", "developer_dashboard", "site_management", "agent_tokens", "all"'
            }
          },
          required: ['suite']
        }
      }
    ]
  };
});

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  
  try {
    switch (name) {
      case 'lemma_view_page': {
        const p = await getPage();
        const url = `${LEMMA_BASE_URL}${args.path}`;
        await p.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
        
        const title = await p.title();
        const content = await p.evaluate(() => {
          // Get main content, excluding scripts and styles
          const main = document.querySelector('main') || document.body;
          return main.innerText.substring(0, 5000); // Limit content length
        });
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              url,
              title,
              content,
              timestamp: new Date().toISOString()
            }, null, 2)
          }]
        };
      }
      
      case 'lemma_screenshot': {
        const p = await getPage();
        const url = `${LEMMA_BASE_URL}${args.path}`;
        await p.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
        
        const screenshot = await p.screenshot({ encoding: 'base64', fullPage: false });
        
        return {
          content: [{
            type: 'image',
            data: screenshot,
            mimeType: 'image/png'
          }]
        };
      }
      
      case 'lemma_api_call': {
        const result = await callApi(args.endpoint, {
          method: args.method || 'GET',
          body: args.body ? JSON.stringify(args.body) : undefined
        });
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              endpoint: args.endpoint,
              status: result.status,
              ok: result.ok,
              data: result.data
            }, null, 2)
          }]
        };
      }
      
      case 'lemma_debug_dashboard': {
        const endpoints = [
          '/api/admin/platform-stats',
          '/api/admin/sites',
          '/api/admin/customers',
          '/api/admin/user-stats',
          '/api/admin/recent-activity',
          '/api/health/detailed',
          '/api/developer/stats',
          '/api/developer/sites'
        ];
        
        const results = {};
        for (const endpoint of endpoints) {
          const result = await callApi(endpoint);
          results[endpoint] = {
            status: result.status,
            ok: result.ok,
            data: result.data
          };
        }
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify(results, null, 2)
          }]
        };
      }
      
      case 'lemma_check_auth': {
        const result = await callApi('/api/agent/validate', { method: 'POST' });
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              token_configured: !!AGENT_TOKEN,
              token_preview: AGENT_TOKEN ? AGENT_TOKEN.substring(0, 20) + '...' : 'not set',
              validation: result.data
            }, null, 2)
          }]
        };
      }
      
      case 'lemma_get_console_logs': {
        const p = await getPage();
        const logs = [];
        
        // Capture console messages
        p.on('console', msg => {
          logs.push({
            type: msg.type(),
            text: msg.text()
          });
        });
        
        p.on('pageerror', err => {
          logs.push({
            type: 'error',
            text: err.toString()
          });
        });
        
        const url = `${LEMMA_BASE_URL}${args.path}`;
        await p.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
        
        // Wait a moment for any async console logs
        await new Promise(r => setTimeout(r, 2000));
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              url,
              logs: logs.slice(-50) // Last 50 logs
            }, null, 2)
          }]
        };
      }
      
      // === INTERACTION TOOLS ===
      case 'lemma_click': {
        const p = await getPage();
        const { selector, text, waitAfter = 1000 } = args;
        
        let element;
        if (selector) {
          element = await p.$(selector);
        } else if (text) {
          // Find element by text content
          element = await p.evaluateHandle((searchText) => {
            const elements = [...document.querySelectorAll('button, a, [role="button"], [data-action], .btn, .dev-btn')];
            return elements.find(el => el.textContent.trim().includes(searchText));
          }, text);
        }
        
        if (!element || (element.asElement && !element.asElement())) {
          return {
            content: [{
              type: 'text',
              text: JSON.stringify({
                success: false,
                error: `Element not found: ${selector || text}`,
                currentUrl: p.url()
              })
            }],
            isError: true
          };
        }
        
        await element.click();
        await new Promise(r => setTimeout(r, waitAfter));
        
        // Get updated page state
        const newContent = await p.evaluate(() => {
          const main = document.querySelector('main') || document.body;
          return main.innerText.substring(0, 2000);
        });
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              success: true,
              clicked: selector || text,
              pageUrl: p.url(),
              pageContent: newContent
            }, null, 2)
          }]
        };
      }
      
      case 'lemma_type': {
        const p = await getPage();
        const { selector, text, clear = true } = args;
        
        if (clear) {
          await p.click(selector, { clickCount: 3 }); // Select all
        }
        await p.type(selector, text, { delay: 20 });
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              success: true,
              selector,
              typedText: text
            })
          }]
        };
      }
      
      case 'lemma_select': {
        const p = await getPage();
        const { selector, value } = args;
        
        await p.select(selector, value);
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              success: true,
              selector,
              selectedValue: value
            })
          }]
        };
      }
      
      case 'lemma_checkbox': {
        const p = await getPage();
        const { selector, checked } = args;
        
        const currentState = await p.$eval(selector, el => el.checked);
        
        if (currentState !== checked) {
          await p.click(selector);
        }
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              success: true,
              selector,
              previousState: currentState,
              newState: checked
            })
          }]
        };
      }
      
      case 'lemma_get_elements': {
        const p = await getPage();
        const { selector, path } = args;
        
        if (path) {
          await p.goto(`${LEMMA_BASE_URL}${path}`, { waitUntil: 'networkidle2' });
        }
        
        const elements = await p.evaluate((sel) => {
          return [...document.querySelectorAll(sel)].map(el => ({
            tag: el.tagName.toLowerCase(),
            text: el.textContent.trim().substring(0, 100),
            id: el.id || null,
            className: el.className || null,
            dataAction: el.dataset?.action || null,
            type: el.type || null,
            value: el.value || null,
            href: el.href || null,
            disabled: el.disabled || false,
            visible: el.offsetParent !== null,
            boundingBox: el.getBoundingClientRect ? {
              x: el.getBoundingClientRect().x,
              y: el.getBoundingClientRect().y,
              width: el.getBoundingClientRect().width,
              height: el.getBoundingClientRect().height
            } : null
          }));
        }, selector);
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              selector,
              count: elements.length,
              elements
            }, null, 2)
          }]
        };
      }
      
      case 'lemma_wait_for': {
        const p = await getPage();
        const { selector, timeout = 10000, visible = true } = args;
        
        try {
          await p.waitForSelector(selector, { timeout, visible });
          
          return {
            content: [{
              type: 'text',
              text: JSON.stringify({
                success: true,
                selector,
                found: true
              })
            }]
          };
        } catch (error) {
          return {
            content: [{
              type: 'text',
              text: JSON.stringify({
                success: false,
                selector,
                error: `Element not found within ${timeout}ms`
              })
            }],
            isError: true
          };
        }
      }
      
      case 'lemma_fill_form': {
        const p = await getPage();
        const { fields, submit = false, submitSelector = 'button[type="submit"]' } = args;
        
        const filled = [];
        for (const [selector, value] of Object.entries(fields)) {
          try {
            const tagName = await p.$eval(selector, el => el.tagName.toLowerCase());
            
            if (tagName === 'select') {
              await p.select(selector, value);
            } else if (tagName === 'input') {
              const inputType = await p.$eval(selector, el => el.type);
              if (inputType === 'checkbox') {
                const currentState = await p.$eval(selector, el => el.checked);
                if (currentState !== value) {
                  await p.click(selector);
                }
              } else {
                await p.click(selector, { clickCount: 3 });
                await p.type(selector, String(value), { delay: 20 });
              }
            } else {
              await p.click(selector, { clickCount: 3 });
              await p.type(selector, String(value), { delay: 20 });
            }
            filled.push({ selector, value, success: true });
          } catch (error) {
            filled.push({ selector, value, success: false, error: error.message });
          }
        }
        
        let submitResult = null;
        if (submit) {
          try {
            await p.click(submitSelector);
            await new Promise(r => setTimeout(r, 1500));
            submitResult = { success: true, url: p.url() };
          } catch (error) {
            submitResult = { success: false, error: error.message };
          }
        }
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              filledFields: filled,
              submitResult,
              pageUrl: p.url()
            }, null, 2)
          }]
        };
      }
      
      // === WORKFLOW TESTING TOOLS ===
      case 'lemma_test_site_registration': {
        const p = await getPage();
        const { siteDomain, companyName = 'Test Company' } = args;
        
        const steps = [];
        
        try {
          // Navigate to developer page
          await p.goto(`${LEMMA_BASE_URL}/developer`, { waitUntil: 'networkidle2' });
          steps.push({ step: 'navigate_developer', success: true });
          
          // Look for register site button and click
          const registerBtn = await p.$('[data-action="register-site"], #register-site-btn, .register-site-btn, button:has-text("Register")');
          if (registerBtn) {
            await registerBtn.click();
            steps.push({ step: 'click_register', success: true });
            await new Promise(r => setTimeout(r, 500));
          } else {
            steps.push({ step: 'click_register', success: false, error: 'Register button not found' });
          }
          
          // Fill in domain
          try {
            await p.type('#site-domain, [name="domain"], input[placeholder*="domain"]', siteDomain, { delay: 20 });
            steps.push({ step: 'enter_domain', success: true, value: siteDomain });
          } catch (e) {
            steps.push({ step: 'enter_domain', success: false, error: e.message });
          }
          
          // Submit form
          try {
            await p.click('button[type="submit"], [data-action="submit-registration"], .submit-btn');
            steps.push({ step: 'submit_form', success: true });
            await new Promise(r => setTimeout(r, 2000));
          } catch (e) {
            steps.push({ step: 'submit_form', success: false, error: e.message });
          }
          
          // Check result
          const resultContent = await p.evaluate(() => document.body.innerText);
          const hasSuccess = resultContent.toLowerCase().includes('success') || 
                           resultContent.toLowerCase().includes('registered') ||
                           resultContent.toLowerCase().includes('created');
          
          steps.push({ 
            step: 'verify_result', 
            success: hasSuccess,
            pageContent: resultContent.substring(0, 500)
          });
          
        } catch (error) {
          steps.push({ step: 'error', success: false, error: error.message });
        }
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              workflow: 'site_registration',
              siteDomain,
              steps
            }, null, 2)
          }]
        };
      }
      
      case 'lemma_test_api_key_generation': {
        const p = await getPage();
        const { siteId } = args;
        
        const steps = [];
        
        try {
          await p.goto(`${LEMMA_BASE_URL}/developer/sites/${siteId}`, { waitUntil: 'networkidle2' });
          steps.push({ step: 'navigate_site', success: true });
          
          // Find and click generate API key button
          await p.click('[data-action="generate-api-key"], #generate-api-key, .generate-key-btn');
          steps.push({ step: 'click_generate', success: true });
          await new Promise(r => setTimeout(r, 1500));
          
          // Check for API key in response
          const pageContent = await p.evaluate(() => document.body.innerText);
          const hasApiKey = pageContent.includes('api_') || 
                          pageContent.toLowerCase().includes('api key') ||
                          pageContent.toLowerCase().includes('key generated');
          
          steps.push({ 
            step: 'verify_key', 
            success: hasApiKey,
            pageContent: pageContent.substring(0, 500)
          });
          
        } catch (error) {
          steps.push({ step: 'error', success: false, error: error.message });
        }
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              workflow: 'api_key_generation',
              siteId,
              steps
            }, null, 2)
          }]
        };
      }
      
      case 'lemma_test_agent_token_flow': {
        const p = await getPage();
        const { scope = ['read', 'write'], ttlHours = 8 } = args;
        
        const steps = [];
        
        try {
          await p.goto(`${LEMMA_BASE_URL}/developer`, { waitUntil: 'networkidle2' });
          steps.push({ step: 'navigate_developer', success: true });
          
          // Find agent token section
          try {
            await p.waitForSelector('#agent-token-section, .agent-access-card, [data-section="agent-tokens"]', { timeout: 5000 });
            steps.push({ step: 'find_agent_section', success: true });
          } catch (e) {
            steps.push({ step: 'find_agent_section', success: false, error: 'Agent section not found' });
          }
          
          // Select TTL
          try {
            await p.select('#agent-ttl, [name="ttl"]', String(ttlHours));
            steps.push({ step: 'select_ttl', success: true, value: ttlHours });
          } catch (e) {
            steps.push({ step: 'select_ttl', success: false, error: 'TTL selector not found' });
          }
          
          // Click generate token
          await p.click('[data-action="generate-token"], #generate-agent-token, .generate-token-btn');
          steps.push({ step: 'click_generate', success: true });
          await new Promise(r => setTimeout(r, 2000));
          
          // Check for token display
          const pageContent = await p.evaluate(() => document.body.innerText);
          const hasToken = pageContent.includes('agent_') || 
                          pageContent.toLowerCase().includes('token generated');
          
          steps.push({
            step: 'verify_token',
            success: hasToken,
            pageContent: pageContent.substring(0, 500)
          });
          
        } catch (error) {
          steps.push({ step: 'error', success: false, error: error.message });
        }
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              workflow: 'agent_token_flow',
              scope,
              ttlHours,
              steps
            }, null, 2)
          }]
        };
      }
      
      case 'lemma_run_ui_test': {
        const { suite } = args;
        
        const testResults = {
          suite,
          timestamp: new Date().toISOString(),
          tests: []
        };
        
        const runTest = async (name, testFn) => {
          try {
            const result = await testFn();
            testResults.tests.push({ name, passed: result.passed, details: result.details });
          } catch (error) {
            testResults.tests.push({ name, passed: false, error: error.message });
          }
        };
        
        if (suite === 'admin_dashboard' || suite === 'all') {
          await runTest('admin_page_loads', async () => {
            const p = await getPage();
            await p.goto(`${LEMMA_BASE_URL}/admin`, { waitUntil: 'networkidle2' });
            const content = await p.evaluate(() => document.body.innerText);
            return { passed: content.includes('Admin') || content.includes('Dashboard'), details: 'Admin page loaded' };
          });
          
          await runTest('admin_stats_display', async () => {
            const p = await getPage();
            await p.goto(`${LEMMA_BASE_URL}/admin`, { waitUntil: 'networkidle2' });
            await new Promise(r => setTimeout(r, 1000));
            const statsVisible = await p.evaluate(() => {
              const stats = document.querySelectorAll('.stat-card, .stats-widget, [data-stat], .metric-value');
              return stats.length > 0;
            });
            return { passed: statsVisible, details: `Found stat elements: ${statsVisible}` };
          });
          
          await runTest('admin_users_page', async () => {
            const p = await getPage();
            await p.goto(`${LEMMA_BASE_URL}/admin/users`, { waitUntil: 'networkidle2' });
            await new Promise(r => setTimeout(r, 1000));
            const content = await p.evaluate(() => document.body.innerText);
            return { passed: content.length > 100, details: 'Users page has content' };
          });
          
          await runTest('admin_sites_page', async () => {
            const p = await getPage();
            await p.goto(`${LEMMA_BASE_URL}/admin/sites`, { waitUntil: 'networkidle2' });
            await new Promise(r => setTimeout(r, 1000));
            const content = await p.evaluate(() => document.body.innerText);
            return { passed: content.length > 100, details: 'Sites page has content' };
          });
        }
        
        if (suite === 'developer_dashboard' || suite === 'all') {
          await runTest('developer_page_loads', async () => {
            const p = await getPage();
            await p.goto(`${LEMMA_BASE_URL}/developer`, { waitUntil: 'networkidle2' });
            const content = await p.evaluate(() => document.body.innerText);
            return { passed: content.includes('Developer') || content.includes('Dashboard'), details: 'Developer page loaded' };
          });
          
          await runTest('developer_stats_visible', async () => {
            const p = await getPage();
            await p.goto(`${LEMMA_BASE_URL}/developer`, { waitUntil: 'networkidle2' });
            await new Promise(r => setTimeout(r, 1000));
            const statsPresent = await p.evaluate(() => document.body.innerText.length > 200);
            return { passed: statsPresent, details: 'Developer stats present' };
          });
          
          await runTest('agent_token_section', async () => {
            const p = await getPage();
            await p.goto(`${LEMMA_BASE_URL}/developer`, { waitUntil: 'networkidle2' });
            const hasAgentSection = await p.evaluate(() => {
              const content = document.body.innerText.toLowerCase();
              return content.includes('agent') || content.includes('ai access');
            });
            return { passed: hasAgentSection, details: 'Agent token section visible' };
          });
        }
        
        if (suite === 'site_management' || suite === 'all') {
          await runTest('sites_list_api', async () => {
            const result = await callApi('/api/developer/sites');
            return { 
              passed: result.ok && Array.isArray(result.data?.sites), 
              details: `Found ${result.data?.sites?.length || 0} sites` 
            };
          });
          
          await runTest('admin_sites_api', async () => {
            const result = await callApi('/api/admin/sites');
            return { 
              passed: result.ok && Array.isArray(result.data?.sites), 
              details: `Found ${result.data?.sites?.length || 0} sites` 
            };
          });
        }
        
        if (suite === 'agent_tokens' || suite === 'all') {
          await runTest('agent_validate_endpoint', async () => {
            const result = await callApi('/api/agent/validate', { method: 'POST' });
            return { passed: result.ok && result.data?.valid, details: `Token valid: ${result.data?.valid}` };
          });
          
          await runTest('agent_credentials_list', async () => {
            const result = await callApi('/api/agent/credentials');
            return { passed: result.ok, details: `Status: ${result.status}` };
          });
        }
        
        const passed = testResults.tests.filter(t => t.passed).length;
        const total = testResults.tests.length;
        testResults.summary = `${passed}/${total} tests passed`;
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify(testResults, null, 2)
          }]
        };
      }
      
      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error) {
    return {
      content: [{
        type: 'text',
        text: JSON.stringify({
          error: error.message,
          tool: name,
          args
        }, null, 2)
      }],
      isError: true
    };
  }
});

// Define resources (for viewing platform state)
server.setRequestHandler(ListResourcesRequestSchema, async () => {
  return {
    resources: [
      {
        uri: 'lemma://admin/dashboard',
        name: 'Admin Dashboard',
        description: 'Current state of the admin dashboard',
        mimeType: 'application/json'
      },
      {
        uri: 'lemma://admin/sites',
        name: 'Registered Sites',
        description: 'All sites registered on the platform',
        mimeType: 'application/json'
      },
      {
        uri: 'lemma://admin/customers',
        name: 'Customer Accounts',
        description: 'All customer accounts',
        mimeType: 'application/json'
      },
      {
        uri: 'lemma://health',
        name: 'Platform Health',
        description: 'Current platform health status',
        mimeType: 'application/json'
      }
    ]
  };
});

server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
  const { uri } = request.params;
  
  const resourceMap = {
    'lemma://admin/dashboard': '/api/admin/platform-stats',
    'lemma://admin/sites': '/api/admin/sites',
    'lemma://admin/customers': '/api/admin/customers',
    'lemma://health': '/api/health/detailed'
  };
  
  const endpoint = resourceMap[uri];
  if (!endpoint) {
    throw new Error(`Unknown resource: ${uri}`);
  }
  
  const result = await callApi(endpoint);
  
  return {
    contents: [{
      uri,
      mimeType: 'application/json',
      text: JSON.stringify(result.data, null, 2)
    }]
  };
});

// Cleanup on exit
process.on('SIGINT', async () => {
  if (browser) {
    await browser.close();
  }
  process.exit(0);
});

// Start server
async function main() {
  console.error('Starting Lemma MCP Server...');
  console.error(`Base URL: ${LEMMA_BASE_URL}`);
  console.error(`Agent Token: ${AGENT_TOKEN ? 'configured' : 'NOT SET'}`);
  
  const transport = new StdioServerTransport();
  await server.connect(transport);
  
  console.error('Lemma MCP Server running');
}

main().catch(console.error);
