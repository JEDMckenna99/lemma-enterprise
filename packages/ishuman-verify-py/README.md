# lemma-ishuman-verify

Local-first verifier for [Lemma isHuman](https://lemma.id) presentations.

Runs on **any Python 3.10+ backend** (Flask, FastAPI, Django, AWS Lambda,
Cloud Functions, plain scripts). Single file, one dependency
(`cryptography`).

## Why local verification

- **Privacy** — `lemma.id` never sees an individual verification. It only
  serves a periodic signed Bloom snapshot + trust list (cached, refreshed
  every ~15 minutes by default).
- **Cost** — zero per-request server cost on `lemma.id` and on your backend.
- **Security** — every cryptographic anchor is signed by a trusted issuer
  key listed in the network trust list.

## Install

```sh
pip install lemma-ishuman-verify
# Or, zero-install:
curl -O https://lemma.id/sdk/lemma_ishuman_verify.py
```

## Use

```python
from lemma_ishuman_verify import VerificationContext

ctx = VerificationContext(site_id="tickets-demo.lemma.id")

# In your request handler — the client posts presentation from
# result.presentation returned by IsHumanVerifier.verify()
@app.post("/api/reserve")
def reserve():
    result = ctx.verify(request.json["presentation"])
    if not result.ok:
        abort(401, result.reason)
    return reserve_tickets_for(result.ppid)
```

## What gets checked

For every `verify()` call, all of the following pass locally with no
network calls:

1. Trust list integrity (root of trust, refreshed periodically).
2. Bloom snapshot signature + content hash.
3. Credential `proof.signatureValueWeb` Ed25519 signature against a trusted
   issuer pubkey.
4. `claims.isHuman` is `True`.
5. `claims.siteId` equals the configured `site_id`.
6. `claims.expiresAt` has not passed.
7. SHA-256(credential.id) is not in the Bloom revocation set.
8. (If a `session_assertion` is included) site session signature verifies
   with the credential's `claims.site_signing_pubkey`, the assertion's
   `site_id` matches, and it has not expired.

## API

### `VerificationContext(site_id, lemma_origin=..., refresh_seconds=900, max_session_age_seconds=86400)`

Single long-lived instance per process. Lazily fetches the signed bundle
and caches it. Thread-safe.

### `InMemoryNonceStore`

Simple in-process nonce replay guard for demos/tests.

### `ctx.verify(presentation) -> Result`

### `ctx.verify_stamp(stamped_event, *, key='lemma', durable=False) -> Result`

### `ctx.verify_action_stamp(stamped_event, *, action, method='POST', path='', body=None, nonce_store=None) -> Result`

```python
@dataclass
class Result:
    ok: bool
    reason: str             # "valid" on success, error code on failure
    ppid: str | None = None
    credential_id: str | None = None
    issuer_did: str | None = None
    bound_site_id: str | None = None
```

## License

Apache-2.0
