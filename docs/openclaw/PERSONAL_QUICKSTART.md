# OpenClaw Personal Quickstart

This is the shortest path to a safe local OpenClaw setup with Lemma.

## Outcome

When this works, you should be able to:

- install one CLI
- run one command
- approve once in the browser
- see the local firewall start
- see one protected action succeed
- kill the runtime and see the next protected action get denied

## 1. Install The CLI

```bash
pip install git+https://github.com/JEDMckenna99/lemma-enterprise.git
```

Or for local development:

```bash
git clone https://github.com/JEDMckenna99/lemma-enterprise.git
cd lemma-enterprise/lemma-rebuild
pip install -e .
```

## 2. Run The OpenClaw Starter Flow

```bash
lemma setup-openclaw --api-base https://lemma.id
```

What this command does:

1. Opens one browser approval flow for wallet control-plane access
2. Issues a starter-safe OpenClaw proof
3. Connects your runtime to Lemma controls
4. Starts the local firewall
5. Runs one protected action through the firewall and verifies it is allowed
6. Kills the runtime and verifies the next protected action is denied
7. Prints a final `SAFE`, `DEGRADED`, or `UNSAFE` result

## Beginner Auth Contract

The starter path uses a wallet-issued full credential and the local firewall sends `X-Lemma-Credential` on protected requests.

If you are building a custom advanced integration, move up to the proof-native contract:

- `X-Lemma-Proof`
- `X-Lemma-PoP`

## 3. Re-check Local Safety

```bash
lemma safety-status --firewall-url http://127.0.0.1:8787
```

## 4. What To Look For

Success should look like:

- `Browser approval: PASS`
- `Firewall: PASS`
- `Protected action: PASS`
- `Kill check: PASS (deny observed after kill)`
- `Safety status: SAFE`

If the final status is not `SAFE`, the CLI prints next steps in plain language.

## 5. What Gets Written Locally

- Proof file: `.lemma-proof.json`
- Local firewall listens on `http://127.0.0.1:8787`

## Manual Or Advanced Path

If you want the lower-level setup flow, use:

- [CLI README](../CLI_PYPI_README.md)
- [OpenClaw Operator Runbook](../operations/OPENCLAW_OPERATOR_RUNBOOK.md)
- [OpenClaw Proof-First Setup](../OPENCLAW_PROOF_BASE_TIER_SECONDS.md)
