#!/usr/bin/env python3
"""Section 4 production end-to-end trust-chain drill on live lemma.id."""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from unittest.mock import patch

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from api.issuer_trust_list import verify_signed_trust_list  # noqa: E402
from api.bloom_snapshot import verify_bloom_snapshot, verify_snapshot_matches_payload  # noqa: E402
from api.ishuman import _browser_canonical_message, _assurance_meets_policy  # noqa: E402
from scripts.ishuman_prod_test_wallet import (  # noqa: E402
    prod_test_target_site,
    prod_test_wallet_id,
    require_prod_test_secret,
)
from scripts.run_ishuman_prod_revocation_smoke import (  # noqa: E402
    _derive_assertion,
    _load_fixture_site_ppid,
    _load_site_api_key,
    _resolve_canonical_site_ppid,
    _run_heroku,
    _step,
)


BASE = os.getenv("ISHUMAN_LIVE_BASE_URL", "https://lemma.id").rstrip("/")
JS_MODULE = REPO_ROOT / "static" / "js" / "proof-verifier.mjs"
PY_MODULE = REPO_ROOT / "packages" / "proof-verifier-py" / "lemma_proof_verifier.py"


def _load_heroku_config(name: str) -> str:
    if os.getenv(name, "").strip():
        return os.getenv(name, "").strip()
    proc = _run_heroku(["heroku", "config:get", name, "-a", "lemma-enterprise"])
    value = (proc.stdout or "").strip()
    if value:
        os.environ[name] = value
    return value


def _parse_table_lines(stdout: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in stdout.splitlines():
        if "|" in line and not line.strip().startswith("-") and "wallet_id" not in line.lower():
            rows.append([part.strip() for part in line.split("|")])
    return rows


def _find_ishuman_master_id(stdout: str) -> str:
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("ishuman_master_"):
            return stripped.split()[0]
    for row in _parse_table_lines(stdout):
        for cell in row:
            if cell.startswith("ishuman_master_"):
                return cell
    return ""


def _load_master_credential_id(wallet_id: str) -> str:
    env_id = os.getenv("LEMMA_ISHUMAN_PROD_TEST_MASTER_CREDENTIAL_ID", "").strip()
    if env_id:
        return env_id
    proc = _run_heroku(
        [
            "heroku",
            "pg:psql",
            "-a",
            "lemma-enterprise",
            "-c",
            (
                "SELECT credential_id FROM ishuman_verifications "
                f"WHERE wallet_id='{wallet_id}' AND status='verified' "
                "ORDER BY verified_at DESC LIMIT 1;"
            ),
        ],
    )
    for row in _parse_table_lines(proc.stdout):
        for cell in row:
            if cell.startswith("ishuman_master_"):
                return cell
    return _find_ishuman_master_id(proc.stdout)


def _node_eval(script: str) -> subprocess.CompletedProcess[str]:
    node_bin = shutil.which("node")
    if not node_bin:
        raise RuntimeError("node not available")
    module_url = JS_MODULE.resolve().as_uri()
    wrapped = (
        "import(" + repr(module_url) + ").then(async (m) => {\n"
        "  try {\n"
        f"    {script}\n"
        "  } catch (err) {\n"
        "    console.error(err);\n"
        "    process.exit(1);\n"
        "  }\n"
        "});\n"
    )
    return subprocess.run([node_bin, "-e", wrapped], capture_output=True, text=True, timeout=30)


def _load_py_verifier():
    spec = importlib.util.spec_from_file_location("lemma_proof_verifier_e2e", PY_MODULE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    if not os.getenv("LEMMA_ISHUMAN_PROD_TEST_WALLET_SECRET"):
        secret = _load_heroku_config("LEMMA_ISHUMAN_PROD_TEST_WALLET_SECRET")
        if not secret:
            print("FAIL: LEMMA_ISHUMAN_PROD_TEST_WALLET_SECRET unavailable", file=sys.stderr)
            return 1

    _load_heroku_config("LEMMA_NETWORK_ROOT_PUBKEYS")
    _load_heroku_config("LEMMA_PPID_ROOT_KEY")

    wallet_id = prod_test_wallet_id()
    wallet_secret = require_prod_test_secret()
    target_site = prod_test_target_site()
    master_id = _load_master_credential_id(wallet_id)
    if not master_id:
        print("FAIL: no verified master credential for prod test wallet", file=sys.stderr)
        return 1

    results: list[dict] = []

    # 1) Live bloom + trust list (server crypto)
    bloom_resp = requests.get(f"{BASE}/api/revocation/bloom-filter", timeout=30)
    bloom_data = bloom_resp.json() if bloom_resp.ok else {}
    trust_list = bloom_data.get("trust_list") or {}
    snapshot = bloom_data.get("snapshot") or {}
    hashed_ids = bloom_data.get("hashed_revoked_ids") or []

    trust_ok, trust_reason = verify_signed_trust_list(trust_list)
    bloom_ok, bloom_reason = verify_bloom_snapshot(snapshot)
    payload_ok, payload_reason = verify_snapshot_matches_payload(
        snapshot,
        hashed_revoked_ids=hashed_ids,
    )
    results.append(
        _step(
            "live trust-list pin+sig",
            trust_ok and trust_reason == "ok",
            trust_reason,
        )
    )
    results.append(
        _step(
            "live bloom snapshot",
            bloom_ok and payload_ok,
            f"bloom={bloom_reason} payload={payload_reason}",
        )
    )

    # 2) Issue fresh site credential on prod
    derive_body = {
        "master_credential_id": master_id,
        "wallet_id": wallet_id,
        "target_site": target_site,
        "site_signing_pubkey": "",
        "issue_mode": "site_proof",
    }
    from api.wallet_keys import derive_wallet_signing_keypair, pubkey_to_b64url

    _priv, pub = derive_wallet_signing_keypair(wallet_secret)
    derive_body["site_signing_pubkey"] = pubkey_to_b64url(pub)
    derive_body["wallet_assertion"] = _derive_assertion(BASE, wallet_id, wallet_secret, derive_body)
    derive_resp = requests.post(f"{BASE}/api/ishuman/derive-site-proof", json=derive_body, timeout=60)
    derive_json = derive_resp.json() if derive_resp.ok else {}
    credential = derive_json.get("credential") or {}
    sig = ((credential.get("proof") or {}).get("signatureValueWeb") or "").strip()
    cred_ok = (
        derive_resp.status_code == 200
        and derive_json.get("success")
        and credential.get("id")
        and credential.get("subject")
        and len(sig) == 128
    )
    results.append(
        _step(
            "derive-site-proof (fresh v2 credential)",
            cred_ok,
            f"HTTP {derive_resp.status_code} id={credential.get('id', '-')[:24]} assurance={(credential.get('claims') or {}).get('assurance')}",
        ),
    )
    if not cred_ok:
        for row in results:
            print(f"[{'PASS' if row['ok'] else 'FAIL'}] {row['step']}: {row['detail']}")
        return 1

    claims = credential.get("claims") or {}
    assurance = str(claims.get("assurance") or "ishuman").lower()

    # 3) Canonical bytes: Python server helper vs Node package
    py_bytes = _browser_canonical_message(credential)
    cred_json = json.dumps(credential)
    node_result = _node_eval(
        f"const cred = {cred_json};\n"
        "const bytes = m.browserCanonicalMessage(cred);\n"
        "const hex = Array.from(bytes).map((b) => b.toString(16).padStart(2, '0')).join('');\n"
        f"if (hex !== '{py_bytes.hex()}') process.exit(2);\n"
        "console.log('canonical-match');"
    )
    results.append(
        _step(
            "python/node canonical v2 bytes",
            node_result.returncode == 0,
            node_result.stderr.strip() or node_result.stdout.strip() or f"exit={node_result.returncode}",
        )
    )

    # 4) Server verify-presentation (ishuman + monotonic passkey policy)
    for required, expect_ok in (("ishuman", True), ("passkey", assurance in ("passkey", "ishuman"))):
        vp = requests.post(
            f"{BASE}/api/ishuman/verify-presentation",
            json={
                "site_id": target_site,
                "credential": credential,
                "required_assurance": required,
            },
            timeout=30,
        )
        vp_json = vp.json() if vp.headers.get("content-type", "").startswith("application/json") else {}
        ok = vp.status_code == 200 and vp_json.get("success") is True
        if expect_ok:
            results.append(
                _step(
                    f"verify-presentation required={required}",
                    ok,
                    f"HTTP {vp.status_code} human={vp_json.get('human')} assurance={vp_json.get('assurance')}",
                )
            )
        else:
            denied = vp.status_code == 400 and (vp_json.get("error") or "") == "assurance_insufficient"
            results.append(
                _step(
                    f"verify-presentation rejects passkey-only for ishuman policy",
                    denied,
                    f"HTTP {vp.status_code} error={vp_json.get('error')}",
                )
            )

    # Negative: tampered site binding should fail signature / site check
    tampered = json.loads(json.dumps(credential))
    tampered["claims"]["siteId"] = "evil.example.com"
    tampered["credentialSubject"] = dict(tampered.get("claims") or {})
    bad = requests.post(
        f"{BASE}/api/ishuman/verify-presentation",
        json={"site_id": target_site, "credential": tampered},
        timeout=30,
    )
    bad_json = bad.json() if bad.headers.get("content-type", "").startswith("application/json") else {}
    bad_ok = bad.status_code == 400 and (bad_json.get("error") or "") in {
        "invalid_signature",
        "site_id_mismatch",
    }
    results.append(
        _step(
            "verify-presentation rejects tampered siteId",
            bad_ok,
            f"HTTP {bad.status_code} error={bad_json.get('error')}",
        )
    )

    # 5) Python offline verifier against live bloom bundle
    py_mod = _load_py_verifier()
    presentation = {"credential": credential}

    class _FakeResp:
        def __init__(self, payload: bytes):
            self._payload = payload

        def read(self):
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    bloom_payload = json.dumps(bloom_data).encode("utf-8")

    ctx = py_mod.VerificationContext(site_id=target_site, lemma_origin=BASE)
    with patch("urllib.request.urlopen", return_value=_FakeResp(bloom_payload)):
        offline = ctx.verify(presentation)
    results.append(
        _step(
            "python offline verifier (live bloom fixture)",
            offline.ok,
            offline.reason,
        )
    )

    # 6) Monotonic assurance helper parity
    results.append(
        _step(
            "monotonic assurance python",
            _assurance_meets_policy("ishuman", "passkey") and not _assurance_meets_policy("passkey", "ishuman"),
            f"ishuman->passkey={_assurance_meets_policy('ishuman', 'passkey')}",
        )
    )
    node_assurance = _node_eval(
        "const ok = m.assuranceMeetsPolicy('ishuman', 'passkey');"
        "const bad = m.assuranceMeetsPolicy('passkey', 'ishuman');"
        "if (!ok || bad) process.exit(2);"
        "console.log('assurance-ok');"
    )
    results.append(
        _step(
            "monotonic assurance node",
            node_assurance.returncode == 0,
            node_assurance.stderr.strip() or node_assurance.stdout.strip(),
        )
    )

    failed = [row for row in results if not row["ok"]]
    print("\nSection 4 prod E2E summary:")
    for row in results:
        status = "PASS" if row["ok"] else "FAIL"
        print(f"[{status}] {row['step']}: {row['detail']}")

    if failed:
        print(f"\n{len(failed)} check(s) failed.", file=sys.stderr)
        return 1
    print("\nAll Section 4 prod E2E checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
