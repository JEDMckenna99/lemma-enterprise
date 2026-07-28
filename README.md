# lemma.id

**Passwordless login with no user data to store — and bans that stick.**

lemma.id is **Sign in with lemma.id**: passkey login that gives your site a stable, site-private PPID as the account key, with no usernames, passwords, or email collection and signed local backend verification. The optional **isHuman** step-up tier binds one verified human per account on the same PPID, so bans survive email, SIM, device, and IP rotation — without your site storing ID documents or building a KYC stack.

- **Live:** https://lemma.id · **Docs:** https://lemma.id/docs · **AI integration guide:** [`docs/integration/ISHUMAN_AGENT_INTEGRATION.md`](docs/integration/ISHUMAN_AGENT_INTEGRATION.md)

## The problem

Fraud is an economic problem, not a tech one. The industry can already detect abuse, what it can't do is make a ban stick when the next account is free. Login tells you which account signed in, not whether the same abuser came back as a new account. Bot detection finds suspicious behavior but gives you no durable enforcement handle. Direct KYC works but leaves you holding identity documents and breach liability.

## How it works

**Bind → Detect → Enforce.** lemma.id doesn't replace your login, fraud detection, or moderation, it gives those systems an enforcement handle that survives credential rotation.

1. A user unlocks their passkey-protected lemma.id wallet in the browser (optional identity-verification step-up when your policy requires **isHuman**).
2. Your site receives a **site-private PPID** (pairwise pseudonymous ID, different per site, so no cross-site tracking) and a **signed presentation**.
3. Your backend verifies the presentation **locally** (Ed25519, ~1ms), no per-request call to lemma.id, no rate limits, no meter.
4. When you ban a PPID, the ban is persistent: fresh IDV, wallet recovery, and credential rotation do not clear it.

### Quick integration

```html
<script src="https://lemma.id/sdk/proof-verifier.js"></script>
<script>
  const verifier = new ProofVerifier({ siteId: 'app.example.com' });
  const { ok, presentation } = await verifier.verifyForBackend({ autoProvision: true });
  if (!ok) throw new Error('not_verified');
  await fetch('/api/signup', { method: 'POST', body: JSON.stringify({ presentation }) });
</script>
```

The legacy `ishuman-verifier.js` URL and `IsHumanVerifier` class remain supported
as compatibility aliases.

Verify on the server with `@lemma.id/proof-verifier` (Node) or `lemma_proof_verifier.py` (Python). For signup and account creation, always verify the signed `presentation` server-side, never trust a bare client `ppid`.

### Assurance tiers

| Tier | What it proves | Sybil-resistant? |
|------|----------------|------------------|
| Passkey continuity | Same wallet returning | No |
| Signed presentation | Cryptographically verified proof | Depends on assurance level |
| **isHuman** | One verified human per account (IDV-backed) | Yes, bans survive rotation |

## Pricing

| Line item | Price |
|-----------|-------|
| Proof binding (identity verification included) | $0.50/user · one-time |
| MAU renewal | $0.03/user/month, starting the month after binding |
| Doubt re-entry (fresh IDV at cost) | $0.33/user |
| Local verification | $0 · unlimited, never metered |

Basic `verify()` gating requires no registration or API key. Site API keys unlock abuse controls: persistent site blocks, unblocks, and temporary doubt challenges.

## Agent Ops (operator-only)

The same wallet and proof infrastructure extends to AI agents. **Agent Ops**: lemma-cli, the Lemma Firewall, and the MCP server: gives agent operators scoped, cryptographically verifiable permissions with dynamic trust degradation:

- **Scoped credentials**: Ed25519-signed proofs with `read`, `write`, `admin` scopes bound to specific APIs and actions
- **Proof-of-possession**: every request cryptographically bound to method, path, body hash, and nonce (replay-proof)
- **Taint epoch**: the firewall bumps a monotonic counter when the agent ingests untrusted content; stale credentials are rejected until a human re-approves
- **Monotonic attenuation**: delegated credentials can only narrow authority, never widen it
- **Full audit trail**: every allow/deny decision logged in JSONL for post-session replay

Agent Ops is operator-only tooling, it is **not** part of relying-site integration. The roadmap connects the two: human-backed agent passports and site-private agent acting IDs rooted in the same verified-human wallet (see [`docs/product/HUMAN_BACKED_AGENT_PASSPORT.md`](docs/product/HUMAN_BACKED_AGENT_PASSPORT.md) and [`docs/product/AGENT_ACTING_PPID.md`](docs/product/AGENT_ACTING_PPID.md)).

Try the prompt-injection containment demo:

```bash
python3 scripts/run_prompt_injection_containment_demo.py
```

## Repo layout

```
api/            API endpoints, IAM, credential issuance
api/authz/      Authorization: proof chains, replay, freshness, mode policy
auth/           Decorators, session management, rate limiting
billing/        Stripe metered billing
lemma-crypto/   Rust native extension (Ed25519, HPKE)
scripts/        CLI, firewall, demo scripts
sdk/            Python and Node integration SDKs
mcp-server/     Model Context Protocol server
templates/      Web UI
tests/          Test suites
docs/           Architecture, protocol design, threat model
```

## Development

```bash
pip install -e .
python3 -m pytest tests/ -q
```

All secrets are loaded from environment variables; no credentials are committed to this repository.

Required for full platform operation:
- `DATABASE_URL`, PostgreSQL connection string
- `REDIS_URL`, Redis for session/revocation cache
- `JWT_SIGNING_SECRET`, signing key for access tokens

Optional:
- `STRIPE_SECRET_KEY`, billing integration
- `LEMMA_AGENT_TOKEN`, agent credential for MCP

The local CLI and firewall run standalone without any of these.

## Tech stack

- **Python 3.11+** / Flask, API and platform
- **Rust**: cryptographic verification engine (Ed25519, HPKE)
- **PostgreSQL**: persistent storage
- **Redis**: revocation sync, rate limiting
- **Docker Compose**: local development stack

## Privacy model

- Document images, selfies, and legal names are never persisted on the isHuman path.
- Sites receive only a site-private PPID and a signed human claim, no cross-site identifier.
- Person roots are stored as KMS-encrypted ciphertext; production fails closed without KMS.

See [`docs/architecture/PRIVACY_ARCHITECTURE.md`](docs/architecture/PRIVACY_ARCHITECTURE.md).

## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## License

Apache-2.0, see [LICENSE](LICENSE).
