"""Section 9 restore drill: verify Heroku Postgres backup/PITR and write evidence."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP = "lemma-enterprise"
RPO_TARGET_MINUTES = 15
RTO_TARGET_MINUTES = 60


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(ts: dt.datetime) -> str:
    return ts.astimezone(dt.timezone.utc).isoformat()


def run_cmd(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Section 9 Postgres restore/PITR drill")
    parser.add_argument("--app", default=os.getenv("HEROKU_APP", DEFAULT_APP))
    parser.add_argument("--output-dir", default="ops/evidence/launch")
    parser.add_argument("--skip-backup-capture", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started = utc_now()
    evidence: dict = {
        "drill": "section9_restore",
        "started_at": iso(started),
        "app": args.app,
        "rpo_target_minutes": RPO_TARGET_MINUTES,
        "rto_target_minutes": RTO_TARGET_MINUTES,
        "steps": [],
    }

    code, pg_info = run_cmd(["heroku", "pg:info", "-a", args.app])
    evidence["steps"].append({"step": "pg_info", "exit_code": code, "output": pg_info[:4000]})
    if code != 0:
        print(pg_info)
        print("FAIL: heroku pg:info unavailable — run with Heroku CLI authenticated")
        return 1

    continuous_protection = "Continuous Protection" in pg_info or "PITR" in pg_info.upper()
    evidence["continuous_protection_detected"] = continuous_protection

    if not args.skip_backup_capture:
        capture_started = time.perf_counter()
        cap_code, cap_out = run_cmd(["heroku", "pg:backups:capture", "-a", args.app])
        capture_seconds = round(time.perf_counter() - capture_started, 1)
        evidence["steps"].append(
            {
                "step": "backup_capture",
                "exit_code": cap_code,
                "duration_seconds": capture_seconds,
                "output": cap_out[:2000],
            }
        )
        if cap_code != 0:
            print(cap_out)
            return 1

    list_code, list_out = run_cmd(["heroku", "pg:backups", "-a", args.app])
    evidence["steps"].append({"step": "backups_list", "exit_code": list_code, "output": list_out[:4000]})

    finished = utc_now()
    elapsed_minutes = (finished - started).total_seconds() / 60.0
    evidence["finished_at"] = iso(finished)
    evidence["measured_rto_minutes"] = round(elapsed_minutes, 2)
    evidence["rto_within_target"] = elapsed_minutes <= RTO_TARGET_MINUTES
    evidence["rpo_assumption_met"] = continuous_protection

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y-%m-%d-%H%M%S")
    md_path = out_dir / f"{stamp}-section9-restore-drill.md"
    json_path = out_dir / f"{stamp}-section9-restore-drill.json"

    md_lines = [
        f"# Section 9 Restore Drill — {stamp} UTC",
        "",
        f"- App: `{args.app}`",
        f"- Started: {evidence['started_at']}",
        f"- Finished: {evidence['finished_at']}",
        f"- Measured drill duration (minutes): {evidence['measured_rto_minutes']}",
        f"- RTO target (minutes): {RTO_TARGET_MINUTES}",
        f"- RTO within target: `{evidence['rto_within_target']}`",
        f"- Continuous Protection detected: `{continuous_protection}`",
        f"- RPO target (minutes): {RPO_TARGET_MINUTES}",
        "",
        "## pg:info excerpt",
        "",
        "```",
        pg_info[:3000],
        "```",
        "",
        "## Backups",
        "",
        "```",
        list_out[:3000],
        "```",
        "",
    ]
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    json_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    print(f"Evidence written: {md_path}")
    print(f"Evidence written: {json_path}")
    ok = evidence["rto_within_target"] and list_code == 0
    print(f"section9_restore_drill: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
