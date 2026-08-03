"""
Public documentation allowlist for anonymous /docs/<path> serving.

Only explicitly approved relying-site markdown may be served without auth.
Everything else under docs/ remains in-repo for operators and developers
with repository access.
"""

from __future__ import annotations

import os
import posixpath
import re
from typing import FrozenSet, Optional, Tuple

# Approved public markdown paths (posix-style, relative to docs/).
PUBLIC_DOC_ALLOWLIST: FrozenSet[str] = frozenset(
    {
        "integration/ISHUMAN_AGENT_INTEGRATION.md",
        "integration/QUICK_START_SIMPLE_LOGIN.md",
        "integration/SIMPLE_INTEGRATION_GUIDE.md",
        "integration/SIGN_IN_TRUST_AND_RECOVERY.md",
        "integration/BROWSER_SUPPORT.md",
        "ERROR_CODES.md",
        "demo/README.md",
        "demo/PRESALE_DEMO_SCRIPT.md",
        "product/PASSKEY_STAMP_INPUT_BURN.md",
    }
)

_ENCODED_SEGMENT = re.compile(r"%[0-9A-Fa-f]{2}")


def _decode_path_segments(path: str) -> str:
    """Decode percent-encoded path segments once (e.g. %2e%2e -> ..)."""
    parts = path.split("/")
    decoded = []
    for part in parts:
        if _ENCODED_SEGMENT.search(part):
            try:
                from urllib.parse import unquote

                decoded.append(unquote(part))
            except Exception:
                decoded.append(part)
        else:
            decoded.append(part)
    return "/".join(decoded)


def normalize_public_doc_path(filename: str) -> Optional[str]:
    """
    Normalize a requested docs path to a safe posix relative path.

    Returns None when the path is invalid, attempts traversal, targets a
    non-markdown file, or uses disallowed prefixes.
    """
    if not filename or not isinstance(filename, str):
        return None

    raw = filename.replace("\\", "/").strip()
    if not raw:
        return None

    raw = _decode_path_segments(raw)

    # Reject absolute paths and drive letters.
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        return None

    # Collapse . and .. using posix semantics.
    normalized = posixpath.normpath(raw)
    if normalized in (".", ""):
        return None
    if normalized.startswith("../") or "/../" in f"/{normalized}/":
        return None

    # Block hidden files and alternate roots.
    segments = normalized.split("/")
    if any(seg in ("", ".", "..") for seg in segments):
        return None
    if any(seg.startswith(".") for seg in segments):
        return None

    lowered = normalized.lower()
    blocked_prefixes = (
        "operations/",
        "security/",
        "architecture/",
        "status/",
        "plans/",
        "research/",
        "openclaw/",
        "wallet/",
        "protocol/",
        "testing/",
        "cryptographic/",
    )
    if any(lowered.startswith(prefix) for prefix in blocked_prefixes):
        return None

    if not lowered.endswith(".md"):
        return None

    return normalized


def is_public_doc_allowed(filename: str) -> Tuple[bool, Optional[str]]:
    """
    Return (allowed, normalized_path).

    normalized_path is set when the path syntax is valid but may still be
    denied if it is not on the allowlist.
    """
    normalized = normalize_public_doc_path(filename)
    if normalized is None:
        return False, None
    return normalized in PUBLIC_DOC_ALLOWLIST, normalized


def resolve_public_doc_file(docs_root: str, normalized_path: str) -> Optional[str]:
    """
    Resolve an allowlisted path to a real file under docs_root.

    Uses realpath containment checks to block symlink escapes.
    """
    docs_root_real = os.path.realpath(docs_root)
    candidate = os.path.realpath(os.path.join(docs_root, normalized_path))
    if not candidate.startswith(docs_root_real + os.sep) and candidate != docs_root_real:
        return None
    if not os.path.isfile(candidate):
        return None
    return candidate
