# Lemma Documentation (internal index)

lemma.id is **Sign in with lemma.id**: passwordless login with passkeys and site-private PPIDs, no user data to store, plus an optional **isHuman** step-up when one account must map to one verified human (same PPID across tiers).

This index classifies in-repo markdown for operators and contributors. Only **Public** entries are served anonymously at `https://lemma.id/docs/<path>`.

## Public (allowlisted URLs)

Served without auth per `api/public_docs.py`:

| URL | Source file | Description |
|-----|-------------|-------------|
| [integration/QUICK_START_SIMPLE_LOGIN.md](https://lemma.id/docs/integration/QUICK_START_SIMPLE_LOGIN.md) | `integration/QUICK_START_SIMPLE_LOGIN.md` | Sign in with lemma.id quickstart (passkey login) |
| [integration/SIMPLE_INTEGRATION_GUIDE.md](https://lemma.id/docs/integration/SIMPLE_INTEGRATION_GUIDE.md) | `integration/SIMPLE_INTEGRATION_GUIDE.md` | Full sign-in guide: sessions, account linking, sign-out |
| [integration/ISHUMAN_AGENT_INTEGRATION.md](https://lemma.id/docs/integration/ISHUMAN_AGENT_INTEGRATION.md) | `integration/ISHUMAN_AGENT_INTEGRATION.md` | Canonical relying-site integration contract |
| [integration/BROWSER_SUPPORT.md](https://lemma.id/docs/integration/BROWSER_SUPPORT.md) | `integration/BROWSER_SUPPORT.md` | Browser/passkey support matrix + SDK error codes |
| [ERROR_CODES.md](https://lemma.id/docs/ERROR_CODES.md) | `ERROR_CODES.md` | Error handling reference |
| [demo/README.md](https://lemma.id/docs/demo/README.md) | `demo/README.md` | Demo overview |
| [demo/PRESALE_DEMO_SCRIPT.md](https://lemma.id/docs/demo/PRESALE_DEMO_SCRIPT.md) | `demo/PRESALE_DEMO_SCRIPT.md` | Presale demo script |
| [product/PASSKEY_STAMP_INPUT_BURN.md](https://lemma.id/docs/product/PASSKEY_STAMP_INPUT_BURN.md) | `product/PASSKEY_STAMP_INPUT_BURN.md` | Assurance tiers and site-local input burn spec |

Rendered HTML docs hub (templates): [https://lemma.id/docs](https://lemma.id/docs)

## 1. Sign in with lemma.id (start here)

Free passwordless login; the default integration for relying sites.

| Document | Description | Audience |
|----------|-------------|----------|
| [Quick start: Sign in with lemma.id](integration/QUICK_START_SIMPLE_LOGIN.md) | Drop-in button, backend verify, sessions, testing | Developers |
| [Sign in with lemma.id — integration guide](integration/SIMPLE_INTEGRATION_GUIDE.md) | Architecture, account linking, sign-out, non-features | Developers |
| [Browser support + error codes](integration/BROWSER_SUPPORT.md) | Passkey/PRF matrix, stable SDK outcomes | Developers |
| [llms.txt](https://lemma.id/llms.txt) | Pointer file for agents | AI coding agents |

## 2. isHuman step-up (optional paid tier)

One verified human per account on the **same PPID**; request per action with `requiredAssurance: 'ishuman'`.

| Document | Description |
|----------|-------------|
| [ISHUMAN Agent Integration Guide](integration/ISHUMAN_AGENT_INTEGRATION.md) | Canonical contract: guardrails, trust tiers, abuse APIs, checklist |
| [Assurance tiers + input burn](product/PASSKEY_STAMP_INPUT_BURN.md) | One PPID, `passkey` vs `ishuman`, site-local burn policy |

## 3. Reference

| Document | Description |
|----------|-------------|
| [ERROR_CODES.md](ERROR_CODES.md) | API + SDK error reference |
| [AGENTS.md](../AGENTS.md) | Repo-root agent entrypoint |
| [lemma.id Presentation Model](product/LEMMA_ID_PRESENTATION_MODEL.md) | Platform identity + permission contract (internal) |

**Runtime `siteId`:** canonical hostname (e.g. `app.example.com`), not internal `site_...` dashboard IDs.

## Legacy (superseded)

Retained for historical reference. Do not use for new integrations.

| Document | Notes |
|----------|-------|
| [IAM-Only Integration](integration/IAM_ONLY_INTEGRATION_GUIDE.md) | IAM without proof-of-human |
| [Permission Lemmas Guide](integration/PERMISSION_LEMMAS_IAM_DEVELOPER_GUIDE.md) | IAM developer reference |
| [Integration Guide](integration/INTEGRATION_GUIDE.md) | Wallet-based user authentication (old redirect flow) |

All superseded by the sign-in docs above and the [ISHUMAN Agent Integration Guide](integration/ISHUMAN_AGENT_INTEGRATION.md).

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
| Sign-in button | https://lemma.id/sdk/lemma-signin.js |

## Support

- Email: `support@lemma.id`
- Docs: [https://lemma.id/docs](https://lemma.id/docs)
