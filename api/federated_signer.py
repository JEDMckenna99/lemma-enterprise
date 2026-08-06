"""Federated issuer signing — local (in-process) or remote (signing worker)."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Optional

from api.wallet_keys import b64url_encode, sign_message

logger = logging.getLogger(__name__)

_SIGNER: Optional["FederatedSigner"] = None


def use_remote_federated_signer() -> bool:
    return bool(os.getenv("LEMMA_SIGNING_SERVICE_URL", "").strip())


def is_signing_service_process() -> bool:
    return os.getenv("LEMMA_SIGNING_SERVICE", "").strip() == "1"


def _signing_service_url() -> str:
    return os.getenv("LEMMA_SIGNING_SERVICE_URL", "").strip().rstrip("/")


def _signing_service_token() -> str:
    return os.getenv("LEMMA_SIGNING_SERVICE_TOKEN", "").strip()


class FederatedSigner:
    """Sign with the federated network issuer without exposing seed on web dynos."""

    def get_did(self) -> str:
        raise NotImplementedError

    def get_public_key_hex(self) -> str:
        raise NotImplementedError

    def has_local_seed(self) -> bool:
        return False

    def sign_b64url(self, message: bytes) -> str:
        raise NotImplementedError

    def sign_digest_hex(self, digest: bytes) -> str:
        raise NotImplementedError

    def issue_credential(self, ppid: str, claims_for_issuer: dict[str, str]) -> dict[str, Any]:
        raise NotImplementedError

    def signing_material(self):
        """Return (private_key, public_key, did) — local process only."""
        raise RuntimeError("signing_material unavailable without local seed")


class LocalFederatedSigner(FederatedSigner):
    def __init__(self) -> None:
        from api.issuer_management import get_issuer_manager

        self._issuer = get_issuer_manager().get_federated_issuer()

    def has_local_seed(self) -> bool:
        return True

    def get_did(self) -> str:
        return self._issuer.get_did()

    def get_public_key_hex(self) -> str:
        return self._issuer.get_public_key_hex()

    def signing_material(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        seed = bytes(self._issuer.signing_key_bytes())
        if len(seed) != 32:
            raise ValueError("issuer signing seed must be 32 bytes")
        private_key = Ed25519PrivateKey.from_private_bytes(seed)
        public_key = private_key.public_key()
        return private_key, public_key, self.get_did()

    def sign_b64url(self, message: bytes) -> str:
        private_key, _, _ = self.signing_material()
        return b64url_encode(sign_message(private_key, message))

    def sign_digest_hex(self, digest: bytes) -> str:
        private_key, _, _ = self.signing_material()
        return private_key.sign(digest).hex()

    def issue_credential(self, ppid: str, claims_for_issuer: dict[str, str]) -> dict[str, Any]:
        import hashlib

        from api.ishuman import _browser_canonical_message

        credential_json = self._issuer.issue_credential(ppid, claims_for_issuer)
        credential = json.loads(credential_json)
        try:
            digest = hashlib.sha256(_browser_canonical_message(credential)).digest()
            proof = credential.setdefault("proof", {})
            proof["signatureValueWeb"] = self.sign_digest_hex(digest)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to add browser-format signature: %s", exc)
        return credential


class RemoteFederatedSigner(FederatedSigner):
    def __init__(self) -> None:
        self._base_url = _signing_service_url()
        self._token = _signing_service_token()
        if not self._base_url:
            raise RuntimeError("LEMMA_SIGNING_SERVICE_URL required for remote federated signer")
        if not self._token:
            raise RuntimeError("LEMMA_SIGNING_SERVICE_TOKEN required for remote federated signer")
        self._metadata: Optional[dict[str, str]] = None

    def _request(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(  # noqa: S310
            f"{self._base_url}{path}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"signing_service_{exc.code}:{detail}") from exc

    def _load_metadata(self) -> dict[str, str]:
        if self._metadata:
            return self._metadata
        data = self._request("/internal/issuer-info", {})
        if not data.get("success"):
            raise RuntimeError("signing_service_issuer_info_failed")
        self._metadata = {
            "did": str(data["issuer_did"]),
            "pubkey_hex": str(data["pubkey_hex"]).lower(),
        }
        return self._metadata

    def get_did(self) -> str:
        return self._load_metadata()["did"]

    def get_public_key_hex(self) -> str:
        return self._load_metadata()["pubkey_hex"]

    def sign_b64url(self, message: bytes) -> str:
        data = self._request(
            "/internal/sign",
            {
                "message_b64": base64.b64encode(message).decode("ascii"),
                "signature_format": "b64url",
            },
        )
        if not data.get("success"):
            raise RuntimeError("signing_service_sign_failed")
        return str(data["signature"])

    def sign_digest_hex(self, digest: bytes) -> str:
        data = self._request(
            "/internal/sign",
            {
                "message_b64": base64.b64encode(digest).decode("ascii"),
                "signature_format": "hex",
                "message_is_digest": True,
            },
        )
        if not data.get("success"):
            raise RuntimeError("signing_service_sign_failed")
        return str(data["signature"])

    def issue_credential(self, ppid: str, claims_for_issuer: dict[str, str]) -> dict[str, Any]:
        data = self._request(
            "/internal/issue-credential",
            {"ppid": ppid, "claims": claims_for_issuer},
        )
        if not data.get("success"):
            raise RuntimeError("signing_service_issue_failed")
        credential = data.get("credential")
        if not isinstance(credential, dict):
            raise RuntimeError("signing_service_issue_malformed")
        return credential


def get_federated_signer() -> FederatedSigner:
    global _SIGNER
    if _SIGNER is not None:
        return _SIGNER
    if use_remote_federated_signer() and not is_signing_service_process():
        _SIGNER = RemoteFederatedSigner()
    else:
        _SIGNER = LocalFederatedSigner()
    return _SIGNER


def reset_federated_signer_cache() -> None:
    global _SIGNER
    _SIGNER = None


def get_federated_issuer_metadata() -> dict[str, str]:
    """Return federated issuer DID + pubkey without loading seed on web dynos."""
    if use_remote_federated_signer() and not is_signing_service_process():
        signer = get_federated_signer()
        return {"did": signer.get_did(), "pubkey_hex": signer.get_public_key_hex()}

    from api.database import SessionLocal, Site

    db = SessionLocal()
    try:
        site = db.query(Site).filter_by(site_id="federated_network").first()
        if site and site.issuer_did and site.public_key_hex:
            return {"did": site.issuer_did, "pubkey_hex": site.public_key_hex.lower()}
    finally:
        db.close()

    signer = get_federated_signer()
    return {"did": signer.get_did(), "pubkey_hex": signer.get_public_key_hex()}
