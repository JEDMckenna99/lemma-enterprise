# CIAM Identity Model (Proof-Native)

lemma.id is building toward full CIAM while keeping **Sign in with lemma.id** as the
primary contract: wallet + passkey proofs, **site-private PPIDs**, local presentation
verification, and **site-owned sessions**.

This document freezes the Phase 1 identity vocabulary. OIDC/OAuth are deferred;
they would be a compatibility facade over proofs, not a replacement for them.

## Concepts

| CIAM concept | Store today | External key | Notes |
|---|---|---|---|
| **Tenant** (developer account) | `customers`, optional link on `platform_users.billing_customer_id` | `customer_id` | Billing/API keys |
| **Platform subject** | `platform_users.user_did` | platform-only person-root PPID | lemma.id internal identity |
| **Application** | `sites` + verified hostname | runtime `siteId` = hostname; internal `site_*` id | Never use internal id alone at runtime |
| **App subject** (end user on an app) | `site_users.user_ppid` | hostname-bound PPID | Relying site's account key |
| **App membership** | `site_users` row | `(site_id, user_ppid)` | Directory + role/status |
| **Operator grants** | `site_admins`, `platform_user_sites` | separate from end-user directory | Developer/operator access |
| **Agent Ops workspace** | `workspaces`, workspace memberships | — | **Not** B2B CIAM orgs |
| **Subject alias** (future) | `identity_subject_aliases` | explicit signed link | Opt-in only; off by default |

## Rules (Phase 1)

1. **Default external `sub`** for relying sites = **hostname-private PPID**.
2. **No silent PPID rewrite** across hostnames or applications.
3. **No platform-managed account merge** in Phase 1; sites link accounts by verifying
   a presentation while the user is logged in (integrator-owned merge).
4. **Presentations, not OAuth tokens**, are the canonical authentication artifact.
   After verification, the site issues its own session cookie/JWT.
5. **Legacy OAuth** (`/api/v1/oauth/*`) is retired (HTTP 410). Do not extend it.
6. **SDK redirect callback** (`/auth/sdk-callback`) does not bind a subject; use
   `<lemma-signin>` + `ProofVerifier.verifyForBackend`.

## Multi-application continuity

Default: **hostname-private forever**. Related apps (staging/prod, sibling domains)
must not share a PPID unless an explicit, auditable alias is created.

The `identity_subject_aliases` table is **schema-only in Phase 1**:

- `from_site_id` + `from_ppid` → `to_site_id` + `to_ppid`
- `status`: `reserved` | `active` | `revoked`
- `evidence_jti`: optional proof reference for a future signed link protocol

No public write API ships until a convergence/link protocol is defined.

## OIDC (deferred)

If added later, OIDC should:

- Use passkey + presentation as the authentication event behind `/authorize`
- Emit `sub` = site-private PPID
- Map assurance tiers into claims
- Remain optional; local presentation verification stays supported

## Code entry points

- Identity helpers: [`api/ciam_identity.py`](../../api/ciam_identity.py)
- Site directory API: [`api/site_management_api.py`](../../api/site_management_api.py)
- Presentation model: [`docs/product/LEMMA_ID_PRESENTATION_MODEL.md`](../product/LEMMA_ID_PRESENTATION_MODEL.md)
- Integration guide: [`docs/integration/ISHUMAN_AGENT_INTEGRATION.md`](../integration/ISHUMAN_AGENT_INTEGRATION.md)
