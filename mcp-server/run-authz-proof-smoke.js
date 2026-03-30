#!/usr/bin/env node
import fetch from 'node-fetch';

const LEMMA_BASE_URL = (process.env.LEMMA_BASE_URL || 'https://lemma.id').replace(/\/$/, '');
const LEMMA_CREDENTIAL = (process.env.LEMMA_CREDENTIAL || process.env.LEMMA_PROOF || '').trim();
const API_KEY = (process.env.LEMMA_API_KEY || '').trim();

if (!LEMMA_CREDENTIAL && !API_KEY) {
  console.error('Missing auth: set LEMMA_CREDENTIAL (preferred) or LEMMA_API_KEY');
  process.exit(2);
}

function authHeaders(extra = {}) {
  const headers = { 'Content-Type': 'application/json', ...extra };
  if (LEMMA_CREDENTIAL) headers['X-Lemma-Credential'] = LEMMA_CREDENTIAL;
  if (API_KEY) headers['X-API-Key'] = API_KEY;
  return headers;
}

async function call(path, options = {}) {
  const res = await fetch(`${LEMMA_BASE_URL}${path}`, {
    ...options,
    headers: authHeaders(options.headers || {}),
  });
  const data = await res.json().catch(() => null);
  return { status: res.status, ok: res.ok, data };
}

async function test(name, fn) {
  try {
    const out = await fn();
    if (!out.passed) throw new Error(out.details || 'failed');
    console.log(`✅ ${name}: ${out.details || 'ok'}`);
    return true;
  } catch (e) {
    console.log(`❌ ${name}: ${e.message}`);
    return false;
  }
}

async function main() {
  console.log('=== Lemma proof-first authz smoke ===');
  let pass = 0;
  let fail = 0;

  if (await test('Auth monitor endpoint', async () => {
    const r = await call('/api/agent/credentials/monitor');
    return { passed: r.ok, details: `status=${r.status}` };
  })) pass++; else fail++;

  if (await test('Developer sites list', async () => {
    const r = await call('/api/developer/sites');
    return { passed: r.ok && Array.isArray(r.data?.sites), details: `status=${r.status} sites=${r.data?.sites?.length ?? 'n/a'}` };
  })) pass++; else fail++;

  if (await test('Agent validate (proof path)', async () => {
    const r = await call('/api/agent/validate', { method: 'POST' });
    return { passed: r.ok || r.status === 401 || r.status === 403, details: `status=${r.status} valid=${r.data?.valid}` };
  })) pass++; else fail++;

  console.log(`\nResult: ${pass} passed, ${fail} failed`);
  process.exit(fail > 0 ? 1 : 0);
}

main().catch((e) => {
  console.error(`Fatal: ${e.message}`);
  process.exit(1);
});
