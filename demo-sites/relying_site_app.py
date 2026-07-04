import os
from collections import deque
from typing import Optional

from flask import Flask, Response, jsonify, request

from lemma_ishuman_verify import VerificationContext, InMemoryNonceStore


app = Flask(__name__)

SITE_ID = os.getenv("LEMMA_DEMO_SITE_ID", "tickets-demo.lemma.id")
SITE_NAME = os.getenv("LEMMA_DEMO_SITE_NAME", "Lemma Demo Site")
SITE_KIND = os.getenv("LEMMA_DEMO_SITE_KIND", "ticketing")
LEMMA_ORIGIN = os.getenv("LEMMA_ORIGIN", "https://lemma.id")
DEMO_HUB_URL = os.getenv("LEMMA_DEMO_HUB_URL", f"{LEMMA_ORIGIN}/demo/ishuman")
DEMO_REQUIRED_ASSURANCE = os.getenv("LEMMA_DEMO_REQUIRED_ASSURANCE", "passkey").strip().lower()
ISHUMAN_VERIFIER_SDK_VERSION = os.getenv("ISHUMAN_VERIFIER_SDK_VERSION", "1.9.0").strip()

ACTION_LOG: deque = deque(maxlen=20)
_VERIFY_CTX: Optional[VerificationContext] = None
_NONCE_STORE = InMemoryNonceStore()


def _verify_ctx() -> VerificationContext:
    global _VERIFY_CTX
    if _VERIFY_CTX is None:
        _VERIFY_CTX = VerificationContext(
            site_id=SITE_ID,
            lemma_origin=LEMMA_ORIGIN,
            required_assurance=DEMO_REQUIRED_ASSURANCE,
        )
    return _VERIFY_CTX


def _content():
    if "trial" in SITE_KIND.lower():
        return {
            "eyebrow": "SaaS free trial",
            "headline": "Start a 14-day Pro workspace",
            "subhead": "Protected by Lemma — passkey proof first; IDV only when this site requires isHuman assurance.",
            "primary": "Start free trial",
            "success": "Trial workspace created",
            "form": "Work email",
            "placeholder": "founder@example.com",
            "action": "start_trial",
        }
    return {
        "eyebrow": "Ticket release",
        "headline": "Reserve 2 tickets for the drop",
        "subhead": "Protected by Lemma — passkey proof first; IDV only when this site requires isHuman assurance.",
        "primary": "Reserve tickets",
        "success": "Reservation held",
        "form": "Fan email",
        "placeholder": "fan@example.com",
        "action": "reserve_tickets",
    }


@app.get("/health")
def health():
    return {
        "success": True,
        "site_id": SITE_ID,
        "site_name": SITE_NAME,
        "required_assurance": DEMO_REQUIRED_ASSURANCE,
    }


@app.get("/api/demo/config")
def demo_config():
    return jsonify({
        "success": True,
        "site_id": SITE_ID,
        "lemma_origin": LEMMA_ORIGIN,
        "required_assurance": DEMO_REQUIRED_ASSURANCE,
        "demo_hub_url": DEMO_HUB_URL,
    })


@app.post("/api/demo/action")
def demo_action():
    body = request.get_json(silent=True) or {}
    ctx = _verify_ctx()
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else body
    action_name = (payload or {}).get("action") or (body.get("lemma") or {}).get("action")
    result = ctx.verify_action_stamp(
        body,
        action=action_name or "unknown",
        method="POST",
        path="/api/demo/action",
        body=payload or body,
        required_assurance=DEMO_REQUIRED_ASSURANCE,
        nonce_store=_NONCE_STORE,
    )
    entry = {
        "ok": result.ok,
        "ppid": result.ppid,
        "assurance": getattr(result, "assurance", None),
        "reason": result.reason,
        "action": (body.get("payload") or {}).get("action"),
    }
    ACTION_LOG.appendleft(entry)
    status = 200 if result.ok else 403
    return jsonify({
        "success": result.ok,
        "ppid": result.ppid,
        "assurance": getattr(result, "assurance", None),
        "reason": result.reason,
        "action_log": list(ACTION_LOG),
    }), status


@app.get("/api/demo/action-log")
def demo_action_log():
    return jsonify({"success": True, "entries": list(ACTION_LOG)})


@app.get("/lemma-clear")
def lemma_clear():
    """Same-origin storage wipe, designed to be embedded as a hidden iframe by
    the lemma.id demo hub's "Clear my lemma.id" button.

    Browser same-origin policy prevents lemma.id JS from touching this site's
    IndexedDB/localStorage directly. By framing this page (which runs in THIS
    origin), the demo hub can ask us to clear our own cached isHuman session +
    site proof, then we postMessage confirmation back to the parent.
    """
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Clear</title></head>
<body>
<script>
(function () {{
  var siteId = {SITE_ID!r};
  function wipe() {{
    var cleared = 0;
    try {{
      for (var i = localStorage.length - 1; i >= 0; i -= 1) {{
        var key = localStorage.key(i);
        if (key && (key.indexOf('ishuman') === 0 || key.indexOf('lemma') === 0 || key.indexOf('lemma_ishuman') === 0)) {{
          localStorage.removeItem(key);
          cleared += 1;
        }}
      }}
    }} catch (e) {{}}
    try {{ sessionStorage.clear(); }} catch (e) {{}}
    try {{ indexedDB.deleteDatabase('LemmaWallet'); }} catch (e) {{}}
    return cleared;
  }}
  var cleared = wipe();
  try {{
    if (window.parent && window.parent !== window) {{
      window.parent.postMessage({{ type: 'LEMMA_CLEAR_DONE', siteId: siteId, cleared: cleared }}, '*');
    }}
  }} catch (e) {{}}
}})();
</script>
Cleared.
</body></html>"""
    return Response(html, mimetype="text/html")


@app.get("/")
def index():
    copy = _content()
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{SITE_NAME}</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --ink: #0f172a;
      --muted: #64748b;
      --line: #e2e8f0;
      --brand: #4f46e5;
      --ok: #166534;
      --deny: #991b1b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      background: var(--bg);
      color: var(--ink);
    }}
    header {{
      background: #fff;
      border-bottom: 1px solid var(--line);
      padding: 14px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    header strong {{ font-size: 17px; }}
    header a {{ color: var(--muted); font-size: 13px; text-decoration: none; }}
    main {{ max-width: 920px; margin: 0 auto; padding: 28px 18px 48px; }}
    .layout {{ display: grid; grid-template-columns: 1.1fr .9fr; gap: 18px; }}
    .card {{
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 24px;
      box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
    }}
    .eyebrow {{
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 1.4px;
      text-transform: uppercase;
      color: var(--brand);
      margin: 0 0 8px;
    }}
    h1 {{ margin: 0 0 10px; font-size: clamp(32px, 6vw, 44px); line-height: 1.05; letter-spacing: -0.5px; }}
    .muted {{ color: var(--muted); line-height: 1.55; margin: 0; }}
    label {{ display: block; font-size: 13px; font-weight: 700; margin: 18px 0 6px; }}
    input {{
      width: 100%;
      border: 1px solid #cbd5e1;
      border-radius: 10px;
      padding: 12px;
      font-size: 15px;
    }}
    button {{
      width: 100%;
      border: 0;
      background: var(--brand);
      color: #fff;
      border-radius: 10px;
      padding: 14px 16px;
      font-weight: 800;
      font-size: 15px;
      cursor: pointer;
      margin-top: 16px;
    }}
    button:disabled {{ opacity: 0.65; cursor: not-allowed; }}
    .pill {{
      display: inline-block;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 9px;
      font-size: 11px;
      font-weight: 800;
      background: #f8fafc;
    }}
    .pill.ok {{ border-color: #86efac; background: #dcfce7; color: var(--ok); }}
    .pill.deny {{ border-color: #fca5a5; background: #fee2e2; color: var(--deny); }}
    .pill.checking {{ border-color: #fde68a; background: #fef9c3; color: #854d0e; }}
    .verdict {{
      margin-top: 18px;
      border-radius: 14px;
      padding: 16px;
      background: #0f172a;
      color: #e2e8f0;
      min-height: 120px;
    }}
    .verdict strong {{ color: #fff; display: block; margin-bottom: 6px; }}
    .verdict .tiny {{ font-size: 12px; color: #94a3b8; margin: 0; line-height: 1.45; }}
    .how {{ margin: 0; padding-left: 18px; color: var(--muted); font-size: 14px; line-height: 1.55; }}
    .how li {{ margin-bottom: 8px; }}
    code {{ font-size: 12px; background: #f1f5f9; padding: 2px 6px; border-radius: 6px; }}
    details {{ margin-top: 14px; }}
    summary {{ cursor: pointer; font-weight: 700; color: #334155; }}
    pre {{
      background: #0f172a;
      color: #dbeafe;
      padding: 12px;
      border-radius: 10px;
      overflow: auto;
      font-size: 12px;
    }}
    @media (max-width: 820px) {{ .layout {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header>
    <strong>{SITE_NAME}</strong>
    <a href="{DEMO_HUB_URL}" target="_blank" rel="noopener">Lemma demo hub</a>
  </header>
  <main>
    <div class="layout">
      <section class="card">
        <p class="eyebrow">{copy["eyebrow"]}</p>
        <h1>{copy["headline"]}</h1>
        <p class="muted">{copy["subhead"]}</p>
        <label for="email">{copy["form"]}</label>
        <input id="email" value="{copy["placeholder"]}" aria-label="{copy["form"]}">
        <button id="verify-btn">{copy["primary"]}</button>
        <div class="verdict" id="decision-card">
          <strong>What happens when you click</strong>
          <p class="tiny">Passkey unlock + continuity proof only. This site accepts <code>assurance: passkey</code> — no IDV unless you later step up to isHuman.</p>
        </div>
      </section>
      <aside class="card">
        <p class="eyebrow">Customer site view</p>
        <p class="muted">Site binding: <code id="site-id">{SITE_ID}</code></p>
        <p style="margin:12px 0 6px">Decision <span class="pill" id="status-pill">WAITING</span>
          <span class="pill" id="assurance-pill">policy: {DEMO_REQUIRED_ASSURANCE}</span></p>
        <p class="muted" id="decision-copy">Click the protected action to run the SDK.</p>
        <ol class="how">
          <li>SDK checks local site proof cache first.</li>
          <li>Missing proof → Lemma popup derives passkey assurance (no IDV yet).</li>
          <li>Site policy may require isHuman assurance → IDV step-up, same PPID.</li>
          <li>Server verifies your action stamp with offline revocation checks.</li>
          <li>Business never sees passport, selfie, or cross-site ID.</li>
        </ol>
        <details>
          <summary>Server-verified action log</summary>
          <pre id="action-log">[]</pre>
        </details>
        <details>
          <summary>SDK result object</summary>
          <pre id="result">{{}}</pre>
        </details>
      </aside>
    </div>
  </main>
  <script src="{LEMMA_ORIGIN}/sdk/ishuman-verifier.js?v={ISHUMAN_VERIFIER_SDK_VERSION}" crossorigin="anonymous"
    onerror="window.__lemmaSdkLoadError='ishuman-verifier failed to load from {LEMMA_ORIGIN}'"></script>
  <script>
    if (typeof IsHumanVerifier === 'undefined') {{
      const msg = window.__lemmaSdkLoadError
        || 'Lemma SDK (IsHumanVerifier) did not load — check network connection and that {LEMMA_ORIGIN} is reachable.';
      document.getElementById('decision-copy').textContent = msg;
      document.getElementById('verify-btn').disabled = true;
    }}
    const pill = document.getElementById('status-pill');
    const assurancePill = document.getElementById('assurance-pill');
    const result = document.getElementById('result');
    const actionLogEl = document.getElementById('action-log');
    const decisionCard = document.getElementById('decision-card');
    const decisionCopy = document.getElementById('decision-copy');
    const SITE_POLICY = '{DEMO_REQUIRED_ASSURANCE}';
    let sharedVerifier = null;
    function makeVerifier(autoProvision) {{
      if (sharedVerifier && sharedVerifier.autoProvision === autoProvision) {{
        return sharedVerifier;
      }}
      if (sharedVerifier) sharedVerifier.destroy();
      sharedVerifier = new IsHumanVerifier({{
        siteId: '{SITE_ID}',
        lemmaOrigin: '{LEMMA_ORIGIN}',
        autoProvision,
        requiredAssurance: SITE_POLICY,
        debug: true,
      }});
      sharedVerifier.autoProvision = autoProvision;
      return sharedVerifier;
    }}

    function setAssurancePill(assurance) {{
      if (!assurancePill) return;
      const label = assurance ? ('assurance: ' + assurance) : ('policy: ' + SITE_POLICY);
      assurancePill.textContent = label;
    }}

    async function refreshActionLog() {{
      if (!actionLogEl) return;
      try {{
        const res = await fetch('/api/demo/action-log');
        const data = await res.json();
        actionLogEl.textContent = JSON.stringify(data.entries || [], null, 2);
      }} catch (err) {{
        actionLogEl.textContent = '[]';
      }}
    }}

    function formatMissingProof(reason) {{
      if (reason === 'site_proof_required') {{
        return 'No isHuman proof cached for this site yet. Click the protected action to issue one from your lemma.id.';
      }}
      if (reason === 'no_credential' || reason === 'no_ishuman_credential') {{
        return 'No lemma.id human proof yet. Click the protected action to verify once.';
      }}
      if (reason === 'wallet_locked') {{
        return 'Your lemma.id wallet is locked. Click the protected action to unlock and verify.';
      }}
      return 'No valid isHuman proof on this device (' + (reason || 'unknown') + '). Click the protected action to verify.';
    }}

    function isDemoVerified(response) {{
      if (response.human) return true;
      if (SITE_POLICY !== 'passkey') return false;
      const okReason = response.reason === 'valid'
        || response.reason === 'session_valid'
        || response.reason === 'vc_valid';
      return okReason && !!response.ppid;
    }}

    function applyVerdict(response, {{ silent = false, stampedEvent = null, serverEntry = null }} = {{}}) {{
      const verified = isDemoVerified(response);
      pill.textContent = verified ? 'HUMAN' : 'DENY';
      pill.className = 'pill ' + (verified ? 'ok' : (silent ? 'checking' : 'deny'));
      setAssurancePill(response.assurance || serverEntry?.assurance);
      const lemma = stampedEvent?.lemma || null;
      const ppid = response.ppid || lemma?.ppid || '';
      if (verified) {{
        decisionCopy.textContent = '{copy["success"]}. PPID: ' + (ppid || '').slice(0, 28) + '…';
        if (!silent) {{
          const stampNote = serverEntry?.ok
            ? ' · server verified stamp (assurance=' + (serverEntry.assurance || response.assurance || '?') + ')'
            : '';
          decisionCard.innerHTML = '<strong>{copy["success"]}</strong><p class="tiny">human=true · reason=' + response.reason + ' · ' + response.timeMs.toFixed(0) + 'ms · site-private PPID issued' + stampNote + '.</p>';
        }}
      }} else if (!silent) {{
        decisionCopy.textContent = 'Blocked. Reason: ' + response.reason;
        decisionCard.innerHTML = '<strong>Action blocked</strong><p class="tiny">reason=' + response.reason + (response.reason === 'idv_cancelled' ? ' — complete verification in the Lemma popup to continue.' : '') + '</p>';
      }} else {{
        decisionCopy.textContent = formatMissingProof(response.reason);
      }}
      const payload = stampedEvent || response;
      result.textContent = JSON.stringify(payload, null, 2);
    }}

    async function runBackgroundCheck() {{
      pill.textContent = 'CHECKING';
      pill.className = 'pill checking';
      try {{
        const verifier = makeVerifier(false);
        const response = await verifier.checkStatus();
        if (isDemoVerified(response)) {{
          applyVerdict(response, {{ silent: true }});
        }} else {{
          pill.textContent = 'NO PROOF';
          pill.className = 'pill deny';
          decisionCopy.textContent = formatMissingProof(response.reason);
          result.textContent = JSON.stringify(response, null, 2);
        }}
      }} catch (err) {{
        pill.textContent = 'READY';
        pill.className = 'pill';
        decisionCopy.textContent = 'Background check skipped: ' + err.message;
      }}
    }}

    runBackgroundCheck();
    refreshActionLog();

    document.getElementById('verify-btn').addEventListener('click', async () => {{
      if (typeof IsHumanVerifier === 'undefined') {{
        pill.textContent = 'ERROR';
        pill.className = 'pill deny';
        decisionCopy.textContent = window.__lemmaSdkLoadError
          || 'Lemma SDK failed to load. Open this page in Safari/Chrome (not an in-app browser) and retry.';
        return;
      }}
      const button = document.getElementById('verify-btn');
      button.disabled = true;
      pill.textContent = 'CHECKING';
      pill.className = 'pill checking';
      decisionCard.innerHTML = '<strong>Checking Lemma wallet…</strong><p class="tiny">Continuity proof only — passkey unlock, then a signed site credential. No identity check at this assurance tier.</p>';
      try {{
        const verifier = makeVerifier(true);
        const {{ ok, ppid, assurance, presentation, reason, timeMs }} = await verifier.verifyForBackend({{
          autoProvision: true,
          requiredAssurance: SITE_POLICY,
        }});
        const response = {{ human: !!ok, ppid, assurance, reason, timeMs: timeMs || 0 }};
        if (ok) {{
          const email = document.getElementById('email')?.value || '';
          const actionPayload = {{ action: '{copy["action"]}', email, at: Date.now() }};
          const stampedEvent = await verifier.stampAction(actionPayload, {{
            action: '{copy["action"]}',
            method: 'POST',
            path: '/api/demo/action',
            requiredAssurance: SITE_POLICY,
          }});
          const serverRes = await fetch('/api/demo/action', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(stampedEvent),
          }});
          const serverEntry = await serverRes.json();
          await refreshActionLog();
          applyVerdict(response, {{ stampedEvent, serverEntry }});
        }} else {{
          applyVerdict(response);
        }}
      }} catch (err) {{
        pill.textContent = 'ERROR';
        pill.className = 'pill deny';
        decisionCopy.textContent = 'Verification failed: ' + err.message;
        decisionCard.innerHTML = '<strong>Verification unavailable</strong><p class="tiny">' + err.message + '</p>';
        result.textContent = JSON.stringify({{ error: err.message }}, null, 2);
      }} finally {{
        button.disabled = false;
      }}
    }});

    if (new URLSearchParams(window.location.search).get('lemma_ishuman_return') === '1') {{
      document.getElementById('verify-btn')?.click();
    }}
  </script>
</body>
</html>"""
    return Response(html, mimetype="text/html")
