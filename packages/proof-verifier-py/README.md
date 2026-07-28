# lemma-proof-verifier

Local-first verifier for [Lemma proofs](https://lemma.id).

## Install (PyPI — when published)

```sh
pip install lemma-proof-verifier
```

PyPI upload is pending operator token provisioning. Until then, use the drop-in file:

```sh
curl -O https://lemma.id/sdk/proof-verifier.py
# Place lemma_proof_verifier.py (or proof-verifier.py) on PYTHONPATH
```

From this monorepo during development:

```sh
pip install -e packages/proof-verifier-py
```

## Usage

```python
from lemma_proof_verifier import VerificationContext

ctx = VerificationContext(site_id="app.example.com", required_assurance="passkey")
result = ctx.verify(presentation)
if not result.ok:
    raise PermissionError(result.reason)
account_ppid = result.ppid
```

Legacy names (`lemma-ishuman-verify`, `lemma_ishuman_verify.py`) remain supported as deprecated aliases.

Build artifacts for publish: `python -m build` in `packages/proof-verifier-py/` (requires `PYPI_API_TOKEN` for upload — human action).
