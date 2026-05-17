#!/usr/bin/env python
"""Validate local/staging/production environment safety.

The script reports missing keys and unsafe mode combinations without printing
secret values. It can validate one env source or compare key presence between
two sources, which is useful for local-vs-Heroku parity checks.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable


COMMON_REQUIRED = {
    "SECRET_KEY",
    "FLASK_ENV",
    "ENVIRONMENT",
    "LEMMA_BASE_URL",
    "DATABASE_URL",
    "REDIS_URL",
    "LEMMA_PPID_ROOT_KEY",
    "STRIPE_SECRET_KEY",
    "STRIPE_IDENTITY_WEBHOOK_SECRET",
    "ISHUMAN_RETURN_URL",
}

KMS_REQUIRED = {
    "AWS_REGION",
    "LEMMA_KMS_KEY_ID",
}

DEMO_KEYS = {
    "LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY",
    "LEMMA_ISHUMAN_DEMO_TEST_TOKEN",
    "LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN",
}

PLACEHOLDER_MARKERS = (
    "replace-with",
    "<staging-app>",
    "<production-app>",
    "sk_test_replace",
    "sk_live_replace",
    "whsec_replace",
    "dev-secret-key-for-testing",
)


def parse_env_lines(lines: Iterable[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip().strip('"').strip("'")
    return values


def load_env_file(path: str | None) -> dict[str, str]:
    if not path:
        return dict(os.environ)
    env_path = Path(path)
    if not env_path.exists():
        raise FileNotFoundError(f"Env file not found: {env_path}")
    return parse_env_lines(env_path.read_text(encoding="utf-8").splitlines())


def is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def is_placeholder(value: str | None) -> bool:
    lowered = str(value or "").strip().lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def validate(
    env: dict[str, str],
    environment: str,
    *,
    allow_placeholders: bool = False,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    environment = environment.lower()

    required = set(COMMON_REQUIRED)
    if environment in {"staging", "production"}:
        required |= KMS_REQUIRED

    missing = sorted(key for key in required if not env.get(key))
    if missing:
        errors.append("Missing required keys: " + ", ".join(missing))

    placeholders = sorted(
        key for key in required | DEMO_KEYS
        if env.get(key) and is_placeholder(env.get(key))
    )
    if placeholders and environment in {"staging", "production"} and not allow_placeholders:
        errors.append("Placeholder values present in deployed env: " + ", ".join(placeholders))
    elif placeholders:
        warnings.append("Placeholder values present: " + ", ".join(placeholders))

    stripe_key = env.get("STRIPE_SECRET_KEY", "")
    demo_test_enabled = is_truthy(env.get("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY"))

    if environment == "production":
        if stripe_key and not stripe_key.startswith("sk_live_"):
            errors.append("Production STRIPE_SECRET_KEY must start with sk_live_.")
        if demo_test_enabled:
            errors.append("Production must not enable LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY.")
        if env.get("FLASK_ENV") == "development":
            errors.append("Production FLASK_ENV must not be development.")
        if env.get("ENVIRONMENT") != "production":
            errors.append("Production ENVIRONMENT must be production.")
    else:
        if stripe_key and not stripe_key.startswith("sk_test_"):
            errors.append(f"{environment} STRIPE_SECRET_KEY must start with sk_test_.")
        if demo_test_enabled and not env.get("LEMMA_ISHUMAN_DEMO_TEST_TOKEN"):
            errors.append("Test verification helper enabled without LEMMA_ISHUMAN_DEMO_TEST_TOKEN.")

    if demo_test_enabled and stripe_key and not stripe_key.startswith("sk_test_"):
        errors.append("Test verification helper can only be enabled with Stripe test keys.")

    if environment in {"staging", "production"}:
        if str(env.get("DATABASE_URL", "")).startswith("sqlite"):
            errors.append(f"{environment} DATABASE_URL must not use sqlite.")
        if not str(env.get("LEMMA_BASE_URL", "")).startswith("https://"):
            errors.append(f"{environment} LEMMA_BASE_URL must use https.")
        if not str(env.get("ISHUMAN_RETURN_URL", "")).startswith("https://"):
            errors.append(f"{environment} ISHUMAN_RETURN_URL must use https.")

    if environment == "local" and not env.get("LEMMA_KMS_KEY_ID"):
        warnings.append("LEMMA_KMS_KEY_ID missing locally; real KMS-backed issuance may fail.")

    return errors, warnings


def compare_keys(source: dict[str, str], compare: dict[str, str], environment: str) -> list[str]:
    keys = set(COMMON_REQUIRED)
    if environment.lower() in {"staging", "production"}:
        keys |= KMS_REQUIRED
    # Demo keys are intentionally part of parity checks because staging/prod
    # differ in values, but the explicit presence makes intent reviewable.
    keys |= DEMO_KEYS
    missing_in_compare = sorted(key for key in keys if source.get(key) and key not in compare)
    return missing_in_compare


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Lemma env config safety.")
    parser.add_argument("--environment", choices=["local", "staging", "production"], required=True)
    parser.add_argument("--env-file", help="Env file to validate. Defaults to current process env.")
    parser.add_argument("--compare-env-file", help="Optional env file to compare key presence against.")
    parser.add_argument(
        "--allow-placeholders",
        action="store_true",
        help="Allow placeholder values when validating tracked example templates.",
    )
    args = parser.parse_args()

    env = load_env_file(args.env_file)
    errors, warnings = validate(env, args.environment, allow_placeholders=args.allow_placeholders)

    if args.compare_env_file:
        compare = load_env_file(args.compare_env_file)
        missing = compare_keys(env, compare, args.environment)
        if missing:
            warnings.append(
                "Compared env is missing keys present in source: " + ", ".join(missing)
            )

    print(f"Environment check: {args.environment}")
    print(f"Source: {args.env_file or 'process env'}")
    if args.compare_env_file:
        print(f"Compared with: {args.compare_env_file}")

    for warning in warnings:
        print(f"WARN: {warning}")
    for error in errors:
        print(f"ERROR: {error}")

    if errors:
        print("Result: FAIL")
        return 1

    print("Result: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
