# Five-minute offline demo

Run the verifier accept/reject path with **no network**, **no API keys**, and
**no WebAuthn**. Uses the package testing helpers shipped in `packages/`.

## Prerequisites

- Python 3.10+ **or** Node.js 18+
- From the `oss/` directory (paths below assume you are in `oss/`)

## Run

```bash
# Python
python demo/five_minute.py

# JavaScript (Node 18+)
node demo/five_minute.mjs
```

Expected output: three steps — mint, verify accept, tamper reject — each marked
`PASS`.

## What it demonstrates

1. **Mint** — offline test issuer signs a presentation for `siteId=localhost`.
2. **Accept** — local verifier checks signature, site binding, and assurance.
3. **Reject** — tampering `claims.siteId` fails closed with `site_id_mismatch`.

## Next steps

- Read [`../DESIGN_DECISIONS.md`](../DESIGN_DECISIONS.md) for PPIDs, Ed25519,
  pinned roots, and Bloom snapshots.
- Run cross-language fixtures: `pytest tests/ -q` (from `oss/`).
- For a live browser popup flow, see lemma.id integration docs and the monorepo
  `examples/` directory (Flask, Express, Next.js) — not copied here to keep
  this tree verification-focused.
