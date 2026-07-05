# Assigned person root (`assigned_v1`)

## Invariant

The assigned person root is the permanent human anchor. A relying-site PPID is
derived only from that root and the canonical hostname, so it never changes for
the same assigned person and site.

```text
document_root = HMAC(document number + jurisdiction + DOB)
person_root   = random 32-byte assigned secret
PPID(site)    = HMAC(person_root, domain separator + canonical hostname)
```

Document roots are renewable identity attestations, not the source of the
person root after assignment.

## Resolution rules

1. A known document root resolves its existing assigned person.
2. A newly presented document on an authenticated, already-bound wallet is
   attached to that wallet's assigned person.
3. If the document resolves one person while the wallet is bound to another,
   issuance fails closed.
4. If neither the document nor wallet resolves an assignment, first-time IDV
   creates a new assigned person root.

## Provisional lifecycle (one-PPID model)

When `LEMMA_ONE_PPID_ASSURANCE_MODEL=1`:

1. Wallet registration assigns a **provisional** person_root (`lemma_persons.status = provisional`).
2. Site PPIDs derive from that root immediately — before IDV.
3. First successful IDV on the bound wallet **promotes** the person to `active` and attaches the document root; **PPIDs do not change**.
4. Provisional wallets are disposable (no cross-device recovery promise) until anchored.

If IDV document resolution finds an existing person while the wallet is bound
only to an unanchored provisional person, the provisional binding is replaced
with the existing person. Once the wallet-bound person is anchored, conflicts
fail closed.

Document expiry changes credential validity, not identity. Renewing a document
updates or adds the document attestation while preserving the person root,
master identity, and every site PPID.

Lost-device recovery with the same verified document resolves the same document
root and therefore the same assigned person. A new document can be attached
only through an authenticated flow already bound to that person; the platform
does not change PPIDs or offer PPID migration as an account-linking fallback.

## Storage boundary

Assigned roots are stored as `kms1:` AWS KMS ciphertext. Every load and write
uses `api/person_root_crypto.py`; production fails closed for legacy/plaintext
roots or KMS unavailability.

## Relying-site contract

- PPIDs are stable opaque account identifiers.
- Document renewal requires no relying-site account migration.
- Recovery and credential rotation preserve the PPID.
- Site credentials rotate every 30 days, but their PPID does not.
- A persistent site block continues to apply across every lifecycle operation.

There is no PPID migration endpoint, signed migration object, wallet cache, or
site-specific migration database state.
