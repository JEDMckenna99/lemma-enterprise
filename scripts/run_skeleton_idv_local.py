#!/usr/bin/env python3
"""One-command local skeleton IDV E2E using Heroku config vars.

Pulls config from a non-production Heroku app (default: lemma-staging),
starts ``app.py`` on 127.0.0.1, runs ``run_skeleton_idv_e2e.py``, then stops
the server.

Usage:
  python scripts/run_skeleton_idv_local.py
  python scripts/run_skeleton_idv_local.py --heroku-app lemma-staging --handoff
  python scripts/run_skeleton_idv_local.py --skip-server --port 5000
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HEROKU_EXCLUDE_KEYS = {
    "PORT",
    "DYNO",
    "HOST",
    "HEROKU_APP_NAME",
    "HEROKU_RELEASE_VERSION",
    "SOURCE_VERSION",
    "STACK",
    "HOME",
    "PWD",
    "SHLVL",
}


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _parse_heroku_config(raw: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        env[key] = value
    return env


def _heroku_cli() -> str:
    for candidate in ("heroku", "heroku.cmd"):
        path = shutil.which(candidate)
        if path:
            return path
    raise RuntimeError("Heroku CLI not found in PATH (install from https://devcenter.heroku.com/articles/heroku-cli)")


def _pull_heroku_config(app_name: str) -> dict[str, str]:
    proc = subprocess.run(
        [_heroku_cli(), "config", "-s", "-a", app_name],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"heroku config failed for app {app_name}: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    config = _parse_heroku_config(proc.stdout)
    if not config:
        raise RuntimeError(f"Heroku app {app_name} returned no config vars")
    return config


def _build_local_env(
    heroku_env: dict[str, str],
    *,
    port: int,
    environment: str,
) -> dict[str, str]:
    env = dict(os.environ)
    for key, value in heroku_env.items():
        if key in HEROKU_EXCLUDE_KEYS:
            continue
        env[key] = value

    env["PORT"] = str(port)
    env["FLASK_ENV"] = "development"
    env["ENVIRONMENT"] = environment
    env["LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY"] = "true"
    env["LEMMA_ISHUMAN_SKELETON_IDV_ENABLED"] = "true"
    env.setdefault("LEMMA_ISHUMAN_SKELETON_CREDENTIAL_TTL_SECONDS", "900")
    env.setdefault("LEMMA_IDV_HANDOFF_TTL_SECONDS", "300")
    return env


def _wait_for_health(base_url: str, timeout_seconds: float = 120.0) -> None:
    deadline = time.time() + timeout_seconds
    url = base_url.rstrip("/") + "/api/health"
    last_error = "unknown"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                if resp.status == 200 and payload.get("status") == "ok":
                    return
                last_error = f"unexpected health payload: {payload}"
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(1.0)
    raise RuntimeError(f"Local server did not become healthy at {url}: {last_error}")


def _terminate_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run skeleton IDV E2E against local Flask + Heroku env")
    parser.add_argument("--heroku-app", default=os.getenv("LEMMA_HEROKU_APP", "lemma-staging"))
    parser.add_argument("--environment", default="staging", help="ENVIRONMENT override for local run")
    parser.add_argument("--port", type=int, default=0, help="Local port (0 = auto)")
    parser.add_argument("--handoff", action="store_true", help="Exercise mobile handoff claim path")
    parser.add_argument("--ttl-seconds", type=int, default=900)
    parser.add_argument("--skip-server", action="store_true", help="Assume app.py already running")
    parser.add_argument("--startup-timeout", type=int, default=180)
    args = parser.parse_args()

    port = args.port or _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    print(f"Pulling Heroku config from app={args.heroku_app} ...")
    heroku_env = _pull_heroku_config(args.heroku_app)
    local_env = _build_local_env(heroku_env, port=port, environment=args.environment)

    token = local_env.get("LEMMA_ISHUMAN_DEMO_TEST_TOKEN", "").strip()
    if not token:
        print(
            "LEMMA_ISHUMAN_DEMO_TEST_TOKEN missing from Heroku config. Set it on the staging app first.",
            file=sys.stderr,
        )
        return 2

    server_proc: subprocess.Popen | None = None
    server_log_path: str | None = None
    exit_code = 1
    try:
        if not args.skip_server:
            print(f"Starting local Flask on {base_url} ...")
            log_fd, server_log_path = tempfile.mkstemp(prefix="lemma_local_", suffix=".log")
            os.close(log_fd)
            log_handle = open(server_log_path, "w", encoding="utf-8")
            server_proc = subprocess.Popen(
                [sys.executable, str(ROOT / "app.py")],
                cwd=str(ROOT),
                env=local_env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
            log_handle.close()
            _wait_for_health(base_url, timeout_seconds=float(args.startup_timeout))
            print("Local server healthy.")
        else:
            _wait_for_health(base_url, timeout_seconds=15.0)

        e2e_cmd = [
            sys.executable,
            str(ROOT / "scripts" / "run_skeleton_idv_e2e.py"),
            "--base-url",
            base_url,
            "--token",
            token,
            "--ttl-seconds",
            str(args.ttl_seconds),
        ]
        if args.handoff:
            e2e_cmd.append("--handoff")

        print("Running skeleton IDV E2E ...")
        e2e = subprocess.run(e2e_cmd, cwd=str(ROOT), env=local_env, check=False)
        exit_code = e2e.returncode
        if exit_code == 0:
            print(f"\nLocal skeleton IDV E2E passed ({base_url}).")
        else:
            print(f"\nLocal skeleton IDV E2E failed (exit {exit_code}).", file=sys.stderr)
    except Exception as exc:
        print(f"Local skeleton runner error: {exc}", file=sys.stderr)
        exit_code = 1
    finally:
        if server_proc is not None:
            print("Stopping local server ...")
            if exit_code != 0 and server_log_path and Path(server_log_path).exists():
                try:
                    tail = Path(server_log_path).read_text(encoding="utf-8", errors="replace")
                    if tail.strip():
                        print("--- server log tail ---")
                        print(tail[-4000:])
                except Exception:
                    pass
            if server_proc.poll() is not None and server_proc.returncode not in (0, None):
                print(f"Local server exited early with code {server_proc.returncode}", file=sys.stderr)
            _terminate_process(server_proc)
            if server_log_path:
                try:
                    Path(server_log_path).unlink(missing_ok=True)
                except Exception:
                    pass

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
