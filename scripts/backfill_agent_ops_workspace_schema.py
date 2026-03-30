#!/usr/bin/env python3
"""Backfill the workspace-first Agent Ops schema from legacy tables."""

import json

from api.agent_ops_store import backfill_agent_ops_schema


def main() -> None:
    summary = backfill_agent_ops_schema()
    print(json.dumps({"success": True, "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
