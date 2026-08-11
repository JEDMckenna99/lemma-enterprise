#!/usr/bin/env python3
"""Assemble the public "Sign in with lemma.id" repo staging tree at oss/.

Copies the trust-critical, publishable artifacts from their canonical
locations in the monorepo into oss/, which mirrors the layout of the public
GitHub repository.

Generated (rebuilt on each run):
  - packages/, sdk/, wallet/, specs/, LICENSE

Hand-maintained (preserved across rebuilds):
  - README.md, DESIGN_DECISIONS.md, SECURITY_LIMITATIONS.md
  - docs/, demo/, fixtures/, tests/, .github/

Usage:
  python scripts/build_oss_repo.py          # rebuild generated tree
  python scripts/build_oss_repo.py --check  # fail if generated tree drifts
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OSS_ROOT = REPO_ROOT / "oss"

# (source relative to repo root, destination relative to oss/)
FILE_COPIES = [
    ("LICENSE", "LICENSE"),
    ("static/js/ishuman-verifier.js", "sdk/proof-verifier.js"),
    ("static/js/lemma-signin.js", "sdk/lemma-signin.js"),
    ("static/js/lemma-keys.js", "wallet/lemma-keys.js"),
    ("static/js/wallet-at-rest-crypto.js", "wallet/wallet-at-rest-crypto.js"),
    ("static/js/lemma-wallet.js", "wallet/lemma-wallet.js"),
    ("docs/product/LEMMA_ID_PRESENTATION_MODEL.md", "specs/LEMMA_ID_PRESENTATION_MODEL.md"),
    ("docs/security/HUMAN_AUTH_SECURITY_CONTRACT.md", "specs/HUMAN_AUTH_SECURITY_CONTRACT.md"),
    ("docs/integration/SIGN_IN_TRUST_AND_RECOVERY.md", "specs/SIGN_IN_TRUST_AND_RECOVERY.md"),
    ("docs/cryptographic/NETWORK_ROOT_PUBKEYS.json", "specs/NETWORK_ROOT_PUBKEYS.json"),
]

DIR_COPIES = [
    ("packages/proof-verifier-js", "packages/proof-verifier-js"),
    ("packages/proof-verifier-py", "packages/proof-verifier-py"),
]

DIR_COPY_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "node_modules", ".pytest_cache", "*.egg-info", "dist", "build"
)

# Paths under oss/ that are never deleted or overwritten by this script.
HAND_MAINTAINED = {
    "README.md",
    "DESIGN_DECISIONS.md",
    "SECURITY_LIMITATIONS.md",
    "docs",
    "demo",
    "fixtures",
    "tests",
    ".github",
}


def _is_hand_maintained(rel: Path) -> bool:
    parts = rel.parts
    if not parts:
        return False
    top = parts[0]
    if top in HAND_MAINTAINED:
        return True
    return False


def _clear_generated(oss_root: Path) -> None:
    oss_root.mkdir(exist_ok=True)
    for child in oss_root.iterdir():
        if _is_hand_maintained(Path(child.name)):
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _copy_generated(oss_root: Path) -> None:
    for src, dst in FILE_COPIES:
        target = oss_root / dst
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / src, target)
        print(f"  {src} -> oss/{dst}")

    for src, dst in DIR_COPIES:
        target = oss_root / dst
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(REPO_ROOT / src, target, ignore=DIR_COPY_IGNORE)
        print(f"  {src}/ -> oss/{dst}/")


def _generated_paths(oss_root: Path) -> list[Path]:
    paths: list[Path] = []
    for _, dst in FILE_COPIES:
        paths.append(oss_root / dst)
    for _, dst in DIR_COPIES:
        root = oss_root / dst
        if root.exists():
            paths.extend(p for p in root.rglob("*") if p.is_file())
    return sorted(paths)


def _should_ignore_rel(rel: Path) -> bool:
    parts = rel.parts
    if "__pycache__" in parts:
        return True
    if parts and parts[-1].endswith(".pyc"):
        return True
    return False


def _compare_trees(expected_root: Path, actual_root: Path) -> list[str]:
    errors: list[str] = []
    for path in _generated_paths(expected_root):
        rel = path.relative_to(expected_root)
        if _should_ignore_rel(rel):
            continue
        actual = actual_root / rel
        if not actual.exists():
            errors.append(f"missing: oss/{rel.as_posix()}")
            continue
        if path.is_dir():
            continue
        if not filecmp.cmp(path, actual, shallow=False):
            errors.append(f"drift: oss/{rel.as_posix()}")
    for path in _generated_paths(actual_root):
        rel = path.relative_to(actual_root)
        if _should_ignore_rel(rel):
            continue
        expected = expected_root / rel
        if not expected.exists():
            errors.append(f"extra: oss/{rel.as_posix()}")
    return errors


def build(*, check: bool = False) -> int:
    missing = [src for src, _ in FILE_COPIES + DIR_COPIES if not (REPO_ROOT / src).exists()]
    if missing:
        for src in missing:
            print(f"ERROR: canonical source missing: {src}", file=sys.stderr)
        return 1

    if check:
        with tempfile.TemporaryDirectory(prefix="oss-build-check-") as tmp:
            staging = Path(tmp) / "oss"
            staging.mkdir()
            _copy_generated(staging)
            errors = _compare_trees(staging, OSS_ROOT)
            if errors:
                print("ERROR: oss/ generated tree drift (run build_oss_repo.py):", file=sys.stderr)
                for err in errors:
                    print(f"  {err}", file=sys.stderr)
                return 1
        print("oss/ generated tree matches canonical sources.")
        return 0

    _clear_generated(OSS_ROOT)
    _copy_generated(OSS_ROOT)

    if not (OSS_ROOT / "README.md").exists():
        print("WARNING: oss/README.md missing — it is hand-maintained, not generated.", file=sys.stderr)

    print("\noss/ staging tree assembled.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble or verify oss/ staging tree.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if generated oss/ content differs from canonical sources.",
    )
    args = parser.parse_args(argv)
    return build(check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
