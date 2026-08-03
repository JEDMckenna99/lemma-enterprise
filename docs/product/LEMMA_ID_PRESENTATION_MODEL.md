# lemma.id Presentation Model

Status: Active contract  
Audience: Platform engineers, lemma.id SDK maintainers (internal: `LemmaWallet`), integration partners

## Glossary

| Term | Meaning |
|------|---------|
| **lemma.id** | Preferred public noun: the user's passkey-protected local identity store and credential holder. |
| **wallet** (internal) | Legacy code/API name for a lemma.id instance (`LemmaWallet`, `/api/wallet/*`, `wallet_id`, etc.). |

## Overview

lemma.id separates **identity proof** from **permission proof**. All users, including platform operators, follow the same lemma.id and isHuman identity flow. Operator privileges are additional lemma.id-scoped permission credentials, not a parallel identity system.

```
Unlocked lemma.id
  → isHuman identity proof (master or site-bound)
    → lemma.id permission proof (optional, e.g. admin_access)
      → platform operator access
    → normal user access (no admin permission)
```

## Identity proof

An **identity proof** establishes that a lemma.id holder is human on lemma.id.

| Property | Rule |
|----------|------|
| Primary signals | `claims.assurance` (`passkey` \| `ishuman`), legacy `claims.isHuman === true`, or credential id prefix `ishuman_master_` / `ishuman_site_` |
| Runtime site binding | Normalized hostname; platform binding is `lemma.id` |
| Sparse site fields | Empty `siteId` / `siteDomain` on master records is valid; skip before canonicalization |
| PPID derivation | Assigned **person_root** + normalized hostname (canonical). Legacy local-identity-seed derivation is provisional-only behind flags. |
| Assurance | `passkey` = lemma.id-bound pre-IDV; `ishuman` = IDV-backed. Same PPID across tiers. |

**Complete lemma.id** means the user's lemma.id holds a valid isHuman identity proof for the platform (master credential and/or lemma.id site proof).

## Permission proof

A **permission proof** grants scoped access on a site.

| Property | Rule |
|----------|------|
| Canonical admin permission | `permissionId: admin_access` |
| Requested level | Preserve separately as `permission_level` when needed |
| Platform binding | Runtime `siteId` / `siteDomain` must resolve to `lemma.id` (aliases: `lemma_platform`, `www.lemma.id`) |
| Scope | Array of strings; admin compatibility scopes include `admin`, `write`, `read` |

**Platform operator** = complete lemma.id identity proof + non-expired `admin_access` permission bound to `lemma.id`.

## Presentation

A **presentation** is the signed credential (or derived session artifact) sent to relying parties and APIs.

The security meaning and limitations of passkeys, isHuman credentials, PPIDs,
device signing assertions (internal: wallet assertions), lemma.id unlock sessions
(internal: wallet sessions), action stamps, fresh-passkey attestations,
recovery proofs, and permission credentials are defined in
`docs/security/HUMAN_AUTH_SECURITY_CONTRACT.md`. In particular, a PPID is an
account-continuity handle, not an authentication secret, and a lemma.id unlock
session does not replace a required lemma.id-held proof for a protected mutation.

### Browser headers (platform/admin flows)

Protected platform routes expect:

- `X-Lemma-Credential`, encoded credential selected from the user's lemma.id
- `X-Credential-ID`, credential id when available
- `X-Permission-ID`, canonical permission id (`admin_access` for operators)

lemma.id unlock is required. Server session cookies improve UX but do not replace lemma.id-held proofs on protected flows.

### Site binding keys

| Key | Purpose |
|-----|---------|
| `site_...` (internal) | Database ownership, issuance context, **not** runtime PPID/credential matching |
| `siteId` / `siteDomain` (hostname) | Runtime binding for PPID derivation and credential matching |
| `lemma.id` | Platform canonical binding |

Backend helpers:

- `api/site_hostname.canonicalize_site_hostname()`, strict integrator hostname input
- `api/site_hostname.normalize_runtime_site_binding()`, permissive runtime credential binding normalizer

Frontend helpers (`lemma-credential-utils.js`):

- `canonicalPlatformSite()`, `getCredentialSiteBinding()`
- `isCompleteLemmaIdCredential()`, `isPlatformOperatorCredential()`
- `selectPlatformCredentials()`, `assessLemmaPlatformIdentity()`

## Anti-patterns

- Using `site_*` internal ids as the sole runtime credential match key
- Calling `canonicalizeSiteDomain('')` on empty site fields during credential inspection
- Treating admin server session alone as sufficient for protected platform mutations
- Issuing admin credentials with `permissionId: admin` instead of `admin_access`
- Loose hostname matching (`includes('lemma')`) for platform site detection

## Related docs

- Integration guide: `docs/integration/ISHUMAN_AGENT_INTEGRATION.md`
- Human-auth security contract: `docs/security/HUMAN_AUTH_SECURITY_CONTRACT.md`
- Trust core spec: `docs/architecture/LEMMA_TRUST_CORE_SPEC.md`
- Agent guardrails: `AGENTS.md` (repo root) and `docs/integration/ISHUMAN_AGENT_INTEGRATION.md`

## Verification (deploy smoke)

After deploying lemma.id/auth changes:

1. Hard refresh lemma.id (or unregister service worker + clear site data if SDK version stuck).
2. Confirm `lemma-wallet.js?v=2677` (or current bump) and SDK `VERSION` ≥ 2.74.0 in console.
3. Unlock lemma.id; manager (`/`) should recognize complete lemma.id without `site domain required` errors.
4. Admin pages should attach `X-Lemma-Credential` with `X-Permission-ID: admin_access`.
5. If `Invalid signature` appears on `ishuman_master_*`, hard refresh then unlock; platform login auto-reissues once via `reissueMasterCredential`.
6. Run targeted tests:
   - `tests/test_wallet_hostname_guard.py`
   - `tests/test_platform_manager_navigation.py`
   - `tests/test_platform_identity_contract.py`
   - `tests/test_authz_engine_phase12.py`
   - `tests/test_ishuman_ppid_normalization.py`
