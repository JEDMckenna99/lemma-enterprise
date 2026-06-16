import * as ed from "/static/vendor/noble-ed25519.mjs";

function sortValue(value) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return Object.keys(value).sort().reduce((acc, key) => {
      acc[key] = sortValue(value[key]);
      return acc;
    }, {});
  }
  if (Array.isArray(value)) return value.map(sortValue);
  return value;
}

export function canonicalJsonBytes(payload, exclude = new Set(["signature"])) {
  const cleaned = {};
  Object.keys(payload).sort().forEach((key) => {
    if (!exclude.has(key)) cleaned[key] = payload[key];
  });
  return new TextEncoder().encode(JSON.stringify(sortValue(cleaned)));
}

export async function sha256Hex(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function hexToBytes(hex) {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i += 1) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

function b64urlEncode(bytes) {
  let str = "";
  bytes.forEach((b) => { str += String.fromCharCode(b); });
  return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function b64urlDecode(text) {
  const padded = text + "=".repeat((4 - (text.length % 4)) % 4);
  const raw = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

export async function verifySignedPayload(payload) {
  const message = await crypto.subtle.digest("SHA-256", canonicalJsonBytes(payload));
  const pub = b64urlDecode(payload.issuer_pubkey);
  const sig = b64urlDecode(payload.signature);
  return ed.verify(sig, new Uint8Array(message), pub);
}

export async function verifyRouteCredential(credential, deviceId) {
  if (!(await verifySignedPayload(credential))) return { ok: false, reason: "invalid_signature" };
  if (credential.credential_type !== "RouteCredential") return { ok: false, reason: "wrong_type" };
  if (deviceId && credential.device_id !== deviceId) return { ok: false, reason: "device_mismatch" };
  if (credential.expires_at && Date.now() > Date.parse(credential.expires_at)) {
    return { ok: false, reason: "expired" };
  }
  return { ok: true, reason: "ok" };
}

export async function verifyPackageAgainstRoute(assignment, routeCredential) {
  if (!(await verifySignedPayload(assignment))) return { ok: false, reason: "invalid_signature" };
  const routeMatch = assignment.route_id === routeCredential.route_id;
  const stopMatch = (routeCredential.stops || []).includes(assignment.stop_id);
  if (!routeMatch) return { ok: false, reason: "route_mismatch", routeMatch, stopMatch, policy: {} };
  if (!stopMatch) return { ok: false, reason: "stop_mismatch", routeMatch, stopMatch, policy: assignment.policy || {} };
  return { ok: true, reason: "ok", routeMatch, stopMatch, policy: assignment.policy || {} };
}

export async function chainHash(payload) {
  return sha256Hex(canonicalJsonBytes(payload, new Set()));
}

export async function signDeliveryEvent(event, devicePrivateKeyHex, routeCredential, priorEvent) {
  const privateKey = hexToBytes(devicePrivateKeyHex);
  const publicKey = await ed.getPublicKey(privateKey);
  const payload = { ...event };
  payload.device_pubkey = b64urlEncode(publicKey);
  payload.previous_event_hash = priorEvent ? await chainHash(priorEvent) : "genesis";
  const message = await crypto.subtle.digest("SHA-256", canonicalJsonBytes(payload));
  payload.signature = b64urlEncode(await ed.sign(new Uint8Array(message), privateKey));
  return payload;
}

export function policyLabel(policy) {
  const parts = [];
  if (policy.photo_required) parts.push("photo");
  if (policy.signature_required) parts.push("signature");
  if (policy.otp_required) parts.push("OTP");
  return parts.length ? parts.join(", ") : "none";
}

window.DeliveryCrypto = {
  verifySignedPayload,
  verifyRouteCredential,
  verifyPackageAgainstRoute,
  signDeliveryEvent,
  policyLabel,
};
