"""Tests for the backend SDK `verifyStamp` / `verify_stamp` convenience.

The Python helper is exercised behaviorally (unwrap shapes + the tamper-binding
checks) by stubbing the underlying signature-verifying `verify`. The Node SDK is
pinned with source-pattern assertions (consistent with the other SDK tests), and
the served version headers + docs are checked for lockstep.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PY_SDK_PATH = ROOT / "examples" / "proof-verifier.py"
MJS_PATH = ROOT / "static" / "js" / "proof-verifier.mjs"
APP_PATH = ROOT / "app.py"
DOCS_PATH = ROOT / "templates" / "docs" / "ishuman.html"


def _load_py_sdk():
    pytest.importorskip("cryptography")
    if "proof_verifier" in sys.modules:
        return sys.modules["proof_verifier"]
    spec = importlib.util.spec_from_file_location("proof_verifier", PY_SDK_PATH)
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so dataclasses with `from __future__ import
    # annotations` (string annotations) can resolve cls.__module__.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# _unwrap_stamp: all accepted shapes
# ---------------------------------------------------------------------------

def _vc(cid="c1", subject="did:lemma:ppid_a"):
    """A minimal object that satisfies _looks_like_vc (subject+claims+proof)."""
    return {
        "id": cid,
        "subject": subject,
        "claims": {"isHuman": True},
        "proof": {"signatureValueWeb": "sig"},
    }


def test_unwrap_raw_presentation():
    mod = _load_py_sdk()
    presentation = {"credential": {"id": "c1"}}
    stamp, pres = mod._unwrap_stamp(presentation)
    assert stamp is None
    assert pres["credential"] == {"id": "c1"}


def test_unwrap_bare_vc():
    mod = _load_py_sdk()
    vc = _vc()
    stamp, pres = mod._unwrap_stamp(vc)
    assert stamp is None
    assert pres == {"credential": vc}


def test_unwrap_vc_only_stamp_preserves_tamper_binding():
    mod = _load_py_sdk()
    vc = _vc()
    stamp_obj = {"ppid": "did:lemma:ppid_a", "verified": True, "credential": vc}
    stamp, pres = mod._unwrap_stamp(stamp_obj)
    # Flat fields present -> returned as the stamp for cross-checking.
    assert stamp is stamp_obj
    assert pres["credential"] == vc
    assert pres["session_assertion"] is None


def test_unwrap_stamped_event_with_bare_vc():
    mod = _load_py_sdk()
    vc = _vc()
    inner = {"ppid": "did:lemma:ppid_a", "credential": vc}
    event = {"action": "checkout", "lemma": inner}
    stamp, pres = mod._unwrap_stamp(event)
    assert stamp is inner
    assert pres["credential"] == vc


def test_unwrap_stamp_object_with_proof():
    mod = _load_py_sdk()
    proof = {"credential": {"id": "c1"}}
    stamp = {"ppid": "did:lemma:ppid_a", "proof": proof}
    assert mod._unwrap_stamp(stamp) == (stamp, proof)


def test_unwrap_stamped_event_default_key():
    mod = _load_py_sdk()
    proof = {"credential": {"id": "c1"}}
    inner = {"ppid": "did:lemma:ppid_a", "proof": proof}
    event = {"action": "checkout", "lemma": inner}
    assert mod._unwrap_stamp(event) == (inner, proof)


def test_unwrap_stamped_event_custom_key():
    mod = _load_py_sdk()
    proof = {"credential": {"id": "c1"}}
    inner = {"ppid": "did:lemma:ppid_a", "proof": proof}
    event = {"verifiedBy": inner}
    assert mod._unwrap_stamp(event, key="verifiedBy") == (inner, proof)


def test_unwrap_rejects_junk():
    mod = _load_py_sdk()
    assert mod._unwrap_stamp(None) is None
    assert mod._unwrap_stamp({"action": "noop"}) is None
    assert mod._unwrap_stamp("nope") is None


# ---------------------------------------------------------------------------
# verify_stamp: wrapper behavior with verify() stubbed
# ---------------------------------------------------------------------------

def _ctx(mod):
    return mod.VerificationContext(site_id="your-site-id")


def test_verify_stamp_missing_proof():
    mod = _load_py_sdk()
    ctx = _ctx(mod)
    assert ctx.verify_stamp({"action": "noop"}).reason == "stamp_missing_proof"


def test_verify_stamp_passes_through_verify_failure(monkeypatch):
    mod = _load_py_sdk()
    ctx = _ctx(mod)
    monkeypatch.setattr(ctx, "verify", lambda presentation: mod.VerificationContext.Result(False, "revoked"))
    res = ctx.verify_stamp({"lemma": {"ppid": "x", "proof": {"credential": {"id": "c1"}}}})
    assert res.ok is False
    assert res.reason == "revoked"


def test_verify_stamp_detects_ppid_tamper(monkeypatch):
    mod = _load_py_sdk()
    ctx = _ctx(mod)
    monkeypatch.setattr(
        ctx, "verify",
        lambda presentation: mod.VerificationContext.Result(
            True, "valid", ppid="did:lemma:ppid_REAL", credential_id="c1",
        ),
    )
    stamp = {"lemma": {"ppid": "did:lemma:ppid_FAKE", "proof": {"credential": {"id": "c1"}}}}
    res = ctx.verify_stamp(stamp)
    assert res.ok is False
    assert res.reason == "stamp_ppid_mismatch"
    assert res.ppid == "did:lemma:ppid_REAL"


def test_verify_stamp_detects_credential_tamper(monkeypatch):
    mod = _load_py_sdk()
    ctx = _ctx(mod)
    monkeypatch.setattr(
        ctx, "verify",
        lambda presentation: mod.VerificationContext.Result(
            True, "valid", ppid="did:lemma:ppid_a", credential_id="c_REAL",
        ),
    )
    stamp = {"lemma": {"ppid": "did:lemma:ppid_a", "credentialId": "c_FAKE",
                       "proof": {"credential": {"id": "c_REAL"}}}}
    res = ctx.verify_stamp(stamp)
    assert res.ok is False
    assert res.reason == "stamp_credential_mismatch"


def test_verify_stamp_ok_when_consistent(monkeypatch):
    mod = _load_py_sdk()
    ctx = _ctx(mod)
    monkeypatch.setattr(
        ctx, "verify",
        lambda presentation: mod.VerificationContext.Result(
            True, "valid", ppid="did:lemma:ppid_a", credential_id="c1",
        ),
    )
    stamp = {"lemma": {"ppid": "did:lemma:ppid_a", "credentialId": "c1",
                       "proof": {"credential": {"id": "c1"}}}}
    res = ctx.verify_stamp(stamp)
    assert res.ok is True
    assert res.ppid == "did:lemma:ppid_a"


def test_verify_stamp_accepts_bare_vc(monkeypatch):
    mod = _load_py_sdk()
    ctx = _ctx(mod)
    seen = {}

    def fake_verify(presentation):
        seen["presentation"] = presentation
        return mod.VerificationContext.Result(True, "valid", ppid="did:lemma:ppid_a", credential_id="c1")

    monkeypatch.setattr(ctx, "verify", fake_verify)
    res = ctx.verify_stamp(_vc())
    assert res.ok is True
    assert seen["presentation"]["credential"]["id"] == "c1"


def test_verify_stamp_durable_drops_session_assertion(monkeypatch):
    mod = _load_py_sdk()
    ctx = _ctx(mod)
    seen = {}

    def fake_verify(presentation):
        seen["presentation"] = presentation
        return mod.VerificationContext.Result(True, "valid", ppid="did:lemma:ppid_a", credential_id="c1")

    monkeypatch.setattr(ctx, "verify", fake_verify)
    stamp = {"lemma": {"ppid": "did:lemma:ppid_a",
                       "credential": {"id": "c1"},
                       "session_assertion": {"expires_at_unix": 1}}}
    res = ctx.verify_stamp(stamp, durable=True)
    assert res.ok is True
    # Durable mode strips the session assertion before verifying.
    assert "session_assertion" not in seen["presentation"]
    assert seen["presentation"] == {"credential": {"id": "c1"}}


# ---------------------------------------------------------------------------
# Node SDK + version + docs lockstep (source-pattern)
# ---------------------------------------------------------------------------

def test_node_sdk_exposes_verify_stamp():
    src = MJS_PATH.read_text(encoding="utf-8")
    assert "async function verifyStamp(stamp, { key = \"lemma\", durable = false } = {})" in src
    assert "function unwrapStamp(input, key = \"lemma\")" in src
    assert "function looksLikeVc(obj)" in src
    assert "export async function verifyStamp(stamp, options)" in src
    assert "stamp_ppid_mismatch" in src
    assert "stamp_credential_mismatch" in src
    # Exported from the factory and CommonJS interop.
    assert "return { verify, verifyWithPolicy, verifyStamp, verifyActionStamp, refresh };" in src
    assert "verifyStamp," in src
    assert "@version 1.4.1" in src


def test_node_sdk_durable_drops_session_assertion():
    src = MJS_PATH.read_text(encoding="utf-8")
    assert "(durable || !hasSession)" in src
    assert "credential: presentation.credential" in src


def test_backend_sdk_versions_bumped():
    from api.sdk_versions import backend_verifier_version

    serving = (ROOT / "api" / "sdk_serving.py").read_text(encoding="utf-8")
    assert 'response.headers["X-SDK-Version"] = version' in serving
    assert "backend_verifier_version()" in serving
    assert backend_verifier_version() == "1.4.1"


def test_docs_document_backend_verify_stamp():
    docs = DOCS_PATH.read_text(encoding="utf-8")
    assert "Re-verify a stored stamp on your backend" in docs
    assert "verifyStamp(" in docs
    assert "verify_stamp(" in docs
    assert "durable" in docs
    assert "includeCredential" in docs
