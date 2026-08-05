import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from collections import deque
from typing import Any, Optional

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

SITE_ID = os.getenv("LEMMA_DEMO_SITE_ID", "tickets-demo.lemma.id")
SITE_NAME = os.getenv("LEMMA_DEMO_SITE_NAME", "Lemma Demo Site")
SITE_KIND = os.getenv("LEMMA_DEMO_SITE_KIND", "ticketing")
LEMMA_ORIGIN = os.getenv("LEMMA_ORIGIN", "https://lemma.id")
DEMO_HUB_URL = os.getenv("LEMMA_DEMO_HUB_URL", f"{LEMMA_ORIGIN}/demo")
TRIALS_DEMO_URL = os.getenv("LEMMA_DEMO_TRIALS_URL", "https://trials-demo.lemma.id")

_PLAIN_LANGUAGE_JS = """
function formatDenyReason(reason) {
  if (window.LemmaDemoPlain && typeof window.LemmaDemoPlain.reason === 'function') {
    return window.LemmaDemoPlain.reason(reason);
  }
  return String(reason || 'Something went wrong — try again.');
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
TRIAL_REQUIRED_ASSURANCE = os.getenv(
    "LEMMA_TRIAL_REQUIRED_ASSURANCE", "ishuman"
).strip().lower()
ISHUMAN_VERIFIER_SDK_VERSION = os.getenv("ISHUMAN_VERIFIER_SDK_VERSION", "1.9.3").strip()
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


def _site_header(links_html: str) -> str:
    theme = _site_theme()
    return f"""  <header>
    <div class="site-brand">
      <span class="site-icon">{theme["icon_svg"]}</span>
      <strong>{SITE_NAME}</strong>
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
            "eyebrow": "Sign in with lemma.id",
            "headline": "Passwordless login for your app",
            "subhead": "Sign in with a passkey-backed lemma.id. Your backend verifies a signed presentation and stores a site-private account ID — no passwords or emails required for login.",
            "primary": "Start free trial",
            "trial_eyebrow": "Trial access",
            "trial_subhead": "Starting a trial requires verified human proof — one account per person. Sign in with a passkey first, then step up when you claim access.",
            "success": "Trial workspace created",
            "form": "Work email (optional profile field)",
            "placeholder": "founder@example.com",
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
        "subhead": "Join the drop with a passkey register — no email or password. Unlock your one-time code with verified human proof at claim time. Contact info is optional delivery after you claim. No SMS OTP.",
        "register": "Step 1, Passkey register for drop",
        "claim": "Step 2, Verified human unlocks unique code",
        "retry": "Try again with same lemma.id",
        "flag": "Simulate site risk flag",
        "clear_flag": "Clear risk flag",
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
        f'  <script src="{LEMMA_ORIGIN}/static/js/demo/plain-language.js?v=1" '
        f'crossorigin="anonymous"></script>'
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
    trial_gated_block = ""
    if is_trial:
        trial_gated_block = f"""
        <div class="gated-section" id="trial-gated" hidden>
          <p class="eyebrow">{copy["trial_eyebrow"]}</p>
          <p class="muted" style="font-size:14px;margin-bottom:8px;">{copy["trial_subhead"]}</p>
          <label for="email">{copy["form"]}</label>
          <input id="email" value="{copy["placeholder"]}" aria-label="{copy["form"]}">
          <button id="verify-btn" class="site-cta" disabled>{copy["primary"]}</button>
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
  <title>{SITE_NAME}</title>
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
    @media (max-width: 820px) {{ .layout {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  {_site_header(f'<a href="{DEMO_HUB_URL}?from=demo" target="_blank" rel="noopener">Return to demo hub</a>')}
  <main>
    <div class="layout">
      <section class="card">
        <p class="eyebrow">{copy["eyebrow"]}</p>
        <h1>{copy["headline"]}</h1>
        <p class="muted">{copy["subhead"]}</p>
        {_lemma_signin_element()}
        <p class="muted" id="session-copy" style="margin-top:12px;font-size:13px;">Sign in once with a passkey. This site keeps a session until a fresh passkey is required.</p>
        {trial_gated_block}
        <div class="verdict" id="decision-card">
          <strong>What happens when you click</strong>
          <p class="tiny">Passkey unlock + continuity proof for sign-in (<code>assurance: passkey</code>). {"Trial access requires a separate verified human step-up (<code>assurance: ishuman</code>)." if is_trial else "Protected actions reuse the site session until policy requires fresh passkey."}</p>
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
          <li>Sign in with lemma.id once — passkey assurance, server sets a session cookie.</li>
          <li>{"Start trial requires verified human proof — same PPID, higher assurance tier." if is_trial else "Protected actions reuse the site session until policy requires fresh passkey."}</li>
          <li>Site policy may require human proof assurance → IDV step-up, same PPID.</li>
          <li>Server verifies locally with offline revocation checks.</li>
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
        <p class="hub-return">Continue the walkthrough on the <a href="{DEMO_HUB_URL}?from=demo" target="_blank" rel="noopener">lemma.id demo hub</a>, stages 3–5 cover presentations, escalation, and doubt/revocation.</p>
      </aside>
    </div>
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
    const SITE_POLICY = '{DEMO_REQUIRED_ASSURANCE}';
    const TRIAL_ASSURANCE = '{TRIAL_REQUIRED_ASSURANCE}';
    const IS_TRIAL_SITE = {'true' if is_trial else 'false'};
    let sharedVerifier = null;
    let siteSessionPpid = null;

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
          pill.textContent = 'SIGNED IN';
          pill.className = 'pill ok';
          setAssurancePill(data.assurance || SITE_POLICY);
          return true;
        }}
      }} catch (err) {{}}
      siteSessionPpid = null;
      if (sessionCopy) sessionCopy.textContent = 'Sign in once with a passkey. This site keeps a session until a fresh passkey is required.';
      if (actionBtn) actionBtn.disabled = true;
      setSignInDisabled(false);
      updateGatedVisibility(false);
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
          const verifier = makeVerifier(true, TRIAL_ASSURANCE);
          const fresh = await verifier.verifyFreshForBackend({{
            requiredAssurance: TRIAL_ASSURANCE,
            autoProvision: true,
          }});
          if (!fresh.ok) {{
            const response = {{
              human: false,
              assurance: fresh.assurance || null,
              reason: fresh.reason || 'not_verified',
              timeMs: fresh.timeMs || 0,
              ppid: fresh.ppid || siteSessionPpid,
            }};
            applyVerdict(response, {{ requestPayload }});
            return;
          }}
          requestPayload = {{
            ...requestPayload,
            presentation: fresh.presentation,
          }};
        }}
        const serverRes = await fetch('/api/demo/action', {{
          method: 'POST',
          credentials: 'include',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(requestPayload),
        }});
        serverEntry = await serverRes.json();
        const response = {{
          human: !!serverEntry.success,
          assurance: serverEntry.assurance || (IS_TRIAL_SITE ? TRIAL_ASSURANCE : SITE_POLICY),
          reason: serverEntry.reason,
          timeMs: 0,
          ppid: serverEntry.ppid || siteSessionPpid,
        }};
        await refreshActionLog();
        applyVerdict(response, {{ requestPayload, serverEntry }});
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

    if (new URLSearchParams(window.location.search).get('lemma_ishuman_return') === '1') {{
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
  <title>{SITE_NAME}</title>
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
  {_site_header(f'<a href="{DEMO_HUB_URL}?from=demo" target="_blank" rel="noopener">Return to demo hub</a>')}
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
        "eyebrow": "Try Sign in with lemma.id",
        "headline": "Sign in with a passkey — no email, no password",
        "subhead": "Follow the steps below. Each one shows something different about signing in with lemma.id.",
    })
    return base


def _ticketing_welcome_index():
    return _presale_index(welcome_mode=True)


def _presale_index(welcome_mode=False):
    copy = _welcome_content() if welcome_mode else _presale_content()
    body_class = "welcome-mode tour-mode" if welcome_mode else ""
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
            <li>Verified human proof at claim (Step 2).</li>
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
            <tr><td>Claim presence</td><td>SMS OTP or none</td><td>Verified human proof at unlock</td></tr>
            <tr><td>Contact data</td><td>Auth + CRM</td><td>Site-local delivery only</td></tr>
          </tbody>
        </table>
        <details>
          <summary>Action log</summary>
          <pre id="action-log">[]</pre>
        </details>
      </aside>"""
    welcome_contrast = """
    <section class="card welcome-contrast" id="welcome-contrast">
      <p class="eyebrow">What signing up usually feels like</p>
      <h2 style="margin:0 0 10px;font-size:22px;">Email, password, verify your inbox…</h2>
      <p class="muted" style="font-size:14px;margin-bottom:14px;">This is a mock — it does not submit anything. Typical signup takes minutes and creates data to breach.</p>
      <label>Email<input disabled value="you@example.com" style="opacity:0.7"></label>
      <label>Password<input disabled type="password" value="••••••••" style="opacity:0.7"></label>
      <button type="button" disabled style="opacity:0.5">Create account</button>
      <button type="button" class="btn-secondary" id="welcome-contrast-next" style="margin-top:12px">Now try the lemma.id way →</button>
    </section>""" if welcome_mode else ""
    welcome_progress = """
    <div class="welcome-progress" id="welcome-progress">
      <span class="welcome-step is-active" data-welcome-step="contrast">1 · Contrast</span>
      <span class="welcome-step" data-welcome-step="signin">2 · Sign in</span>
      <span class="welcome-step" data-welcome-step="claim">3 · Claim code</span>
      <span class="welcome-step" data-welcome-step="deny">4 · One per person</span>
      <span class="welcome-step" data-welcome-step="return">5 · Come back</span>
    </div>""" if welcome_mode else ""
    privacy_cta = f"""
    <section class="card welcome-privacy" id="welcome-privacy" hidden>
      <p class="eyebrow">Privacy reveal</p>
      <h2 style="margin:0 0 8px;font-size:22px;">Now try the other site</h2>
      <p class="muted" style="font-size:14px;">Sign in on the trials demo with the same lemma.id. Each site gets a different private ID — they cannot compare notes about you.</p>
      <a class="presale-link" href="{TRIALS_DEMO_URL}/?from=welcome" target="_blank" rel="noopener">Open trials demo site →</a>
      <a class="presale-link" href="{DEMO_HUB_URL}?lane=builder&from=welcome" style="margin-left:12px;">See what the backend saw →</a>
    </section>""" if welcome_mode else ""
    welcome_status = """
        <p style="margin:12px 0 6px"><span class="pill" id="status-pill">WAITING</span>
          <span class="pill" id="assurance-pill">Ready</span></p>
        <p class="muted" id="decision-copy">Sign in to start.</p>""" if welcome_mode else ""
    welcome_engineer_stubs = """
        <div hidden aria-hidden="true">
          <pre id="stamp-json">{{}}</pre>
          <pre id="fresh-attestation-json">{{}}</pre>
          <pre id="action-log">[]</pre>
          <div id="server-receipt"></div>
          <dl id="server-receipt-fields"></dl>
          <div id="gate-chips"></div>
          <p id="receipt-placeholder"></p>
          <input type="checkbox" id="backend-gates-toggle" hidden>
        </div>""" if welcome_mode else ""
    header_links = f"""
    <a href="{DEMO_HUB_URL}?from=welcome" target="_blank" rel="noopener">Demo hub</a>
    <a href="/?tour=presale" style="margin-left:12px;">Builder presale tour →</a>""" if welcome_mode else f"""
    <a href="{DEMO_HUB_URL}?from=demo" target="_blank" rel="noopener">Return to demo hub</a>
    <a href="/" style="margin-left:12px;">← Sign-in demo</a>"""
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{SITE_NAME}</title>
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
      padding: 14px 24px;
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
      max-width: 640px;
      margin: 0 auto;
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
    body.welcome-mode #clear-flag-btn {{
      display: none;
    }}
    .attack-lab-buttons {{
      display: grid;
      gap: 8px;
      margin-top: 10px;
    }}
    {SITE_CTA_CSS}
    {LEMMA_SIGNIN_CSS}
    @media (max-width: 820px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .defense-strip {{ grid-template-columns: 1fr 1fr; }}
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
        <li data-tour-step="claim" id="tour-step-claim">Unlock code — verified human proof at claim time</li>
        <li data-tour-step="retry" id="tour-step-retry">Retry with the same lemma.id, denied, one code per fan</li>
        <li data-tour-step="flag" id="tour-step-flag">Simulate risk flag, IDV penalty, then code at isHuman</li>
        <li data-tour-step="attack" id="tour-step-attack">Attack lab, replay stamp or skip Step 1</li>
      </ol>
      <p class="tour-impact" id="tour-impact">Sign in with a passkey first. Register for the drop, then unlock your code with verified human proof.</p>
    </div>
    <div class="{layout_class}">
      <section class="card">
        <p class="eyebrow">{copy["eyebrow"]}</p>
        <h1>{copy["headline"]}</h1>
        <p class="muted">{copy["subhead"]}</p>
        {_lemma_signin_element()}
        <p class="contact-note" id="session-copy">Sign in once with a passkey. Presale steps unlock after you have a site session.</p>
        <div class="gated-section" id="presale-gated" hidden>
        <div class="defense-strip" id="defense-strip">
          <div class="defense-item">Site PPID<small>passkey proof</small></div>
          <div class="defense-item">Action stamp<small>bound mutation</small></div>
          <div class="defense-item">Server nonce<small>replay block</small></div>
          <div class="defense-item">Human proof<small>claim ceremony</small></div>
          <div class="defense-item">1 code / fan<small>PPID ledger</small></div>
        </div>
        <div class="steps">
          <div class="step active" id="step-register">1 · Passkey register</div>
          <div class="step" id="step-claim">2 · Verified human claim</div>
        </div>
        <p class="muted" style="margin-top:12px;font-size:13px;">Drop: <code id="drop-id">{PRESALE_DROP_ID}</code></p>
        <button id="register-btn" disabled>{copy["register"]}</button>
        <button type="button" class="btn-secondary site-cta" id="claim-btn" disabled>{copy["claim"]}</button>
        <button type="button" class="btn-secondary" id="retry-btn" disabled>{copy["retry"]}</button>
        <button type="button" class="btn-secondary btn-ghost" id="flag-btn">{copy["flag"]}</button>
        <button type="button" class="btn-secondary btn-ghost" id="clear-flag-btn">{copy["clear_flag"]}</button>
        {welcome_status}
        {welcome_engineer_stubs}
        <details class="attack-lab" id="attack-lab">
          <summary>Attack lab</summary>
          <div class="attack-lab-buttons">
            <button type="button" class="btn-secondary btn-ghost" id="replay-btn">Replay last stamp</button>
            <button type="button" class="btn-secondary btn-ghost" id="skip-step-btn">Skip Step 1 (claim without register)</button>
          </div>
        </details>
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
        <div class="verdict" id="decision-card">
          <strong>Protected presale flow</strong>
          <p class="tiny">Step 1: passkey register binds your site-private ID. Step 2: verified human proof unlocks your unique code — one account per person. Contact info is optional delivery after you claim.</p>
        </div>
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
      claim: 'Verified human proof at unlock — one account per person, bots cannot replay cached sessions for codes.',
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
      setWelcomeStep('contrast');
      document.getElementById('welcome-contrast-next')?.addEventListener('click', () => {{
        document.getElementById('welcome-contrast')?.classList.add('is-dismissed');
        setWelcomeStep('signin');
        decisionCopy.textContent = 'Tap Sign in with lemma.id — no form, no email.';
      }});
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
      if (claimBtn) claimBtn.disabled = !registered;
      if (retryBtn) retryBtn.disabled = !registered;
      savePresaleSession({{ registered: presaleRegistered, ppid: lastPpid || null }});
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
          decisionCopy.textContent = 'Joined drop ' + (serverEntry.drop_id || DROP_ID) + '. Use Step 2 for verified human code unlock.';
          decisionCard.innerHTML = '<strong>{copy["success_register"]}</strong><p class="tiny">PPID '
            + (serverEntry.ppid || '').slice(0, 24) + '… registered. Step 2 requires verified human proof to issue your unique code.</p>';
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
          : 'Verified human proof required at unlock — one account per person. Server verifies fresh_passkey_attestation bound to this action.';
        decisionCard.innerHTML = '<strong>Step 2, Verified human unlock</strong><p class="tiny">' + idvNote + '</p>';
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
          pill.textContent = 'CODE ISSUED';
          pill.className = 'pill ok';
          if (codeDisplay) {{
            codeDisplay.hidden = false;
            codeDisplay.textContent = serverEntry.code;
          }}
          decisionCopy.textContent = 'Code ' + serverEntry.code + ' bound to PPID ' + (serverEntry.ppid || '').slice(0, 24) + '…';
          decisionCard.innerHTML = '<strong>{copy["success"]}</strong><p class="tiny">One code per person for this drop. This site never saw your ID documents.</p>';
          showDeliveryPanel();
          if (WELCOME_MODE) {{
            setWelcomeStep('deny');
            decisionCopy.textContent = 'You got your code. Now try to grab a second one.';
          }}
          if (!isRetry) advanceTour('claim');
        }} else {{
          pill.textContent = 'DENY';
          pill.className = 'pill deny';
          const reason = serverEntry.reason || 'denied';
          decisionCopy.textContent = formatDenyReason(reason);
          decisionCard.innerHTML = '<strong>Claim denied</strong><p class="tiny">' + formatDenyReason(reason) + '</p>';
          if (codeDisplay && serverEntry.existing_code) {{
            codeDisplay.hidden = false;
            codeDisplay.textContent = serverEntry.existing_code;
          }}
          if (isRetry && reason === 'allocation_already_claimed') {{
            if (WELCOME_MODE) {{
              setWelcomeStep('return');
              showWelcomePrivacy();
              decisionCard.innerHTML = '<strong>One per person</strong><p class="tiny">' + formatDenyReason(reason) + ' Close this tab and come back — you will still be you.</p>';
            }}
            advanceTour('retry');
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
    document.getElementById('replay-btn')?.addEventListener('click', () => runReplayAttack());
    document.getElementById('skip-step-btn')?.addEventListener('click', () => runSkipStepAttack());
    document.getElementById('save-delivery-btn')?.addEventListener('click', () => saveDelivery(false));
    document.getElementById('skip-delivery-btn')?.addEventListener('click', () => saveDelivery(true));

    async function resumeAfterLemmaRedirect() {{
      const params = new URLSearchParams(window.location.search);
      if (params.get('lemma_ishuman_return') !== '1') return;
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
            pill.textContent = 'CODE ISSUED';
            pill.className = 'pill ok';
            if (codeDisplay) {{
              codeDisplay.hidden = false;
              codeDisplay.textContent = serverEntry.code;
            }}
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
