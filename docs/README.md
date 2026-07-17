# Lemma Documentation (internal index)

lemma.id is a **private proof layer** for web platforms: site-private PPIDs for account continuity, signed backend verification, and **isHuman** assurance when one account must map to one verified human.

This index classifies in-repo markdown for operators and contributors. Only **Public** entries are served anonymously at `https://lemma.id/docs/<path>`.

## Public (allowlisted URLs)

Served without auth per `api/public_docs.py`:

| URL | Source file | Description |
|-----|-------------|-------------|
| [integration/ISHUMAN_AGENT_INTEGRATION.md](https://lemma.id/docs/integration/ISHUMAN_AGENT_INTEGRATION.md) | `integration/ISHUMAN_AGENT_INTEGRATION.md` | Canonical relying-site integration guide |
| [ERROR_CODES.md](https://lemma.id/docs/ERROR_CODES.md) | `ERROR_CODES.md` | Error handling reference |
| [demo/README.md](https://lemma.id/docs/demo/README.md) | `demo/README.md` | Demo overview |
| [demo/PRESALE_DEMO_SCRIPT.md](https://lemma.id/docs/demo/PRESALE_DEMO_SCRIPT.md) | `demo/PRESALE_DEMO_SCRIPT.md` | Presale demo script |
| [product/PASSKEY_STAMP_INPUT_BURN.md](https://lemma.id/docs/product/PASSKEY_STAMP_INPUT_BURN.md) | `product/PASSKEY_STAMP_INPUT_BURN.md` | Passkey stamp input burn spec |

Rendered HTML docs hub (templates): [https://lemma.id/docs](https://lemma.id/docs)

## Canonical integration

Start here for relying-site and agent integration work:

| Document | Description | Audience |
|----------|-------------|----------|
| [ISHUMAN Agent Integration Guide](integration/ISHUMAN_AGENT_INTEGRATION.md) | Guardrails, trust tiers, code patterns, checklist | Developers, AI coding agents |
| [AGENTS.md](../AGENTS.md) | Repo-root agent entrypoint | AI coding agents in this repo |
| [llms.txt](https://lemma.id/llms.txt) | Pointer file for agents | AI coding agents |
| [Public docs hub](https://lemma.id/docs) | SDK, API reference, quickstart, revocation | Developers |

**Runtime `siteId`:** canonical hostname (e.g. `app.example.com`), not internal `site_...` dashboard IDs.

## Legacy (superseded)

Retained for historical reference. Do not use for new integrations.

| Document | Notes |
|----------|-------|
| [Simple Integration](integration/SIMPLE_INTEGRATION_GUIDE.md) | Wallet redirect login walkthrough |
| [Quick Start: Simple Login](integration/QUICK_START_SIMPLE_LOGIN.md) | End-user login quickstart |
| [IAM-Only Integration](integration/IAM_ONLY_INTEGRATION_GUIDE.md) | IAM without proof-of-human |
| [Permission Lemmas Guide](integration/PERMISSION_LEMMAS_IAM_DEVELOPER_GUIDE.md) | IAM developer reference |
| [Integration Guide](integration/INTEGRATION_GUIDE.md) | Wallet-based user authentication |

All superseded by [ISHUMAN Agent Integration Guide](integration/ISHUMAN_AGENT_INTEGRATION.md).

## Operator-only

Not for relying-site integrators. Requires repo access and/or platform credentials.

| Area | Examples |
|------|----------|
| Agent Ops | [AGENT_OPS_READINESS.md](AGENT_OPS_READINESS.md), [FIREWALL_QUICKSTART.md](FIREWALL_QUICKSTART.md), `docs/openclaw/` |
| Operations | [operations/ENVIRONMENT_CONFIG.md](operations/ENVIRONMENT_CONFIG.md), [operations/ISHUMAN_PROD_READINESS_CHECKLIST.md](operations/ISHUMAN_PROD_READINESS_CHECKLIST.md), deploy and incident runbooks |
| Security (internal) | [security/THREAT_MODEL.md](security/THREAT_MODEL.md), [security/SECURITY_CHECKLIST.md](security/SECURITY_CHECKLIST.md) |
| Architecture (internal) | [architecture/ARCHITECTURE_WALLET_FIRST.md](architecture/ARCHITECTURE_WALLET_FIRST.md), trust-core and privacy specs |
| Status / plans / research | `docs/status/`, `docs/plans/`, `docs/research/` |

Agent Ops (lemma-cli, Lemma Firewall, runtime control plane) is operator-only and not part of public relying-site docs.

## Draft / unimplemented

Internal product proposals, **not shipped**. Do not link from integrator-facing docs.

| Document | Status |
|----------|--------|
| [Compartmentalized Personas](product/COMPARTMENTALIZED_PERSONAS.md) | Design sketch |
| [Agent Acting PPID](product/AGENT_ACTING_PPID.md) | Design sketch |
| [Human-Backed Agent Passport](product/HUMAN_BACKED_AGENT_PASSPORT.md) | Product spec draft |

## Architecture and security (internal reference)

| Document | Description |
|----------|-------------|
| [Wallet-First Architecture](architecture/ARCHITECTURE_WALLET_FIRST.md) | How wallet-first differs from OAuth |
| [lemma.id Presentation Model](product/LEMMA_ID_PRESENTATION_MODEL.md) | Platform identity + permission contract |
| [Threat Model](security/THREAT_MODEL.md) | Security analysis and mitigations |
| [isHuman local-first outline](security/ISHUMAN_LOCAL_FIRST_IMPLEMENTATION_OUTLINE.md) | Local verification design |
| [Security Checklist](security/SECURITY_CHECKLIST.md) | Launch and audit verification checklist |

## Quick links

| Resource | URL |
|----------|-----|
| Live platform | https://lemma.id |
| Developer hub | https://lemma.id/developer |
| Live demo | https://lemma.id/demo |
| Browser SDK | https://lemma.id/sdk/proof-verifier.js |

## Support

- Email: `support@lemma.id`
- Docs: [https://lemma.id/docs](https://lemma.id/docs)
