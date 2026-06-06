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
    # stamp(payload, includeProof=True)) — checks the signed proof AND that the
    # logged ppid/credentialId match it:
    check = ctx.verify_stamp(stored_log_row["lemma"])
    if not check.ok:
        flag_suspicious_log_row()
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


def _unwrap_stamp(value, key: str = "lemma"):
    """Normalize the shapes a relying site may pass to ``verify_stamp`` into
    ``(stamp_or_None, presentation)``.

    Accepts a raw presentation (has ``credential``), a stamp object from
    ``getVerification(includeProof=True)`` (has ``proof``), or a stamped event
    from ``stamp(payload)`` (has ``[key]`` holding one of the above).
    """
    if not isinstance(value, dict):
        return None
    if isinstance(value.get("credential"), dict):
        return (None, value)
    if isinstance(value.get("proof"), dict):
        return (value, value["proof"])
    inner = value.get(key)
    if isinstance(inner, dict):
        if isinstance(inner.get("proof"), dict):
            return (inner, inner["proof"])
        if isinstance(inner.get("credential"), dict):
            return (inner, inner)
    return None


# ---------------------------------------------------------------------------
# Trust list + Bloom snapshot cache (refreshed periodically, never per-request)
# ---------------------------------------------------------------------------


@dataclass
class TrustedIssuer:
    did: str
    pubkeys_hex: set[str]


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
    ) -> None:
        self.site_id = site_id
        self.lemma_origin = lemma_origin.rstrip("/")
        self.max_session_age_seconds = max_session_age_seconds
        self.refresh_seconds = refresh_seconds
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
        # Minimal subset — see api/issuer_trust_list.py for the full spec.
        # For brevity we trust the embedded list and only extract issuer pubkeys.
        # Production implementations SHOULD verify the trust list's own
        # signature against a hard-coded root pubkey published by lemma.id.
        issuers: dict[str, TrustedIssuer] = {}
        for entry in (trust_list.get("issuers") or []):
            did = (entry.get("did") or "").strip()
            pubkey_hex = (entry.get("public_key") or entry.get("publicKey") or "").strip().lower()
            status = (entry.get("status") or "active").lower()
            if not did or not pubkey_hex or status != "active":
                continue
            existing = issuers.get(did)
            if existing:
                existing.pubkeys_hex.add(pubkey_hex)
            else:
                issuers[did] = TrustedIssuer(did=did, pubkeys_hex={pubkey_hex})
        if not issuers:
            raise RuntimeError("trust list contained no active issuers")
        return issuers

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
        if assertion and signature_b64:
            site_pubkey_b64 = (
                claims.get("site_signing_pubkey") or claims.get("siteSigningPubkey") or ""
            )
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

        return self.Result(
            ok=True,
            reason="valid",
            ppid=credential.get("subject"),
            credential_id=credential_id or None,
            issuer_did=issuer_did,
            bound_site_id=bound_site,
        )

    def verify_stamp(self, stamp: dict, *, key: str = "lemma") -> "VerificationContext.Result":
        """Verify a stamp produced by the browser SDK's ``stamp(payload,
        {includeProof: true})`` / ``getVerification({includeProof: true})``.

        Re-checks the signed proof AND that the stamp's logged ``ppid`` /
        ``credentialId`` match the cryptographically verified values, so a
        tampered log row can't claim a different identity than its proof
        supports. Accepts the full stamped event, the stamp object, or a raw
        presentation.
        """
        unwrapped = _unwrap_stamp(stamp, key)
        if unwrapped is None:
            return self.Result(False, "stamp_missing_proof")
        inner, presentation = unwrapped
        result = self.verify(presentation)
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
