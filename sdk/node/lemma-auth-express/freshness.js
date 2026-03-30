async function fetchJson(url, timeoutMs = 3000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { method: "GET", signal: controller.signal });
    if (!res.ok) return null;
    return await res.json();
  } catch (_err) {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

function createFreshnessClient(options = {}) {
  const baseUrl = String(options.baseUrl || "https://lemma.id").replace(/\/+$/, "");
  const failClosed = options.failClosed !== false;
  const maxStalenessSeconds = Number(options.maxStalenessSeconds || 30);
  const rootType = String(options.rootType || "passkey_root");
  const state = {
    jwksLastSyncEpoch: null,
    revocationLastSyncEpoch: null,
    policyLastSyncEpoch: null,
    revocationCursor: 0,
    policyVersion: null,
    rootType,
    failClosed,
    maxStalenessSeconds,
  };

  async function pollOnce() {
    const now = Date.now() / 1000;
    const [jwks, revocation, policy] = await Promise.all([
      fetchJson(`${baseUrl}/api/authz/jwks`, options.timeoutMs || 3000),
      fetchJson(`${baseUrl}/api/authz/revocation/delta?since=${state.revocationCursor}`, options.timeoutMs || 3000),
      fetchJson(
        `${baseUrl}/api/authz/policy/snapshot?version=${encodeURIComponent(state.policyVersion || "")}`,
        options.timeoutMs || 3000
      ),
    ]);
    if (jwks) state.jwksLastSyncEpoch = now;
    if (revocation) {
      state.revocationLastSyncEpoch = now;
      state.revocationCursor = Number(revocation.next_cursor || state.revocationCursor || 0);
    }
    if (policy) {
      state.policyLastSyncEpoch = now;
      state.policyVersion = policy?.policy?.policy_version || state.policyVersion;
    }
    return { ...state };
  }

  return {
    pollOnce,
    assertFreshOrThrow: () => {
      const now = Date.now() / 1000;
      const lastSync = Math.min(
        state.jwksLastSyncEpoch || 0,
        state.revocationLastSyncEpoch || 0,
        state.policyLastSyncEpoch || 0
      );
      const stale = !lastSync || now - lastSync > maxStalenessSeconds;
      if (failClosed && stale) {
        throw new Error(`lemma_freshness_stale:${rootType}`);
      }
      return { stale, state: { ...state } };
    },
    getState: () => ({ ...state }),
  };
}

module.exports = {
  createFreshnessClient,
};

