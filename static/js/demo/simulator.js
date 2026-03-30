(function () {
  "use strict";

  var actionsCache = [];
  var STEP_BUTTON_IDS = ["demo-issue", "demo-step-verify", "demo-taint-bump", "demo-step-reissue", "demo-revoke"];
  var TOUR_STEP_DELAY_MS = 1400;
  var AUTO_START_DELAY_MS = 800;
  var INTEGRATION_TOKEN_PLACEHOLDER = "<PROOF_TOKEN_FROM_ISSUE_STEP>";
  var lastResult = null;
  var tourState = { status: "idle", step: 0 };
  var userInteracted = false;

  function nowClock() {
    return new Date().toISOString().split("T")[1].replace("Z", "");
  }

  function explain(reason) {
    var map = {
      proof_missing: "No credential active. Click Step 1 to issue one.",
      proof_issued: "A new proof was issued and is now available for action checks.",
      proof_allowed: "Proof scope, resource bounds, and trust state matched, so this action is allowed.",
      proof_taint_epoch_stale: "Trust state changed after untrusted input, so the older proof is stale and denied.",
      token_revoked: "This proof was revoked in the control plane, so the runtime deterministically denies.",
      proof_scope_denied: "Requested action is outside proof scope.",
      proof_resource_denied: "Requested resource path is outside proof bounds.",
      proof_revoked: "Revocation requested; waiting for verifier deny to confirm propagation.",
    };
    return map[reason] || "Verifier returned a deterministic reason code for this decision.";
  }

  function friendlyError(message) {
    var m = String(message || "");
    if (m === "demo_service_unavailable") return "Demo service temporarily unavailable. Retry in a moment.";
    if (m === "demo_service_unauthorized") return "Demo service token is unauthorized. Rotate service credential.";
    if (m === "empty_error_response") return "Upstream returned an empty error payload.";
    if (m === "invalid_json_response") return "Upstream returned invalid JSON. Please retry.";
    if (m === "request_failed_401") return "Demo service principal is unauthorized. Rotate demo token.";
    if (m === "request_failed_403") return "Request blocked by policy. Check demo service scope.";
    if (m.indexOf("request_failed_5") === 0) return "Control plane is unavailable right now.";
    if (m.indexOf("tour_") === 0) return "Guided tour timed out on a step. Retry or run manual flow.";
    return m || "Unexpected error";
  }

  function sleep(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  function sanitizeSnapshotValue(value, maxLen) {
    var out = String(value == null ? "" : value).trim();
    if (!out || out.length > (maxLen || 120)) return "";
    return /^[a-zA-Z0-9._:-]+$/.test(out) ? out : "";
  }

  function showToast(text) {
    var toast = document.getElementById("demo-toast");
    if (!toast) return;
    toast.textContent = text;
    toast.classList.add("show");
    setTimeout(function () { toast.classList.remove("show"); }, 2400);
  }

  function b64EncodeJson(payload) {
    try {
      return btoa(unescape(encodeURIComponent(JSON.stringify(payload))))
        .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
    } catch (_) {
      return "";
    }
  }

  function b64DecodeJson(raw) {
    try {
      var normalized = String(raw || "").replace(/-/g, "+").replace(/_/g, "/");
      var pad = normalized.length % 4;
      if (pad) normalized += "====".slice(pad);
      return JSON.parse(decodeURIComponent(escape(atob(normalized))));
    } catch (_) {
      return null;
    }
  }

  function hardenShareQuery() {
    var params = new URLSearchParams(window.location.search || "");
    var allowed = ["runtime_id", "jti", "taint_epoch", "trust_state", "state", "proof", "taint", "revoked"];
    var dirty = false;
    params.forEach(function (_, key) {
      if (allowed.indexOf(key) < 0) {
        params.delete(key);
        dirty = true;
      }
    });
    if (params.has("proof_token") || params.has("token")) {
      params.delete("proof_token");
      params.delete("token");
      dirty = true;
    }
    if (dirty) {
      var clean = params.toString();
      var nextUrl = window.location.pathname + (clean ? ("?" + clean) : "");
      window.history.replaceState({}, "", nextUrl);
    }
    return params;
  }

  function highlightJson(payload, focusKeys) {
    var json = JSON.stringify(payload || {}, null, 2);
    focusKeys = focusKeys || [];
    var html = json
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"([^"]+)":/g, '<span class="k">"$1"</span>:')
      .replace(/: "([^"]*)"/g, ': <span class="s">"$1"</span>')
      .replace(/: (true|false)/g, ': <span class="b">$1</span>')
      .replace(/: (-?\d+(\.\d+)?)/g, ': <span class="n">$1</span>');
    focusKeys.forEach(function (key) {
      html = html.replace(new RegExp('<span class="k">"' + key + '"<\\/span>:', "g"), '<span class="k"><mark>"' + key + '"</mark></span>:');
    });
    return html;
  }

  function setActiveStep(index) {
    STEP_BUTTON_IDS.forEach(function (id, i) {
      var el = document.getElementById(id);
      if (el) el.classList.toggle("active", i === index);
      if (el && i === index && window.matchMedia && window.matchMedia("(max-width: 760px)").matches) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
  }

  function haptic(pattern) {
    if (!navigator.vibrate || !userInteracted) return;
    try {
      navigator.vibrate(pattern);
    } catch (_) {
      // Ignore vibration failures on unsupported environments.
    }
  }

  function bindUserGestureFlag() {
    function mark() {
      userInteracted = true;
      document.removeEventListener("pointerdown", mark, true);
      document.removeEventListener("keydown", mark, true);
      document.removeEventListener("touchstart", mark, true);
    }
    document.addEventListener("pointerdown", mark, true);
    document.addEventListener("keydown", mark, true);
    document.addEventListener("touchstart", mark, true);
  }

  function flashResultPanel(decision) {
    var panel = document.getElementById("demo-live-result");
    if (!panel) return;
    panel.classList.remove("flash-allow", "flash-deny");
    // Force reflow so repeated same-class flashes still animate.
    void panel.offsetWidth;
    panel.classList.add(decision === "allow" ? "flash-allow" : "flash-deny");
  }

  function flashAction(actionId, decision) {
    var btn = document.querySelector('.demo-action[data-action-id="' + actionId + '"]');
    if (!btn) return;
    btn.classList.remove("allow", "deny");
    var cls = decision === "allow" ? "allow" : "deny";
    btn.classList.add(cls);
    setTimeout(function () { btn.classList.remove(cls); }, 650);
  }

  function setHumanStatus(text) {
    var el = document.getElementById("demo-human-status");
    if (el) el.textContent = text;
  }

  function tourCopy(step) {
    var copies = [
      "Step 1/5: Issue a fresh proof bound to this runtime and current taint epoch.",
      "Step 2/5: Same read action is allowed because proof + trust state match.",
      "Step 3/5: Taint bump invalidates old proof; same action now denies.",
      "Step 4/5: Re-issue proof at new epoch; action is allowed again.",
      "Step 5/5: Revoke the proof. Verifier converges to token_revoked deny.",
    ];
    return copies[step] || "Guided tour is running.";
  }

  function setTourStatus(status) {
    tourState.status = status;
    var overlay = document.getElementById("demo-tour-overlay");
    var pauseBtn = document.getElementById("demo-tour-pause");
    var resumeBtn = document.getElementById("demo-tour-resume");
    if (overlay) overlay.hidden = (status === "idle" || status === "completed");
    if (pauseBtn) pauseBtn.hidden = status !== "running";
    if (resumeBtn) resumeBtn.hidden = status !== "paused";
  }

  function renderTourOverlay(step) {
    var title = document.getElementById("demo-tour-title");
    var copy = document.getElementById("demo-tour-copy");
    var overlay = document.getElementById("demo-tour-overlay");
    tourState.step = step;
    if (title) title.textContent = "Guided tour (" + (step + 1) + "/5)";
    if (copy) copy.textContent = tourCopy(step);
    if (overlay) {
      overlay.classList.remove("fading");
      void overlay.offsetWidth;
      overlay.classList.add("fading");
    }
  }

  async function waitUntilResumed() {
    while (tourState.status === "paused") {
      await sleep(180);
    }
  }

  async function waitForReason(reasons, timeoutMs) {
    var start = Date.now();
    while ((Date.now() - start) < timeoutMs) {
      await waitUntilResumed();
      if (tourState.status !== "running") return false;
      if (lastResult && reasons.indexOf(String(lastResult.reason_code || "")) >= 0) return true;
      await sleep(180);
    }
    return false;
  }

  function setTrustBadgeFromReason(reason) {
    if (!window.DemoProofControls || !window.DemoProofControls.setTrustStateBadge) return;
    if (reason === "proof_taint_epoch_stale" || reason === "taint_epoch_bumped") window.DemoProofControls.setTrustStateBadge("tainted");
    else if (reason === "token_revoked" || reason === "proof_revoked") window.DemoProofControls.setTrustStateBadge("revoked");
    else if (reason === "proof_allowed" || reason === "proof_issued") window.DemoProofControls.setTrustStateBadge("trusted");
  }

  function updateResultPanel(data) {
    lastResult = data || null;
    var decision = String(data.decision || "deny");
    var reason = String(data.reason_code || "proof_missing");
    var controls = window.DemoProofControls.getState();
    var proof = controls.activeProof || {};
    var pill = document.getElementById("demo-result-pill");
    var reasonEl = document.getElementById("demo-result-reason");
    var explainEl = document.getElementById("demo-result-explain");
    var scopeEl = document.getElementById("demo-field-scope");
    var epochEl = document.getElementById("demo-field-epoch");
    var trustEl = document.getElementById("demo-field-trust");
    var expiryEl = document.getElementById("demo-field-expiry");
    var decisionEl = document.getElementById("demo-decision-json");
    var proofEl = document.getElementById("demo-proof-json");
    var trustMap = {
      trusted: "credential_valid",
      tainted: "runtime_tainted",
      revoked: "credential_revoked",
    };

    if (pill) {
      pill.classList.remove("allow", "deny");
      pill.classList.add(decision === "allow" ? "allow" : "deny");
      pill.textContent = decision.toUpperCase();
    }
    if (reasonEl) reasonEl.textContent = reason;
    if (explainEl) explainEl.textContent = explain(reason);
    if (scopeEl) scopeEl.textContent = (proof.action_ids && proof.action_ids.length) ? proof.action_ids.join(", ") : "-";
    if (epochEl) epochEl.textContent = String((proof.taint_epoch != null ? proof.taint_epoch : controls.runtimeState.taint_epoch) || 0);
    if (trustEl) {
      var rawTrust = String(controls.runtimeState.trust_state || "trusted").toLowerCase();
      trustEl.textContent = trustMap[rawTrust] || "credential_valid";
    }
    if (expiryEl) expiryEl.textContent = proof.expires_at || proof.expiration || "-";
    if (decisionEl) {
      decisionEl.innerHTML = highlightJson(data || {}, ["decision", "reason_code"]);
      decisionEl.scrollTop = decisionEl.scrollHeight;
    }

    var focus = [];
    if (reason === "proof_taint_epoch_stale") focus = ["taint_epoch", "trust_state"];
    else if (reason === "token_revoked") focus = ["jti", "revoked"];
    else if (reason === "proof_allowed") focus = ["action_ids", "resources", "expires_at", "ppid"];
    if (proofEl) {
      proofEl.innerHTML = highlightJson(proof || {}, focus);
      proofEl.scrollTop = proofEl.scrollHeight;
    }

    flashResultPanel(decision);
    setTrustBadgeFromReason(reason);
    if (window.DemoArchitecture) window.DemoArchitecture.updateDecision(decision, reason);
    if (window.DemoExplain) window.DemoExplain.set(data);
  }

  function appendLog(actionLabel, data) {
    if (!window.DemoVerifierLog) return;
    window.DemoVerifierLog.append({
      time: nowClock(),
      action: actionLabel,
      decision: data.decision || "error",
      reason: data.reason_code || data.error || "unknown",
    });
  }

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

  function renderIntegration(lang) {
    var preview = document.getElementById("demo-integration-preview");
    if (!preview) return;
    var controls = window.DemoProofControls.getState();
    var token = INTEGRATION_TOKEN_PLACEHOLDER;
    var runtimeId = controls.runtimeId || "<RUNTIME_ID>";
    var snippets = {
      ts: "import fetch from \"node-fetch\";\n\nconst res = await fetch(\"https://lemma.id/api/demo/verify\", {\n  method: \"POST\",\n  headers: { \"Content-Type\": \"application/json\" },\n  body: JSON.stringify({ runtime_id: \"" + runtimeId + "\", action_id: \"read_src_app\", proof_token: \"" + token + "\" })\n});\nconsole.log(await res.json());",
      py: "import requests\n\nres = requests.post(\"https://lemma.id/api/demo/verify\", json={\n  \"runtime_id\": \"" + runtimeId + "\",\n  \"action_id\": \"read_src_app\",\n  \"proof_token\": \"" + token + "\"\n})\nprint(res.json())",
      go: "payload := strings.NewReader(`{\"runtime_id\":\"" + runtimeId + "\",\"action_id\":\"read_src_app\",\"proof_token\":\"" + token + "\"}`)\nreq, _ := http.NewRequest(\"POST\", \"https://lemma.id/api/demo/verify\", payload)\nreq.Header.Add(\"Content-Type\", \"application/json\")\nresp, _ := http.DefaultClient.Do(req)\n// decode resp body JSON",
      langgraph: "from langgraph.graph import StateGraph\nimport requests\n\ndef authorize(state):\n    decision = requests.post(\"https://lemma.id/api/demo/verify\", json={\n        \"runtime_id\": \"" + runtimeId + "\",\n        \"action_id\": \"read_src_app\",\n        \"proof_token\": \"" + token + "\"\n    }).json()\n    state[\"lemma_decision\"] = decision\n    return state",
      crewai: "from crewai import Agent, Task\nimport requests\n\ndef guard(action_id):\n    return requests.post(\"https://lemma.id/api/demo/verify\", json={\n        \"runtime_id\": \"" + runtimeId + "\",\n        \"action_id\": action_id,\n        \"proof_token\": \"" + token + "\"\n    }).json()",
      autogen: "import requests\n\ndef lemma_verify(action_id):\n    return requests.post(\"https://lemma.id/api/demo/verify\", json={\n        \"runtime_id\": \"" + runtimeId + "\",\n        \"action_id\": action_id,\n        \"proof_token\": \"" + token + "\"\n    }).json()\n\n# call lemma_verify before each tool execution",
    };
    preview.textContent = snippets[lang] || snippets.ts;
    document.querySelectorAll(".demo-tab[data-lang]").forEach(function (tab) {
      tab.classList.toggle("active", tab.getAttribute("data-lang") === lang);
    });
  }

  async function verifyAction(action, stepIndex) {
    var controls = window.DemoProofControls.getState();
    if (!controls.activeProof || !controls.activeProof.token) {
      var missing = { decision: "deny", reason_code: "proof_missing", action_id: action && action.action_id };
      updateResultPanel(missing);
      appendLog(action ? action.label : "verify", missing);
      setHumanStatus("No credential active. Click Step 1 to issue one.");
      return missing;
    }

    // Local verification: check credential properties without server call
    var proof = controls.activeProof;
    var runtimeState = controls.runtimeState || {};
    var runtimeEpoch = parseInt(runtimeState.taint_epoch || "0", 10);
    var proofEpoch = parseInt(proof.taint_epoch || "0", 10);
    var scope = proof.scope || [];
    var decision = "allow";
    var reason_code = "proof_allowed";

    // Check revocation
    if (proof.revoked) {
      decision = "deny";
      reason_code = "token_revoked";
    }

    // Check taint epoch
    if (decision === "allow" && runtimeEpoch > 0 && proofEpoch < runtimeEpoch) {
      decision = "deny";
      reason_code = "proof_taint_epoch_stale";
    }

    // Check scope against action
    if (decision === "allow" && action && action.required_scope) {
      var requiredScope = action.required_scope;
      var hasScope = scope.indexOf(requiredScope) !== -1 ||
        scope.indexOf("admin") !== -1 ||
        (requiredScope === "read" && (scope.indexOf("write") !== -1 || scope.indexOf("admin") !== -1)) ||
        (requiredScope === "write" && scope.indexOf("admin") !== -1);
      if (!hasScope) {
        decision = "deny";
        reason_code = "proof_scope_denied";
      }
    }

    var payload = {
      success: true,
      decision: decision,
      reason_code: reason_code,
      action_id: action ? action.action_id : null,
      runtime_id: controls.runtimeId,
      scope: scope,
      taint_epoch: proofEpoch,
      runtime_taint_epoch: runtimeEpoch,
      verification: "local",
    };

    updateResultPanel(payload);
    flashAction(action.action_id, payload.decision);
    haptic(payload.decision === "allow" ? [10] : [14, 24, 14]);
    setHumanStatus(action.label + " -> " + String(payload.decision || "deny").toUpperCase() + " (" + String(payload.reason_code || "no_reason") + ")");
    if (typeof stepIndex === "number") setActiveStep(stepIndex);
    appendLog(action.label, payload);
    if (window.DemoTimeline) {
      window.DemoTimeline.push({
        label: "t2 " + action.action_id,
        decision: payload.decision || "deny",
        reason_code: payload.reason_code,
      });
    }
    if (window.DemoArchitecture) {
      window.DemoArchitecture.updateDecision(decision, reason_code);
    }
    return payload;
  }

  function getReadAction() {
    return (actionsCache || []).find(function (a) { return a.action_id === "read_src_app"; }) || (actionsCache || [])[0];
  }

  function bindActionButtons(actions) {
    var wrap = document.getElementById("demo-actions");
    if (!wrap) return;
    wrap.innerHTML = "";
    actions.forEach(function (action) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "demo-action";
      button.setAttribute("data-action-id", action.action_id);
      button.innerHTML =
        "<strong>" + action.label + "</strong>" +
        "<span>" + action.method + " " + action.route_path + "</span>";
      button.addEventListener("click", function () {
        verifyAction(action).catch(function (err) {
          var payload = { decision: "deny", reason_code: "verify_failed", message: err.message };
          updateResultPanel(payload);
          setHumanStatus("Action check failed: " + friendlyError(err.message));
          appendLog(action.label, payload);
        });
      });
      wrap.appendChild(button);
    });
    var actionsLabel = document.getElementById("demo-actions-label");
    if (actionsLabel) actionsLabel.style.display = "block";
  }

  function bindIntegrationTabs() {
    var tabs = document.querySelectorAll(".demo-tab[data-lang]");
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        renderIntegration(tab.getAttribute("data-lang"));
      });
    });
    renderIntegration("ts");
  }

  function bindPolicyPills() {
    var wrap = document.getElementById("demo-policy-profile");
    if (!wrap) return;
    var pills = wrap.querySelectorAll(".demo-policy-pill");
    pills.forEach(function (pill) {
      pill.addEventListener("click", function () {
        pills.forEach(function (p) { p.classList.remove("active"); });
        pill.classList.add("active");
      });
    });
  }

  function bindThemeToggle() {
    var root = document.getElementById("demo-root");
    var btn = document.getElementById("demo-theme-toggle");
    if (!root || !btn) return;
    btn.addEventListener("click", function () {
      var current = root.getAttribute("data-demo-theme") || "light";
      var next = current === "light" ? "dark" : "light";
      root.setAttribute("data-demo-theme", next);
      btn.textContent = next === "dark" ? "Light mode" : "Dark mode";
    });
  }

  async function runAutoStartIfNeeded(params) {
    // Disabled: let users click Step 1 themselves for a clean experience
    return;
  }

  async function runTourFlow() {
    var issueBtn = document.getElementById("demo-issue");
    var verifyBtn = document.getElementById("demo-step-verify");
    var taintBtn = document.getElementById("demo-taint-bump");
    var reissueBtn = document.getElementById("demo-step-reissue");
    var revokeBtn = document.getElementById("demo-revoke");
    var startCard = document.getElementById("demo-tour-start-card");

    setTourStatus("running");
    if (startCard) startCard.hidden = true;

    renderTourOverlay(0);
    if (issueBtn) issueBtn.click();
    if (!(await waitForReason(["proof_issued"], 12000))) throw new Error("tour_issue_timeout");

    renderTourOverlay(1);
    await sleep(TOUR_STEP_DELAY_MS);
    if (verifyBtn) verifyBtn.click();
    if (!(await waitForReason(["proof_allowed"], 12000))) throw new Error("tour_verify_timeout");

    renderTourOverlay(2);
    await sleep(TOUR_STEP_DELAY_MS);
    if (taintBtn) taintBtn.click();
    if (!(await waitForReason(["proof_taint_epoch_stale"], 14000))) throw new Error("tour_taint_timeout");

    renderTourOverlay(3);
    await sleep(TOUR_STEP_DELAY_MS);
    if (reissueBtn) reissueBtn.click();
    if (!(await waitForReason(["proof_allowed"], 14000))) throw new Error("tour_reissue_timeout");

    renderTourOverlay(4);
    await sleep(TOUR_STEP_DELAY_MS);
    if (revokeBtn) revokeBtn.click();
    if (!(await waitForReason(["token_revoked"], 28000))) throw new Error("tour_revoke_timeout");

    setTourStatus("completed");
    setHumanStatus("Guided tour complete: allow -> stale deny -> allow -> revoked deny.");
  }

  function bindTourControls() {
    var startButtons = ["demo-start-tour", "demo-tour-start-cta"];
    var skipStart = document.getElementById("demo-tour-skip-cta");
    var pauseBtn = document.getElementById("demo-tour-pause");
    var resumeBtn = document.getElementById("demo-tour-resume");
    var skipBtn = document.getElementById("demo-tour-skip");
    var resetBtn = document.getElementById("demo-tour-reset");
    var tourStartCard = document.getElementById("demo-tour-start-card");
    var resetMain = document.getElementById("demo-reset");

    function start() {
      if (tourState.status === "running") return;
      runTourFlow().catch(function (err) {
        setTourStatus("idle");
        setHumanStatus("Tour stopped: " + friendlyError(err.message));
      });
    }

    startButtons.forEach(function (id) {
      var btn = document.getElementById(id);
      if (btn) btn.addEventListener("click", start);
    });

    if (skipStart) {
      skipStart.addEventListener("click", function () {
        if (tourStartCard) tourStartCard.hidden = true;
        setHumanStatus("Manual mode enabled. Use the 5-step flow.");
      });
    }
    if (pauseBtn) {
      pauseBtn.addEventListener("click", function () {
        if (tourState.status !== "running") return;
        setTourStatus("paused");
        setHumanStatus("Tour paused.");
      });
    }
    if (resumeBtn) {
      resumeBtn.addEventListener("click", function () {
        if (tourState.status !== "paused") return;
        setTourStatus("running");
        setHumanStatus("Tour resumed.");
      });
    }
    if (skipBtn) {
      skipBtn.addEventListener("click", function () {
        setTourStatus("idle");
        setHumanStatus("Tour skipped. You can continue manually.");
      });
    }
    if (resetBtn) {
      resetBtn.addEventListener("click", function () {
        setTourStatus("idle");
        if (resetMain) resetMain.click();
      });
    }
  }

  function bindStepButtons() {
    var issueTopBtn = document.getElementById("demo-issue-top");
    var issueBtn = document.getElementById("demo-issue");
    var verifyBtn = document.getElementById("demo-step-verify");
    var taintBtn = document.getElementById("demo-taint-bump");
    var reissueBtn = document.getElementById("demo-step-reissue");
    var revokeBtn = document.getElementById("demo-revoke");
    var resetBtn = document.getElementById("demo-reset");
    var copyLinkBtn = document.getElementById("demo-copy-link");
    var copyCurl = document.getElementById("demo-copy-curl");

    function doIssue(stepIndex) {
      setActiveStep(stepIndex);
      var tourCard = document.getElementById("demo-tour-start-card");
      if (tourCard) tourCard.hidden = true;
      return window.DemoProofControls.issueProof().then(function (payload) {
        var out = { decision: "allow", reason_code: "proof_issued", payload: payload };
        updateResultPanel(out);
        appendLog("issue_proof", out);
        haptic([8, 16, 8]);
        setHumanStatus("Credential issued. Click Step 2 to try an action.");
        renderIntegration("ts");
        if (window.DemoTimeline) window.DemoTimeline.push({ label: "t1 issue", decision: "allow", reason_code: "proof_issued" });
      }).catch(function (err) {
        var failed = { decision: "deny", reason_code: "issue_failed", message: err.message };
        updateResultPanel(failed);
        appendLog("issue_proof", failed);
        setHumanStatus("Credential issue failed: " + friendlyError(err.message));
        haptic([20, 30, 20]);
        throw err;
      });
    }

    if (issueTopBtn) {
      issueTopBtn.addEventListener("click", function () {
        doIssue(0).catch(function () { /* handled in doIssue */ });
      });
    }
    if (issueBtn) {
      issueBtn.addEventListener("click", function () {
        doIssue(0).catch(function () { /* handled in doIssue */ });
      });
    }
    if (verifyBtn) {
      verifyBtn.addEventListener("click", function () {
        var readAction = getReadAction();
        verifyAction(readAction, 1).catch(function (err) {
          var payload = { decision: "deny", reason_code: "verify_failed", message: err.message };
          updateResultPanel(payload);
          setHumanStatus("Action check failed: " + friendlyError(err.message));
          appendLog(readAction ? readAction.label : "verify", payload);
        });
      });
    }
    if (taintBtn) {
      taintBtn.addEventListener("click", function () {
        setActiveStep(2);
        window.DemoProofControls.bumpTaint().then(function () {
          var readAction = getReadAction();
          return verifyAction(readAction, 2);
        }).catch(function (err) {
          var payload = { decision: "deny", reason_code: "taint_failed", message: err.message };
          updateResultPanel(payload);
          appendLog("taint_bump", payload);
          setHumanStatus("Taint bump failed: " + friendlyError(err.message));
          haptic([20, 30, 20]);
        });
      });
    }
    if (reissueBtn) {
      reissueBtn.addEventListener("click", function () {
        doIssue(3).then(function () {
          var readAction = getReadAction();
          return verifyAction(readAction, 3);
        }).catch(function () { /* handled in doIssue/verify */ });
      });
    }
    if (revokeBtn) {
      revokeBtn.addEventListener("click", function () {
        setActiveStep(4);
        var readAction = getReadAction();
        window.DemoProofControls.revokeProof().then(function () {
          return verifyAction(readAction, 4);
        }).catch(function (err) {
          var payload = { decision: "deny", reason_code: "revoke_failed", message: err.message };
          updateResultPanel(payload);
          appendLog("revoke", payload);
          setHumanStatus("Revoke failed: " + friendlyError(err.message));
          haptic([20, 30, 20]);
        });
      });
    }
    if (resetBtn) {
      resetBtn.addEventListener("click", function () {
        window.DemoProofControls.reset().then(function () {
          if (window.DemoTimeline) window.DemoTimeline.seed();
          setActiveStep(0);
          var missing = { decision: "deny", reason_code: "proof_missing" };
          updateResultPanel(missing);
          appendLog("verify_on_load", missing);
          setHumanStatus("Reset complete. Click Step 1 to issue a new credential.");
          renderIntegration("ts");
          haptic([10]);
        });
      });
    }
    if (copyLinkBtn) {
      copyLinkBtn.addEventListener("click", function () {
        var state = window.DemoProofControls.getState();
        var snapshot = {
          runtime_id: sanitizeSnapshotValue(state.runtimeId || "", 120),
          jti: sanitizeSnapshotValue(state.activeProof && state.activeProof.jti, 180),
          taint_epoch: Number(state.runtimeState && state.runtimeState.taint_epoch || 0),
          trust_state: sanitizeSnapshotValue(state.runtimeState && state.runtimeState.trust_state, 24),
          last_reason: sanitizeSnapshotValue(lastResult && lastResult.reason_code, 64),
        };
        var qs = new URLSearchParams();
        if (snapshot.runtime_id) qs.set("runtime_id", snapshot.runtime_id);
        if (snapshot.jti) qs.set("proof", snapshot.jti);
        if (!Number.isNaN(snapshot.taint_epoch)) qs.set("taint", String(snapshot.taint_epoch));
        qs.set("revoked", String(snapshot.trust_state === "revoked" || snapshot.last_reason === "token_revoked"));
        var encoded = b64EncodeJson(snapshot);
        if (encoded) qs.set("state", encoded);
        var qsString = qs.toString();
        var url = window.location.origin + window.location.pathname + (qsString ? ("?" + qsString) : "");
        navigator.clipboard.writeText(url).then(function () {
          setHumanStatus("Share link copied.");
          haptic([8]);
        });
      });
    }
    if (copyCurl) {
      copyCurl.addEventListener("click", function () {
        var state = window.DemoProofControls.getState();
        var cmd =
          "curl -X POST https://lemma.id/api/demo/verify " +
          "-H \"Content-Type: application/json\" " +
          "-d '{\"runtime_id\":\"" + state.runtimeId + "\",\"action_id\":\"read_src_app\",\"proof_token\":\"" + INTEGRATION_TOKEN_PLACEHOLDER + "\"}'";
        navigator.clipboard.writeText(cmd).then(function () {
          setHumanStatus("Integration call copied.");
          haptic([8]);
        });
      });
    }
  }

  function bindShortcuts() {
    document.addEventListener("keydown", function (event) {
      if (event.target && /input|textarea|select/i.test(event.target.tagName)) return;
      if (String(event.key || "").toLowerCase() === "r") {
        var resetBtn = document.getElementById("demo-reset");
        if (resetBtn) resetBtn.click();
        return;
      }
      var idx = Number(event.key);
      if (!idx || idx < 1 || idx > 5) return;
      var button = document.getElementById(STEP_BUTTON_IDS[idx - 1]);
      if (button) button.click();
    });
  }

  async function init() {
    var root = document.getElementById("demo-root");
    if (!root) return;
    var params = hardenShareQuery();
    var stateSnapshot = b64DecodeJson(params.get("state"));
    if (!stateSnapshot && (params.has("proof") || params.has("taint") || params.has("revoked"))) {
      stateSnapshot = {
        runtime_id: sanitizeSnapshotValue(params.get("runtime_id"), 120),
        jti: sanitizeSnapshotValue(params.get("proof"), 180),
        taint_epoch: Number(params.get("taint") || 0),
        trust_state: params.get("revoked") === "true" ? "revoked" : "trusted",
        last_reason: params.get("revoked") === "true" ? "token_revoked" : "proof_allowed",
      };
    }
    var runtimeId = sanitizeSnapshotValue((stateSnapshot && stateSnapshot.runtime_id) || params.get("runtime_id"), 120) || root.getAttribute("data-runtime-id");
    if (window.DemoArchitecture) {
      window.DemoArchitecture.mount("demo-architecture");
    }
    if (window.DemoTimeline) {
      window.DemoTimeline.seed();
    }
    await window.DemoProofControls.init(runtimeId);
    var statePayload = await requestJson("/api/demo/state?runtime_id=" + encodeURIComponent(runtimeId));
    actionsCache = statePayload.actions || [];
    bindActionButtons(statePayload.actions || []);
    bindStepButtons();
    bindUserGestureFlag();
    bindTourControls();
    bindIntegrationTabs();
    bindPolicyPills();
    bindThemeToggle();
    bindShortcuts();
    setTourStatus("idle");
    setActiveStep(0);
    if (stateSnapshot) {
      if (window.DemoProofControls && window.DemoProofControls.applySnapshot) {
        window.DemoProofControls.applySnapshot(stateSnapshot);
      }
      var restoredReason = sanitizeSnapshotValue(stateSnapshot.last_reason || "", 64) || "proof_missing";
      var restoredDecision = (restoredReason === "proof_allowed" || restoredReason === "proof_issued") ? "allow" : "deny";
      updateResultPanel({ decision: restoredDecision, reason_code: restoredReason });
      setHumanStatus("State restored from link. Last observed reason: " + restoredReason + ".");
    } else {
      setHumanStatus("Ready to start. Click Step 1 to issue a credential.");
    }
    runAutoStartIfNeeded(params).catch(function () { /* no-op auto-start fallback */ });
  }

  document.addEventListener("DOMContentLoaded", function () {
    init().catch(function (err) {
      updateResultPanel({ decision: "deny", reason_code: "init_failed", message: err.message });
      setHumanStatus("Demo init failed: " + friendlyError(err.message));
    });
  });
})();
