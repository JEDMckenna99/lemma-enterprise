# Assigned person root (`assigned_v1`)

## Problem

Legacy Lemma identities derive `person_root` from the verified document:

```
document_root = HMAC(document claims)
person_root   = HKDF(document_root)
PPID(site)    = HMAC(person_root, site)
```

When a user renews a passport or gets a new driver's license number, the document hash changes, which mints a **new** person and **new** PPIDs. Relying sites must run [PPID migration](../integration/PPID_MIGRATION.md) to link accounts.

## Model

With `LEMMA_PERSON_ROOT_SOURCE=assigned_v1`:

| Layer | Role |
|-------|------|
| `lemma_document_roots` | Renewable attestation from IDV (passport, DL, etc.) |
| `lemma_persons.person_root` | Stable server-assigned 32-byte secret (random) |
| `lemma_wallet_bindings` | Wallet possession binds to one `lemma_person` |
| PPID | Derived from stable `person_root`, not document number |

Re-IDV with a **new document number** on the **same wallet** attaches a new document row to the existing person and **preserves** `person_root` and all PPIDs.

## Rollout

1. Apply migration `034_assigned_person_root_source.sql` (adds `person_root_source` column).
2. Set `LEMMA_PERSON_ROOT_SOURCE=assigned_v1` on the platform when ready.
3. **Existing rows** keep `document_derived_v1`; only **new** first-time IDVs get assigned roots.
4. Wallet-bound re-IDV uses document attach for **all** persons (legacy and assigned), so PPIDs stay stable without migration when the user uses the same wallet.

## Security

- Document attach requires wallet binding to match (fail closed if document maps to a different person than the wallet).
- Fresh IDV still required for each new document attestation.
- PPID migration remains for legacy pairs where a site already recorded the wrong PPID before document attach shipped.

## Environment

```bash
# Default (legacy)
LEMMA_PERSON_ROOT_SOURCE=document_derived_v1

# New identities get assigned person_root
LEMMA_PERSON_ROOT_SOURCE=assigned_v1
```
