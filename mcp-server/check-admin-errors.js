#!/usr/bin/env node
import puppeteer from 'puppeteer';

const LEMMA_BASE_URL = 'https://lemma.id';
const AGENT_TOKEN = process.env.LEMMA_AGENT_TOKEN || '';

if (!AGENT_TOKEN.startsWith('lm_agent_')) {
  throw new Error('Missing valid LEMMA_AGENT_TOKEN in environment');
}

async function main() {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox']
  });
  
  const page = await browser.newPage();
  
  // Track all network requests
  const failedRequests = [];
  
  page.on('response', response => {
    if (response.status() >= 400) {
      failedRequests.push({
        url: response.url(),
        status: response.status(),
        statusText: response.statusText()
      });
    }
  });
  
  // Create agent session
  await page.goto(`${LEMMA_BASE_URL}/api/agent/session?token=${AGENT_TOKEN}`);
  console.log('Agent session created');
  
  // Visit admin page
  await page.goto(`${LEMMA_BASE_URL}/admin`, { waitUntil: 'networkidle2' });
  console.log('Admin page loaded');
  
  // Wait for JS to execute
  await new Promise(r => setTimeout(r, 3000));
  
  console.log('\n=== FAILED REQUESTS ===');
  failedRequests.forEach(req => {
    console.log(`${req.status} ${req.statusText}: ${req.url}`);
  });
  
  await browser.close();
}

main().catch(console.error);
