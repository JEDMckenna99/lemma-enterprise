"""
Canonical action taxonomy for agent containment.

Every credential, firewall check, and delegation chain references this registry.
Actions are organized by category, each with a risk tier and minimum scope.
"""

from __future__ import annotations

import fnmatch
from typing import Any

TAXONOMY: dict[str, dict[str, str]] = {
    # File system
    "file.read":    {"risk": "low",      "scope": "read",  "description": "Read files"},
    "file.write":   {"risk": "high",     "scope": "write", "description": "Write/modify files"},
    "file.delete":  {"risk": "critical", "scope": "admin", "description": "Delete files"},
    "file.list":    {"risk": "low",      "scope": "read",  "description": "List directory contents"},

    # Shell
    "shell.exec":           {"risk": "critical", "scope": "admin", "description": "Execute shell commands"},
    "shell.exec.sandboxed": {"risk": "high",     "scope": "write", "description": "Execute in sandbox"},

    # API calls
    "api.call.read":   {"risk": "low",      "scope": "read",  "description": "GET API requests"},
    "api.call.write":  {"risk": "high",     "scope": "write", "description": "POST/PUT/PATCH API requests"},
    "api.call.admin":  {"risk": "critical", "scope": "admin", "description": "Admin API endpoints"},

    # Browser
    "browser.read":     {"risk": "low",  "scope": "read",  "description": "View pages, screenshots"},
    "browser.interact": {"risk": "high", "scope": "write", "description": "Click, type, fill forms"},

    # Network
    "net.egress.internal": {"risk": "high",     "scope": "write", "description": "Internal network calls"},
    "net.egress.external": {"risk": "critical", "scope": "admin", "description": "External network calls"},

    # Secrets
    "secret.read":   {"risk": "critical", "scope": "admin", "description": "Read secrets/env vars"},
    "secret.write":  {"risk": "critical", "scope": "admin", "description": "Write/rotate secrets"},

    # Deploy
    "deploy.staging":    {"risk": "high",     "scope": "write", "description": "Deploy to staging"},
    "deploy.production": {"risk": "critical", "scope": "admin", "description": "Deploy to production"},
    "deploy.rollback":   {"risk": "critical", "scope": "admin", "description": "Rollback deployment"},

    # Ingest (content that might be injection vectors)
    "ingest.internal":     {"risk": "low",  "scope": "read", "description": "Read internal docs/code"},
    "ingest.external":     {"risk": "high", "scope": "read", "description": "Read external content"},
    "ingest.user_content": {"risk": "high", "scope": "read", "description": "Read user-submitted content"},

    # Database
    "db.query.read":  {"risk": "low",      "scope": "read",  "description": "SELECT queries"},
    "db.query.write": {"risk": "high",     "scope": "write", "description": "INSERT/UPDATE/DELETE"},
    "db.migrate":     {"risk": "critical", "scope": "admin", "description": "Schema migrations"},
}

RISK_ORDER = {"low": 0, "high": 1, "critical": 2}
SCOPE_HIERARCHY = {"read": 0, "write": 1, "admin": 2}


def is_valid_action(action: str) -> bool:
    return action in TAXONOMY


def risk_for_action(action: str) -> str:
    entry = TAXONOMY.get(action)
    return entry["risk"] if entry else "critical"


def scope_for_action(action: str) -> str:
    entry = TAXONOMY.get(action)
    return entry["scope"] if entry else "admin"


def actions_for_scope(scope: str) -> list[str]:
    """Return all actions that require at most the given scope level."""
    max_level = SCOPE_HIERARCHY.get(scope, 0)
    return sorted(
        a for a, meta in TAXONOMY.items()
        if SCOPE_HIERARCHY.get(meta["scope"], 99) <= max_level
    )


def actions_for_risk(max_risk: str) -> list[str]:
    """Return all actions at or below the given risk tier."""
    max_level = RISK_ORDER.get(max_risk, 0)
    return sorted(
        a for a, meta in TAXONOMY.items()
        if RISK_ORDER.get(meta["risk"], 99) <= max_level
    )


def _path_matches(path: str, pattern: str) -> bool:
    """Check if a path matches a glob pattern."""
    if pattern == "**" or pattern == "/*":
        return True
    return fnmatch.fnmatch(path, pattern)


def check_action_granted(
    actions_map: dict[str, Any] | None,
    action: str,
    resource_path: str | None = None,
) -> tuple[bool, str]:
    """Check if an action is granted in the actions map.

    Returns (allowed, reason).
    """
    if actions_map is None:
        return True, "no_actions_constraint"

    grant = actions_map.get(action)
    if grant is None:
        return False, "action_not_granted"

    if grant is True or grant == "true":
        return True, "action_granted"

    if isinstance(grant, dict):
        paths = grant.get("paths")
        if paths and resource_path:
            if not any(_path_matches(resource_path, p) for p in paths):
                return False, "action_path_not_allowed"

        commands = grant.get("commands")
        if commands and resource_path:
            if resource_path not in commands:
                return False, "action_command_not_allowed"

        return True, "action_granted_with_bounds"

    return True, "action_granted"


def is_actions_subset(child: dict[str, Any], parent: dict[str, Any]) -> tuple[bool, str | None]:
    """Verify that child's actions are a subset of parent's (monotonic attenuation).

    Returns (is_subset, first_violation_action).
    """
    for action, child_grant in child.items():
        parent_grant = parent.get(action)
        if parent_grant is None:
            return False, action

        if parent_grant is True or parent_grant == "true":
            continue

        if child_grant is True or child_grant == "true":
            if isinstance(parent_grant, dict) and parent_grant.get("paths"):
                return False, action
            continue

        if isinstance(child_grant, dict) and isinstance(parent_grant, dict):
            child_paths = set(child_grant.get("paths") or [])
            parent_paths = set(parent_grant.get("paths") or [])
            if child_paths and parent_paths:
                for cp in child_paths:
                    if not any(_path_matches(cp, pp) for pp in parent_paths):
                        return False, action

            child_cmds = set(child_grant.get("commands") or [])
            parent_cmds = set(parent_grant.get("commands") or [])
            if child_cmds and parent_cmds:
                if not child_cmds.issubset(parent_cmds):
                    return False, action

    return True, None


def build_default_actions(scope: list[str] | str, paths: list[str] | None = None) -> dict[str, Any]:
    """Build a default actions map from scope list, optionally with path bounds."""
    if isinstance(scope, str):
        scope = [s.strip() for s in scope.split(",") if s.strip()]
    granted = actions_for_scope(max(scope, key=lambda s: SCOPE_HIERARCHY.get(s, 0)) if scope else "read")
    actions: dict[str, Any] = {}
    for action in granted:
        if paths:
            actions[action] = {"paths": list(paths)}
        else:
            actions[action] = True
    return actions
