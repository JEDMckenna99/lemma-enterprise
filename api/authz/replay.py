from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping

try:
    from auth.redis_store import get_redis_client
except ImportError:
    get_redis_client = None  # Standalone mode (no Redis)


@dataclass(frozen=True)
class ReplayDecision:
    valid: bool
    code: str | None
    reason: str | None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _decode_pop_header(pop_header: str) -> dict | None:
    text = (pop_header or "").strip()
    if not text:
        return None
    if text.startswith("{"):
        try:
            payload = json.loads(text)
            return payload if isinstance(payload, dict) else None
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
    try:
        padded = text + ("=" * (-len(text) % 4))
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        payload = json.loads(decoded)
        return payload if isinstance(payload, dict) else None
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


def _decode_proof_header(headers: Mapping[str, str]) -> dict | None:
    raw = str(headers.get("X-Lemma-Proof") or "").strip()
    if not raw:
        return None
    if raw.startswith("{"):
        try:
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else None
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
    try:
        padded = raw + ("=" * (-len(raw) % 4))
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        payload = json.loads(decoded)
        return payload if isinstance(payload, dict) else None
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


def _parse_ts(raw) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    text = str(raw).strip()
    if not text:
        return None
    try:
        return datetime.fromtimestamp(float(text), tz=timezone.utc)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None


def _body_hash(body_bytes: bytes) -> str:
    return hashlib.sha256(body_bytes or b"").hexdigest()


def _nonce_set_once(key: str, ttl_seconds: int) -> bool:
    redis_client = get_redis_client()
    if not redis_client:
        return False
    return bool(redis_client.set(key, "1", nx=True, ex=max(1, ttl_seconds)))


def _b64url_decode(value: str) -> bytes:
    text = str(value or "").strip()
    padded = text + ("=" * (-len(text) % 4))
    return base64.urlsafe_b64decode(padded.encode("utf-8"))


def _canonical_pop_payload(pop_payload: dict) -> bytes:
    envelope = {
        "agent_key_id": str(pop_payload.get("agent_key_id") or "").strip(),
        "aud": str(pop_payload.get("aud") or "").strip(),
        "body_hash": str(pop_payload.get("body_hash") or "").strip().lower(),
        "exp": pop_payload.get("exp"),
        "iat": pop_payload.get("iat"),
        "method": str(pop_payload.get("method") or "").strip().upper(),
        "nonce": str(pop_payload.get("nonce") or "").strip(),
        "path": str(pop_payload.get("path") or "").strip(),
        "proof_id": str(pop_payload.get("proof_id") or "").strip(),
    }
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _resolve_bound_public_key(headers: Mapping[str, str], pop_payload: dict) -> tuple[str | None, str | None]:
    proof_payload = _decode_proof_header(headers) or {}
    delegated = proof_payload.get("delegated_proof") if isinstance(proof_payload.get("delegated_proof"), dict) else {}
    delegated_claims = delegated.get("claims") if isinstance(delegated.get("claims"), dict) else {}
    pop_key_id = str(pop_payload.get("agent_key_id") or "").strip()
    proof_key_id = str(
        delegated.get("agent_key_id")
        or delegated_claims.get("agent_key_id")
        or proof_payload.get("agent_key_id")
        or ""
    ).strip()
    if pop_key_id and proof_key_id and pop_key_id != proof_key_id:
        return None, "agent_key_id_mismatch"
    candidate = str(
        delegated.get("agent_public_key")
        or delegated_claims.get("agent_public_key")
        or delegated.get("public_key")
        or delegated_claims.get("public_key")
        or pop_payload.get("public_key")
        or headers.get("X-Lemma-Agent-Public-Key")
        or ""
    ).strip()
    if not candidate:
        return None, "missing_agent_public_key"
    return candidate, None


def _verify_ed25519_signature(public_key_b64: str, signature_b64: str, message: bytes) -> bool:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return False
    try:
        public_key_bytes = _b64url_decode(public_key_b64)
        signature_bytes = _b64url_decode(signature_b64)
        verifier = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        verifier.verify(signature_bytes, message)
        return True
    except Exception:
        return False


def validate_pop_replay(
    *,
    headers: Mapping[str, str],
    method: str,
    path: str,
    body_bytes: bytes | None = None,
    required: bool = False,
    ttl_seconds: int = 60,
    skew_seconds: int = 30,
    nonce_writer: Callable[[str, int], bool] | None = None,
    require_signature: bool | None = None,
) -> ReplayDecision:
    pop_payload = _decode_pop_header(headers.get("X-Lemma-PoP") or "")
    if not pop_payload:
        if required:
            return ReplayDecision(valid=False, code="AUTH_PROOF_OF_POSSESSION_FAILED", reason="missing_pop")
        return ReplayDecision(valid=True, code=None, reason="pop_not_required")

    nonce = str(pop_payload.get("nonce") or "").strip()
    proof_id = str(pop_payload.get("proof_id") or "").strip()
    signed_method = str(pop_payload.get("method") or "").upper().strip()
    signed_path = str(pop_payload.get("path") or "").strip()
    signed_body_hash = str(pop_payload.get("body_hash") or "").strip().lower()
    issued_at = _parse_ts(pop_payload.get("iat"))
    expires_at = _parse_ts(pop_payload.get("exp"))
    if not nonce or not proof_id:
        return ReplayDecision(valid=False, code="AUTH_PROOF_OF_POSSESSION_FAILED", reason="missing_nonce_or_proof_id")
    if signed_method and signed_method != str(method).upper():
        return ReplayDecision(valid=False, code="AUTH_PROOF_OF_POSSESSION_FAILED", reason="method_mismatch")
    if signed_path and signed_path != str(path):
        return ReplayDecision(valid=False, code="AUTH_PROOF_OF_POSSESSION_FAILED", reason="path_mismatch")
    if signed_body_hash and signed_body_hash != _body_hash(body_bytes or b""):
        return ReplayDecision(valid=False, code="AUTH_PROOF_OF_POSSESSION_FAILED", reason="body_hash_mismatch")
    now = _now()
    if issued_at and issued_at > now.replace(microsecond=0) and (issued_at - now).total_seconds() > skew_seconds:
        return ReplayDecision(valid=False, code="AUTH_PROOF_OF_POSSESSION_FAILED", reason="issued_at_in_future")
    if expires_at and (now - expires_at).total_seconds() > skew_seconds:
        return ReplayDecision(valid=False, code="AUTH_PROOF_OF_POSSESSION_FAILED", reason="expired")

    if require_signature is None:
        require_signature = str(os.getenv("LEMMA_POP_SIGNATURE_REQUIRED", "0")).strip().lower() in {"1", "true", "yes", "on"}
    pop_signature = str(pop_payload.get("sig") or pop_payload.get("signature") or "").strip()
    if require_signature:
        if not pop_signature:
            return ReplayDecision(valid=False, code="AUTH_PROOF_OF_POSSESSION_FAILED", reason="missing_signature")
        public_key_b64, key_error = _resolve_bound_public_key(headers, pop_payload)
        if key_error:
            return ReplayDecision(valid=False, code="AUTH_PROOF_OF_POSSESSION_FAILED", reason=key_error)
        verified = _verify_ed25519_signature(
            public_key_b64=public_key_b64 or "",
            signature_b64=pop_signature,
            message=_canonical_pop_payload(pop_payload),
        )
        if not verified:
            return ReplayDecision(valid=False, code="AUTH_PROOF_OF_POSSESSION_FAILED", reason="invalid_signature")

    writer = nonce_writer or _nonce_set_once
    nonce_key = f"lemma:pop_nonce:{proof_id}:{nonce}"
    stored = writer(nonce_key, ttl_seconds + skew_seconds)
    if not stored:
        return ReplayDecision(valid=False, code="AUTH_REPLAY_DETECTED", reason="nonce_reused_or_store_unavailable")
    return ReplayDecision(valid=True, code=None, reason="ok")

