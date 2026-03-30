#!/usr/bin/env node
import fetch from 'node-fetch';

const LEMMA_BASE_URL = (process.env.LEMMA_BASE_URL || 'https://lemma.id').replace(/\/$/, '');
const ADMIN_TOKEN = process.env.LEMMA_AGENT_TOKEN;

if (!ADMIN_TOKEN) {
  console.error('Missing LEMMA_AGENT_TOKEN');
  process.exit(2);
}

function headers(token = ADMIN_TOKEN) {
  return {
    'Content-Type': 'application/json',
    'X-Agent-Token': token,
  };
}

async function call(path, options = {}) {
  const res = await fetch(`${LEMMA_BASE_URL}${path}`, options);
  const data = await res.json().catch(() => null);
  return { res, data };
}

async function main() {
  console.log('=== Revocation Regression (issue -> validate -> revoke -> deny) ===');

  const preflight = await call('/api/agent/validate', { method: 'POST', headers: headers() });
  const scopes = preflight.data?.scope || preflight.data?.scopes || [];
  if (!preflight.res.ok || preflight.data?.valid !== true || !Array.isArray(scopes) || !scopes.includes('admin')) {
    throw new Error(`Preflight failed: status=${preflight.res.status} body=${JSON.stringify(preflight.data)}`);
  }
  console.log('Preflight OK');

  const issuePayload = {
    agent_name: `revocation-regression-${Date.now()}`,
    ttl_hours: 1,
    scope: ['read'],
    intended_platform: 'lemma.id'
  };

  const issued = await call('/api/agent/credentials/issue', {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(issuePayload)
  });

  if (!issued.res.ok || !issued.data?.success) {
    throw new Error(`Issue failed: status=${issued.res.status} body=${JSON.stringify(issued.data)}`);
  }

  const newToken = issued.data?.credential?.token;
  const tokenId = issued.data?.credential?.token_id;
  if (!newToken || !tokenId) {
    throw new Error(`Issue response missing token/token_id: ${JSON.stringify(issued.data)}`);
  }
  console.log(`Issued token: ${tokenId}`);

  const validBefore = await call('/api/agent/validate', { method: 'POST', headers: headers(newToken) });
  if (!validBefore.res.ok || validBefore.data?.valid !== true) {
    throw new Error(`Validation before revoke failed: status=${validBefore.res.status} body=${JSON.stringify(validBefore.data)}`);
  }
  console.log('Validation before revoke OK');

  const revoked = await call(`/api/agent/credentials/${encodeURIComponent(tokenId)}/revoke`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ reason: 'Automated revocation regression' })
  });

  if (!revoked.res.ok || !revoked.data?.success) {
    throw new Error(`Revoke failed: status=${revoked.res.status} body=${JSON.stringify(revoked.data)}`);
  }
  console.log('Revoke OK');

  const validAfter = await call('/api/agent/validate', { method: 'POST', headers: headers(newToken) });
  if (!(validAfter.res.status === 401 && validAfter.data?.valid === false && (validAfter.data?.error === 'invalid_token' || validAfter.data?.error))) {
    throw new Error(`Validation after revoke did not deny as expected: status=${validAfter.res.status} body=${JSON.stringify(validAfter.data)}`);
  }

  console.log('✅ PASS: revoked token denied after revocation');
}

main().catch((err) => {
  console.error(`❌ FAIL: ${err.message}`);
  process.exit(1);
});
