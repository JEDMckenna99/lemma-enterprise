from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC_SDK = ROOT / "static" / "js" / "lemma-wallet.js"
CDN_SDK = ROOT / "cdn" / "dist" / "js" / "lemma-wallet.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_version(source: str) -> str | None:
    match = re.search(r"static VERSION = '([^']+)'", source)
    return match.group(1) if match else None


def test_wallet_sdk_static_and_cdn_version_match():
    static_src = _read(STATIC_SDK)
    cdn_src = _read(CDN_SDK)

    assert _extract_version(static_src), "static wallet SDK version marker missing"
    assert _extract_version(cdn_src), "cdn wallet SDK version marker missing"
    assert _extract_version(static_src) == _extract_version(cdn_src)


def test_wallet_sdk_parity_keeps_critical_auth_symbols():
    static_src = _read(STATIC_SDK)
    cdn_src = _read(CDN_SDK)
    critical_symbols = [
        "_connectSessionSSE",
        "syncRevocations",
        "invalidateRevocationCache",
        "getAuthState",
    ]

    for symbol in critical_symbols:
        assert symbol in static_src, f"missing {symbol} in static SDK"
        assert symbol in cdn_src, f"missing {symbol} in CDN SDK"
