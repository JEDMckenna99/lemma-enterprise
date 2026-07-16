"""Offline isHuman presentation verification for relying sites.

Drop-in Python helper that verifies an `IsHumanVerifier.verify()` result
**entirely on the relying site's own backend** with no per-request calls to
lemma.id. lemma.id is only contacted periodically to refresh the signed
revocation snapshot + issuer trust list (typically every ~15 minutes, or
whatever the snapshot's `max_staleness_seconds` field indicates).

Privacy and cost properties:
  * lemma.id never sees the PPID, site_id, or timing of an individual
    verification.
  * Zero per-request server-side cost on lemma.id.
  * Only one cached HTTP fetch per refresh interval per relying site.

Security: every cryptographic anchor is signed by a Lemma issuer key that
itself appears in the signed trust list. The trust list signature is the
network's root of trust; everything else is checked locally.

Requirements: ``cryptography>=42`` (standard PyPI package). No other deps.

Example:

    from relying_site_offline_verify import VerificationContext

    ctx = VerificationContext(
        site_id="tickets-demo.lemma.id",
        lemma_origin="https://lemma.id",
    )

    # ... in your request handler:
    presentation = request.json["presentation"]
    result = ctx.verify(presentation)
    if not result.ok:
        abort(401, result.reason)
    user_ppid = result.ppid

    # Or re-verify a stamp you stored earlier (from the browser SDK's
    # stamp(payload, includeCredential=True)), which checks the credential +
    # revocation AND that the logged ppid/credentialId match it. Accepts a bare
    # VC, a presentation, a stamp, or a stamped event interchangeably:
    check = ctx.verify_stamp(stored_log_row["lemma"])
    if not check.ok:
        flag_suspicious_log_row()

    # Re-verifying OLD log rows? Use durable mode so an aged session assertion
    # is treated as informational (credential + revocation still enforced):
    audit = ctx.verify_stamp(old_row["lemma"], durable=True)
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


SESSION_PRESENTATION_PREFIX = "lemma:site-session-presentation:v1"
ACTION_PRESENTATION_PREFIX = "lemma:site-action-presentation:v1"
ACTION_STAMP_VERSION = "action_stamp_v1"
TRUST_LIST_PREFIX = "lemma:issuer-trust-list:v1"
BLOOM_SNAPSHOT_PREFIX = "lemma:bloom-snapshot:v1"
TIME_SKEW_SECONDS = 300
DEFAULT_MAX_ACTION_AGE_SECONDS = 60
CONVERGENCE_PREFIX = "lemma:ppid-convergence:v1"
CONVERGENCE_SCHEMA = "ppid_convergence.v1"
ACTION_COMMITMENT_PREFIX = "lemma:action-commitment:v1"
FRESH_PASSKEY_PREFIX = "lemma:fresh-passkey-attestation:v1"
FRESH_PASSKEY_SCHEMA = "fresh_passkey_attestation.v1"
DEFAULT_FRESH_PASSKEY_MAX_AGE_SECONDS = 120
NONCE_STORE_MODE_OPTIONAL = "optional"
NONCE_STORE_MODE_REQUIRED = "required"


class SiteHostnameError(ValueError):
    """Raised when a hostname cannot be canonicalized for site binding."""


def _canonicalize_rp_id(rp_id: Optional[str]) -> str:
    """Mirror api.ppid.canonicalize_rp_id for zero-install usage."""
    value = (rp_id or "").strip().lower()
    if not value:
        return "unknown"
    if "://" in value:
        parsed = urllib.parse.urlparse(value)
        if parsed.hostname:
            value = parsed.hostname.lower()
        else:
            value = value.split("://", 1)[-1]
    host = value.split("/")[0]
    if ":" in host and not host.startswith("["):
        host = host.rsplit(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host or "unknown"


def canonicalize_site_hostname(value: Optional[str]) -> str:
    """Normalize integrator hostname input (mirrors api.site_hostname)."""
    try:
        from api.site_hostname import canonicalize_site_hostname as _api_canonicalize

        return _api_canonicalize(value)
    except ImportError:
        raw = (value or "").strip()
        if not raw:
            raise SiteHostnameError("hostname_required")
        if raw.lower().startswith("site_"):
            raise SiteHostnameError("internal_site_id_not_allowed")
        canonical = _canonicalize_rp_id(raw)
        if not canonical or canonical == "unknown":
            raise SiteHostnameError("invalid_hostname")
        return canonical


def try_canonicalize_site_hostname(value: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    try:
        return canonicalize_site_hostname(value), None
    except SiteHostnameError as exc:
        return None, str(exc)


def _import_enforce_site_policy():
    """Load site-policy helper from package or sibling zero-install file."""
    try:
        from lemma_ishuman_site_policy import enforce_site_policy

        return enforce_site_policy
    except ImportError:
        import importlib.util
        import sys
        from pathlib import Path

        sibling = Path(__file__).resolve().with_name("lemma_ishuman_site_policy.py")
        if not sibling.exists():
            raise ImportError("lemma_ishuman_site_policy unavailable") from None
        spec = importlib.util.spec_from_file_location("lemma_ishuman_site_policy", sibling)
        if spec is None or spec.loader is None:
            raise ImportError("lemma_ishuman_site_policy unavailable") from None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod.enforce_site_policy


def browser_canonical_message(credential: dict) -> bytes:
    """Reproduce the canonical message signed as proof.signatureValueWeb."""
    claims = credential.get("claims") or credential.get("credentialSubject") or {}
    sorted_claims: dict = {}
    for key in sorted(claims.keys()):
        value = claims[key]
        if value is True:
            sorted_claims[key] = "true"
        elif value is False:
            sorted_claims[key] = "false"
        elif isinstance(value, (list, dict)):
            sorted_claims[key] = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        else:
            sorted_claims[key] = value

    payload: dict = {
        "issuer": credential.get("issuer"),
        "subject": credential.get("subject"),
        "claims": sorted_claims,
    }
    if credential.get("issuedAt") is not None:
        payload["issuedAt"] = credential["issuedAt"]
    if credential.get("expiresAt") is not None:
        payload["expiresAt"] = credential["expiresAt"]
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def build_convergence_canonical_message(artifact: dict) -> bytes:
    lines = [
        CONVERGENCE_PREFIX,
        str(artifact.get("site_id") or "").strip(),
        str(artifact.get("legacy_ppid") or "").strip(),
        str(artifact.get("canonical_ppid") or "").strip(),
        str(artifact.get("convergence_id") or "").strip(),
        str(artifact.get("nonce") or "").strip(),
        str(int(artifact.get("issued_at_unix") or 0)),
        str(int(artifact.get("expires_at_unix") or 0)),
    ]
    return "\n".join(lines).encode("utf-8")


def verify_ppid_convergence_artifact(
    artifact: dict,
    *,
    site_id: str,
    canonical_ppid: str,
    trusted_issuer_pubkeys: list[str],
    now_unix: Optional[int] = None,
) -> tuple[bool, str]:
    if not isinstance(artifact, dict):
        return False, "convergence_missing"
    if str(artifact.get("schema") or "") != CONVERGENCE_SCHEMA:
        return False, "convergence_schema_mismatch"
    if str(artifact.get("site_id") or "").strip() != str(site_id or "").strip():
        return False, "convergence_site_mismatch"
    if str(artifact.get("canonical_ppid") or "").strip() != str(canonical_ppid or "").strip():
        return False, "convergence_canonical_ppid_mismatch"
    now = int(now_unix if now_unix is not None else time.time())
    try:
        expires_at = int(artifact.get("expires_at_unix") or 0)
        issued_at = int(artifact.get("issued_at_unix") or 0)
    except (TypeError, ValueError):
        return False, "convergence_timestamps_invalid"
    if not issued_at or not expires_at or expires_at < now:
        return False, "convergence_expired"
    if issued_at > now + TIME_SKEW_SECONDS:
        return False, "convergence_issued_in_future"
    proof = artifact.get("proof") or {}
    signature_hex = str(proof.get("signatureValueWeb") or "").strip()
    if not signature_hex:
        return False, "convergence_signature_missing"
    try:
        signature = bytes.fromhex(signature_hex)
    except ValueError:
        return False, "convergence_signature_malformed"
    unsigned = {
        key: artifact[key]
        for key in (
            "schema",
            "convergence_id",
            "site_id",
            "legacy_ppid",
            "canonical_ppid",
            "issued_at_unix",
            "expires_at_unix",
            "nonce",
        )
        if key in artifact
    }
    digest = hashlib.sha256(build_convergence_canonical_message(unsigned)).digest()
    for pubkey_hex in trusted_issuer_pubkeys:
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex)).verify(signature, digest)
            return True, "valid"
        except (InvalidSignature, ValueError):
            continue
    return False, "convergence_invalid_signature"


# ---------------------------------------------------------------------------
# Canonical message helpers (must byte-exactly match the issuer/verifier)
# ---------------------------------------------------------------------------


def _b64url_decode(text: str) -> bytes:
    pad = "=" * ((4 - len(text) % 4) % 4)
    return base64.urlsafe_b64decode(text + pad)


@dataclass
class TrustedIssuer:
    did: str
    pubkeys_hex: set[str]


def _compute_trust_list_content_hash(entries: list[dict]) -> str:
    canonical_entries = [
        {
            "did": str(item["did"]),
            "pubkey": str(item["pubkey"]).lower(),
            "key_id": str(item["key_id"]),
            "status": str(item["status"]),
            "valid_from_unix": int(item["valid_from_unix"]),
            "valid_until_unix": int(item["valid_until_unix"]),
            "priority": int(item.get("priority") or 0),
        }
        for item in entries
    ]
    canonical = json.dumps(canonical_entries, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_trust_list_signature_message(
    *, version: int, content_hash: str, generated_at_unix: int, valid_until_unix: int
) -> bytes:
    return "\n".join(
        [
            TRUST_LIST_PREFIX,
            str(int(version)),
            str(content_hash or "").strip(),
            str(int(generated_at_unix)),
            str(int(valid_until_unix)),
        ]
    ).encode("utf-8")


def _build_bloom_signature_message(
    *,
    sequence_number: int,
    content_hash: str,
    generated_at_unix: int,
    valid_until_unix: int,
) -> bytes:
    return "\n".join(
        [
            BLOOM_SNAPSHOT_PREFIX,
            str(int(sequence_number)),
            str(content_hash or "").strip(),
            str(int(generated_at_unix)),
            str(int(valid_until_unix)),
        ]
    ).encode("utf-8")


def _normalize_issuer_did(did: str) -> str:
    return (
        str(did or "")
        .strip()
        .lower()
        .split("#", 1)[0]
        .split("?", 1)[0]
        .rstrip("/")
    )


def _parse_snapshot_issuer_pubkey_hex(snapshot: dict) -> str:
    direct = str(snapshot.get("issuer_pubkey") or "").strip().lower()
    if len(direct) == 64 and all(ch in "0123456789abcdef" for ch in direct):
        return direct
    did = str(snapshot.get("issuer_did") or "")
    if did.startswith("did:lemma:"):
        maybe = did.replace("did:lemma:", "")[:64].lower()
        if len(maybe) == 64 and all(ch in "0123456789abcdef" for ch in maybe):
            return maybe
    return ""


def _decode_signature(value: str) -> bytes:
    text = str(value or "").strip()
    if not text:
        raise ValueError("empty signature")
    if len(text) == 128 and all(ch in "0123456789abcdef" for ch in text.lower()):
        return bytes.fromhex(text)
    return _b64url_decode(text)


def _normalize_trust_list_entry(raw: dict) -> dict | None:
    did = str(raw.get("did") or raw.get("issuer_did") or "").strip()
    pubkey = str(raw.get("pubkey") or raw.get("public_key") or raw.get("publicKey") or "").strip().lower()
    if not did or len(pubkey) != 64 or not all(c in "0123456789abcdef" for c in pubkey):
        return None
    status = str(raw.get("status") or "active").strip().lower()
    if status == "revoked":
        return None
    return {
        "did": did,
        "pubkey": pubkey,
        "key_id": str(raw.get("key_id") or f"{did}#{pubkey[:12]}").strip(),
        "status": status,
        "valid_from_unix": int(raw.get("valid_from_unix") or 0),
        "valid_until_unix": int(raw.get("valid_until_unix") or 0),
        "priority": int(raw.get("priority") or 0),
    }


def _verify_signed_trust_list_payload(payload: dict, *, now_unix: int | None = None) -> dict[str, TrustedIssuer]:
    if not isinstance(payload, dict):
        raise RuntimeError("trust_list_missing")

    required = (
        "version",
        "generated_at_unix",
        "valid_until_unix",
        "content_hash",
        "signer_pubkey",
        "signature",
        "issuers",
    )
    for key in required:
        if payload.get(key) in (None, ""):
            raise RuntimeError(f"trust_list_{key}_missing")

    now = int(now_unix if now_unix is not None else time.time())
    if now + TIME_SKEW_SECONDS < int(payload["generated_at_unix"]):
        raise RuntimeError("trust_list_not_yet_valid")
    if now - TIME_SKEW_SECONDS > int(payload["valid_until_unix"]):
        raise RuntimeError("trust_list_expired")

    raw_issuers = payload.get("issuers")
    if not isinstance(raw_issuers, list) or not raw_issuers:
        raise RuntimeError("trust_list_issuers_missing")

    normalized: list[dict] = []
    for row in raw_issuers:
        if not isinstance(row, dict):
            raise RuntimeError("trust_list_issuer_malformed")
        entry = _normalize_trust_list_entry(row)
        if not entry:
            raise RuntimeError("trust_list_issuer_invalid")
        normalized.append(entry)

    expected_hash = _compute_trust_list_content_hash(normalized)
    if expected_hash != str(payload["content_hash"]):
        raise RuntimeError("trust_list_content_hash_mismatch")

    try:
        signer_key_bytes = bytes.fromhex(str(payload["signer_pubkey"]))
        signature = _decode_signature(str(payload["signature"]))
    except Exception as exc:
        raise RuntimeError("trust_list_malformed") from exc

    message = _build_trust_list_signature_message(
        version=int(payload["version"]),
        content_hash=str(payload["content_hash"]),
        generated_at_unix=int(payload["generated_at_unix"]),
        valid_until_unix=int(payload["valid_until_unix"]),
    )
    try:
        _verify_site_ed25519_digest(signer_key_bytes, signature, message)
    except (InvalidSignature, ValueError, KeyError) as exc:
        raise RuntimeError("trust_list_invalid_signature") from exc

    issuers: dict[str, TrustedIssuer] = {}
    for entry in normalized:
        valid_from = int(entry.get("valid_from_unix") or 0)
        valid_until = int(entry.get("valid_until_unix") or 0)
        if valid_from and (now + TIME_SKEW_SECONDS) < valid_from:
            continue
        if valid_until and (now - TIME_SKEW_SECONDS) > valid_until:
            continue
        existing = issuers.get(_normalize_issuer_did(entry["did"]))
        if existing:
            existing.pubkeys_hex.add(entry["pubkey"])
        else:
            issuers[_normalize_issuer_did(entry["did"])] = TrustedIssuer(
                did=_normalize_issuer_did(entry["did"]),
                pubkeys_hex={entry["pubkey"]},
            )

    if not issuers:
        raise RuntimeError("trust_list_no_active_issuers")
    return issuers


def _build_session_message(assertion: dict) -> bytes:
    lines = [
        SESSION_PRESENTATION_PREFIX,
        str(assertion["session_id"]).strip(),
        str(assertion["site_id"]).strip(),
        str(assertion["credential_id"]).strip(),
        str(assertion["subject"]).strip(),
        str(assertion["session_nonce"]).strip(),
        str(assertion["bloom_sequence"]),
        str(assertion["issued_at_unix"]),
        str(assertion["expires_at_unix"]),
    ]
    return "\n".join(lines).encode("utf-8")


def _canonical_json_stringify(value) -> str:
    if value is None or not isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(_canonical_json_stringify(item) for item in value) + "]"
    keys = sorted(value.keys())
    parts = [
        json.dumps(key, separators=(",", ":"), ensure_ascii=False)
        + ":"
        + _canonical_json_stringify(value[key])
        for key in keys
    ]
    return "{" + ",".join(parts) + "}"


def hash_action_body(body) -> str:
    """Stable SHA-256 hex digest of a request body (matches browser SDK)."""
    canonical = _canonical_json_stringify(body if body is not None else {})
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_action_commitment(
    *,
    server_nonce: str,
    site_id: str,
    action: str,
    method: str = "POST",
    path: str = "",
    body_hash: str = "",
) -> str:
    """Opaque action binding; lemma.id never receives action details."""
    lines = [
        ACTION_COMMITMENT_PREFIX,
        str(server_nonce or "").strip(),
        str(site_id or "").strip(),
        str(action or "").strip(),
        str(method or "POST").strip().upper(),
        str(path or "").strip(),
        str(body_hash or "").strip().lower(),
    ]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def build_fresh_passkey_canonical_message(artifact: dict) -> bytes:
    lines = [
        FRESH_PASSKEY_PREFIX,
        str(artifact.get("schema") or FRESH_PASSKEY_SCHEMA).strip(),
        str(artifact.get("site_id") or "").strip(),
        str(artifact.get("credential_id") or "").strip(),
        str(artifact.get("subject") or "").strip(),
        str(artifact.get("action_commitment") or "").strip().lower(),
        str(artifact.get("attestation_id") or "").strip(),
        str(int(artifact.get("issued_at_unix") or 0)),
        str(int(artifact.get("expires_at_unix") or 0)),
    ]
    return "\n".join(lines).encode("utf-8")


def verify_fresh_passkey_attestation(
    attestation: dict,
    *,
    site_id: str,
    credential_id: str,
    subject: str,
    action_commitment: str,
    trusted_issuer_pubkeys: list[str],
    now_unix: Optional[int] = None,
    max_age_seconds: int = DEFAULT_FRESH_PASSKEY_MAX_AGE_SECONDS,
) -> tuple[bool, str]:
    if not isinstance(attestation, dict):
        return False, "fresh_passkey_missing"
    if str(attestation.get("schema") or "") != FRESH_PASSKEY_SCHEMA:
        return False, "fresh_passkey_schema_mismatch"
    if str(attestation.get("site_id") or "").strip() != str(site_id or "").strip():
        return False, "fresh_passkey_site_mismatch"
    if str(attestation.get("credential_id") or "").strip() != str(credential_id or "").strip():
        return False, "fresh_passkey_credential_mismatch"
    if str(attestation.get("subject") or "").strip() != str(subject or "").strip():
        return False, "fresh_passkey_subject_mismatch"
    expected_commitment = str(action_commitment or "").strip().lower()
    if expected_commitment and str(attestation.get("action_commitment") or "").strip().lower() != expected_commitment:
        return False, "fresh_passkey_commitment_mismatch"
    now = int(now_unix if now_unix is not None else time.time())
    try:
        expires_at = int(attestation.get("expires_at_unix") or 0)
        issued_at = int(attestation.get("issued_at_unix") or 0)
    except (TypeError, ValueError):
        return False, "fresh_passkey_timestamps_invalid"
    if not issued_at or not expires_at or expires_at < now:
        return False, "fresh_passkey_expired"
    if issued_at > now + TIME_SKEW_SECONDS:
        return False, "fresh_passkey_issued_in_future"
    if now - issued_at > max(1, int(max_age_seconds)):
        return False, "fresh_passkey_too_old"
    proof = attestation.get("proof") or {}
    signature_hex = str(proof.get("signatureValueWeb") or "").strip()
    if not signature_hex:
        return False, "fresh_passkey_signature_missing"
    try:
        signature = bytes.fromhex(signature_hex)
    except ValueError:
        return False, "fresh_passkey_signature_malformed"
    unsigned = {
        key: attestation[key]
        for key in (
            "schema",
            "attestation_id",
            "site_id",
            "credential_id",
            "subject",
            "action_commitment",
            "issued_at_unix",
            "expires_at_unix",
        )
        if key in attestation
    }
    digest = hashlib.sha256(build_fresh_passkey_canonical_message(unsigned)).digest()
    for pubkey_hex in trusted_issuer_pubkeys:
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex)).verify(signature, digest)
            return True, "valid"
        except (InvalidSignature, ValueError):
            continue
    return False, "fresh_passkey_invalid_signature"


def _build_action_message(assertion: dict) -> bytes:
    lines = [
        ACTION_PRESENTATION_PREFIX,
        str(assertion.get("version") or ACTION_STAMP_VERSION).strip(),
        str(assertion["site_id"]).strip(),
        str(assertion["credential_id"]).strip(),
        str(assertion["subject"]).strip(),
        str(assertion.get("assurance") or "").strip(),
        str(assertion["action"]).strip(),
        str(assertion.get("method") or "POST").strip().upper(),
        str(assertion.get("path") or "").strip(),
        str(assertion["body_hash"]).strip(),
        str(assertion["nonce"]).strip(),
        str(assertion["issued_at_unix"]),
        str(assertion["expires_at_unix"]),
    ]
    return "\n".join(lines).encode("utf-8")


def _verify_site_ed25519_digest(pubkey_bytes: bytes, signature_bytes: bytes, message_bytes: bytes) -> None:
    digest = hashlib.sha256(message_bytes).digest()
    Ed25519PublicKey.from_public_bytes(pubkey_bytes).verify(signature_bytes, digest)


class InMemoryNonceStore:
    """Simple replay guard for action-stamp nonces (single-process demos/tests)."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def consume(self, nonce: str, *, site_id: str = "", ttl_seconds: int = 300) -> bool:
        del site_id, ttl_seconds
        text = str(nonce or "").strip()
        if not text or text in self._seen:
            return False
        self._seen.add(text)
        return True


def _import_redis_nonce_store():
    try:
        from lemma_ishuman_nonce_store import RedisNonceStore

        return RedisNonceStore
    except ImportError:
        import importlib.util
        import sys
        from pathlib import Path

        sibling = Path(__file__).resolve().with_name("lemma_ishuman_nonce_store.py")
        if not sibling.exists():
            return None
        spec = importlib.util.spec_from_file_location("lemma_ishuman_nonce_store", sibling)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod.RedisNonceStore


def _looks_like_vc(obj) -> bool:
    """A bare verifiable credential has subject + claims + a proof object."""
    return (
        isinstance(obj, dict)
        and "subject" in obj
        and "claims" in obj
        and isinstance(obj.get("proof"), dict)
    )


def _has_stamp_fields(obj: dict) -> bool:
    """Does this object carry the flat summary fields a stamp adds?"""
    return any(k in obj for k in ("ppid", "verified", "verifiedAt", "credentialId"))


def _has_action_stamp_fields(obj: dict) -> bool:
    return isinstance(obj, dict) and (
        obj.get("version") == ACTION_STAMP_VERSION
        or bool(obj.get("action_assertion") and obj.get("action_signature"))
    )


def _unwrap_action_stamp(value, key: str = "lemma"):
    if not isinstance(value, dict):
        return None
    if value.get(key) and isinstance(value[key], dict) and _has_action_stamp_fields(value[key]):
        return value[key]
    if _has_action_stamp_fields(value):
        return value
    return None


def _unwrap_stamp(value, key: str = "lemma"):
    """Normalize the shapes a relying site may pass to ``verify_stamp`` into
    ``(stamp_or_None, presentation)``.

    Accepts:
      - a bare verifiable credential (has ``subject`` + ``claims``)
      - a raw presentation (has ``credential`` + optional session assertion)
      - a stamp from ``getVerification(includeCredential=True)`` (flat fields + ``credential``)
      - a stamp from ``getVerification(includeProof=True)`` (flat fields + ``proof``)
      - a stamped event from ``stamp(payload)`` (has ``[key]`` holding one of the above)

    The first element is the flat-field stamp (used for tamper-binding) when
    present, else ``None``.
    """
    if not isinstance(value, dict):
        return None

    # Stamped event: unwrap the [key] envelope first, but only if the top level
    # isn't itself a credential/presentation/stamp.
    if (
        not _looks_like_vc(value)
        and not isinstance(value.get("proof"), dict)
        and not isinstance(value.get("credential"), dict)
        and isinstance(value.get(key), dict)
    ):
        value = value[key]

    # Bare VC -> wrap as a presentation; nothing to cross-check.
    if _looks_like_vc(value):
        return (None, {"credential": value})

    # Stamp carrying a full session presentation under ``proof``.
    proof = value.get("proof")
    if isinstance(proof, dict) and isinstance(proof.get("credential"), dict):
        return (value, proof)

    # Object carrying a VC under ``credential``: either a raw presentation
    # (no flat fields) or a VC-only stamp (flat fields present).
    if isinstance(value.get("credential"), dict):
        is_stamp = _has_stamp_fields(value)
        presentation = {
            "credential": value["credential"],
            "session_assertion": value.get("session_assertion"),
            "session_signature": value.get("session_signature"),
            "session_nonce": value.get("session_nonce"),
            "bloom_sequence": value.get("bloom_sequence"),
        }
        return (value if is_stamp else None, presentation)

    return None


# ---------------------------------------------------------------------------
# Trust list + Bloom snapshot cache (refreshed periodically, never per-request)
# ---------------------------------------------------------------------------


@dataclass
class _Snapshot:
    sequence_number: int
    revoked_hash_set: set[str]
    valid_until_unix: int
    fetched_at_unix: float
    max_staleness_seconds: int
    issuers: dict[str, TrustedIssuer]


class VerificationContext:
    """Caches the signed trust list + Bloom snapshot and verifies presentations."""

    def __init__(
        self,
        *,
        site_id: str,
        lemma_origin: str = "https://lemma.id",
        max_session_age_seconds: int = 24 * 60 * 60,
        refresh_seconds: int = 15 * 60,
        require_session_assertion: bool = False,
        required_assurance: str = "ishuman",
        max_action_age_seconds: int = DEFAULT_MAX_ACTION_AGE_SECONDS,
        nonce_store_mode: str = NONCE_STORE_MODE_OPTIONAL,
        fresh_passkey_max_age_seconds: int = DEFAULT_FRESH_PASSKEY_MAX_AGE_SECONDS,
    ) -> None:
        self.site_id = canonicalize_site_hostname(site_id)
        self.lemma_origin = lemma_origin.rstrip("/")
        self.max_session_age_seconds = max_session_age_seconds
        self.refresh_seconds = refresh_seconds
        self.require_session_assertion = require_session_assertion
        self.required_assurance = (required_assurance or "ishuman").strip().lower()
        self.max_action_age_seconds = max_action_age_seconds
        self.nonce_store_mode = (nonce_store_mode or NONCE_STORE_MODE_OPTIONAL).strip().lower()
        self.fresh_passkey_max_age_seconds = fresh_passkey_max_age_seconds
        self._lock = threading.Lock()
        self._snapshot: Optional[_Snapshot] = None

    @staticmethod
    def _credential_assurance(claims: dict) -> Optional[str]:
        raw = claims.get("assurance")
        if raw:
            return str(raw).strip().lower()
        if claims.get("isHuman") in (True, "true", "True", 1, "1"):
            return "ishuman"
        return None

    @staticmethod
    def _assurance_meets_policy(actual: Optional[str], required: str) -> bool:
        if not actual:
            return False
        required = (required or "ishuman").strip().lower()
        return actual.strip().lower() == required

    def _fetch_signed_bundle(self) -> _Snapshot:
        url = f"{self.lemma_origin}/api/revocation/bloom-filter"
        with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310, lemma.id only
            data = json.loads(resp.read().decode("utf-8"))
        if not data.get("success"):
            raise RuntimeError("bloom-filter endpoint returned failure")

        # Verify the trust list signature first (root of trust)
        trust_list = data.get("trust_list") or {}
        issuers = self._verify_trust_list(trust_list)

        # Verify the Bloom snapshot signature using the trust list
        snapshot = data.get("snapshot") or {}
        self._verify_bloom_snapshot(snapshot, data.get("hashed_revoked_ids") or [], issuers)

        return _Snapshot(
            sequence_number=int(snapshot.get("sequence_number") or 0),
            revoked_hash_set=set(data.get("hashed_revoked_ids") or []),
            valid_until_unix=int(snapshot.get("valid_until_unix") or 0),
            fetched_at_unix=time.time(),
            max_staleness_seconds=int(snapshot.get("max_staleness_seconds") or self.refresh_seconds),
            issuers=issuers,
        )

    def _verify_trust_list(self, trust_list: dict) -> dict[str, TrustedIssuer]:
        return _verify_signed_trust_list_payload(trust_list)

    def _verify_bloom_snapshot(
        self,
        snapshot: dict,
        hashed_revoked_ids: list[str],
        issuers: dict[str, TrustedIssuer],
    ) -> None:
        # Verify content_hash matches the payload
        expected_hash = hashlib.sha256(
            json.dumps(
                {"hashed_revoked_ids": hashed_revoked_ids, "count": len(hashed_revoked_ids)},
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        if expected_hash != (snapshot.get("content_hash") or ""):
            raise RuntimeError("bloom snapshot content_hash mismatch")

        issuer_did = _normalize_issuer_did(snapshot.get("issuer_did") or "")
        trusted = issuers.get(issuer_did)
        if not trusted:
            raise RuntimeError(f"bloom snapshot signed by untrusted issuer {issuer_did}")

        pubkey_hex = _parse_snapshot_issuer_pubkey_hex(snapshot)
        if not pubkey_hex or pubkey_hex not in trusted.pubkeys_hex:
            raise RuntimeError("bloom snapshot issuer pubkey untrusted")

        try:
            signature = _decode_signature(str(snapshot.get("signature") or ""))
        except ValueError as exc:
            raise RuntimeError("bloom snapshot signature malformed") from exc

        message = _build_bloom_signature_message(
            sequence_number=int(snapshot.get("sequence_number") or 0),
            content_hash=str(snapshot.get("content_hash") or ""),
            generated_at_unix=int(snapshot.get("generated_at_unix") or 0),
            valid_until_unix=int(snapshot.get("valid_until_unix") or 0),
        )
        try:
            _verify_site_ed25519_digest(bytes.fromhex(pubkey_hex), signature, message)
        except (InvalidSignature, ValueError, KeyError) as exc:
            raise RuntimeError("bloom snapshot signature did not verify") from exc

    def _ensure_fresh_snapshot(self) -> _Snapshot:
        with self._lock:
            now = time.time()
            stale = (
                self._snapshot is None
                or now - self._snapshot.fetched_at_unix > self._snapshot.max_staleness_seconds
                or now - self._snapshot.fetched_at_unix > self.refresh_seconds
            )
            if stale:
                self._snapshot = self._fetch_signed_bundle()
            return self._snapshot

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @dataclass
    class Result:
        ok: bool
        reason: str
        ppid: Optional[str] = None
        credential_id: Optional[str] = None
        issuer_did: Optional[str] = None
        bound_site_id: Optional[str] = None
        assurance: Optional[str] = None
        legacy_ppid: Optional[str] = None

    def verify(self, presentation: dict) -> "VerificationContext.Result":
        """Verify a presentation bundle without contacting lemma.id per-request."""
        credential = (presentation or {}).get("credential")
        if not isinstance(credential, dict):
            return self.Result(False, "credential_missing")

        proof = credential.get("proof") or {}
        signature_hex = (proof.get("signatureValueWeb") or "").strip()
        if not signature_hex:
            return self.Result(False, "browser_signature_missing")

        issuer_did = (credential.get("issuer") or "").strip()
        snapshot = self._ensure_fresh_snapshot()
        trusted = snapshot.issuers.get(issuer_did)
        if not trusted:
            return self.Result(False, "untrusted_issuer")

        # 1. Verify credential Ed25519 signature against trust-list pubkeys
        try:
            signature = bytes.fromhex(signature_hex)
        except ValueError:
            return self.Result(False, "signature_malformed")
        message = browser_canonical_message(credential)
        digest = hashlib.sha256(message).digest()
        sig_ok = False
        for pubkey_hex in trusted.pubkeys_hex:
            try:
                Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex)).verify(signature, digest)
                sig_ok = True
                break
            except InvalidSignature:
                continue
        if not sig_ok:
            return self.Result(False, "invalid_signature")

        # 2. Claim-level checks: assurance tier, site binding, expiry
        claims = credential.get("claims") or credential.get("credentialSubject") or {}
        assurance = self._credential_assurance(claims)
        if not assurance:
            return self.Result(False, "not_ishuman")
        if assurance not in ("passkey", "ishuman"):
            return self.Result(False, "invalid_assurance")
        if not self._assurance_meets_policy(assurance, self.required_assurance):
            return self.Result(False, "assurance_insufficient", assurance=assurance)
        bound_site_raw = (
            claims.get("siteId") or claims.get("site_id") or claims.get("siteDomain") or ""
        )
        bound_site, bound_err = try_canonicalize_site_hostname(bound_site_raw)
        if bound_err or bound_site != self.site_id:
            return self.Result(False, "site_id_mismatch", bound_site_id=bound_site_raw)
        try:
            expires_at = int(claims.get("expiresAt") or 0)
        except (TypeError, ValueError):
            return self.Result(False, "expiresAt_malformed")
        if expires_at and expires_at < int(time.time()):
            return self.Result(False, "expired")

        # 3. Local Bloom revocation check (SHA-256 of credential id)
        credential_id = credential.get("id") or ""
        if credential_id:
            id_hash = hashlib.sha256(credential_id.encode("utf-8")).hexdigest()
            if id_hash in snapshot.revoked_hash_set:
                return self.Result(False, "revoked", credential_id=credential_id)

        # 4. Verify the site-bound session assertion (proof of possession)
        assertion = (presentation or {}).get("session_assertion")
        signature_b64 = (presentation or {}).get("session_signature") or ""
        site_pubkey_b64 = (
            claims.get("site_signing_pubkey") or claims.get("siteSigningPubkey") or ""
        )
        if assertion and signature_b64:
            if not site_pubkey_b64:
                return self.Result(False, "credential_missing_site_signing_pubkey")
            try:
                pubkey_bytes = _b64url_decode(site_pubkey_b64)
                signature_bytes = _b64url_decode(signature_b64)
                _verify_site_ed25519_digest(
                    pubkey_bytes,
                    signature_bytes,
                    _build_session_message(assertion),
                )
            except (InvalidSignature, ValueError, KeyError):
                return self.Result(False, "invalid_session_signature")
            try:
                if int(assertion["expires_at_unix"]) < int(time.time()):
                    return self.Result(False, "session_expired")
                age = int(time.time()) - int(assertion["issued_at_unix"])
                if age > self.max_session_age_seconds:
                    return self.Result(False, "session_too_old")
            except (TypeError, ValueError, KeyError):
                return self.Result(False, "session_timestamps_invalid")
            session_site, session_site_err = try_canonicalize_site_hostname(
                assertion.get("site_id") or ""
            )
            if session_site_err or session_site != self.site_id:
                return self.Result(False, "session_site_id_mismatch")
        elif self.require_session_assertion and site_pubkey_b64:
            return self.Result(False, "session_assertion_required")

        legacy_ppid = None
        convergence = (presentation or {}).get("ppid_convergence")
        if convergence:
            trusted_pubkeys: list[str] = []
            for trusted_issuer in snapshot.issuers.values():
                trusted_pubkeys.extend(sorted(trusted_issuer.pubkeys_hex))
            ok_conv, conv_reason = verify_ppid_convergence_artifact(
                convergence,
                site_id=self.site_id,
                canonical_ppid=credential.get("subject") or "",
                trusted_issuer_pubkeys=trusted_pubkeys,
            )
            if not ok_conv:
                return self.Result(False, conv_reason)
            legacy_ppid = str(convergence.get("legacy_ppid") or "").strip() or None

        return self.Result(
            ok=True,
            reason="valid",
            ppid=credential.get("subject"),
            credential_id=credential_id or None,
            issuer_did=issuer_did,
            bound_site_id=bound_site,
            assurance=assurance,
            legacy_ppid=legacy_ppid,
        )

    def verify_with_policy(
        self,
        presentation: dict,
        *,
        policy_store=None,
        require_policy: bool = True,
    ) -> "VerificationContext.Result":
        """Verify presentation crypto, then enforce site block/doubt policy."""
        result = self.verify(presentation)
        if not result.ok:
            return result
        try:
            enforce_site_policy = _import_enforce_site_policy()
        except ImportError:
            if require_policy:
                return self.Result(False, "site_policy_not_configured")
            return result
        ok, reason, _decision = enforce_site_policy(
            ppid=result.ppid or "",
            policy_store=policy_store,
            legacy_ppid=result.legacy_ppid,
            require_policy=require_policy,
        )
        if not ok:
            return self.Result(False, reason, ppid=result.ppid, legacy_ppid=result.legacy_ppid)
        return result

    def verify_stamp(
        self, stamp: dict, *, key: str = "lemma", durable: bool = False
    ) -> "VerificationContext.Result":
        """Verify a stamp/credential produced by the browser SDK's
        ``stamp(payload, {includeCredential: true})`` / ``getVerification(...)``.

        Re-checks the credential + revocation AND that the stamp's logged
        ``ppid`` / ``credentialId`` match the cryptographically verified values,
        so a tampered log row can't claim a different identity than its proof
        supports. Accepts a bare VC, a raw presentation, a stamp object, or a
        full stamped event interchangeably.

        Pass ``durable=True`` to re-verify OLD log rows: any aged session
        assertion is treated as informational (the session assertion is dropped
        before verification) while the credential + revocation are still
        enforced.
        """
        unwrapped = _unwrap_stamp(stamp, key)
        if unwrapped is None:
            return self.Result(False, "stamp_missing_proof")
        inner, presentation = unwrapped
        has_session = bool(
            presentation.get("session_assertion") and presentation.get("session_signature")
        )
        if durable or not has_session:
            to_verify = {"credential": presentation.get("credential")}
        else:
            to_verify = presentation
        result = self.verify(to_verify)
        if not result.ok:
            return result
        if inner:
            stamped_ppid = inner.get("ppid")
            if stamped_ppid and result.ppid and stamped_ppid != result.ppid:
                return self.Result(False, "stamp_ppid_mismatch", ppid=result.ppid)
            stamped_cred = inner.get("credentialId")
            if stamped_cred and result.credential_id and stamped_cred != result.credential_id:
                return self.Result(
                    False, "stamp_credential_mismatch", credential_id=result.credential_id,
                )
        return result

    def verify_action_stamp(
        self,
        stamped_event: dict,
        *,
        action: str,
        method: str = "POST",
        path: str = "",
        body=None,
        required_assurance: Optional[str] = None,
        nonce_store=None,
        nonce_store_mode: Optional[str] = None,
        require_fresh_passkey: bool = False,
        server_nonce: Optional[str] = None,
        key: str = "lemma",
    ) -> "VerificationContext.Result":
        """Verify an action-bound stamp from ``stampAction()`` locally."""
        inner = _unwrap_action_stamp(stamped_event, key)
        if inner is None:
            return self.Result(False, "action_stamp_missing")

        credential = inner.get("credential")
        assertion = inner.get("action_assertion")
        signature_b64 = (inner.get("action_signature") or "").strip()
        if not isinstance(credential, dict) or not isinstance(assertion, dict) or not signature_b64:
            return self.Result(False, "action_stamp_incomplete")

        cred_result = self.verify({"credential": credential})
        if not cred_result.ok:
            return cred_result

        policy = (required_assurance or self.required_assurance or "ishuman").strip().lower()
        if not self._assurance_meets_policy(cred_result.assurance, policy):
            return self.Result(False, "assurance_insufficient", assurance=cred_result.assurance)

        expected_body_hash = hash_action_body(body)
        stamped_hash = str(
            inner.get("bodyHash") or inner.get("body_hash") or assertion.get("body_hash") or ""
        ).strip()
        if stamped_hash and stamped_hash != expected_body_hash:
            return self.Result(False, "action_body_hash_mismatch")

        expected_action = str(action or "").strip()
        expected_method = str(method or "POST").strip().upper()
        expected_path = str(path or "").strip()
        if str(assertion.get("action") or "").strip() != expected_action:
            return self.Result(False, "action_name_mismatch")
        if str(assertion.get("method") or "POST").strip().upper() != expected_method:
            return self.Result(False, "action_method_mismatch")
        if str(assertion.get("path") or "").strip() != expected_path:
            return self.Result(False, "action_path_mismatch")
        action_site, action_site_err = try_canonicalize_site_hostname(assertion.get("site_id") or "")
        if action_site_err or action_site != self.site_id:
            return self.Result(False, "action_site_id_mismatch")

        try:
            expires_at = int(assertion.get("expires_at_unix") or 0)
            issued_at = int(assertion.get("issued_at_unix") or 0)
        except (TypeError, ValueError):
            return self.Result(False, "action_timestamps_invalid")
        now = int(time.time())
        if expires_at and now >= expires_at:
            return self.Result(False, "action_expired")
        if issued_at and now - issued_at > self.max_action_age_seconds:
            return self.Result(False, "action_too_old")

        nonce = str(assertion.get("nonce") or inner.get("nonce") or "").strip()
        if not nonce:
            return self.Result(False, "action_nonce_missing")

        mode = (nonce_store_mode or self.nonce_store_mode or NONCE_STORE_MODE_OPTIONAL).strip().lower()
        if mode == NONCE_STORE_MODE_REQUIRED and nonce_store is None:
            return self.Result(False, "action_nonce_store_required")
        if nonce_store is not None:
            consume = getattr(nonce_store, "consume", None)
            if not callable(consume):
                return self.Result(False, "action_nonce_store_invalid")
            consumed = consume(nonce, site_id=self.site_id, ttl_seconds=self.max_action_age_seconds + 300)
            if not consumed:
                return self.Result(False, "action_nonce_reused")

        if require_fresh_passkey:
            attestation = inner.get("fresh_passkey_attestation")
            if not isinstance(attestation, dict):
                return self.Result(False, "fresh_passkey_missing")
            if not server_nonce:
                return self.Result(False, "fresh_passkey_server_nonce_missing")
            action_commitment = build_action_commitment(
                server_nonce=str(server_nonce),
                site_id=self.site_id,
                action=expected_action,
                method=expected_method,
                path=expected_path,
                body_hash=expected_body_hash,
            )
            snapshot = self._ensure_fresh_snapshot()
            trusted_pubkeys: list[str] = []
            for trusted_issuer in snapshot.issuers.values():
                trusted_pubkeys.extend(sorted(trusted_issuer.pubkeys_hex))
            ok_fp, fp_reason = verify_fresh_passkey_attestation(
                attestation,
                site_id=self.site_id,
                credential_id=str(credential.get("id") or cred_result.credential_id or ""),
                subject=str(credential.get("subject") or cred_result.ppid or ""),
                action_commitment=action_commitment,
                trusted_issuer_pubkeys=trusted_pubkeys,
                max_age_seconds=self.fresh_passkey_max_age_seconds,
            )
            if not ok_fp:
                return self.Result(False, fp_reason)

        claims = credential.get("claims") or credential.get("credentialSubject") or {}
        site_pubkey_b64 = claims.get("site_signing_pubkey") or claims.get("siteSigningPubkey") or ""
        if not site_pubkey_b64:
            return self.Result(False, "credential_missing_site_signing_pubkey")

        if inner.get("ppid") and cred_result.ppid and inner.get("ppid") != cred_result.ppid:
            return self.Result(False, "stamp_ppid_mismatch", ppid=cred_result.ppid)
        if (
            inner.get("credentialId")
            and cred_result.credential_id
            and inner.get("credentialId") != cred_result.credential_id
        ):
            return self.Result(
                False, "stamp_credential_mismatch", credential_id=cred_result.credential_id,
            )

        try:
            _verify_site_ed25519_digest(
                _b64url_decode(site_pubkey_b64),
                _b64url_decode(signature_b64),
                _build_action_message(assertion),
            )
        except (InvalidSignature, ValueError, KeyError):
            return self.Result(False, "invalid_action_signature")

        return cred_result


# ---------------------------------------------------------------------------
# Tiny CLI for manual testing:
#   python relying_site_offline_verify.py <site_id> <presentation.json>
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("usage: relying_site_offline_verify.py <site_id> <presentation.json>")
        sys.exit(2)
    site_id = sys.argv[1]
    with open(sys.argv[2], encoding="utf-8") as fh:
        presentation = json.load(fh)
    ctx = VerificationContext(site_id=site_id)
    result = ctx.verify(presentation)
    print(json.dumps(result.__dict__, indent=2, default=str))
    sys.exit(0 if result.ok else 1)
