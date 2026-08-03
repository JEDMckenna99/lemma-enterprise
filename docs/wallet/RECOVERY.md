# lemma.id recovery & cross-device transfer

> Identity lives in the network, not the device. You can never lose your
> verified-human status, only the device that held your lemma.id.

This document describes the two supported ways a user regains access to their
Lemma identity, and the trust model behind each. It corresponds to Phase 4 of
[`V2_DESIGN_IMPROVEMENTS.md`](../architecture/V2_DESIGN_IMPROVEMENTS.md).

Endpoint paths retain the internal `/api/wallet/*` prefix; they operate on the user's lemma.id.

## 1. Re-IDV: the primary recovery path

If a user loses their device, clears IndexedDB, or installs a fresh browser,
the canonical recovery is to **verify identity again**. Re-verifying with the
**same government document** resolves to the same `LemmaPerson` via
`lemma_document_roots`, which yields the same per-site PPIDs and therefore the
same network identity everywhere.

> **Assigned person root (`assigned_v1`):** `person_root` is no longer
> `HKDF(document_root)` for new identities, it is server-assigned and stable.
> Recovery still works because the server matches the document attestation to
> the existing person before binding the new lemma.id. See
> [`ASSIGNED_PERSON_ROOT.md`](../architecture/ASSIGNED_PERSON_ROOT.md).

Legacy (`document_derived_v1`) identities additionally could re-derive
`person_root` deterministically from the document hash alone; assigned identities
require the server document → person link (or a sealed seed envelope on device).

Flow:

1. User opens their lemma.id and chooses **"Lost your device?"**.
2. The lemma.id UI runs the standard Didit identity verification (default IDV rail).
3. On completion the server derives the document-root lookup key, resolves its
   existing `LemmaPerson`, and loads that person's assigned `person_root`. The lemma.id client calls
   [`POST /api/ishuman/reissue-master`](../../api/ishuman.py) (Phase 1.3) to
   re-fetch a freshly signed master credential. The old master id is revoked
   and lands in the next Bloom snapshot.
4. Per-site credentials are re-derived on demand against the restored master.

**Provisional lemma.id instances (pre-IDV):** When `LEMMA_ONE_PPID_ASSURANCE_MODEL=1`, a user receives an assigned **provisional** person_root at registration. Site PPIDs are stable from that point, but **cross-device recovery is not promised** until the person is **anchored** by first successful IDV. Treat empty pre-IDV lemma.id instances as disposable; after anchoring, re-IDV recovery preserves PPIDs as today.

Assigned-root recovery requires the durable `lemma_document_roots` ->
`lemma_persons` mapping. The resolver checks compatible document-root schema,
pepper-version, and legacy IDV-provider keys before it may create a person. A
legacy match is linked to the current write key so later recovery is direct.
Re-IDV + reissue-master together give the full recovery story.

### Internal IAM continuity

`platform_users.user_did` is the person-root PPID for `lemma.id`. After a lost
device re-verifies the same document, the new lemma.id is bound to the existing
`LemmaPerson`; `resolve_platform_login_ppid()` therefore returns the same PPID
and the existing internal IAM account, roles, and site links remain in force.
Recovery must never rewrite IAM ownership from a client-supplied bare PPID.

### Why this is safe

- The PPID for a site is `HMAC(person_root, "lemma.id/site-ppid/v1" + canonical_site)`.
  It depends only on `person_root` + site, so it is stable across devices and
  re-verifications.
- The old master credential id is revoked, so a stolen old device cannot keep
  presenting it once the user has recovered.

## 2. Explicit cross-device transfer (QR): no re-IDV

For users who still have their original device and simply want to add another,
the lemma.id UI offers an **"Add device"** QR flow that moves identity material
device-to-device without re-running IDV.

Because the server never persists the plaintext `person_root` or the derived
seeds, **it cannot reseal envelopes itself**. The transfer is therefore a
short-lived (60 s), one-time *relay*: the new device proposes a key, the old
device reseals to it, and the server only ever stores opaque ciphertext.

```mermaid
sequenceDiagram
    participant New as New device
    participant Srv as Lemma server
    participant Old as Old device

    New->>New: generateEncryptionKeypair() + random transfer_id
    New-->>Old: QR { transfer_id, new_device_enc_pubkey }
    Old->>Old: open own seed envelopes (Phase 1.1)
    Old->>Old: reseal seeds to new_device_enc_pubkey
    Old->>Srv: POST /sync-device deposit (wallet_assertion binds<br/>transfer_id + new_device_enc_pubkey)
    Srv->>Srv: verify assertion, store opaque bundle (TTL 60s)
    New->>Srv: POST /sync-device claim { transfer_id }
    Srv-->>New: bundle (then delete; one-time)
    New->>New: open resealed seeds with transient private key
```

### Endpoint: `POST /api/wallet/sync-device`

Two actions over one channel keyed by the new device's `transfer_id`:

| action    | who        | body                                                                                   | result |
|-----------|------------|----------------------------------------------------------------------------------------|--------|
| `deposit` | old device | `wallet_id`, `transfer_id`, `new_device_enc_pubkey`, `bundle`, `wallet_assertion`      | stores opaque bundle, 60 s TTL |
| `claim`   | new device | `transfer_id`                                                                          | returns bundle once, then deletes |

Security properties:

- **Key binding.** The deposit `wallet_assertion` is signed over both
  `transfer_id` and `new_device_enc_pubkey`. A man-in-the-middle who swaps the
  target key invalidates the signature (the server rejects with
  `wallet assertion signature invalid`).
- **Confidentiality.** The bundle is sealed (X25519 + HKDF-SHA256 + AES-256-GCM,
  see [`api/seed_envelope.py`](../../api/seed_envelope.py)) to the new device's
  transient key. Even if the relay entry is claimed by an attacker, it cannot be
  opened without the transient private key, which never leaves the new device.
- **One-time + short-lived.** The relay entry is burned on first claim and
  expires after 60 seconds.
- **No plaintext at rest.** The server stores only ciphertext; it never sees the
  `wallet_local_seed` or `person_root_proxy`.

### lemma.id SDK helpers (internal: `LemmaWallet`)

- `beginDeviceTransfer()`, new device: mint transient keypair + `transfer_id`,
  return the QR payload.
- `depositDeviceTransfer({ transferId, newDeviceEncPubkeyB64, masterCredentialId })`
, old device: reseal seeds and deposit.
- `claimDeviceTransfer(transferId)`, new device: claim and open.

## Rollout note

The QR transfer reuses the Phase 1.1 seed-envelope machinery and is therefore
only meaningful for post-IDV lemma.id instances once
`LEMMA_ISHUMAN_USE_PERSON_ROOT_SEEDS` is enabled. Until then, re-IDV (path 1)
remains the supported recovery mechanism for all lemma.id instances.
