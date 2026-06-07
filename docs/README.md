# Lemma Documentation

Lemma is a proof-first Agent Ops authorization system with a local-first OpenClaw starter path.

## Start Here

### Personal OpenClaw

If you want the practical beginner flow, start here:

| Document | Description | Time |
|----------|-------------|------|
| [OpenClaw Personal Quickstart](openclaw/PERSONAL_QUICKSTART.md) | Install one CLI, run one command, approve once, see allow and kill-to-deny | 5-10 min |
| [What Lemma Adds Beyond OpenClaw](openclaw/WHAT_LEMMA_ADDS_BEYOND_OPENCLAW.md) | Plain-language explanation of the extra controls Lemma provides | 5 min |
| [CLI README](CLI_PYPI_README.md) | Packaged CLI install and command summary | Reference |

### Enterprise And Advanced Controls

If you need policy lifecycle, exports, or org-level controls:

| Document | Description | Time |
|----------|-------------|------|
| [OpenClaw Operator Runbook](operations/OPENCLAW_OPERATOR_RUNBOOK.md) | Runtime onboarding, incident flows, and kill/revoke drills | 10 min |
| [Developer Auth Contract](api/DEVELOPER_AUTH_CONTRACT_V1.md) | Proof-first contract for advanced agent/runtime integrations | 10 min |
| [Agent Ops Readiness](AGENT_OPS_READINESS.md) | Build/test tracker for production controls | Reference |
| [Prompt Injection Ontology](security/AGENT_PROOF_ONTOLOGY_PROMPT_INJECTION.md) | Trust-state and taint-epoch containment model | Reference |

## What Lemma Does

1. Runtime onboarding links agent runtimes to PPID-bound controls.
2. Proof-native checks enforce scope, resource, and risk at request time.
3. Agent Ops controls provide kill switches, decision logs, exports, and alerts.
4. Prompt-injection containment is modeled with trust-state and taint-epoch policy.
5. lemma.id proof of humanity issues reusable human credentials with site-private PPID derivation and two-tier revocation controls.

## Architecture And Security

| Document | Description |
|----------|-------------|
| [Wallet-First Architecture](architecture/ARCHITECTURE_WALLET_FIRST.md) | How wallet-first differs from OAuth |
| [Whitepaper](architecture/WHITEPAPER_DIGITAL_LEMMAS.md) | Complete technical specification |
| [Protocol Design](protocol/PROTOCOL_DESIGN.md) | Core verification protocol |
| [Threat Model](security/THREAT_MODEL.md) | Security analysis and mitigations |
| [Security Review Package](security/SECURITY_REVIEW_PACKAGE.md) | Comprehensive security documentation |
| [Security Checklist](security/SECURITY_CHECKLIST.md) | Launch and audit verification checklist |
| [Error Codes](ERROR_CODES.md) | Error handling reference |

## Other Guides

| Document | Use Case |
|----------|----------|
| [Simple Integration](integration/SIMPLE_INTEGRATION_GUIDE.md) | Website and backend login flow walkthrough |
| [Quick Start: Simple Login](integration/QUICK_START_SIMPLE_LOGIN.md) | User-login quickstart, distinct from agent runtime auth |
| [IAM-Only Integration](integration/IAM_ONLY_INTEGRATION_GUIDE.md) | IAM without Proof-of-Human |
| [Permission Lemmas Guide](integration/PERMISSION_LEMMAS_IAM_DEVELOPER_GUIDE.md) | Complete IAM developer reference |
| [lemma.id proof of humanity](https://lemma.id/docs) | SDK and API reference for proof-of-humanity integration |
| [Agent Ops](https://lemma.id/docs/agents) | CLI, Lemma Firewall, and runtime control-plane documentation |
| [KMS Setup Guide](operations/KMS_SETUP_GUIDE.md) | AWS KMS configuration for key management |
| [CLI Release Checklist](operations/CLI_RELEASE_CHECKLIST.md) | Packaging and release workflow |
| [Launch Status](status/GA_GATE_STATUS.md) | Current readiness snapshot |

## Quick Links

| Resource | URL |
|----------|-----|
| Live Platform | https://lemma.id |
| Developer Platform | https://lemma.id/platform |
| Wallet | https://lemma.id/wallet |
| API Status | https://status.lemma.id |

## Support

- Email: `support@lemma.id`
- Docs: [https://lemma.id/docs](https://lemma.id/docs)
