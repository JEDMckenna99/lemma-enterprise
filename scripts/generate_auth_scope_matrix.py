#!/usr/bin/env python3
"""
Generate an initial auth scope matrix from route decorators in api/.

Output:
  docs/AUTH_SCOPE_MATRIX_V1.json
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPO_ROOT / "api"
OUTPUT_PATH = REPO_ROOT / "docs" / "AUTH_SCOPE_MATRIX_V1.json"


# Decorator names mapped to a default required scope.
DEFAULT_SCOPE_BY_DECORATOR = {
    "require_site_admin": "admin",
    "require_admin": "admin",
    "require_customer_or_admin": "read",
    "require_wallet_ppid": "read",
    "require_authenticated": "read",
    "require_api_key": "api_key",
    "validate_api_key": "api_key",
}


def _is_auth_decorator(name: str) -> bool:
    return (
        name.startswith("require_")
        or name in {"optional_auth", "validate_api_key"}
    )


def _const_value(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    return None


def _decorator_name_and_scope(dec: ast.AST) -> tuple[str | None, str | None]:
    if isinstance(dec, ast.Name):
        name = dec.id
        return name, DEFAULT_SCOPE_BY_DECORATOR.get(name)

    if isinstance(dec, ast.Call):
        if isinstance(dec.func, ast.Name):
            name = dec.func.id
        elif isinstance(dec.func, ast.Attribute):
            name = dec.func.attr
        else:
            return None, None

        if name == "require_agent_or_user_auth":
            for kw in dec.keywords:
                if kw.arg == "required_scope":
                    val = _const_value(kw.value)
                    if isinstance(val, str) and val:
                        return name, val.strip().lower()
            return name, "read"

        return name, DEFAULT_SCOPE_BY_DECORATOR.get(name)

    return None, None


def _route_meta(dec: ast.AST) -> tuple[str | None, list[str] | None]:
    if not isinstance(dec, ast.Call):
        return None, None
    if not isinstance(dec.func, ast.Attribute):
        return None, None
    if dec.func.attr != "route":
        return None, None

    route_path = None
    methods: list[str] | None = None

    if dec.args:
        first = _const_value(dec.args[0])
        if isinstance(first, str):
            route_path = first

    for kw in dec.keywords:
        if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
            parsed = []
            for elt in kw.value.elts:
                val = _const_value(elt)
                if isinstance(val, str):
                    parsed.append(val.upper())
            if parsed:
                methods = parsed

    if methods is None:
        methods = ["GET"]

    return route_path, methods


def _classify_auth_mode(decorators: list[str], scope: str | None) -> str:
    if "require_api_key" in decorators or "validate_api_key" in decorators:
        return "api_key"
    if "require_site_admin" in decorators or "require_admin" in decorators:
        return "admin_controlled"
    if "require_customer_or_admin" in decorators:
        return "customer_or_admin"
    if "require_wallet_ppid" in decorators:
        return "wallet_or_api_key"
    if "require_agent_or_user_auth" in decorators:
        return "agent_or_user"
    if scope == "public":
        return "public"
    return "custom_or_internal"


def _derive_required_scope(route_path: str, methods: list[str], scope_hint: str | None, decorators: list[str]) -> str:
    if scope_hint:
        return scope_hint
    if "require_site_admin" in decorators or "require_admin" in decorators:
        return "admin"
    if "require_customer_or_admin" in decorators or "require_wallet_ppid" in decorators:
        return "read"
    if "require_api_key" in decorators or "validate_api_key" in decorators:
        return "api_key"
    if route_path.startswith("/api/admin/"):
        return "admin"
    if any(m in {"POST", "PUT", "PATCH", "DELETE"} for m in methods):
        return "write"
    return "public"


def generate_matrix() -> dict[str, Any]:
    routes = []

    for py_file in sorted(API_DIR.rglob("*.py")):
        rel = py_file.relative_to(REPO_ROOT).as_posix()
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))

        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue

            route_path = None
            methods = None
            auth_decorators: list[str] = []
            decorator_chain: list[str] = []
            scope_hints: list[str] = []

            for dec in node.decorator_list:
                path, mth = _route_meta(dec)
                if path:
                    route_path = path
                    methods = mth
                    continue

                name, scope = _decorator_name_and_scope(dec)
                if name:
                    decorator_chain.append(name)
                    if _is_auth_decorator(name):
                        auth_decorators.append(name)
                if scope:
                    scope_hints.append(scope)

            if not route_path or not route_path.startswith("/api/"):
                continue

            required_scope = _derive_required_scope(
                route_path=route_path,
                methods=methods or ["GET"],
                scope_hint=scope_hints[0] if scope_hints else None,
                decorators=auth_decorators,
            )

            routes.append(
                {
                    "path": route_path,
                    "methods": methods or ["GET"],
                    "module": rel,
                    "handler": node.name,
                    "required_scope": required_scope,
                    "auth_mode": _classify_auth_mode(auth_decorators, required_scope),
                    "auth_decorators": auth_decorators,
                    "decorator_chain": decorator_chain,
                }
            )

    routes.sort(key=lambda r: (r["path"], ",".join(r["methods"]), r["module"]))
    return {
        "version": "1.0.0",
        "generated_by": "scripts/generate_auth_scope_matrix.py",
        "description": "Initial scope map inferred from route decorators; review required before enforcement.",
        "routes": routes,
    }


def main() -> int:
    matrix = generate_matrix()
    OUTPUT_PATH.write_text(json.dumps(matrix, indent=2), encoding="utf-8")
    print(f"Wrote scope matrix: {OUTPUT_PATH}")
    print(f"Routes: {len(matrix['routes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

