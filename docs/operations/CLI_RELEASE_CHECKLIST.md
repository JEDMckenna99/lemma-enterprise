# Lemma CLI Release Checklist

Use this checklist to publish the `lemma-cli` package so developers can install with `pipx install lemma-cli` (without cloning the full repo).

## 1) Prepare Version

- Update `version` in `pyproject.toml`.
- Verify `license` metadata matches repository `LICENSE`.
- Verify `readme` points to CLI-specific package readme.
- Add release notes entry (commands, fixes, known limits).
- Commit the version bump.

## 2) Run Local Validation

- `python -m pytest tests/test_lemma_cli.py -q`
- `python -m pip install -e . --no-deps`
- `lemma --help`
- `python -m pip wheel . --no-deps -w .tmp_wheels`
- `python -m build`
- `python -m twine check dist/*`
- Validate on Python 3.10, 3.11, and 3.12 (local or CI matrix).

Expected outcome:
- tests pass
- wheel is created in `.tmp_wheels`
- CLI command runs

## 3) Build Distributions

- `python -m pip install --upgrade build twine`
- `python -m build`
- `python -m twine check dist/*`

## 4) Publish

- Preferred: trusted publishing in CI (OIDC) with tagged release.
- TestPyPI (dry run/manual):
  - `python -m twine upload --repository testpypi dist/*`
- PyPI (production/manual):
  - `python -m twine upload dist/*`

Hard requirements before production publish:
- At least one clean install test in a fresh virtualenv.
- At least one clean install test via `pipx`.
- No failing required CI checks on release commit/tag.

## 5) Post-Publish Verification

- `pipx install lemma-cli`
- `lemma --help`
- `lemma login --api-base https://lemma.id --no-browser --json` (verify browser flow URL is emitted)
- `lemma setup --site-id site_demo --site-domain example.com --framework flask --json`
- `lemma audit --project-dir . --framework flask --skip-health --json`
- `lemma fix --project-dir . --framework flask --safe --skip-health --json`
- `lemma smoke --url "https://lemma.id/api/health" --header "abc" --expect-status 200 --json`
- `lemma ci --project-dir . --framework flask --skip-health --skip-smoke --json`
- `lemma doctor --error "invalid_lemma:untrusted_issuer" --json`

## 6) Documentation + Deploy

- Ensure docs use `pipx install lemma-cli`.
- Ensure docs call it "browser-based lemma.id login" (not third-party CLI comparison wording).
- Deploy docs update to production.
- Smoke check:
  - `GET https://lemma.id/docs/quickstart` => 200
  - verify install command in rendered page

## 7) Rollback / Incident Procedure

- If bad release is published:
  - Yank affected version on PyPI.
  - Publish patch version with fix.
  - Post incident note with affected versions and mitigation.

