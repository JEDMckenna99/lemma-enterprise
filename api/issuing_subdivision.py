"""Normalize issuing state/province/subdivision for document-root v2."""

from __future__ import annotations

import re
from typing import Any, Optional

# ISO 3166-2 style: ``US-CA``, ``CA-ON``, ``AU-QLD``.
_SUBDIVISION_CODE = re.compile(r"^[A-Z]{2}-[A-Z0-9]{1,3}$")

_US_NAME_TO_CODE: dict[str, str] = {
    "ALABAMA": "AL",
    "ALASKA": "AK",
    "ARIZONA": "AZ",
    "ARKANSAS": "AR",
    "CALIFORNIA": "CA",
    "COLORADO": "CO",
    "CONNECTICUT": "CT",
    "DELAWARE": "DE",
    "DISTRICT_OF_COLUMBIA": "DC",
    "WASHINGTON_DC": "DC",
    "FLORIDA": "FL",
    "GEORGIA": "GA",
    "HAWAII": "HI",
    "IDAHO": "ID",
    "ILLINOIS": "IL",
    "INDIANA": "IN",
    "IOWA": "IA",
    "KANSAS": "KS",
    "KENTUCKY": "KY",
    "LOUISIANA": "LA",
    "MAINE": "ME",
    "MARYLAND": "MD",
    "MASSACHUSETTS": "MA",
    "MICHIGAN": "MI",
    "MINNESOTA": "MN",
    "MISSISSIPPI": "MS",
    "MISSOURI": "MO",
    "MONTANA": "MT",
    "NEBRASKA": "NE",
    "NEVADA": "NV",
    "NEW_HAMPSHIRE": "NH",
    "NEW_JERSEY": "NJ",
    "NEW_MEXICO": "NM",
    "NEW_YORK": "NY",
    "NORTH_CAROLINA": "NC",
    "NORTH_DAKOTA": "ND",
    "OHIO": "OH",
    "OKLAHOMA": "OK",
    "OREGON": "OR",
    "PENNSYLVANIA": "PA",
    "RHODE_ISLAND": "RI",
    "SOUTH_CAROLINA": "SC",
    "SOUTH_DAKOTA": "SD",
    "TENNESSEE": "TN",
    "TEXAS": "TX",
    "UTAH": "UT",
    "VERMONT": "VT",
    "VIRGINIA": "VA",
    "WASHINGTON": "WA",
    "WEST_VIRGINIA": "WV",
    "WISCONSIN": "WI",
    "WYOMING": "WY",
}

_CA_NAME_TO_CODE: dict[str, str] = {
    "ALBERTA": "AB",
    "BRITISH_COLUMBIA": "BC",
    "MANITOBA": "MB",
    "NEW_BRUNSWICK": "NB",
    "NEWFOUNDLAND_AND_LABRADOR": "NL",
    "NEWFOUNDLAND": "NL",
    "NORTHWEST_TERRITORIES": "NT",
    "NOVA_SCOTIA": "NS",
    "NUNAVUT": "NU",
    "ONTARIO": "ON",
    "PRINCE_EDWARD_ISLAND": "PE",
    "QUEBEC": "QC",
    "SASKATCHEWAN": "SK",
    "YUKON": "YT",
}

_AU_NAME_TO_CODE: dict[str, str] = {
    "AUSTRALIAN_CAPITAL_TERRITORY": "ACT",
    "NEW_SOUTH_WALES": "NSW",
    "NORTHERN_TERRITORY": "NT",
    "QUEENSLAND": "QLD",
    "SOUTH_AUSTRALIA": "SA",
    "TASMANIA": "TAS",
    "VICTORIA": "VIC",
    "WESTERN_AUSTRALIA": "WA",
}

# Driving licences in these countries need a subdivision in document-root v2.
SUBDIVISION_REQUIRED_COUNTRIES = frozenset({"US", "CA", "AU"})


def normalize_issuing_subdivision(country_alpha2: str, raw: str) -> Optional[str]:
    """Return ``CC-SS`` subdivision code or None when unparseable."""
    country = (country_alpha2 or "").strip().upper()
    text = (raw or "").strip()
    if not country or not text:
        return None

    if _SUBDIVISION_CODE.fullmatch(text.upper()):
        prefix, suffix = text.upper().split("-", 1)
        if prefix == country:
            return f"{prefix}-{suffix}"

    compact = re.sub(r"[^A-Za-z0-9]", "_", text).strip("_").upper()
    if not compact:
        return None

    if country == "US":
        if len(compact) == 2 and compact in set(_US_NAME_TO_CODE.values()):
            return f"US-{compact}"
        for name, code in sorted(_US_NAME_TO_CODE.items(), key=lambda item: -len(item[0])):
            if compact == name or compact.startswith(name + "_"):
                return f"US-{code}"

    if country == "CA":
        if len(compact) == 2 and compact in set(_CA_NAME_TO_CODE.values()):
            return f"CA-{compact}"
        for name, code in sorted(_CA_NAME_TO_CODE.items(), key=lambda item: -len(item[0])):
            if compact == name or compact.startswith(name + "_"):
                return f"CA-{code}"

    if country == "AU":
        if compact in set(_AU_NAME_TO_CODE.values()):
            return f"AU-{compact}"
        for name, code in sorted(_AU_NAME_TO_CODE.items(), key=lambda item: -len(item[0])):
            if compact == name or compact.startswith(name + "_"):
                return f"AU-{code}"

    return None


def subdivision_from_document_subtype(country_alpha2: str, document_subtype: Optional[str]) -> Optional[str]:
    subtype = (document_subtype or "").strip()
    if not subtype:
        return None
    compact = re.sub(r"[^A-Za-z0-9]", "_", subtype).strip("_").upper()
    return normalize_issuing_subdivision(country_alpha2, compact)


def extract_didit_issuing_subdivision(idv: dict[str, Any], country_alpha2: str) -> Optional[str]:
    """Best-effort subdivision from a didit ``id_verifications[]`` entry."""
    from_subtype = subdivision_from_document_subtype(country_alpha2, idv.get("document_subtype"))
    if from_subtype:
        return from_subtype

    parsed = idv.get("parsed_address") or {}
    region = parsed.get("region")
    if region:
        normalized = normalize_issuing_subdivision(country_alpha2, str(region))
        if normalized:
            return normalized

    extra = idv.get("extra_fields") or {}
    for key in ("state", "province", "region", "issuing_state_code"):
        value = extra.get(key)
        if value:
            normalized = normalize_issuing_subdivision(country_alpha2, str(value))
            if normalized:
                return normalized

    return None


def extract_stripe_issuing_subdivision(
    *,
    country_alpha2: str,
    document: Any,
    verified: Any,
) -> Optional[str]:
    """Best-effort subdivision from Stripe Identity verified outputs."""

    def _read(obj: Any, key: str) -> Any:
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    for source in (document, verified):
        for key in ("issuing_authority", "state", "region", "jurisdiction"):
            value = _read(source, key)
            if value:
                normalized = normalize_issuing_subdivision(country_alpha2, str(value))
                if normalized:
                    return normalized

    address = _read(verified, "address")
    for key in ("state", "region"):
        value = _read(address, key)
        if value:
            normalized = normalize_issuing_subdivision(country_alpha2, str(value))
            if normalized:
                return normalized

    return None


def requires_issuing_subdivision(country_alpha2: str, document_type: str) -> bool:
    country = (country_alpha2 or "").strip().upper()
    doc_type = (document_type or "").strip().lower()
    return country in SUBDIVISION_REQUIRED_COUNTRIES and doc_type == "driving_license"
