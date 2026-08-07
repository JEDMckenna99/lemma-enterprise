import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from collections import deque
from typing import Any, Optional
from urllib.parse import urlparse

from flask import Flask, Response, g, jsonify, make_response, redirect, request

logger = logging.getLogger(__name__)

from lemma_proof_verifier import (
    InMemoryNonceStore,
    VerificationContext,
    build_action_commitment,
    hash_action_body,
)
from lemma_proof_verifier_site_policy import InMemorySitePolicyStore, enforce_site_policy

from presale_allocation import create_presale_stores


app = Flask(__name__)

SITE_ID = os.getenv(
    "LEMMA_DEMO_SITE_ID",
    "lemma-demo-tickets-1d3d7411af33.herokuapp.com",
)
SITE_NAME = os.getenv("LEMMA_DEMO_SITE_NAME", "Lemma Demo Site")
SITE_KIND = os.getenv("LEMMA_DEMO_SITE_KIND", "ticketing")
LEMMA_ORIGIN = os.getenv("LEMMA_ORIGIN", "https://lemma.id")
# Builder / integration hub (not /demo — that dogfood front door redirects
# signed-in users to /app).
DEMO_HUB_URL = os.getenv("LEMMA_DEMO_HUB_URL", f"{LEMMA_ORIGIN}/demo/how-it-works")
TRIALS_DEMO_URL = os.getenv(
    "LEMMA_DEMO_TRIALS_URL",
    "https://lemma-demo-trials-7090f46cae0d.herokuapp.com",
)

_PLAIN_LANGUAGE_JS = """
function formatDenyReason(reason) {
  if (window.LemmaDemoPlain && typeof window.LemmaDemoPlain.reason === 'function') {
    return window.LemmaDemoPlain.reason(reason);
  }
  const key = String(reason || '').trim();
  if (key === 'allocation_already_claimed') {
    return "You already got your code — it's one per person.";
  }
  if (key === 'trial_already_used') {
    return 'You already activated your free workspace — free trials are one per person.';
  }
  return key || 'Something went wrong — try again.';
}
function plainAssurance(tier) {
  if (window.LemmaDemoPlain && typeof window.LemmaDemoPlain.assurance === 'function') {
    return window.LemmaDemoPlain.assurance(tier);
  }
  return tier || '';
}
"""
DEMO_REQUIRED_ASSURANCE = os.getenv("LEMMA_DEMO_REQUIRED_ASSURANCE", "passkey").strip().lower()
PRESALE_DROP_ID = os.getenv("LEMMA_PRESALE_DROP_ID", "artist-presale-2026").strip()
PRESALE_CODE_CLAIM_ASSURANCE = os.getenv(
    "LEMMA_PRESALE_CODE_CLAIM_ASSURANCE", "ishuman"
).strip().lower()
PRESALE_ESCALATED_ASSURANCE = os.getenv(
    "LEMMA_PRESALE_ESCALATED_ASSURANCE", "ishuman"
).strip().lower()
TRIAL_ACTION = "start_trial"
TRIAL_DROP_ID = os.getenv("LEMMA_TRIAL_DROP_ID", "northstar-free-trial").strip()
TRIAL_REQUIRED_ASSURANCE = os.getenv(
    "LEMMA_TRIAL_REQUIRED_ASSURANCE", "ishuman"
).strip().lower()
ISHUMAN_VERIFIER_SDK_VERSION = os.getenv("ISHUMAN_VERIFIER_SDK_VERSION", "1.9.4").strip()
SESSION_SECRET = os.getenv("SESSION_SECRET", "lemma-demo-site-session-dev-secret")
SESSION_COOKIE = "lemma_demo_session"
SESSION_MAX_AGE = int(os.getenv("LEMMA_DEMO_SESSION_MAX_AGE", "86400"))
DEMO_CONTROL_SECRET = os.getenv("LEMMA_DEMO_CONTROL_SECRET", "").strip()

TICKETING_ICON_SVG = """<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
  <rect x="6.8" y="3.4" width="13.6" height="8.4" rx="1.4" stroke="#d97706" stroke-width="1.6" opacity="0.5" transform="rotate(8 13.6 7.6)"/>
  <rect x="3.6" y="10.6" width="14.8" height="9" rx="1.5" stroke="#d97706" stroke-width="1.6"/>
  <path d="M13.8 10.6v9" stroke="#d97706" stroke-width="1.4" stroke-dasharray="1.8 2"/>
</svg>"""

TICKETING_FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none">
  <rect x=".5" y=".5" width="31" height="31" rx="7.5" fill="#fffbeb" stroke="#fde68a"/>
  <g transform="translate(4 4)">
    <rect x="6.8" y="3.4" width="13.6" height="8.4" rx="1.4" stroke="#d97706" stroke-width="1.6" opacity="0.5" transform="rotate(8 13.6 7.6)"/>
    <rect x="3.6" y="10.6" width="14.8" height="9" rx="1.5" stroke="#d97706" stroke-width="1.6"/>
    <path d="M13.8 10.6v9" stroke="#d97706" stroke-width="1.4" stroke-dasharray="1.8 2"/>
  </g>
</svg>"""

TRIALS_ICON_SVG = """<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
  <path d="M7 17.5h10a3 3 0 0 0 .2-6 4.5 4.5 0 0 0-8.7-1.5A3.5 3.5 0 0 0 7 17.5Z" stroke="#16a34a" stroke-width="1.8"/>
</svg>"""

TRIALS_FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none">
  <rect x=".5" y=".5" width="31" height="31" rx="7.5" fill="#f0fdf4" stroke="#bbf7d0"/>
  <g transform="translate(4 4)">
    <path d="M7 17.5h10a3 3 0 0 0 .2-6 4.5 4.5 0 0 0-8.7-1.5A3.5 3.5 0 0 0 7 17.5Z" stroke="#16a34a" stroke-width="1.8"/>
  </g>
</svg>"""

LEMMA_SIGNIN_CSS = """
    lemma-signin { display: block; width: 100%; margin-top: 16px; }
    lemma-signin::part(button) {
      width: 100%;
      background: #1A1A24;
      box-shadow: none;
    }
    lemma-signin::part(button):hover:not(:disabled) { background: #32313F; }
"""

SITE_CTA_CSS = """
    button.site-cta, .site-cta {
      background: var(--accent);
      color: #fff;
    }
    button.site-cta:hover:not(:disabled) {
      filter: brightness(0.95);
    }
    .gated-section {
      margin-top: 18px;
      padding-top: 18px;
      border-top: 1px solid var(--line);
    }
    .gated-section[hidden] { display: none; }
    .site-brand { display: flex; align-items: center; gap: 10px; }
    .site-icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 42px;
      height: 42px;
      flex: 0 0 42px;
      border: 1px solid var(--icon-border);
      border-radius: 10px;
      background: var(--icon-bg);
    }
    .site-icon svg { width: 28px; height: 28px; }
"""


def _site_theme() -> dict[str, str]:
    if "trial" in SITE_KIND.lower():
        return {
            "accent": "#16a34a",
            "bg": "#f0fdf4",
            "icon_border": "#bbf7d0",
            "icon_bg": "#f0fdf4",
            "icon_svg": TRIALS_ICON_SVG,
            "favicon_svg": TRIALS_FAVICON_SVG,
        }
    return {
        "accent": "#d97706",
        "bg": "#fffbeb",
        "icon_border": "#fde68a",
        "icon_bg": "#fffbeb",
        "icon_svg": TICKETING_ICON_SVG,
        "favicon_svg": TICKETING_FAVICON_SVG,
    }


def _theme_css_root() -> str:
    theme = _site_theme()
    return f"""
    :root {{
      --bg: {theme["bg"]};
      --ink: #0f172a;
      --muted: #64748b;
      --line: #e2e8f0;
      --brand: {theme["accent"]};
      --accent: {theme["accent"]};
      --ok: #166534;
      --deny: #991b1b;
      --icon-border: {theme["icon_border"]};
      --icon-bg: {theme["icon_bg"]};
    }}"""


def _site_display_name() -> str:
    return "Northstar" if "trial" in SITE_KIND.lower() else "Encore"


def _site_header(links_html: str) -> str:
    theme = _site_theme()
    return f"""  <header>
    <div class="site-brand">
      <span class="site-icon">{theme["icon_svg"]}</span>
      <strong>{_site_display_name()}</strong>
    </div>
    {links_html}
  </header>"""

PRESALE_REGISTER_ACTION = "register_presale"
PRESALE_REGISTER_PATH = "/api/presale/register"
PRESALE_CLAIM_ACTION = "claim_presale_code"
PRESALE_CLAIM_PATH = "/api/presale/claim-code"

ACTION_LOG: deque = deque(maxlen=20)
_VERIFY_CTX: Optional[VerificationContext] = None
_CLAIM_VERIFY_CTX: Optional[VerificationContext] = None
_TRIAL_VERIFY_CTX: Optional[VerificationContext] = None
_POLICY_STORE = InMemorySitePolicyStore()
_PRESALE_REGISTRATIONS, _PRESALE_LEDGER = create_presale_stores()
_NONCE_STORE = InMemoryNonceStore()
_CHALLENGE_STORE: dict[str, dict] = {}
_RATE_BUCKETS: dict[str, deque] = {}


def _sign_session(ppid: str, assurance: str = "") -> str:
    payload = {
        "ppid": ppid,
        "assurance": assurance or DEMO_REQUIRED_ASSURANCE,
        "exp": int(time.time()) + SESSION_MAX_AGE,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode().hex()
    sig = hmac.new(SESSION_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def _read_session(token: str | None) -> Optional[dict[str, Any]]:
    if not token or "." not in token:
        return None
    raw, sig = token.rsplit(".", 1)
    expected = hmac.new(SESSION_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        payload = json.loads(bytes.fromhex(raw).decode())
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("exp") or 0) < int(time.time()):
        return None
    ppid = payload.get("ppid")
    if not ppid:
        return None
    return {
        "ppid": str(ppid),
        "assurance": str(payload.get("assurance") or DEMO_REQUIRED_ASSURANCE),
    }


def _session_from_request() -> Optional[dict[str, Any]]:
    return _read_session(request.cookies.get(SESSION_COOKIE))


def _set_session_cookie(response, ppid: str, assurance: str = "") -> None:
    response.set_cookie(
        SESSION_COOKIE,
        _sign_session(ppid, assurance),
        httponly=True,
        samesite="Lax",
        secure=request.is_secure,
        max_age=SESSION_MAX_AGE,
    )


def _clear_session_cookie(response) -> None:
    response.delete_cookie(SESSION_COOKIE)


def _apply_policy_to_result(ctx: VerificationContext, result) -> tuple:
    if not result.ok:
        return result, None
    available, decision, policy_reason = _POLICY_STORE.check(result.ppid or "")
    if not available:
        return ctx.Result(
            False,
            policy_reason or "site_policy_unavailable",
            ppid=result.ppid,
            credential_id=result.credential_id,
            issuer_did=result.issuer_did,
            bound_site_id=result.bound_site_id,
            assurance=getattr(result, "assurance", None),
        ), "session_cleared"
    if decision.blocked:
        return ctx.Result(
            False,
            "site_blocked",
            ppid=result.ppid,
            credential_id=result.credential_id,
            issuer_did=result.issuer_did,
            bound_site_id=result.bound_site_id,
            assurance=getattr(result, "assurance", None),
        ), "session_cleared"
    if decision.doubt_required:
        return ctx.Result(
            False,
            "doubt_required",
            ppid=result.ppid,
            credential_id=result.credential_id,
            issuer_did=result.issuer_did,
            bound_site_id=result.bound_site_id,
            assurance=getattr(result, "assurance", None),
        ), None
    return result, None


def _verify_control_hmac(body: dict) -> bool:
    if not DEMO_CONTROL_SECRET:
        return False
    signature = (request.headers.get("X-Demo-Control-Signature") or "").strip()
    if not signature:
        return False
    payload = json.dumps(body or {}, separators=(",", ":"), sort_keys=True).encode()
    expected = hmac.new(
        DEMO_CONTROL_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


def _authorize_policy_mutation(target_ppid: str, body: dict | None = None) -> Optional[tuple]:
    ppid = (target_ppid or "").strip()
    if not ppid:
        return jsonify({"success": False, "reason": "ppid_required"}), 400
    session = _session_from_request()
    if session and session["ppid"] == ppid:
        return None
    if _verify_control_hmac(body or {"ppid": ppid}):
        return None
    return jsonify({"success": False, "reason": "demo_policy_unauthorized"}), 403


@app.before_request
def load_demo_session():
    g.demo_session = _session_from_request()


def _client_ip() -> str:
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return forwarded or (request.remote_addr or "unknown")


def _rate_limit(key: str, *, limit: int, window_seconds: int) -> bool:
    """Return True when under limit, False when exceeded."""
    now = time.time()
    bucket = _RATE_BUCKETS.setdefault(key, deque())
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


def _issue_presale_challenge(action: str, method: str, path: str, body: dict) -> dict:
    server_nonce = secrets.token_urlsafe(16)
    body_hash = hash_action_body(body)
    action_commitment = build_action_commitment(
        server_nonce=server_nonce,
        site_id=SITE_ID,
        action=action,
        method=method,
        path=path,
        body_hash=body_hash,
    )
    _CHALLENGE_STORE[server_nonce] = {
        "action": action,
        "method": method,
        "path": path,
        "body_hash": body_hash,
        "action_commitment": action_commitment,
        "issued_at": time.time(),
    }
    return {
        "server_nonce": server_nonce,
        "action_commitment": action_commitment,
        "body_hash": body_hash,
    }


def _verify_ctx() -> VerificationContext:
    global _VERIFY_CTX
    if _VERIFY_CTX is None:
        _VERIFY_CTX = VerificationContext(
            site_id=SITE_ID,
            lemma_origin=LEMMA_ORIGIN,
            required_assurance=DEMO_REQUIRED_ASSURANCE,
            nonce_store_mode="required",
        )
    return _VERIFY_CTX


def _claim_verify_ctx() -> VerificationContext:
    global _CLAIM_VERIFY_CTX
    if _CLAIM_VERIFY_CTX is None:
        _CLAIM_VERIFY_CTX = VerificationContext(
            site_id=SITE_ID,
            lemma_origin=LEMMA_ORIGIN,
            required_assurance=PRESALE_CODE_CLAIM_ASSURANCE,
            nonce_store_mode="required",
        )
    return _CLAIM_VERIFY_CTX


def _trial_verify_ctx() -> VerificationContext:
    global _TRIAL_VERIFY_CTX
    if _TRIAL_VERIFY_CTX is None:
        _TRIAL_VERIFY_CTX = VerificationContext(
            site_id=SITE_ID,
            lemma_origin=LEMMA_ORIGIN,
            required_assurance=TRIAL_REQUIRED_ASSURANCE,
            nonce_store_mode="required",
        )
    return _TRIAL_VERIFY_CTX


def _is_presale_site() -> bool:
    return "ticket" in SITE_KIND.lower()


def _presale_claim_body(body: dict) -> dict:
    return {
        "drop_id": str(body.get("drop_id") or PRESALE_DROP_ID).strip(),
        "email": str(body.get("email") or "").strip(),
        "phone": str(body.get("phone") or "").strip(),
    }


def _resolve_claim_assurance(body: dict) -> str:
    requested = str(body.get("required_assurance") or PRESALE_CODE_CLAIM_ASSURANCE).strip().lower()
    if requested in ("passkey", "ishuman"):
        return requested
    return PRESALE_CODE_CLAIM_ASSURANCE


def _presale_register_body(body: dict) -> dict:
    base = _presale_claim_body(body)
    return base


_STAMP_GATE_CHAIN = ("action_stamp", "site_binding", "nonce_consumed", "assurance")
_FRESH_PASSKEY_GATE = "fresh_passkey_attestation"
_REASON_FAILED_GATE = {
    "action_stamp_missing": "action_stamp",
    "action_stamp_incomplete": "action_stamp",
    "invalid_action_signature": "action_stamp",
    "action_name_mismatch": "action_stamp",
    "action_method_mismatch": "action_stamp",
    "action_path_mismatch": "action_stamp",
    "action_site_id_mismatch": "site_binding",
    "action_body_hash_mismatch": "action_stamp",
    "action_nonce_reused": "nonce_consumed",
    "action_nonce_missing": "nonce_consumed",
    "assurance_insufficient": "assurance",
    "fresh_passkey_missing": _FRESH_PASSKEY_GATE,
    "fresh_passkey_expired": _FRESH_PASSKEY_GATE,
    "fresh_passkey_too_old": _FRESH_PASSKEY_GATE,
    "fresh_passkey_invalid_signature": _FRESH_PASSKEY_GATE,
    "fresh_passkey_signature_missing": _FRESH_PASSKEY_GATE,
    "fresh_passkey_server_nonce_missing": _FRESH_PASSKEY_GATE,
}


def _presale_gate_report(
    *,
    phase: str,
    success: bool,
    reason: str,
    require_fresh_passkey: bool = False,
) -> dict:
    """Summarize which verification gates passed or failed for demo receipts."""
    stamp_chain = list(_STAMP_GATE_CHAIN)
    if require_fresh_passkey:
        stamp_chain.append(_FRESH_PASSKEY_GATE)

    if success:
        passed = list(stamp_chain)
        passed.append("registration_stored" if phase == "register" else "ledger_claim")
        return {"gates_passed": passed}

    reason = str(reason or "unknown").strip()
    if reason == "rate_limited":
        return {"gates_passed": [], "gate_failed": reason}

    failed_gate = _REASON_FAILED_GATE.get(reason)
    if failed_gate and failed_gate in stamp_chain:
        idx = stamp_chain.index(failed_gate)
        passed = list(stamp_chain[:idx])
    elif reason in (
        "registration_required",
        "doubt_required",
        "allocation_already_claimed",
        "site_blocked",
        "site_policy_unavailable",
    ):
        passed = list(stamp_chain)
    elif reason.startswith("fresh_passkey_"):
        passed = list(_STAMP_GATE_CHAIN)
    else:
        passed = []

    return {"gates_passed": passed, "gate_failed": reason}


def _signin_content():
    if "trial" in SITE_KIND.lower():
        return {
            "eyebrow": "Northstar workspace",
            "headline": "Your work, moving forward.",
            "subhead": "Plan projects, share updates, and keep your team in sync.",
            "primary": "Activate free workspace",
            "trial_eyebrow": "Founding team offer",
            "trial_subhead": "Free workspaces are limited to one per person. Verify you are human to activate yours — Northstar never receives your identity documents.",
            "success": "Workspace activated",
            "form": "Workspace name",
            "placeholder": "Acme Studio",
            "action": TRIAL_ACTION,
        }
    return {
        "eyebrow": "Sign in with lemma.id",
        "headline": "Sign in to this demo site",
        "subhead": "Same integration as the docs quickstart: drop in the lemma-signin element, verify the presentation on your backend, issue a session cookie. When you need Sybil-resistant enforcement, open the presale tour.",
        "primary": "Run protected action",
        "success": "Action completed",
        "form": "Note (optional)",
        "placeholder": "Signed in demo",
        "action": "demo_action",
        "presale_link": True,
    }


def _presale_content():
    return {
        "eyebrow": "Unique presale code distributor",
        "headline": "Passkey proves who you are",
        "subhead": "Join the drop with a passkey register — no email or password. Reveal your one-time code with verified-human confirmation and a fresh passkey. Contact info is optional delivery after you claim. No SMS OTP.",
        "register": "Step 1, Passkey register for drop",
        "claim": "Confirm and reveal code",
        "retry": "Request another code",
        "flag": "Simulate site risk flag",
        "clear_flag": "Clear risk flag",
        "clear_claim": "Clear claim (demo reset)",
        "success_register": "Registered for presale",
        "success": "Your unique code",
        "form_email": "Email for code delivery",
        "form_phone": "Mobile for SMS alerts",
        "placeholder_email": "fan@example.com",
        "placeholder_phone": "+1 555 010 1234",
        "register_action": "register_presale",
        "claim_action": "claim_presale_code",
    }


def _content():
    return _signin_content()


def _sdk_script_tags() -> str:
    return (
        f'<script src="{LEMMA_ORIGIN}/sdk/proof-verifier.js?v={ISHUMAN_VERIFIER_SDK_VERSION}" '
        f'crossorigin="anonymous" '
        f'onerror="window.__lemmaSdkLoadError=\'proof-verifier failed to load from {LEMMA_ORIGIN}\'"></script>\n'
        f'  <script src="{LEMMA_ORIGIN}/sdk/lemma-signin.js?v={ISHUMAN_VERIFIER_SDK_VERSION}" '
        f'crossorigin="anonymous" '
        f'onerror="window.__lemmaSdkLoadError=\'lemma-signin failed to load from {LEMMA_ORIGIN}\'"></script>\n'
        f'  <script src="{LEMMA_ORIGIN}/static/js/demo/plain-language.js?v=1"></script>'
    )


def _lemma_signin_element() -> str:
    return (
        f'<lemma-signin id="lemma-signin-btn" site-id="{SITE_ID}" '
        f'required-assurance="{DEMO_REQUIRED_ASSURANCE}" auto-provision="true" '
        f'lemma-origin="{LEMMA_ORIGIN}"></lemma-signin>'
    )


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
        payload["presale_escalated_assurance"] = PRESALE_ESCALATED_ASSURANCE
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


@app.get("/api/me")
def demo_me():
    session = getattr(g, "demo_session", None) or _session_from_request()
    if not session:
        return jsonify({"success": False, "error": "auth_required"}), 401
    return jsonify({
        "success": True,
        "ppid": session["ppid"],
        "assurance": session.get("assurance"),
        "site_id": SITE_ID,
    })


@app.post("/api/login")
def demo_login():
    body = request.get_json(silent=True) or {}
    presentation = _extract_presentation(body)
    if not presentation:
        return jsonify({"success": False, "reason": "presentation_missing"}), 400
    ctx = _verify_ctx()
    try:
        result = ctx.verify(presentation)
        result, clear_session = _apply_policy_to_result(ctx, result)
    except Exception:
        logger.exception("demo login presentation verification failed")
        return jsonify({"success": False, "reason": "verify_error"}), 500
    if not result.ok:
        resp = make_response(jsonify({
            "success": False,
            "reason": result.reason,
            "ppid": result.ppid,
        }))
        if clear_session == "session_cleared":
            _clear_session_cookie(resp)
        return resp, 401

    assurance = getattr(result, "assurance", None) or DEMO_REQUIRED_ASSURANCE
    resp = make_response(jsonify({
        "success": True,
        "ppid": result.ppid,
        "assurance": assurance,
        "site_id": SITE_ID,
    }))
    _set_session_cookie(resp, result.ppid or "", assurance)
    return resp


@app.post("/api/logout")
@app.get("/api/logout")
def demo_logout():
    resp = make_response(jsonify({"success": True}))
    _clear_session_cookie(resp)
    return resp


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
    denied = _authorize_policy_mutation(ppid, body)
    if denied:
        return denied
    if ppid:
        _POLICY_STORE.blocked.add(ppid)
    return jsonify({"success": True, "ppid": ppid, "blocked": True})


@app.post("/api/demo/policy/doubt")
def demo_policy_doubt():
    body = request.get_json(silent=True) or {}
    ppid = (body.get("ppid") or "").strip()
    denied = _authorize_policy_mutation(ppid, body)
    if denied:
        return denied
    if ppid:
        _POLICY_STORE.doubted.add(ppid)
    return jsonify({"success": True, "ppid": ppid, "doubt_required": True})


@app.post("/api/demo/policy/clear")
def demo_policy_clear():
    body = request.get_json(silent=True) or {}
    ppid = (body.get("ppid") or "").strip()
    denied = _authorize_policy_mutation(ppid, body)
    if denied:
        return denied
    if ppid:
        _POLICY_STORE.blocked.discard(ppid)
        _POLICY_STORE.doubted.discard(ppid)
    return jsonify({"success": True, "ppid": ppid})


@app.get("/api/demo/trial/status")
def demo_trial_status():
    session = getattr(g, "demo_session", None) or _session_from_request()
    if not session:
        return jsonify({"success": False, "reason": "auth_required"}), 403
    record = _PRESALE_LEDGER.lookup(TRIAL_DROP_ID, session["ppid"])
    return jsonify({
        "success": True,
        "activated": bool(record),
        "activated_at": record.claimed_at if record else None,
        "ppid": session["ppid"],
    })


@app.post("/api/demo/trial/reset")
def demo_trial_reset():
    """Demo-only: release this PPID's trial activation so the flow can be replayed."""
    body = request.get_json(silent=True) or {}
    ppid = (body.get("ppid") or "").strip()
    denied = _authorize_policy_mutation(ppid, body)
    if denied:
        return denied
    removed = _PRESALE_LEDGER.clear_claim(TRIAL_DROP_ID, ppid)
    return jsonify({
        "success": True,
        "ppid": ppid,
        "cleared": removed > 0,
        "removed": removed,
    })


@app.post("/api/demo/presale/clear-claim")
def demo_presale_clear_claim():
    """Demo-only: release this PPID's allocated code so the claim flow can be replayed."""
    if not _is_presale_site():
        return jsonify({"success": False, "reason": "presale_only"}), 404
    body = request.get_json(silent=True) or {}
    ppid = (body.get("ppid") or "").strip()
    denied = _authorize_policy_mutation(ppid, body)
    if denied:
        return denied
    drop_id = (body.get("drop_id") or PRESALE_DROP_ID).strip() or PRESALE_DROP_ID
    legacy_ppid = (body.get("legacy_ppid") or "").strip() or None
    removed = _PRESALE_LEDGER.clear_claim(drop_id, ppid, legacy_ppid=legacy_ppid)
    return jsonify({
        "success": True,
        "ppid": ppid,
        "drop_id": drop_id,
        "cleared": removed > 0,
        "removed": removed,
    })


@app.post("/api/demo/action")
def demo_action():
    body = request.get_json(silent=True) or {}
    presentation = _extract_presentation(body)
    action_name = body.get("action") or "unknown"
    clear_session = None

    if action_name == TRIAL_ACTION:
        if not presentation:
            entry = {
                "ok": False,
                "ppid": None,
                "assurance": None,
                "reason": "human_proof_required",
                "action": action_name,
            }
            ACTION_LOG.appendleft(entry)
            return jsonify({
                "success": False,
                "reason": "human_proof_required",
                "action_log": list(ACTION_LOG),
            }), 403
        ctx = _trial_verify_ctx()
        try:
            result = ctx.verify(presentation)
            result, clear_session = _apply_policy_to_result(ctx, result)
        except Exception:
            logger.exception("demo_action trial verification failed")
            return jsonify({
                "success": False,
                "reason": "verify_error",
                "error": "Presentation verification failed on the server",
            }), 500
        if result.ok:
            # One free trial per verified person: the PPID ledger is the
            # integrator-side dedupe, exactly like the presale code ledger.
            claim = _PRESALE_LEDGER.claim(
                TRIAL_DROP_ID,
                result.ppid or "",
                legacy_ppid=getattr(result, "legacy_ppid", None),
                assurance=getattr(result, "assurance", None),
            )
            if not claim.ok and claim.reason == "allocation_already_claimed":
                entry = {
                    "ok": False,
                    "ppid": result.ppid,
                    "assurance": getattr(result, "assurance", None),
                    "reason": "trial_already_used",
                    "action": action_name,
                }
                ACTION_LOG.appendleft(entry)
                return jsonify({
                    "success": False,
                    "reason": "trial_already_used",
                    "ppid": result.ppid,
                    "activated_at": claim.existing.claimed_at if claim.existing else None,
                    "action_log": list(ACTION_LOG),
                }), 403
    elif presentation:
        ctx = _verify_ctx()
        try:
            result = ctx.verify(presentation)
            result, clear_session = _apply_policy_to_result(ctx, result)
        except Exception:
            logger.exception("demo_action presentation verification failed")
            return jsonify({
                "success": False,
                "reason": "verify_error",
                "error": "Presentation verification failed on the server",
            }), 500
    else:
        ctx = _verify_ctx()
        session = getattr(g, "demo_session", None) or _session_from_request()
        if not session:
            result = ctx.Result(False, "auth_required")
        else:
            result = ctx.Result(
                True,
                "session_valid",
                ppid=session["ppid"],
                assurance=session.get("assurance"),
            )
            result, clear_session = _apply_policy_to_result(ctx, result)
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
    resp = make_response(jsonify({
        "success": result.ok,
        "ppid": result.ppid,
        "assurance": getattr(result, "assurance", None),
        "reason": result.reason,
        "action_log": list(ACTION_LOG),
    }), status)
    if clear_session == "session_cleared":
        _clear_session_cookie(resp)
    return resp


@app.get("/api/demo/action-log")
def demo_action_log():
    return jsonify({"success": True, "entries": list(ACTION_LOG)})


@app.post("/api/presale/challenge")
def presale_challenge():
    body = request.get_json(silent=True) or {}
    action = str(body.get("action") or PRESALE_REGISTER_ACTION).strip()
    method = str(body.get("method") or "POST").strip().upper()
    path = str(body.get("path") or PRESALE_REGISTER_PATH).strip()
    payload = body.get("body") if isinstance(body.get("body"), dict) else _presale_register_body(body)
    if not _rate_limit(f"challenge:{_client_ip()}", limit=30, window_seconds=60):
        return jsonify({"success": False, "reason": "rate_limited"}), 429
    issued = _issue_presale_challenge(action, method, path, payload)
    return jsonify({"success": True, "site_id": SITE_ID, **issued})


@app.post("/api/presale/status")
def presale_status():
    body = request.get_json(silent=True) or {}
    drop_id = (body.get("drop_id") or PRESALE_DROP_ID).strip()
    presentation = _extract_presentation(body)
    session = getattr(g, "demo_session", None) or _session_from_request()
    if not presentation and not session:
        return jsonify({"success": False, "reason": "auth_required"}), 403
    if not _rate_limit(f"status:{_client_ip()}", limit=20, window_seconds=60):
        return jsonify({"success": False, "reason": "rate_limited"}), 429
    if presentation:
        try:
            result = _verify_ctx().verify_with_policy(
                presentation,
                policy_store=_POLICY_STORE,
                require_policy=True,
            )
        except Exception:
            logger.exception("presale status verification failed")
            return jsonify({"success": False, "reason": "verify_error"}), 500
        if not result.ok:
            return jsonify({"success": False, "reason": result.reason}), 403
        ppid = result.ppid or ""
        assurance = getattr(result, "assurance", None)
        legacy_ppid = getattr(result, "legacy_ppid", None)
    else:
        ppid = session["ppid"]
        assurance = session.get("assurance")
        legacy_ppid = None
        ok_policy, policy_reason, _decision = enforce_site_policy(
            ppid=ppid,
            policy_store=_POLICY_STORE,
            require_policy=True,
        )
        if not ok_policy:
            resp = make_response(jsonify({"success": False, "reason": policy_reason}), 403)
            if policy_reason in ("site_blocked", "doubt_required"):
                _clear_session_cookie(resp)
            return resp
    record = _PRESALE_LEDGER.lookup(drop_id, ppid, legacy_ppid=legacy_ppid)
    registered = _PRESALE_REGISTRATIONS.is_registered(
        drop_id,
        ppid,
        legacy_ppid=legacy_ppid,
    )
    if not record:
        return jsonify({
            "success": True,
            "allocated": False,
            "registered": registered,
            "drop_id": drop_id,
            "ppid": ppid,
            "assurance": assurance,
        })
    return jsonify({
        "success": True,
        "allocated": True,
        "registered": registered,
        "drop_id": record.drop_id,
        "ppid": record.ppid,
        "code": record.code,
        "claimed_at": record.claimed_at,
        "assurance": record.assurance or assurance,
    })


@app.post("/api/presale/register")
def presale_register():
    body = request.get_json(silent=True) or {}
    register_body = _presale_register_body(body)
    server_nonce = str(body.get("server_nonce") or "").strip()
    if not _rate_limit(f"register:{_client_ip()}", limit=10, window_seconds=60):
        return jsonify({
            "success": False,
            "reason": "rate_limited",
            **_presale_gate_report(phase="register", success=False, reason="rate_limited"),
        }), 429
    ctx = _verify_ctx()
    try:
        result = ctx.verify_action_stamp(
            body,
            action=PRESALE_REGISTER_ACTION,
            method="POST",
            path=PRESALE_REGISTER_PATH,
            body=register_body,
            required_assurance=DEMO_REQUIRED_ASSURANCE,
            nonce_store=_NONCE_STORE,
            nonce_store_mode="required",
            server_nonce=server_nonce or None,
        )
    except Exception:
        logger.exception("presale register verification failed")
        return jsonify({
            "success": False,
            "reason": "verify_error",
            **_presale_gate_report(phase="register", success=False, reason="verify_error"),
        }), 500

    legacy_ppid = getattr(result, "legacy_ppid", None)
    entry_base = {
        "action": PRESALE_REGISTER_ACTION,
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
            **_presale_gate_report(
                phase="register",
                success=False,
                reason=result.reason or "unknown",
            ),
        }), 403

    if result.ppid and not _rate_limit(f"register:ppid:{result.ppid}", limit=5, window_seconds=300):
        return jsonify({
            "success": False,
            "reason": "rate_limited",
            **_presale_gate_report(phase="register", success=False, reason="rate_limited"),
        }), 429

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
            **_presale_gate_report(
                phase="register",
                success=False,
                reason=policy_reason or "site_blocked",
            ),
        }), 403

    registered = _PRESALE_REGISTRATIONS.register(
        register_body["drop_id"],
        result.ppid or "",
        email=register_body["email"],
        phone=register_body["phone"],
    )
    if not registered.ok:
        return jsonify({
            "success": False,
            "reason": registered.reason,
            **_presale_gate_report(
                phase="register",
                success=False,
                reason=registered.reason or "registration_store_error",
            ),
        }), 403

    entry = {**entry_base, "ok": True, "reason": "ok", "drop_id": registered.drop_id}
    ACTION_LOG.appendleft(entry)
    return jsonify({
        "success": True,
        "drop_id": registered.drop_id,
        "ppid": registered.ppid,
        "assurance": getattr(result, "assurance", None),
        "reason": "ok",
        "action_log": list(ACTION_LOG),
        **_presale_gate_report(phase="register", success=True, reason="ok"),
    })


@app.post("/api/presale/delivery")
def presale_delivery():
    """Optional post-claim contact update — site-local delivery fields only."""
    body = request.get_json(silent=True) or {}
    session = _session_from_request()
    if not session or not session.get("ppid"):
        return jsonify({"success": False, "reason": "site_proof_required"}), 403
    drop_id = str(body.get("drop_id") or PRESALE_DROP_ID).strip()
    email = str(body.get("email") or "").strip()
    phone = str(body.get("phone") or "").strip()
    updated = _PRESALE_REGISTRATIONS.update_contact(
        drop_id,
        session["ppid"],
        email=email,
        phone=phone,
    )
    if not updated.ok:
        return jsonify({"success": False, "reason": updated.reason}), 403
    return jsonify({
        "success": True,
        "drop_id": updated.drop_id,
        "ppid": updated.ppid,
        "reason": "ok",
    })


@app.post("/api/presale/claim-code")
def presale_claim_code():
    body = request.get_json(silent=True) or {}
    claim_body = _presale_claim_body(body)
    claim_assurance = _resolve_claim_assurance(body)
    server_nonce = str(body.get("server_nonce") or "").strip()
    if not _rate_limit(f"claim:{_client_ip()}", limit=10, window_seconds=60):
        return jsonify({
            "success": False,
            "reason": "rate_limited",
            **_presale_gate_report(
                phase="claim",
                success=False,
                reason="rate_limited",
                require_fresh_passkey=True,
            ),
        }), 429
    ctx = _claim_verify_ctx()
    try:
        result = ctx.verify_action_stamp(
            body,
            action=PRESALE_CLAIM_ACTION,
            method="POST",
            path=PRESALE_CLAIM_PATH,
            body=claim_body,
            required_assurance=claim_assurance,
            nonce_store=_NONCE_STORE,
            nonce_store_mode="required",
            require_fresh_passkey=True,
            server_nonce=server_nonce or None,
        )
    except Exception:
        logger.exception("presale claim verification failed")
        return jsonify({
            "success": False,
            "reason": "verify_error",
            "error": "Action stamp verification failed on the server",
            **_presale_gate_report(
                phase="claim",
                success=False,
                reason="verify_error",
                require_fresh_passkey=True,
            ),
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
            "required_assurance": claim_assurance,
            "action_log": list(ACTION_LOG),
            **_presale_gate_report(
                phase="claim",
                success=False,
                reason=result.reason or "unknown",
                require_fresh_passkey=True,
            ),
        }), 403

    if result.ppid and not _rate_limit(f"claim:ppid:{result.ppid}", limit=5, window_seconds=300):
        return jsonify({
            "success": False,
            "reason": "rate_limited",
            **_presale_gate_report(
                phase="claim",
                success=False,
                reason="rate_limited",
                require_fresh_passkey=True,
            ),
        }), 429

    if claim_assurance == PRESALE_ESCALATED_ASSURANCE and result.ppid:
        _POLICY_STORE.doubted.discard(result.ppid)
        if legacy_ppid:
            _POLICY_STORE.doubted.discard(legacy_ppid)

    ok_policy, policy_reason, _decision = enforce_site_policy(
        ppid=result.ppid or "",
        policy_store=_POLICY_STORE,
        legacy_ppid=legacy_ppid,
        require_policy=True,
    )
    if not ok_policy:
        entry = {**entry_base, "ok": False, "reason": policy_reason}
        ACTION_LOG.appendleft(entry)
        payload = {
            "success": False,
            "reason": policy_reason,
            "ppid": result.ppid,
            "required_assurance": PRESALE_ESCALATED_ASSURANCE,
            "action_log": list(ACTION_LOG),
            **_presale_gate_report(
                phase="claim",
                success=False,
                reason=policy_reason or "site_blocked",
                require_fresh_passkey=True,
            ),
        }
        if policy_reason == "doubt_required":
            payload["escalation"] = "fresh_idv"
        return jsonify(payload), 403

    if not _PRESALE_REGISTRATIONS.is_registered(
        claim_body["drop_id"],
        result.ppid or "",
        legacy_ppid=legacy_ppid,
    ):
        entry = {**entry_base, "ok": False, "reason": "registration_required"}
        ACTION_LOG.appendleft(entry)
        return jsonify({
            "success": False,
            "reason": "registration_required",
            "ppid": result.ppid,
            "action_log": list(ACTION_LOG),
            **_presale_gate_report(
                phase="claim",
                success=False,
                reason="registration_required",
                require_fresh_passkey=True,
            ),
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
            **_presale_gate_report(
                phase="claim",
                success=False,
                reason=claim.reason or "allocation_already_claimed",
                require_fresh_passkey=True,
            ),
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
        **_presale_gate_report(
            phase="claim",
            success=True,
            reason="ok",
            require_fresh_passkey=True,
        ),
    })


def _origin_from_url(raw: str) -> str:
    try:
        parsed = urlparse((raw or "").strip())
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}".lower()


def _allowed_hub_origins() -> set[str]:
    """Origins allowed to open /hub-verify and receive the result postMessage."""
    origins = {
        _origin_from_url(DEMO_HUB_URL),
        _origin_from_url(LEMMA_ORIGIN),
        "https://lemma.id",
        "https://www.lemma.id",
        "http://localhost:5000",
        "http://127.0.0.1:5000",
    }
    return {o for o in origins if o}


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


@app.get("/hub-verify")
def hub_verify():
    """Popup bridge for the lemma.id demo hub.

    Flow-state mint requires opener origin == site hostname, so the hub cannot
    run tickets/trials ceremonies on lemma.id. Instead the hub opens this page
    on the demo Origin; we mint/run the ceremony here and postMessage a result
    summary back to window.opener.
    """
    hub_origin = _origin_from_url(request.args.get("hub_origin", ""))
    allowed = _allowed_hub_origins()
    if hub_origin not in allowed:
        return Response(
            "<!doctype html><html><body><p>Invalid hub_origin.</p></body></html>",
            status=400,
            mimetype="text/html",
        )

    request_id = (request.args.get("request_id") or "").strip()[:128]
    mode = (request.args.get("mode") or "signin").strip().lower()
    if mode not in {"signin", "fresh_presence", "fresh_idv"}:
        mode = "signin"
    required_assurance = (request.args.get("required_assurance") or DEMO_REQUIRED_ASSURANCE).strip().lower()
    if required_assurance not in {"passkey", "ishuman"}:
        required_assurance = DEMO_REQUIRED_ASSURANCE or "passkey"

    theme = _site_theme()
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hub verify · {SITE_NAME}</title>
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <style>
    :root {{
      --bg: {theme.get("bg", "#fafafa")};
      --ink: {theme.get("ink", "#1a1a24")};
      --muted: {theme.get("muted", "#5c5b66")};
      --accent: {theme.get("accent", "#4E3D8F")};
      --line: {theme.get("line", "#e5e4ea")};
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; min-height: 100vh; font-family: Georgia, 'Times New Roman', serif;
      background: var(--bg); color: var(--ink);
      display: grid; place-items: center; padding: 24px;
    }}
    .card {{
      width: min(420px, 100%); text-align: center;
      border-top: 3px solid var(--accent); padding: 28px 22px 24px;
    }}
    .brand {{ display: inline-flex; align-items: center; gap: 10px; margin-bottom: 14px; }}
    .brand svg {{ width: 36px; height: 36px; }}
    h1 {{ font-size: 1.35rem; margin: 0 0 8px; font-weight: 600; }}
    p {{ margin: 0; color: var(--muted); font-size: 0.95rem; line-height: 1.45; }}
    #status {{ margin-top: 18px; font-family: ui-sans-serif, system-ui, sans-serif; font-size: 0.85rem; }}
    #status[data-state="error"] {{ color: #b42318; }}
    #status[data-state="ok"] {{ color: #027a48; }}
  </style>
  {_sdk_script_tags()}
</head>
<body>
  <main class="card">
    <div class="brand" aria-hidden="true">{theme.get("icon_svg", "")}</div>
    <h1>{SITE_NAME}</h1>
    <p>Completing sign-in for the lemma.id demo hub on this site's origin.</p>
    <p id="status" data-state="pending">Starting…</p>
  </main>
  <script>
(async function () {{
  var HUB_ORIGIN = {hub_origin!r};
  var REQUEST_ID = {request_id!r};
  var MODE = {mode!r};
  var REQUIRED_ASSURANCE = {required_assurance!r};
  var SITE_ID = {SITE_ID!r};
  var LEMMA_ORIGIN = {LEMMA_ORIGIN!r};
  var statusEl = document.getElementById('status');
  var settled = false;

  function setStatus(text, state) {{
    if (!statusEl) return;
    statusEl.textContent = text;
    if (state) statusEl.setAttribute('data-state', state);
  }}

  function notify(payload) {{
    if (settled) return;
    settled = true;
    var msg = Object.assign({{
      type: 'LEMMA_HUB_VERIFY_RESULT',
      request_id: REQUEST_ID,
      site_id: SITE_ID,
    }}, payload || {{}});
    try {{
      if (window.opener && !window.opener.closed) {{
        window.opener.postMessage(msg, HUB_ORIGIN);
      }}
    }} catch (e) {{}}
    setTimeout(function () {{
      try {{ window.close(); }} catch (e) {{}}
    }}, msg.ok ? 600 : 1600);
  }}

  function cancel(reason) {{
    notify({{
      type: 'LEMMA_HUB_VERIFY_RESULT',
      ok: false,
      human: false,
      ppid: null,
      assurance: null,
      presentation: null,
      reason: reason || 'idv_cancelled',
      timeMs: 0,
    }});
  }}

  if (!window.opener) {{
    setStatus('Open this page from the demo hub Sign in button.', 'error');
    return;
  }}
  if (!window.IsHumanVerifier) {{
    setStatus(window.__lemmaSdkLoadError || 'SDK failed to load.', 'error');
    cancel('sdk_load_failed');
    return;
  }}

  var Verifier = window.IsHumanVerifier || window.ProofVerifier;
  var verifier = new Verifier({{
    siteId: SITE_ID,
    lemmaOrigin: LEMMA_ORIGIN,
    autoProvision: true,
    requiredAssurance: REQUIRED_ASSURANCE,
    debug: true,
    isBlockedLocally: async function (ppid) {{
      try {{
        var res = await fetch('/api/demo/policy/check?ppid=' + encodeURIComponent(ppid));
        var data = await res.json();
        return {{ blocked: !!data.blocked, doubt_required: !!data.doubt_required }};
      }} catch (e) {{
        return {{ blocked: false, doubt_required: false }};
      }}
    }},
  }});

  try {{
    setStatus(MODE === 'fresh_idv'
      ? 'Confirm fresh human proof…'
      : (MODE === 'fresh_presence' ? 'Confirm fresh presence…' : 'Signing in…'));

    var backend = null;
    if (MODE === 'fresh_idv') {{
      backend = await verifier.verifyFreshForBackend({{
        requiredAssurance: 'ishuman',
        freshIdv: true,
      }});
    }} else if (MODE === 'fresh_presence') {{
      var issued = await verifier._issueSiteProofViaPopup({{
        freshIdv: false,
        requireFreshPasskey: true,
        refreshReason: 'site_doubt',
      }});
      if (!issued || !issued.ok) {{
        setStatus('Presence confirmation cancelled.', 'error');
        cancel(issued && issued.reason ? issued.reason : 'fresh_presence_cancelled');
        return;
      }}
      var applied = await verifier._applyIssuedSiteProof(
        Object.assign({{}}, issued.detail || {{}}, {{ refresh_reason: 'site_doubt' }}),
        performance.now()
      );
      backend = {{
        ok: !!(applied && applied.human),
        human: !!(applied && applied.human),
        ppid: applied && applied.ppid,
        assurance: (applied && applied.assurance) || 'passkey',
        presentation: applied && applied.presentation,
        reason: (applied && applied.reason) || 'valid',
        timeMs: (applied && applied.timeMs) || 0,
      }};
    }} else {{
      backend = await verifier.verifyForBackend({{
        autoProvision: true,
        requiredAssurance: REQUIRED_ASSURANCE,
      }});
    }}

    var ok = !!(backend && (backend.ok || backend.human));
    if (ok && backend.presentation) {{
      try {{
        await fetch('/api/login', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          credentials: 'same-origin',
          body: JSON.stringify({{ presentation: backend.presentation }}),
        }});
      }} catch (e) {{ /* session cookie optional for hub UI */ }}
    }}

    if (ok) setStatus('Signed in — returning to hub…', 'ok');
    else setStatus('Sign-in did not complete (' + ((backend && backend.reason) || 'denied') + ').', 'error');

    notify({{
      ok: ok,
      human: ok,
      ppid: (backend && backend.ppid) || null,
      assurance: (backend && backend.assurance) || null,
      presentation: (backend && backend.presentation) || null,
      reason: (backend && backend.reason) || (ok ? 'valid' : 'not_verified'),
      timeMs: (backend && backend.timeMs) || 0,
    }});
  }} catch (err) {{
    var reason = (err && err.message) ? String(err.message) : 'verify_failed';
    setStatus('Sign-in failed: ' + reason, 'error');
    cancel(reason);
  }}
}})();
  </script>
</body>
</html>"""
    return Response(html, mimetype="text/html")


@app.get("/")
def index():
    if _is_presale_site():
        tour = request.args.get("tour")
        if tour == "presale":
            return _presale_index()
        if tour == "signin":
            return _ticketing_signin_index()
        return _ticketing_welcome_index()
    return _generic_index()


@app.get("/favicon.svg")
def favicon():
    return Response(_site_theme()["favicon_svg"], mimetype="image/svg+xml")


def _generic_index():
    copy = _content()
    theme = _site_theme()
    is_trial = "trial" in SITE_KIND.lower()
    demo_walkthrough = """
    <div class="demo-progress" id="demo-progress" aria-label="Demo walkthrough">
      <span class="demo-progress-label">Live demo</span>
      <span class="demo-step" data-demo-step="signin">1 · Sign in with a passkey</span>
      <span class="demo-step" data-demo-step="activate">2 · Activate your free workspace</span>
      <span class="demo-step" data-demo-step="deny">3 · Try to activate again</span>
      <span class="demo-step" data-demo-step="one">4 · One trial per person</span>
    </div>""" if is_trial else ""
    trial_gated_block = ""
    if is_trial:
        trial_gated_block = f"""
        <div class="gated-section" id="trial-gated" hidden>
          <p class="eyebrow">{copy["trial_eyebrow"]}</p>
          <p class="muted" style="font-size:14px;margin-bottom:8px;">{copy["trial_subhead"]}</p>
          <label for="email">{copy["form"]}</label>
          <input id="email" value="{copy["placeholder"]}" aria-label="{copy["form"]}">
          <button id="verify-btn" class="site-cta" disabled>{copy["primary"]}</button>
          <div class="trial-active" id="trial-active" hidden>
            <strong>Workspace active</strong>
            <p>Your free workspace is live — verified one per person, no email or documents shared with Northstar.</p>
          </div>
          <div class="trial-used-notice" id="trial-used-notice" hidden>
            <strong>You already used your free trial</strong>
            <p>Free workspaces are one per person. Same lemma.id, same answer — even after clearing cookies or reinstalling.</p>
          </div>
          <button type="button" id="trial-reset-btn" class="trial-reset-btn" hidden>Clear trial (demo reset)</button>
        </div>"""
    else:
        trial_gated_block = f"""
        <label for="email">{copy["form"]}</label>
        <input id="email" value="{copy["placeholder"]}" aria-label="{copy["form"]}">
        <button id="verify-btn" disabled>{copy["primary"]}</button>"""
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_site_display_name()}</title>
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <style>
    {_theme_css_root()}
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
      padding: 14px max(24px, calc((100vw - 1120px) / 2));
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    header strong {{ font-size: 19px; letter-spacing: -0.3px; }}
    header a {{ color: var(--muted); font-size: 13px; text-decoration: none; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 48px 22px 72px; }}
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
      background: #1A1A24;
      color: #fff;
      border-radius: 10px;
      padding: 14px 16px;
      font-weight: 800;
      font-size: 15px;
      cursor: pointer;
      margin-top: 16px;
    }}
    button:disabled {{ opacity: 0.65; cursor: not-allowed; }}
    {SITE_CTA_CSS}
    {LEMMA_SIGNIN_CSS}
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
      border: 1px solid #cbd5e1;
      background: #f8fafc;
    }}
    .server-receipt strong {{ display: block; margin-bottom: 8px; color: #334155; }}
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
    .auth-shell {{
      min-height: calc(100vh - 190px);
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) minmax(340px, .85fr);
      gap: clamp(40px, 8vw, 100px);
      align-items: center;
    }}
    .auth-copy h1 {{ max-width: 680px; font-size: clamp(46px, 7vw, 72px); }}
    .auth-copy .muted {{ max-width: 560px; font-size: 18px; }}
    .auth-card {{ padding: 30px; }}
    .auth-card h2 {{ margin: 0 0 8px; font-size: 24px; }}
    .auth-note {{ margin-top: 14px; font-size: 12px; text-align: center; color: var(--muted); }}
    .app-shell[hidden], .auth-shell[hidden] {{ display: none; }}
    .app-topline {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; margin-bottom: 28px; }}
    .app-topline h1 {{ font-size: clamp(34px, 5vw, 48px); }}
    .account-chip {{ padding: 8px 12px; border: 1px solid var(--line); border-radius: 999px; background: #fff; font-size: 12px; color: var(--muted); }}
    .dashboard-grid {{ display: grid; grid-template-columns: 1.35fr .65fr; gap: 18px; }}
    .project-list {{ display: grid; gap: 12px; margin-top: 20px; }}
    .project-row {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px; border: 1px solid var(--line); border-radius: 12px; }}
    .project-row strong {{ display: block; margin-bottom: 4px; }}
    .progress {{ width: 120px; height: 7px; overflow: hidden; background: #e2e8f0; border-radius: 999px; }}
    .progress span {{ display: block; height: 100%; background: var(--brand); border-radius: inherit; }}
    .offer-card {{ background: #052e16; color: #dcfce7; border: 0; }}
    .offer-card .eyebrow {{ color: #86efac; }}
    .offer-card .muted {{ color: #bbf7d0; }}
    .offer-card label {{ color: #fff; }}
    .offer-card input {{ background: rgba(255,255,255,.96); }}
    .dev-tools {{ margin-top: 20px; border: 1px solid var(--line); border-radius: 12px; background: #fff; padding: 0 16px 16px; }}
    .dev-tools > summary {{ padding: 15px 0; list-style: none; display: flex; justify-content: space-between; }}
    .dev-tools > summary::after {{ content: "＋"; color: var(--muted); }}
    .dev-tools[open] > summary::after {{ content: "−"; }}
    .dev-tools .verdict {{ min-height: 0; }}
    .logout-btn {{ width: auto; margin: 0; padding: 9px 13px; color: #475569; background: #fff; border: 1px solid var(--line); font-size: 12px; }}
    .demo-progress {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      margin-bottom: 18px;
    }}
    .demo-progress-label {{
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
      margin-right: 4px;
    }}
    .demo-step {{
      font-size: 12px;
      font-weight: 700;
      padding: 5px 11px;
      border-radius: 999px;
      border: 1px solid var(--line);
      color: var(--muted);
      background: #fff;
    }}
    .demo-step.is-active {{
      border-color: var(--brand);
      color: var(--brand);
      background: #f0fdf4;
    }}
    .demo-step.is-done {{
      border-color: #86efac;
      color: var(--ok);
      background: #f0fdf4;
    }}
    .trial-active {{
      margin-top: 16px;
      padding: 14px 16px;
      border-radius: 12px;
      border: 1px solid #4ade80;
      background: rgba(255, 255, 255, 0.08);
      color: #dcfce7;
    }}
    .trial-active strong {{ display: block; margin-bottom: 4px; color: #fff; }}
    .trial-active p {{ margin: 0; font-size: 13px; line-height: 1.45; color: #bbf7d0; }}
    .trial-used-notice {{
      margin-top: 16px;
      padding: 14px 16px;
      border-radius: 12px;
      border: 1px solid #fcd34d;
      background: rgba(255, 251, 235, 0.95);
      color: #92400e;
    }}
    .trial-used-notice strong {{ display: block; margin-bottom: 4px; color: #78350f; }}
    .trial-used-notice p {{ margin: 0; font-size: 13px; line-height: 1.45; }}
    .trial-reset-btn {{
      background: transparent;
      border: 1px solid #86efac;
      color: #dcfce7;
      font-size: 13px;
      padding: 10px 14px;
    }}
    @media (max-width: 820px) {{
      .layout, .auth-shell, .dashboard-grid {{ grid-template-columns: 1fr; }}
      .auth-shell {{ min-height: auto; gap: 28px; }}
      main {{ padding-top: 32px; }}
      .app-topline {{ flex-direction: column; }}
    }}
  </style>
</head>
<body>
  {_site_header('<button class="logout-btn" id="logout-btn" hidden>Sign out</button>')}
  <main>
    {demo_walkthrough}
    <section class="auth-shell" id="auth-view">
      <div class="auth-copy">
        <p class="eyebrow">{copy["eyebrow"]}</p>
        <h1>{copy["headline"]}</h1>
        <p class="muted">{copy["subhead"]}</p>
      </div>
      <div class="card auth-card">
        <h2>Sign in to Northstar</h2>
        <p class="muted">Use your passkey-backed lemma.id to continue.</p>
        {_lemma_signin_element()}
        <p class="auth-note">No password or email required. Northstar receives only a private account ID.</p>
      </div>
    </section>
    <section class="app-shell" id="app-view" hidden>
      <div class="app-topline">
        <div>
          <p class="eyebrow">Workspace overview</p>
          <h1>Good evening.</h1>
          <p class="muted" id="session-copy">Loading your workspace…</p>
        </div>
        <span class="account-chip">Personal workspace</span>
      </div>
      <div class="dashboard-grid">
        <section class="card">
          <p class="eyebrow">Recent projects</p>
          <h2 style="margin:0;">Everything is on track</h2>
          <div class="project-list">
            <div class="project-row"><div><strong>Website launch</strong><span class="muted">8 of 12 tasks complete</span></div><div class="progress"><span style="width:67%"></span></div></div>
            <div class="project-row"><div><strong>Q3 planning</strong><span class="muted">4 of 10 tasks complete</span></div><div class="progress"><span style="width:40%"></span></div></div>
            <div class="project-row"><div><strong>Customer research</strong><span class="muted">11 of 14 tasks complete</span></div><div class="progress"><span style="width:79%"></span></div></div>
          </div>
        </section>
        <aside class="card offer-card">
          {trial_gated_block}
        </aside>
      </div>
      <details class="dev-tools">
        <summary>Developer details</summary>
        <p class="muted">Site binding: <code id="site-id">{SITE_ID}</code></p>
        <p style="margin:12px 0 6px">Decision <span class="pill" id="status-pill">WAITING</span>
          <span class="pill" id="assurance-pill">policy: {DEMO_REQUIRED_ASSURANCE}</span></p>
        <p class="muted" id="decision-copy">Sign in to inspect server verification.</p>
        <div class="server-receipt" id="server-receipt" hidden>
          <strong>Server verification receipt</strong>
          <dl id="server-receipt-fields"></dl>
        </div>
        <div class="verdict" id="decision-card"><strong>Server session ready</strong><p class="tiny">Passkey sign-in creates a normal HttpOnly site session. The founding-team offer requires a separate human-assurance presentation.</p></div>
        <details>
          <summary>Signed presentation JSON</summary>
          <pre id="presentation-json">{{}}</pre>
        </details>
        <details>
          <summary>Server-verified action log</summary>
          <pre id="action-log">[]</pre>
        </details>
        <p class="hub-return"><a href="{DEMO_HUB_URL}?lane=builder&from=demo">Return to demo hub →</a></p>
      </details>
    </section>
  </main>
  {_sdk_script_tags()}
  <script>
  {_PLAIN_LANGUAGE_JS}
    if (typeof ProofVerifier === 'undefined') {{
      const msg = window.__lemmaSdkLoadError
        || 'Lemma SDK (ProofVerifier) did not load, check network connection and that {LEMMA_ORIGIN} is reachable.';
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
    const sessionCopy = document.getElementById('session-copy');
    const signInEl = document.getElementById('lemma-signin-btn');
    const actionBtn = document.getElementById('verify-btn');
    const trialGated = document.getElementById('trial-gated');
    const trialActiveEl = document.getElementById('trial-active');
    const trialUsedNotice = document.getElementById('trial-used-notice');
    const trialResetBtn = document.getElementById('trial-reset-btn');
    const authView = document.getElementById('auth-view');
    const appView = document.getElementById('app-view');
    const logoutBtn = document.getElementById('logout-btn');
    const SITE_POLICY = '{DEMO_REQUIRED_ASSURANCE}';
    const TRIAL_ASSURANCE = '{TRIAL_REQUIRED_ASSURANCE}';
    const IS_TRIAL_SITE = {'true' if is_trial else 'false'};
    const DEMO_SEQUENCE = ['signin', 'activate', 'deny', 'one'];
    let sharedVerifier = null;
    let siteSessionPpid = null;

    function setDemoStep(stepId) {{
      const idx = DEMO_SEQUENCE.indexOf(stepId);
      if (idx < 0) return;
      document.querySelectorAll('.demo-step').forEach((el) => {{
        const stepIdx = DEMO_SEQUENCE.indexOf(el.getAttribute('data-demo-step'));
        el.classList.remove('is-active', 'is-done');
        if (stepIdx < idx) el.classList.add('is-done');
        else if (stepIdx === idx) el.classList.add('is-active');
      }});
    }}

    function showTrialActive() {{
      if (trialActiveEl) trialActiveEl.hidden = false;
      if (trialUsedNotice) trialUsedNotice.hidden = true;
      if (trialResetBtn) trialResetBtn.hidden = false;
    }}

    function showTrialAlreadyUsed() {{
      if (trialUsedNotice) trialUsedNotice.hidden = false;
      if (trialActiveEl) trialActiveEl.hidden = true;
      if (trialResetBtn) trialResetBtn.hidden = false;
      setDemoStep('one');
    }}

    function resetTrialUi() {{
      if (trialActiveEl) trialActiveEl.hidden = true;
      if (trialUsedNotice) trialUsedNotice.hidden = true;
      if (trialResetBtn) trialResetBtn.hidden = true;
    }}

    async function syncTrialStatus() {{
      if (!IS_TRIAL_SITE || !siteSessionPpid) return;
      try {{
        const res = await fetch('/api/demo/trial/status', {{ credentials: 'include' }});
        if (!res.ok) return;
        const data = await res.json();
        if (data.activated) {{
          showTrialActive();
          setDemoStep('deny');
        }}
      }} catch (err) {{}}
    }}

    function setSignInDisabled(disabled) {{
      if (!signInEl) return;
      if (disabled) signInEl.setAttribute('disabled', '');
      else signInEl.removeAttribute('disabled');
    }}

    function makeVerifier(autoProvision, requiredAssurance) {{
      const assurance = requiredAssurance || SITE_POLICY;
      if (sharedVerifier && sharedVerifier.autoProvision === autoProvision && sharedVerifier.requiredAssurance === assurance) {{
        return sharedVerifier;
      }}
      if (sharedVerifier) sharedVerifier.destroy();
      sharedVerifier = new IsHumanVerifier({{
        siteId: '{SITE_ID}',
        lemmaOrigin: '{LEMMA_ORIGIN}',
        autoProvision,
        requiredAssurance: assurance,
        debug: true,
        isBlockedLocally: async (ppid) => {{
          const res = await fetch('/api/demo/policy/check?ppid=' + encodeURIComponent(ppid));
          const data = await res.json();
          return {{ blocked: !!data.blocked, doubt_required: !!data.doubt_required }};
        }},
      }});
      sharedVerifier.autoProvision = autoProvision;
      sharedVerifier.requiredAssurance = assurance;
      return sharedVerifier;
    }}

    function updateGatedVisibility(signedIn) {{
      if (!IS_TRIAL_SITE || !trialGated) return;
      trialGated.hidden = !signedIn;
    }}

    function renderSiteSession(signedIn) {{
      if (authView) authView.hidden = signedIn;
      if (appView) appView.hidden = !signedIn;
      if (logoutBtn) logoutBtn.hidden = !signedIn;
      document.body.classList.toggle('signed-in', !!signedIn);
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

    {_PLAIN_LANGUAGE_JS}

    function renderServerReceipt(response, serverEntry) {{
      if (!serverReceipt || !serverReceiptFields) return;
      if (!serverEntry) {{
        serverReceipt.hidden = true;
        return;
      }}
      serverReceipt.hidden = false;
      const rows = [
        ['Site binding', '{SITE_ID}'],
        ['PPID', serverEntry.ppid || response.ppid || 'Not available'],
        ['Assurance', serverEntry.assurance || response.assurance || 'Not available'],
        ['Server reason', serverEntry.reason || 'Not available'],
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
        ? ' · continuity only, IDV not required at this tier'
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
        return 'Your lemma.id is locked. Click the protected action to unlock and verify.';
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
        decisionCopy.textContent = detail;
        decisionCard.innerHTML = '<strong>Action blocked</strong><p class="tiny">' + detail + '</p>';
      }} else {{
        decisionCopy.textContent = formatMissingProof(response.reason);
      }}
    }}

    async function refreshSessionState() {{
      try {{
        const me = await fetch('/api/me', {{ credentials: 'include' }});
        if (me.ok) {{
          const data = await me.json();
          siteSessionPpid = data.ppid || null;
          if (sessionCopy) {{
            sessionCopy.textContent = 'Signed in with passkey · PPID ' + (siteSessionPpid || '').slice(0, 24) + '…';
          }}
          if (actionBtn) actionBtn.disabled = false;
          setSignInDisabled(true);
          updateGatedVisibility(true);
          renderSiteSession(true);
          pill.textContent = 'SIGNED IN';
          pill.className = 'pill ok';
          setAssurancePill(data.assurance || SITE_POLICY);
          setDemoStep('activate');
          await syncTrialStatus();
          return true;
        }}
      }} catch (err) {{}}
      siteSessionPpid = null;
      if (sessionCopy) sessionCopy.textContent = 'Sign in once with a passkey. This site keeps a session until a fresh passkey is required.';
      if (actionBtn) actionBtn.disabled = true;
      setSignInDisabled(false);
      updateGatedVisibility(false);
      renderSiteSession(false);
      setDemoStep('signin');
      return false;
    }}

    async function completeLoginFromPresentation(presentation, timeMs) {{
      pill.textContent = 'CHECKING';
      pill.className = 'pill checking';
      decisionCard.innerHTML = '<strong>Sign in with lemma.id</strong><p class="tiny">Server verifies your signed presentation and sets a site session cookie.</p>';
      try {{
        const loginRes = await fetch('/api/login', {{
          method: 'POST',
          credentials: 'include',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ presentation }}),
        }});
        const loginPayload = await loginRes.json();
        if (!loginRes.ok || !loginPayload.success) {{
          throw new Error(loginPayload.reason || 'login_failed');
        }}
        siteSessionPpid = loginPayload.ppid || null;
        await refreshSessionState();
        decisionCard.innerHTML = '<strong>Signed in</strong><p class="tiny">Site session active · '
          + (timeMs || 0).toFixed(0) + 'ms verify · PPID '
          + (siteSessionPpid || '').slice(0, 24) + '…</p>';
        if (presentationJson) presentationJson.textContent = JSON.stringify(presentation, null, 2);
        return true;
      }} catch (err) {{
        pill.textContent = 'ERROR';
        pill.className = 'pill deny';
        decisionCopy.textContent = 'Sign in failed: ' + err.message;
        setSignInDisabled(false);
        return false;
      }}
    }}

    async function runProtectedAction() {{
      if (!siteSessionPpid) {{
        const signedIn = await refreshSessionState();
        if (!signedIn) {{
          decisionCopy.textContent = 'Sign in with lemma.id first.';
          return;
        }}
      }}
      actionBtn.disabled = true;
      pill.textContent = 'CHECKING';
      pill.className = 'pill checking';
      decisionCard.innerHTML = '<strong>Starting trial access</strong><p class="tiny">Verified human proof required — one account per person.</p>';
      try {{
        const email = document.getElementById('email')?.value || '';
        let requestPayload = {{
          action: '{copy["action"]}',
          email,
          at: Date.now(),
        }};
        let serverEntry = null;
        if (IS_TRIAL_SITE) {{
          // Step-up to ishuman: reuse master human proof + derive site VC.
          // Site-doubt fresh IDV is a separate deliberate ceremony.
          const verifier = makeVerifier(true, TRIAL_ASSURANCE);
          const stepped = await verifier.verifyForBackend({{
            requiredAssurance: TRIAL_ASSURANCE,
            autoProvision: true,
          }});
          if (!stepped.ok) {{
            const response = {{
              human: false,
              assurance: stepped.assurance || null,
              reason: stepped.reason || 'not_verified',
              timeMs: stepped.timeMs || 0,
              ppid: stepped.ppid || siteSessionPpid,
            }};
            applyVerdict(response, {{ requestPayload }});
            return;
          }}
          requestPayload = {{
            ...requestPayload,
            presentation: stepped.presentation,
          }};
        }}
        const serverRes = await fetch('/api/demo/action', {{
          method: 'POST',
          credentials: 'include',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(requestPayload),
        }});
        serverEntry = await serverRes.json();
        await refreshActionLog();
        if (IS_TRIAL_SITE && serverEntry.reason === 'trial_already_used') {{
          showTrialAlreadyUsed();
          pill.textContent = 'ALREADY USED';
          pill.className = 'pill deny';
          const msg = formatDenyReason('trial_already_used');
          decisionCopy.textContent = msg;
          decisionCard.innerHTML = '<strong>One free trial per person</strong><p class="tiny">' + msg
            + ' Use Clear trial (demo reset) to replay the flow.</p>';
          return;
        }}
        const response = {{
          human: !!serverEntry.success,
          assurance: serverEntry.assurance || (IS_TRIAL_SITE ? TRIAL_ASSURANCE : SITE_POLICY),
          reason: serverEntry.reason,
          timeMs: 0,
          ppid: serverEntry.ppid || siteSessionPpid,
        }};
        applyVerdict(response, {{ requestPayload, serverEntry }});
        if (IS_TRIAL_SITE && serverEntry.success) {{
          showTrialActive();
          setDemoStep('deny');
        }}
      }} catch (err) {{
        pill.textContent = 'ERROR';
        pill.className = 'pill deny';
        decisionCopy.textContent = 'Action failed: ' + err.message;
      }} finally {{
        actionBtn.disabled = !siteSessionPpid;
      }}
    }}

    refreshSessionState();
    refreshActionLog();
    signInEl?.addEventListener('lemma-signin-success', (e) => {{
      completeLoginFromPresentation(e.detail.presentation, e.detail.timeMs);
    }});
    signInEl?.addEventListener('lemma-signin-error', (e) => {{
      pill.textContent = 'DENY';
      pill.className = 'pill deny';
      decisionCopy.textContent = formatDenyReason(e.detail.reason);
      setSignInDisabled(false);
    }});
    actionBtn?.addEventListener('click', () => runProtectedAction());
    trialResetBtn?.addEventListener('click', async () => {{
      if (!siteSessionPpid) return;
      try {{
        const res = await fetch('/api/demo/trial/reset', {{
          method: 'POST',
          credentials: 'include',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ ppid: siteSessionPpid }}),
        }});
        const data = await res.json();
        if (!res.ok || !data.success) throw new Error(data.reason || 'reset_failed');
        resetTrialUi();
        setDemoStep('activate');
        pill.textContent = 'TRIAL CLEARED';
        pill.className = 'pill ok';
        decisionCopy.textContent = 'Demo reset: this account can activate a free workspace again.';
        decisionCard.innerHTML = '<strong>Demo trial cleared</strong><p class="tiny">Activation released for this site-private PPID — run the flow again.</p>';
      }} catch (err) {{
        decisionCopy.textContent = 'Could not clear trial: ' + err.message;
      }}
    }});
    logoutBtn?.addEventListener('click', async () => {{
      await fetch('/api/logout', {{ method: 'POST', credentials: 'include' }});
      window.location.reload();
    }});

    if (new URLSearchParams(window.location.search).get('lemma_ishuman_return') === '1') {{
      try {{
        const cleaned = new URL(window.location.href);
        ['lemma_ishuman_return', 'request_nonce', 'redirect_kind'].forEach((k) => cleaned.searchParams.delete(k));
        window.history.replaceState(null, '', cleaned.toString());
      }} catch (e) {{}}
      signInEl?.signIn()?.then((result) => {{
        if (result?.ok) completeLoginFromPresentation(result.presentation, result.timeMs).then((ok) => {{
          if (ok) runProtectedAction();
        }});
      }});
    }}
  </script>
</body>
</html>"""
    return Response(html, mimetype="text/html")


def _ticketing_signin_index():
    copy = _signin_content()
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_site_display_name()}</title>
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <style>
    {_theme_css_root()}
    * {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: var(--bg); color: var(--ink); }}
    header {{ background: #fff; border-bottom: 1px solid var(--line); padding: 14px 24px; display: flex; justify-content: space-between; align-items: center; }}
    header a {{ color: var(--muted); font-size: 13px; text-decoration: none; }}
    main {{ max-width: 920px; margin: 0 auto; padding: 28px 18px 48px; }}
    .layout {{ display: grid; grid-template-columns: 1.1fr .9fr; gap: 18px; }}
    .card {{ background: #fff; border: 1px solid var(--line); border-radius: 18px; padding: 24px; box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06); }}
    .eyebrow {{ font-size: 11px; font-weight: 800; letter-spacing: 1.4px; text-transform: uppercase; color: var(--brand); margin: 0 0 8px; }}
    h1 {{ margin: 0 0 10px; font-size: clamp(32px, 6vw, 44px); line-height: 1.05; }}
    .muted {{ color: var(--muted); line-height: 1.55; margin: 0; }}
    button {{ width: 100%; border: 0; background: #1A1A24; color: #fff; border-radius: 10px; padding: 14px 16px; font-weight: 800; font-size: 15px; cursor: pointer; margin-top: 16px; }}
    button:disabled {{ opacity: 0.65; cursor: not-allowed; }}
    .pill {{ display: inline-block; border: 1px solid var(--line); border-radius: 999px; padding: 4px 9px; font-size: 11px; font-weight: 800; background: #f8fafc; }}
    .pill.ok {{ border-color: #86efac; background: #dcfce7; color: var(--ok); }}
    .pill.deny {{ border-color: #fca5a5; background: #fee2e2; color: var(--deny); }}
    .pill.checking {{ border-color: #fde68a; background: #fef9c3; color: #854d0e; }}
    .verdict {{ margin-top: 18px; border-radius: 14px; padding: 16px; background: #0f172a; color: #e2e8f0; min-height: 100px; }}
    .verdict strong {{ color: #fff; display: block; margin-bottom: 6px; }}
    .verdict .tiny {{ font-size: 12px; color: #94a3b8; margin: 0; line-height: 1.45; }}
    .how {{ margin: 0; padding-left: 18px; color: var(--muted); font-size: 14px; line-height: 1.55; }}
    .how li {{ margin-bottom: 8px; }}
    code {{ font-size: 12px; background: #f1f5f9; padding: 2px 6px; border-radius: 6px; }}
    .presale-link {{ display: inline-block; margin-top: 14px; color: var(--brand); font-weight: 700; text-decoration: none; }}
    {SITE_CTA_CSS}
    {LEMMA_SIGNIN_CSS}
    @media (max-width: 820px) {{ .layout {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  {_site_header(f'<a href="{DEMO_HUB_URL}?lane=builder&from=demo">Return to demo hub</a>')}
  <main>
    <div class="layout">
      <section class="card">
        <p class="eyebrow">{copy["eyebrow"]}</p>
        <h1>{copy["headline"]}</h1>
        <p class="muted">{copy["subhead"]}</p>
        {_lemma_signin_element()}
        <button id="verify-btn" disabled>{copy["primary"]}</button>
        <p class="muted" id="session-copy" style="margin-top:12px;font-size:13px;">Sign in once. This site keeps a session until a fresh passkey is required.</p>
        <a class="presale-link" href="/?tour=presale">Open presale enforcement demo →</a>
        <div class="verdict" id="decision-card">
          <strong>Drop-in Sign in</strong>
          <p class="tiny">This page uses the same <code>&lt;lemma-signin&gt;</code> element from the docs quickstart. Your backend verifies the presentation and sets a session cookie.</p>
        </div>
      </section>
      <aside class="card">
        <p class="eyebrow">Customer site view</p>
        <p class="muted">Site binding: <code id="site-id">{SITE_ID}</code></p>
        <p style="margin:12px 0 6px">Decision <span class="pill" id="status-pill">WAITING</span>
          <span class="pill" id="assurance-pill">policy: {DEMO_REQUIRED_ASSURANCE}</span></p>
        <p class="muted" id="decision-copy">Sign in to start.</p>
        <ol class="how">
          <li>Sign in with lemma.id once — server verifies presentation and sets a session cookie.</li>
          <li>Protected actions reuse the site session until policy requires fresh passkey.</li>
          <li>For Sybil-resistant presale flows, open the presale tour.</li>
        </ol>
      </aside>
    </div>
  </main>
  {_sdk_script_tags()}
  <script>
  {_PLAIN_LANGUAGE_JS}
    const pill = document.getElementById('status-pill');
    const assurancePill = document.getElementById('assurance-pill');
    const decisionCard = document.getElementById('decision-card');
    const decisionCopy = document.getElementById('decision-copy');
    const sessionCopy = document.getElementById('session-copy');
    const signInEl = document.getElementById('lemma-signin-btn');
    const actionBtn = document.getElementById('verify-btn');
    const SITE_POLICY = '{DEMO_REQUIRED_ASSURANCE}';
    let siteSessionPpid = null;

    function setSignInDisabled(disabled) {{
      if (!signInEl) return;
      if (disabled) signInEl.setAttribute('disabled', '');
      else signInEl.removeAttribute('disabled');
    }}

    function setAssurancePill(assurance) {{
      if (!assurancePill) return;
      assurancePill.textContent = assurance ? plainAssurance(assurance) : ('Policy: passkey');
    }}

    async function refreshSessionState() {{
      try {{
        const me = await fetch('/api/me', {{ credentials: 'include' }});
        if (me.ok) {{
          const data = await me.json();
          siteSessionPpid = data.ppid || null;
          if (sessionCopy) sessionCopy.textContent = 'Signed in · PPID ' + (siteSessionPpid || '').slice(0, 24) + '…';
          if (actionBtn) actionBtn.disabled = false;
          setSignInDisabled(true);
          pill.textContent = 'SIGNED IN';
          pill.className = 'pill ok';
          setAssurancePill(data.assurance || SITE_POLICY);
          return true;
        }}
      }} catch (err) {{}}
      siteSessionPpid = null;
      if (sessionCopy) sessionCopy.textContent = 'Sign in once. This site keeps a session until a fresh passkey is required.';
      if (actionBtn) actionBtn.disabled = true;
      setSignInDisabled(false);
      return false;
    }}

    async function completeLoginFromPresentation(presentation, timeMs) {{
      try {{
        const loginRes = await fetch('/api/login', {{
          method: 'POST', credentials: 'include',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ presentation }}),
        }});
        const loginPayload = await loginRes.json();
        if (!loginRes.ok || !loginPayload.success) throw new Error(loginPayload.reason || 'login_failed');
        siteSessionPpid = loginPayload.ppid || null;
        await refreshSessionState();
        decisionCard.innerHTML = '<strong>Signed in</strong><p class="tiny">Site session active · '
          + (timeMs || 0).toFixed(0) + 'ms · PPID ' + (siteSessionPpid || '').slice(0, 24) + '…</p>';
        decisionCopy.textContent = 'Session active. Run a protected action or open the presale tour.';
        return true;
      }} catch (err) {{
        pill.textContent = 'ERROR';
        pill.className = 'pill deny';
        decisionCopy.textContent = 'Sign in failed: ' + err.message;
        setSignInDisabled(false);
        return false;
      }}
    }}

    async function runProtectedAction() {{
      if (!siteSessionPpid && !(await refreshSessionState())) {{
        decisionCopy.textContent = 'Sign in with lemma.id first.';
        return;
      }}
      actionBtn.disabled = true;
      pill.textContent = 'CHECKING';
      pill.className = 'pill checking';
      try {{
        const serverRes = await fetch('/api/demo/action', {{
          method: 'POST', credentials: 'include',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ action: '{copy["action"]}', at: Date.now() }}),
        }});
        const serverEntry = await serverRes.json();
        if (serverEntry.success) {{
          pill.textContent = 'ALLOW';
          pill.className = 'pill ok';
          decisionCopy.textContent = 'Protected action allowed via site session.';
        }} else {{
          pill.textContent = 'DENY';
          pill.className = 'pill deny';
          decisionCopy.textContent = formatDenyReason(serverEntry.reason || 'denied');
        }}
      }} catch (err) {{
        decisionCopy.textContent = 'Action failed: ' + err.message;
      }} finally {{
        actionBtn.disabled = !siteSessionPpid;
      }}
    }}

    refreshSessionState();
    signInEl?.addEventListener('lemma-signin-success', (e) => {{
      pill.textContent = 'CHECKING';
      pill.className = 'pill checking';
      completeLoginFromPresentation(e.detail.presentation, e.detail.timeMs);
    }});
    signInEl?.addEventListener('lemma-signin-error', (e) => {{
      pill.textContent = 'DENY';
      pill.className = 'pill deny';
      decisionCopy.textContent = formatDenyReason(e.detail.reason || 'not_verified');
      setSignInDisabled(false);
    }});
    actionBtn?.addEventListener('click', () => runProtectedAction());
  </script>
</body>
</html>"""
    return Response(html, mimetype="text/html")


def _welcome_content():
    base = _presale_content()
    base.update({
        "eyebrow": "Encore member access",
        "headline": "Tickets for fans, not bots.",
        "subhead": "Sign in to browse member presales and unlock one verified-fan code for the Midnight Atlas tour.",
        "register": "Join the Midnight Atlas presale",
        "claim": "Confirm and reveal code",
        "retry": "Request another code",
    })
    return base


def _ticketing_welcome_index():
    return _presale_index(welcome_mode=True)


def _presale_index(welcome_mode=False):
    copy = _welcome_content() if welcome_mode else _presale_content()
    body_class = "welcome-mode" if welcome_mode else ""
    layout_class = "layout layout-welcome" if welcome_mode else "layout"
    aside_block = "" if welcome_mode else f"""
      <aside class="card">
        <p class="eyebrow">Server verification</p>
        <p class="muted">Site binding: <code>{SITE_ID}</code></p>
        <p style="margin:12px 0 6px">Decision <span class="pill" id="status-pill">WAITING</span>
          <span class="pill" id="assurance-pill">default: {PRESALE_CODE_CLAIM_ASSURANCE}</span></p>
        <p class="muted" id="decision-copy">Join the presale first, then unlock your code.</p>
        <label class="dev-toggle">
          <input type="checkbox" id="backend-gates-toggle">
          Show backend gates (engineer view)
        </label>
        <details open>
          <summary>Fan-visible flow</summary>
          <ol class="how">
            <li>Passkey register binds a site-private ID (Step 1).</li>
            <li>Claim confirms with verified human + fresh passkey (Step 2).</li>
            <li>One code per person per drop.</li>
          </ol>
        </details>
        <details open class="engineer-only" id="receipt-details">
          <summary>Server verification receipt</summary>
          <div class="server-receipt" id="server-receipt" hidden>
            <div id="gate-chips" class="gate-chips"></div>
            <dl id="server-receipt-fields"></dl>
          </div>
          <p class="muted" id="receipt-placeholder" style="font-size:12px;margin-top:8px;">Run a presale action to populate the receipt.</p>
        </details>
        <details class="engineer-only" id="crypto-envelope-details">
          <summary>Cryptographic envelope</summary>
          <pre id="stamp-json">{{}}</pre>
          <pre id="fresh-attestation-json" style="margin-top:10px;">{{}}</pre>
        </details>
        <p class="eyebrow" style="margin-top:18px;">Typical phone-first vs this demo</p>
        <table class="compare-table">
          <thead>
            <tr><th>Dimension</th><th>Phone-first presale</th><th>This demo</th></tr>
          </thead>
          <tbody>
            <tr><td>Identity</td><td>Phone or email uniqueness</td><td>Site-scoped ID from passkey</td></tr>
            <tr><td>Claim confirmation</td><td>SMS OTP or none</td><td>Verified human + fresh passkey</td></tr>
            <tr><td>Contact data</td><td>Auth + CRM</td><td>Site-local delivery only</td></tr>
          </tbody>
        </table>
        <details>
          <summary>Action log</summary>
          <pre id="action-log">[]</pre>
        </details>
      </aside>"""
    verdict_intro = """
        <div class="verdict" id="decision-card">
          <strong>How this works</strong>
          <p class="tiny">Sign in with your passkey, join the drop, then reveal one verified-fan code. Encore never sees your email, password, or identity documents — just a private member ID.</p>
        </div>""" if welcome_mode else """
        <div class="verdict" id="decision-card">
          <strong>Protected presale flow</strong>
          <p class="tiny">Step 1: passkey register binds your site-private ID. Step 2: confirm and reveal with verified-human assurance plus a fresh passkey — one code per person. Contact info is optional delivery after you claim.</p>
        </div>"""
    welcome_contrast = ""
    welcome_progress = """
    <div class="welcome-progress" id="welcome-progress" aria-label="Demo walkthrough">
      <span class="welcome-progress-label">Live demo</span>
      <span class="welcome-step" data-welcome-step="signin">1 · Sign in with a passkey</span>
      <span class="welcome-step" data-welcome-step="claim">2 · Claim your presale code</span>
      <span class="welcome-step" data-welcome-step="deny">3 · Try to claim a second</span>
      <span class="welcome-step" data-welcome-step="return">4 · One code per person</span>
    </div>""" if welcome_mode else ""
    privacy_cta = f"""
    <section class="card welcome-privacy" id="welcome-privacy" hidden>
      <p class="eyebrow">Recommended for you</p>
      <h2 style="margin:0 0 8px;font-size:22px;">More member presales</h2>
      <p class="muted" style="font-size:14px;">Your Encore account is active. New verified-fan drops will appear here.</p>
      <a class="presale-link" href="{TRIALS_DEMO_URL}/?from=welcome" target="_blank" rel="noopener">Explore Northstar →</a>
      <a class="presale-link" href="{DEMO_HUB_URL}?lane=builder&from=welcome" style="margin-left:12px;">lemma.id developer guide →</a>
    </section>""" if welcome_mode else ""
    welcome_status = "" if welcome_mode else ""
    welcome_engineer_stubs = """
        <details class="developer-tools">
          <summary>Developer details</summary>
          <p style="margin:4px 0 6px"><span class="pill" id="status-pill">SIGNED IN</span>
            <span class="pill" id="assurance-pill">passkey session</span></p>
          <p class="muted" id="decision-copy">Server session active.</p>
          <label class="dev-toggle">
            <input type="checkbox" id="backend-gates-toggle">
            Show verification gates
          </label>
          <div class="server-receipt" id="server-receipt" hidden>
            <div id="gate-chips" class="gate-chips"></div>
            <dl id="server-receipt-fields"></dl>
          </div>
          <details class="engineer-only"><summary>Cryptographic envelope</summary>
          <pre id="stamp-json">{{}}</pre>
          <pre id="fresh-attestation-json">{{}}</pre>
          </details>
          <details class="engineer-only"><summary>Server action log</summary>
          <pre id="action-log">[]</pre>
          </details>
          <p id="receipt-placeholder"></p>
        </details>""" if welcome_mode else ""
    header_links = f"""
    <nav class="site-nav"><a href="#events">Events</a><a href="#presale">Presales</a><button class="nav-account" id="logout-btn" hidden>Sign out</button></nav>""" if welcome_mode else f"""
    <a href="{DEMO_HUB_URL}?lane=builder&from=demo">Return to demo hub</a>
    <a href="/" style="margin-left:12px;">← Sign-in demo</a>"""
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_site_display_name()}</title>
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <style>
    {_theme_css_root()}
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
      padding: 14px max(24px, calc((100vw - 1120px) / 2));
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .site-brand {{ display: flex; align-items: center; gap: 10px; }}
    .site-icon {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 42px;
      height: 42px;
      flex: 0 0 42px;
      border: 1px solid var(--icon-border);
      border-radius: 10px;
      background: var(--icon-bg);
    }}
    .site-icon svg {{ width: 28px; height: 28px; }}
    header strong {{ font-size: 19px; letter-spacing: -0.3px; }}
    header a {{ color: var(--muted); font-size: 13px; text-decoration: none; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 48px 22px 72px; }}
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
      background: #1A1A24;
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
      color: #334155;
      border: 1px solid #cbd5e1;
    }}
    .btn-ghost {{
      background: #f8fafc;
      color: #475569;
      border: 1px solid var(--line);
    }}
    button:disabled, .btn-secondary:disabled {{ opacity: 0.65; cursor: not-allowed; }}
    .steps {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin: 18px 0 8px;
    }}
    .step {{
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px 12px;
      font-size: 12px;
      font-weight: 700;
      color: var(--muted);
      background: #f8fafc;
    }}
    .step.active {{ border-color: #cbd5e1; background: #f8fafc; color: #334155; }}
    .step.done {{ border-color: #86efac; background: #dcfce7; color: var(--ok); }}
    .code-display {{
      margin-top: 18px;
      font-size: clamp(28px, 6vw, 40px);
      font-weight: 800;
      letter-spacing: 4px;
      text-align: center;
      padding: 16px;
      border-radius: 14px;
      background: #f8fafc;
      border: 1px solid #cbd5e1;
      color: #334155;
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
    .already-claimed-notice {{
      margin-top: 14px;
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid #fcd34d;
      background: #fffbeb;
      color: #92400e;
    }}
    .already-claimed-notice strong {{
      display: block;
      margin-bottom: 4px;
      font-size: 15px;
      color: #78350f;
    }}
    .already-claimed-notice p {{
      margin: 0;
      font-size: 13px;
      line-height: 1.45;
      color: #92400e;
    }}
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
      border: 1px solid #cbd5e1;
      background: #f8fafc;
    }}
    .server-receipt strong {{ display: block; margin-bottom: 8px; color: #334155; }}
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
    .defense-strip {{
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 8px;
      margin: 16px 0 4px;
    }}
    .defense-item {{
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 8px 10px;
      background: #f8fafc;
      font-size: 11px;
      font-weight: 700;
      color: #334155;
    }}
    .defense-item small {{
      display: block;
      margin-top: 2px;
      font-weight: 500;
      color: var(--muted);
    }}
    .contact-note {{
      margin: 4px 0 0;
      font-size: 12px;
      color: var(--muted);
    }}
    .tour-banner {{
      margin-bottom: 18px;
      padding: 16px 18px;
      border: 1px solid #cbd5e1;
      border-radius: 14px;
      background: #f8fafc;
    }}
    .tour-banner strong {{
      display: block;
      margin-bottom: 10px;
      color: #334155;
      font-size: 14px;
    }}
    .tour-checklist {{
      margin: 0;
      padding-left: 20px;
      font-size: 13px;
      line-height: 1.6;
      color: #334155;
    }}
    .tour-checklist li {{ margin-bottom: 4px; }}
    .tour-checklist li.active {{ font-weight: 800; color: #334155; }}
    .tour-checklist li.done {{ color: var(--ok); }}
    .tour-impact {{
      margin: 12px 0 0;
      padding: 10px 12px;
      border-radius: 10px;
      background: #fff;
      border: 1px solid var(--line);
      font-size: 13px;
      color: #334155;
      line-height: 1.45;
    }}
    .compare-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      margin-top: 8px;
    }}
    .compare-table th,
    .compare-table td {{
      border: 1px solid var(--line);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    .compare-table th {{
      background: #f8fafc;
      font-weight: 800;
      color: #334155;
    }}
    .compare-table td:first-child {{
      font-weight: 700;
      color: #475569;
      width: 34%;
    }}
    .gate-chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 10px;
    }}
    .gate-chip {{
      display: inline-block;
      border: 1px solid #86efac;
      background: #dcfce7;
      color: var(--ok);
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 10px;
      font-weight: 800;
    }}
    .gate-chip.fail {{
      border-color: #fca5a5;
      background: #fee2e2;
      color: var(--deny);
    }}
    .dev-toggle {{
      margin: 14px 0 0;
      font-size: 12px;
      color: var(--muted);
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .engineer-only {{
      display: none;
    }}
    body.show-backend-gates .engineer-only {{
      display: block;
    }}
    .attack-lab {{
      margin-top: 14px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
      display: none;
    }}
    body.show-backend-gates .attack-lab,
    body.tour-mode .attack-lab {{
      display: block;
    }}
    body.welcome-mode .defense-strip,
    body.welcome-mode .attack-lab {{
      display: none;
    }}
    body.welcome-mode .layout-welcome {{
      grid-template-columns: 1fr;
      max-width: 1120px;
      margin: 0 auto;
    }}
    .site-nav {{ display: flex; align-items: center; gap: 22px; }}
    .nav-account {{
      width: auto;
      margin: 0;
      padding: 8px 12px;
      color: #475569;
      background: #fff;
      border: 1px solid var(--line);
      font-size: 12px;
    }}
    body.welcome-mode main {{ min-height: calc(100vh - 72px); }}
    body.welcome-mode .layout-welcome > .card {{
      padding: clamp(28px, 5vw, 56px);
      background:
        radial-gradient(circle at 92% 8%, rgba(217,119,6,.12), transparent 32%),
        #fff;
    }}
    body.welcome-mode .auth-intro {{
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(320px, .8fr);
      gap: clamp(36px, 7vw, 88px);
      align-items: center;
      min-height: 520px;
    }}
    .auth-message h1 {{ font-size: clamp(46px, 7vw, 72px); max-width: 680px; }}
    .auth-message .muted {{ font-size: 18px; max-width: 600px; }}
    .signin-panel {{ padding: 26px; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,255,255,.94); box-shadow: 0 18px 45px rgba(15,23,42,.08); }}
    .signin-panel h2 {{ margin: 0 0 8px; font-size: 23px; }}
    .signin-panel .contact-note {{ text-align: center; margin-top: 12px; }}
    body.welcome-mode.signed-in .auth-intro {{ display: none; }}
    .member-home {{ display: none; }}
    body.welcome-mode.signed-in .member-home {{ display: block; }}
    .member-hero {{ display: flex; justify-content: space-between; gap: 24px; align-items: flex-end; margin-bottom: 26px; }}
    .member-hero h1 {{ font-size: clamp(36px, 5vw, 52px); }}
    .event-card {{ display: grid; grid-template-columns: minmax(220px, .75fr) minmax(0, 1.25fr); overflow: hidden; border: 1px solid var(--line); border-radius: 18px; }}
    .event-art {{ min-height: 290px; padding: 28px; display: flex; flex-direction: column; justify-content: flex-end; color: #fff; background: linear-gradient(145deg,#111827,#4c1d95 60%,#d97706); }}
    .event-art strong {{ font-size: 31px; line-height: 1; }}
    .event-art span {{ margin-top: 8px; color: #fde68a; }}
    .event-info {{ padding: 30px; background: #fff; }}
    .event-meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 18px; }}
    .event-meta span {{ padding: 6px 9px; border-radius: 999px; background: #f8fafc; border: 1px solid var(--line); color: #475569; font-size: 12px; }}
    .human-gate-copy {{ margin: 18px 0 10px; padding: 14px; border-radius: 12px; background: #fffbeb; border: 1px solid #fde68a; }}
    .human-gate-copy strong {{ display: block; margin-bottom: 4px; }}
    .code-locked {{
      margin-top: 18px;
      padding: 16px;
      border-radius: 14px;
      border: 1px dashed #f59e0b;
      background: #fffbeb;
    }}
    .code-locked strong {{ display: block; margin-bottom: 6px; color: #92400e; }}
    .code-locked .muted {{ font-size: 13px; }}
    .code-display.is-locked {{
      margin-top: 12px;
      letter-spacing: 6px;
      color: #92400e;
      background: #fff7ed;
      border-color: #fde68a;
    }}
    .confirm-chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 14px 0 4px;
    }}
    .confirm-chip {{
      display: inline-flex;
      align-items: center;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid #86efac;
      background: #dcfce7;
      color: var(--ok);
      font-size: 12px;
      font-weight: 800;
    }}
    .developer-tools {{ margin-top: 22px; border: 1px solid var(--line); border-radius: 12px; padding: 0 16px 16px; background: #fff; }}
    .developer-tools > summary {{ padding: 15px 0; list-style: none; display: flex; justify-content: space-between; }}
    .developer-tools > summary::after {{ content: "＋"; color: var(--muted); }}
    .developer-tools[open] > summary::after {{ content: "−"; }}
    body.welcome-mode .verdict {{ display: none; }}
    body.welcome-mode .steps,
    body.welcome-mode .drop-meta {{
      display: none;
    }}
    .welcome-progress {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 16px;
      max-width: 640px;
      margin-left: auto;
      margin-right: auto;
    }}
    .welcome-step {{
      font-size: 11px;
      font-weight: 700;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      color: var(--muted);
      background: #fff;
    }}
    .welcome-step.is-active {{
      border-color: var(--brand);
      color: var(--brand);
      background: var(--icon-bg);
    }}
    .welcome-step.is-done {{
      border-color: #86efac;
      color: var(--ok);
      background: #f0fdf4;
    }}
    body.welcome-mode .welcome-contrast.is-dismissed {{
      display: none;
    }}
    body.welcome-mode #flag-btn,
    body.welcome-mode #clear-flag-btn,
    body.welcome-mode #attack-lab,
    body.welcome-mode #defense-strip,
    body.welcome-mode .drop-meta {{
      display: none;
    }}
    .welcome-progress {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      margin-bottom: 18px;
    }}
    .welcome-progress-label {{
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
      margin-right: 4px;
    }}
    .attack-lab-buttons {{
      display: grid;
      gap: 8px;
      margin-top: 10px;
    }}
    {SITE_CTA_CSS}
    {LEMMA_SIGNIN_CSS}
    @media (max-width: 820px) {{
      .layout, body.welcome-mode .auth-intro, .event-card {{ grid-template-columns: 1fr; }}
      .defense-strip {{ grid-template-columns: 1fr 1fr; }}
      main {{ padding-top: 28px; }}
      .site-nav a {{ display: none; }}
      .member-hero {{ align-items: flex-start; flex-direction: column; }}
    }}
  </style>
</head>
<body class="{body_class}">
  {_site_header(header_links)}
  <main>
    {welcome_progress}
    {welcome_contrast}
    <div class="tour-banner" id="tour-banner" hidden>
      <strong>Guided presale demo</strong>
      <ol class="tour-checklist" id="tour-checklist">
        <li data-tour-step="register" id="tour-step-register">Register with passkey, phone is delivery only</li>
        <li data-tour-step="claim" id="tour-step-claim">Confirm and reveal code — verified human + fresh passkey</li>
        <li data-tour-step="retry" id="tour-step-retry">Retry with the same lemma.id, denied, one code per fan</li>
        <li data-tour-step="flag" id="tour-step-flag">Simulate risk flag, IDV penalty, then code at isHuman</li>
        <li data-tour-step="attack" id="tour-step-attack">Attack lab, replay stamp or skip Step 1</li>
      </ol>
      <p class="tour-impact" id="tour-impact">Sign in with a passkey first. Join the drop, then confirm and reveal your code with verified-human + fresh passkey proof.</p>
    </div>
    <div class="{layout_class}">
      <section class="card">
        <div class="auth-intro">
          <div class="auth-message">
            <p class="eyebrow">{copy["eyebrow"]}</p>
            <h1>{copy["headline"]}</h1>
            <p class="muted">{copy["subhead"]}</p>
          </div>
          <div class="signin-panel">
            <h2>Sign in to Encore</h2>
            <p class="muted">Use your lemma.id passkey to access member presales.</p>
            {_lemma_signin_element()}
            <p class="contact-note" id="session-copy">No email or password required.</p>
          </div>
        </div>
        <div class="gated-section" id="presale-gated" hidden>
        <div class="member-home">
        <div class="member-hero">
          <div><p class="eyebrow">Member presales</p><h1 style="margin-bottom:8px;">Welcome back.</h1><p class="muted">Your saved events and verified-fan offers.</p></div>
          <span class="pill ok">Member signed in</span>
        </div>
        <div class="event-card" id="presale">
          <div class="event-art"><strong>Midnight<br>Atlas</strong><span>Afterglow World Tour</span></div>
          <div class="event-info">
            <p class="eyebrow">Presale opens today</p>
            <h2 style="margin:0;font-size:28px;">Brooklyn · October 18</h2>
            <div class="event-meta"><span>8:00 PM</span><span>Harbor Arena</span><span>From $48</span></div>
            <p class="muted">Join the member list with your passkey. Revealing a code is limited to one verified human per account.</p>
            <div class="human-gate-copy"><strong>Verified-fan code requires confirmation</strong><span class="muted">Confirm with verified-human assurance and a fresh passkey to reveal your one-time code.</span></div>
        </div>
        </div>
        <div class="defense-strip" id="defense-strip">
          <div class="defense-item">Site PPID<small>passkey proof</small></div>
          <div class="defense-item">Action stamp<small>bound mutation</small></div>
          <div class="defense-item">Server nonce<small>replay block</small></div>
          <div class="defense-item">Human proof<small>claim ceremony</small></div>
          <div class="defense-item">1 code / fan<small>PPID ledger</small></div>
        </div>
        <div class="steps">
          <div class="step active" id="step-register">1 · Passkey register</div>
          <div class="step" id="step-claim">2 · Confirm &amp; reveal</div>
        </div>
        <p class="muted drop-meta" style="margin-top:12px;font-size:13px;">Drop: <code id="drop-id">{PRESALE_DROP_ID}</code></p>
        <button id="register-btn" disabled>{copy["register"]}</button>
        <div class="code-locked" id="code-locked" hidden>
          <strong>Verified-fan code requires confirmation</strong>
          <p class="muted">One code per person. Confirm with a verified-human passkey to reveal yours.</p>
          <div class="code-display is-locked" aria-hidden="true">••••••••</div>
        </div>
        <button type="button" class="btn-secondary site-cta" id="claim-btn" disabled>{copy["claim"]}</button>
        <button type="button" class="btn-secondary" id="retry-btn" disabled>{copy["retry"]}</button>
        <button type="button" class="btn-secondary btn-ghost" id="flag-btn">{copy["flag"]}</button>
        <button type="button" class="btn-secondary btn-ghost" id="clear-flag-btn">{copy["clear_flag"]}</button>
        <button type="button" class="btn-secondary btn-ghost" id="clear-claim-btn" hidden>{copy["clear_claim"]}</button>
        <div class="already-claimed-notice" id="already-claimed-notice" hidden>
          <strong>You already claimed your code</strong>
          <p>This drop is one code per person. Your existing code is shown below. Use Clear claim (demo reset) to release this PPID and try again.</p>
        </div>
        {welcome_status}
        {welcome_engineer_stubs}
        <details class="attack-lab" id="attack-lab">
          <summary>Attack lab</summary>
          <div class="attack-lab-buttons">
            <button type="button" class="btn-secondary btn-ghost" id="replay-btn">Replay last stamp</button>
            <button type="button" class="btn-secondary btn-ghost" id="skip-step-btn">Skip Step 1 (claim without register)</button>
          </div>
        </details>
        <div class="confirm-chips" id="confirm-chips" hidden>
          <span class="confirm-chip">One-person limit verified</span>
          <span class="confirm-chip">Passkey confirmed just now</span>
        </div>
        <div class="code-display" id="code-display" hidden>--------</div>
        <div id="delivery-panel" hidden style="margin-top:18px;padding-top:18px;border-top:1px solid var(--line);">
          <p class="eyebrow" style="margin-bottom:6px;">Optional delivery</p>
          <p class="muted" style="font-size:13px;margin-bottom:12px;">Where should we send your code? Stays on this site — lemma.id never sees it.</p>
          <label for="email">{copy["form_email"]}</label>
          <input id="email" value="" placeholder="{copy["placeholder_email"]}" aria-label="{copy["form_email"]}">
          <label for="phone">{copy["form_phone"]}</label>
          <input id="phone" value="" placeholder="{copy["placeholder_phone"]}" aria-label="{copy["form_phone"]}">
          <button type="button" class="btn-secondary" id="save-delivery-btn">Save delivery info</button>
          <button type="button" class="btn-secondary btn-ghost" id="skip-delivery-btn">Skip for now</button>
        </div>
        </div>
        </div>
        {verdict_intro}
      </section>
      {aside_block}
    </div>
    {privacy_cta}
  </main>
  {_sdk_script_tags()}
  <script>
  {_PLAIN_LANGUAGE_JS}
    const DROP_ID = {PRESALE_DROP_ID!r};
    const SITE_ID = '{SITE_ID}';
    const CLAIM_ASSURANCE = {PRESALE_CODE_CLAIM_ASSURANCE!r};
    const ESCALATED_ASSURANCE = {PRESALE_ESCALATED_ASSURANCE!r};
    const REGISTER_PATH = {PRESALE_REGISTER_PATH!r};
    const REGISTER_ACTION = {copy["register_action"]!r};
    const CLAIM_ACTION = {copy["claim_action"]!r};
    const CLAIM_PATH = {PRESALE_CLAIM_PATH!r};
    const TOUR_MODE = new URLSearchParams(window.location.search).get('tour') === 'presale';
    const WELCOME_MODE = document.body.classList.contains('welcome-mode');
    const WELCOME_SEQUENCE = ['contrast', 'signin', 'claim', 'deny', 'return'];
    const TOUR_IMPACTS = {{
      register: 'Passkey binds a site-private ID — no email or password required.',
      claim: 'Confirm and reveal: verified human + fresh passkey — one account per person, bots cannot replay cached sessions for codes.',
      retry: 'Ledger enforces one code per verified person. Same lemma.id cannot farm multiple codes.',
      flag: 'Site doubt escalates to fresh IDV, policy-driven penalty before code issuance.',
      attack: 'Attack lab shows replay and skip-step denies that bots hit in production.',
    }};
    const pill = document.getElementById('status-pill');
    const assurancePill = document.getElementById('assurance-pill');
    const stampJson = document.getElementById('stamp-json');
    const freshAttestationJson = document.getElementById('fresh-attestation-json');
    const gateChipsEl = document.getElementById('gate-chips');
    const receiptPlaceholder = document.getElementById('receipt-placeholder');
    const backendGatesToggle = document.getElementById('backend-gates-toggle');
    const actionLogEl = document.getElementById('action-log');
    const decisionCard = document.getElementById('decision-card');
    const decisionCopy = document.getElementById('decision-copy');
    const serverReceipt = document.getElementById('server-receipt');
    const serverReceiptFields = document.getElementById('server-receipt-fields');
    const codeDisplay = document.getElementById('code-display');
    const stepRegister = document.getElementById('step-register');
    const stepClaim = document.getElementById('step-claim');
    const tourBanner = document.getElementById('tour-banner');
    const tourImpact = document.getElementById('tour-impact');
    const signInEl = document.getElementById('lemma-signin-btn');
    const presaleGated = document.getElementById('presale-gated');
    const logoutBtn = document.getElementById('logout-btn');
    let sharedVerifier = null;
    let lastPpid = null;
    let siteSessionPpid = null;
    let presaleRegistered = false;
    let tourStepIndex = 0;
    let lastStampedRequest = null;
    const TOUR_SEQUENCE = ['register', 'claim', 'retry', 'flag', 'attack'];
    const BACKEND_GATES_KEY = 'lemma_presale_show_backend_gates';
    const PRESALE_SESSION_KEY = 'lemma_presale_session_v2';

    function savePresaleSession(patch) {{
      try {{
        const prev = JSON.parse(sessionStorage.getItem(PRESALE_SESSION_KEY) || '{{}}');
        sessionStorage.setItem(PRESALE_SESSION_KEY, JSON.stringify({{ ...prev, ...patch, dropId: DROP_ID }}));
      }} catch (e) {{}}
    }}

    function loadPresaleSession() {{
      try {{
        const saved = JSON.parse(sessionStorage.getItem(PRESALE_SESSION_KEY) || '{{}}');
        if (saved.dropId !== DROP_ID) return null;
        return saved;
      }} catch (e) {{
        return null;
      }}
    }}

    if (TOUR_MODE) {{
      document.body.classList.add('tour-mode');
    }}
    if (TOUR_MODE && tourBanner) {{
      tourBanner.hidden = false;
      setTourHighlight('register');
    }}

    function setWelcomeStep(stepId) {{
      if (!WELCOME_MODE) return;
      const idx = WELCOME_SEQUENCE.indexOf(stepId);
      document.querySelectorAll('.welcome-step').forEach((el) => {{
        const step = el.getAttribute('data-welcome-step');
        const stepIdx = WELCOME_SEQUENCE.indexOf(step);
        el.classList.remove('is-active', 'is-done');
        if (stepIdx < idx) el.classList.add('is-done');
        else if (stepIdx === idx) el.classList.add('is-active');
      }});
    }}

    function showWelcomePrivacy() {{
      const panel = document.getElementById('welcome-privacy');
      if (panel) panel.hidden = false;
    }}

    if (WELCOME_MODE) {{
      setWelcomeStep('signin');
    }}

    function applyBackendGatesToggle(enabled) {{
      document.body.classList.toggle('show-backend-gates', !!enabled);
      try {{
        localStorage.setItem(BACKEND_GATES_KEY, enabled ? '1' : '0');
      }} catch (e) {{}}
    }}

    if (backendGatesToggle) {{
      let stored = false;
      try {{
        stored = localStorage.getItem(BACKEND_GATES_KEY) === '1';
      }} catch (e) {{}}
      backendGatesToggle.checked = stored;
      applyBackendGatesToggle(stored);
      backendGatesToggle.addEventListener('change', () => {{
        applyBackendGatesToggle(backendGatesToggle.checked);
      }});
    }}

    function setTourHighlight(stepId) {{
      if (!TOUR_MODE) return;
      const idx = TOUR_SEQUENCE.indexOf(stepId);
      if (idx >= 0) tourStepIndex = idx;
      TOUR_SEQUENCE.forEach((id, i) => {{
        const el = document.getElementById('tour-step-' + id);
        if (!el) return;
        el.className = i < tourStepIndex ? 'done' : (i === tourStepIndex ? 'active' : '');
      }});
      if (tourImpact && TOUR_IMPACTS[stepId]) {{
        tourImpact.textContent = TOUR_IMPACTS[stepId];
      }}
      const target = document.getElementById(
        stepId === 'register' ? 'register-btn'
          : stepId === 'claim' ? 'claim-btn'
          : stepId === 'retry' ? 'retry-btn'
          : stepId === 'attack' ? 'replay-btn'
          : 'flag-btn'
      );
      if (target) {{
        try {{ target.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }}); }} catch (e) {{}}
      }}
    }}

    function advanceTour(stepId) {{
      if (!TOUR_MODE) return;
      const idx = TOUR_SEQUENCE.indexOf(stepId);
      if (idx < 0) return;
      tourStepIndex = Math.min(TOUR_SEQUENCE.length - 1, idx + 1);
      const next = TOUR_SEQUENCE[tourStepIndex] || stepId;
      setTourHighlight(next);
    }}

    if (typeof ProofVerifier === 'undefined' && typeof IsHumanVerifier === 'undefined') {{
      const msg = window.__lemmaSdkLoadError
        || 'Lemma SDK did not load, check that {LEMMA_ORIGIN} is reachable.';
      decisionCopy.textContent = msg;
      ['register-btn', 'claim-btn', 'retry-btn', 'flag-btn', 'clear-flag-btn'].forEach((id) => {{
        const el = document.getElementById(id);
        if (el) el.disabled = true;
      }});
    }}

    function makeVerifier(requiredAssurance) {{
      const assurance = requiredAssurance || CLAIM_ASSURANCE;
      if (!sharedVerifier) {{
        sharedVerifier = new IsHumanVerifier({{
          siteId: '{SITE_ID}',
          lemmaOrigin: '{LEMMA_ORIGIN}',
          autoProvision: true,
          requiredAssurance: assurance,
          debug: true,
          isBlockedLocally: async (ppid) => {{
            const res = await fetch('/api/demo/policy/check?ppid=' + encodeURIComponent(ppid));
            const data = await res.json();
            return {{ blocked: !!data.blocked, doubt_required: !!data.doubt_required }};
          }},
        }});
      }} else {{
        sharedVerifier.requiredAssurance = assurance;
        sharedVerifier.autoProvision = true;
      }}
      return sharedVerifier;
    }}

    function contactPayload() {{
      return {{ drop_id: DROP_ID }};
    }}

    function deliveryPayload() {{
      return {{
        drop_id: DROP_ID,
        email: document.getElementById('email')?.value || '',
        phone: document.getElementById('phone')?.value || '',
      }};
    }}

    function showDeliveryPanel() {{
      const panel = document.getElementById('delivery-panel');
      if (panel) panel.hidden = false;
    }}

    async function saveDelivery(skipEmpty) {{
      const payload = deliveryPayload();
      if (skipEmpty && !payload.email && !payload.phone) {{
        const panel = document.getElementById('delivery-panel');
        if (panel) panel.hidden = true;
        return;
      }}
      try {{
        const res = await fetch('/api/presale/delivery', {{
          method: 'POST',
          credentials: 'include',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload),
        }});
        const data = await res.json();
        if (data.success) {{
          savePresaleSession({{ contact: {{ email: payload.email, phone: payload.phone }} }});
          decisionCopy.textContent = 'Delivery info saved on this site only.';
          const panel = document.getElementById('delivery-panel');
          if (panel) panel.hidden = true;
        }} else {{
          decisionCopy.textContent = formatDenyReason(data.reason || 'unknown');
        }}
      }} catch (err) {{
        decisionCopy.textContent = err.message;
      }}
    }}

    function setSignInDisabled(disabled) {{
      if (!signInEl) return;
      if (disabled) signInEl.setAttribute('disabled', '');
      else signInEl.removeAttribute('disabled');
    }}

    function updatePresaleGatedVisibility(signedIn) {{
      if (presaleGated) presaleGated.hidden = !signedIn;
      document.body.classList.toggle('signed-in', !!signedIn);
      if (logoutBtn) logoutBtn.hidden = !signedIn;
    }}

    async function refreshSessionState() {{
      const sessionCopy = document.getElementById('session-copy');
      const registerBtn = document.getElementById('register-btn');
      try {{
        const me = await fetch('/api/me', {{ credentials: 'include' }});
        if (me.ok) {{
          const data = await me.json();
          siteSessionPpid = data.ppid || null;
          lastPpid = siteSessionPpid || lastPpid;
          if (sessionCopy) {{
            sessionCopy.textContent = 'Signed in with passkey · PPID ' + (siteSessionPpid || '').slice(0, 24) + '…';
          }}
          setSignInDisabled(true);
          updatePresaleGatedVisibility(true);
          if (registerBtn && !presaleRegistered) registerBtn.disabled = false;
          pill.textContent = 'SIGNED IN';
          pill.className = 'pill ok';
          if (WELCOME_MODE) setWelcomeStep('claim');
          await syncPresaleRegistrationStatus();
          return true;
        }}
      }} catch (err) {{}}
      siteSessionPpid = null;
      if (sessionCopy) {{
        sessionCopy.textContent = 'Sign in once with a passkey. Presale steps unlock after you have a site session.';
      }}
      setSignInDisabled(false);
      updatePresaleGatedVisibility(false);
      if (registerBtn) registerBtn.disabled = true;
      return false;
    }}

    async function ensureSiteSession() {{
      if (siteSessionPpid) return true;
      const ok = await refreshSessionState();
      if (ok) return true;
      decisionCopy.textContent = 'Sign in with lemma.id before running presale steps.';
      return false;
    }}

    async function completeLoginFromPresentation(presentation) {{
      pill.textContent = 'CHECKING';
      pill.className = 'pill checking';
      decisionCard.innerHTML = '<strong>Sign in with lemma.id</strong><p class="tiny">Server verifies your signed presentation and sets a site session cookie.</p>';
      try {{
        const loginRes = await fetch('/api/login', {{
          method: 'POST',
          credentials: 'include',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ presentation }}),
        }});
        const loginPayload = await loginRes.json();
        if (!loginRes.ok || !loginPayload.success) {{
          throw new Error(loginPayload.reason || 'login_failed');
        }}
        siteSessionPpid = loginPayload.ppid || null;
        lastPpid = siteSessionPpid;
        await refreshSessionState();
        await syncPresaleRegistrationStatus();
        if (WELCOME_MODE) {{
          setWelcomeStep('claim');
          decisionCopy.textContent = "You're in. No email, no password, nothing to breach.";
          decisionCard.innerHTML = '<strong>Signed in</strong><p class="tiny">Next: register for the drop, then claim your one-time code.</p>';
        }} else {{
          decisionCopy.textContent = 'Signed in. Continue with Step 1 register or Step 2 claim.';
        }}
        return true;
      }} catch (err) {{
        pill.textContent = 'ERROR';
        pill.className = 'pill deny';
        decisionCopy.textContent = 'Sign in failed: ' + err.message;
        setSignInDisabled(false);
        return false;
      }}
    }}

    function stampBody(payload) {{
      const source = payload || contactPayload();
      return {{
        drop_id: String(source.drop_id || DROP_ID).trim(),
        email: String(source.email || '').trim(),
        phone: String(source.phone || '').trim(),
      }};
    }}

    function stampBodiesMatch(left, right) {{
      const a = stampBody(left);
      const b = stampBody(right);
      return a.drop_id === b.drop_id && a.email === b.email && a.phone === b.phone;
    }}

    function setStepState(registered) {{
      presaleRegistered = !!registered;
      if (stepRegister) stepRegister.className = 'step ' + (registered ? 'done' : 'active');
      if (stepClaim) stepClaim.className = 'step ' + (registered ? 'active' : '');
      const claimBtn = document.getElementById('claim-btn');
      const retryBtn = document.getElementById('retry-btn');
      const codeLocked = document.getElementById('code-locked');
      const confirmChips = document.getElementById('confirm-chips');
      if (claimBtn) claimBtn.disabled = !registered;
      if (retryBtn) retryBtn.disabled = !registered;
      if (codeLocked) {{
        const codeShown = codeDisplay && !codeDisplay.hidden;
        codeLocked.hidden = !registered || !!codeShown;
      }}
      if (confirmChips && !registered) confirmChips.hidden = true;
      savePresaleSession({{ registered: presaleRegistered, ppid: lastPpid || null }});
    }}

    function setClearClaimVisible(visible) {{
      const clearClaimBtn = document.getElementById('clear-claim-btn');
      if (clearClaimBtn) clearClaimBtn.hidden = !visible;
    }}

    function showAlreadyClaimed(code, {{ ppid }} = {{}}) {{
      if (ppid) lastPpid = ppid;
      const notice = document.getElementById('already-claimed-notice');
      if (notice) notice.hidden = false;
      setClearClaimVisible(true);
      pill.textContent = 'ALREADY CLAIMED';
      pill.className = 'pill deny';
      const msg = formatDenyReason('allocation_already_claimed');
      decisionCopy.textContent = msg;
      decisionCard.innerHTML = '<strong>You already claimed your code</strong><p class="tiny">'
        + msg
        + ' Use Clear claim (demo reset) to release this PPID and run the flow again.</p>';
      if (code) showClaimSuccess(code);
      setStepState(true);
      if (WELCOME_MODE) {{
        setWelcomeStep('return');
        showWelcomePrivacy();
      }}
    }}

    function hideAlreadyClaimed() {{
      const notice = document.getElementById('already-claimed-notice');
      if (notice) notice.hidden = true;
    }}

    async function syncPresaleRegistrationStatus() {{
      if (!siteSessionPpid) return;
      try {{
        const res = await fetch('/api/presale/status', {{
          method: 'POST',
          credentials: 'include',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ drop_id: DROP_ID }}),
        }});
        if (!res.ok) return;
        const data = await res.json();
        if (data.registered) {{
          setStepState(true);
        }}
        if (data.allocated && data.code) {{
          showAlreadyClaimed(data.code, {{ ppid: data.ppid || siteSessionPpid }});
        }} else {{
          hideAlreadyClaimed();
          setClearClaimVisible(false);
        }}
      }} catch (err) {{}}
    }}

    function showClaimSuccess(code) {{
      const codeLocked = document.getElementById('code-locked');
      const confirmChips = document.getElementById('confirm-chips');
      if (codeLocked) codeLocked.hidden = true;
      if (confirmChips) confirmChips.hidden = false;
      if (codeDisplay) {{
        codeDisplay.hidden = false;
        codeDisplay.textContent = code;
      }}
    }}

    const restoredSession = loadPresaleSession();
    if (restoredSession?.registered) {{
      lastPpid = restoredSession.ppid || null;
      setStepState(true);
    }}
    if (restoredSession?.contact) {{
      const emailEl = document.getElementById('email');
      const phoneEl = document.getElementById('phone');
      if (emailEl && restoredSession.contact.email) emailEl.value = restoredSession.contact.email;
      if (phoneEl && restoredSession.contact.phone) phoneEl.value = restoredSession.contact.phone;
    }}

    function redactFreshPasskeyAttestation(stamped) {{
      const inner = (stamped && stamped.lemma) ? stamped.lemma : {{}};
      const att = inner.fresh_passkey_attestation;
      if (!att || typeof att !== 'object') return null;
      const commitment = String(att.action_commitment || '');
      return {{
        schema: att.schema || 'fresh_passkey_attestation.v1',
        site_id: att.site_id || SITE_ID,
        credential_id: att.credential_id || inner.credentialId || 'Not available',
        action_commitment_prefix: commitment ? commitment.slice(0, 16) + '…' : 'Not available',
        issued_at_unix: att.issued_at_unix,
        expires_at_unix: att.expires_at_unix,
      }};
    }}

    function renderCryptoEnvelope(stamped) {{
      if (stampJson) {{
        stampJson.textContent = stamped ? JSON.stringify(stamped, null, 2) : '{{}}';
      }}
      if (freshAttestationJson) {{
        const redacted = redactFreshPasskeyAttestation(stamped);
        freshAttestationJson.textContent = redacted
          ? JSON.stringify(redacted, null, 2)
          : '{{ "note": "fresh_passkey_attestation appears after Step 2 claim stamp" }}';
      }}
    }}

    function renderGateChips(serverEntry) {{
      if (!gateChipsEl) return;
      const passed = Array.isArray(serverEntry.gates_passed) ? serverEntry.gates_passed : [];
      const failed = serverEntry.gate_failed;
      if (!passed.length && !failed) {{
        gateChipsEl.innerHTML = '';
        return;
      }}
      const chips = passed.map((gate) =>
        '<span class="gate-chip">' + gate + '</span>'
      ).join('');
      const failChip = failed
        ? '<span class="gate-chip fail">gate_failed: ' + failed + '</span>'
        : '';
      gateChipsEl.innerHTML = chips + failChip;
    }}

    function renderReceipt(serverEntry, context) {{
      if (!serverReceipt || !serverReceiptFields || !serverEntry) {{
        if (serverReceipt) serverReceipt.hidden = true;
        if (receiptPlaceholder) receiptPlaceholder.hidden = false;
        return;
      }}
      serverReceipt.hidden = false;
      if (receiptPlaceholder) receiptPlaceholder.hidden = true;
      renderGateChips(serverEntry);
      const ctx = context || {{}};
      const stampInner = (ctx.stamped && ctx.stamped.lemma) ? ctx.stamped.lemma : {{}};
      const freshAttestation = stampInner.fresh_passkey_attestation;
      const freshGate = !!ctx.requireFreshPasskey;
      let freshStatus = 'not required';
      if (freshGate) {{
        freshStatus = freshAttestation ? 'verified' : 'missing';
      }}
      const nonceStatus = ctx.serverNonce ? 'consumed' : 'Not available';
      let registrationStatus = 'Not available';
      if (ctx.phase === 'register') {{
        registrationStatus = serverEntry.success ? 'stored' : 'denied';
      }} else if (ctx.phase === 'claim') {{
        registrationStatus = presaleRegistered ? 'yes' : 'required';
      }}
      const gateReason = serverEntry.reason || stampInner.reason || 'Not available';
      const rows = [
        ['Site binding', SITE_ID],
        ['Action', ctx.action || serverEntry.action || 'Not available'],
        ['Fresh passkey', freshStatus],
        ['Nonce consumed', nonceStatus],
        ['Registration', registrationStatus],
        ['Gate reason', gateReason],
        ['Drop', serverEntry.drop_id || DROP_ID],
        ['Code', serverEntry.code || serverEntry.existing_code || 'Not available'],
        ['PPID', serverEntry.ppid || 'Not available'],
        ['Assurance', serverEntry.assurance || serverEntry.required_assurance || 'Not available'],
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

    async function fetchPresaleChallenge(action, path, payload) {{
      const res = await fetch('/api/presale/challenge', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
          action,
          method: 'POST',
          path,
          body: payload,
        }}),
      }});
      const data = await res.json();
      if (!res.ok || !data.success) {{
        throw new Error(data.reason || data.error || 'challenge_failed');
      }}
      return data;
    }}

    function buildStampedFromRedirectSign(payload, signResult, claimAssurance) {{
      const assertion = signResult.action_assertion || {{}};
      const credential = signResult.credential || {{}};
      return {{
        ...payload,
        lemma: {{
          version: 1,
          verified: true,
          siteId: SITE_ID,
          ppid: credential.subject || null,
          credentialId: credential.id || null,
          assurance: claimAssurance || CLAIM_ASSURANCE,
          action: assertion.action,
          method: assertion.method,
          path: assertion.path,
          bodyHash: assertion.body_hash,
          nonce: assertion.nonce,
          issuedAtUnix: assertion.issued_at_unix,
          expiresAtUnix: assertion.expires_at_unix,
          credential,
          action_assertion: assertion,
          action_signature: signResult.action_signature,
          fresh_passkey_attestation: signResult.fresh_passkey_attestation || null,
        }},
      }};
    }}

    async function postPresaleStamp(path, stamped, serverNonce, context) {{
      const body = {{ ...stamped, server_nonce: serverNonce }};
      if (context.phase === 'claim' && context.claimAssurance) {{
        body.required_assurance = context.claimAssurance;
      }}
      const serverRes = await fetch(path, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(body),
      }});
      lastStampedRequest = {{ path, body, action: context.action }};
      const serverEntry = await serverRes.json();
      // The server nonce is consumed once posted; a stale challenge would
      // only produce action_nonce_reused on the next attempt.
      savePresaleSession({{ pendingChallenge: null }});
      await refreshActionLog();
      renderReceipt(serverEntry, context);
      return serverEntry;
    }}

    async function runRegister() {{
      if (typeof IsHumanVerifier === 'undefined') return;
      if (!(await ensureSiteSession())) return;
      savePresaleSession({{ pendingAction: 'register', contact: contactPayload() }});
      const registerBtn = document.getElementById('register-btn');
      registerBtn.disabled = true;
      pill.textContent = 'CHECKING';
      pill.className = 'pill checking';
      setTourHighlight('register');
      decisionCard.innerHTML = '<strong>Step 1, Passkey register</strong><p class="tiny">Action-bound passkey proof. Email and phone are delivery fields stored on this site, not your identity and not sent to lemma.id.</p>';
      try {{
        const payload = stampBody(contactPayload());
        const challenge = await fetchPresaleChallenge(REGISTER_ACTION, REGISTER_PATH, payload);
        savePresaleSession({{
          pendingAction: 'register',
          contact: payload,
          pendingChallenge: {{
            action: REGISTER_ACTION,
            path: REGISTER_PATH,
            server_nonce: challenge.server_nonce,
            payload,
          }},
        }});
        const verifier = makeVerifier('passkey');
        const stamped = await verifier.stampAction(payload, {{
          action: REGISTER_ACTION,
          method: 'POST',
          path: REGISTER_PATH,
          nonce: challenge.server_nonce,
          requiredAssurance: 'passkey',
          autoProvision: true,
        }});
        if (stampJson) stampJson.textContent = JSON.stringify(stamped, null, 2);
        renderCryptoEnvelope(stamped);
        const stampMeta = stamped.lemma || {{}};
        if (!stampMeta.verified) {{
          if (stampMeta.reason === 'redirect_started') {{
            pill.textContent = 'REDIRECT';
            pill.className = 'pill checking';
            decisionCopy.textContent = formatDenyReason('redirect_started');
            return;
          }}
          pill.textContent = 'DENY';
          pill.className = 'pill deny';
          decisionCopy.textContent = formatDenyReason(stampMeta.reason || 'not_verified');
          decisionCard.innerHTML = '<strong>Registration blocked</strong><p class="tiny">' + formatDenyReason(stampMeta.reason) + '</p>';
          return;
        }}
        const serverEntry = await postPresaleStamp(REGISTER_PATH, stamped, challenge.server_nonce, {{
          phase: 'register',
          action: REGISTER_ACTION,
          stamped,
          serverNonce: challenge.server_nonce,
          requireFreshPasskey: false,
        }});
        if (serverEntry.success) {{
          lastPpid = serverEntry.ppid || null;
          setStepState(true);
          savePresaleSession({{ pendingAction: null }});
          pill.textContent = 'REGISTERED';
          pill.className = 'pill ok';
          assurancePill.textContent = 'register: passkey';
          decisionCopy.textContent = 'Joined drop ' + (serverEntry.drop_id || DROP_ID) + '. Confirm and reveal your code next.';
          decisionCard.innerHTML = '<strong>{copy["success_register"]}</strong><p class="tiny">PPID '
            + (serverEntry.ppid || '').slice(0, 24) + '… registered. Next: confirm with verified-human assurance and a fresh passkey to reveal your unique code.</p>';
          advanceTour('register');
        }} else {{
          pill.textContent = 'DENY';
          pill.className = 'pill deny';
          decisionCopy.textContent = formatDenyReason(serverEntry.reason || 'denied');
          decisionCard.innerHTML = '<strong>Registration denied</strong><p class="tiny">' + formatDenyReason(serverEntry.reason) + '</p>';
        }}
      }} catch (err) {{
        pill.textContent = 'ERROR';
        pill.className = 'pill deny';
        decisionCopy.textContent = err.message;
        decisionCard.innerHTML = '<strong>Registration failed</strong><p class="tiny">' + err.message + '</p>';
      }} finally {{
        registerBtn.disabled = false;
      }}
    }}

    async function runClaim(assuranceOverride, depth, options) {{
      if (typeof IsHumanVerifier === 'undefined') return;
      if (!(await ensureSiteSession())) return;
      const opts = options || {{}};
      const isRetry = !!opts.isRetry;
      if (!opts.skipStepDemo) {{
        savePresaleSession({{
          pendingAction: isRetry ? 'retry' : 'claim',
          contact: contactPayload(),
        }});
      }}
      const retryDepth = depth || 0;
      if (retryDepth > 2) return;
        const claimAssurance = assuranceOverride || CLAIM_ASSURANCE;
        const claimBtn = document.getElementById('claim-btn');
        const retryBtn = document.getElementById('retry-btn');
        claimBtn.disabled = true;
        retryBtn.disabled = true;
        pill.textContent = 'CHECKING';
        pill.className = 'pill checking';
        setTourHighlight(isRetry ? 'retry' : 'claim');
        const idvNote = claimAssurance === ESCALATED_ASSURANCE
          ? 'Fresh IDV-backed proof required after site risk flag.'
          : 'Confirm with verified-human assurance and a fresh passkey — one account per person. Server verifies fresh_passkey_attestation bound to this action.';
        decisionCard.innerHTML = '<strong>Confirm and reveal code</strong><p class="tiny">' + idvNote + '</p>';
      try {{
        const verifier = makeVerifier(claimAssurance);
        const payload = stampBody(contactPayload());
        const saved = loadPresaleSession();
        let challenge = saved?.pendingChallenge;
        const challengeUsable = challenge?.server_nonce
          && challenge.action === CLAIM_ACTION
          && stampBodiesMatch(challenge.payload, payload);
        if (!challengeUsable) {{
          const issued = await fetchPresaleChallenge(CLAIM_ACTION, CLAIM_PATH, payload);
          challenge = {{
            action: CLAIM_ACTION,
            path: CLAIM_PATH,
            server_nonce: issued.server_nonce,
            payload,
          }};
        }} else {{
          challenge.payload = payload;
        }}
        savePresaleSession({{
          pendingAction: isRetry ? 'retry' : 'claim',
          contact: payload,
          claimAssurance,
          pendingChallenge: challenge,
        }});
        const stamped = await verifier.stampAction(payload, {{
          action: CLAIM_ACTION,
          method: 'POST',
          path: CLAIM_PATH,
          nonce: challenge.server_nonce,
          requiredAssurance: claimAssurance,
          requireFreshPasskey: true,
          serverNonce: challenge.server_nonce,
          autoProvision: true,
        }});
        if (stampJson) stampJson.textContent = JSON.stringify(stamped, null, 2);
        renderCryptoEnvelope(stamped);
        const stampMeta = stamped.lemma || {{}};
        if (!stampMeta.verified) {{
          if (stampMeta.reason === 'redirect_started') {{
            pill.textContent = 'REDIRECT';
            pill.className = 'pill checking';
            decisionCopy.textContent = formatDenyReason('redirect_started');
            return;
          }}
          pill.textContent = 'DENY';
          pill.className = 'pill deny';
          const reason = stampMeta.reason || 'not_verified';
          decisionCopy.textContent = formatDenyReason(reason);
          decisionCard.innerHTML = '<strong>Verification required</strong><p class="tiny">' + formatDenyReason(reason) + '</p>';
          if (codeDisplay) codeDisplay.hidden = true;
          return;
        }}
        const serverEntry = await postPresaleStamp(CLAIM_PATH, stamped, challenge.server_nonce, {{
          phase: 'claim',
          action: CLAIM_ACTION,
          claimAssurance,
          stamped,
          serverNonce: challenge.server_nonce,
          requireFreshPasskey: true,
        }});
        assurancePill.textContent = 'claim: ' + (serverEntry.assurance || claimAssurance);
        if (serverEntry.reason === 'doubt_required' && claimAssurance !== ESCALATED_ASSURANCE) {{
          pill.textContent = 'IDV REQUIRED';
          pill.className = 'pill checking';
          decisionCopy.textContent = 'Site risk flag, complete fresh IDV to unlock your code.';
          decisionCard.innerHTML = '<strong>Risk flag penalty</strong><p class="tiny">Site doubt requires fresh IDV via verifyFreshForBackend, then retry at ishuman assurance.</p>';
          const fresh = await verifier.verifyFreshForBackend({{
            requiredAssurance: ESCALATED_ASSURANCE,
            autoProvision: true,
          }});
          if (!fresh.ok) {{
            pill.textContent = 'DENY';
            pill.className = 'pill deny';
            decisionCopy.textContent = formatDenyReason(fresh.reason || 'not_verified');
            return;
          }}
          return runClaim(ESCALATED_ASSURANCE, retryDepth + 1, opts);
        }}
        if (serverEntry.success && serverEntry.code) {{
          savePresaleSession({{ pendingAction: null }});
          hideAlreadyClaimed();
          setClearClaimVisible(true);
          pill.textContent = 'CODE ISSUED';
          pill.className = 'pill ok';
          showClaimSuccess(serverEntry.code);
          decisionCopy.textContent = 'Code ' + serverEntry.code + ' bound to PPID ' + (serverEntry.ppid || '').slice(0, 24) + '…';
          decisionCard.innerHTML = '<strong>{copy["success"]}</strong><p class="tiny">One-person limit verified. Passkey confirmed just now. This site never saw your ID documents.</p>';
          showDeliveryPanel();
          if (WELCOME_MODE) {{
            setWelcomeStep('deny');
            decisionCopy.textContent = 'You got your code. Now try to grab a second one.';
          }}
          if (!isRetry) advanceTour('claim');
        }} else {{
          const reason = serverEntry.reason || 'denied';
          if (reason === 'allocation_already_claimed') {{
            showAlreadyClaimed(serverEntry.existing_code || serverEntry.code, {{
              ppid: serverEntry.ppid || lastPpid,
            }});
            if (WELCOME_MODE) {{
              setWelcomeStep('return');
              showWelcomePrivacy();
              decisionCard.innerHTML = '<strong>One per person</strong><p class="tiny">'
                + formatDenyReason(reason)
                + ' Close this tab and come back — you will still be you. Or use Clear claim (demo reset) to replay.</p>';
            }}
            if (isRetry) advanceTour('retry');
          }} else {{
            pill.textContent = 'DENY';
            pill.className = 'pill deny';
            decisionCopy.textContent = formatDenyReason(reason);
            decisionCard.innerHTML = '<strong>Claim denied</strong><p class="tiny">' + formatDenyReason(reason) + '</p>';
          }}
          if (opts.skipStepDemo && reason === 'registration_required') {{
            advanceTour('attack');
          }}
        }}
      }} catch (err) {{
        pill.textContent = 'ERROR';
        pill.className = 'pill deny';
        decisionCopy.textContent = err.message;
        decisionCard.innerHTML = '<strong>Claim failed</strong><p class="tiny">' + err.message + '</p>';
      }} finally {{
        claimBtn.disabled = !presaleRegistered;
        retryBtn.disabled = !presaleRegistered;
      }}
    }}

    async function simulateRiskFlag() {{
      if (!lastPpid) {{
        decisionCopy.textContent = 'Complete Step 1 first so we have a PPID to flag.';
        return;
      }}
      setTourHighlight('flag');
      await fetch('/api/demo/policy/doubt', {{
        method: 'POST',
        credentials: 'include',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ ppid: lastPpid }}),
      }});
      pill.textContent = 'FLAGGED';
      pill.className = 'pill checking';
      decisionCopy.textContent = 'Simulated site risk flag on ' + lastPpid.slice(0, 20) + '…, Step 2 will require fresh IDV.';
      advanceTour('flag');
    }}

    async function clearRiskFlag() {{
      if (!lastPpid) return;
      await fetch('/api/demo/policy/clear', {{
        method: 'POST',
        credentials: 'include',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ ppid: lastPpid }}),
      }});
      decisionCopy.textContent = 'Risk flag cleared for demo reset.';
    }}

    async function clearClaimReset() {{
      const ppid = lastPpid || siteSessionPpid;
      if (!ppid) {{
        decisionCopy.textContent = 'Sign in first so we know which PPID claim to clear.';
        return;
      }}
      try {{
        const res = await fetch('/api/demo/presale/clear-claim', {{
          method: 'POST',
          credentials: 'include',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ ppid, drop_id: DROP_ID }}),
        }});
        const data = await res.json();
        if (!res.ok || !data.success) {{
          throw new Error(data.reason || 'clear_claim_failed');
        }}
        hideAlreadyClaimed();
        setClearClaimVisible(false);
        if (codeDisplay) {{
          codeDisplay.hidden = true;
          codeDisplay.textContent = '--------';
        }}
        const confirmChips = document.getElementById('confirm-chips');
        if (confirmChips) confirmChips.hidden = true;
        const deliveryPanel = document.getElementById('delivery-panel');
        if (deliveryPanel) deliveryPanel.hidden = true;
        setStepState(presaleRegistered || !!siteSessionPpid);
        pill.textContent = data.cleared ? 'CLAIM CLEARED' : 'NO CLAIM';
        pill.className = 'pill ok';
        decisionCopy.textContent = data.cleared
          ? 'Demo reset: this PPID can claim a new code. Run Step 2 again.'
          : 'No existing claim for this PPID — you can claim now.';
        decisionCard.innerHTML = '<strong>Demo claim cleared</strong><p class="tiny">Allocation released for this site-private PPID. Registration is unchanged.</p>';
      }} catch (err) {{
        pill.textContent = 'ERROR';
        pill.className = 'pill deny';
        decisionCopy.textContent = 'Could not clear claim: ' + err.message;
      }}
    }}

    async function runReplayAttack() {{
      if (!lastStampedRequest) {{
        decisionCopy.textContent = 'Complete a register or claim action first to cache a stamped body.';
        return;
      }}
      setTourHighlight('attack');
      pill.textContent = 'CHECKING';
      pill.className = 'pill checking';
      decisionCard.innerHTML = '<strong>Replay attack</strong><p class="tiny">Re-posting the last stamped body and nonce, server should return action_nonce_reused.</p>';
      try {{
        const serverRes = await fetch(lastStampedRequest.path, {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(lastStampedRequest.body),
        }});
        const serverEntry = await serverRes.json();
        await refreshActionLog();
        renderReceipt(serverEntry, {{
          phase: lastStampedRequest.path === CLAIM_PATH ? 'claim' : 'register',
          action: lastStampedRequest.action,
          stamped: lastStampedRequest.body,
          serverNonce: lastStampedRequest.body.server_nonce,
          requireFreshPasskey: lastStampedRequest.path === CLAIM_PATH,
        }});
        const reason = serverEntry.reason || 'unknown';
        pill.textContent = serverEntry.success ? 'ACCEPT' : 'DENY';
        pill.className = 'pill ' + (serverEntry.success ? 'ok' : 'deny');
        decisionCopy.textContent = 'Replay result: ' + reason;
        decisionCard.innerHTML = '<strong>Replay ' + (serverEntry.success ? 'accepted' : 'denied') + '</strong><p class="tiny">'
          + formatDenyReason(reason) + '</p>';
        if (reason === 'action_nonce_reused') advanceTour('attack');
      }} catch (err) {{
        pill.textContent = 'ERROR';
        pill.className = 'pill deny';
        decisionCopy.textContent = err.message;
      }}
    }}

    async function runSkipStepAttack() {{
      if (presaleRegistered) {{
        decisionCopy.textContent = 'Already registered on server, reload without Step 1 to demo skip-step deny.';
        return;
      }}
      setTourHighlight('attack');
      decisionCard.innerHTML = '<strong>Skip Step 1</strong><p class="tiny">Attempting claim before passkey register, server should return registration_required.</p>';
      await runClaim(undefined, 0, {{ isRetry: false, skipStepDemo: true }});
    }}

    refreshSessionState();
    refreshActionLog();
    signInEl?.addEventListener('lemma-signin-success', (e) => {{
      completeLoginFromPresentation(e.detail.presentation);
    }});
    signInEl?.addEventListener('lemma-signin-error', (e) => {{
      pill.textContent = 'DENY';
      pill.className = 'pill deny';
      decisionCopy.textContent = formatDenyReason(e.detail.reason);
      setSignInDisabled(false);
    }});
    document.getElementById('register-btn')?.addEventListener('click', () => runRegister());
    document.getElementById('claim-btn')?.addEventListener('click', () => runClaim());
    document.getElementById('retry-btn')?.addEventListener('click', () => runClaim(undefined, 0, {{ isRetry: true }}));
    document.getElementById('flag-btn')?.addEventListener('click', () => simulateRiskFlag());
    document.getElementById('clear-flag-btn')?.addEventListener('click', () => clearRiskFlag());
    document.getElementById('clear-claim-btn')?.addEventListener('click', () => clearClaimReset());
    document.getElementById('replay-btn')?.addEventListener('click', () => runReplayAttack());
    document.getElementById('skip-step-btn')?.addEventListener('click', () => runSkipStepAttack());
    document.getElementById('save-delivery-btn')?.addEventListener('click', () => saveDelivery(false));
    document.getElementById('skip-delivery-btn')?.addEventListener('click', () => saveDelivery(true));
    logoutBtn?.addEventListener('click', async () => {{
      await fetch('/api/logout', {{ method: 'POST', credentials: 'include' }});
      try {{ sessionStorage.removeItem(PRESALE_SESSION_KEY); }} catch (e) {{}}
      window.location.reload();
    }});

    function stripLemmaReturnParams() {{
      try {{
        const cleaned = new URL(window.location.href);
        ['lemma_ishuman_return', 'request_nonce', 'redirect_kind'].forEach((k) => cleaned.searchParams.delete(k));
        window.history.replaceState(null, '', cleaned.toString());
      }} catch (e) {{}}
    }}

    async function resumeAfterLemmaRedirect() {{
      const params = new URLSearchParams(window.location.search);
      if (params.get('lemma_ishuman_return') !== '1') return;
      stripLemmaReturnParams();
      const saved = loadPresaleSession();
      const pending = saved?.pendingAction;
      if (!pending) {{
        decisionCopy.textContent = 'Returned from lemma.id, tap the presale step to continue.';
        return;
      }}
      decisionCard.innerHTML = '<strong>Resuming after passkey unlock</strong><p class="tiny">Finishing the presale step you started before returning from lemma.id.</p>';
      const redirectKind = (params.get('redirect_kind') || 'site_proof').trim().toLowerCase();
      if (redirectKind === 'action_sign' && saved?.pendingChallenge) {{
        const verifier = makeVerifier(saved.claimAssurance || CLAIM_ASSURANCE);
        const claimed = await verifier.claimRedirectActionSign();
        if (claimed?.ok && claimed.signResult) {{
          const stamped = buildStampedFromRedirectSign(
            stampBody(saved.pendingChallenge.payload || contactPayload()),
            claimed.signResult,
            saved.claimAssurance || CLAIM_ASSURANCE,
          );
          renderCryptoEnvelope(stamped);
          const path = saved.pendingChallenge.path || CLAIM_PATH;
          const serverEntry = await postPresaleStamp(path, stamped, saved.pendingChallenge.server_nonce, {{
            phase: pending === 'register' ? 'register' : 'claim',
            action: saved.pendingChallenge.action || CLAIM_ACTION,
            claimAssurance: saved.claimAssurance || CLAIM_ASSURANCE,
            stamped,
            serverNonce: saved.pendingChallenge.server_nonce,
            requireFreshPasskey: path === CLAIM_PATH,
          }});
          if (serverEntry.success && serverEntry.code) {{
            savePresaleSession({{ pendingAction: null, pendingChallenge: null }});
            hideAlreadyClaimed();
            setClearClaimVisible(true);
            pill.textContent = 'CODE ISSUED';
            pill.className = 'pill ok';
            showClaimSuccess(serverEntry.code);
            decisionCopy.textContent = 'Code ' + serverEntry.code + ' issued after redirect return.';
            setStepState(true);
            return;
          }}
          if (serverEntry.success && path === REGISTER_PATH) {{
            savePresaleSession({{ pendingAction: null, pendingChallenge: null }});
            setStepState(true);
            pill.textContent = 'REGISTERED';
            pill.className = 'pill ok';
            decisionCopy.textContent = 'Registered after redirect return.';
            return;
          }}
          if (serverEntry.reason === 'allocation_already_claimed') {{
            savePresaleSession({{ pendingAction: null, pendingChallenge: null }});
            showAlreadyClaimed(serverEntry.existing_code || serverEntry.code, {{
              ppid: serverEntry.ppid || lastPpid,
            }});
            return;
          }}
          savePresaleSession({{ pendingAction: null, pendingChallenge: null }});
          pill.textContent = 'DENY';
          pill.className = 'pill deny';
          decisionCopy.textContent = formatDenyReason(serverEntry.reason || 'denied');
          return;
        }}
      }}
      if (pending === 'claim') {{
        await runClaim();
      }} else if (pending === 'retry') {{
        await runClaim(undefined, 0, {{ isRetry: true }});
      }} else {{
        await runRegister();
      }}
    }}

    resumeAfterLemmaRedirect();
  </script>
</body>
</html>"""
    return Response(html, mimetype="text/html")
