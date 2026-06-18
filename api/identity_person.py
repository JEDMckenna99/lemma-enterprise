"""
Persist and resolve LemmaPerson records from Stripe document roots.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Tuple

from api.identity_roots import (
    IdentityRootMaterialError,
    StripeIdentityRootMaterial,
    build_document_root_claims,
    derive_document_root_hash,
    derive_person_root_hash,
    document_root_hash_from_material,
    extract_root_material_from_stripe_session,
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
    stripe_session_id: Optional[str] = None
    stripe_report_id: Optional[str] = None
    document_country: Optional[str] = None
    document_type: Optional[str] = None
    merged_from_person_id: Optional[str] = None


def _new_person_id() -> str:
    return f"person_{secrets.token_urlsafe(16)}"


def resolve_or_create_person_from_material(
    db,
    *,
    material: StripeIdentityRootMaterial,
    wallet_id: Optional[str],
    provider: str = "stripe_identity",
    allow_wallet_person_merge: bool = False,
    merge_from_person_id: Optional[str] = None,
) -> ResolvedLemmaPerson:
    from api.database import LemmaDocumentRoot, LemmaPerson, LemmaWalletBinding

    from api.identity_roots import active_root_version

    root_version = active_root_version()
    claims = build_document_root_claims(material, provider)
    document_root_hash = derive_document_root_hash(claims, root_version)
    person_root_hash = derive_person_root_hash(document_root_hash, root_version)

    existing_link = db.query(LemmaDocumentRoot).filter_by(document_root_hash=document_root_hash).first()
    created_person = False
    created_document_link = False

    if existing_link:
        person = db.query(LemmaPerson).filter_by(person_id=existing_link.lemma_person_id).first()
        if not person:
            raise RuntimeError("document_root linked to missing lemma_person")
        person_id = person.person_id
    else:
        from api.column_crypto import encrypt_column

        person = LemmaPerson(
            person_id=_new_person_id(),
            person_root_hash=encrypt_column(person_root_hash),
            root_version=root_version,
            primary_wallet_id=wallet_id,
            status="active",
        )
        db.add(person)
        created_person = True
        person_id = person.person_id

        link = LemmaDocumentRoot(
            document_root_hash=document_root_hash,
            lemma_person_id=person_id,
            root_version=root_version,
            provider=provider,
            stripe_verification_session_id=material.stripe_session_id,
            stripe_verification_report_id=material.stripe_report_id,
            document_country=claims.get("country"),
            document_type=claims.get("document_type"),
            confidence_level=CONFIDENCE_DOCUMENT_ROOT_V1,
        )
        db.add(link)
        created_document_link = True

    merged_from_person_id: Optional[str] = None

    if wallet_id:
        binding = db.query(LemmaWalletBinding).filter_by(wallet_id=wallet_id).first()
        if not binding:
            db.add(
                LemmaWalletBinding(
                    wallet_id=wallet_id,
                    lemma_person_id=person_id,
                    binding_status="active",
                )
            )
        elif binding.lemma_person_id != person_id:
            if (
                allow_wallet_person_merge
                and merge_from_person_id
                and binding.lemma_person_id == merge_from_person_id
            ):
                merged_from_person_id = merge_from_person_id
                binding.lemma_person_id = person_id
                binding.updated_at = datetime.utcnow()
            else:
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
        stripe_session_id=material.stripe_session_id,
        stripe_report_id=material.stripe_report_id,
        document_country=claims.get("country"),
        document_type=claims.get("document_type"),
        merged_from_person_id=merged_from_person_id,
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
    """Resolve a LemmaPerson from a verified didit decision payload.

    Unlike the Stripe path there is no server-side re-fetch: the didit webhook
    already carries the (HMAC-authenticated) ``decision`` object, so we build
    root material directly from it. Raises IdentityRootMaterialError on
    missing/invalid fields (fail closed).
    """
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
        id_number_type=kwargs.get("id_number_type", "us_ssn"),
        id_number_last4=kwargs.get("id_number_last4", "1234"),
        stripe_session_id=kwargs.get("stripe_session_id"),
        stripe_report_id=kwargs.get("stripe_report_id"),
    )
