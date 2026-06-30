from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Sequence
from urllib.parse import urlparse


@dataclass(frozen=True)
class ProofDecision:
    allowed: bool
    reason_code: str
    profile: str
    proof_id: str | None = None
    root_grant_id: str | None = None
    policy_version: str | None = None


def _decode_proof(raw_value: str) -> dict | None:
    text = (raw_value or "").strip()
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        try:
            return datetime.fromtimestamp(float(text), tz=timezone.utc)
        except ValueError:
            return None


def _host_from_base_url(base_url: str | None) -> str:
    text = str(base_url or "").strip()
    if not text:
        return ""
    try:
        parsed = urlparse(text)
        return (parsed.hostname or "").lower()
    except ValueError:
        return ""


def _scope_norm(scope_value) -> list[str]:
    scope = scope_value or []
    if isinstance(scope, str):
        scope = [part.strip() for part in scope.split(",") if part.strip()]
    return [str(item).strip().lower() for item in scope if str(item).strip()]


def _normalize_root_type(value) -> str:
    root_type = str(value or "").strip().lower()
    if root_type in {"passkey_root", "workload_root", "policy_root"}:
        return root_type
    return "passkey_root"


def _is_supported_profile(version_text: str) -> bool:
    value = (version_text or "").strip().lower()
    return value in {"v2", "authz_profile_v2"} or value.startswith("authz_profile_v2")


def _validate_known_keys(payload: dict, allowed_keys: set[str]) -> bool:
    for key in payload.keys():
        text = str(key).strip()
        if not text:
            return False
        if text.startswith("critical_") and text not in allowed_keys:
            return False
    return True


def _path_bound_subset(child: Sequence[str], parent: Sequence[str]) -> bool:
    parent_vals = [str(item).strip() for item in parent if str(item).strip()]
    if not parent_vals:
        return False
    for entry in child:
        candidate = str(entry).strip()
        if not candidate:
            return False
        ok = False
        for parent_entry in parent_vals:
            if parent_entry.endswith("**"):
                parent_prefix = parent_entry[:-2]
                if candidate.startswith(parent_prefix):
                    ok = True
                    break
            if candidate == parent_entry:
                ok = True
                break
        if not ok:
            return False
    return True


def _resource_bounds_subset(child_bounds: dict, parent_bounds: dict) -> bool:
    for scope_key, child_entries in child_bounds.items():
        parent_entries = parent_bounds.get(scope_key)
        if not isinstance(parent_entries, list):
            return False
        if not isinstance(child_entries, list):
            return False
        if not _path_bound_subset(child_entries, parent_entries):
            return False
    return True


def _validate_chain_signatures(root_proof: dict, delegated_proof: dict) -> bool:
    try:
        from api.trusted_issuers import verify_credential_with_trust
    except ImportError:
        # If verifier is unavailable, fail closed for proof-native chain verification.
        return False
    root_result = verify_credential_with_trust(root_proof)
    delegated_result = verify_credential_with_trust(delegated_proof)
    return bool((root_result or {}).get("valid")) and bool((delegated_result or {}).get("valid"))


def _extract_chain_links(proof: dict) -> list[dict]:
    chain = proof.get("proof_chain")
    if isinstance(chain, list):
        links = [item for item in chain if isinstance(item, dict)]
        if len(links) >= 2:
            return links
    root_proof = proof.get("root_proof")
    delegated_proof = proof.get("delegated_proof")
    if isinstance(root_proof, dict) and isinstance(delegated_proof, dict):
        return [root_proof, delegated_proof]
    if isinstance(proof, dict):
        return [proof]
    return []


def _proof_ref(link: dict) -> str:
    return str(link.get("proof_id") or link.get("id") or "").strip()


def evaluate_proof_native(
    *,
    headers: Mapping[str, str],
    method: str,
    path: str,
    required_scope: str | None = None,
    base_url: str | None = None,
    profile: str = "authz_profile_v2",
    revoked_proof_ids: set[str] | None = None,
    revoked_root_grant_ids: set[str] | None = None,
    min_revocation_epoch: int | None = None,
) -> ProofDecision:
    raw = (headers.get("X-Lemma-Proof") or "").strip()
    if not raw:
        return ProofDecision(allowed=False, reason_code="AUTH_PROOF_REQUIRED", profile=profile)
    proof = _decode_proof(raw)
    if not proof:
        return ProofDecision(allowed=False, reason_code="AUTH_CHAIN_BROKEN", profile=profile)

    allowed_top_level = {
        "version",
        "policy_version",
        "root_type",
        "proof_chain",
        "root_proof",
        "delegated_proof",
        "proof_id",
        "root_grant_id",
        "scope",
        "resource_bounds",
        "aud",
        "method",
        "path",
        "issued_at",
        "expires_at",
        "revocation_epoch",
        "delegation_depth",
        "agent_key_id",
        "agent_public_key",
        "agent_key_alg",
        "acting_for_ppid",
        "requested_by_ppid",
    }
    if not _validate_known_keys(proof, allowed_top_level):
        return ProofDecision(allowed=False, reason_code="AUTH_CHAIN_BROKEN", profile=profile)

    proof_id = str(proof.get("proof_id") or "").strip() or None
    root_grant_id = str(proof.get("root_grant_id") or "").strip() or None
    root_type = _normalize_root_type(proof.get("root_type"))
    policy_version = str(proof.get("policy_version") or proof.get("version") or "").strip() or None
    if policy_version and not _is_supported_profile(policy_version):
        return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)

    links = _extract_chain_links(proof)
    if not links:
        return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)
    root_proof = links[0]
    delegated_proof = links[-1]

    allowed_link_keys = {
        "proof_id",
        "parent_proof_id",
        "root_type",
        "root_grant_id",
        "subject_ppid",
        "acting_for_ppid",
        "requested_by_ppid",
        "scope",
        "resource_bounds",
        "aud",
        "method",
        "path",
        "issued_at",
        "expires_at",
        "revocation_epoch",
        "delegation_depth",
        "agent_key_id",
        "agent_public_key",
        "agent_key_alg",
        "issuer",
        "subject",
        "claims",
        "proof",
        "credentialSubject",
        "id",
    }
    for link in links:
        if not _validate_known_keys(link, allowed_link_keys):
            return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)

    max_depth = max(1, int(os.getenv("LEMMA_MAX_DELEGATION_DEPTH", "3") or "3"))
    for idx, link in enumerate(links):
        depth_raw = link.get("delegation_depth", idx)
        try:
            depth = int(depth_raw)
        except (TypeError, ValueError):
            return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)
        if depth != idx or depth > max_depth:
            return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)
        if idx == 0:
            continue
        parent = links[idx - 1]
        parent_id = _proof_ref(parent)
        parent_ref = str(link.get("parent_proof_id") or "").strip()
        if parent_id and parent_ref and parent_ref != parent_id:
            return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)
        parent_scope = _scope_norm(parent.get("scope") or (parent.get("claims") or {}).get("scope"))
        child_scope = _scope_norm(link.get("scope") or (link.get("claims") or {}).get("scope"))
        if parent_scope and child_scope and not set(child_scope).issubset(set(parent_scope)):
            return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)
        parent_bounds = parent.get("resource_bounds") or (parent.get("claims") or {}).get("resource_bounds") or {}
        child_bounds = link.get("resource_bounds") or (link.get("claims") or {}).get("resource_bounds") or {}
        if child_bounds:
            if not isinstance(parent_bounds, dict) or not isinstance(child_bounds, dict):
                return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)
            if not _resource_bounds_subset(child_bounds, parent_bounds):
                return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)
        # Actions attenuation: child actions must be subset of parent
        parent_actions = parent.get("actions")
        child_actions = link.get("actions")
        if parent_actions and child_actions:
            if isinstance(parent_actions, str):
                try:
                    parent_actions = json.loads(parent_actions)
                except (ValueError, TypeError):
                    parent_actions = None
            if isinstance(child_actions, str):
                try:
                    child_actions = json.loads(child_actions)
                except (ValueError, TypeError):
                    child_actions = None
            if parent_actions and child_actions and isinstance(parent_actions, dict) and isinstance(child_actions, dict):
                try:
                    from api.action_taxonomy import is_actions_subset
                    subset_ok, violation = is_actions_subset(child_actions, parent_actions)
                    if not subset_ok:
                        return ProofDecision(
                            allowed=False,
                            reason_code="AUTH_CHAIN_BROKEN",
                            profile=profile,
                            proof_id=link.get("proof_id"),
                            root_grant_id=link.get("root_grant_id"),
                        )
                except ImportError:
                    pass
        parent_issued = _parse_time(parent.get("issued_at") or (parent.get("claims") or {}).get("issued_at"))
        child_issued = _parse_time(link.get("issued_at") or (link.get("claims") or {}).get("issued_at"))
        parent_exp = _parse_time(parent.get("expires_at") or (parent.get("claims") or {}).get("expires_at"))
        child_exp = _parse_time(link.get("expires_at") or (link.get("claims") or {}).get("expires_at"))
        if parent_issued and child_issued and child_issued < parent_issued:
            return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)
        if parent_exp and child_exp and child_exp > parent_exp:
            return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)

    root_id = _proof_ref(root_proof)
    root_rg = str(root_proof.get("root_grant_id") or "").strip()
    delegated_rg = str(delegated_proof.get("root_grant_id") or "").strip()
    if root_rg and delegated_rg and root_rg != delegated_rg:
        return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)
    if root_rg and not root_grant_id:
        root_grant_id = root_rg
    root_root_type = _normalize_root_type(root_proof.get("root_type"))
    delegated_root_type = _normalize_root_type(delegated_proof.get("root_type"))
    if root_root_type != delegated_root_type:
        return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)
    root_type = root_root_type
    if not proof_id:
        proof_id = _proof_ref(delegated_proof) or None

    root_ppid = str(
        root_proof.get("subject_ppid")
        or (root_proof.get("claims") or {}).get("subject_ppid")
        or root_proof.get("subject")
        or ""
    ).strip()
    delegated_ppid = str(
        delegated_proof.get("acting_for_ppid")
        or (delegated_proof.get("claims") or {}).get("acting_for_ppid")
        or ""
    ).strip()
    if root_type == "passkey_root" and root_ppid and delegated_ppid and root_ppid != delegated_ppid:
        return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)
    top_key_id = str(proof.get("agent_key_id") or "").strip()
    delegated_key_id = str(
        delegated_proof.get("agent_key_id")
        or (delegated_proof.get("claims") or {}).get("agent_key_id")
        or ""
    ).strip()
    if top_key_id and delegated_key_id and top_key_id != delegated_key_id:
        return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)
    delegated_public_key = str(
        delegated_proof.get("agent_public_key")
        or (delegated_proof.get("claims") or {}).get("agent_public_key")
        or ""
    ).strip()
    top_public_key = str(proof.get("agent_public_key") or "").strip()
    if top_public_key and delegated_public_key and top_public_key != delegated_public_key:
        return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)

    # SECURITY: Every proof link must pass cryptographic trust verification,
    # including the single-link (degenerate) case. Previously this only ran for
    # chains of >= 2 links, so a single-link proof passed structural checks with
    # no signature/trust verification at all — letting an attacker craft a JSON
    # proof that satisfied proof_required routes without any valid issuer
    # signature. Legitimate proofs always carry a root + delegated chain; a
    # single link that cannot be anchored to a trusted issuer fails closed.
    if links:
        try:
            from api.trusted_issuers import verify_credential_with_trust
        except ImportError:
            return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)
        for link in links:
            verify_result = verify_credential_with_trust(link)
            if not bool((verify_result or {}).get("valid")):
                return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)

    if revoked_root_grant_ids and root_grant_id and root_grant_id in revoked_root_grant_ids:
        return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)
    if revoked_proof_ids:
        for link in links:
            link_ref = _proof_ref(link)
            if link_ref and link_ref in revoked_proof_ids:
                return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)
            ancestors = link.get("ancestor_ids") if isinstance(link.get("ancestor_ids"), list) else []
            for ancestor in ancestors:
                ancestor_ref = str(ancestor or "").strip()
                if ancestor_ref and ancestor_ref in revoked_proof_ids:
                    return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)
    if min_revocation_epoch is not None:
        rev_epoch_value = delegated_proof.get("revocation_epoch", proof.get("revocation_epoch", 0))
        try:
            rev_epoch = int(rev_epoch_value)
        except (TypeError, ValueError):
            rev_epoch = 0
        if rev_epoch < int(min_revocation_epoch):
            return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)

    proof_claims = delegated_proof.get("claims") if isinstance(delegated_proof.get("claims"), dict) else {}
    claim_method = str(proof.get("method") or "").strip().upper()
    claim_path = str(proof.get("path") or "").strip()
    if not claim_method:
        claim_method = str(delegated_proof.get("method") or proof_claims.get("method") or "").strip().upper()
    if not claim_path:
        claim_path = str(delegated_proof.get("path") or proof_claims.get("path") or "").strip()
    if claim_method and claim_method != str(method).upper():
        return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)
    if claim_path and claim_path != str(path):
        return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)
    issued_at = _parse_time(proof.get("issued_at") or delegated_proof.get("issued_at") or proof_claims.get("issued_at"))
    expires_at = _parse_time(proof.get("expires_at") or delegated_proof.get("expires_at") or proof_claims.get("expires_at"))
    now = _now()
    if issued_at and issued_at > now:
        return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)
    if expires_at and expires_at <= now:
        return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)

    scope_norm = _scope_norm(proof.get("scope") or delegated_proof.get("scope") or proof_claims.get("scope"))
    if required_scope and str(required_scope).strip().lower() not in scope_norm:
        return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)

    # Optional audience binding to reduce accidental cross-domain proof reuse.
    proof_aud = str(proof.get("aud") or delegated_proof.get("aud") or proof_claims.get("aud") or "").strip().lower()
    expected_host = _host_from_base_url(base_url)
    if proof_aud and expected_host and proof_aud not in {expected_host, str(base_url).strip().lower()}:
        return ProofDecision(False, "AUTH_CHAIN_BROKEN", profile, proof_id, root_grant_id, policy_version)

    return ProofDecision(True, "OK", profile, proof_id, root_grant_id, policy_version)

