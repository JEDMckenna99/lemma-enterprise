"""
Persist and resolve LemmaPerson records from Stripe document roots.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from api.identity_roots import (
    IdentityRootMaterialError,
    PERSON_ROOT_SOURCE_ASSIGNED,
    PERSON_ROOT_SOURCE_DOCUMENT_DERIVED,
    StripeIdentityRootMaterial,
    build_document_root_claims,
    derive_document_root_hash,
    derive_person_root_hash,
    extract_root_material_from_stripe_session,
    generate_assigned_person_root_hash,
)

logger = logging.getLogger(__name__)

CONFIDENCE_DOCUMENT_ROOT_V1 = "document_root_v1"


class WalletPersonBindingConflictError(ValueError):
    """Raised when a wallet is already bound to a different LemmaPerson."""


@dataclass
class ResolvedLemmaPerson:
    person_id: str
    document_root_hash: str
    person_root_hash: str
    created_person: bool
    created_document_link: bool
    confidence_level: str
    person_root_source: str = PERSON_ROOT_SOURCE_DOCUMENT_DERIVED
    stripe_session_id: Optional[str] = None
    stripe_report_id: Optional[str] = None
    document_country: Optional[str] = None
    document_type: Optional[str] = None
    document_expiration_date: Optional[str] = None
    issuing_subdivision: Optional[str] = None
    merged_from_person_id: Optional[str] = None
    document_attached: bool = False


def _new_person_id() -> str:
    return f"person_{secrets.token_urlsafe(16)}"


def _load_person_root_hash_hex(person) -> str:
    from api.column_crypto import decrypt_column

    return decrypt_column(person.person_root_hash)


def _add_document_link(
    db,
    *,
    document_root_hash: str,
    person_id: str,
    root_version: str,
    provider: str,
    material: StripeIdentityRootMaterial,
    claims: dict,
) -> None:
    from api.column_crypto import encrypt_column
    from api.database import LemmaDocumentRoot
    from api.privacy_hashes import hash_provider_identifier

    subdivision = claims.get("issuing_subdivision") or material.issuing_subdivision
    provider_session_hash = hash_provider_identifier(
        provider,
        material.stripe_session_id,
        label="session",
    )
    provider_report_hash = hash_provider_identifier(
        provider,
        material.stripe_report_id,
        label="report",
    )

    db.add(
        LemmaDocumentRoot(
            document_root_hash=document_root_hash,
            lemma_person_id=person_id,
            root_version=root_version,
            provider=provider,
            stripe_verification_session_id=None,
            stripe_verification_report_id=None,
            provider_session_id_hash=provider_session_hash,
            provider_report_id_hash=provider_report_hash,
            document_country=encrypt_column(claims.get("country")) if claims.get("country") else None,
            document_type=encrypt_column(claims.get("document_type")) if claims.get("document_type") else None,
            issuing_subdivision=encrypt_column(subdivision) if subdivision else None,
            document_expiration_date=encrypt_column(material.document_expiration_date)
            if material.document_expiration_date
            else None,
            date_of_birth=encrypt_column(material.date_of_birth) if material.date_of_birth else None,
            document_root_schema=claims.get("schema"),
            confidence_level=CONFIDENCE_DOCUMENT_ROOT_V1,
        )
    )


def resolve_or_create_person_from_material(
    db,
    *,
    material: StripeIdentityRootMaterial,
    wallet_id: Optional[str],
    provider: str = "stripe_identity",
    allow_wallet_person_merge: bool = False,
    merge_from_person_id: Optional[str] = None,
) -> ResolvedLemmaPerson:
    """Resolve or create a LemmaPerson for verified IDV material.

    Document roots are renewable attestations. When a wallet is already bound,
    a new document links to the **existing** person (same person_root / PPIDs)
    instead of minting a new person from the new document hash.

    With ``LEMMA_PERSON_ROOT_SOURCE=assigned_v1``, first-time IDV assigns a random
    person_root; otherwise person_root = HKDF(document_root) (legacy).
    """
    from api.config import use_assigned_person_root
    from api.database import LemmaDocumentRoot, LemmaPerson, LemmaWalletBinding
    from api.identity_roots import active_root_version

    from api.column_crypto import encrypt_column

    root_version = active_root_version()
    claims = build_document_root_claims(material, provider)
    document_root_hash = derive_document_root_hash(claims, root_version)

    existing_link = (
        db.query(LemmaDocumentRoot).filter_by(document_root_hash=document_root_hash).first()
    )
    doc_person_id = existing_link.lemma_person_id if existing_link else None

    binding = (
        db.query(LemmaWalletBinding).filter_by(wallet_id=wallet_id).first()
        if wallet_id
        else None
    )
    bound_person_id = binding.lemma_person_id if binding else None

    if doc_person_id and bound_person_id and doc_person_id != bound_person_id:
        raise WalletPersonBindingConflictError(
            f"wallet {wallet_id} bound to {bound_person_id}; "
            f"document maps to {doc_person_id}"
        )

    created_person = False
    created_document_link = False
    document_attached = False
    merged_from_person_id: Optional[str] = None

    if doc_person_id:
        person = db.query(LemmaPerson).filter_by(person_id=doc_person_id).first()
        if not person:
            raise RuntimeError("document_root linked to missing lemma_person")
        person_id = person.person_id
        person_root_hash = _load_person_root_hash_hex(person)
        person_root_source = person.person_root_source or PERSON_ROOT_SOURCE_DOCUMENT_DERIVED
    elif bound_person_id:
        # New document for an already-bound wallet: attach attestation, keep person_root.
        person = db.query(LemmaPerson).filter_by(person_id=bound_person_id).first()
        if not person:
            raise RuntimeError("wallet binding references missing lemma_person")
        person_id = person.person_id
        person_root_hash = _load_person_root_hash_hex(person)
        person_root_source = person.person_root_source or PERSON_ROOT_SOURCE_DOCUMENT_DERIVED
        _add_document_link(
            db,
            document_root_hash=document_root_hash,
            person_id=person_id,
            root_version=root_version,
            provider=provider,
            material=material,
            claims=claims,
        )
        created_document_link = True
        document_attached = True
        logger.info(
            "Attached new document_root to bound person wallet=%s person=%s",
            (wallet_id or "")[:24],
            person_id[:24],
        )
    else:
        if use_assigned_person_root():
            person_root_hash = generate_assigned_person_root_hash()
            person_root_source = PERSON_ROOT_SOURCE_ASSIGNED
        else:
            person_root_hash = derive_person_root_hash(document_root_hash, root_version)
            person_root_source = PERSON_ROOT_SOURCE_DOCUMENT_DERIVED

        person = LemmaPerson(
            person_id=_new_person_id(),
            person_root_hash=encrypt_column(person_root_hash),
            root_version=root_version,
            person_root_source=person_root_source,
            primary_wallet_id=wallet_id,
            status="active",
        )
        db.add(person)
        created_person = True
        person_id = person.person_id
        _add_document_link(
            db,
            document_root_hash=document_root_hash,
            person_id=person_id,
            root_version=root_version,
            provider=provider,
            material=material,
            claims=claims,
        )
        created_document_link = True

    if wallet_id:
        if not binding:
            db.add(
                LemmaWalletBinding(
                    wallet_id=wallet_id,
                    lemma_person_id=person_id,
                    binding_status="active",
                )
            )
        elif binding.lemma_person_id != person_id:
            raise WalletPersonBindingConflictError(
                f"wallet {wallet_id} already bound to {binding.lemma_person_id}; "
                f"verified document maps to {person_id}"
            )

    return ResolvedLemmaPerson(
        person_id=person_id,
        document_root_hash=document_root_hash,
        person_root_hash=person_root_hash,
        created_person=created_person,
        created_document_link=created_document_link,
        confidence_level=CONFIDENCE_DOCUMENT_ROOT_V1,
        person_root_source=person_root_source,
        stripe_session_id=material.stripe_session_id,
        stripe_report_id=material.stripe_report_id,
        document_country=claims.get("country"),
        document_type=claims.get("document_type"),
        document_expiration_date=material.document_expiration_date,
        issuing_subdivision=material.issuing_subdivision,
        merged_from_person_id=merged_from_person_id,
        document_attached=document_attached,
    )


def resolve_person_from_stripe_session(
    db,
    *,
    stripe_session: Any,
    wallet_id: Optional[str],
) -> ResolvedLemmaPerson:
    material = extract_root_material_from_stripe_session(stripe_session)
    return resolve_or_create_person_from_material(db, material=material, wallet_id=wallet_id)


def load_person_root_bytes(db, lemma_person_id: str) -> bytes:
    from api.database import LemmaPerson

    from api.column_crypto import decrypt_column

    person = db.query(LemmaPerson).filter_by(person_id=lemma_person_id).first()
    if not person or not person.person_root_hash:
        raise ValueError("lemma_person not found")
    return bytes.fromhex(decrypt_column(person.person_root_hash))


def process_verified_stripe_identity(
    db,
    *,
    stripe_session_id: str,
    wallet_id: Optional[str],
) -> Tuple[ResolvedLemmaPerson, Optional[Any]]:
    """
    Retrieve Stripe session with sensitive expansions, resolve LemmaPerson.

    Returns (resolved, stripe_session) or raises IdentityRootMaterialError.
    """
    from billing.stripe_manager import StripeManager

    mgr = StripeManager()
    session = mgr.retrieve_identity_root_material(stripe_session_id)
    if session is None:
        raise IdentityRootMaterialError("could not retrieve stripe identity session")

    resolved = resolve_person_from_stripe_session(db, stripe_session=session, wallet_id=wallet_id)
    return resolved, session


def process_verified_didit_identity(
    db,
    *,
    decision: dict,
    wallet_id: Optional[str],
    allow_wallet_person_merge: bool = False,
    merge_from_person_id: Optional[str] = None,
) -> ResolvedLemmaPerson:
    """Resolve a LemmaPerson from a verified didit decision payload."""
    from api.identity_roots import extract_root_material_from_didit_decision

    material = extract_root_material_from_didit_decision(decision)
    return resolve_or_create_person_from_material(
        db,
        material=material,
        wallet_id=wallet_id,
        provider="didit",
        allow_wallet_person_merge=allow_wallet_person_merge,
        merge_from_person_id=merge_from_person_id,
    )


def material_from_test_fixture(**kwargs) -> StripeIdentityRootMaterial:
    """Build root material for unit tests without Stripe API."""
    return StripeIdentityRootMaterial(
        country=kwargs.get("country", "US"),
        document_type=kwargs.get("document_type", "passport"),
        document_number=kwargs.get("document_number", "X12345678"),
        date_of_birth=kwargs.get("date_of_birth", "1990-01-15"),
        document_expiration_date=kwargs.get("document_expiration_date"),
        issuing_subdivision=kwargs.get("issuing_subdivision"),
        id_number_type=kwargs.get("id_number_type", "us_ssn"),
        id_number_last4=kwargs.get("id_number_last4", "1234"),
        stripe_session_id=kwargs.get("stripe_session_id"),
        stripe_report_id=kwargs.get("stripe_report_id"),
    )


def load_latest_person_idv_attributes(db, lemma_person_id: str) -> Optional[dict]:
    """Latest active document row for age/state policy gates (no re-IDV)."""
    from api.column_crypto import decrypt_column
    from api.database import LemmaDocumentRoot
    from api.identity_roots import age_years_from_dob

    row = (
        db.query(LemmaDocumentRoot)
        .filter_by(lemma_person_id=lemma_person_id)
        .filter(LemmaDocumentRoot.revoked_at.is_(None))
        .order_by(LemmaDocumentRoot.created_at.desc())
        .first()
    )
    if not row:
        return None
    dob = decrypt_column(row.date_of_birth) if row.date_of_birth else None
    country = decrypt_column(row.document_country) if row.document_country else None
    doc_type = decrypt_column(row.document_type) if row.document_type else None
    subdivision = decrypt_column(row.issuing_subdivision) if row.issuing_subdivision else None
    expiration = (
        decrypt_column(row.document_expiration_date) if row.document_expiration_date else None
    )
    return {
        "document_country": country,
        "document_type": doc_type,
        "issuing_subdivision": subdivision,
        "document_expiration_date": expiration,
        "date_of_birth": dob,
        "age_years": age_years_from_dob(dob) if dob else None,
        "document_root_schema": row.document_root_schema,
    }


def document_expiration_date_for_person(db, lemma_person_id: Optional[str]) -> Optional[str]:
    """Latest document expiration for a person (encrypted column, decrypted)."""
    if not lemma_person_id:
        return None
    attrs = load_latest_person_idv_attributes(db, lemma_person_id)
    if not attrs:
        return None
    return attrs.get("document_expiration_date")
