# Lemma Documentation (internal index)

lemma.id is a **local-first proof layer** for relying sites: verify a signed
presentation and enforce policy on a site-private `ppid` + assurance level.
Optional **isHuman** step-up (IDV-backed person assurance on the same PPID;
document uniqueness, not biometric unique-human),
action stamps, and site-block for continuity under abuse. Passkey unlock mints
presentations; optional session cookies are an appendix, not the headline.

This index classifies in-repo markdown for operators and contributors. Only **Public** entries are served anonymously at `https://lemma.id/docs/<path>`.

## Public (allowlisted URLs)

Served without auth per `api/public_docs.py`:

| URL | Source file | Description |
|-----|-------------|-------------|
| [integration/CONTINUITY_AND_ABUSE.md](https://lemma.id/docs/integration/CONTINUITY_AND_ABUSE.md) | `integration/CONTINUITY_AND_ABUSE.md` | Continuity, assurance, site-block, stamps: start here |
| [integration/QUICK_START_SIMPLE_LOGIN.md](https://lemma.id/docs/integration/QUICK_START_SIMPLE_LOGIN.md) | `integration/QUICK_START_SIMPLE_LOGIN.md` | Quick start: verify a lemma proof / gate an action |
| [integration/SIMPLE_INTEGRATION_GUIDE.md](https://lemma.id/docs/integration/SIMPLE_INTEGRATION_GUIDE.md) | `integration/SIMPLE_INTEGRATION_GUIDE.md` | Full guide: assurance, stamps, abuse, optional sessions |
| [integration/SIGN_IN_TRUST_AND_RECOVERY.md](https://lemma.id/docs/integration/SIGN_IN_TRUST_AND_RECOVERY.md) | `integration/SIGN_IN_TRUST_AND_RECOVERY.md` | Trust, recovery, availability for the proof dependency |
| [integration/ISHUMAN_AGENT_INTEGRATION.md](https://lemma.id/docs/integration/ISHUMAN_AGENT_INTEGRATION.md) | `integration/ISHUMAN_AGENT_INTEGRATION.md` | Canonical relying-site integration contract |
| [integration/BROWSER_SUPPORT.md](https://lemma.id/docs/integration/BROWSER_SUPPORT.md) | `integration/BROWSER_SUPPORT.md` | Browser/passkey support matrix + SDK error codes |
| [ERROR_CODES.md](https://lemma.id/docs/ERROR_CODES.md) | `ERROR_CODES.md` | Error handling reference |
| [demo/README.md](https://lemma.id/docs/demo/README.md) | `demo/README.md` | Demo overview |
| [demo/PRESALE_DEMO_SCRIPT.md](https://lemma.id/docs/demo/PRESALE_DEMO_SCRIPT.md) | `demo/PRESALE_DEMO_SCRIPT.md` | Presale demo script |
| [product/PASSKEY_STAMP_INPUT_BURN.md](https://lemma.id/docs/product/PASSKEY_STAMP_INPUT_BURN.md) | `product/PASSKEY_STAMP_INPUT_BURN.md` | Assurance tiers and site-local input burn spec |

Rendered HTML docs hub (templates): [https://lemma.id/docs](https://lemma.id/docs)

## 1. Continuity & enforcement (start here)

Site-private person handle, assurance ladder, stamps, and abuse controls.

| Document | Description | Audience |
|----------|-------------|----------|
| [Continuity & abuse](integration/CONTINUITY_AND_ABUSE.md) | PPID, assurance, site-block, stamps, keep-your-login pattern | Developers |
| [Quick start: verify a lemma proof](integration/QUICK_START_SIMPLE_LOGIN.md) | Gate an action, backend verify, testing | Developers |
| [Integration guide](integration/SIMPLE_INTEGRATION_GUIDE.md) | Architecture, assurance, stamps, abuse, optional sessions | Developers |
| [Trust, recovery & availability](integration/SIGN_IN_TRUST_AND_RECOVERY.md) | Proof dependency failure modes; "no blockchain" | Developers |
| [ISHUMAN Agent Integration Guide](integration/ISHUMAN_AGENT_INTEGRATION.md) | Canonical contract: guardrails, trust tiers, checklist | AI agents / developers |
| [Assurance tiers + input burn](product/PASSKEY_STAMP_INPUT_BURN.md) | One PPID, `passkey` vs `ishuman`, site-local burn policy | Developers |
| [llms.txt](https://lemma.id/llms.txt) | Pointer file for agents | AI coding agents |

## 2. isHuman step-up (Sybil-sensitive actions)

IDV-backed person assurance on the **same PPID** (document uniqueness); request
per action with `requiredAssurance: 'ishuman'`. Uniqueness bounds (internal):
[HUMAN_UNIQUENESS_BOUNDS.md](security/HUMAN_UNIQUENESS_BOUNDS.md).

| Document | Description |
|----------|-------------|
| [ISHUMAN Agent Integration Guide](integration/ISHUMAN_AGENT_INTEGRATION.md) | Canonical contract: assurance policy, abuse APIs, stamps |
| [Assurance tiers + input burn](product/PASSKEY_STAMP_INPUT_BURN.md) | One PPID, `passkey` vs `ishuman`, site-local burn policy |
| [Human uniqueness bounds](security/HUMAN_UNIQUENESS_BOUNDS.md) | Internal: document uniqueness vs unique-human claims |

## 3. Optional: sessions & sign-in UX

Issue your own session cookie from a verified presentation if you want passwordless login.

| Document | Description |
|----------|-------------|
| [Integration guide: sessions appendix](integration/SIMPLE_INTEGRATION_GUIDE.md) | Session cookies, account linking, sign-out |
| [Quick start: mint a presentation](integration/QUICK_START_SIMPLE_LOGIN.md) | `<lemma-signin>` drop-in for presentation mint |

## 4. Reference

| Document | Description |
|----------|-------------|
| [Browser support + error codes](integration/BROWSER_SUPPORT.md) | Passkey/PRF matrix, stable SDK outcomes |
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
| [Integration Guide](integration/INTEGRATION_GUIDE.md) | lemma.id-based user authentication, legacy `LemmaWallet` SDK (old redirect flow) |

All superseded by the continuity docs above and the [ISHUMAN Agent Integration Guide](integration/ISHUMAN_AGENT_INTEGRATION.md).

## Operator-only

Not for relying-site integrators. Requires repo access and/or platform credentials.

| Area | Examples |
|------|----------|
| Agent Ops | [AGENT_OPS_READINESS.md](AGENT_OPS_READINESS.md), [FIREWALL_QUICKSTART.md](FIREWALL_QUICKSTART.md), `docs/openclaw/` |
| Operations | [operations/ENVIRONMENT_CONFIG.md](operations/ENVIRONMENT_CONFIG.md), [operations/ISHUMAN_PROD_READINESS_CHECKLIST.md](operations/ISHUMAN_PROD_READINESS_CHECKLIST.md), deploy and incident runbooks |
| Security (internal) | [security/THREAT_MODEL.md](security/THREAT_MODEL.md), [security/SECURITY_CHECKLIST.md](security/SECURITY_CHECKLIST.md) |
| Architecture (internal) | [architecture/ARCHITECTURE_WALLET_FIRST.md](architecture/ARCHITECTURE_WALLET_FIRST.md) (historical filename; product noun is lemma.id), trust-core and privacy specs |
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
| [Identity construction](architecture/IDENTITY_CONSTRUCTION.md) | Internal: IDV → document root → assigned person → PPID → human proof |
| [lemma.id-first architecture (historical doc name)](architecture/ARCHITECTURE_WALLET_FIRST.md) | How local-credential auth differs from OAuth; see doc banner for terminology |
| [lemma.id Presentation Model](product/LEMMA_ID_PRESENTATION_MODEL.md) | Platform identity + permission contract |
| [Browser storage contract](security/LEMMA_ID_BROWSER_STORAGE_CONTRACT.md) | Canonical IndexedDB / localStorage / cookie inventory + encryption rules |
| [Threat Model](security/THREAT_MODEL.md) | Security analysis and mitigations |
| [isHuman local-first outline](security/ISHUMAN_LOCAL_FIRST_IMPLEMENTATION_OUTLINE.md) | Local verification design (historical phases; storage inventory superseded) |
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
