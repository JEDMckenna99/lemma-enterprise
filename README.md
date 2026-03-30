# Lemma.id

**Local-first authorization and dynamic trust for AI agents.**

Lemma.id is a credential-based authorization platform that gives AI agents scoped, cryptographically verifiable permissions — and automatically contains them when trust degrades.

## Problem

AI agents that call APIs, read files, and execute code operate on static permissions. Once granted access, nothing prevents a prompt-injected or misbehaving agent from escalating — there's no mechanism to *revoke authority mid-session* based on what the agent just did.

## Approach

Lemma.id introduces **dynamic trust degradation**: a local HTTP firewall that sits between the agent and external services, enforcing scoped credentials with proof-of-possession and a taint epoch that invalidates an agent's authority the moment it ingests untrusted content.

### Key capabilities

- **Scoped credentials** — Ed25519-signed proofs with `read`, `write`, `admin` scopes bound to specific APIs and actions
- **Proof-of-possession** — every request cryptographically bound to method, path, body hash, and nonce (replay-proof)
- **Taint epoch** — the firewall bumps a monotonic counter when the agent touches external content; stale credentials are rejected until a human re-approves
- **Monotonic attenuation** — delegated credentials can only narrow authority, never widen it
- **Risk-tiered freshness** — high-risk actions require more recent revocation data than low-risk reads
- **Action taxonomy** — 24 canonical actions with predefined risk tiers (`file.read`, `shell.exec`, `api.call.write`, etc.)
- **Full audit trail** — every allow/deny decision logged in JSONL for post-session replay

## Architecture

```
Agent ──► Lemma Firewall (local HTTP proxy)
              │
              ├─ credential verification (Ed25519 + scope check)
              ├─ taint epoch enforcement
              ├─ risk-tier freshness gate
              ├─ action taxonomy mapping
              └─ audit log (JSONL)
              │
              ▼
         Upstream APIs (scoped, proxied)
```

### Core components

| Component | Path | Description |
|-----------|------|-------------|
| Firewall | `scripts/lemma_firewall.py` | Local proxy enforcing policy, taint, and auth |
| CLI | `scripts/lemma_cli.py` | Session management, credential bootstrapping |
| Crypto engine | `lemma-crypto/` | Rust Ed25519 signing and verification |
| Action taxonomy | `api/action_taxonomy.py` | Canonical actions, risk tiers, scope mapping |
| Proof chain verifier | `api/authz/verifier.py` | Monotonic attenuation and delegation chain validation |
| Replay protection | `api/authz/replay.py` | Nonce-based PoP with request binding |
| Policy engine | `api/authz/mode_policy.py` | Auth mode evaluation (bearer / proof-required) |
| Platform API | `app.py` | Flask app with IAM, wallet, and credential endpoints |
| MCP server | `mcp-server/` | Model Context Protocol integration for agent hosts |

## Quick start

### Run the prompt injection containment demo

```bash
python3 scripts/run_prompt_injection_containment_demo.py
```

This self-contained demo simulates an agent that:
1. Reads an internal API (allowed)
2. Writes data (allowed, no taint)
3. Fetches external content containing hidden instructions (allowed, taint epoch bumps)
4. Attempts a privileged write (denied — credential taint epoch is stale)
5. Gets human re-approval with fresh credential (allowed)

### Run the CLI

```bash
pip install -e .
lemma start --scope read,write --policy default
lemma replay
lemma stop
```

### Run tests

```bash
python3 -m pytest tests/ -q
```

## Repo layout

```
api/            API endpoints, IAM, credential issuance
api/authz/      Authorization: proof chains, replay, freshness, mode policy
auth/           Decorators, session management, rate limiting
billing/        Stripe integration (optional)
lemma-crypto/   Rust native extension (Ed25519, HPKE)
scripts/        CLI, firewall, demo scripts
sdk/            Python and Node integration SDKs
mcp-server/     Model Context Protocol server
templates/      Web UI
tests/          Test suites
docs/           Architecture, protocol design, threat model
```

## Configuration

All secrets are loaded from environment variables. No credentials are committed to this repository.

Required for full platform operation:
- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis for session/revocation cache
- `JWT_SIGNING_SECRET` — signing key for access tokens

Optional:
- `STRIPE_SECRET_KEY` — billing integration
- `LEMMA_AGENT_TOKEN` — agent credential for MCP

The local CLI and firewall run standalone without any of these.

## Tech stack

- **Python 3.11+** / Flask — API and firewall
- **Rust** — cryptographic verification engine (Ed25519, HPKE)
- **PostgreSQL** — persistent storage
- **Redis** — revocation sync, rate limiting
- **Docker Compose** — local development stack

## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## License

Apache-2.0 — see [LICENSE](LICENSE).
