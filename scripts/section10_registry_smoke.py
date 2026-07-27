"""Section 10 registry + zero-install smoke for proof-verifier packages."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://lemma.id"
NPM_PACKAGE = "@lemma.id/proof-verifier"
PYPI_PACKAGE = "lemma-proof-verifier"
EXPECTED_VERSION = "1.4.0"


def _get(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "section10-registry-smoke/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def _npm_registry_version() -> tuple[bool, str]:
    url = f"https://registry.npmjs.org/{NPM_PACKAGE.replace('/', '%2F')}"
    code, body = _get(url)
    if code != 200:
        return False, f"http_{code}"
    try:
        data = json.loads(body)
        version = (data.get("dist-tags") or {}).get("latest") or ""
        return version == EXPECTED_VERSION, version or "missing"
    except json.JSONDecodeError:
        return False, "invalid_json"


def _pypi_registry_version() -> tuple[bool, str]:
    url = f"https://pypi.org/pypi/{PYPI_PACKAGE}/json"
    code, body = _get(url)
    if code != 200:
        return False, f"http_{code}"
    try:
        data = json.loads(body)
        version = str((data.get("info") or {}).get("version") or "")
        return version == EXPECTED_VERSION, version or "missing"
    except json.JSONDecodeError:
        return False, "invalid_json"


def _local_wheel_install() -> tuple[bool, str]:
    dist_dir = REPO_ROOT / "packages" / "proof-verifier-py" / "dist"
    wheels = sorted(dist_dir.glob("*.whl"))
    if not wheels:
        build = subprocess.run(
            [sys.executable, "-m", "pip", "install", "build", "-q"],
            capture_output=True,
            text=True,
        )
        if build.returncode != 0:
            return False, f"pip_build_dep:{build.stderr.strip()}"
        built = subprocess.run(
            [sys.executable, "-m", "build"],
            cwd=REPO_ROOT / "packages" / "proof-verifier-py",
            capture_output=True,
            text=True,
        )
        if built.returncode != 0:
            return False, f"build_failed:{built.stderr.strip()}"
        wheels = sorted(dist_dir.glob("*.whl"))
    if not wheels:
        return False, "no_wheel"

    with tempfile.TemporaryDirectory() as tmp:
        venv = Path(tmp) / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        py = venv / "Scripts" / "python.exe"
        if not py.is_file():
            py = venv / "bin" / "python"
        pip_install = subprocess.run(
            [str(py), "-m", "pip", "install", str(wheels[-1]), "cryptography>=42", "-q"],
            capture_output=True,
            text=True,
        )
        if pip_install.returncode != 0:
            return False, pip_install.stderr.strip() or "pip_install_failed"
        probe = subprocess.run(
            [
                str(py),
                "-c",
                "from lemma_proof_verifier import VerificationContext; "
                "print(VerificationContext.__name__)",
            ],
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0:
            return False, probe.stderr.strip() or "import_failed"
        return probe.stdout.strip() == "VerificationContext", probe.stdout.strip()


def _local_npm_pack() -> tuple[bool, str]:
    import shutil

    npm_bin = shutil.which("npm")
    if not npm_bin:
        return True, "skipped_no_npm"
    out_dir = REPO_ROOT / "tmp-section10-npm"
    out_dir.mkdir(exist_ok=True)
    packed = subprocess.run(
        [npm_bin, "pack", "--pack-destination", str(out_dir)],
        cwd=REPO_ROOT / "packages" / "proof-verifier-js",
        capture_output=True,
        text=True,
    )
    if packed.returncode != 0:
        return False, packed.stderr.strip() or "npm_pack_failed"
    names = [p.name for p in out_dir.glob("*.tgz")]
    return bool(names), ",".join(names) or "packed"


def main() -> int:
    checks: list[tuple[str, bool, object, bool]] = []
    require_registry = "--require-registry" in sys.argv

    for name, url, needle in (
        ("zero-install-mjs", f"{ORIGIN}/sdk/v{EXPECTED_VERSION}/proof-verifier.mjs", "createVerifier"),
        ("zero-install-py", f"{ORIGIN}/sdk/v{EXPECTED_VERSION}/proof-verifier.py", "VerificationContext"),
        ("legacy-mjs-alias", f"{ORIGIN}/sdk/lemma-ishuman-verify.mjs", "createVerifier"),
        ("legacy-py-alias", f"{ORIGIN}/sdk/lemma_ishuman_verify.py", "VerificationContext"),
    ):
        try:
            code, text = _get(url)
            ok = code == 200 and needle in text
            checks.append((name, ok, {"status": code}, True))
        except Exception as exc:
            checks.append((name, False, str(exc), True))

    try:
        ok, detail = _local_wheel_install()
        checks.append(("local-pypi-wheel-import", ok, detail, True))
    except Exception as exc:
        checks.append(("local-pypi-wheel-import", False, str(exc), True))

    try:
        ok, detail = _local_npm_pack()
        checks.append(("local-npm-pack", ok, detail, True))
    except Exception as exc:
        checks.append(("local-npm-pack", False, str(exc), True))

    try:
        ok, detail = _npm_registry_version()
        checks.append(("npm-registry", ok, detail, require_registry))
    except Exception as exc:
        checks.append(("npm-registry", False, str(exc), require_registry))

    try:
        ok, detail = _pypi_registry_version()
        checks.append(("pypi-registry", ok, detail, require_registry))
    except Exception as exc:
        checks.append(("pypi-registry", False, str(exc), require_registry))

    passed = 0
    required = 0
    for name, ok, detail, is_required in checks:
        if is_required:
            required += 1
            if ok:
                passed += 1
        flag = "PASS" if ok else ("WARN" if not is_required else "FAIL")
        print(f"{flag}\t{name}\t{detail}")

    print(f"\nsection10_registry_smoke: {passed}/{required} required checks passed")
    if require_registry and passed < required:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
