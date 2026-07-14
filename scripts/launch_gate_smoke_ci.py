#!/usr/bin/env python3
"""
Non-destructive launch gate smoke checks for Lemma.id production endpoints.

Thin wrapper around scripts/smoke_platform_prod.py for backward compatibility.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.smoke_platform_prod import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
