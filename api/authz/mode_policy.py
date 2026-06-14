from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping


MODE_COMPAT_BEARER = "compat_bearer"
MODE_COMPAT_PROOF_WRAPPED = "compat_proof_wrapped"
MODE_CREDENTIAL_REQUIRED = "credential_required"
MODE_PROOF_REQUIRED = "proof_required"

_MODE_ORDER = {
    MODE_COMPAT_BEARER: 0,
    MODE_COMPAT_PROOF_WRAPPED: 1,
    MODE_CREDENTIAL_REQUIRED: 2,
    MODE_PROOF_REQUIRED: 3,
}


@dataclass(frozen=True)
class ModeDecision:
    allowed: bool
    reason_code: str | None
    expected_mode: str
    effective_mode: str
    proof_present: bool
    bearer_present: bool


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_iso_utc(text: str | None) -> datetime | None:
    value = str(text or "").strip()
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _proof_present(headers: Mapping[str, str]) -> bool:
    return bool(
        (headers.get("X-Lemma-Proof") or "").strip()
        or (headers.get("X-Lemma-Proof-Ref") or "").strip()
    )


def _bearer_present(headers: Mapping[str, str]) -> bool:
    if (headers.get("X-Agent-Token") or "").strip():
        return True
    auth_header = (headers.get("Authorization") or "").strip()
    return auth_header.startswith("Bearer ")


def _credential_or_agent_present(headers: Mapping[str, str]) -> bool:
    if (headers.get("X-Lemma-Credential") or "").strip():
        return True
    if (headers.get("X-Agent-Token") or "").strip():
        return True
    token = (headers.get("X-Agent-Token") or "").strip()
    if token.startswith("lm_agent_"):
        return True
    return False


def evaluate_mode_policy(
    *,
    expected_mode: str,
    headers: Mapping[str, str],
    compat_sunset_utc: str | None = None,
) -> ModeDecision:
    proof_present = _proof_present(headers)
    bearer_present = _bearer_present(headers)
    effective_mode = MODE_COMPAT_BEARER
    if proof_present and bearer_present:
        effective_mode = MODE_COMPAT_PROOF_WRAPPED
    elif proof_present:
        effective_mode = MODE_PROOF_REQUIRED

    # Enforce required mode floor if caller provides one.
    requested_floor = str(headers.get("X-Lemma-Min-Mode") or "").strip().lower()
    if requested_floor in _MODE_ORDER and _MODE_ORDER.get(effective_mode, 0) < _MODE_ORDER[requested_floor]:
        return ModeDecision(
            allowed=False,
            reason_code="AUTH_MODE_DOWNGRADE",
            expected_mode=expected_mode,
            effective_mode=effective_mode,
            proof_present=proof_present,
            bearer_present=bearer_present,
        )

    if expected_mode == MODE_PROOF_REQUIRED and not proof_present:
        agent_token = (headers.get("X-Agent-Token") or "").strip()
        if agent_token.startswith("lm_agent_"):
            return ModeDecision(
                allowed=True,
                reason_code=None,
                expected_mode=expected_mode,
                effective_mode=MODE_CREDENTIAL_REQUIRED,
                proof_present=proof_present,
                bearer_present=bearer_present,
            )
        return ModeDecision(
            allowed=False,
            reason_code="AUTH_PROOF_REQUIRED",
            expected_mode=expected_mode,
            effective_mode=effective_mode,
            proof_present=proof_present,
            bearer_present=bearer_present,
        )

    if expected_mode == MODE_CREDENTIAL_REQUIRED and not _credential_or_agent_present(headers):
        return ModeDecision(
            allowed=False,
            reason_code="AUTH_CREDENTIAL_REQUIRED",
            expected_mode=expected_mode,
            effective_mode=effective_mode,
            proof_present=proof_present,
            bearer_present=bearer_present,
        )

    # Hard sunset for bearer compatibility.
    if expected_mode == MODE_COMPAT_BEARER:
        sunset = _parse_iso_utc(compat_sunset_utc or os.getenv("LEMMA_COMPAT_BEARER_SUNSET_UTC"))
        if sunset and datetime.now(timezone.utc) >= sunset:
            return ModeDecision(
                allowed=False,
                reason_code="AUTH_COMPAT_MODE_EXPIRED",
                expected_mode=expected_mode,
                effective_mode=effective_mode,
                proof_present=proof_present,
                bearer_present=bearer_present,
            )

    if _MODE_ORDER.get(effective_mode, 0) < _MODE_ORDER.get(expected_mode, 0):
        # Do not enforce downgrade for credential_required when lemma/agent present.
        if expected_mode == MODE_CREDENTIAL_REQUIRED and _credential_or_agent_present(headers):
            return ModeDecision(
                allowed=True,
                reason_code=None,
                expected_mode=expected_mode,
                effective_mode=MODE_CREDENTIAL_REQUIRED,
                proof_present=proof_present,
                bearer_present=bearer_present,
            )
        # Do not enforce by default for compat rollout unless explicit proof-required.
        if expected_mode == MODE_COMPAT_PROOF_WRAPPED and _bool_env("LEMMA_ENFORCE_COMPAT_PROOF_WRAPPED", default=False):
            return ModeDecision(
                allowed=False,
                reason_code="AUTH_MODE_DOWNGRADE",
                expected_mode=expected_mode,
                effective_mode=effective_mode,
                proof_present=proof_present,
                bearer_present=bearer_present,
            )

    return ModeDecision(
        allowed=True,
        reason_code=None,
        expected_mode=expected_mode,
        effective_mode=effective_mode,
        proof_present=proof_present,
        bearer_present=bearer_present,
    )

