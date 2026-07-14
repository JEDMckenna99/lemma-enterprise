> **Unimplemented internal proposal — not shipped.** Do not use for integration planning. Shipped relying-site behavior is documented in public docs at [lemma.id/docs](https://lemma.id/docs).

# Compartmentalized Personas — Design Sketch

**Status:** Product / architecture spec (draft, unimplemented)  
**Date:** 2026-06-22  
**Audience:** Product, platform, privacy reviewers  

Related: `docs/architecture/ASSIGNED_PERSON_ROOT.md`, `docs/architecture/PRIVACY_ARCHITECTURE.md`, `docs/integration/PPID_MIGRATION.md`, `docs/product/AGENT_ACTING_PPID.md`

---

## 1. Summary

**Compartmentalized personas** let one verified human maintain **multiple site-unlinkable identity compartments** under a single IDV anchor — e.g. “Work” vs “Personal” — without uploading ID documents again and without giving relying sites a global identifier.

Today Lemma enforces **one `person_root` → one PPID graph per site**. Personas add an optional layer:

```text
document_root  →  lemma_person (enforcement anchor; one per real human + document graph)
persona_root   →  HKDF(person_root, "lemma.id/persona-root/v1" || persona_id)
PPID(site)     →  HMAC(persona_root, "lemma.id/site-ppid/v1" || canonical_site)
```

Sites in different compartments see **different PPIDs** and cannot link them. Lemma **still** can, on the enforcement plane — same as today, but with explicit persona metadata.

This is **not** “Lemma-blind identity.” It is **user-directed compartmentalization** with bounded fraud surface.

---

## 2. Problem

### 2.1 User stories

| Story | Today | With personas |
|-------|-------|---------------|
| Same human, work app + personal app, no cross-linking | Relying sites already unlinkable via PPIDs; user may still reuse email | Same, plus user can **choose** distinct PPIDs even if sites share telemetry brokers |
| Hide work identity from personal services (and vice versa) | Only via separate email/browser hygiene | Wallet assigns sites to compartments; PPIDs differ by design |
| Recover one compartment without resetting all accounts | Erase is all-or-nothing | Persona-scoped revoke / optional persona delete |
| Ban evasion with unlimited fresh identities | Blocked: one document → one person | Still blocked: capped personas, sticky site binding, network revoke spans document |

### 2.2 What this does **not** solve

- **Site ↔ site correlation via email, card, IP, fingerprint** — out of scope; PPIDs were never the leak there.
- **Lemma operator blindness** — personas are stored and linked to `lemma_person`; revocation requires that linkage.
- **Two legal humans on one document** — fraud; remains forbidden.
- **Unlimited Sybil identities from one passport** — capped and rate-limited by design.

---

## 3. Current model (baseline)

```text
IDV → document_root → lemma_person.person_root (assigned_v1 or document_derived_v1)
                     → PPID(site) = HMAC(person_root, site)
                     → derived_credentials (server-side cross-site map for revocation)
```

Constraints that personas must respect:

1. **Document uniqueness** — one `document_root_hash` maps to at most one `lemma_person` (anti-hijack).
2. **Wallet binding conflict** — wallet bound to person A cannot claim document mapped to person B.
3. **Network revocation** — operator/site abuse flows resolve `lemma_person` and all bound wallets + site PPIDs.
4. **Site binding key** — PPID derivation uses normalized hostname, not internal `site_...` IDs.

Personas **extend** layer 2–4; they do not replace the document → person anchor.

---

## 4. Proposed model

### 4.1 Entities

```text
LemmaPerson          — unchanged; IDV anchor (document graph, network revoke root)
LemmaPersona         — user-created compartment (label, status, created_at)
PersonaSiteBinding   — sticky (persona_id, canonical_site) → cached ppid
DerivedCredential    — gains persona_id column (nullable; null = default persona)
```

**Default persona:** every `lemma_person` has exactly one `default` persona created at first IDV (`persona_id = "default"`). Existing users need no migration behavior change until they opt in.

**Persona cap:** configurable, default **2** (default + one extra). Platform may raise to 3 for enterprise tiers. Hard ceiling prevents Sybil farming.

### 4.2 Derivation

```python
# Domain-separated; persona_id is UUID or slug assigned by server
persona_root = HKDF(
    person_root_bytes,
    salt=LEMMA_PERSON_ROOT_SALT_V1,
    info=f"lemma.id/persona-root/v1\x00{persona_id}",
    length=32,
)
ppid = HMAC(persona_root, b"lemma.id/site-ppid/v1" + canonical_site.encode())
```

Properties:

- Same persona + same site → same PPID (account continuity preserved **within** compartment).
- Different personas → different PPIDs on every site (cross-compartment unlinkability).
- `persona_id = "default"` with HKDF input `"default"` reproduces today’s graph if we define default as `HKDF(person_root, ..., "default")` **or** treat default as alias to raw `person_root` for backward compatibility (recommended: **alias** — default persona uses `person_root` directly so existing PPIDs unchanged).

**Backward compatibility rule:** `persona_id = "default"` → `persona_root := person_root` (no HKDF). New personas use HKDF. Existing issued credentials and PPIDs remain valid without re-issuance.

### 4.3 Site assignment (sticky binding)

First time a wallet calls `derive-site-proof` for `app.example.com` with optional `persona_id`:

1. If binding exists → use bound persona (ignore conflicting `persona_id` unless `force_rebind` + cooldown — see §6).
2. If no binding → use requested `persona_id` or default; persist `PersonaSiteBinding`.

**Sticky binding prevents ban evasion:** a site-scoped block on PPID\_work cannot be bypassed by switching to PPID\_personal on the **same** site. User can still use different personas on **different** sites.

Wallet UI shows compartment picker on first visit per site; settings screen allows viewing bindings (not silent cross-compartment moves).

---

## 5. API surface (draft)

All endpoints require wallet authentication (`wallet_assertion`) unless noted.

### 5.1 Persona management

```http
GET /api/ishuman/personas
```

Response:

```json
{
  "success": true,
  "personas": [
    {
      "personaId": "default",
      "label": "Default",
      "status": "active",
      "siteBindingCount": 4,
      "createdAt": 1710000000
    },
    {
      "personaId": "persona_7xk2...",
      "label": "Work",
      "status": "active",
      "siteBindingCount": 1,
      "createdAt": 1710086400
    }
  ],
  "maxPersonas": 2,
  "canCreate": true
}
```

```http
POST /api/ishuman/personas
Content-Type: application/json

{
  "label": "Work"
}
```

```http
GET /api/ishuman/personas/{personaId}/site-bindings
```

```http
POST /api/ishuman/personas/{personaId}/revoke
```

Persona-scoped revoke (user-initiated): network-revokes all credentials and site PPIDs **for that persona only**; other personas remain active.

### 5.2 Issuance (changes to existing)

```http
POST /api/ishuman/derive-site-proof
```

Add optional field:

```json
{
  "wallet_id": "wallet_...",
  "wallet_secret": "...",
  "target_site": "app.example.com",
  "persona_id": "persona_7xk2..."
}
```

Response unchanged shape; `ppid` reflects persona-specific derivation. On first visit, creates `PersonaSiteBinding`.

Presentation / credential metadata (optional, for site audit):

```json
{
  "personaHint": "work",
  "personaId": "persona_7xk2..."
}
```

Sites **must not** treat `personaHint` as authoritative; PPID is the subject. Hint is UX only.

### 5.3 Erasure (extends existing)

```http
POST /api/ishuman/erase
```

Add optional:

```json
{
  "wallet_id": "wallet_...",
  "scope": "persona",
  "persona_id": "persona_7xk2..."
}
```

| `scope` | Effect |
|---------|--------|
| `wallet` (default today) | Full wallet erase; delete person if last wallet |
| `persona` | Revoke + scrub bindings/credentials for one persona; keep person + other personas |
| `all_personas` | Delete all persona bindings + credentials; keep document/person for re-bind OR cascade to full erase (product choice — recommend cascade only when last persona deleted) |

### 5.4 Abuse / operator (unchanged semantics, persona-aware)

```http
POST /api/ishuman/network-revoke
```

Operator/site abuse: resolves **`lemma_person`**, revokes **all personas** and all site PPIDs. Optional future flag `persona_id` for site-scoped abuse on one compartment only (see §7).

---

## 6. Wallet UX (sketch)

```text
┌─────────────────────────────────────┐
│  lemma.id wallet                    │
│  ─────────────────────────────────  │
│  Personas                           │
│    ● Default (4 sites)              │
│    ○ Work (1 site)     [+ New]      │
│                                     │
│  app.example.com → Work             │
│  (change) — 30-day cooldown         │
└─────────────────────────────────────┘
```

- **First visit to site:** “Which persona for this site?” with short explanation.
- **Change binding:** allowed only after cooldown (e.g. 30 days) + fresh passkey unlock; old PPID remains in site DB (site treats as new user unless migration — see §8).
- **Create persona:** passkey + cap check; no second IDV.

---

## 7. Revocation tradeoffs

| Event | Scope | Rationale |
|-------|-------|-----------|
| User revokes one persona | That persona’s PPIDs + credentials | User autonomy |
| User full erase | Entire `lemma_person` if last wallet | GDPR Art. 17 |
| Site blocks PPID | That site + that PPID only | Existing Tier-1 |
| Network abuse revoke (default) | **All personas** under `lemma_person` | Fraud: compartments must not dodge human-level bans |
| Network abuse revoke (`persona_id` optional) | Single compartment | Weaker fraud guarantee; only if site proves compartment-specific abuse |
| Document conflict / fraud kill (`is_amnesty_eligible=false`) | All personas, sticky | Same as today’s governance kills |

**Product recommendation:** ship **person-wide network revoke** first; add persona-scoped operator revoke only for enterprise appeals workflows.

Amnesty after fresh IDV (`clear_amnesty_eligible_wallet_revocations`) clears blocks per **person** across wallets; extend to iterate all **persona roots** for that person when clearing site-scoped PPID blocks.

---

## 8. PPID migration interaction

Personas **replace most migration motivation** for compartmentalization use cases. Migration remains for:

- Legacy `document_derived_v1` PPID rotation before document attach.
- Wallet-loss divergent person merge (A → B).

**New rule:** migration objects MUST include `personaId` and MUST NOT allow cross-persona PPID pairing. `legacyPpid` and `currentPpid` must belong to the same persona (or both default).

Changing a site’s persona binding is **not** migration — it is a new account from the site’s perspective unless the site explicitly supports account linking (out of band).

---

## 9. Fraud and abuse

### 9.1 Threats

| Threat | Mitigation |
|--------|------------|
| Unlimited Sybil PPIDs from one passport | Persona cap (2–3); creation rate limit |
| Ban evasion on same site | Sticky `PersonaSiteBinding`; site block follows PPID |
| Ban evasion across sites via new persona | Network revoke spans all personas on abuse |
| Document sharing / second wallet hijack | Unchanged: `WalletPersonBindingConflictError` |
| Persona farming for referral fraud | Site policy + velocity limits; optional site flag `max_one_ppid_per_person` (already implicit) |
| Operator correlating compartments | By design on enforcement plane; disclosed in privacy policy |

### 9.2 What integrators see

No change to verification API by default. Sites verify `{ human, ppid }` locally. They **cannot** tell whether the PPID came from “Work” or “Default” compartment unless they collude on non-PPID signals.

Optional **`personaHint`** in presentation is **not** a security claim — sites should not store it as identity.

---

## 10. Privacy analysis

### 10.1 vs relying sites

| Property | Today | With personas |
|----------|-------|---------------|
| Cross-site unlinkability | Yes (pairwise PPID) | **Stronger when user assigns sites to different personas** |
| Same site continuity | Stable PPID | Stable within compartment |
| Document renewal visibility | Stable with `assigned_v1` | Unchanged |

Personas help users who **reuse emails or behavioral signals** across contexts and want Lemma IDs to differ anyway. They do not help if the user uses the same email on both sites.

### 10.2 vs Lemma

Lemma stores:

- `lemma_person` ↔ `document_root` (unchanged)
- `lemma_personas` ↔ `lemma_person` (new)
- `persona_site_bindings` (new — **reveals user’s compartmentalization choices** to Lemma)

This is **strictly more metadata** than today. Mitigations:

- Encrypt `label` at rest; minimize logging of persona labels.
- Do not expose persona graph to relying sites or customer dashboards by default.
- Erasure scrubs persona rows with person erase.

**Honest claim:**

> Personas give **users** stronger cross-context separation at relying sites. They do **not** reduce Lemma’s enforcement-plane visibility; they organize it.

### 10.3 vs “Lemma-blind” alternatives

True operator blindness requires blind credentials or federated issuers without shared revocation — incompatible with “one human ban everywhere.” Personas are the pragmatic middle tier.

---

## 11. Alternatives considered

| Alternative | Verdict |
|-------------|---------|
| **Separate wallets + separate IDV** | Strong separation but double liveness cost; same document still resolves to same person |
| **Erase + re-IDV “fresh start”** | Already shipped; nuclear option; breaks all continuity |
| **Client-only random PPIDs per site (no server map)** | Breaks network revocation and site-block lists |
| **Agent Acting PPID (AAP)** | Good for **agent** compartmentalization, not human signup identity |
| **ZK / unlinkable selective disclosure** | Research tier; high cost; weak global revoke |
| **Email alias integration (Hide My Email)** | Complementary; orthogonal to PPID |

---

## 12. Phased rollout

| Phase | Deliverable | Flag |
|-------|-------------|------|
| **0** | Design review, fraud policy, privacy policy update | — |
| **1** | Schema: `lemma_personas`, `persona_site_bindings`; default persona only (no-op) | `LEMMA_PERSONAS_ENABLED=0` |
| **2** | `POST/GET /api/ishuman/personas`, derive-site-proof `persona_id`, wallet UI | `LEMMA_PERSONAS_ENABLED=1` |
| **3** | Persona-scoped user revoke + erase scope | — |
| **4** | Operator tooling: revoke graph shows personas; optional persona-scoped abuse | — |
| **5** | Enterprise: raised cap, SSO binding per persona (future) | tier-gated |

**Migration:** existing users stay on `default` persona with identical PPIDs. No mandatory re-issuance.

---

## 13. Schema sketch

```sql
-- migration 0xx_personas.sql (illustrative)

CREATE TABLE lemma_personas (
    persona_id       VARCHAR(64) PRIMARY KEY,
    lemma_person_id  VARCHAR(64) NOT NULL REFERENCES lemma_persons(person_id),
    label_encrypted  BYTEA,
    status           VARCHAR(16) NOT NULL DEFAULT 'active',
    is_default       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at       TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_persona_default
    ON lemma_personas (lemma_person_id) WHERE is_default = TRUE;

CREATE TABLE persona_site_bindings (
    binding_id       VARCHAR(64) PRIMARY KEY,
    persona_id       VARCHAR(64) NOT NULL REFERENCES lemma_personas(persona_id),
    canonical_site   VARCHAR(255) NOT NULL,
    ppid             VARCHAR(128) NOT NULL,
    bound_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (persona_id, canonical_site)
);

ALTER TABLE derived_credentials
    ADD COLUMN persona_id VARCHAR(64);
```

---

## 14. Open questions

1. **Default cap of 2** — enough for Work/Personal? Enterprise tier at 3–5?
2. **Persona binding cooldown** — 30 days vs never allow rebind (strongest anti-evasion)?
3. **Should sites opt in to persona hints** for support (“which compartment did you use?”)?
4. **Persona-scoped network revoke** — ever, or always person-wide for v1?
5. **Regulatory framing** — personas as “pseudonym layers” under same Art. 30 record or separate purpose?

---

## 15. Recommendation

**Build personas if** product research shows demand for user-controlled identity compartments beyond what pairwise PPIDs already provide — primarily **privacy-forward consumers** and **integrators marketing “no cross-context ID leakage.”**

**Do not build** if the goal is Lemma operator blindness; that requires a different architecture.

**Ship v1 as:**

- Default + 1 extra persona  
- Sticky site binding with cooldown  
- Person-wide network revoke  
- Default persona = backward-compatible PPIDs  
- Clear privacy copy: “Sites can’t link compartments; Lemma holds enforcement linkage.”

---

## 16. One-line positioning

> **Compartmentalized personas:** one passport, multiple site-unlinkable PPIDs — user choice, capped and revocable, without giving relying sites a global ID.
