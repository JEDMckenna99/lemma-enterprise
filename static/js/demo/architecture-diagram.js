(function () {
  "use strict";
  var archCursor = 0;
  var archTimeline = ["Start", "Issue", "Verify", "Taint", "Revoke"];

  function renderArchitecture(target) {
    if (!target) return;
    archCursor = 0;

    var svg = [
      '<svg viewBox="0 0 960 440" width="100%" role="img" aria-label="Lemma Firewall architecture" style="font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif">',
      '<defs>',
      '<marker id="a-g" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><polygon points="0 0,6 3,0 6" fill="#22c55e"/></marker>',
      '<marker id="a-a" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><polygon points="0 0,6 3,0 6" fill="#f59e0b"/></marker>',
      '<marker id="a-r" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><polygon points="0 0,6 3,0 6" fill="#ef4444"/></marker>',
      '<marker id="a-p" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><polygon points="0 0,6 3,0 6" fill="#8b5cf6"/></marker>',
      '<marker id="a-d" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><polygon points="0 0,6 3,0 6" fill="#d4d4d8"/></marker>',
      '<filter id="sh"><feDropShadow dx="0" dy="1" stdDeviation="2" flood-color="#0f172a" flood-opacity="0.05"/></filter>',
      '<filter id="gl-g"><feDropShadow dx="0" dy="0" stdDeviation="5" flood-color="#22c55e" flood-opacity="0.45"/></filter>',
      '<filter id="gl-r"><feDropShadow dx="0" dy="0" stdDeviation="5" flood-color="#ef4444" flood-opacity="0.45"/></filter>',
      '<filter id="gl-a"><feDropShadow dx="0" dy="0" stdDeviation="5" flood-color="#f59e0b" flood-opacity="0.45"/></filter>',
      '<filter id="gl-p"><feDropShadow dx="0" dy="0" stdDeviation="5" flood-color="#8b5cf6" flood-opacity="0.4"/></filter>',
      '<circle id="dot" cx="0" cy="0" r="5" fill="#22c55e" opacity="0"/>',
      '</defs>',

      // Background
      '<rect width="960" height="440" rx="14" fill="#fafbfc"/>',

      // ── Zone: Your machine (subtle) ──
      '<rect x="8" y="8" width="746" height="310" rx="10" fill="none" stroke="#e4e4e7" stroke-dasharray="4 3"/>',
      '<text x="20" y="26" fill="#d4d4d8" font-size="9" font-weight="600" letter-spacing="1.5">YOUR MACHINE</text>',

      // ── Zone: lemma.id badge (top-right) ──
      '<rect id="node-server" x="772" y="8" width="178" height="310" rx="10" fill="#f5f3ff" stroke="#ddd6fe" stroke-dasharray="4 3"/>',
      '<circle cx="786" cy="28" r="4" fill="#8b5cf6"/>',
      '<text x="796" y="32" fill="#7c3aed" font-size="10" font-weight="700">lemma.id</text>',
      '<text x="786" y="52" fill="#a78bfa" font-size="9">Passkey auth</text>',
      '<text x="786" y="66" fill="#a78bfa" font-size="9">KMS credential signing</text>',
      '<text x="786" y="86" fill="#a78bfa" font-size="9">Revocation registry</text>',
      '<text x="786" y="100" fill="#a78bfa" font-size="9">Taint coordination</text>',
      '<text x="786" y="114" fill="#a78bfa" font-size="9">Decision logs</text>',

      // ── Node: Human (left) ──
      '<rect id="node-human" x="24" y="50" width="120" height="72" rx="10" fill="#fff" stroke="#e4e4e7" filter="url(#sh)"/>',
      '<circle cx="38" cy="72" r="4" fill="#8b5cf6"/>',
      '<text x="50" y="76" fill="#18181b" font-size="13" font-weight="700">Human</text>',
      '<text x="38" y="94" fill="#a1a1aa" font-size="9">Passkey holder</text>',
      '<text x="38" y="108" fill="#a1a1aa" font-size="9">Grants authority</text>',

      // ── Node: Agent (middle-left) ──
      '<rect id="node-agent" x="196" y="50" width="140" height="72" rx="10" fill="#fff" stroke="#e4e4e7" filter="url(#sh)"/>',
      '<circle cx="210" cy="72" r="4" fill="#3b82f6"/>',
      '<text x="222" y="76" fill="#18181b" font-size="13" font-weight="700">Agent</text>',
      '<text x="210" y="94" fill="#a1a1aa" font-size="9">Carries credential</text>',
      '<text x="210" y="108" fill="#a1a1aa" font-size="9">24 action types</text>',

      // ── Node: Firewall (center, largest) ──
      '<rect id="node-fw-bg" x="388" y="36" width="200" height="100" rx="12" fill="#f0fdf4" stroke="#bbf7d0"/>',
      '<rect id="node-fw" x="396" y="44" width="184" height="84" rx="10" fill="#fff" stroke="#86efac" filter="url(#sh)"/>',
      '<circle cx="410" cy="66" r="5" fill="#22c55e"/>',
      '<text x="422" y="70" fill="#18181b" font-size="14" font-weight="700">Firewall</text>',
      '<text x="410" y="88" fill="#52525b" font-size="10">Ed25519 verify &lt;1ms</text>',
      '<text x="410" y="102" fill="#52525b" font-size="10">Action + taint + revoke</text>',
      '<text x="410" y="116" fill="#16a34a" font-size="9" font-weight="600">Zero server calls</text>',

      // ── Arrows: Issue flow (purple) ──
      '<path id="path-issue" d="M772 60 Q740 60 336 86" stroke="#c4b5fd" stroke-width="1.5" fill="none" stroke-dasharray="4 3" marker-end="url(#a-p)" opacity="0.4"/>',
      '<text x="540" y="56" fill="#c4b5fd" font-size="8">credential issued</text>',

      // ── Arrow: Human -> Agent (delegation) ──
      '<path d="M144 86 L196 86" stroke="#d4d4d8" stroke-width="1.5" fill="none" marker-end="url(#a-d)"/>',
      '<text x="150" y="80" fill="#d4d4d8" font-size="8">delegates</text>',

      // ── Arrow: Agent -> Firewall ──
      '<path d="M336 86 L388 86" stroke="#d4d4d8" stroke-width="1.5" fill="none" marker-end="url(#a-d)"/>',
      '<text x="342" y="78" fill="#a1a1aa" font-size="8">every action</text>',

      // ── GREEN: Allow (right, local) ──
      '<path id="path-allow" d="M580 70 Q620 70 660 70" stroke="#22c55e" stroke-width="2.5" fill="none" opacity="0.1" marker-end="url(#a-g)"/>',
      '<rect id="node-allow" x="666" y="50" width="80" height="40" rx="8" fill="#f0fdf4" stroke="#bbf7d0" opacity="0.7"/>',
      '<text x="706" y="68" text-anchor="middle" fill="#166534" font-size="11" font-weight="700">Allow</text>',
      '<text x="706" y="82" text-anchor="middle" fill="#86efac" font-size="8">local only</text>',

      // ── RED: Denied (below-right, local) ──
      '<path id="path-deny" d="M540 128 Q560 160 600 176" stroke="#ef4444" stroke-width="2.5" fill="none" opacity="0.1" marker-end="url(#a-r)"/>',
      '<rect id="node-deny" x="606" y="158" width="120" height="40" rx="8" fill="#fef2f2" stroke="#fecaca" opacity="0.7"/>',
      '<text x="666" y="176" text-anchor="middle" fill="#991b1b" font-size="11" font-weight="700">Action Denied</text>',
      '<text x="666" y="190" text-anchor="middle" fill="#f87171" font-size="8">local only</text>',

      // ── AMBER: Taint Stale (curves back to Human, local reauth) ──
      '<path id="path-taint-local" d="M440 128 Q400 190 200 210 Q100 220 84 130" stroke="#f59e0b" stroke-width="2" fill="none" opacity="0.1" stroke-dasharray="5 3" marker-end="url(#a-a)"/>',
      '<rect id="node-taint" x="160" y="168" width="150" height="46" rx="8" fill="#fffbeb" stroke="#fde68a" opacity="0.7"/>',
      '<text x="235" y="186" text-anchor="middle" fill="#92400e" font-size="11" font-weight="700">Taint Stale</text>',
      '<text x="235" y="200" text-anchor="middle" fill="#d97706" font-size="8">re-auth: button or passkey</text>',

      // ── AMBER: Taint server path (to lemma.id for hard passkey) ──
      '<path id="path-taint-server" d="M310 191 Q540 220 772 140" stroke="#f59e0b" stroke-width="1.5" fill="none" opacity="0.08" stroke-dasharray="3 3" marker-end="url(#a-a)"/>',
      '<text x="560" y="218" fill="#fbbf24" font-size="7" opacity="0.5">hard passkey (remote)</text>',

      // ── RED: Revoked local (below firewall) ──
      '<path id="path-revoke-local" d="M490 128 Q490 170 490 200" stroke="#ef4444" stroke-width="2" fill="none" opacity="0.1" marker-end="url(#a-r)"/>',
      '<rect id="node-revoke" x="432" y="206" width="120" height="46" rx="8" fill="#fef2f2" stroke="#fecaca" opacity="0.7"/>',
      '<text x="492" y="224" text-anchor="middle" fill="#991b1b" font-size="11" font-weight="700">Revoked</text>',
      '<text x="492" y="238" text-anchor="middle" fill="#f87171" font-size="8">local kill or remote</text>',

      // ── RED: Revoke server path (to lemma.id registry) ──
      '<path id="path-revoke-server" d="M552 229 Q660 250 772 180" stroke="#ef4444" stroke-width="1.5" fill="none" opacity="0.08" stroke-dasharray="3 3" marker-end="url(#a-r)"/>',
      '<text x="660" y="258" fill="#f87171" font-size="7" opacity="0.5">propagate to all (remote)</text>',

      // ── Sync arrows (background, from server to firewall) ──
      '<path d="M772 120 Q720 130 588 100" stroke="#c4b5fd" stroke-width="1" fill="none" stroke-dasharray="3 3" opacity="0.25" marker-end="url(#a-p)"/>',
      '<text x="660" y="134" fill="#c4b5fd" font-size="7" opacity="0.5">sync revocation + taint</text>',

      // ── Narration callout ──
      '<g id="demo-callout" opacity="0" transform="translate(480,300)">',
      '<rect x="-160" y="-16" width="320" height="32" rx="8" fill="#0f172a" opacity="0.92"/>',
      '<text id="demo-callout-text" x="0" y="2" text-anchor="middle" fill="#f1f5f9" font-size="11" font-weight="600"></text>',
      '</g>',

      // Credential status
      '<g id="demo-cred-status" opacity="0" transform="translate(266,86)">',
      '<rect x="-30" y="-9" width="60" height="18" rx="4" fill="#0f172a" opacity="0.85"/>',
      '<text id="demo-cred-status-text" x="0" y="3" text-anchor="middle" fill="#f1f5f9" font-size="9" font-weight="700"></text>',
      '</g>',

      // ── Timeline ──
      '<line x1="24" y1="340" x2="936" y2="340" stroke="#e4e4e7" stroke-width="1"/>',
      archTimeline.map(function (label, i) {
        var x = 24 + i * 228;
        return '<circle id="demo-arch-tl-' + i + '" cx="' + x + '" cy="340" r="7" fill="#fafafa" stroke="#d4d4d8" stroke-width="1.5"/>' +
          '<text x="' + x + '" y="360" text-anchor="middle" fill="#a1a1aa" font-size="10">' + label + '</text>';
      }).join(""),

      // Legend
      '<circle cx="30" cy="396" r="4" fill="#22c55e"/>',
      '<text x="40" y="400" fill="#71717a" font-size="9">Allow (local)</text>',
      '<circle cx="130" cy="396" r="4" fill="#ef4444"/>',
      '<text x="140" y="400" fill="#71717a" font-size="9">Deny / Revoke</text>',
      '<circle cx="240" cy="396" r="4" fill="#f59e0b"/>',
      '<text x="250" y="400" fill="#71717a" font-size="9">Re-auth needed</text>',
      '<circle cx="360" cy="396" r="4" fill="#8b5cf6"/>',
      '<text x="370" y="400" fill="#71717a" font-size="9">lemma.id (remote)</text>',

      '<text id="demo-diagram-state" x="480" y="420" text-anchor="middle" fill="#e4e4e7" font-size="9">state: waiting</text>',

      '</svg>',
    ].join("");

    target.innerHTML = svg;
  }

  // ── Animation ──

  function animateDot(pathId, color, dur) {
    var dot = document.getElementById("dot");
    var path = document.getElementById(pathId);
    if (!dot || !path) return;
    var gm = {"#22c55e":"g","#ef4444":"r","#f59e0b":"a","#8b5cf6":"p"};
    dot.setAttribute("fill", color);
    dot.setAttribute("filter", "url(#gl-" + (gm[color]||"g") + ")");
    dot.style.opacity = "1";
    var len = path.getTotalLength(), st = null, ms = dur || 550;
    function step(ts) {
      if (!st) st = ts;
      var p = Math.min((ts - st) / ms, 1);
      var e = p < 0.5 ? 2*p*p : 1 - Math.pow(-2*p+2,2)/2;
      var pt = path.getPointAtLength(e * len);
      dot.setAttribute("cx", pt.x); dot.setAttribute("cy", pt.y);
      if (p < 1) requestAnimationFrame(step);
      else setTimeout(function(){ dot.style.opacity = "0"; }, 350);
    }
    requestAnimationFrame(step);
  }

  function flash(id, color, dur) {
    var n = document.getElementById(id); if (!n) return;
    var o = n.getAttribute("stroke");
    n.setAttribute("stroke", color); n.setAttribute("stroke-width","3");
    setTimeout(function(){ n.setAttribute("stroke", o||"#e4e4e7"); n.setAttribute("stroke-width","1"); }, dur||1200);
  }

  function light(pathId, opacity) {
    var p = document.getElementById(pathId); if (p) p.style.opacity = String(opacity);
  }

  function showCallout(text, x, y) {
    var g = document.getElementById("demo-callout"), t = document.getElementById("demo-callout-text");
    if (!g||!t) return;
    g.setAttribute("transform","translate("+x+","+y+")");
    t.textContent = text; g.style.transition="opacity 0.2s"; g.style.opacity="1";
    setTimeout(function(){ g.style.opacity="0"; }, 3200);
  }

  function showCred(text, c) {
    var g = document.getElementById("demo-cred-status"), t = document.getElementById("demo-cred-status-text");
    if (!g||!t) return; t.textContent=text; t.setAttribute("fill",c||"#f1f5f9");
    g.style.transition="opacity 0.2s"; g.style.opacity="1";
    setTimeout(function(){ g.style.opacity="0"; }, 2200);
  }

  function resetPaths() {
    ["path-allow","path-deny","path-taint-local","path-taint-server","path-revoke-local","path-revoke-server","path-issue"].forEach(function(id){
      var p=document.getElementById(id); if(p) p.style.opacity = p.id==="path-issue"?"0.4":"0.1";
    });
  }

  window.DemoArchitecture = {
    mount: function(rootId) { renderArchitecture(document.getElementById(rootId)); },
    updateDecision: function(decision, reasonCode) {
      var st = document.getElementById("demo-diagram-state");
      if (st) st.textContent = "state: " + String(reasonCode||"pending");
      function paintTL(i,c,s){ var n=document.getElementById("demo-arch-tl-"+i); if(n){n.setAttribute("fill",c);n.setAttribute("stroke",s||c);} }
      if (archCursor<=4) { paintTL(archCursor,"#d4d4d8","#a1a1aa"); archCursor+=1; }
      resetPaths();

      if (reasonCode==="proof_issued") {
        animateDot("path-issue","#8b5cf6",700);
        flash("node-agent","#8b5cf6",1500);
        flash("node-server","#8b5cf6",1500);
        light("path-issue","0.7");
        showCred("ISSUED","#a7f3d0");
        showCallout("Credential issued from lemma.id. Ed25519 signed.",480,300);
        paintTL(Math.min(archCursor,4),"#8b5cf6","#7c3aed");
        return;
      }
      if (reasonCode==="proof_allowed"&&decision==="allow") {
        animateDot("path-allow","#22c55e",500);
        flash("node-fw","#22c55e",1200);
        flash("node-allow","#22c55e",1200);
        light("path-allow","0.8");
        showCred("VALID","#a7f3d0");
        showCallout("Verified locally by the firewall. No server call.",480,300);
        paintTL(Math.min(archCursor,4),"#22c55e","#16a34a");
        return;
      }
      if (reasonCode==="proof_taint_epoch_stale") {
        animateDot("path-taint-local","#f59e0b",700);
        flash("node-fw","#f59e0b",1500);
        flash("node-taint","#f59e0b",1500);
        flash("node-human","#f59e0b",1500);
        light("path-taint-local","0.7");
        light("path-taint-server","0.3");
        showCred("STALE","#fcd34d");
        showCallout("Taint epoch bumped. Re-auth needed (local or passkey).",480,300);
        paintTL(Math.min(archCursor,4),"#f59e0b","#d97706");
        return;
      }
      if (reasonCode==="action_not_granted"||reasonCode==="action_path_not_allowed") {
        animateDot("path-deny","#ef4444",500);
        flash("node-fw","#3b82f6",1200);
        flash("node-deny","#3b82f6",1200);
        light("path-deny","0.7");
        showCallout("Action not in credential. Blocked locally.",480,300);
        paintTL(Math.min(archCursor,4),"#3b82f6","#2563eb");
        return;
      }
      if (reasonCode==="token_revoked") {
        animateDot("path-revoke-local","#ef4444",500);
        flash("node-fw","#ef4444",1500);
        flash("node-revoke","#ef4444",1500);
        light("path-revoke-local","0.8");
        light("path-revoke-server","0.4");
        showCred("REVOKED","#fca5a5");
        showCallout("Kill switch. Local kill + propagates to lemma.id.",480,300);
        paintTL(Math.min(archCursor,4),"#ef4444","#dc2626");
        return;
      }
      if (decision==="allow") {
        animateDot("path-allow","#22c55e",500);
        flash("node-fw","#22c55e",1200);
        light("path-allow","0.8");
        showCallout("Allowed locally.",480,300);
        paintTL(Math.min(archCursor,4),"#22c55e","#16a34a");
      } else {
        animateDot("path-deny","#ef4444",500);
        flash("node-fw","#ef4444",1200);
        light("path-deny","0.7");
        showCallout("Denied.",480,300);
        paintTL(Math.min(archCursor,4),"#ef4444","#dc2626");
      }
    },
  };
})();
