# Architecture

## Components

- **Flask app** (`app.py`) — serves UI + JSON APIs
- **Crypto layer** (`crypto/`) — Ed25519 route credentials, package assignments, delivery events
- **SQLite** (`models/db.py`) — routes, synced events, benchmark runs
- **Driver PWA** — localStorage route bundle + IndexedDB offline queue
- **Field metrics** — localStorage logs, server-side validation/aggregation only

## Flow

1. Dispatch signs a `RouteCredential` and package assignments
2. Driver downloads bundle to localStorage
3. Scan verifies assignment against route credential locally
4. Local-first mode signs `DeliveryEvent` and queues offline if needed
5. Sync API verifies signatures + hash chain
6. Audit dashboard replays custody steps

## Crypto

- Canonical JSON (sorted keys) → SHA-256 → Ed25519 sign
- Chain: `previous_event_hash = SHA-256(canonical_json(prior_event))` or `genesis`
- Issuer key: `data/keys/issuer_private.pem`
- Demo device key: `data/keys/device_private.pem`

## Lemma.id patterns reused

| Pattern | Source inspiration |
|---------|-------------------|
| Ed25519 signed JSON credentials | `api/real_iam_manager.py` |
| Client sign/verify | `static/js/lemma-keys.js` |
| Offline backend verify | `packages/ishuman-verify-py` |
| Stamped action events | `ishuman-verifier.js` `stamp()` |

Not used: isHuman IDV, PPID, wallet, bloom revocation, production DB.
