/**
 * @lemma/ishuman-verify — Local-first isHuman presentation verifier.
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
 *   // stamp(payload, { includeProof: true })) — re-checks the signed proof
 *   // AND that the stamp's logged ppid/credentialId match it:
 *   const check = await verifier.verifyStamp(storedLogRow.lemma);
 *   if (!check.ok) flagSuspiciousLogRow();
 *
 * @version 1.1.0
 */

const SESSION_PRESENTATION_PREFIX = "lemma:site-session-presentation:v1";
const DEFAULT_LEMMA_ORIGIN = "https://lemma.id";
const DEFAULT_REFRESH_MS = 15 * 60 * 1000;
const DEFAULT_MAX_SESSION_AGE_S = 24 * 60 * 60;

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
  if (credential.issuedAt !== undefined && credential.issuedAt !== null) {
    payload.issuedAt = credential.issuedAt;
  }
  if (credential.expiresAt !== undefined && credential.expiresAt !== null) {
    payload.expiresAt = credential.expiresAt;
  }
  return new TextEncoder().encode(JSON.stringify(payload));
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

// ---------------------------------------------------------------------------
// Cached signed bundle (trust list + Bloom snapshot) refresh
// ---------------------------------------------------------------------------

async function verifyTrustList(trustList) {
  // Minimal: extract active issuers. Production should also verify trustList
  // signature against a hard-coded network-root pubkey.
  const issuers = new Map();
  for (const entry of (trustList?.issuers || [])) {
    const did = String(entry.did || "").trim();
    const pubkeyHex = String(entry.public_key || entry.publicKey || "").trim().toLowerCase();
    const status = String(entry.status || "active").toLowerCase();
    if (!did || !pubkeyHex || status !== "active") continue;
    const existing = issuers.get(did);
    if (existing) existing.add(pubkeyHex);
    else issuers.set(did, new Set([pubkeyHex]));
  }
  if (issuers.size === 0) throw new Error("trust_list_empty");
  return issuers;
}

async function verifyBloomSnapshot(snapshot, hashedRevokedIds, issuers) {
  const expectedHash = await sha256Bytes(new TextEncoder().encode(
    JSON.stringify(
      { hashed_revoked_ids: hashedRevokedIds, count: hashedRevokedIds.length },
    ),
  ));
  // Note: Python uses sort_keys=True. JS keys are already in stable order
  // because the object only has two keys defined in this order. Match exactly.
  const expectedHex = bytesToHex(expectedHash);
  if (expectedHex !== snapshot.content_hash) {
    throw new Error("bloom_snapshot_content_hash_mismatch");
  }
  const issuerDid = String(snapshot.issuer_did || "").trim();
  const trusted = issuers.get(issuerDid);
  if (!trusted) throw new Error(`bloom_snapshot_untrusted_issuer:${issuerDid}`);
  const envelope = { ...snapshot };
  delete envelope.signature;
  const sortedKeys = Object.keys(envelope).sort();
  const envelopeSorted = {};
  for (const k of sortedKeys) envelopeSorted[k] = envelope[k];
  const message = new TextEncoder().encode(JSON.stringify(envelopeSorted));
  const signature = hexToBytes(snapshot.signature);
  for (const pubkeyHex of trusted) {
    if (await verifyEd25519(hexToBytes(pubkeyHex), message, signature)) return;
  }
  throw new Error("bloom_snapshot_invalid_signature");
}

async function fetchSignedBundle(lemmaOrigin, fetchImpl) {
  const url = `${lemmaOrigin.replace(/\/$/, "")}/api/revocation/bloom-filter`;
  const res = await (fetchImpl || globalThis.fetch)(url);
  if (!res.ok) throw new Error(`bloom_fetch_${res.status}`);
  const data = await res.json();
  if (!data.success) throw new Error("bloom_fetch_failed");
  const issuers = await verifyTrustList(data.trust_list || {});
  await verifyBloomSnapshot(data.snapshot || {}, data.hashed_revoked_ids || [], issuers);
  return {
    sequenceNumber: Number(data.snapshot?.sequence_number || 0),
    revokedHashSet: new Set(data.hashed_revoked_ids || []),
    validUntilUnix: Number(data.snapshot?.valid_until_unix || 0),
    fetchedAtMs: Date.now(),
    maxStalenessSeconds: Number(data.snapshot?.max_staleness_seconds || 900),
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
  fetch: fetchImpl,
} = {}) {
  if (!siteId) throw new Error("siteId required");
  let snapshot = null;
  let inflight = null;

  async function ensureFresh() {
    const now = Date.now();
    const stale = !snapshot
      || now - snapshot.fetchedAtMs > Math.min(refreshMs, snapshot.maxStalenessSeconds * 1000);
    if (!stale) return snapshot;
    if (inflight) return inflight;
    inflight = fetchSignedBundle(lemmaOrigin, fetchImpl)
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
    const proof = credential.proof || {};
    const sigHex = String(proof.signatureValueWeb || "").trim();
    if (!sigHex) return { ok: false, reason: "browser_signature_missing" };

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
    if (!claims.isHuman) return { ok: false, reason: "not_ishuman" };
    const boundSite = claims.siteId || claims.site_id || claims.siteDomain || "";
    if (boundSite !== siteId) {
      return { ok: false, reason: "site_id_mismatch", boundSiteId: boundSite };
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
    if (assertion && sigB64) {
      const sitePubkeyB64 = claims.site_signing_pubkey || claims.siteSigningPubkey || "";
      if (!sitePubkeyB64) {
        return { ok: false, reason: "credential_missing_site_signing_pubkey" };
      }
      try {
        const pubkey = base64urlToBytes(sitePubkeyB64);
        const sigBytes = base64urlToBytes(sigB64);
        const msg = buildSessionPresentationMessage(assertion);
        const ok = await verifyEd25519(pubkey, msg, sigBytes);
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
      if (String(assertion.site_id || "") !== siteId) {
        return { ok: false, reason: "session_site_id_mismatch" };
      }
    }

    return {
      ok: true,
      reason: "valid",
      ppid: credential.subject || null,
      credentialId: credentialId || null,
      issuerDid,
      boundSiteId: boundSite,
    };
  }

  async function verifyStamp(stamp, { key = "lemma" } = {}) {
    const unwrapped = unwrapStamp(stamp, key);
    if (!unwrapped) return { ok: false, reason: "stamp_missing_proof" };
    const { stamp: inner, presentation } = unwrapped;
    const result = await verify(presentation);
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

  async function refresh() {
    snapshot = null;
    await ensureFresh();
  }

  return { verify, verifyStamp, refresh };
}

/**
 * Normalize the many shapes a relying site might pass to verifyStamp into
 * `{ stamp, presentation }`. Accepts:
 *   - a raw presentation (has `.credential`)
 *   - a stamp object from `getVerification({ includeProof: true })` (has `.proof`)
 *   - a stamped event from `stamp(payload)` (has `[key]` with one of the above)
 * @returns {{stamp: object|null, presentation: object}|null}
 */
function unwrapStamp(input, key = "lemma") {
  if (!input || typeof input !== "object") return null;
  if (input.credential && typeof input.credential === "object") {
    return { stamp: null, presentation: input };
  }
  if (input.proof && typeof input.proof === "object") {
    return { stamp: input, presentation: input.proof };
  }
  const inner = input[key];
  if (inner && typeof inner === "object") {
    if (inner.proof && typeof inner.proof === "object") {
      return { stamp: inner, presentation: inner.proof };
    }
    if (inner.credential && typeof inner.credential === "object") {
      return { stamp: inner, presentation: inner };
    }
  }
  return null;
}

/**
 * Convenience one-shot verify: creates a verifier, verifies once, discards.
 * Prefer createVerifier() for long-running servers so the snapshot is cached.
 */
export async function verifyPresentation(presentation, options) {
  return createVerifier(options).verify(presentation);
}

/**
 * One-shot verify of a stamp produced by the browser SDK's
 * `stamp(payload, { includeProof: true })` or `getVerification({ includeProof: true })`.
 * Prefer `createVerifier().verifyStamp()` for long-running servers so the
 * signed snapshot is cached across requests.
 */
export async function verifyStamp(stamp, options) {
  return createVerifier(options).verifyStamp(stamp, options);
}

// CommonJS interop for Node.js require()
if (typeof module !== "undefined" && typeof module.exports !== "undefined") {
  module.exports = {
    createVerifier,
    verifyPresentation,
    verifyStamp,
    browserCanonicalMessage,
  };
}
