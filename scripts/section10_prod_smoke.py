"""Section 10 production smoke: SDK productization signals on lemma.id."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ORIGIN = "https://lemma.id"
UA = "section10-prod-smoke/1.0"


def get(url: str) -> tuple[int, dict | str | bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as resp:
        raw = resp.read()
        text = raw.decode("utf-8", errors="replace")
        try:
            return resp.status, json.loads(text), dict(resp.headers)
        except json.JSONDecodeError:
            return resp.status, text, dict(resp.headers)


def main() -> int:
    from api.sdk_versions import backend_verifier_version, browser_verifier_version

    checks: list[tuple[str, bool, object]] = []
    browser_v = browser_verifier_version()
    backend_v = backend_verifier_version()

    try:
        code, body, headers = get(f"{ORIGIN}/api/sdk/versions")
        ok = (
            code == 200
            and isinstance(body, dict)
            and body.get("success") is True
            and body.get("manifest", {}).get("browser_verifier") == browser_v
        )
        checks.append(("sdk-versions-manifest", ok, body if isinstance(body, dict) else code))
    except Exception as exc:
        checks.append(("sdk-versions-manifest", False, str(exc)))

    try:
        code, text, headers = get(f"{ORIGIN}/sdk/v{browser_v}/proof-verifier.js")
        ok = (
            code == 200
            and isinstance(text, str)
            and "ProofVerifier" in text
            and headers.get("X-SDK-Version") == browser_v
            and "immutable" in (headers.get("Cache-Control") or "")
        )
        checks.append(("versioned-browser-sdk", ok, {"version": browser_v, "cache": headers.get("Cache-Control")}))
    except Exception as exc:
        checks.append(("versioned-browser-sdk", False, str(exc)))

    try:
        code, text, headers = get(f"{ORIGIN}/sdk/v{backend_v}/lemma-ishuman-verify.mjs")
        ok = (
            code == 200
            and isinstance(text, str)
            and "createVerifier" in text
            and headers.get("X-SDK-Version") == backend_v
        )
        checks.append(("versioned-backend-sdk", ok, {"version": backend_v}))
    except Exception as exc:
        checks.append(("versioned-backend-sdk", False, str(exc)))

    try:
        code, body, _headers = get(f"{ORIGIN}/api/sdk/integrity")
        files = body.get("files") if isinstance(body, dict) else {}
        ok = (
            code == 200
            and isinstance(files, dict)
            and "proof-verifier.js" in files
            and "lemma-ishuman-verify.mjs" in files
        )
        checks.append(("sri-includes-ishuman-assets", ok, list(files.keys()) if isinstance(files, dict) else body))
    except Exception as exc:
        checks.append(("sri-includes-ishuman-assets", False, str(exc)))

    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "sync_ishuman_verify_packages",
            REPO_ROOT / "scripts/sync_ishuman_verify_packages.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        checks.append(("package-mirror-sync", mod.sync(check_only=True), {}))
    except Exception as exc:
        checks.append(("package-mirror-sync", False, str(exc)))

    passed = sum(1 for _, ok, _ in checks if ok)
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}\t{name}\t{detail}")
    print(f"\nsection10_prod_smoke: {passed}/{len(checks)} passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
