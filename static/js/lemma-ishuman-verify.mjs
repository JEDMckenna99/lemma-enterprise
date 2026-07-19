/**
 * @lemma/ishuman-verify, Local-first isHuman presentation verifier.
 *
 * Drop-in ES module that verifies an `IsHumanVerifier.verify()` result
 * **entirely on your backend** with no per-request calls to lemma.id.
 *
 * Works in: Node.js 19+, Deno, Bun, Cloudflare Workers, Vercel Edge, Netlify
 * Edge, browsers (modern). Only requires globalThis.crypto.subtle (WebCrypto).
 * Zero npm dependencies.
 *
 * Privacy / cost: lemma.id is contacted only to refresh the signed Bloom
 * snapshot + trust list (default every 15 minutes, cached). lemma.id never
 * sees an individual verification.
 *
 * @example
 *   import { createVerifier } from "https://lemma.id/sdk/lemma-ishuman-verify.mjs";
 *
 *   const verifier = createVerifier({ siteId: "tickets-demo.lemma.id" });
 *
 *   // In your request handler:
 *   const result = await verifier.verify(presentationFromClient);
 *   if (!result.ok) return new Response(result.reason, { status: 401 });
 *   const ppid = result.ppid;
 *
 *   // Or verify a stamp you stored earlier (from the browser SDK's
 *   // stamp(payload, { includeCredential: true })), re-checks the credential
 *   // + revocation AND that the stamp's logged ppid/credentialId match it.
 *   // verifyStamp accepts a bare VC, a presentation, a stamp, or a stamped
 *   // event interchangeably:
 *   const check = await verifier.verifyStamp(storedLogRow.lemma);
 *   if (!check.ok) flagSuspiciousLogRow();
 *
 *   // Re-verifying OLD log rows? Use durable mode so an aged session
 *   // assertion is treated as informational (credential + revocation still
 *   // enforced):
 *   const audit = await verifier.verifyStamp(oldRow.lemma, { durable: true });
 *
 * @version 1.4.0
 */

const SESSION_PRESENTATION_PREFIX = "lemma:site-session-presentation:v1";
const ACTION_PRESENTATION_PREFIX = "lemma:site-action-presentation:v1";
const ACTION_STAMP_VERSION = "action_stamp_v1";
const DEFAULT_LEMMA_ORIGIN = "https://lemma.id";
const DEFAULT_REFRESH_MS = 15 * 60 * 1000;
const DEFAULT_MAX_SESSION_AGE_S = 24 * 60 * 60;
const DEFAULT_MAX_ACTION_AGE_S = 60;
const CONVERGENCE_PREFIX = "lemma:ppid-convergence:v1";
const CONVERGENCE_SCHEMA = "ppid_convergence.v1";
const ACTION_COMMITMENT_PREFIX = "lemma:action-commitment:v1";
const FRESH_PASSKEY_PREFIX = "lemma:fresh-passkey-attestation:v1";
const FRESH_PASSKEY_SCHEMA = "fresh_passkey_attestation.v1";
const DEFAULT_FRESH_PASSKEY_MAX_AGE_S = 120;
const NONCE_STORE_MODE_OPTIONAL = "optional";
const NONCE_STORE_MODE_REQUIRED = "required";
const BLOOM_SNAPSHOT_PREFIX = "lemma:bloom-snapshot:v1";
const TRUST_LIST_PREFIX = "lemma:issuer-trust-list:v1";
const TIME_SKEW_SECONDS = 300;
const DEFAULT_MAX_BLOOM_STALENESS_SECONDS = 900;
const BROWSER_CANONICAL_V2 = "browser_canonical_v2";

/** Sync with docs/cryptographic/NETWORK_ROOT_PUBKEYS.json for Browser embed. */
const DEFAULT_NETWORK_ROOT_PUBKEYS_HEX = [
  "3782cf10beea1dcc9a88127a5dbb71c6cba30c1c8c63327a83b8f09867d6a6c2",
];

// ---------------------------------------------------------------------------
// Site hostname canonicalization (mirrors api/site_hostname.py)
// ---------------------------------------------------------------------------

function canonicalizeRpId(rpId) {
  let value = String(rpId || "").trim().toLowerCase();
  if (!value) return "unknown";
  if (value.includes("://")) {
    try {
      value = new URL(value).hostname.toLowerCase();
    } catch {
      value = value.split("://").slice(1).join("://") || value;
    }
  }
  let host = value.split("/")[0];
  if (host.includes(":") && !host.startsWith("[")) {
    host = host.split(":")[0];
  }
  if (host.startsWith("www.")) {
    host = host.slice(4);
  }
  return host || "unknown";
}

export function canonicalizeSiteHostname(value) {
  const raw = String(value || "").trim();
  if (!raw) throw new Error("hostname_required");
  if (raw.toLowerCase().startsWith("site_")) {
    throw new Error("internal_site_id_not_allowed");
  }
  const canonical = canonicalizeRpId(raw);
  if (!canonical || canonical === "unknown") {
    throw new Error("invalid_hostname");
  }
  return canonical;
}

function tryCanonicalizeSiteHostname(value) {
  try {
    return { canonical: canonicalizeSiteHostname(value), error: null };
  } catch (err) {
    return { canonical: null, error: err.message || "invalid_hostname" };
  }
}

// ---------------------------------------------------------------------------
// Tiny byte / hex / base64url helpers
// ---------------------------------------------------------------------------

function hexToBytes(hex) {
  const clean = String(hex || "").trim();
  if (!clean || clean.length % 2 !== 0) throw new Error("malformed_hex");
  const out = new Uint8Array(clean.length / 2);
  for (let i = 0; i < out.length; i += 1) {
    out[i] = parseInt(clean.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}

function bytesToHex(bytes) {
  let hex = "";
  for (let i = 0; i < bytes.length; i += 1) {
    hex += bytes[i].toString(16).padStart(2, "0");
  }
  return hex;
}

function base64urlToBytes(text) {
  const raw = String(text || "").trim();
  if (!raw) return new Uint8Array(0);
  const padded = raw.replace(/-/g, "+").replace(/_/g, "/")
    + "=".repeat((4 - (raw.length % 4)) % 4);
  // atob is available in all target runtimes
  const bin = atob(padded);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) out[i] = bin.charCodeAt(i);
  return out;
}

async function sha256Bytes(input) {
  const digest = await crypto.subtle.digest("SHA-256", input);
  return new Uint8Array(digest);
}

async function sha256HexText(text) {
  return bytesToHex(await sha256Bytes(new TextEncoder().encode(String(text))));
}

function normalizeDid(did) {
  return String(did || "")
    .trim()
    .split("#", 1)[0]
    .split("?", 1)[0]
    .replace(/\/+$/, "")
    .toLowerCase();
}

function parseIssuerPubkeyHex(snapshot) {
  const direct = String(snapshot?.issuer_pubkey || "").trim().toLowerCase();
  if (direct.length === 64) return direct;
  const did = String(snapshot?.issuer_did || "");
  const fromDid = did.replace("did:lemma:", "").substring(0, 64).toLowerCase();
  return fromDid.length === 64 ? fromDid : "";
}

function resolveNetworkRootPubkeys(override) {
  if (Array.isArray(override) && override.length) {
    return override.map((p) => String(p).trim().toLowerCase()).filter((p) => p.length === 64);
  }
  const env = typeof process !== "undefined" ? process.env?.LEMMA_NETWORK_ROOT_PUBKEYS : "";
  if (env) {
    return String(env)
      .split(",")
      .map((p) => p.trim().toLowerCase())
      .filter((p) => p.length === 64);
  }
  return DEFAULT_NETWORK_ROOT_PUBKEYS_HEX.slice();
}

function signerPubkeyIsPinned(signerPubkey, networkRootPubkeys) {
  const normalized = String(signerPubkey || "").trim().toLowerCase();
  if (!normalized || normalized.length !== 64) return false;
  const pins = resolveNetworkRootPubkeys(networkRootPubkeys);
  if (!pins.length) {
    return typeof process !== "undefined"
      && process.env?.LEMMA_ALLOW_UNPINNED_TRUST_ROOT === "1";
  }
  return pins.includes(normalized);
}

async function computeTrustListContentHash(issuers) {
  const canonicalEntries = (Array.isArray(issuers) ? issuers : []).map((row) => ({
    did: String(row?.did || row?.issuer_did || "").trim(),
    pubkey: String(row?.pubkey || row?.public_key || row?.publicKey || "").trim().toLowerCase(),
    key_id: String(row?.key_id || "").trim(),
    status: String(row?.status || "active").trim().toLowerCase(),
    valid_from_unix: Number(row?.valid_from_unix || 0),
    valid_until_unix: Number(row?.valid_until_unix || 0),
    priority: Number(row?.priority || 0),
  }));
  const canonical = JSON.stringify(
    canonicalEntries.map((entry) => {
      const sorted = {};
      for (const key of Object.keys(entry).sort()) sorted[key] = entry[key];
      return sorted;
    }),
  );
  return sha256HexText(canonical);
}

function buildBloomSignatureMessage(snapshot) {
  return new TextEncoder().encode([
    BLOOM_SNAPSHOT_PREFIX,
    String(snapshot.sequence_number || ""),
    String(snapshot.content_hash || ""),
    String(snapshot.generated_at_unix || ""),
    String(snapshot.valid_until_unix || ""),
  ].join("\n"));
}

function buildTrustListSignatureMessage(trustList) {
  return new TextEncoder().encode([
    TRUST_LIST_PREFIX,
    String(trustList.version || ""),
    String(trustList.content_hash || ""),
    String(trustList.generated_at_unix || ""),
    String(trustList.valid_until_unix || ""),
  ].join("\n"));
}

function flattenTrustedIssuerPubkeys(issuers) {
  const out = [];
  if (issuers instanceof Map) {
    for (const keySet of issuers.values()) {
      if (keySet instanceof Set) {
        for (const pubkey of keySet) out.push(String(pubkey).toLowerCase());
      }
    }
  } else if (issuers && typeof issuers === "object") {
    for (const value of Object.values(issuers)) {
      if (value instanceof Set) {
        for (const pubkey of value) out.push(String(pubkey).toLowerCase());
      } else if (value && typeof value === "object" && value.pubkeys_hex) {
        for (const pubkey of value.pubkeys_hex) out.push(String(pubkey).toLowerCase());
      }
    }
  }
  return out;
}

export function assuranceMeetsPolicy(actual, required) {
  if (!actual) return false;
  const policy = String(required || "ishuman").toLowerCase();
  const normalized = String(actual).toLowerCase();
  if (policy === "passkey") return normalized === "passkey" || normalized === "ishuman";
  return normalized === "ishuman";
}

async function verifyEd25519(pubkeyBytes, message, signature) {
  // WebCrypto Ed25519 (Node 22+, browsers/Deno modern). Fall back to noble
  // when subtle.importKey rejects "Ed25519".
  try {
    const key = await crypto.subtle.importKey(
      "raw",
      pubkeyBytes,
      { name: "Ed25519", namedCurve: "Ed25519" },
      false,
      ["verify"],
    );
    return crypto.subtle.verify("Ed25519", key, signature, message);
  } catch (_err) {
    const noble = await import("@noble/ed25519").catch(() => null);
    if (!noble) {
      throw new Error(
        "ed25519_unavailable: install @noble/ed25519 or run on a runtime "
        + "with WebCrypto Ed25519 (Node 22+, Deno, modern browsers)",
      );
    }
    if (noble.etc && typeof noble.etc.sha512Sync !== "function") {
      noble.etc.sha512Async = async (...messages) => {
        const total = messages.reduce((sum, m) => sum + m.length, 0);
        const merged = new Uint8Array(total);
        let offset = 0;
        for (const m of messages) {
          merged.set(m, offset);
          offset += m.length;
        }
        const d = await crypto.subtle.digest("SHA-512", merged);
        return new Uint8Array(d);
      };
    }
    return noble.verifyAsync(signature, message, pubkeyBytes);
  }
}

// ---------------------------------------------------------------------------
// Canonical message helpers (must byte-exactly match the issuer)
// ---------------------------------------------------------------------------

/**
 * Reproduce the canonical message signed as `proof.signatureValueWeb`.
 * Mirrors `_browser_canonical_message` in api/ishuman.py.
 */
export function browserCanonicalMessage(credential) {
  const claims = credential.claims || credential.credentialSubject || {};
  const sorted = {};
  for (const key of Object.keys(claims).sort()) {
    const value = claims[key];
    if (value === true) sorted[key] = "true";
    else if (value === false) sorted[key] = "false";
    else if (Array.isArray(value) || (value && typeof value === "object")) {
      sorted[key] = JSON.stringify(value);
    } else {
      sorted[key] = value;
    }
  }
  const payload = {
    issuer: credential.issuer,
    subject: credential.subject,
    claims: sorted,
  };
  const credentialId = String(credential.id || "").trim();
  if (credentialId) payload.id = credentialId;
  if (credential.issuedAt !== undefined && credential.issuedAt !== null) {
    payload.issuedAt = credential.issuedAt;
  }
  if (credential.expiresAt !== undefined && credential.expiresAt !== null) {
    payload.expiresAt = credential.expiresAt;
  }
  return new TextEncoder().encode(JSON.stringify(payload));
}

export function browserCanonicalMessageVersion(credential) {
  return String(credential?.id || "").trim() ? BROWSER_CANONICAL_V2 : "browser_canonical_v1";
}

function extractCredentialAssurance(claims) {
  if (claims?.assurance) return String(claims.assurance).toLowerCase();
  if (claims?.isHuman === true || claims?.isHuman === "true") return "ishuman";
  return null;
}

export function validateCredentialRequiredFields(credential) {
  if (!credential || typeof credential !== "object") return "credential_missing";
  if (!String(credential.id || "").trim()) return "credential_id_missing";
  if (!String(credential.issuer || "").trim()) return "credential_issuer_missing";
  if (!String(credential.subject || "").trim()) return "credential_subject_missing";
  const claims = credential.claims || credential.credentialSubject || {};
  const boundSite = claims.siteId || claims.site_id || claims.siteDomain || claims.site_domain || "";
  if (!String(boundSite || "").trim()) return "credential_site_binding_missing";
  const issuedAt = claims.issuedAt ?? credential.issuedAt;
  const expiresAt = claims.expiresAt ?? credential.expiresAt;
  if (issuedAt === undefined || issuedAt === null || issuedAt === "") {
    return "credential_issued_at_missing";
  }
  if (expiresAt === undefined || expiresAt === null || expiresAt === "") {
    return "credential_expires_at_missing";
  }
  if (!extractCredentialAssurance(claims)) return "credential_assurance_missing";
  const sigHex = String((credential.proof || {}).signatureValueWeb || "").trim();
  if (!sigHex) return "browser_signature_missing";
  return null;
}

function buildConvergenceCanonicalMessage(artifact) {
  return new TextEncoder().encode([
    CONVERGENCE_PREFIX,
    String(artifact.site_id || "").trim(),
    String(artifact.legacy_ppid || "").trim(),
    String(artifact.canonical_ppid || "").trim(),
    String(artifact.convergence_id || "").trim(),
    String(artifact.nonce || "").trim(),
    String(Number(artifact.issued_at_unix || 0)),
    String(Number(artifact.expires_at_unix || 0)),
  ].join("\n"));
}

async function verifyPpidConvergenceArtifact(
  artifact,
  { siteId, canonicalPpid, trustedIssuerPubkeys, nowUnix },
) {
  if (!artifact || typeof artifact !== "object") {
    return { ok: false, reason: "convergence_missing" };
  }
  if (String(artifact.schema || "") !== CONVERGENCE_SCHEMA) {
    return { ok: false, reason: "convergence_schema_mismatch" };
  }
  if (String(artifact.site_id || "").trim() !== String(siteId || "").trim()) {
    return { ok: false, reason: "convergence_site_mismatch" };
  }
  if (String(artifact.canonical_ppid || "").trim() !== String(canonicalPpid || "").trim()) {
    return { ok: false, reason: "convergence_canonical_ppid_mismatch" };
  }
  const now = Number(nowUnix ?? Math.floor(Date.now() / 1000));
  const expiresAt = Number(artifact.expires_at_unix || 0);
  const issuedAt = Number(artifact.issued_at_unix || 0);
  if (!issuedAt || !expiresAt || expiresAt < now) {
    return { ok: false, reason: "convergence_expired" };
  }
  const signatureHex = String((artifact.proof || {}).signatureValueWeb || "").trim();
  if (!signatureHex) return { ok: false, reason: "convergence_signature_missing" };
  const unsigned = {
    schema: artifact.schema,
    convergence_id: artifact.convergence_id,
    site_id: artifact.site_id,
    legacy_ppid: artifact.legacy_ppid,
    canonical_ppid: artifact.canonical_ppid,
    issued_at_unix: artifact.issued_at_unix,
    expires_at_unix: artifact.expires_at_unix,
    nonce: artifact.nonce,
  };
  const digest = await sha256Bytes(buildConvergenceCanonicalMessage(unsigned));
  for (const pubkeyHex of trustedIssuerPubkeys) {
    try {
      const ok = await verifySiteEd25519Digest(
        hexToBytes(pubkeyHex),
        hexToBytes(signatureHex),
        digest,
      );
      if (ok) return { ok: true, reason: "valid", legacyPpid: String(artifact.legacy_ppid || "").trim() || null };
    } catch {
      continue;
    }
  }
  return { ok: false, reason: "convergence_invalid_signature" };
}

export function createInMemorySitePolicyStore({ blocked = [], doubted = [] } = {}) {
  const blockedSet = new Set(blocked);
  const doubtedSet = new Set(doubted);
  return {
    async check(ppid) {
      const subject = String(ppid || "").trim();
      if (!subject) return { available: true, decision: {}, reason: "ppid_missing" };
      if (blockedSet.has(subject)) {
        return { available: true, decision: { blocked: true, reason: "site_block" }, reason: "ok" };
      }
      if (doubtedSet.has(subject)) {
        return { available: true, decision: { doubtRequired: true, doubtReason: "site_doubt" }, reason: "ok" };
      }
      return { available: true, decision: {}, reason: "ok" };
    },
  };
}

/**
 * Server-only site block/doubt store backed by GET /api/ishuman/check.
 * Mirrors packages/ishuman-verify-py/lemma_ishuman_site_policy.LemmaCheckPolicyStore.
 */
export function createLemmaCheckPolicyStore({
  siteId,
  apiKey,
  lemmaOrigin = DEFAULT_LEMMA_ORIGIN,
  cacheTtlSeconds = 30,
  timeoutSeconds = 5,
  failClosed = true,
  fetch: fetchImpl,
} = {}) {
  if (!siteId) throw new Error("siteId required");
  if (!apiKey) throw new Error("apiKey required");
  const canonicalSiteId = canonicalizeSiteHostname(siteId);
  const cache = new Map();

  return {
    async check(ppid) {
      const subject = String(ppid || "").trim();
      if (!subject) {
        return { available: false, decision: {}, reason: "ppid_missing" };
      }
      const now = Date.now();
      const cached = cache.get(subject);
      if (cached && now - cached.at <= cacheTtlSeconds * 1000) {
        return { available: true, decision: cached.decision, reason: "ok" };
      }
      const url = (
        `${lemmaOrigin.replace(/\/$/, "")}/api/ishuman/check`
        + `?ppid=${encodeURIComponent(subject)}`
        + `&site_id=${encodeURIComponent(canonicalSiteId)}`
      );
      const fetchFn = fetchImpl || globalThis.fetch;
      if (typeof fetchFn !== "function") {
        return failClosed
          ? { available: false, decision: {}, reason: "site_policy_unavailable" }
          : { available: true, decision: {}, reason: "site_policy_unavailable" };
      }
      try {
        const controller = typeof AbortController === "function" ? new AbortController() : null;
        const timer = controller
          ? setTimeout(() => controller.abort(), Math.max(1, timeoutSeconds) * 1000)
          : null;
        const resp = await fetchFn(url, {
          method: "GET",
          headers: { "X-API-Key": apiKey },
          signal: controller?.signal,
        });
        if (timer) clearTimeout(timer);
        const payload = await resp.json();
        if (!payload?.success) {
          return failClosed
            ? { available: false, decision: {}, reason: "site_policy_unavailable" }
            : { available: true, decision: {}, reason: "site_policy_unavailable" };
        }
        const decision = {
          blocked: !!payload.blocked,
          doubtRequired: !!payload.doubt_required,
          reason: payload.reason || null,
          doubtReason: payload.doubt_reason || null,
        };
        cache.set(subject, { at: now, decision });
        return { available: true, decision, reason: "ok" };
      } catch {
        return failClosed
          ? { available: false, decision: {}, reason: "site_policy_unavailable" }
          : { available: true, decision: {}, reason: "site_policy_unavailable" };
      }
    },
  };
}

async function enforceSitePolicy({ ppid, legacyPpid, policyStore, requirePolicy = true }) {
  if (!policyStore) {
    return requirePolicy
      ? { ok: false, reason: "site_policy_not_configured" }
      : { ok: true, reason: "ok" };
  }
  for (const candidate of [ppid, legacyPpid]) {
    if (!candidate) continue;
    const { available, decision } = await policyStore.check(candidate);
    if (!available) return { ok: false, reason: "site_policy_unavailable" };
    if (decision.blocked) return { ok: false, reason: "site_blocked" };
    if (decision.doubtRequired || decision.doubt_required) {
      return { ok: false, reason: "doubt_required" };
    }
  }
  return { ok: true, reason: "ok" };
}

function buildSessionPresentationMessage(assertion) {
  return new TextEncoder().encode([
    SESSION_PRESENTATION_PREFIX,
    String(assertion.session_id || "").trim(),
    String(assertion.site_id || "").trim(),
    String(assertion.credential_id || "").trim(),
    String(assertion.subject || "").trim(),
    String(assertion.session_nonce || "").trim(),
    String(assertion.bloom_sequence ?? ""),
    String(assertion.issued_at_unix ?? ""),
    String(assertion.expires_at_unix ?? ""),
  ].join("\n"));
}

function canonicalJsonStringify(value) {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJsonStringify(item)).join(",")}]`;
  }
  const keys = Object.keys(value).sort();
  return `{${keys.map((key) => `${JSON.stringify(key)}:${canonicalJsonStringify(value[key])}`).join(",")}}`;
}

export async function hashActionBody(body) {
  const canonical = canonicalJsonStringify(body ?? {});
  const digest = await sha256Bytes(new TextEncoder().encode(canonical));
  return bytesToHex(digest);
}

export async function buildActionCommitment({
  serverNonce,
  siteId,
  action,
  method = "POST",
  path = "",
  bodyHash = "",
}) {
  const lines = [
    ACTION_COMMITMENT_PREFIX,
    String(serverNonce || "").trim(),
    String(siteId || "").trim(),
    String(action || "").trim(),
    String(method || "POST").trim().toUpperCase(),
    String(path || "").trim(),
    String(bodyHash || "").trim().toLowerCase(),
  ];
  const digest = await sha256Bytes(new TextEncoder().encode(lines.join("\n")));
  return bytesToHex(digest);
}

function buildFreshPasskeyCanonicalMessage(artifact) {
  return new TextEncoder().encode([
    FRESH_PASSKEY_PREFIX,
    String(artifact.schema || FRESH_PASSKEY_SCHEMA).trim(),
    String(artifact.site_id || "").trim(),
    String(artifact.credential_id || "").trim(),
    String(artifact.subject || "").trim(),
    String(artifact.action_commitment || "").trim().toLowerCase(),
    String(artifact.attestation_id || "").trim(),
    String(artifact.issued_at_unix ?? ""),
    String(artifact.expires_at_unix ?? ""),
  ].join("\n"));
}

export async function verifyFreshPasskeyAttestation(
  attestation,
  {
    siteId,
    credentialId,
    subject,
    actionCommitment,
    trustedIssuerPubkeys = [],
    nowUnix = Math.floor(Date.now() / 1000),
    maxAgeSeconds = DEFAULT_FRESH_PASSKEY_MAX_AGE_S,
  },
) {
  if (!attestation || typeof attestation !== "object") {
    return { ok: false, reason: "fresh_passkey_missing" };
  }
  if (String(attestation.schema || "") !== FRESH_PASSKEY_SCHEMA) {
    return { ok: false, reason: "fresh_passkey_schema_mismatch" };
  }
  if (String(attestation.site_id || "").trim() !== String(siteId || "").trim()) {
    return { ok: false, reason: "fresh_passkey_site_mismatch" };
  }
  if (String(attestation.credential_id || "").trim() !== String(credentialId || "").trim()) {
    return { ok: false, reason: "fresh_passkey_credential_mismatch" };
  }
  if (String(attestation.subject || "").trim() !== String(subject || "").trim()) {
    return { ok: false, reason: "fresh_passkey_subject_mismatch" };
  }
  const expectedCommitment = String(actionCommitment || "").trim().toLowerCase();
  if (expectedCommitment && String(attestation.action_commitment || "").trim().toLowerCase() !== expectedCommitment) {
    return { ok: false, reason: "fresh_passkey_commitment_mismatch" };
  }
  const issuedAt = Number(attestation.issued_at_unix || 0);
  const expiresAt = Number(attestation.expires_at_unix || 0);
  const now = Number(nowUnix || Math.floor(Date.now() / 1000));
  if (!issuedAt || !expiresAt || expiresAt < now) {
    return { ok: false, reason: "fresh_passkey_expired" };
  }
  if (issuedAt > now + 300) {
    return { ok: false, reason: "fresh_passkey_issued_in_future" };
  }
  if (now - issuedAt > Math.max(1, Number(maxAgeSeconds || DEFAULT_FRESH_PASSKEY_MAX_AGE_S))) {
    return { ok: false, reason: "fresh_passkey_too_old" };
  }
  const signatureHex = String(attestation?.proof?.signatureValueWeb || "").trim();
  if (!signatureHex) return { ok: false, reason: "fresh_passkey_signature_missing" };
  const unsigned = {
    schema: attestation.schema,
    attestation_id: attestation.attestation_id,
    site_id: attestation.site_id,
    credential_id: attestation.credential_id,
    subject: attestation.subject,
    action_commitment: attestation.action_commitment,
    issued_at_unix: attestation.issued_at_unix,
    expires_at_unix: attestation.expires_at_unix,
  };
  const digest = await sha256Bytes(buildFreshPasskeyCanonicalMessage(unsigned));
  const signature = hexToBytes(signatureHex);
  for (const pubkeyHex of trustedIssuerPubkeys) {
    if (await verifyEd25519(hexToBytes(pubkeyHex), digest, signature)) {
      return { ok: true, reason: "valid" };
    }
  }
  return { ok: false, reason: "fresh_passkey_invalid_signature" };
}

function buildActionPresentationMessage(assertion) {
  return new TextEncoder().encode([
    ACTION_PRESENTATION_PREFIX,
    String(assertion.version || ACTION_STAMP_VERSION).trim(),
    String(assertion.site_id || "").trim(),
    String(assertion.credential_id || "").trim(),
    String(assertion.subject || "").trim(),
    String(assertion.assurance || "").trim(),
    String(assertion.action || "").trim(),
    String(assertion.method || "POST").trim().toUpperCase(),
    String(assertion.path || "").trim(),
    String(assertion.body_hash || "").trim(),
    String(assertion.nonce || "").trim(),
    String(assertion.issued_at_unix ?? ""),
    String(assertion.expires_at_unix ?? ""),
  ].join("\n"));
}

async function verifySiteEd25519Digest(pubkeyBytes, signatureBytes, messageBytes) {
  const digest = await sha256Bytes(messageBytes);
  return verifyEd25519(pubkeyBytes, digest, signatureBytes);
}

export class InMemoryNonceStore {
  constructor() {
    this._seen = new Set();
  }

  consume(nonce, { siteId = "", ttlSeconds = 300 } = {}) {
    void siteId;
    void ttlSeconds;
    const text = String(nonce || "").trim();
    if (!text || this._seen.has(text)) return false;
    this._seen.add(text);
    return true;
  }
}

export class RedisNonceStore {
  constructor(redisClient = null, { keyPrefix = "lemma:action-nonce" } = {}) {
    this._redis = redisClient;
    this._keyPrefix = String(keyPrefix || "lemma:action-nonce").replace(/:+$/g, "");
  }

  _client() {
    return this._redis;
  }

  consume(nonce, { siteId = "", ttlSeconds = 300 } = {}) {
    const client = this._client();
    if (!client || typeof client.set !== "function") return false;
    const text = String(nonce || "").trim();
    if (!text) return false;
    const site = String(siteId || "global").trim() || "global";
    const key = `${this._keyPrefix}:${site}:${text}`;
    const ttl = Math.max(1, Number(ttlSeconds || 300));
    try {
      return Boolean(client.set(key, "1", { NX: true, EX: ttl }));
    } catch (_err) {
      return false;
    }
  }
}

// ---------------------------------------------------------------------------
// Cached signed bundle (trust list + Bloom snapshot) refresh
// ---------------------------------------------------------------------------

async function verifyTrustList(trustList, networkRootPubkeys) {
  if (!trustList || typeof trustList !== "object") {
    throw new Error("trust_list_missing");
  }
  const required = [
    "version",
    "generated_at_unix",
    "valid_until_unix",
    "content_hash",
    "signer_pubkey",
    "signature",
    "issuers",
  ];
  for (const key of required) {
    if (trustList[key] === undefined || trustList[key] === null || trustList[key] === "") {
      throw new Error(`trust_list_${key}_missing`);
    }
  }
  if (!signerPubkeyIsPinned(trustList.signer_pubkey, networkRootPubkeys)) {
    throw new Error("trust_list_signer_not_pinned");
  }

  const nowSec = Math.floor(Date.now() / 1000);
  if (nowSec + TIME_SKEW_SECONDS < Number(trustList.generated_at_unix)) {
    throw new Error("trust_list_not_yet_valid");
  }
  if (nowSec - TIME_SKEW_SECONDS > Number(trustList.valid_until_unix)) {
    throw new Error("trust_list_expired");
  }
  if (!Array.isArray(trustList.issuers) || trustList.issuers.length === 0) {
    throw new Error("trust_list_issuers_missing");
  }

  const expectedHash = await computeTrustListContentHash(trustList.issuers);
  if (expectedHash !== String(trustList.content_hash || "")) {
    throw new Error("trust_list_content_hash_mismatch");
  }

  const trustValid = await verifyEd25519(
    hexToBytes(String(trustList.signer_pubkey || "").toLowerCase()),
    await sha256Bytes(buildTrustListSignatureMessage(trustList)),
    base64urlToBytes(String(trustList.signature || "")),
  );
  if (!trustValid) throw new Error("trust_list_invalid_signature");

  const issuers = new Map();
  for (const row of trustList.issuers) {
    const did = normalizeDid(row?.did || row?.issuer_did || "");
    const pubkey = String(row?.pubkey || row?.public_key || row?.publicKey || "").trim().toLowerCase();
    const status = String(row?.status || "active").toLowerCase();
    const validFrom = Number(row?.valid_from_unix || 0);
    const validUntil = Number(row?.valid_until_unix || 0);
    if (!did || pubkey.length !== 64 || !/^[0-9a-f]+$/.test(pubkey)) continue;
    if (status === "revoked") continue;
    if (validFrom && (nowSec + TIME_SKEW_SECONDS) < validFrom) continue;
    if (validUntil && (nowSec - TIME_SKEW_SECONDS) > validUntil) continue;
    if (!issuers.has(did)) issuers.set(did, new Set());
    issuers.get(did).add(pubkey);
  }
  if (!issuers.size) throw new Error("trust_list_no_active_issuers");
  return issuers;
}

async function verifyBloomSnapshot(snapshot, hashedRevokedIds, trustedIssuers) {
  if (!snapshot || typeof snapshot !== "object") {
    throw new Error("bloom_snapshot_missing");
  }
  const required = ["sequence_number", "generated_at_unix", "valid_until_unix", "content_hash", "signature"];
  for (const key of required) {
    if (snapshot[key] === undefined || snapshot[key] === null || snapshot[key] === "") {
      throw new Error(`bloom_snapshot_${key}_missing`);
    }
  }

  const nowSec = Math.floor(Date.now() / 1000);
  const generatedAt = Number(snapshot.generated_at_unix);
  const validUntil = Number(snapshot.valid_until_unix);
  const maxStale = Number(snapshot.max_staleness_seconds || DEFAULT_MAX_BLOOM_STALENESS_SECONDS);
  if (nowSec + TIME_SKEW_SECONDS < generatedAt) throw new Error("bloom_snapshot_not_yet_valid");
  if (nowSec - TIME_SKEW_SECONDS > validUntil) throw new Error("bloom_snapshot_expired");
  if (nowSec - generatedAt > maxStale + TIME_SKEW_SECONDS) throw new Error("bloom_snapshot_stale");

  const canonicalBody = JSON.stringify({
    count: hashedRevokedIds.length,
    hashed_revoked_ids: hashedRevokedIds,
  });
  const expectedHash = await sha256HexText(canonicalBody);
  if (expectedHash !== String(snapshot.content_hash || "")) {
    throw new Error("bloom_snapshot_content_hash_mismatch");
  }
  if (snapshot.count === undefined || snapshot.count === null) {
    throw new Error("bloom_snapshot_count_missing");
  }
  if (Number(snapshot.count) !== hashedRevokedIds.length) {
    throw new Error("bloom_snapshot_count_mismatch");
  }

  const pubHex = parseIssuerPubkeyHex(snapshot);
  if (!pubHex) throw new Error("bloom_snapshot_issuer_pubkey_missing");
  const issuerDid = normalizeDid(snapshot.issuer_did || "");
  const trustedKeys = trustedIssuers?.get(issuerDid);
  if (!issuerDid || !trustedKeys || !trustedKeys.has(pubHex.toLowerCase())) {
    throw new Error("bloom_snapshot_issuer_untrusted");
  }

  const messageHash = await sha256Bytes(buildBloomSignatureMessage(snapshot));
  const valid = await verifyEd25519(
    hexToBytes(pubHex),
    messageHash,
    base64urlToBytes(String(snapshot.signature || "")),
  );
  if (!valid) throw new Error("bloom_snapshot_invalid_signature");
}

async function fetchSignedBundle(lemmaOrigin, fetchImpl, networkRootPubkeys) {
  const url = `${lemmaOrigin.replace(/\/$/, "")}/api/revocation/bloom-filter`;
  const res = await (fetchImpl || globalThis.fetch)(url);
  if (!res.ok) throw new Error(`bloom_fetch_${res.status}`);
  const data = await res.json();
  if (!data.success) throw new Error("bloom_fetch_failed");
  const issuers = await verifyTrustList(data.trust_list || {}, networkRootPubkeys);
  await verifyBloomSnapshot(data.snapshot || {}, data.hashed_revoked_ids || [], issuers);
  return {
    sequenceNumber: Number(data.snapshot?.sequence_number || 0),
    revokedHashSet: new Set(data.hashed_revoked_ids || []),
    validUntilUnix: Number(data.snapshot?.valid_until_unix || 0),
    fetchedAtMs: Date.now(),
    maxStalenessSeconds: Number(data.snapshot?.max_staleness_seconds || DEFAULT_MAX_BLOOM_STALENESS_SECONDS),
    issuers,
  };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * @param {object} options
 * @param {string} options.siteId                   Expected site_id binding.
 * @param {string} [options.lemmaOrigin]            Defaults to https://lemma.id.
 * @param {number} [options.refreshMs]              Snapshot refresh interval. Defaults to 15 min.
 * @param {number} [options.maxSessionAgeSeconds]   Reject session assertions older than this. Defaults to 24h.
 * @param {Function} [options.fetch]                Custom fetch impl (e.g. for Cloudflare Workers).
 * @returns {{ verify: (presentation: object) => Promise<VerifyResult>, refresh: () => Promise<void> }}
 */
export function createVerifier({
  siteId,
  lemmaOrigin = DEFAULT_LEMMA_ORIGIN,
  refreshMs = DEFAULT_REFRESH_MS,
  maxSessionAgeSeconds = DEFAULT_MAX_SESSION_AGE_S,
  requireSessionAssertion = false,
  requiredAssurance = "ishuman",
  maxActionAgeSeconds = DEFAULT_MAX_ACTION_AGE_S,
  nonceStoreMode = NONCE_STORE_MODE_OPTIONAL,
  freshPasskeyMaxAgeSeconds = DEFAULT_FRESH_PASSKEY_MAX_AGE_S,
  networkRootPubkeys = null,
  fetch: fetchImpl,
} = {}) {
  if (!siteId) throw new Error("siteId required");
  const canonicalSiteId = canonicalizeSiteHostname(siteId);
  let snapshot = null;
  let inflight = null;

  function credentialAssurance(claims) {
    return extractCredentialAssurance(claims);
  }

  async function ensureFresh() {
    const now = Date.now();
    const stale = !snapshot
      || now - snapshot.fetchedAtMs > Math.min(refreshMs, snapshot.maxStalenessSeconds * 1000);
    if (!stale) return snapshot;
    if (inflight) return inflight;
    inflight = fetchSignedBundle(lemmaOrigin, fetchImpl, networkRootPubkeys)
      .then((next) => {
        snapshot = next;
        return snapshot;
      })
      .finally(() => {
        inflight = null;
      });
    return inflight;
  }

  async function verify(presentation) {
    const credential = presentation && presentation.credential;
    if (!credential || typeof credential !== "object") {
      return { ok: false, reason: "credential_missing" };
    }
    const requiredErr = validateCredentialRequiredFields(credential);
    if (requiredErr) return { ok: false, reason: requiredErr };
    const proof = credential.proof || {};
    const sigHex = String(proof.signatureValueWeb || "").trim();

    const issuerDid = String(credential.issuer || "").trim();
    let bundle;
    try {
      bundle = await ensureFresh();
    } catch (err) {
      return { ok: false, reason: `trust_refresh_failed:${err.message}` };
    }
    const trustedKeys = bundle.issuers.get(issuerDid);
    if (!trustedKeys) return { ok: false, reason: "untrusted_issuer" };

    let credSigValid = false;
    try {
      const message = browserCanonicalMessage(credential);
      const digest = await sha256Bytes(message);
      const signature = hexToBytes(sigHex);
      for (const pubkeyHex of trustedKeys) {
        if (await verifyEd25519(hexToBytes(pubkeyHex), digest, signature)) {
          credSigValid = true;
          break;
        }
      }
    } catch (err) {
      return { ok: false, reason: `verify_error:${err.message}` };
    }
    if (!credSigValid) return { ok: false, reason: "invalid_signature" };

    const claims = credential.claims || credential.credentialSubject || {};
    const assurance = credentialAssurance(claims);
    if (!assurance) return { ok: false, reason: "not_ishuman" };
    if (assurance !== "passkey" && assurance !== "ishuman") {
      return { ok: false, reason: "invalid_assurance" };
    }
    if (!assuranceMeetsPolicy(assurance, requiredAssurance)) {
      return { ok: false, reason: "assurance_insufficient", assurance };
    }
    const boundSiteRaw = claims.siteId || claims.site_id || claims.siteDomain || "";
    const { canonical: boundSite, error: boundSiteErr } = tryCanonicalizeSiteHostname(boundSiteRaw);
    if (boundSiteErr || boundSite !== canonicalSiteId) {
      return { ok: false, reason: "site_id_mismatch", boundSiteId: boundSiteRaw };
    }
    const expiresAt = Number(claims.expiresAt || 0);
    if (expiresAt && expiresAt < Math.floor(Date.now() / 1000)) {
      return { ok: false, reason: "expired" };
    }

    const credentialId = credential.id || "";
    if (credentialId) {
      const idHashBytes = await sha256Bytes(new TextEncoder().encode(credentialId));
      const idHashHex = bytesToHex(idHashBytes);
      if (bundle.revokedHashSet.has(idHashHex)) {
        return { ok: false, reason: "revoked", credentialId };
      }
    }

    const assertion = presentation.session_assertion;
    const sigB64 = presentation.session_signature;
    const sitePubkeyB64 = claims.site_signing_pubkey || claims.siteSigningPubkey || "";
    if (assertion && sigB64) {
      if (!sitePubkeyB64) {
        return { ok: false, reason: "credential_missing_site_signing_pubkey" };
      }
      try {
        const pubkey = base64urlToBytes(sitePubkeyB64);
        const sigBytes = base64urlToBytes(sigB64);
        const msg = buildSessionPresentationMessage(assertion);
        const ok = await verifySiteEd25519Digest(pubkey, sigBytes, msg);
        if (!ok) return { ok: false, reason: "invalid_session_signature" };
      } catch (err) {
        return { ok: false, reason: `session_verify_error:${err.message}` };
      }
      const nowSec = Math.floor(Date.now() / 1000);
      const expiresAtSec = Number(assertion.expires_at_unix || 0);
      if (expiresAtSec && expiresAtSec < nowSec) {
        return { ok: false, reason: "session_expired" };
      }
      const issuedAtSec = Number(assertion.issued_at_unix || 0);
      if (issuedAtSec && nowSec - issuedAtSec > maxSessionAgeSeconds) {
        return { ok: false, reason: "session_too_old" };
      }
      const { canonical: sessionSite, error: sessionSiteErr } = tryCanonicalizeSiteHostname(
        assertion.site_id || "",
      );
      if (sessionSiteErr || sessionSite !== canonicalSiteId) {
        return { ok: false, reason: "session_site_id_mismatch" };
      }
    } else if (requireSessionAssertion && sitePubkeyB64) {
      return { ok: false, reason: "session_assertion_required" };
    }

    let legacyPpid = null;
    const convergence = presentation.ppid_convergence;
    if (convergence) {
      const trustedPubkeys = flattenTrustedIssuerPubkeys(bundle.issuers);
      const conv = await verifyPpidConvergenceArtifact(convergence, {
        siteId: canonicalSiteId,
        canonicalPpid: credential.subject || "",
        trustedIssuerPubkeys: trustedPubkeys,
      });
      if (!conv.ok) return conv;
      legacyPpid = conv.legacyPpid || null;
    }

    return {
      ok: true,
      reason: "valid",
      ppid: credential.subject || null,
      credentialId: credentialId || null,
      issuerDid,
      boundSiteId: boundSite,
      assurance,
      legacyPpid,
    };
  }

  async function verifyWithPolicy(presentation, { policyStore = null, requirePolicy = true } = {}) {
    const result = await verify(presentation);
    if (!result.ok) return result;
    const policy = await enforceSitePolicy({
      ppid: result.ppid,
      legacyPpid: result.legacyPpid,
      policyStore,
      requirePolicy,
    });
    if (!policy.ok) return { ...result, ok: false, reason: policy.reason };
    return result;
  }

  async function verifyStamp(stamp, { key = "lemma", durable = false } = {}) {
    const unwrapped = unwrapStamp(stamp, key);
    if (!unwrapped) return { ok: false, reason: "stamp_missing_proof" };
    const { stamp: inner, presentation } = unwrapped;
    const hasSession = !!(presentation.session_assertion && presentation.session_signature);
    const toVerify = (durable || !hasSession)
      ? { credential: presentation.credential }
      : presentation;
    const result = await verify(toVerify);
    if (!result.ok) return result;
    // Bind the loggable fields to the cryptographically verified values so a
    // tampered log row can't claim a different identity than the proof supports.
    if (inner) {
      if (inner.ppid && result.ppid && inner.ppid !== result.ppid) {
        return {
          ok: false,
          reason: "stamp_ppid_mismatch",
          ppid: result.ppid,
          stampedPpid: inner.ppid,
        };
      }
      if (
        inner.credentialId && result.credentialId
        && inner.credentialId !== result.credentialId
      ) {
        return { ok: false, reason: "stamp_credential_mismatch", credentialId: result.credentialId };
      }
    }
    return result;
  }

  async function verifyActionStamp(
    stampedEvent,
    {
      action,
      method = "POST",
      path = "",
      body = null,
      requiredAssurance: actionAssurance,
      nonceStore = null,
      nonceStoreMode: actionNonceStoreMode,
      requireFreshPasskey = false,
      serverNonce = "",
      key = "lemma",
    } = {},
  ) {
    const inner = unwrapActionStamp(stampedEvent, key);
    if (!inner) return { ok: false, reason: "action_stamp_missing" };

    const credential = inner.credential;
    const assertion = inner.action_assertion;
    const signatureB64 = String(inner.action_signature || "").trim();
    if (!credential || !assertion || !signatureB64) {
      return { ok: false, reason: "action_stamp_incomplete" };
    }

    const credResult = await verify({ credential });
    if (!credResult.ok) return credResult;

    const policy = String(actionAssurance || requiredAssurance || "ishuman").toLowerCase();
    if (!assuranceMeetsPolicy(credResult.assurance, policy)) {
      return { ok: false, reason: "assurance_insufficient", assurance: credResult.assurance };
    }

    const expectedBodyHash = await hashActionBody(body);
    const stampedHash = String(
      inner.bodyHash || inner.body_hash || assertion.body_hash || "",
    ).trim();
    if (stampedHash && stampedHash !== expectedBodyHash) {
      return { ok: false, reason: "action_body_hash_mismatch" };
    }

    if (String(assertion.action || "").trim() !== String(action || "").trim()) {
      return { ok: false, reason: "action_name_mismatch" };
    }
    if (String(assertion.method || "POST").trim().toUpperCase() !== String(method || "POST").trim().toUpperCase()) {
      return { ok: false, reason: "action_method_mismatch" };
    }
    if (String(assertion.path || "").trim() !== String(path || "").trim()) {
      return { ok: false, reason: "action_path_mismatch" };
    }
    const { canonical: actionSite, error: actionSiteErr } = tryCanonicalizeSiteHostname(
      assertion.site_id || "",
    );
    if (actionSiteErr || actionSite !== canonicalSiteId) {
      return { ok: false, reason: "action_site_id_mismatch" };
    }

    const nowSec = Math.floor(Date.now() / 1000);
    const expiresAtSec = Number(assertion.expires_at_unix || 0);
    const issuedAtSec = Number(assertion.issued_at_unix || 0);
    if (expiresAtSec && nowSec >= expiresAtSec) {
      return { ok: false, reason: "action_expired" };
    }
    if (issuedAtSec && nowSec - issuedAtSec > maxActionAgeSeconds) {
      return { ok: false, reason: "action_too_old" };
    }

    const nonce = String(assertion.nonce || inner.nonce || "").trim();
    if (!nonce) return { ok: false, reason: "action_nonce_missing" };
    const mode = String(actionNonceStoreMode || nonceStoreMode || NONCE_STORE_MODE_OPTIONAL).toLowerCase();
    if (mode === NONCE_STORE_MODE_REQUIRED && !nonceStore) {
      return { ok: false, reason: "action_nonce_store_required" };
    }
    if (nonceStore && typeof nonceStore.consume === "function") {
      const consumed = nonceStore.consume(nonce, {
        siteId: canonicalSiteId,
        ttlSeconds: maxActionAgeSeconds + 300,
      });
      if (!consumed) return { ok: false, reason: "action_nonce_reused" };
    }

    if (requireFreshPasskey) {
      const attestation = inner.fresh_passkey_attestation;
      if (!attestation || typeof attestation !== "object") {
        return { ok: false, reason: "fresh_passkey_missing" };
      }
      if (!serverNonce) return { ok: false, reason: "fresh_passkey_server_nonce_missing" };
      const actionCommitment = await buildActionCommitment({
        serverNonce,
        siteId: canonicalSiteId,
        action,
        method,
        path,
        bodyHash: expectedBodyHash,
      });
      const bundle = await ensureFresh();
      const trustedPubkeys = [];
      for (const pubkeys of bundle.issuers.values()) {
        for (const pubkeyHex of pubkeys) trustedPubkeys.push(pubkeyHex);
      }
      const fp = await verifyFreshPasskeyAttestation(attestation, {
        siteId: canonicalSiteId,
        credentialId: String(credential.id || credResult.credentialId || ""),
        subject: String(credential.subject || credResult.ppid || ""),
        actionCommitment,
        trustedIssuerPubkeys: trustedPubkeys,
        maxAgeSeconds: freshPasskeyMaxAgeSeconds,
      });
      if (!fp.ok) return fp;
    }

    const claims = credential.claims || credential.credentialSubject || {};
    const sitePubkeyB64 = claims.site_signing_pubkey || claims.siteSigningPubkey || "";
    if (!sitePubkeyB64) {
      return { ok: false, reason: "credential_missing_site_signing_pubkey" };
    }

    if (inner.ppid && credResult.ppid && inner.ppid !== credResult.ppid) {
      return { ok: false, reason: "stamp_ppid_mismatch", ppid: credResult.ppid };
    }
    if (
      inner.credentialId && credResult.credentialId
      && inner.credentialId !== credResult.credentialId
    ) {
      return { ok: false, reason: "stamp_credential_mismatch", credentialId: credResult.credentialId };
    }

    try {
      const ok = await verifySiteEd25519Digest(
        base64urlToBytes(sitePubkeyB64),
        base64urlToBytes(signatureB64),
        buildActionPresentationMessage(assertion),
      );
      if (!ok) return { ok: false, reason: "invalid_action_signature" };
    } catch (err) {
      return { ok: false, reason: `action_verify_error:${err.message}` };
    }

    return credResult;
  }

  async function refresh() {
    snapshot = null;
    await ensureFresh();
  }

  return { verify, verifyWithPolicy, verifyStamp, verifyActionStamp, refresh };
}

/** A bare verifiable credential has subject + claims + a proof object. */
function looksLikeVc(obj) {
  return (
    !!obj && typeof obj === "object"
    && typeof obj.subject !== "undefined"
    && typeof obj.claims !== "undefined"
    && !!obj.proof && typeof obj.proof === "object"
  );
}

function hasActionStampFields(obj) {
  return !!obj && typeof obj === "object" && (
    obj.version === ACTION_STAMP_VERSION
    || (obj.action_assertion && obj.action_signature)
  );
}

function unwrapActionStamp(input, key = "lemma") {
  if (!input || typeof input !== "object") return null;
  if (input[key] && hasActionStampFields(input[key])) return input[key];
  if (hasActionStampFields(input)) return input;
  return null;
}

/** Does this object carry the flat summary fields a stamp adds? */
function hasStampFields(obj) {
  return (
    typeof obj.ppid !== "undefined"
    || typeof obj.verified !== "undefined"
    || typeof obj.verifiedAt !== "undefined"
    || typeof obj.credentialId !== "undefined"
  );
}

/**
 * Normalize the many shapes a relying site might pass to verifyStamp into
 * `{ stamp, presentation }`. Accepts:
 *   - a bare verifiable credential (has `.subject` + `.claims`)
 *   - a raw presentation (has `.credential` + optional session assertion)
 *   - a stamp from `getVerification({ includeCredential: true })` (flat fields + `.credential`)
 *   - a stamp from `getVerification({ includeProof: true })` (flat fields + `.proof`)
 *   - a stamped event from `stamp(payload)` (has `[key]` with one of the above)
 * `stamp` is the flat-field object (used for tamper-binding) when present, else null.
 * @returns {{stamp: object|null, presentation: object}|null}
 */
function unwrapStamp(input, key = "lemma") {
  if (!input || typeof input !== "object") return null;

  // Stamped event: unwrap the [key] envelope first, but only if the top level
  // isn't itself a credential/presentation/stamp.
  if (
    !looksLikeVc(input)
    && !(input.proof && typeof input.proof === "object")
    && !(input.credential && typeof input.credential === "object")
    && input[key] && typeof input[key] === "object"
  ) {
    input = input[key];
  }

  // Bare VC -> wrap as a presentation; nothing to cross-check.
  if (looksLikeVc(input)) {
    return { stamp: null, presentation: { credential: input } };
  }

  // Stamp carrying a full session presentation under `proof`.
  if (input.proof && typeof input.proof === "object" && input.proof.credential) {
    return { stamp: input, presentation: input.proof };
  }

  // Object carrying a VC under `credential`: either a raw presentation
  // (no flat fields) or a VC-only stamp (flat fields present).
  if (input.credential && typeof input.credential === "object") {
    const isStamp = hasStampFields(input);
    const presentation = {
      credential: input.credential,
      session_assertion: input.session_assertion,
      session_signature: input.session_signature,
      session_nonce: input.session_nonce,
      bloom_sequence: input.bloom_sequence,
    };
    return { stamp: isStamp ? input : null, presentation };
  }

  return null;
}

/**
 * Convenience one-shot verify: creates a verifier, verifies once, discards.
 * Prefer createVerifier() for long-running servers so the snapshot is cached.
 */
export async function verifyWithPolicy(presentation, options) {
  return createVerifier(options).verifyWithPolicy(presentation, options);
}

export async function verifyPresentation(presentation, options) {
  return createVerifier(options).verify(presentation);
}

/**
 * One-shot verify of a stamp/credential produced by the browser SDK's
 * `stamp(payload, { includeCredential: true })` / `getVerification(...)`.
 * Accepts a bare VC, presentation, stamp, or stamped event. Pass
 * `{ durable: true }` to re-verify old log rows without session-freshness.
 * Prefer `createVerifier().verifyStamp()` for long-running servers so the
 * signed snapshot is cached across requests.
 */
export async function verifyStamp(stamp, options) {
  return createVerifier(options).verifyStamp(stamp, options);
}

export async function verifyActionStamp(stamp, options) {
  return createVerifier(options).verifyActionStamp(stamp, options);
}

// CommonJS interop for Node.js require()
if (typeof module !== "undefined" && typeof module.exports !== "undefined") {
  module.exports = {
    createVerifier,
    verifyPresentation,
    verifyWithPolicy,
    verifyStamp,
    verifyActionStamp,
    hashActionBody,
    buildActionCommitment,
    verifyFreshPasskeyAttestation,
    InMemoryNonceStore,
    RedisNonceStore,
    createInMemorySitePolicyStore,
    createLemmaCheckPolicyStore,
    canonicalizeSiteHostname,
    browserCanonicalMessage,
  };
}
