# lemma-cli

Local firewall for AI agents. Scope what your agent can do, proxy and enforce API access, get an audit log of every action, and kill the session instantly.

## Install

```bash
pipx install lemma-cli
```

## Agent Quick Start

No account or control plane required. One command starts a scoped session with a local firewall:

```bash
lemma start --scope write
```

This:
- Issues a local credential scoped to `write`
- Starts the Lemma Firewall on `127.0.0.1:8787` with an httpbin test API
- Writes a session log to `~/.lemma/sessions/`

Make a request through the firewall:

```bash
curl http://127.0.0.1:8787/firewall/httpbin/get
```

When you're done, tear down and review:

```bash
lemma stop
lemma replay --last
```

### What you get

- **Scoped credentials** -- `read`, `write`, or `admin` limit which of 24 action types are allowed
- **API proxy enforcement** -- method, path, and scope restrictions per upstream API that the agent cannot bypass
- **Audit log** -- every allow/deny decision logged to JSONL; `lemma replay` shows the summary
- **Kill switch** -- `lemma stop` revokes the credential and kills the firewall instantly
- **Approval workflow** -- `--approve "shell.exec file.delete"` blocks dangerous actions until you approve in the live dashboard
- **Taint containment** -- if the agent violates policy, its credential is automatically invalidated

### Real APIs

Use `--policy` to proxy real APIs (presets: `httpbin`, `github`, `openai`, `anthropic`, `stripe`):

```bash
lemma start --scope write --policy "openai,github"
```

Or point to your own policy file:

```bash
lemma start --scope read --policy ./my-policy.json
```

Run `lemma demo` for a full containment test (allow/deny, taint epoch, revocation) against a live control plane.

## OpenClaw Starter Path

```bash
lemma setup-openclaw --api-base https://lemma.id --json
lemma safety-status --firewall-url http://127.0.0.1:8787 --json
```

`lemma setup-openclaw` is the public starter-safe path. It:

- opens one browser approval
- issues a starter-safe OpenClaw proof
- connects the runtime
- starts the local firewall
- verifies one protected allow
- kills the runtime and verifies deny

## Other Core Commands

```bash
lemma session start --api-base https://lemma.id
lemma session status --api-base https://lemma.id --json
lemma setup-firewall --api-base https://lemma.id --json
lemma setup --site-id site_demo --site-domain example.com --framework flask --json
lemma audit --project-dir . --framework flask --skip-health --json
lemma fix --project-dir . --framework flask --safe --skip-health --json
lemma ci --project-dir . --framework flask --skip-health --skip-smoke --json
```

## Authentication for Sensitive Operations

Local interactive browser flow:

```bash
lemma login --api-base https://lemma.id
lemma auth-status --api-base https://lemma.id --json
```

Headless/CI flow:

```bash
lemma login --api-base https://lemma.id --non-interactive --platform-api-key "$LEMMA_API_KEY" --user-email "$LEMMA_ADMIN_EMAIL" --json
```

## Sensitive Management Commands

```bash
lemma site-create --domain demo.example --environment development --json
lemma key-bootstrap --site-id site_demo --name "CI Key" --permissions read,write --json
lemma iam-type-create --site-id site_demo --name admin_access --iam-type role --json
lemma iam-type-list --site-id site_demo --json
```

## Contract

All machine-oriented commands support `--json` and emit:
- `schema_version`
- `command`
- `ok`
- `error_code`

## Documentation

- OpenClaw Personal Quickstart: `docs/openclaw/PERSONAL_QUICKSTART.md`
- Quickstart: <https://lemma.id/docs/quickstart>
- Release checklist: `docs/operations/CLI_RELEASE_CHECKLIST.md`
