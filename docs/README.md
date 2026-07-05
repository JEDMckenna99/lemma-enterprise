# Lemma Documentation

lemma.id is a **private proof layer** for web platforms: site-private PPIDs for account continuity, signed backend verification, and **isHuman** assurance when one account must map to one verified human.

## Start here

| Document | Description | Audience |
|----------|-------------|----------|
| [Public docs](https://lemma.id/docs) | SDK, API reference, quickstart, revocation | Developers |
| [AI agent integration guide](integration/ISHUMAN_AGENT_INTEGRATION.md) | Guardrails, trust tiers, code patterns, checklist | AI coding agents |
| [llms.txt](https://lemma.id/llms.txt) | Pointer file for agents | AI coding agents |
| [AGENTS.md](../AGENTS.md) | Repo-root agent entrypoint | AI coding agents in this repo |

## What lemma.id provides

1. User creates or unlocks a passkey-backed lemma.id wallet.
2. Relying sites receive a stable, site-private PPID they can bind to their own user record.
3. Browser and backend verifiers check signed credentials locally (Ed25519 + revocation bloom).
4. Sites require isHuman only when policy needs IDV-backed uniqueness.
5. Optional site API keys enable server-side PPID blocks and site-scoped abuse response.

## Integration guides

| Document | Use case |
|----------|----------|
| [Simple Integration](integration/SIMPLE_INTEGRATION_GUIDE.md) | Website and backend login flow walkthrough |
| [Quick Start: Simple Login](integration/QUICK_START_SIMPLE_LOGIN.md) | User-login quickstart |
| [IAM-Only Integration](integration/IAM_ONLY_INTEGRATION_GUIDE.md) | IAM without proof-of-human |
| [Permission Lemmas Guide](integration/PERMISSION_LEMMAS_IAM_DEVELOPER_GUIDE.md) | Complete IAM developer reference |

## Architecture and security

| Document | Description |
|----------|-------------|
| [Wallet-First Architecture](architecture/ARCHITECTURE_WALLET_FIRST.md) | How wallet-first differs from OAuth |
| [Threat Model](security/THREAT_MODEL.md) | Security analysis and mitigations |
| [isHuman local-first outline](security/ISHUMAN_LOCAL_FIRST_IMPLEMENTATION_OUTLINE.md) | Local verification design |
| [Security Checklist](security/SECURITY_CHECKLIST.md) | Launch and audit verification checklist |
| [Error Codes](ERROR_CODES.md) | Error handling reference |

## Operations (internal)

| Document | Description |
|----------|-------------|
| [isHuman prod readiness](operations/ISHUMAN_PROD_READINESS_CHECKLIST.md) | Production go-live checklist |
| [Environment config](operations/ENVIRONMENT_CONFIG.md) | Environment variables |

Agent Ops (lemma-cli, Lemma Firewall, runtime control plane) documentation is operator-only and not part of public relying-site docs.

## Quick links

| Resource | URL |
|----------|-----|
| Live platform | https://lemma.id |
| Developer hub | https://lemma.id/developer |
| Live demo | https://lemma.id/demo/ishuman |
| Browser SDK | https://lemma.id/sdk/ishuman-verifier.js |

## Support

- Email: `support@lemma.id`
- Docs: [https://lemma.id/docs](https://lemma.id/docs)
