#!/usr/bin/env python3
"""Install built proof-verifier artifacts in clean envs and verify mint→verify.

Fails closed if the wheel/tarball that would be published cannot round-trip a
passkey presentation. Use before registry publish.

Usage:
  python scripts/proof_verifier_artifact_smoke.py \\
    --wheel packages/proof-verifier-py/dist/*.whl \\
    --tgz packages/proof-verifier-py/dist/lemma.id-proof-verifier-*.tgz
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _one(pattern: str) -> Path:
    matches = sorted(Path(p) for p in glob.glob(pattern))
    if not matches:
        raise SystemExit(f"no artifact matched: {pattern}")
    return matches[0].resolve()


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        raise SystemExit(f"command failed ({result.returncode}): {' '.join(cmd)}")


def _smoke_python(wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="pv-py-") as tmp:
        root = Path(tmp)
        venv = root / "venv"
        _run([sys.executable, "-m", "venv", str(venv)])
        py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        _run([str(py), "-m", "pip", "install", "--upgrade", "pip", "-q"])
        _run([str(py), "-m", "pip", "install", str(wheel), "-q"])
        script = textwrap.dedent(
            """
            from lemma_proof_verifier_testing import (
                create_offline_test_context,
                mint_test_issuer,
                mint_test_presentation,
            )

            issuer = mint_test_issuer()
            presentation = mint_test_presentation(
                site_id="ci.example.com",
                ppid="did:lemma:ppid_artifact_smoke",
                assurance="passkey",
                issuer=issuer,
            )
            ctx = create_offline_test_context(
                site_id="ci.example.com",
                issuer_did=issuer["did"],
                issuer_pubkey_hex=issuer["pubkey_hex"],
                required_assurance="passkey",
            )
            result = ctx.verify(presentation)
            assert result.ok is True, result
            assert result.ppid == "did:lemma:ppid_artifact_smoke"
            assert result.assurance == "passkey"
            print("PASS python-wheel-mint-verify")
            """
        ).strip()
        _run([str(py), "-c", script])


def _smoke_npm(tgz: Path) -> None:
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm:
        raise SystemExit("node/npm required for npm artifact smoke")

    with tempfile.TemporaryDirectory(prefix="pv-npm-") as tmp:
        root = Path(tmp)
        _run([npm, "init", "-y"], cwd=root)
        _run([npm, "install", str(tgz)], cwd=root)
        script = textwrap.dedent(
            """
            import {
              mintTestIssuer,
              mintTestPresentation,
              verifyTestPresentationOffline,
            } from '@lemma.id/proof-verifier/testing';

            const issuer = await mintTestIssuer();
            const presentation = await mintTestPresentation({
              siteId: 'ci.example.com',
              ppid: 'did:lemma:ppid_artifact_smoke',
              assurance: 'passkey',
              issuer,
            });
            const result = await verifyTestPresentationOffline({
              presentation,
              siteId: 'ci.example.com',
              requiredAssurance: 'passkey',
              trustedIssuerPubkeyHex: issuer.pubkeyHex,
            });
            if (!result.ok) {
              console.error(result);
              process.exit(2);
            }
            if (result.ppid !== 'did:lemma:ppid_artifact_smoke') process.exit(3);
            console.log('PASS npm-tarball-mint-verify');
            """
        ).strip()
        script_path = root / "smoke.mjs"
        script_path.write_text(script + "\n", encoding="utf-8")
        _run([node, str(script_path)], cwd=root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, help="Path or glob to .whl")
    parser.add_argument("--tgz", required=True, help="Path or glob to npm .tgz")
    args = parser.parse_args()

    wheel = _one(args.wheel)
    tgz = _one(args.tgz)
    print(f"wheel={wheel}")
    print(f"tgz={tgz}")

    _smoke_python(wheel)
    _smoke_npm(tgz)
    print("proof_verifier_artifact_smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
