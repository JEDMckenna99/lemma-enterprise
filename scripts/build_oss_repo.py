#!/usr/bin/env python3
"""Assemble the public "Sign in with lemma.id" repo staging tree at oss/.

Copies the trust-critical, publishable artifacts from their canonical
locations in the monorepo into oss/, which mirrors the layout of the public
GitHub repository. Everything under oss/ except README.md is generated;
edit the canonical sources, not the copies, then re-run this script.

Scope (deliberately narrow — the verification path only):
  - Server-side verifier packages (the code relying sites run)
  - Browser SDK served from https://lemma.id/sdk/
  - Client-side credential-store crypto (the "keys stay on device" surface)
  - Protocol/trust specs + network root public keys

Usage:  python scripts/build_oss_repo.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OSS_ROOT = REPO_ROOT / "oss"

# (source relative to repo root, destination relative to oss/)
FILE_COPIES = [
    ("LICENSE", "LICENSE"),
    # Browser SDK — canonical file is ishuman-verifier.js, served publicly as
    # /sdk/proof-verifier.js (see api/sdk_serving.py).
    ("static/js/ishuman-verifier.js", "sdk/proof-verifier.js"),
    ("static/js/lemma-signin.js", "sdk/lemma-signin.js"),
    # lemma.id credential store (client-held keys).
    ("static/js/lemma-keys.js", "wallet/lemma-keys.js"),
    ("static/js/wallet-at-rest-crypto.js", "wallet/wallet-at-rest-crypto.js"),
    ("static/js/lemma-wallet.js", "wallet/lemma-wallet.js"),
    # Specs.
    ("docs/product/LEMMA_ID_PRESENTATION_MODEL.md", "specs/LEMMA_ID_PRESENTATION_MODEL.md"),
    ("docs/security/HUMAN_AUTH_SECURITY_CONTRACT.md", "specs/HUMAN_AUTH_SECURITY_CONTRACT.md"),
    ("docs/integration/SIGN_IN_TRUST_AND_RECOVERY.md", "specs/SIGN_IN_TRUST_AND_RECOVERY.md"),
    ("docs/cryptographic/NETWORK_ROOT_PUBKEYS.json", "specs/NETWORK_ROOT_PUBKEYS.json"),
]

# Whole directories copied recursively (source, destination).
DIR_COPIES = [
    ("packages/proof-verifier-js", "packages/proof-verifier-js"),
    ("packages/proof-verifier-py", "packages/proof-verifier-py"),
]

DIR_COPY_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "node_modules", ".pytest_cache", "*.egg-info", "dist", "build"
)


def main() -> int:
    missing = [src for src, _ in FILE_COPIES + DIR_COPIES if not (REPO_ROOT / src).exists()]
    if missing:
        for src in missing:
            print(f"ERROR: canonical source missing: {src}", file=sys.stderr)
        return 1

    # Clear generated content but preserve the hand-maintained README.
    if OSS_ROOT.exists():
        for child in OSS_ROOT.iterdir():
            if child.name == "README.md":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    OSS_ROOT.mkdir(exist_ok=True)

    for src, dst in FILE_COPIES:
        target = OSS_ROOT / dst
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / src, target)
        print(f"  {src} -> oss/{dst}")

    for src, dst in DIR_COPIES:
        target = OSS_ROOT / dst
        shutil.copytree(REPO_ROOT / src, target, ignore=DIR_COPY_IGNORE)
        print(f"  {src}/ -> oss/{dst}/")

    if not (OSS_ROOT / "README.md").exists():
        print("WARNING: oss/README.md missing — it is hand-maintained, not generated.", file=sys.stderr)

    print("\noss/ staging tree assembled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
