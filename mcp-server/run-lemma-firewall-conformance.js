#!/usr/bin/env node
import fetch from 'node-fetch';
import crypto from 'crypto';

const LEMMA_BASE_URL = (process.env.LEMMA_BASE_URL || process.env.LEMMA_URL || 'https://lemma.id').replace(/\/$/, '');
const ADMIN_TOKEN = process.env.LEMMA_AGENT_TOKEN || '';
const REQUIRED_AUDIENCE = (process.env.LEMMA_FIREWALL_REQUIRED_AUDIENCE || 'lemma-firewall').trim().toLowerCase();

if (!ADMIN_TOKEN.startsWith('lm_agent_')) {
  throw new Error('Missing valid LEMMA_AGENT_TOKEN in environment');
}

function headers(token = ADMIN_TOKEN) {
  return {
    'Content-Type': 'application/json',
    'X-Agent-Token': token
  };
}

async function call(path, options = {}) {
  const res = await fetch(`${LEMMA_BASE_URL}${path}`, options);
  const data = await res.json().catch(() => null);
  return { res, data };
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function authorizeDecision({ validation, requiredScope, requiredAudience, requestPath, expectedTaskHash }) {
  if (!(validation?.valid === true)) {
    return { allow: false, error_code: validation?.error || 'invalid_token' };
  }

  const scope = Array.isArray(validation.scope) ? validation.scope : [];
  if (requiredScope && !scope.includes(requiredScope)) {
    return { allow: false, error_code: 'missing_scope' };
  }

  if (requiredAudience) {
    const tokenAudience = String(validation.audience || '').trim().toLowerCase();
    if (tokenAudience !== requiredAudience) {
      return { allow: false, error_code: 'audience_mismatch' };
    }
  }

  if (requestPath && Array.isArray(validation.allowed_paths)) {
    const allowed = validation.allowed_paths.some((pattern) => {
      if (typeof pattern !== 'string') return false;
      const escaped = pattern
        .replace(/[.+?^${}()|[\]\\]/g, '\\$&')
        .replace(/\*\*/g, '.*')
        .replace(/\*/g, '[^/]*');
      return new RegExp(`^${escaped}$`).test(requestPath);
    });
    if (!allowed) {
      return { allow: false, error_code: 'path_not_allowed' };
    }
  }

  if (expectedTaskHash && validation.task_hash && validation.task_hash !== expectedTaskHash) {
    return { allow: false, error_code: 'task_mismatch' };
  }

  if (typeof validation.operations_remaining === 'number' && validation.operations_remaining < 0) {
    return { allow: false, error_code: 'max_operations_exceeded' };
  }

  return { allow: true };
}

async function issueToken(overrides = {}) {
  const payload = {
    agent_name: `lemma-firewall-conformance-${Date.now()}`,
    ttl_hours: 1,
    scope: ['read'],
    audience: REQUIRED_AUDIENCE,
    ...overrides
  };

  const maxAttempts = 4;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const issued = await call('/api/agent/credentials/issue', {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify(payload)
    });
    if (issued.res.ok && issued.data?.success) {
      return issued.data.credential;
    }

    const isRateLimited = issued.res.status === 429 || issued.data?.error === 'rate_limit_exceeded';
    if (!isRateLimited || attempt === maxAttempts) {
      throw new Error(`Failed to issue token: status=${issued.res.status} body=${JSON.stringify(issued.data)}`);
    }

    const retryAfterSeconds = Number(
      issued.data?.retry_after ||
      issued.res.headers.get('retry-after') ||
      60
    );
    const waitMs = Math.max(1000, retryAfterSeconds * 1000);
    console.log(`Rate-limited on token issue. Waiting ${Math.round(waitMs / 1000)}s before retry ${attempt + 1}/${maxAttempts}...`);
    await sleep(waitMs);
  }

  throw new Error('Failed to issue token after retries');
}

async function revokeToken(tokenId) {
  await call(`/api/agent/credentials/${encodeURIComponent(tokenId)}/revoke`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ reason: 'Lemma Firewall conformance cleanup' })
  });
}

async function validateToken(token) {
  return call('/api/agent/validate', { method: 'POST', headers: headers(token) });
}

const tests = [];
async function runTest(name, fn) {
  try {
    await fn();
    tests.push({ name, passed: true });
    console.log(`PASS ${name}`);
  } catch (err) {
    tests.push({ name, passed: false, error: err.message });
    console.log(`FAIL ${name}: ${err.message}`);
  }
}

async function main() {
  console.log('=== Lemma Firewall Conformance (Sprint 1 minimum matrix) ===');

  let tokenValid;
  let validationValid;
  await runTest('1) valid token + required scope + allowed path -> allow', async () => {
    const issued = await issueToken({
      scope: ['read'],
      allowed_paths: ['/api/agent/**']
    });
    tokenValid = issued.token;
    const { data } = await validateToken(issued.token);
    validationValid = data;
    const decision = authorizeDecision({
      validation: data,
      requiredScope: 'read',
      requiredAudience: REQUIRED_AUDIENCE,
      requestPath: '/api/agent/validate'
    });
    if (!decision.allow) {
      throw new Error(`Expected allow, got ${decision.error_code}`);
    }
  });

  await runTest('2) missing token -> auth_required', async () => {
    const { data } = await call('/api/agent/validate', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
    if (!(data?.valid === false && data?.error === 'auth_required')) {
      throw new Error(`Unexpected response: ${JSON.stringify(data)}`);
    }
  });

  await runTest('3) wrong audience -> audience_mismatch', async () => {
    const decision = authorizeDecision({
      validation: validationValid,
      requiredScope: 'read',
      requiredAudience: 'not-lemma-firewall',
      requestPath: '/api/agent/validate'
    });
    if (!(decision.allow === false && decision.error_code === 'audience_mismatch')) {
      throw new Error(`Unexpected decision: ${JSON.stringify(decision)}`);
    }
  });

  await runTest('4) expired token -> token_expired', async () => {
    const decision = authorizeDecision({
      validation: { valid: false, error: 'token_expired' },
      requiredScope: 'read',
      requiredAudience: REQUIRED_AUDIENCE,
      requestPath: '/api/agent/validate'
    });
    if (!(decision.allow === false && decision.error_code === 'token_expired')) {
      throw new Error(`Unexpected decision: ${JSON.stringify(decision)}`);
    }
  });

  await runTest('5) revoked token -> token_revoked', async () => {
    const issued = await issueToken({ scope: ['read'] });
    await revokeToken(issued.token_id);
    const { res, data } = await validateToken(issued.token);
    if (!(res.status === 401 && data?.error === 'token_revoked')) {
      throw new Error(`Unexpected revoke result: status=${res.status} body=${JSON.stringify(data)}`);
    }
  });

  await runTest('6) missing scope -> missing_scope', async () => {
    const decision = authorizeDecision({
      validation: validationValid,
      requiredScope: 'write',
      requiredAudience: REQUIRED_AUDIENCE,
      requestPath: '/api/agent/validate'
    });
    if (!(decision.allow === false && decision.error_code === 'missing_scope')) {
      throw new Error(`Unexpected decision: ${JSON.stringify(decision)}`);
    }
  });

  await runTest('7) disallowed path -> path_not_allowed', async () => {
    const issued = await issueToken({ scope: ['read'], allowed_paths: ['/api/developer/**'] });
    const { data } = await validateToken(issued.token);
    const decision = authorizeDecision({
      validation: data,
      requiredScope: 'read',
      requiredAudience: REQUIRED_AUDIENCE,
      requestPath: '/api/admin/sites'
    });
    if (!(decision.allow === false && decision.error_code === 'path_not_allowed')) {
      throw new Error(`Unexpected decision: ${JSON.stringify(decision)}`);
    }
  });

  await runTest('8) max operations exceeded -> max_operations_exceeded', async () => {
    const issued = await issueToken({ scope: ['read'], max_operations: 1 });
    await validateToken(issued.token); // consume the only operation
    const { res, data } = await validateToken(issued.token); // should exceed now
    if (!(res.status === 401 && data?.error === 'max_operations_exceeded')) {
      throw new Error(`Unexpected max-op result: status=${res.status} body=${JSON.stringify(data)}`);
    }
  });

  const passed = tests.filter(t => t.passed).length;
  const failed = tests.length - passed;
  console.log(`\nSummary: ${passed}/${tests.length} passed`);
  if (failed > 0) {
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(`Conformance run failed: ${err.message}`);
  process.exit(1);
});
