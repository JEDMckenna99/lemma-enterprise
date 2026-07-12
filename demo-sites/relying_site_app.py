import logging
import os
from collections import deque
from typing import Optional

from flask import Flask, Response, jsonify, request

logger = logging.getLogger(__name__)

from lemma_ishuman_verify import InMemoryNonceStore, VerificationContext
from lemma_ishuman_site_policy import InMemorySitePolicyStore, enforce_site_policy

from presale_allocation import PresaleAllocationLedger


app = Flask(__name__)

SITE_ID = os.getenv("LEMMA_DEMO_SITE_ID", "tickets-demo.lemma.id")
SITE_NAME = os.getenv("LEMMA_DEMO_SITE_NAME", "Lemma Demo Site")
SITE_KIND = os.getenv("LEMMA_DEMO_SITE_KIND", "ticketing")
LEMMA_ORIGIN = os.getenv("LEMMA_ORIGIN", "https://lemma.id")
DEMO_HUB_URL = os.getenv("LEMMA_DEMO_HUB_URL", f"{LEMMA_ORIGIN}/demo")
DEMO_REQUIRED_ASSURANCE = os.getenv("LEMMA_DEMO_REQUIRED_ASSURANCE", "passkey").strip().lower()
PRESALE_DROP_ID = os.getenv("LEMMA_PRESALE_DROP_ID", "artist-presale-2026").strip()
PRESALE_CODE_CLAIM_ASSURANCE = os.getenv(
    "LEMMA_PRESALE_CODE_CLAIM_ASSURANCE", "ishuman"
).strip().lower()
ISHUMAN_VERIFIER_SDK_VERSION = os.getenv("ISHUMAN_VERIFIER_SDK_VERSION", "1.9.1").strip()

PRESALE_CLAIM_ACTION = "claim_presale_code"
PRESALE_CLAIM_PATH = "/api/presale/claim-code"

ACTION_LOG: deque = deque(maxlen=20)
_VERIFY_CTX: Optional[VerificationContext] = None
_CLAIM_VERIFY_CTX: Optional[VerificationContext] = None
_POLICY_STORE = InMemorySitePolicyStore()
_PRESALE_LEDGER = PresaleAllocationLedger()
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


def _claim_verify_ctx() -> VerificationContext:
    global _CLAIM_VERIFY_CTX
    if _CLAIM_VERIFY_CTX is None:
        _CLAIM_VERIFY_CTX = VerificationContext(
            site_id=SITE_ID,
            lemma_origin=LEMMA_ORIGIN,
            required_assurance=PRESALE_CODE_CLAIM_ASSURANCE,
        )
    return _CLAIM_VERIFY_CTX


def _is_presale_site() -> bool:
    return "ticket" in SITE_KIND.lower()


def _presale_claim_body(body: dict) -> dict:
    return {
        "drop_id": str(body.get("drop_id") or PRESALE_DROP_ID).strip(),
        "email": str(body.get("email") or "").strip(),
        "phone": str(body.get("phone") or "").strip(),
    }


def _content():
    if "trial" in SITE_KIND.lower():
        return {
            "eyebrow": "SaaS free trial",
            "headline": "Start a 14-day Pro workspace",
            "subhead": "Protected by Lemma — passkey proof first; IDV only when this site requires human proof assurance.",
            "primary": "Start free trial",
            "success": "Trial workspace created",
            "form": "Work email",
            "placeholder": "founder@example.com",
            "action": "start_trial",
        }
    return {
        "eyebrow": "Artist presale",
        "headline": "Get your unique presale code",
        "subhead": "RealFan-style reference — verify once as a human, receive one single-use code per drop. Phone and email stay on this site; Lemma never receives them.",
        "primary": "Verify & get code",
        "retry": "Try again with same wallet",
        "success": "Your unique code",
        "form_email": "Fan email",
        "form_phone": "Mobile number",
        "placeholder_email": "fan@example.com",
        "placeholder_phone": "+1 555 010 1234",
        "action": "claim_presale_code",
    }


@app.get("/health")
def health():
    payload = {
        "success": True,
        "site_id": SITE_ID,
        "site_name": SITE_NAME,
        "required_assurance": DEMO_REQUIRED_ASSURANCE,
        "presale_mode": _is_presale_site(),
    }
    if _is_presale_site():
        payload["presale_drop_id"] = PRESALE_DROP_ID
        payload["presale_claim_assurance"] = PRESALE_CODE_CLAIM_ASSURANCE
    return payload


@app.get("/api/demo/config")
def demo_config():
    return jsonify({
        "success": True,
        "site_id": SITE_ID,
        "lemma_origin": LEMMA_ORIGIN,
        "required_assurance": DEMO_REQUIRED_ASSURANCE,
        "demo_hub_url": DEMO_HUB_URL,
    })


def _extract_presentation(body: dict) -> Optional[dict]:
    presentation = body.get("presentation")
    if isinstance(presentation, dict):
        return presentation
    return None


@app.get("/api/demo/policy/check")
def demo_policy_check():
    ppid = (request.args.get("ppid") or "").strip()
    available, decision, err = _POLICY_STORE.check(ppid)
    return jsonify({
        "success": available,
        "blocked": decision.blocked,
        "doubt_required": decision.doubt_required,
        "reason": decision.reason or err,
        "doubt_reason": decision.doubt_reason,
    })


@app.post("/api/demo/policy/block")
def demo_policy_block():
    body = request.get_json(silent=True) or {}
    ppid = (body.get("ppid") or "").strip()
    if ppid:
        _POLICY_STORE.blocked.add(ppid)
    return jsonify({"success": True, "ppid": ppid, "blocked": True})


@app.post("/api/demo/policy/doubt")
def demo_policy_doubt():
    body = request.get_json(silent=True) or {}
    ppid = (body.get("ppid") or "").strip()
    if ppid:
        _POLICY_STORE.doubted.add(ppid)
    return jsonify({"success": True, "ppid": ppid, "doubt_required": True})


@app.post("/api/demo/policy/clear")
def demo_policy_clear():
    body = request.get_json(silent=True) or {}
    ppid = (body.get("ppid") or "").strip()
    if ppid:
        _POLICY_STORE.blocked.discard(ppid)
        _POLICY_STORE.doubted.discard(ppid)
    return jsonify({"success": True, "ppid": ppid})


@app.post("/api/demo/action")
def demo_action():
    body = request.get_json(silent=True) or {}
    ctx = _verify_ctx()
    presentation = _extract_presentation(body)
    action_name = body.get("action") or "unknown"
    if not presentation:
        result = ctx.Result(False, "presentation_missing")
    else:
        try:
            result = ctx.verify(presentation)
            if result.ok:
                available, decision, policy_reason = _POLICY_STORE.check(
                    result.ppid or ""
                )
                denial_reason = None
                if not available:
                    denial_reason = policy_reason or "site_policy_unavailable"
                elif decision.blocked:
                    denial_reason = "site_blocked"
                elif decision.doubt_required:
                    denial_reason = "doubt_required"
                if denial_reason:
                    result = ctx.Result(
                        False,
                        denial_reason,
                        ppid=result.ppid,
                        credential_id=result.credential_id,
                        issuer_did=result.issuer_did,
                        bound_site_id=result.bound_site_id,
                        assurance=result.assurance,
                    )
        except Exception:
            logger.exception("demo_action presentation verification failed")
            return jsonify({
                "success": False,
                "reason": "verify_error",
                "error": "Presentation verification failed on the server",
            }), 500
    entry = {
        "ok": result.ok,
        "ppid": result.ppid,
        "legacy_ppid": getattr(result, "legacy_ppid", None),
        "assurance": getattr(result, "assurance", None),
        "reason": result.reason,
        "action": action_name,
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


@app.get("/api/presale/status")
def presale_status():
    drop_id = (request.args.get("drop_id") or PRESALE_DROP_ID).strip()
    ppid = (request.args.get("ppid") or "").strip()
    legacy_ppid = (request.args.get("legacy_ppid") or "").strip() or None
    record = _PRESALE_LEDGER.lookup(drop_id, ppid, legacy_ppid=legacy_ppid)
    if not record:
        return jsonify({
            "success": True,
            "allocated": False,
            "drop_id": drop_id,
            "ppid": ppid or None,
        })
    return jsonify({
        "success": True,
        "allocated": True,
        "drop_id": record.drop_id,
        "ppid": record.ppid,
        "code": record.code,
        "claimed_at": record.claimed_at,
        "assurance": record.assurance,
    })


@app.post("/api/presale/claim-code")
def presale_claim_code():
    body = request.get_json(silent=True) or {}
    claim_body = _presale_claim_body(body)
    ctx = _claim_verify_ctx()
    try:
        result = ctx.verify_action_stamp(
            body,
            action=PRESALE_CLAIM_ACTION,
            method="POST",
            path=PRESALE_CLAIM_PATH,
            body=claim_body,
            required_assurance=PRESALE_CODE_CLAIM_ASSURANCE,
            nonce_store=_NONCE_STORE,
        )
    except Exception:
        logger.exception("presale claim verification failed")
        return jsonify({
            "success": False,
            "reason": "verify_error",
            "error": "Action stamp verification failed on the server",
        }), 500

    legacy_ppid = getattr(result, "legacy_ppid", None)
    entry_base = {
        "action": PRESALE_CLAIM_ACTION,
        "ppid": result.ppid,
        "legacy_ppid": legacy_ppid,
        "assurance": getattr(result, "assurance", None),
    }

    if not result.ok:
        entry = {**entry_base, "ok": False, "reason": result.reason}
        ACTION_LOG.appendleft(entry)
        return jsonify({
            "success": False,
            "reason": result.reason,
            "ppid": result.ppid,
            "action_log": list(ACTION_LOG),
        }), 403

    ok_policy, policy_reason, _decision = enforce_site_policy(
        ppid=result.ppid or "",
        policy_store=_POLICY_STORE,
        legacy_ppid=legacy_ppid,
        require_policy=True,
    )
    if not ok_policy:
        entry = {**entry_base, "ok": False, "reason": policy_reason}
        ACTION_LOG.appendleft(entry)
        return jsonify({
            "success": False,
            "reason": policy_reason,
            "ppid": result.ppid,
            "action_log": list(ACTION_LOG),
        }), 403

    claim = _PRESALE_LEDGER.claim(
        claim_body["drop_id"],
        result.ppid or "",
        legacy_ppid=legacy_ppid,
        assurance=getattr(result, "assurance", None),
    )
    if not claim.ok:
        entry = {**entry_base, "ok": False, "reason": claim.reason}
        ACTION_LOG.appendleft(entry)
        payload = {
            "success": False,
            "reason": claim.reason,
            "ppid": claim.ppid,
            "drop_id": claim.drop_id,
            "action_log": list(ACTION_LOG),
        }
        if claim.existing:
            payload["existing_code"] = claim.existing.code
        return jsonify(payload), 403

    entry = {
        **entry_base,
        "ok": True,
        "reason": "ok",
        "code": claim.code,
        "drop_id": claim.drop_id,
    }
    ACTION_LOG.appendleft(entry)
    return jsonify({
        "success": True,
        "code": claim.code,
        "drop_id": claim.drop_id,
        "ppid": claim.ppid,
        "assurance": claim.assurance,
        "claimed_at": claim.claimed_at,
        "reason": "ok",
        "action_log": list(ACTION_LOG),
    })


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
    if _is_presale_site():
        return _presale_index()
    return _generic_index()


def _generic_index():
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
    .server-receipt {{
      margin-top: 14px;
      padding: 14px;
      border-radius: 12px;
      border: 1px solid #c7d2fe;
      background: #eef2ff;
    }}
    .server-receipt strong {{ display: block; margin-bottom: 8px; color: #312e81; }}
    .server-receipt dl {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
      gap: 6px 12px;
      margin: 0;
      font-size: 12px;
    }}
    .server-receipt dt {{ margin: 0; color: #64748b; font-weight: 700; }}
    .server-receipt dd {{ margin: 0; color: #0f172a; word-break: break-all; }}
    .hub-return {{ margin-top: 14px; font-size: 13px; }}
    .hub-return a {{ color: var(--brand); font-weight: 700; text-decoration: none; }}
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
    <a href="{DEMO_HUB_URL}?from=demo" target="_blank" rel="noopener">Return to demo hub</a>
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
          <p class="tiny">Passkey unlock + continuity proof only. This site accepts <code>assurance: passkey</code> — no IDV unless you later step up to human proofs.</p>
        </div>
      </section>
      <aside class="card">
        <p class="eyebrow">Customer site view</p>
        <p class="muted">Site binding: <code id="site-id">{SITE_ID}</code></p>
        <p style="margin:12px 0 6px">Decision <span class="pill" id="status-pill">WAITING</span>
          <span class="pill" id="assurance-pill">policy: {DEMO_REQUIRED_ASSURANCE}</span></p>
        <p class="muted" id="decision-copy">Click the protected action to run the SDK.</p>
        <div class="server-receipt" id="server-receipt" hidden>
          <strong>Server verification receipt</strong>
          <dl id="server-receipt-fields"></dl>
        </div>
        <ol class="how">
          <li>SDK checks local site proof cache first.</li>
          <li>Missing proof → Lemma popup derives passkey assurance (no IDV yet).</li>
          <li>Site policy may require human proof assurance → IDV step-up, same PPID.</li>
          <li>After first site proof, later clicks reuse the cached presentation — no action-sign popup.</li>
          <li>Server verifies your presentation with offline revocation checks.</li>
          <li>Business never sees passport, selfie, or cross-site ID.</li>
        </ol>
        <details>
          <summary>Signed presentation JSON</summary>
          <pre id="presentation-json">{{}}</pre>
        </details>
        <details>
          <summary>Server-verified action log</summary>
          <pre id="action-log">[]</pre>
        </details>
        <p class="hub-return">Continue the walkthrough on the <a href="{DEMO_HUB_URL}?from=demo" target="_blank" rel="noopener">lemma.id demo hub</a> — stages 3–5 cover presentations, escalation, and doubt/revocation.</p>
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
    const presentationJson = document.getElementById('presentation-json');
    const serverReceipt = document.getElementById('server-receipt');
    const serverReceiptFields = document.getElementById('server-receipt-fields');
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
        isBlockedLocally: async (ppid) => {{
          const res = await fetch('/api/demo/policy/check?ppid=' + encodeURIComponent(ppid));
          const data = await res.json();
          return {{ blocked: !!data.blocked, doubt_required: !!data.doubt_required }};
        }},
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

    function formatDenyReason(reason) {{
      if (reason === 'site_blocked' || reason === 'revoked') {{
        return 'Persistent site revocation — fresh verification does not clear this.';
      }}
      if (reason === 'doubt_required') {{
        return 'Temporary doubt — the site requires a deliberate fresh proof.';
      }}
      if (reason === 'assurance_insufficient' || reason === 'not_ishuman') {{
        return 'Valid wallet proof, but this site policy requires stronger assurance.';
      }}
      if (reason === 'idv_cancelled') {{
        return 'Complete verification in the Lemma popup to continue.';
      }}
      return reason || 'unknown';
    }}

    function renderServerReceipt(response, serverEntry) {{
      if (!serverReceipt || !serverReceiptFields) return;
      if (!serverEntry) {{
        serverReceipt.hidden = true;
        return;
      }}
      serverReceipt.hidden = false;
      const rows = [
        ['Site binding', '{SITE_ID}'],
        ['PPID', serverEntry.ppid || response.ppid || '—'],
        ['Assurance', serverEntry.assurance || response.assurance || '—'],
        ['Server reason', serverEntry.reason || '—'],
        ['Decision', serverEntry.ok ? 'accept' : 'deny'],
        ['Action', serverEntry.action || '{copy["action"]}'],
      ];
      serverReceiptFields.innerHTML = rows.map(([label, value]) =>
        '<dt>' + label + '</dt><dd>' + value + '</dd>'
      ).join('');
    }}

    function formatVerdictPill(verified, assurance) {{
      if (!verified) return 'DENY';
      if (assurance === 'ishuman') return 'Human (ishuman)';
      if (assurance === 'passkey') return 'Verified (passkey)';
      return 'Verified';
    }}

    function formatVerdictDetail(response, serverNote, assurance) {{
      const tier = assurance || response.assurance || SITE_POLICY;
      const tierNote = tier === 'passkey'
        ? ' · continuity only — IDV not required at this tier'
        : (tier === 'ishuman' ? ' · IDV-backed human proof' : '');
      return 'policy satisfied · assurance=' + tier
        + ' · reason=' + response.reason
        + ' · ' + response.timeMs.toFixed(0) + 'ms · site-private PPID issued'
        + serverNote
        + tierNote
        + '.';
    }}

    function formatMissingProof(reason) {{
      if (reason === 'site_proof_required') {{
        return 'No human proof cached for this site yet. Click the protected action to issue one from your lemma.id.';
      }}
      if (reason === 'no_credential' || reason === 'no_ishuman_credential') {{
        return 'No lemma.id human proof yet. Click the protected action to verify once.';
      }}
      if (reason === 'wallet_locked') {{
        return 'Your lemma.id wallet is locked. Click the protected action to unlock and verify.';
      }}
      return 'No valid human proof on this device (' + (reason || 'unknown') + '). Click the protected action to verify.';
    }}

    function isDemoVerified(response) {{
      if (response.human) return true;
      if (SITE_POLICY !== 'passkey') return false;
      const okReason = response.reason === 'valid'
        || response.reason === 'session_valid'
        || response.reason === 'vc_valid';
      return okReason && !!response.ppid;
    }}

    function applyVerdict(response, {{ silent = false, requestPayload = null, serverEntry = null }} = {{}}) {{
      const verified = isDemoVerified(response);
      const assurance = response.assurance || serverEntry?.assurance || null;
      pill.textContent = formatVerdictPill(verified, assurance);
      pill.className = 'pill ' + (verified ? 'ok' : (silent ? 'checking' : 'deny'));
      setAssurancePill(assurance);
      const ppid = response.ppid || serverEntry?.ppid || '';
      renderServerReceipt(response, serverEntry);
      if (presentationJson) {{
        const presentation = requestPayload?.presentation || null;
        presentationJson.textContent = presentation
          ? JSON.stringify(presentation, null, 2)
          : '{{}}';
      }}
      if (verified) {{
        decisionCopy.textContent = '{copy["success"]}. PPID: ' + (ppid || '').slice(0, 28) + '…';
        if (!silent) {{
          const serverNote = serverEntry?.ok
            ? ' · server verified presentation'
            : '';
          decisionCard.innerHTML = '<strong>{copy["success"]}</strong><p class="tiny">'
            + formatVerdictDetail(response, serverNote, assurance)
            + '</p>';
        }}
      }} else if (!silent) {{
        const detail = formatDenyReason(response.reason);
        decisionCopy.textContent = 'Blocked. Reason: ' + response.reason;
        decisionCard.innerHTML = '<strong>Action blocked</strong><p class="tiny">reason=' + response.reason + ' — ' + detail + '</p>';
      }} else {{
        decisionCopy.textContent = formatMissingProof(response.reason);
      }}
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
          if (presentationJson) presentationJson.textContent = JSON.stringify(response, null, 2);
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
        const {{ ok, presentation, reason, timeMs }} = await verifier.verifyForBackend({{
          autoProvision: true,
          requiredAssurance: SITE_POLICY,
        }});
        const response = {{ human: !!ok, assurance: SITE_POLICY, reason, timeMs: timeMs || 0 }};
        if (ok) {{
          const email = document.getElementById('email')?.value || '';
          const requestPayload = {{
            action: '{copy["action"]}',
            email,
            at: Date.now(),
            presentation,
          }};
          const serverRes = await fetch('/api/demo/action', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(requestPayload),
          }});
          const serverRaw = await serverRes.text();
          let serverEntry;
          try {{
            serverEntry = JSON.parse(serverRaw);
          }} catch (parseErr) {{
            throw new Error(
              'Server returned non-JSON (HTTP ' + serverRes.status + '). '
              + 'Redeploy the demo site app if this persists.',
            );
          }}
          response.ppid = serverEntry.ppid || null;
          response.assurance = serverEntry.assurance || SITE_POLICY;
          await refreshActionLog();
          applyVerdict(response, {{ requestPayload, serverEntry }});
        }} else {{
          applyVerdict(response);
        }}
      }} catch (err) {{
        pill.textContent = 'ERROR';
        pill.className = 'pill deny';
        decisionCopy.textContent = 'Verification failed: ' + err.message;
        decisionCard.innerHTML = '<strong>Verification unavailable</strong><p class="tiny">' + err.message + '</p>';
        if (presentationJson) presentationJson.textContent = JSON.stringify({{ error: err.message }}, null, 2);
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


def _presale_index():
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
    button, .btn-secondary {{
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
    .btn-secondary {{
      background: #fff;
      color: var(--brand);
      border: 1px solid #c7d2fe;
    }}
    button:disabled, .btn-secondary:disabled {{ opacity: 0.65; cursor: not-allowed; }}
    .code-display {{
      margin-top: 18px;
      font-size: clamp(28px, 6vw, 40px);
      font-weight: 800;
      letter-spacing: 4px;
      text-align: center;
      padding: 16px;
      border-radius: 14px;
      background: #eef2ff;
      border: 1px solid #c7d2fe;
      color: #312e81;
    }}
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
      min-height: 100px;
    }}
    .verdict strong {{ color: #fff; display: block; margin-bottom: 6px; }}
    .verdict .tiny {{ font-size: 12px; color: #94a3b8; margin: 0; line-height: 1.45; }}
    .server-receipt {{
      margin-top: 14px;
      padding: 14px;
      border-radius: 12px;
      border: 1px solid #c7d2fe;
      background: #eef2ff;
    }}
    .server-receipt strong {{ display: block; margin-bottom: 8px; color: #312e81; }}
    .server-receipt dl {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
      gap: 6px 12px;
      margin: 0;
      font-size: 12px;
    }}
    .server-receipt dt {{ margin: 0; color: #64748b; font-weight: 700; }}
    .server-receipt dd {{ margin: 0; color: #0f172a; word-break: break-all; }}
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
    <a href="{DEMO_HUB_URL}?from=demo" target="_blank" rel="noopener">Return to demo hub</a>
  </header>
  <main>
    <div class="layout">
      <section class="card">
        <p class="eyebrow">{copy["eyebrow"]}</p>
        <h1>{copy["headline"]}</h1>
        <p class="muted">{copy["subhead"]}</p>
        <label for="email">{copy["form_email"]}</label>
        <input id="email" value="{copy["placeholder_email"]}" aria-label="{copy["form_email"]}">
        <label for="phone">{copy["form_phone"]}</label>
        <input id="phone" value="{copy["placeholder_phone"]}" aria-label="{copy["form_phone"]}">
        <p class="muted" style="margin-top:12px;font-size:13px;">Drop: <code id="drop-id">{PRESALE_DROP_ID}</code></p>
        <button id="claim-btn">{copy["primary"]}</button>
        <button type="button" class="btn-secondary" id="retry-btn">{copy["retry"]}</button>
        <div class="code-display" id="code-display" hidden>--------</div>
        <div class="verdict" id="decision-card">
          <strong>One verified person, one code</strong>
          <p class="tiny">Code issuance requires <code>assurance: ishuman</code> — wallet unlock plus live IDV. The site ledger keys allocations by <code>(drop_id, ppid)</code>, not phone or email.</p>
        </div>
      </section>
      <aside class="card">
        <p class="eyebrow">Reference integration</p>
        <p class="muted">Site binding: <code>{SITE_ID}</code></p>
        <p style="margin:12px 0 6px">Decision <span class="pill" id="status-pill">WAITING</span>
          <span class="pill" id="assurance-pill">claim: {PRESALE_CODE_CLAIM_ASSURANCE}</span></p>
        <p class="muted" id="decision-copy">Enter contact info, then claim your code.</p>
        <div class="server-receipt" id="server-receipt" hidden>
          <strong>Server verification receipt</strong>
          <dl id="server-receipt-fields"></dl>
        </div>
        <ol class="how">
          <li>Fan registers email/phone on this site only.</li>
          <li>SDK runs IDV-backed verification (<code>stampAction</code>).</li>
          <li>Server verifies action stamp + site policy offline.</li>
          <li>Ledger enforces one code per PPID per drop.</li>
          <li>Second claim with the same wallet is denied.</li>
        </ol>
        <details>
          <summary>Action stamp JSON</summary>
          <pre id="stamp-json">{{}}</pre>
        </details>
        <details>
          <summary>Claim log</summary>
          <pre id="action-log">[]</pre>
        </details>
      </aside>
    </div>
  </main>
  <script src="{LEMMA_ORIGIN}/sdk/ishuman-verifier.js?v={ISHUMAN_VERIFIER_SDK_VERSION}" crossorigin="anonymous"
    onerror="window.__lemmaSdkLoadError='ishuman-verifier failed to load from {LEMMA_ORIGIN}'"></script>
  <script>
    const DROP_ID = {PRESALE_DROP_ID!r};
    const CLAIM_ASSURANCE = {PRESALE_CODE_CLAIM_ASSURANCE!r};
    const CLAIM_PATH = {PRESALE_CLAIM_PATH!r};
    const pill = document.getElementById('status-pill');
    const assurancePill = document.getElementById('assurance-pill');
    const stampJson = document.getElementById('stamp-json');
    const actionLogEl = document.getElementById('action-log');
    const decisionCard = document.getElementById('decision-card');
    const decisionCopy = document.getElementById('decision-copy');
    const serverReceipt = document.getElementById('server-receipt');
    const serverReceiptFields = document.getElementById('server-receipt-fields');
    const codeDisplay = document.getElementById('code-display');
    let sharedVerifier = null;

    if (typeof IsHumanVerifier === 'undefined') {{
      const msg = window.__lemmaSdkLoadError
        || 'Lemma SDK did not load — check that {LEMMA_ORIGIN} is reachable.';
      decisionCopy.textContent = msg;
      document.getElementById('claim-btn').disabled = true;
      document.getElementById('retry-btn').disabled = true;
    }}

    function makeVerifier() {{
      if (sharedVerifier) return sharedVerifier;
      sharedVerifier = new IsHumanVerifier({{
        siteId: '{SITE_ID}',
        lemmaOrigin: '{LEMMA_ORIGIN}',
        autoProvision: true,
        requiredAssurance: CLAIM_ASSURANCE,
        debug: true,
        isBlockedLocally: async (ppid) => {{
          const res = await fetch('/api/demo/policy/check?ppid=' + encodeURIComponent(ppid));
          const data = await res.json();
          return {{ blocked: !!data.blocked, doubt_required: !!data.doubt_required }};
        }},
      }});
      return sharedVerifier;
    }}

    function claimPayload() {{
      return {{
        drop_id: DROP_ID,
        email: document.getElementById('email')?.value || '',
        phone: document.getElementById('phone')?.value || '',
      }};
    }}

    function formatDenyReason(reason) {{
      if (reason === 'allocation_already_claimed') {{
        return 'This verified person already received a code for this drop.';
      }}
      if (reason === 'action_nonce_reused') {{
        return 'Replay blocked — each claim needs a fresh action stamp.';
      }}
      if (reason === 'assurance_insufficient') {{
        return 'IDV-backed human proof is required before code issuance.';
      }}
      if (reason === 'idv_cancelled') {{
        return 'Complete verification in the Lemma popup to continue.';
      }}
      return reason || 'unknown';
    }}

    function renderReceipt(serverEntry) {{
      if (!serverReceipt || !serverReceiptFields || !serverEntry) {{
        if (serverReceipt) serverReceipt.hidden = true;
        return;
      }}
      serverReceipt.hidden = false;
      const rows = [
        ['Drop', serverEntry.drop_id || DROP_ID],
        ['Code', serverEntry.code || serverEntry.existing_code || '—'],
        ['PPID', serverEntry.ppid || '—'],
        ['Assurance', serverEntry.assurance || '—'],
        ['Reason', serverEntry.reason || '—'],
        ['Decision', serverEntry.success ? 'accept' : 'deny'],
      ];
      serverReceiptFields.innerHTML = rows.map(([label, value]) =>
        '<dt>' + label + '</dt><dd>' + value + '</dd>'
      ).join('');
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

    async function runClaim() {{
      if (typeof IsHumanVerifier === 'undefined') return;
      const claimBtn = document.getElementById('claim-btn');
      const retryBtn = document.getElementById('retry-btn');
      claimBtn.disabled = true;
      retryBtn.disabled = true;
      pill.textContent = 'CHECKING';
      pill.className = 'pill checking';
      decisionCard.innerHTML = '<strong>Verifying human proof…</strong><p class="tiny">Wallet unlock and live IDV when needed. Then the server issues at most one code for this PPID.</p>';
      try {{
        const verifier = makeVerifier();
        const payload = claimPayload();
        const stamped = await verifier.stampAction(payload, {{
          action: '{copy["action"]}',
          method: 'POST',
          path: CLAIM_PATH,
          requiredAssurance: CLAIM_ASSURANCE,
          autoProvision: true,
        }});
        if (stampJson) stampJson.textContent = JSON.stringify(stamped, null, 2);
        const stampMeta = stamped.lemma || {{}};
        if (!stampMeta.verified) {{
          pill.textContent = 'DENY';
          pill.className = 'pill deny';
          const reason = stampMeta.reason || 'not_verified';
          decisionCopy.textContent = 'Blocked: ' + reason;
          decisionCard.innerHTML = '<strong>Verification required</strong><p class="tiny">' + formatDenyReason(reason) + '</p>';
          if (codeDisplay) codeDisplay.hidden = true;
          return;
        }}
        const serverRes = await fetch(CLAIM_PATH, {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(stamped),
        }});
        const serverEntry = await serverRes.json();
        await refreshActionLog();
        renderReceipt(serverEntry);
        assurancePill.textContent = 'assurance: ' + (serverEntry.assurance || CLAIM_ASSURANCE);
        if (serverEntry.success && serverEntry.code) {{
          pill.textContent = 'CODE ISSUED';
          pill.className = 'pill ok';
          if (codeDisplay) {{
            codeDisplay.hidden = false;
            codeDisplay.textContent = serverEntry.code;
          }}
          decisionCopy.textContent = 'Code ' + serverEntry.code + ' bound to PPID ' + (serverEntry.ppid || '').slice(0, 24) + '…';
          decisionCard.innerHTML = '<strong>{copy["success"]}</strong><p class="tiny">Single-use code for drop '
            + (serverEntry.drop_id || DROP_ID) + '. Try again with the same wallet to see duplicate denial.</p>';
        }} else {{
          pill.textContent = 'DENY';
          pill.className = 'pill deny';
          const reason = serverEntry.reason || 'denied';
          decisionCopy.textContent = 'Blocked: ' + reason;
          decisionCard.innerHTML = '<strong>Claim denied</strong><p class="tiny">' + formatDenyReason(reason) + '</p>';
          if (codeDisplay && serverEntry.existing_code) {{
            codeDisplay.hidden = false;
            codeDisplay.textContent = serverEntry.existing_code;
          }}
        }}
      }} catch (err) {{
        pill.textContent = 'ERROR';
        pill.className = 'pill deny';
        decisionCopy.textContent = err.message;
        decisionCard.innerHTML = '<strong>Claim failed</strong><p class="tiny">' + err.message + '</p>';
      }} finally {{
        claimBtn.disabled = false;
        retryBtn.disabled = false;
      }}
    }}

    refreshActionLog();
    document.getElementById('claim-btn')?.addEventListener('click', () => runClaim());
    document.getElementById('retry-btn')?.addEventListener('click', () => runClaim());

    if (new URLSearchParams(window.location.search).get('lemma_ishuman_return') === '1') {{
      document.getElementById('claim-btn')?.click();
    }}
  </script>
</body>
</html>"""
    return Response(html, mimetype="text/html")
