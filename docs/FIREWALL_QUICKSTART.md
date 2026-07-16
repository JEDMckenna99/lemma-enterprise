# Lemma Firewall Quickstart

## What It Does

The Lemma Firewall is a local enforcement gateway that validates agent credentials on every API request, checks scope/path/method constraints, syncs revocation from the lemma.id control plane, and forwards only allowed calls to upstream APIs. It runs between your agent and the APIs it calls. Credentials are verified locally using Ed25519 signature checks, no per-request server calls required.

## OpenClaw Starter Path

If you are setting this up for a personal OpenClaw runtime, start with:

```bash
lemma setup-openclaw --api-base https://lemma.id
```

That command approves once in the browser, issues a starter-safe proof, starts the firewall, verifies one allowed protected action, then kills the runtime and verifies deny.

## Quick Demo (one command)

```bash
lemma demo
```

This issues a credential, starts the firewall, and runs containment tests, all in one command.

## Prerequisites

- Python 3.10+ (or Docker)
- A lemma.id account (sign up at [https://lemma.id](https://lemma.id))
- Install CLI from git (current path):
  - `pip install git+https://github.com/JEDMckenna99/lemma-enterprise.git`

---

## Option A: Run with Python

### 1. Get a signed credential

```bash
curl -X POST https://lemma.id/api/demo/issue-credential \
  -H "Content-Type: application/json" \
  -d '{"runtime_id": "lemma-demo-runtime", "scope": ["read", "write"]}'
```

This returns a signed W3C credential that the firewall verifies locally via Ed25519 signature. No server call needed on each request.

### 2. Configure your policy

Create a `policy.json` file defining which APIs the agent can call:

```json
{
  "apis": {
    "my-api": {
      "base_url": "https://api.example.com",
      "allowed_methods": ["GET", "POST"],
      "path_prefixes": ["/v1/"],
      "required_scope": "read",
      "risk_tier": "low"
    }
  }
}
```

### 3. Run the firewall

```bash
export LEMMA_BASE_URL=https://lemma.id
export LEMMA_CREDENTIAL='<JSON-encoded credential from step 1>'
export LEMMA_FIREWALL_POLICY_FILE=./policy.json
python scripts/lemma_firewall.py
```

Firewall listens on `http://localhost:8787`.

### 4. Point your agent at the firewall

Instead of calling `https://api.example.com/v1/data` directly, configure your agent to call:

```
http://localhost:8787/firewall/my-api/v1/data
```

The firewall validates the credential, checks scope and path, and forwards allowed requests.

---

## Option B: Run with Docker

```bash
docker build -f Dockerfile.firewall -t lemma-firewall .
docker run -p 8787:8787 \
  -e LEMMA_BASE_URL=https://lemma.id \
  -e LEMMA_CREDENTIAL='<JSON-encoded credential>' \
  -v ./policy.json:/app/policy.json \
  -e LEMMA_FIREWALL_POLICY_FILE=/app/policy.json \
  lemma-firewall
```

---

## Verify It Works

Allowed request (should succeed):

```bash
curl -H 'X-Lemma-Credential: <JSON-encoded credential>' http://localhost:8787/firewall/my-api/v1/data
```

Denied request (wrong path, should get 403):

```bash
curl -H 'X-Lemma-Credential: <JSON-encoded credential>' http://localhost:8787/firewall/my-api/admin/secret
```

## Health Check

```bash
curl http://localhost:8787/aim/health
```

Returns sync status, revocation counts, and taint epoch state.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LEMMA_BASE_URL` | `https://lemma.id` | Control plane URL for credential validation and sync |
| `LEMMA_CREDENTIAL` |, | JSON-encoded signed credential (W3C VC format) |
| `LEMMA_PROOF_FILE` |, | Path to credential proof file (alternative to `LEMMA_CREDENTIAL`) |
| `LEMMA_AGENT_TOKEN` |, | Compatibility alias for agent token header validation |
| `LEMMA_FIREWALL_POLICY_FILE` |, | Path to `policy.json` defining allowed API routes |
| `LEMMA_FIREWALL_RUNTIME_ID` | `lemma-firewall-default` | Unique identifier for this firewall instance |
| `LEMMA_FIREWALL_HOST` | `127.0.0.1` | Host address the firewall binds to |
| `LEMMA_FIREWALL_PORT` | `8787` | Port the firewall listens on |
| `LEMMA_FIREWALL_TAINT_ENFORCEMENT_ENABLED` | `1` | Enable taint-epoch enforcement (`0` to disable) |
| `LEMMA_FIREWALL_REVOCATION_SYNC_INTERVAL_MS` | `30000` | Interval (ms) for syncing revocation lists from control plane |
| `LEMMA_FIREWALL_TAINT_SYNC_INTERVAL_MS` | `10000` | Interval (ms) for syncing taint epoch state from control plane |

---

## How Local Verification Works

The credential is a **W3C Verifiable Credential** signed with **Ed25519**. On each request the firewall checks:

1. **Signature validity**: the Ed25519 signature on the credential is verified against the issuer's public key.
2. **Issuer trust**: the issuer must be in the firewall's trusted issuer set.
3. **Scope**: the credential's scope must cover the requested API operation.
4. **Expiry**: the credential must not be expired.
5. **Revocation status**: checked against a locally-cached revocation list (updated via background sync).

Zero server calls on the hot path, verification takes <1ms. The control plane is only contacted for background sync (revocation lists, taint epoch, policy updates).

---

## Next Steps

- **Set up runtime registration:** `lemma firewall-connect`
- **Monitor decisions:** check the `/api/wallet/runtimes/decisions` endpoint
- **Revoke credentials:** `POST /api/wallet/revoke`
