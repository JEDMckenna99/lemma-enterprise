"""Verify a lemma proof — Flask example with optional session cookies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

from flask import Flask, g, jsonify, make_response, redirect, render_template_string, request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "proof-verifier-py"))

from lemma_proof_verifier import VerificationContext  # noqa: E402

app = Flask(__name__)
SITE_ID = os.getenv("SITE_ID", "localhost")
REQUIRED = os.getenv("REQUIRED_ASSURANCE", "passkey")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-change-me")
SESSION_COOKIE = "lemma_example_session"
_CTX = VerificationContext(site_id=SITE_ID, required_assurance=REQUIRED)
_USERS: dict[str, dict] = {}
# Demo store for "existing password account" → verified lemma PPID links.
_LOCAL_LINKS: dict[str, str] = {}


def _sign_session(ppid: str) -> str:
    payload = {"ppid": ppid, "exp": int(time.time()) + 86400}
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    sig = hmac.new(SESSION_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def _read_session(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    raw, sig = token.rsplit(".", 1)
    expected = hmac.new(SESSION_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw.encode()).decode())
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("exp") or 0) < int(time.time()):
        return None
    ppid = payload.get("ppid")
    return str(ppid) if ppid else None


def _find_or_create_user(ppid: str) -> dict:
    user = _USERS.get(ppid)
    if user:
        return user
    user = {"ppid": ppid, "created_at": int(time.time())}
    _USERS[ppid] = user
    return user


@app.before_request
def load_session():
    g.ppid = _read_session(request.cookies.get(SESSION_COOKIE))


def require_auth():
    if not getattr(g, "ppid", None):
        return jsonify({"success": False, "error": "auth_required"}), 401
    return None


LOGIN_PAGE = """
<!doctype html>
<html>
<head><title>Verify a lemma proof (Flask)</title></head>
<body>
  <h1>Verify a lemma proof</h1>
  <p id="status">Loading…</p>
  <button id="signin" type="button" style="display:none">Sign in with lemma.id</button>
  <div id="link-panel" style="display:none; margin-top:1rem">
    <p>Already have a local password account? Link lemma.id while signed in:</p>
    <label>Local user id <input id="local-user-id" value="user_42" /></label>
    <button id="link" type="button">Link lemma.id to this account</button>
    <p id="link-status"></p>
  </div>
  <script src="https://lemma.id/sdk/proof-verifier.js"></script>
  <script src="https://lemma.id/sdk/lemma-signin.js"></script>
  <script>
    const SITE_ID = {{ site_id|tojson }};
    const statusEl = document.getElementById('status');
    const btn = document.getElementById('signin');
    const linkPanel = document.getElementById('link-panel');
    const linkBtn = document.getElementById('link');
    const linkStatus = document.getElementById('link-status');
    async function refresh() {
      const me = await fetch('/api/me', { credentials: 'include' });
      if (me.ok) {
        const data = await me.json();
        statusEl.textContent = 'Signed in as ' + data.ppid;
        btn.style.display = 'none';
        linkPanel.style.display = 'block';
        return;
      }
      statusEl.textContent = 'Not signed in';
      btn.style.display = 'inline-block';
      linkPanel.style.display = 'none';
    }
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      try {
        const verifier = new ProofVerifier({ siteId: SITE_ID });
        const { ok, presentation, reason } = await verifier.verifyForBackend({
          autoProvision: true,
          requiredAssurance: {{ required|tojson }},
        });
        if (!ok) throw new Error(reason || 'not_verified');
        const resp = await fetch('/api/login', {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ presentation }),
        });
        if (!resp.ok) throw new Error('server_denied');
        await refresh();
      } catch (err) {
        statusEl.textContent = err.message || String(err);
        btn.disabled = false;
      }
    });
    // Account linking: verify a presentation while already authenticated, then
    // attach the verified PPID to an existing local user id.
    linkBtn.addEventListener('click', async () => {
      linkBtn.disabled = true;
      linkStatus.textContent = 'Verifying…';
      try {
        const verifier = new ProofVerifier({ siteId: SITE_ID });
        const { ok, presentation, reason } = await verifier.verifyForBackend({
          autoProvision: true,
          requiredAssurance: 'passkey',
        });
        if (!ok) throw new Error(reason || 'not_verified');
        const localUserId = document.getElementById('local-user-id').value;
        const resp = await fetch('/api/link-lemma', {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ presentation, local_user_id: localUserId }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.reason || 'link_failed');
        linkStatus.textContent = 'Linked local user ' + data.local_user_id + ' → ' + data.ppid;
      } catch (err) {
        linkStatus.textContent = err.message || String(err);
      } finally {
        linkBtn.disabled = false;
      }
    });
    refresh();
  </script>
  <p><a href="/logout">Logout</a></p>
</body>
</html>
"""


@app.get("/")
def index():
    return render_template_string(
        LOGIN_PAGE,
        site_id=SITE_ID,
        required=REQUIRED,
    )


@app.get("/api/me")
def me():
    denied = require_auth()
    if denied:
        return denied
    return jsonify({"success": True, "ppid": g.ppid})


@app.post("/api/login")
def login():
    body = request.get_json(silent=True) or {}
    presentation = body.get("presentation")
    if not presentation:
        return jsonify({"success": False, "reason": "presentation_missing"}), 400

    result = _CTX.verify(presentation)
    if not result.ok:
        return jsonify({"success": False, "reason": result.reason}), 401

    _find_or_create_user(result.ppid)
    resp = make_response(jsonify({"success": True, "ppid": result.ppid, "assurance": result.assurance}))
    resp.set_cookie(
        SESSION_COOKIE,
        _sign_session(result.ppid),
        httponly=True,
        samesite="Lax",
        secure=request.is_secure,
        max_age=86400,
    )
    return resp


@app.post("/api/link-lemma")
def link_lemma():
    """Link a verified lemma PPID to an existing local account (session required)."""
    denied = require_auth()
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    presentation = body.get("presentation")
    local_user_id = (body.get("local_user_id") or "").strip()
    if not presentation:
        return jsonify({"success": False, "reason": "presentation_missing"}), 400
    if not local_user_id:
        return jsonify({"success": False, "reason": "local_user_id_missing"}), 400

    result = _CTX.verify(presentation)
    if not result.ok:
        return jsonify({"success": False, "reason": result.reason}), 401

    # Never link on a bare client ppid — only the verified result.
    _LOCAL_LINKS[local_user_id] = result.ppid
    _find_or_create_user(result.ppid)
    return jsonify({
        "success": True,
        "local_user_id": local_user_id,
        "ppid": result.ppid,
        "assurance": result.assurance,
    })


@app.post("/logout")
@app.get("/logout")
def logout():
    resp = redirect("/")
    resp.delete_cookie(SESSION_COOKIE)
    return resp


if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", "5050")), host="0.0.0.0")
