#!/usr/bin/env python3
"""Validate the human-auth authority-operation contract against Flask routes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "docs" / "api" / "AUTHORITY_OPERATIONS_V1.json"
STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
REQUIRED_OPERATION_FIELDS = {
    "operation_id",
    "authority_class",
    "mutates",
    "routes",
    "current_auth",
    "required_auth",
    "required_scope",
    "site_binding",
    "risk_tier",
    "enforcement_layer",
    "compliance",
    "threat_tags",
    "checklist_sections",
    "test_refs",
}
AUTHORITY_CLASSES = {"wallet", "identity", "tenant", "billing", "recovery"}
RISK_TIERS = {"medium", "high", "critical"}
COMPLIANCE_VALUES = {"compliant", "gap", "review_required"}
ENFORCEMENT_LAYERS = {"decorator", "in_handler", "decorator_and_handler"}


def _load_contract() -> dict[str, Any]:
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("authority contract must be a JSON object")
    return payload


def _generated_routes() -> set[tuple[str, str, str]]:
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.generate_auth_scope_matrix import generate_matrix

    routes: set[tuple[str, str, str]] = set()
    for row in generate_matrix().get("routes", []):
        module = str(row.get("module") or "")
        path = str(row.get("path") or "")
        for method in row.get("methods") or []:
            routes.add((str(method).upper(), path, module))
    return routes


def _route_key(route: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(route.get("method") or "").upper(),
        str(route.get("path") or ""),
        str(route.get("module") or ""),
    )


def validate_contract(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    operations = payload.get("operations")
    exemptions = payload.get("exemptions")
    covered_modules = payload.get("covered_modules")

    if not isinstance(operations, list) or not operations:
        return ["operations must be a non-empty list"]
    if not isinstance(exemptions, list):
        errors.append("exemptions must be a list")
        exemptions = []
    if not isinstance(covered_modules, list) or not covered_modules:
        errors.append("covered_modules must be a non-empty list")
        covered_modules = []

    generated = _generated_routes()
    operation_ids: set[str] = set()
    declared_routes: set[tuple[str, str, str]] = set()

    for index, operation in enumerate(operations):
        label = f"operations[{index}]"
        if not isinstance(operation, dict):
            errors.append(f"{label} must be an object")
            continue

        missing = sorted(REQUIRED_OPERATION_FIELDS - set(operation))
        if missing:
            errors.append(f"{label} missing fields: {', '.join(missing)}")

        operation_id = str(operation.get("operation_id") or "")
        if not operation_id:
            errors.append(f"{label} operation_id is empty")
        elif operation_id in operation_ids:
            errors.append(f"duplicate operation_id: {operation_id}")
        operation_ids.add(operation_id)

        authority_class = operation.get("authority_class")
        if authority_class not in AUTHORITY_CLASSES:
            errors.append(f"{operation_id} has invalid authority_class: {authority_class}")
        if operation.get("risk_tier") not in RISK_TIERS:
            errors.append(f"{operation_id} has invalid risk_tier")
        if operation.get("compliance") not in COMPLIANCE_VALUES:
            errors.append(f"{operation_id} has invalid compliance")
        if operation.get("enforcement_layer") not in ENFORCEMENT_LAYERS:
            errors.append(f"{operation_id} has invalid enforcement_layer")

        for field in (
            "mutates",
            "current_auth",
            "required_auth",
            "site_binding",
            "threat_tags",
            "checklist_sections",
        ):
            if operation.get(field) in (None, "", []):
                errors.append(f"{operation_id} has empty {field}")

        routes = operation.get("routes")
        if not isinstance(routes, list) or not routes:
            errors.append(f"{operation_id} routes must be a non-empty list")
            continue

        for route in routes:
            if not isinstance(route, dict):
                errors.append(f"{operation_id} contains a non-object route")
                continue
            key = _route_key(route)
            if not all(key):
                errors.append(f"{operation_id} has an incomplete route declaration")
                continue
            if key in declared_routes:
                errors.append(f"duplicate route declaration: {key}")
            declared_routes.add(key)
            if key not in generated:
                errors.append(f"{operation_id} route does not exist in generated matrix: {key}")

    exemption_routes: set[tuple[str, str, str]] = set()
    for index, exemption in enumerate(exemptions):
        label = f"exemptions[{index}]"
        if not isinstance(exemption, dict):
            errors.append(f"{label} must be an object")
            continue
        key = _route_key(exemption)
        reason = str(exemption.get("reason") or "").strip()
        if not all(key) or not reason:
            errors.append(f"{label} requires method, path, module, and reason")
            continue
        if key in exemption_routes or key in declared_routes:
            errors.append(f"duplicate or conflicting exemption: {key}")
        exemption_routes.add(key)
        if key not in generated:
            errors.append(f"exempt route does not exist in generated matrix: {key}")

    covered = set(str(module) for module in covered_modules)
    expected = {
        route
        for route in generated
        if route[0] in STATE_CHANGING_METHODS and route[2] in covered
    }
    missing_routes = sorted(expected - declared_routes - exemption_routes)
    for method, path, module in missing_routes:
        errors.append(f"covered authority mutation is undeclared: {method} {path} ({module})")

    return errors


def main() -> int:
    payload = _load_contract()
    errors = validate_contract(payload)
    if errors:
        print("Authority-operation contract failed:")
        for error in errors:
            print(f" - {error}")
        return 1

    operations = payload["operations"]
    route_count = sum(len(operation["routes"]) for operation in operations)
    gaps = sum(operation["compliance"] == "gap" for operation in operations)
    print(
        "Authority-operation contract passed: "
        f"{len(operations)} operations, {route_count} routes, {gaps} declared gaps"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
