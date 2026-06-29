# Lemma Privacy and Data-Handling Architecture

This document describes the privacy-minimized isHuman architecture introduced
by migrations 038 and 039. Pseudonymous identifiers remain personal data; this
is an engineering description, not legal advice.

## Identity plane

Lemma transiently processes the document number, issuing jurisdiction, and DOB
received from the IDV provider to derive a keyed document root. It does not
persist document images, selfie/liveness images, or legal name in the isHuman
path.

The document root resolves to an assigned person. Document renewal can attach a
new document root to that assignment without changing downstream site PPIDs.
Recovery repeats IDV and resolves the same assignment when the document matches.

Assigned person roots are stored only as versioned `kms1:` AWS KMS ciphertext.
The KMS encryption context contains:

- `key_type=ishuman_person_root`
- `purpose=ppid_derivation`
- `version=1`
- an opaque HMAC of the person ID

The raw person ID is never sent to KMS or CloudTrail. Production fails closed
when KMS is unavailable or a root is not KMS encrypted. Plaintext roots are not
cached between requests.

## Site issuance plane

A site PPID remains deterministic:

```text
PPID = HMAC(assigned_person_root, domain_separator || canonical_hostname)
```

This preserves existing relying-site account bindings. Each 30-day renewal gets
a new random credential ID; Lemma does not retain that ID as site billing state.

Lemma necessarily observes the hostname and PPID transiently while issuing.
After issuance, it stores only:

- site scope: registered internal site ID, or canonical hostname for an
  unregistered integration;
- a keyed HMAC token of the already site-private PPID;
- first issuance month/time and last issuance time.

`ishuman_site_billing_subjects` contains no wallet ID, person ID, master credential ID,
PPID, or site credential ID. Consequently, the database no longer contains a
persistent person/wallet-to-site usage graph. Migration 039 removes
`derived_credentials` after cutover verification.

Relying sites still receive only their site-private PPID and signed human claim.
They cannot correlate PPIDs issued to other hostnames.

## Billing data

`ishuman_site_monthly_usage` is unique on `(site_scope, month, subject_token)`
for exact MAU deduplication. Subject-level monthly rows are deleted after 90
days; `ishuman_site_usage_aggregates` retains only site/month totals.

Lifetime subject tokens remain until site/customer deletion so a returning
person is not charged a second initial-binding fee.

Stripe receives only a random event ID, customer/site billing identity, month,
event type, and unit count. Stripe payloads contain no PPID hash, wallet ID,
person ID, master ID, or credential ID. Postgres is authoritative; Redis is an
optional cache and a one-time source for current-month cutover import.

## Enforcement

`SiteBlock` is persistent. Fresh IDV, wallet recovery, document renewal, and
credential rotation never clear or weaken it. Only the authenticated site
unblock operation can remove it.

`SiteDoubt` is a separate temporary state keyed to one site and PPID. A
successful deliberate fresh-IDV flow clears only the matching doubt when it
derives the same PPID. It does not inspect another site.

Enumeration-based network-wide revocation is retired. Legacy customer, admin,
and demo endpoints return HTTP 410. A Didit compromise event can revoke the
wallet/master and prevent future issuance, but existing site credentials may
remain locally valid until their 30-day expiry unless a relying site blocks its
PPID.

## PPID continuity

There is no PPID migration system. Document renewal and recovery resolve the
assigned person root before issuance, so the same person/site pair always
derives the same PPID. A conflicting document and wallet assignment fails
closed rather than producing an account-linking token.

## Retention summary

| Data | Retention |
|---|---|
| Site credential | 30 days by default |
| Monthly subject token | 90 days |
| Aggregate site/month totals | Billing retention period |
| Lifetime site billing-subject token | Until site/customer deletion |
| Site block | Until authenticated site unblock |
| Site doubt | Until explicit clear or matching successful fresh IDV |

Normal presentation verification remains local-first. A relying site can verify
the issuer signature, site binding, expiry, and signed session without sending a
per-request user event to Lemma.
