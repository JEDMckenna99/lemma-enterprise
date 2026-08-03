/**
 * @lemma.id/proof-verifier/testing — offline test helpers for integrator CI.
 *
 * Mint signed presentations and verify credential signatures without lemma.id
 * or WebAuthn. Use for unit-testing your login handler; use end-to-end tests
 * with the browser SDK separately.
 */

import { assuranceMeetsPolicy, browserCanonicalMessage, canonicalizeSiteHostname } from './index.mjs';

const DEFAULT_DEV_ISSUER_SEED = new TextEncoder().encode(
  'e2e-dev-issuer-seed-0123456789!!',
);

function bytesToHex(bytes) {
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

async function sha256(data) {
  const digest = await crypto.subtle.digest('SHA-256', data);
  return new Uint8Array(digest);
}

function concatPkcs8(raw32) {
  const prefix = new Uint8Array([
    0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70,
    0x04, 0x22, 0x04, 0x20,
  ]);
  const out = new Uint8Array(prefix.length + raw32.length);
  out.set(prefix, 0);
  out.set(raw32, prefix.length);
  return out;
}

async function importEd25519PrivateKey(seedBytes) {
  const digest = await sha256(seedBytes);
  return crypto.subtle.importKey(
    'pkcs8',
    concatPkcs8(digest),
    { name: 'Ed25519' },
    true,
    ['sign'],
  );
}

function base64urlToBytes(value) {
  const padded = String(value || '').replace(/-/g, '+').replace(/_/g, '/');
  const padLen = (4 - (padded.length % 4)) % 4;
  const normalized = padded + '='.repeat(padLen);
  const binary = atob(normalized);
  return Uint8Array.from(binary, (ch) => ch.charCodeAt(0));
}

async function exportPublicKeyHex(privateKey) {
  const jwk = await crypto.subtle.exportKey('jwk', privateKey);
  if (!jwk?.x) throw new Error('public_key_unavailable');
  return bytesToHex(base64urlToBytes(jwk.x));
}

export async function mintTestIssuer(seedBytes = DEFAULT_DEV_ISSUER_SEED) {
  const privateKey = await importEd25519PrivateKey(seedBytes);
  const pubkeyHex = await exportPublicKeyHex(privateKey);
  const did = `did:lemma:test:${pubkeyHex.slice(0, 16)}`;
  return { did, pubkeyHex, privateKey };
}

async function signCredentialBody(body, privateKey) {
  const message = browserCanonicalMessage(body);
  const digest = await sha256(message);
  const signature = await crypto.subtle.sign('Ed25519', privateKey, digest);
  return bytesToHex(new Uint8Array(signature));
}

export async function mintTestCredential({
  siteId,
  ppid,
  assurance = 'passkey',
  issuer = null,
  credentialId = null,
} = {}) {
  if (!siteId || !ppid) throw new Error('siteId and ppid required');
  const resolvedIssuer = issuer || (await mintTestIssuer());
  const now = Math.floor(Date.now() / 1000);
  const credId = credentialId || `ishuman_test_${bytesToHex(crypto.getRandomValues(new Uint8Array(8)))}`;
  const claims = {
    assurance,
    siteId,
    issuedAt: String(now),
    expiresAt: String(now + 86400 * 30),
    packageType: 'identity',
    verificationMethod: assurance === 'passkey' ? 'passkey' : 'stripe_identity',
  };
  if (assurance === 'ishuman') claims.isHuman = true;
  const body = {
    id: credId,
    issuer: resolvedIssuer.did,
    subject: ppid,
    claims,
    credentialSubject: { ...claims },
  };
  const signatureValueWeb = await signCredentialBody(body, resolvedIssuer.privateKey);
  return {
    ...body,
    issuerInfo: { did: resolvedIssuer.did, publicKey: resolvedIssuer.pubkeyHex },
    proof: {
      type: 'Ed25519Signature2020',
      verificationMethod: resolvedIssuer.did,
      signatureValueWeb,
    },
  };
}

export async function mintTestPresentation(options = {}) {
  const credential = await mintTestCredential(options);
  return {
    siteId: options.siteId,
    credential,
  };
}

/**
 * Lightweight offline verify for integrator unit tests (no bloom/trust fetch).
 */
export async function verifyTestPresentationOffline({
  presentation,
  siteId,
  requiredAssurance = 'passkey',
  trustedIssuerPubkeyHex,
} = {}) {
  const credential = presentation?.credential;
  if (!credential || typeof credential !== 'object') {
    return { ok: false, reason: 'credential_missing' };
  }
  const canonicalSite = canonicalizeSiteHostname(siteId || presentation.siteId || '');
  const claims = credential.claims || credential.credentialSubject || {};
  const assurance = String(claims.assurance || '').toLowerCase();
  if (!assuranceMeetsPolicy(assurance, requiredAssurance)) {
    return { ok: false, reason: 'assurance_insufficient', assurance };
  }
  const boundSite = canonicalizeSiteHostname(
    claims.siteId || claims.site_id || claims.siteDomain || '',
  );
  if (boundSite !== canonicalSite) {
    return { ok: false, reason: 'site_id_mismatch' };
  }
  const pubkeyHex = String(
    trustedIssuerPubkeyHex || credential.issuerInfo?.publicKey || '',
  ).trim().toLowerCase();
  if (!pubkeyHex || pubkeyHex.length !== 64) {
    return { ok: false, reason: 'trusted_issuer_pubkey_missing' };
  }
  try {
    const message = browserCanonicalMessage(credential);
    const digest = await sha256(message);
    const signature = hexToBytes(String(credential.proof?.signatureValueWeb || ''));
    const publicKey = await crypto.subtle.importKey(
      'raw',
      hexToBytes(pubkeyHex),
      { name: 'Ed25519' },
      false,
      ['verify'],
    );
    const valid = await crypto.subtle.verify('Ed25519', publicKey, signature, digest);
    if (!valid) return { ok: false, reason: 'invalid_signature' };
  } catch {
    return { ok: false, reason: 'invalid_signature' };
  }
  return {
    ok: true,
    reason: 'valid',
    ppid: credential.subject,
    assurance,
    credential_id: credential.id,
  };
}

function hexToBytes(hex) {
  const normalized = String(hex || '').trim();
  const out = new Uint8Array(normalized.length / 2);
  for (let i = 0; i < out.length; i += 1) {
    out[i] = parseInt(normalized.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}

export function createOfflineTestVerifier({
  siteId,
  issuerDid,
  issuerPubkeyHex,
  requiredAssurance = 'passkey',
} = {}) {
  return {
    verify: (presentation) => verifyTestPresentationOffline({
      presentation,
      siteId,
      requiredAssurance,
      trustedIssuerPubkeyHex: issuerPubkeyHex,
    }),
  };
}
