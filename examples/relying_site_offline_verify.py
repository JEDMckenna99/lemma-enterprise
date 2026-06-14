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
    # stamp(payload, includeCredential=True)) — checks the credential +
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
import urllib.request
from dataclasses import dataclass
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


SESSION_PRESENTATION_PREFIX = "lemma:site-session-presentation:v1"
TRUST_LIST_PREFIX = "lemma:issuer-trust-list:v1"
TIME_SKEW_SECONDS = 300


# ---------------------------------------------------------------------------
# Canonical message helpers (must byte-exactly match the issuer/verifier)
# ---------------------------------------------------------------------------


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
        signer_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(str(payload["signer_pubkey"])))
        signature = _b64url_decode(str(payload["signature"]))
    except Exception as exc:
        raise RuntimeError("trust_list_malformed") from exc

    message = _build_trust_list_signature_message(
        version=int(payload["version"]),
        content_hash=str(payload["content_hash"]),
        generated_at_unix=int(payload["generated_at_unix"]),
        valid_until_unix=int(payload["valid_until_unix"]),
    )
    try:
        signer_key.verify(signature, message)
    except InvalidSignature as exc:
        raise RuntimeError("trust_list_invalid_signature") from exc

    issuers: dict[str, TrustedIssuer] = {}
    for entry in normalized:
        valid_from = int(entry.get("valid_from_unix") or 0)
        valid_until = int(entry.get("valid_until_unix") or 0)
        if valid_from and (now + TIME_SKEW_SECONDS) < valid_from:
            continue
        if valid_until and (now - TIME_SKEW_SECONDS) > valid_until:
            continue
        existing = issuers.get(entry["did"])
        if existing:
            existing.pubkeys_hex.add(entry["pubkey"])
        else:
            issuers[entry["did"]] = TrustedIssuer(did=entry["did"], pubkeys_hex={entry["pubkey"]})

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
        require_session_assertion: bool = True,
    ) -> None:
        self.site_id = site_id
        self.lemma_origin = lemma_origin.rstrip("/")
        self.max_session_age_seconds = max_session_age_seconds
        self.refresh_seconds = refresh_seconds
        self.require_session_assertion = require_session_assertion
        self._lock = threading.Lock()
        self._snapshot: Optional[_Snapshot] = None

    def _fetch_signed_bundle(self) -> _Snapshot:
        url = f"{self.lemma_origin}/api/revocation/bloom-filter"
        with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310 — lemma.id only
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

        # Verify the issuer-signed snapshot envelope
        issuer_did = (snapshot.get("issuer_did") or "").strip()
        trusted = issuers.get(issuer_did)
        if not trusted:
            raise RuntimeError(f"bloom snapshot signed by untrusted issuer {issuer_did}")
        signature_hex = snapshot.get("signature") or ""
        try:
            signature = bytes.fromhex(signature_hex)
        except ValueError as exc:
            raise RuntimeError("bloom snapshot signature malformed") from exc

        envelope = {k: snapshot[k] for k in snapshot if k != "signature"}
        message = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
        verified = False
        for pubkey_hex in trusted.pubkeys_hex:
            try:
                Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex)).verify(signature, message)
                verified = True
                break
            except InvalidSignature:
                continue
        if not verified:
            raise RuntimeError("bloom snapshot signature did not verify")

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

        # 2. Claim-level checks: isHuman, site binding, expiry
        claims = credential.get("claims") or credential.get("credentialSubject") or {}
        if not claims.get("isHuman"):
            return self.Result(False, "not_ishuman")
        bound_site = (
            claims.get("siteId") or claims.get("site_id") or claims.get("siteDomain") or ""
        )
        if bound_site != self.site_id:
            return self.Result(False, "site_id_mismatch", bound_site_id=bound_site)
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
                Ed25519PublicKey.from_public_bytes(pubkey_bytes).verify(
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
            if str(assertion.get("site_id") or "") != self.site_id:
                return self.Result(False, "session_site_id_mismatch")
        elif self.require_session_assertion and site_pubkey_b64:
            return self.Result(False, "session_assertion_required")

        return self.Result(
            ok=True,
            reason="valid",
            ppid=credential.get("subject"),
            credential_id=credential_id or None,
            issuer_did=issuer_did,
            bound_site_id=bound_site,
        )

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
        to_verify = {"credential": presentation.get("credential")} if durable else presentation
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
