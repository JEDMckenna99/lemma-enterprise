"""Single source of truth for isHuman SDK versions (Section 10)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MANIFEST_PATH = _REPO_ROOT / "docs" / "sdk" / "ISHUMAN_SDK_VERSIONS.json"


@lru_cache(maxsize=1)
def load_sdk_manifest() -> dict:
    data = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("ISHUMAN_SDK_VERSIONS.json must be a JSON object")
    return data


def browser_verifier_version() -> str:
    return str(load_sdk_manifest().get("browser_verifier") or "1.9.2")


def backend_verifier_version() -> str:
    return str(load_sdk_manifest().get("backend_verifier") or "1.4.0")


def npm_package_version() -> str:
    return str(load_sdk_manifest().get("npm_package") or backend_verifier_version())


def pypi_package_version() -> str:
    return str(load_sdk_manifest().get("pypi_package") or backend_verifier_version())


def versioned_sdk_url(relative_path: str) -> str:
    """Return immutable versioned URL for a manifest asset key or path suffix."""
    manifest = load_sdk_manifest()
    base = str(manifest.get("immutable_base") or "/sdk/v").rstrip("/")
    rel = relative_path.lstrip("/")
    for asset in (manifest.get("assets") or {}).values():
        versioned = str(asset.get("versioned_url") or "")
        if versioned.endswith(rel) or rel in versioned:
            return versioned
    if rel.endswith("proof-verifier.js"):
        return f"{base}{browser_verifier_version()}/proof-verifier.js"
    if rel.endswith("lemma-ishuman-verify.mjs"):
        return f"{base}{backend_verifier_version()}/lemma-ishuman-verify.mjs"
    if rel.endswith("lemma_ishuman_verify.py"):
        return f"{base}{backend_verifier_version()}/lemma_ishuman_verify.py"
    return f"/sdk/{rel}"


# Backward-compatible alias used across the codebase for the browser SDK line.
ISHUMAN_VERIFIER_SDK_VERSION = browser_verifier_version()
