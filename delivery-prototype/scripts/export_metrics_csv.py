#!/usr/bin/env python3
"""Export field metrics JSON file to CSV."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", type=Path, help="JSON array of metric logs")
    parser.add_argument("-o", "--output", type=Path, default=Path("field_metrics.csv"))
    args = parser.parse_args()

    logs = json.loads(args.input_json.read_text(encoding="utf-8"))
    if not isinstance(logs, list):
        print("Expected JSON array", file=sys.stderr)
        sys.exit(1)
    headers = [
        "log_id", "timestamp", "route_type", "stop_type", "signal_quality",
        "delayed_action", "delay_bucket", "retry_needed", "sensitive_data_collected",
    ]
    with args.output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        for row in logs:
            writer.writerow({h: row.get(h, "") for h in headers})
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
