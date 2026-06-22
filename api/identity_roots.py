"""
Stripe Identity document-root and Lemma person-root derivation.

document_root = HMAC(pepper, canonical_json(verified document claims))
lemma_person_root = HKDF(document_root_hash, salt, info=person-root/v1)
site_ppid = HMAC(lemma_person_root, "lemma.id/site-ppid/v1" || canonical_site)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

DOCUMENT_ROOT_SCHEMA = "lemma.identity.document-root.v1"
DOCUMENT_ROOT_SCHEMA_V2 = "lemma.identity.document-root.v2"
PERSON_ROOT_VERSION = "v1"
PERSON_ROOT_HKDF_INFO = b"lemma.id/person-root/v1"
SITE_PPID_MSG_PREFIX = "lemma.id/site-ppid/v1"
PERSON_ROOT_SOURCE_DOCUMENT_DERIVED = "document_derived_v1"
PERSON_ROOT_SOURCE_ASSIGNED = "assigned_v1"


class IdentityRootError(Exception):
    """Base error for identity root derivation."""


class IdentityRootMaterialError(IdentityRootError):
    """Verified Stripe session missing required fields for document root."""


@dataclass(frozen=True)
class StripeIdentityRootMaterial:
    """Non-persistent view of Stripe fields needed for document-root v1."""

    country: str
    document_type: str
    document_number: str
    date_of_birth: str  # YYYY-MM-DD
    document_expiration_date: Optional[str] = None  # YYYY-MM-DD from IDV
    issuing_subdivision: Optional[str] = None  # ISO 3166-2 style, e.g. US-CA
    id_number_type: Optional[str] = None
    id_number_last4: Optional[str] = None
    stripe_session_id: Optional[str] = None
    stripe_report_id: Optional[str] = None


def active_root_version() -> str:
    """The pepper/salt version new IDVs derive under (Phase 3.1).

    Defaults to ``v1`` so existing deployments are unchanged. Operators rotate by
    provisioning ``LEMMA_IDENTITY_ROOT_PEPPER_<VER>`` + ``LEMMA_PERSON_ROOT_SALT_<VER>``
    and setting ``LEMMA_ACTIVE_ROOT_VERSION``.
    """
    return (os.environ.get("LEMMA_ACTIVE_ROOT_VERSION") or PERSON_ROOT_VERSION).strip()


def document_root_schema() -> str:
    """Claim-set schema for new document roots (v2 adds ``issuing_subdivision``).

    Env: ``LEMMA_DOCUMENT_ROOT_SCHEMA=v2`` (default) or ``v1`` for legacy bytes.
    """
    mode = (os.environ.get("LEMMA_DOCUMENT_ROOT_SCHEMA") or "v2").strip().lower()
    if mode in ("v1", "1", "legacy", "document_derived_v1"):
        return DOCUMENT_ROOT_SCHEMA
    return DOCUMENT_ROOT_SCHEMA_V2


def _is_v1(version: str) -> bool:
    return (version or "").strip().upper() == "V1"


def _get_identity_root_pepper(version: str | None = None, issuer: str | None = None) -> bytes:
    version = version or active_root_version()
    # Per-issuer pepper isolation (Phase 3.2 Option A). Applied only for
    # non-Stripe issuers and only when an issuer-namespaced pepper is explicitly
    # provisioned (>=32 bytes); otherwise we fall through to the shared
    # version-based resolution so dev and existing Stripe deploys are unchanged
    # and the pinned cryptographic invariants stay byte-stable.
    issuer_norm = (issuer or "").strip().lower()
    if issuer_norm and issuer_norm != "stripe_identity":
        ns_key = f"LEMMA_IDENTITY_ROOT_PEPPER_{issuer_norm.upper()}_{version.strip().upper()}"
        ns_val = os.environ.get(ns_key)
        if ns_val and len(ns_val) >= 32:
            return ns_val.encode("utf-8")
    # V1 preserves legacy resolution (api.config -> env -> dev default) so the
    # pinned cryptographic invariants stay byte-stable across this refactor.
    if _is_v1(version):
        try:
            from api.config import get_identity_root_pepper

            return get_identity_root_pepper().encode("utf-8")
        except Exception:
            key = os.environ.get("LEMMA_IDENTITY_ROOT_PEPPER_V1")
            if key and len(key) >= 32:
                return key.encode("utf-8")
            return b"lemma_dev_identity_root_pepper_change_me_32b"
    env_key = f"LEMMA_IDENTITY_ROOT_PEPPER_{version.strip().upper()}"
    val = os.environ.get(env_key)
    if not val or len(val) < 32:
        raise IdentityRootError(f"missing or short pepper: {env_key}")
    return val.encode("utf-8")


def _get_person_root_salt(version: str | None = None) -> bytes:
    version = version or active_root_version()
    if _is_v1(version):
        try:
            from api.config import get_person_root_salt

            return get_person_root_salt().encode("utf-8")
        except Exception:
            key = os.environ.get("LEMMA_PERSON_ROOT_SALT_V1")
            if key and len(key) >= 32:
                return key.encode("utf-8")
            return b"lemma_dev_person_root_salt_change_me_32bytes"
    env_key = f"LEMMA_PERSON_ROOT_SALT_{version.strip().upper()}"
    val = os.environ.get(env_key)
    if not val or len(val) < 32:
        raise IdentityRootError(f"missing or short salt: {env_key}")
    return val.encode("utf-8")


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    """Deterministic JSON encoding for HMAC inputs."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def normalize_country(value: str) -> str:
    code = (value or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", code):
        raise IdentityRootMaterialError("invalid issuing country")
    return code


def normalize_document_type(value: str) -> str:
    doc_type = (value or "").strip().lower()
    allowed = {"driving_license", "passport", "id_card"}
    if doc_type not in allowed:
        raise IdentityRootMaterialError(f"unsupported document_type: {doc_type!r}")
    return doc_type


def normalize_document_number(value: str) -> str:
    raw = (value or "").strip().upper()
    if not raw:
        raise IdentityRootMaterialError("document_number required")
    return re.sub(r"[\s\-]", "", raw)


def normalize_document_expiration_date(value: Any) -> Optional[str]:
    """Parse IDV document expiration to YYYY-MM-DD (returns None if absent/invalid)."""
    if value is None:
        return None
    if isinstance(value, dict):
        year = int(value.get("year") or 0)
        month = int(value.get("month") or 0)
        day = int(value.get("day") or 0)
        if year < 1900 or not (1 <= month <= 12) or not (1 <= day <= 31):
            return None
        return f"{year:04d}-{month:02d}-{day:02d}"
    raw = str(value).strip()
    if not raw:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return None
    year_s, month_s, day_s = raw.split("-")
    year, month, day = int(year_s), int(month_s), int(day_s)
    if year < 1900 or not (1 <= month <= 12) or not (1 <= day <= 31):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def document_expiration_end_of_day_utc(expiration_date: Optional[str]) -> Optional[datetime]:
    """End of the expiration calendar day (UTC) for master TTL binding."""
    normalized = normalize_document_expiration_date(expiration_date)
    if not normalized:
        return None
    year_s, month_s, day_s = normalized.split("-")
    return datetime(
        int(year_s),
        int(month_s),
        int(day_s),
        23,
        59,
        59,
        tzinfo=timezone.utc,
    ).replace(tzinfo=None)


def format_dob_from_stripe(dob: Any) -> str:
    if dob is None:
        raise IdentityRootMaterialError("date_of_birth required")
    if isinstance(dob, dict):
        year = int(dob.get("year") or 0)
        month = int(dob.get("month") or 0)
        day = int(dob.get("day") or 0)
    else:
        year = int(getattr(dob, "year", 0) or 0)
        month = int(getattr(dob, "month", 0) or 0)
        day = int(getattr(dob, "day", 0) or 0)
    if year < 1900 or not (1 <= month <= 12) or not (1 <= day <= 31):
        raise IdentityRootMaterialError("invalid date_of_birth")
    return f"{year:04d}-{month:02d}-{day:02d}"


def age_years_from_dob(date_of_birth: str, *, on: Optional[datetime] = None) -> int:
    """Whole years since ``date_of_birth`` (YYYY-MM-DD) for policy gates."""
    ref = on or datetime.utcnow()
    year, month, day = (int(part) for part in date_of_birth.split("-"))
    years = ref.year - year
    if (ref.month, ref.day) < (month, day):
        years -= 1
    return years


def build_document_root_claims(
    material: StripeIdentityRootMaterial,
    provider: str = "stripe_identity",
    *,
    schema: str | None = None,
) -> dict[str, Any]:
    """Build the canonical document-root claim set.

    ``provider`` is part of the signed claim set, so the same physical document
    verified through different IDV rails (e.g. ``stripe_identity`` vs ``didit``)
    derives a distinct document_root and therefore a distinct person_root/PPID
    (Phase 3.2 Option A: provider-namespaced identities). Defaults to
    ``stripe_identity`` so the pinned Stripe invariants stay byte-stable.

    Schema v2 adds ``issuing_subdivision`` when present (required for US/CA/AU
    driving licences) to avoid cross-jurisdiction document-number collisions.
    """
    from api.issuing_subdivision import requires_issuing_subdivision

    schema_id = schema or document_root_schema()
    country = normalize_country(material.country)
    document_type = normalize_document_type(material.document_type)
    claims: dict[str, Any] = {
        "schema": schema_id,
        "provider": provider,
        "country": country,
        "document_type": document_type,
        "document_number": normalize_document_number(material.document_number),
        "date_of_birth": material.date_of_birth,
    }
    if schema_id == DOCUMENT_ROOT_SCHEMA_V2:
        subdivision = (material.issuing_subdivision or "").strip().upper() or None
        if requires_issuing_subdivision(country, document_type):
            if not subdivision:
                raise IdentityRootMaterialError(
                    f"issuing_subdivision required for {country} {document_type}"
                )
            claims["issuing_subdivision"] = subdivision
        elif subdivision:
            claims["issuing_subdivision"] = subdivision
    if material.id_number_type:
        claims["id_number_type"] = str(material.id_number_type).strip().lower()
    if material.id_number_last4:
        claims["id_number_last4"] = re.sub(r"\D", "", str(material.id_number_last4))[-4:]
    return claims


def derive_document_root_hash(claims: dict[str, Any], version: str | None = None) -> str:
    pepper = _get_identity_root_pepper(version, issuer=claims.get("provider"))
    digest = hmac.new(pepper, canonical_json_bytes(claims), hashlib.sha256).hexdigest()
    return digest


def derive_person_root_bytes(document_root_hash: str, version: str | None = None) -> bytes:
    if not document_root_hash or len(document_root_hash) != 64:
        raise IdentityRootError("document_root_hash must be 64 hex chars")
    ikm = bytes.fromhex(document_root_hash)
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_get_person_root_salt(version),
        info=PERSON_ROOT_HKDF_INFO,
    ).derive(ikm)


def derive_person_root_hash(document_root_hash: str, version: str | None = None) -> str:
    return derive_person_root_bytes(document_root_hash, version).hex()


def generate_assigned_person_root_bytes() -> bytes:
    """Cryptographically random person_root for assigned_v1 identities."""
    return secrets.token_bytes(32)


def generate_assigned_person_root_hash() -> str:
    return generate_assigned_person_root_bytes().hex()


def _site_ppid_message(rp_id: str) -> bytes:
    from api.ppid import canonicalize_rp_id

    site = canonicalize_rp_id(rp_id)
    if not site or site == "unknown":
        raise ValueError("invalid site for person-root PPID")
    return f"{SITE_PPID_MSG_PREFIX}{site}".encode("utf-8")


def derive_ppid_from_person_root_bytes(person_root: bytes, rp_id: str) -> str:
    if len(person_root) != 32:
        raise ValueError("person_root must be 32 bytes")
    ppid = hmac.new(person_root, _site_ppid_message(rp_id), hashlib.sha256).hexdigest()
    return f"did:lemma:ppid_{ppid}"


def derive_ppid_from_document_root_hash(document_root_hash: str, rp_id: str, version: str | None = None) -> str:
    person_root = derive_person_root_bytes(document_root_hash, version)
    return derive_ppid_from_person_root_bytes(person_root, rp_id)


def extract_root_material_from_stripe_session(session: Any) -> StripeIdentityRootMaterial:
    """Parse a verified Stripe VerificationSession (expanded) into root material."""
    status = getattr(session, "status", None) or (session.get("status") if isinstance(session, dict) else None)
    if status != "verified":
        raise IdentityRootMaterialError("verification session not verified")

    verified = getattr(session, "verified_outputs", None)
    if verified is None and isinstance(session, dict):
        verified = session.get("verified_outputs")

    report = getattr(session, "last_verification_report", None)
    if report is None and isinstance(session, dict):
        report = session.get("last_verification_report")

    if not verified or not report:
        raise IdentityRootMaterialError("verified_outputs and last_verification_report required")

    dob = format_dob_from_stripe(getattr(verified, "dob", None) if not isinstance(verified, dict) else verified.get("dob"))

    document = getattr(report, "document", None)
    if document is None and isinstance(report, dict):
        document = report.get("document")
    if not document:
        raise IdentityRootMaterialError("document report required")

    def _doc_field(name: str) -> Any:
        if isinstance(document, dict):
            return document.get(name)
        return getattr(document, name, None)

    country = _doc_field("issuing_country") or getattr(verified, "address", None)
    if country is None and isinstance(verified, dict):
        addr = verified.get("address") or {}
        country = addr.get("country") if isinstance(addr, dict) else getattr(addr, "country", None)
    elif hasattr(country, "country"):
        country = country.country

    doc_number = _doc_field("number")
    doc_type = _doc_field("type")
    document_expiration_date = normalize_document_expiration_date(_doc_field("expiration_date"))
    from api.issuing_subdivision import extract_stripe_issuing_subdivision

    raw_country = str(country or "").strip()
    country_alpha2 = normalize_country(raw_country) if raw_country else ""
    issuing_subdivision = extract_stripe_issuing_subdivision(
        country_alpha2=country_alpha2,
        document=document,
        verified=verified,
    )

    id_number = getattr(verified, "id_number", None) if not isinstance(verified, dict) else verified.get("id_number")
    id_number_type = (
        getattr(verified, "id_number_type", None) if not isinstance(verified, dict) else verified.get("id_number_type")
    )

    session_id = getattr(session, "id", None) or (session.get("id") if isinstance(session, dict) else None)
    report_id = getattr(report, "id", None) if not isinstance(report, dict) else report.get("id")

    return StripeIdentityRootMaterial(
        country=country_alpha2 or raw_country,
        document_type=str(doc_type or ""),
        document_number=str(doc_number or ""),
        date_of_birth=dob,
        document_expiration_date=document_expiration_date,
        issuing_subdivision=issuing_subdivision,
        id_number_type=str(id_number_type) if id_number_type else None,
        id_number_last4=str(id_number)[-4:] if id_number else None,
        stripe_session_id=str(session_id) if session_id else None,
        stripe_report_id=str(report_id) if report_id else None,
    )


# ---------------------------------------------------------------------------
# Didit IDV rail (Phase 3.2 second issuer)
# ---------------------------------------------------------------------------

# Map didit's human-readable document_type labels onto Lemma's canonical enum
# ({driving_license, passport, id_card}). Unmapped types fail closed downstream
# via normalize_document_type.
_DIDIT_DOCTYPE_MAP = {
    "passport": "passport",
    "identity card": "id_card",
    "id card": "id_card",
    "national id": "id_card",
    "national identity card": "id_card",
    "id_card": "id_card",
    "driver's license": "driving_license",
    "drivers license": "driving_license",
    "driving license": "driving_license",
    "driving licence": "driving_license",
    "driver's licence": "driving_license",
    "driving_license": "driving_license",
}


def map_didit_document_type(value: str) -> str:
    key = (value or "").strip().lower()
    mapped = _DIDIT_DOCTYPE_MAP.get(key)
    if not mapped:
        raise IdentityRootMaterialError(f"unsupported didit document_type: {value!r}")
    return mapped


def map_didit_country(value: str) -> str:
    from api.iso_country_codes import alpha3_to_alpha2

    alpha2 = alpha3_to_alpha2(value)
    if not alpha2:
        raise IdentityRootMaterialError(f"unrecognized didit issuing country: {value!r}")
    return alpha2


def _normalize_didit_dob(value: Any) -> str:
    raw = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise IdentityRootMaterialError("didit date_of_birth must be YYYY-MM-DD")
    return raw


def _didit_feature_entry_approved(entry: Any) -> bool:
    return str((entry or {}).get("status", "")).strip().lower() == "approved"


def _require_approved_didit_feature_array(
    decision: dict[str, Any],
    key: str,
    label: str,
) -> None:
    """Fail closed unless at least one entry in a V3 plural feature array is Approved."""
    entries = decision.get(key)
    if not isinstance(entries, list) or not entries:
        raise IdentityRootMaterialError(f"didit decision missing {key}")
    if not any(_didit_feature_entry_approved(v) for v in entries):
        raise IdentityRootMaterialError(f"no approved didit {label}")


def validate_didit_workflow_id(workflow_id: Optional[str]) -> None:
    """Ensure the session used the configured proof-of-humanity Didit workflow."""
    from api.config import get_didit_workflow_id

    expected = (get_didit_workflow_id() or "").strip().lower()
    if not expected:
        return
    actual = (workflow_id or "").strip().lower()
    if actual != expected:
        raise IdentityRootMaterialError(
            f"didit workflow_id mismatch: expected {expected}, got {actual or '(missing)'}"
        )


def extract_root_material_from_didit_decision(decision: dict[str, Any]) -> StripeIdentityRootMaterial:
    """Parse a verified didit ``decision`` payload into document-root material.

    Requires approved entries in ``id_verifications[]``, ``liveness_checks[]``,
    and ``face_matches[]`` (the proof-of-humanity workflow). Maps didit's alpha-3
    issuing country and human-readable document type onto Lemma's canonical forms.
    Raises ``IdentityRootMaterialError`` when required fields are missing or any
    feature is not approved (fail closed).
    """
    if not isinstance(decision, dict):
        raise IdentityRootMaterialError("didit decision must be an object")

    _require_approved_didit_feature_array(decision, "id_verifications", "id_verification")
    _require_approved_didit_feature_array(decision, "liveness_checks", "liveness_check")
    _require_approved_didit_feature_array(decision, "face_matches", "face_match")

    id_verifications = decision.get("id_verifications") or []

    idv = next((v for v in id_verifications if _didit_feature_entry_approved(v)), None)
    if idv is None:
        raise IdentityRootMaterialError("no approved didit id_verification")

    country = map_didit_country(idv.get("issuing_country") or idv.get("issuing_state") or "")
    document_type = map_didit_document_type(idv.get("document_type") or "")
    from api.issuing_subdivision import extract_didit_issuing_subdivision

    issuing_subdivision = extract_didit_issuing_subdivision(idv, country)
    document_number = str(idv.get("document_number") or "")
    if not document_number:
        raise IdentityRootMaterialError("didit id_verification missing document_number")
    dob = _normalize_didit_dob(idv.get("date_of_birth"))
    document_expiration_date = normalize_document_expiration_date(idv.get("expiration_date"))

    return StripeIdentityRootMaterial(
        country=country,
        document_type=document_type,
        document_number=document_number,
        date_of_birth=dob,
        document_expiration_date=document_expiration_date,
        issuing_subdivision=issuing_subdivision,
        stripe_session_id=None,
        stripe_report_id=None,
    )


def document_root_hash_from_material(
    material: StripeIdentityRootMaterial,
    version: str | None = None,
    provider: str = "stripe_identity",
) -> str:
    claims = build_document_root_claims(material, provider)
    return derive_document_root_hash(claims, version)
