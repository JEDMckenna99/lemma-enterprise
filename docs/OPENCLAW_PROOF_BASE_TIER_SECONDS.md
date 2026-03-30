# OpenClaw Proof-First Setup (Seconds)

This document covers the manual proof-first OpenClaw setup path.

If you want the public beginner flow, use:

```bash
lemma setup-openclaw --api-base https://lemma.id
```

That one command handles browser approval, runtime connect, firewall start, one allowed action, and kill-to-deny verification.

## Public Starter Path

```bash
lemma setup-openclaw --api-base https://lemma.id
```

The public starter path uses a wallet-issued full credential under the hood and sends `X-Lemma-Credential` on protected requests.
Use the proof-chain contract (`X-Lemma-Proof` + `X-Lemma-PoP`) only for advanced integrations and custom runtimes.

## Manual Advanced Path

This is the fastest manual setup path using the Lemma Authz API and CLI only.
No MCP wiring required.

### 1) Run proof-first bootstrap

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_lemma_firewall_authz_seconds.ps1 `
  -LemmaUrl "https://lemma.id"
```

Default behavior (no `-CredentialFile`) opens browser wallet approval, then auto-mints
and saves `.lemma-proof.json`.

You can still pass an existing file explicitly:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_lemma_firewall_authz_seconds.ps1 `
  -LemmaUrl "https://lemma.id" `
  -CredentialFile ".\.lemma-proof.json"
```

Break-glass only (root recovery path; explicit opt-in):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_lemma_firewall_authz_seconds.ps1 `
  -LemmaUrl "https://lemma.id" `
  -UseBreakGlassSelfIssue `
  -PlatformApiKey "lemma_api_..." `
  -UserEmail "you@company.com"
```

### 2) What it does

- Self-issues a Lemma credential proof (or uses `-CredentialFile` if provided).
- Validates proof exchange through `POST /api/auth/exchange-proof`.
- Runs `lemma_cli.py authz-latency` in proof mode to smoke test the path.
- Saves proof to `.lemma-proof.json` for reuse.
- Auto-patches OpenClaw config with:
  - `env.vars.LEMMA_BASE_URL`
  - `env.vars.LEMMA_PROOF_FILE`
- Uses `lemma runtime-onboard` to register runtime defaults tied to wallet identity.

### 2.5) Connect runtime (recommended)

```powershell
python .\scripts\lemma_cli.py runtime-onboard `
  --api-base "https://lemma.id" `
  --runtime-id "openclaw-default" `
  --agent-id "main" `
  --workspace-id "default" `
  --display-name "OpenClaw Runtime" `
  --json
```

### 3) Start AIM firewall in proof mode (optional)

```powershell
$env:LEMMA_BASE_URL = "https://lemma.id"
$env:LEMMA_PROOF_FILE = ".\.lemma-proof.json"
python .\scripts\lemma_firewall.py
```

The firewall now accepts `X-Lemma-Credential` directly and logs activity to AIM
without requiring `X-Agent-Token`.

## Legacy note

- Token/MCP setup is compatibility-only.
- New integrations should use proof-first setup and runtime headers:
  - `X-Lemma-Credential`
  - optional `X-Lemma-PoP`

