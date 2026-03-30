function decodeLemmaHeader(rawHeader) {
  if (!rawHeader || typeof rawHeader !== "string") return null;
  const text = rawHeader.trim();
  if (!text) return null;

  try {
    if (text.startsWith("{")) return JSON.parse(text);
    return JSON.parse(Buffer.from(text, "base64url").toString("utf8"));
  } catch (_err) {
    return null;
  }
}

function normalizeScope(scope) {
  if (!scope) return [];
  const items = Array.isArray(scope) ? scope : String(scope).split(",");
  const out = [];
  for (const value of items) {
    const token = String(value).trim().toLowerCase();
    if (token && !out.includes(token)) out.push(token);
  }
  return out;
}

function canonicalizeSite(value) {
  const text = (value || "").toString().trim().toLowerCase();
  if (!text) return null;

  let host = text;
  try {
    const parsed = new URL(text.includes("://") ? text : `https://${text}`);
    host = (parsed.hostname || "").toLowerCase();
  } catch (_err) {
    host = text;
  }

  host = host.split("/")[0].split(":")[0];
  if (host.startsWith("www.")) host = host.slice(4);
  host = host.replace(/\.+$/, "");
  return host || null;
}

function errorMessageFor(code) {
  const value = String(code || "").trim();
  if (!value) return "Authentication required";
  if (value === "auth_required") return "Authentication required";
  if (value === "missing_scope") return "Insufficient scope";
  if (value === "site_mismatch") return "Credential site binding mismatch";
  if (value === "AUTH_PROOF_REQUIRED") return "Proof-native authorization is required";
  if (value === "AUTH_MODE_DOWNGRADE") return "Authorization mode downgrade is not allowed";
  if (value === "AUTH_CHAIN_BROKEN") return "Proof chain validation failed";
  if (value === "AUTH_REPLAY_DETECTED") return "Replay detected";
  if (value === "AUTH_PROOF_OF_POSSESSION_FAILED") return "Proof-of-possession validation failed";
  if (value === "invalid_lemma_header") return "Invalid X-Lemma-Credential header";
  if (value.startsWith("invalid_lemma:")) return "Credential verification failed";
  return "Authentication required";
}

function errorPayload(code) {
  return {
    success: false,
    error: String(code || "auth_required"),
    message: errorMessageFor(code),
  };
}

function extractPrincipal(credential) {
  const claims = credential?.claims || credential?.credentialSubject || {};
  const ppid =
    credential?.subject ||
    credential?.sub ||
    claims?.ppid ||
    claims?.id ||
    claims?.subject;
  if (!ppid || !String(ppid).startsWith("did:lemma:ppid_")) return null;

  const scope = normalizeScope(claims.scope);
  return {
    ppid: String(ppid),
    credentialId: credential.id || null,
    permissionId:
      claims.permissionId ||
      claims.permission_id ||
      claims.permission_level ||
      claims.permission ||
      "read",
    scope: scope.length ? scope : ["read"],
    siteBinding: canonicalizeSite(
      claims.siteId || claims.site_id || claims.siteDomain || claims.site_domain || ""
    ),
    rawCredential: credential,
  };
}

function evaluateProofContract(proof, options = {}) {
  const requiredScope = String(options.requiredScope || "").trim().toLowerCase();
  const profile = String(proof?.profile || proof?.version || "authz_profile_v2");
  const out = {
    decision: "deny",
    reason_code: "AUTH_CHAIN_BROKEN",
    proof_id: proof?.proof_id || null,
    root_grant_id: proof?.root_grant_id || null,
    policy_version: proof?.policy_version || proof?.version || null,
    profile,
  };
  if (!proof || typeof proof !== "object") return out;
  const exp = Number(proof.expires_at || 0);
  if (Number.isFinite(exp) && exp > 0 && exp <= Math.floor(Date.now() / 1000)) return out;
  const scope = normalizeScope(proof.scope);
  if (requiredScope && !scope.includes(requiredScope)) return out;
  return { ...out, decision: "allow", reason_code: "OK" };
}

function createLemmaAuth(options = {}) {
  const verifyCredential = options.verifyCredential;
  const requiredSite = canonicalizeSite(options.requiredSite);

  if (typeof verifyCredential !== "function") {
    throw new Error("createLemmaAuth requires options.verifyCredential(credential)");
  }

  function attachPrincipal() {
    return async function lemmaAttachPrincipal(req, _res, next) {
      const credential = decodeLemmaHeader(req.header("X-Lemma-Credential"));
      if (!credential) {
        req.lemmaAuthError = "invalid_lemma_header";
        return next();
      }

      let verification = null;
      try {
        verification = await verifyCredential(credential);
      } catch (_err) {
        req.lemmaAuthError = "invalid_lemma:verification_error";
        return next();
      }

      if (!verification?.valid) {
        req.lemmaAuthError = `invalid_lemma:${verification?.reason || "verification_failed"}`;
        return next();
      }

      try {
        req.lemmaPrincipal = extractPrincipal(credential);
      } catch (_err) {
        req.lemmaPrincipal = null;
      }
      if (!req.lemmaPrincipal) req.lemmaAuthError = "invalid_lemma:missing_ppid";
      return next();
    };
  }

  function requireLemma({ scope = null, siteBound = false } = {}) {
    const requiredScope = scope ? String(scope).trim().toLowerCase() : null;

    return function lemmaRequireMiddleware(req, res, next) {
      if (!req.lemmaPrincipal) {
        return res.status(401).json(errorPayload(req.lemmaAuthError || "auth_required"));
      }

      if (requiredScope && !req.lemmaPrincipal.scope.includes(requiredScope)) {
        return res.status(403).json(errorPayload("missing_scope"));
      }

      if (siteBound && requiredSite && req.lemmaPrincipal.siteBinding !== requiredSite) {
        return res.status(403).json(errorPayload("site_mismatch"));
      }

      return next();
    };
  }

  return {
    attachPrincipal,
    requireLemma,
    decodeLemmaHeader,
    extractPrincipal,
  };
}

module.exports = {
  createLemmaAuth,
  evaluateProofContract,
  createFreshnessClient: require("./freshness").createFreshnessClient,
};

