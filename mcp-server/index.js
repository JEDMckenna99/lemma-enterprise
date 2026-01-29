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
