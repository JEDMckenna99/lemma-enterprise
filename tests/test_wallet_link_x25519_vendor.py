"""Static checks for self-contained X25519 vendor bundles used by /link QR flow."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "static" / "js" / "vendor"

VENDOR_FILES = (
    "noble-curves-ed25519.mjs",
    "noble-hashes-sha512.mjs",
    "noble-hashes-utils.mjs",
    "noble-hashes-crypto.mjs",
)


@pytest.mark.unit
@pytest.mark.parametrize("filename", VENDOR_FILES)
def test_x25519_vendor_files_exist(filename: str) -> None:
    path = VENDOR / filename
    assert path.is_file(), f"missing vendor file: {path}"


@pytest.mark.unit
def test_noble_curves_ed25519_uses_local_hash_imports() -> None:
    text = (VENDOR / "noble-curves-ed25519.mjs").read_text(encoding="utf-8")
    assert 'from"/npm/' not in text
    assert 'from"/npm/' not in text.replace("'", '"')
    assert "cdn.jsdelivr.net/npm/@noble/hashes" not in text
    assert "./noble-hashes-sha512.mjs" in text
    assert "./noble-hashes-utils.mjs" in text


@pytest.mark.unit
def test_noble_hashes_modules_use_local_crypto() -> None:
    for name in ("noble-hashes-sha512.mjs", "noble-hashes-utils.mjs"):
        text = (VENDOR / name).read_text(encoding="utf-8")
        assert 'from"/npm/' not in text
        assert 'import"/npm/' not in text
        assert "./noble-hashes-crypto.mjs" in text


@pytest.mark.unit
def test_lemma_keys_does_not_fallback_to_jsdelivr_curves() -> None:
    keys_js = (ROOT / "static" / "js" / "lemma-keys.js").read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net/npm/@noble/curves" not in keys_js
