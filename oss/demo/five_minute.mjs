#!/usr/bin/env node
/**
 * Five-minute offline demo: mint, verify accept, tamper reject.
 */

import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const OSS_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const testingUrl = pathToFileURL(
  path.join(OSS_ROOT, 'packages', 'proof-verifier-js', 'testing.mjs'),
).href;

const {
  mintTestIssuer,
  mintTestPresentation,
  verifyTestPresentationOffline,
} = await import(testingUrl);

const SITE_ID = 'localhost';
const PPID = 'did:lemma:ppid_demo_user';
const REQUIRED = 'passkey';

function ok(label) {
  console.log(`  PASS  ${label}`);
}

function fail(label, detail) {
  console.error(`  FAIL  ${label}: ${detail}`);
  process.exit(1);
}

console.log('lemma.id offline verifier demo (Node)\n');

console.log('1. Mint test presentation');
const issuer = await mintTestIssuer();
const presentation = await mintTestPresentation({
  siteId: SITE_ID,
  ppid: PPID,
  assurance: REQUIRED,
  issuer,
});
if (!presentation?.credential?.proof?.signatureValueWeb) {
  fail('mint', 'missing signature');
}
ok('signed presentation minted');

console.log('2. Verify accept');
const accept = await verifyTestPresentationOffline({
  presentation,
  siteId: SITE_ID,
  requiredAssurance: REQUIRED,
  trustedIssuerPubkeyHex: issuer.pubkeyHex,
});
if (!accept.ok) {
  fail('verify', accept.reason || 'unknown');
}
if (accept.ppid !== PPID) {
  fail('verify', `unexpected ppid ${accept.ppid}`);
}
ok(`ppid=${accept.ppid} assurance=${accept.assurance}`);

console.log('3. Tamper site binding -> reject');
const bad = structuredClone(presentation);
bad.credential.claims.siteId = 'evil.example';
bad.credential.credentialSubject.siteId = 'evil.example';
const reject = await verifyTestPresentationOffline({
  presentation: bad,
  siteId: SITE_ID,
  requiredAssurance: REQUIRED,
  trustedIssuerPubkeyHex: issuer.pubkeyHex,
});
if (reject.ok) {
  fail('tamper', 'expected rejection');
}
if (reject.reason !== 'site_id_mismatch') {
  fail('tamper', `expected site_id_mismatch got ${reject.reason}`);
}
ok(`fail-closed reason=${reject.reason}`);

console.log('\nDone — verifier accept/reject path works offline.');
