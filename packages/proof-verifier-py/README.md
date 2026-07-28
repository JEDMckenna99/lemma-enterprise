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



## Testing (integrator CI)

Copy `lemma_proof_verifier_testing.py` alongside the verifier for offline fixtures:

```python
from lemma_proof_verifier_testing import mint_test_presentation, create_offline_test_context

presentation = mint_test_presentation(site_id="localhost", ppid="did:lemma:ppid_test", assurance="passkey")
ctx = create_offline_test_context(site_id="localhost", issuer_did=..., issuer_pubkey_hex=..., required_assurance="passkey")
assert ctx.verify(presentation).ok
```

See [QUICK_START_SIMPLE_LOGIN.md](../../docs/integration/QUICK_START_SIMPLE_LOGIN.md#testing-your-integration).



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

