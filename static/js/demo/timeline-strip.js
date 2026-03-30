(function () {
  "use strict";

  var nodes = [];
  var labels = ["t0 Start", "t1 Issue Proof", "t2 Verify", "t3 Policy Check", "t4 Execute", "t5 Taint Bump", "t6 Stale Deny", "t7 Revoke", "t8 Blocked"];
  var cursor = 0;
  var chipsWrap = null;

  function colorFor(decision) {
    if (decision === "allow") return "#22c55e";
    if (decision === "deny") return "#ef4444";
    return "#f59e0b";
  }

  function paintNode(index, decision, reason) {
    var node = nodes[index];
    if (!node) return;
    node.setAttribute("fill", colorFor(decision));
    node.setAttribute("stroke", colorFor(decision));
    node.setAttribute("r", "9");
    node.style.filter = "drop-shadow(0 0 6px " + colorFor(decision) + ")";
    node.style.transition = "all .22s ease";
    setTimeout(function () { node.setAttribute("r", "8"); }, 240);
    node.setAttribute("data-reason", String(reason || ""));
    node.setAttribute("title", String(reason || "timeline_step"));
    var label = document.getElementById("demo-tl-label-" + index);
    if (label) {
      label.setAttribute("fill", colorFor(decision));
      label.textContent = labels[index];
    }
  }

  function addChip(entry) {
    if (!chipsWrap) return;
    var chip = document.createElement("span");
    var decision = String(entry.decision || "warn");
    chip.className = "demo-chip " + (decision === "allow" ? "ok" : (decision === "deny" ? "deny" : "warn"));
    chip.textContent = (entry.label || "step") + " - " + String(entry.reason_code || "decision");
    chipsWrap.prepend(chip);
    while (chipsWrap.children.length > 10) {
      chipsWrap.removeChild(chipsWrap.lastChild);
    }
  }

  function mountTimeline(el) {
    if (!el) return;
    el.innerHTML = [
      '<div id="demo-tl-reasons" style="display:flex;gap:6px;flex-wrap:wrap;margin:0 0 8px"></div>',
      '<svg viewBox="0 0 1400 92" width="100%" role="img" aria-label="Appendix B timeline">',
      '<line x1="40" y1="34" x2="1360" y2="34" stroke="#cbd5e1" stroke-width="3"></line>',
      labels.map(function (_, i) {
        var x = 40 + i * 165;
        return '<circle id="demo-tl-node-' + i + '" cx="' + x + '" cy="34" r="8" fill="#e2e8f0" stroke="#94a3b8" stroke-width="2"></circle>' +
          '<text id="demo-tl-label-' + i + '" x="' + x + '" y="70" text-anchor="middle" fill="#334155" font-size="11">' + labels[i] + "</text>";
      }).join(""),
      "</svg>",
    ].join("");
    nodes = labels.map(function (_, i) {
      return document.getElementById("demo-tl-node-" + i);
    });
    chipsWrap = document.getElementById("demo-tl-reasons");
    cursor = 0;
  }

  window.DemoTimeline = {
    push: function push(entry) {
      var el = document.getElementById("demo-timeline");
      if (!el) return;
      var index = Math.min(cursor, nodes.length - 1);
      paintNode(index, entry.decision, entry.reason_code);
      addChip(entry);
      cursor += 1;
    },
    seed: function seed() {
      var el = document.getElementById("demo-timeline");
      if (!el) return;
      mountTimeline(el);
      paintNode(0, "warn", "start");
      addChip({ label: "t0 boot", decision: "warn", reason_code: "proof_missing" });
    },
  };
})();
