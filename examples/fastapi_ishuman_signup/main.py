"""Sign in with lemma.id — FastAPI example with session cookies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "proof-verifier-py"))

from lemma_proof_verifier import VerificationContext  # noqa: E402

app = FastAPI()
SITE_ID = os.getenv("SITE_ID", "localhost")
REQUIRED = os.getenv("REQUIRED_ASSURANCE", "passkey")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-change-me")
SESSION_COOKIE = "lemma_example_session"
_CTX = VerificationContext(site_id=SITE_ID, required_assurance=REQUIRED)
_USERS: dict[str, dict[str, Any]] = {}


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


def _find_or_create_user(ppid: str) -> dict[str, Any]:
    user = _USERS.get(ppid)
    if user:
        return user
    user = {"ppid": ppid, "created_at": int(time.time())}
    _USERS[ppid] = user
    return user


def require_auth(session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> str:
    ppid = _read_session(session)
    if not ppid:
        raise HTTPException(status_code=401, detail="auth_required")
    return ppid


class LoginBody(BaseModel):
    presentation: dict[str, Any]


LOGIN_HTML = f"""<!doctype html>
<html><head><title>Sign in with lemma.id (FastAPI)</title></head><body>
<h1>Sign in with lemma.id</h1>
<p id="status">Loading…</p>
<button id="signin" type="button" style="display:none">Sign in with lemma.id</button>
<script src="https://lemma.id/sdk/proof-verifier.js"></script>
<script>
const SITE_ID = {json.dumps(SITE_ID)};
const REQUIRED = {json.dumps(REQUIRED)};
const statusEl = document.getElementById('status');
const btn = document.getElementById('signin');
async function refresh() {{
  const me = await fetch('/api/me', {{ credentials: 'include' }});
  if (me.ok) {{ statusEl.textContent = 'Signed in as ' + (await me.json()).ppid; btn.style.display='none'; return; }}
  statusEl.textContent = 'Not signed in'; btn.style.display='inline-block';
}}
btn.onclick = async () => {{
  btn.disabled = true;
  try {{
    const verifier = new ProofVerifier({{ siteId: SITE_ID }});
    const {{ ok, presentation, reason }} = await verifier.verifyForBackend({{ autoProvision: true, requiredAssurance: REQUIRED }});
    if (!ok) throw new Error(reason || 'not_verified');
    const resp = await fetch('/api/login', {{ method:'POST', credentials:'include', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{ presentation }}) }});
    if (!resp.ok) throw new Error('server_denied');
    await refresh();
  }} catch (e) {{ statusEl.textContent = e.message; btn.disabled = false; }}
}};
refresh();
</script>
<p><a href="/logout">Logout</a></p>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return LOGIN_HTML


@app.get("/api/me")
def me(ppid: str = Depends(require_auth)):
    return {"success": True, "ppid": ppid}


@app.post("/api/login")
def login(body: LoginBody, response: Response):
    result = _CTX.verify(body.presentation)
    if not result.ok:
        raise HTTPException(status_code=401, detail=result.reason)
    _find_or_create_user(result.ppid)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=_sign_session(result.ppid),
        httponly=True,
        samesite="lax",
        max_age=86400,
    )
    return {"success": True, "ppid": result.ppid, "assurance": result.assurance}


@app.get("/logout")
def logout():
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie(SESSION_COOKIE)
    return resp
