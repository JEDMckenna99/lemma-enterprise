# @lemma/ishuman-verify

Local-first verifier for [Lemma isHuman](https://lemma.id) presentations.

Runs in **Node.js 18+**, **Deno**, **Bun**, **Cloudflare Workers**, **Vercel
Edge**, **Netlify Edge**, and modern **browsers**. Zero required
dependencies — uses the standard WebCrypto API.

## Why local verification

- **Privacy** — `lemma.id` never sees an individual verification. It only
  serves a periodic signed Bloom snapshot + trust list (cached, refreshed
  every ~15 minutes by default).
- **Cost** — zero per-request server cost on `lemma.id` and on your backend.
- **Latency** — typical verify is a few hundred microseconds (one SHA-256 +
  one or two Ed25519 verifies).
- **Security** — each layer is signed by a trusted issuer key listed in the
  network trust list.

## Install

```sh
npm install @lemma/ishuman-verify
# or, zero-install, import directly:
import { createVerifier } from "https://lemma.id/sdk/lemma-ishuman-verify.mjs";
```

## Use

```js
import { createVerifier } from "@lemma/ishuman-verify";

const verifier = createVerifier({ siteId: "tickets-demo.lemma.id" });

// In your request handler — the client posts presentation from
// result.presentation returned by IsHumanVerifier.verify()
app.post("/api/reserve", async (req, res) => {
  const result = await verifier.verify(req.body.presentation);
  if (!result.ok) return res.status(401).json({ error: result.reason });
  // result.ppid is the cryptographically-bound site-scoped identifier
  await reserveTicketsFor(result.ppid);
  res.json({ ok: true });
});
```

## What gets checked

For every `verify()` call, all of the following pass locally with no
network calls:

1. Trust list signature (root of trust, refreshed periodically).
2. Bloom snapshot signature + content hash.
3. Credential `proof.signatureValueWeb` Ed25519 signature against a trusted
   issuer pubkey.
4. `claims.isHuman` is true.
5. `claims.siteId` equals the configured `siteId` (no cross-site replay).
6. `claims.expiresAt` has not passed.
7. SHA-256(credential.id) is not in the Bloom revocation set.
8. (If a `session_assertion` is included) session signature verifies with the
   credential's `claims.site_signing_pubkey`, the assertion's `site_id`
   matches, and it has not expired.

## API

### `createVerifier(options)`

| option                | default                  | meaning                                                   |
|-----------------------|--------------------------|-----------------------------------------------------------|
| `siteId`              | **required**             | Expected site binding for credentials.                    |
| `lemmaOrigin`         | `"https://lemma.id"`     | Override for staging or self-hosted networks.             |
| `refreshMs`           | `900_000` (15 minutes)   | Max age of the signed bundle before re-fetching.          |
| `maxSessionAgeSeconds`| `86_400` (24 hours)      | Reject session presentations older than this.             |
| `fetch`               | `globalThis.fetch`       | Custom fetch (e.g. Cloudflare Workers `env.SOMETHING`).   |

Returns `{ verify(presentation), refresh() }`.

### `verifier.verify(presentation)`

Returns `Promise<VerifyResult>`:

```ts
type VerifyResult = {
  ok: boolean;
  reason: string;          // "valid" on success, error code on failure
  ppid?: string;           // site-scoped DID
  credentialId?: string;
  issuerDid?: string;
  boundSiteId?: string;
};
```

Failure reasons (non-exhaustive): `credential_missing`,
`browser_signature_missing`, `untrusted_issuer`, `invalid_signature`,
`not_ishuman`, `site_id_mismatch`, `expired`, `revoked`,
`invalid_session_signature`, `session_expired`, `session_too_old`,
`session_site_id_mismatch`, `trust_refresh_failed:<reason>`.

## Older Node / non-WebCrypto-Ed25519 runtimes

Node 18 lacks WebCrypto Ed25519. If the runtime can't import `Ed25519`,
this package falls back to `@noble/ed25519` (an optional dependency that
will be auto-installed by npm). No code changes required.

## License

Apache-2.0
