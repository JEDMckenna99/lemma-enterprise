(function () {
  "use strict";
  var entries = [];
  var filters = { decision: "", text: "" };

  function reasonHint(reason) {
    var hints = {
      proof_allowed: "Allowed because scope, resource, and trust state match.",
      proof_taint_epoch_stale: "Denied because proof taint epoch is older than runtime epoch.",
      token_revoked: "Denied because this proof was revoked by the control plane.",
      proof_scope_denied: "Denied because proof scopes do not include this action.",
      proof_resource_denied: "Denied because resource path is outside proof bounds.",
    };
    return hints[String(reason || "")] || "Verifier returned this deterministic reason code.";
  }

  function toRow(entry) {
    var tr = document.createElement("tr");
    tr.className = "demo-log-row";
    var icon = entry.decision === "allow" ? "✓" : "✕";
    tr.innerHTML =
      "<td>" + entry.time + "</td>" +
      "<td>" + entry.action + "</td>" +
      "<td>" + icon + " " + entry.decision + "</td>" +
      "<td><span class=\"demo-reason\" title=\"" + reasonHint(entry.reason).replace(/"/g, "&quot;") + "\">" + entry.reason + "</span></td>";
    return tr;
  }

  function passesFilter(entry) {
    if (filters.decision && String(entry.decision || "").toLowerCase() !== filters.decision) return false;
    if (filters.text) {
      var hay = (String(entry.action || "") + " " + String(entry.reason || "")).toLowerCase();
      if (hay.indexOf(filters.text) < 0) return false;
    }
    return true;
  }

  function render() {
    var tbody = document.getElementById("demo-log-rows");
    if (!tbody) return;
    tbody.innerHTML = "";
    entries.filter(passesFilter).forEach(function (entry) {
      tbody.appendChild(toRow(entry));
    });
  }

  function bindFilters() {
    var decision = document.getElementById("demo-log-filter-decision");
    var text = document.getElementById("demo-log-filter-text");
    if (decision) {
      decision.addEventListener("change", function () {
        filters.decision = String(decision.value || "").toLowerCase();
        render();
      });
    }
    if (text) {
      text.addEventListener("input", function () {
        filters.text = String(text.value || "").trim().toLowerCase();
        render();
      });
    }
  }

  window.DemoVerifierLog = {
    append: function append(entry) {
      entries.unshift(entry);
      while (entries.length > 18) {
        entries.pop();
      }
      render();
    },
  };

  document.addEventListener("DOMContentLoaded", bindFilters);
})();
