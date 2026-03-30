(function () {
  "use strict";

  var state = {
    runtimeId: null,
    issuerId: null,
    siteId: null,
    runtimeState: { taint_epoch: 0, trust_state: "trusted" },
    activeProof: null,
  };

  async function requestJson(url, options) {
    var response = await fetch(url, options || {});
    var text = await response.text();
    var data = null;
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {
      data = null;
    }
    if (!response.ok) {
      var message =
        (data && (data.error_code || data.error || data.message))
          ? (data.error_code || data.error || data.message)
          : ("request_failed_" + response.status);
      if (!data && response.status >= 500) message = "demo_service_unavailable";
      if (response.status === 401) message = "demo_service_unauthorized";
      if (!data && !text) message = "empty_error_response";
      throw new Error(message);
    }
    if (data === null) {
      throw new Error("invalid_json_response");
    }
    return data;
  }

  function highlightJson(payload) {
    var json = JSON.stringify(payload || {}, null, 2);
    return json
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"([^"]+)":/g, '<span class="k">"$1"</span>:')
      .replace(/: "([^"]*)"/g, ': <span class="s">"$1"</span>')
      .replace(/: (true|false)/g, ': <span class="b">$1</span>')
      .replace(/: (-?\d+(\.\d+)?)/g, ': <span class="n">$1</span>');
  }

  function setProofView(payload) {
    var el = document.getElementById("demo-proof-json");
    if (el) {
      el.innerHTML = highlightJson(payload || {});
    }
  }

  function setTrustBadge() {
    var badge = document.getElementById("demo-trust-badge");
    if (!badge) return;
    var trust = String(state.runtimeState.trust_state || "trusted").toLowerCase();
    badge.classList.remove("trusted", "tainted", "revoked");
    if (trust !== "trusted" && trust !== "tainted" && trust !== "revoked") trust = "trusted";
    badge.classList.add(trust);
    var labels = {
      trusted: "PROOF VALID",
      tainted: "RUNTIME TAINTED",
      revoked: "PROOF REVOKED",
    };
    badge.textContent = labels[trust] || "PROOF VALID";
  }

  function setRuntimeView() {
    var rid = document.getElementById("demo-runtime-id");
    var issuer = document.getElementById("demo-issuer-id");
    var site = document.getElementById("demo-site-id");
    var status = document.getElementById("demo-runtime-status");
    if (rid) rid.textContent = state.runtimeId || "-";
    if (issuer) issuer.textContent = state.issuerId || "-";
    if (site) site.textContent = state.siteId || "-";
    if (status) {
      status.textContent =
        "Runtime trust_state=" + state.runtimeState.trust_state +
        " taint_epoch=" + state.runtimeState.taint_epoch;
    }
    setTrustBadge();
  }

  async function loadState() {
    var payload = await requestJson("/api/demo/state?runtime_id=" + encodeURIComponent(state.runtimeId));
    state.runtimeState = payload.runtime_state || state.runtimeState;
    state.issuerId = payload.issuer_id || state.issuerId;
    state.siteId = payload.site_id || state.siteId;
    setRuntimeView();
    return payload;
  }

  async function issueProof() {
    var profileWrap = document.getElementById("demo-policy-profile");
    var activePill = profileWrap ? profileWrap.querySelector(".demo-policy-pill.active") : null;
    var profile = activePill ? String(activePill.getAttribute("data-profile") || "low") : "low";
    var payload = await requestJson("/api/demo/issue-credential", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        runtime_id: state.runtimeId,
        scope: ["read", "write"],
        taint_epoch: state.runtimeState.taint_epoch,
        trust_state: state.runtimeState.trust_state,
        ttl_hours: 1,
      }),
    });
    var credential = payload.credential || {};
    var claims = credential.credentialSubject || {};
    state.activeProof = {
      jti: credential.id || payload.runtime_id,
      token: JSON.stringify(credential),
      scope: (claims.scope || "read,write").split(","),
      expires_at: claims.expiresAt,
      taint_epoch: state.runtimeState.taint_epoch,
    };
    setProofView({
      proof: state.activeProof,
      runtime_id: payload.runtime_id,
      selected_actions: ["file.read", "file.write", "api.call.read", "api.call.write"],
    });
    if (window.DemoTimeline) {
      window.DemoTimeline.push({ label: "t1 issue", decision: "allow", reason_code: "proof_issued" });
    }
    return payload;
  }

  async function revokeProof() {
    if (!state.activeProof || !state.activeProof.jti) {
      throw new Error("issue a credential first");
    }
    state.activeProof.revoked = true;
    if (window.DemoTimeline) {
      window.DemoTimeline.push({ label: "t7 revoke", decision: "deny", reason_code: "token_revoked" });
    }
    return { success: true, event: "credential_revoked" };
  }

  async function refreshRevocation() {
    if (!state.activeProof || !state.activeProof.jti) {
      throw new Error("issue a credential first");
    }
    return requestJson("/api/demo/revocation-status?jti=" + encodeURIComponent(state.activeProof.jti));
  }

  async function bumpTaint() {
    var payload = await requestJson("/api/demo/taint-bump", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ runtime_id: state.runtimeId, trust_state: "tainted" }),
    });
    state.runtimeState = payload.runtime_state || state.runtimeState;
    setRuntimeView();
    if (window.DemoTimeline) {
      window.DemoTimeline.push({ label: "t5 taint", decision: "warn", reason_code: "taint_epoch_bumped" });
    }
    return payload;
  }

  window.DemoProofControls = {
    init: async function init(runtimeId) {
      state.runtimeId = runtimeId;
      await loadState();
      setProofView({});
      return state;
    },
    getState: function getState() {
      return state;
    },
    loadState: loadState,
    issueProof: issueProof,
    revokeProof: revokeProof,
    refreshRevocation: refreshRevocation,
    bumpTaint: bumpTaint,
    reset: async function reset() {
      state.runtimeState = { taint_epoch: 0, trust_state: "trusted" };
      state.activeProof = null;
      await loadState();
      setProofView({});
      return state;
    },
    setTrustStateBadge: function setTrustStateBadge(kind) {
      if (!kind) return;
      state.runtimeState.trust_state = kind;
      setTrustBadge();
    },
    applySnapshot: function applySnapshot(snapshot) {
      if (!snapshot) return;
      if (typeof snapshot.taint_epoch !== "undefined") {
        var epoch = Number(snapshot.taint_epoch);
        if (!Number.isNaN(epoch) && epoch >= 0) state.runtimeState.taint_epoch = epoch;
      }
      if (snapshot.trust_state) {
        state.runtimeState.trust_state = String(snapshot.trust_state);
      }
      setRuntimeView();
    },
  };
})();
