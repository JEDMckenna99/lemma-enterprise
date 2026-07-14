> **Unimplemented internal proposal — not shipped.** Do not use for integration planning. Shipped relying-site behavior is documented in public docs at [lemma.id/docs](https://lemma.id/docs).

# Agent Acting PPID (AAP) — Compressed Chain Identity

**Status:** Product / architecture spec (draft, unimplemented)  
**Date:** 2026-06-17  
**Audience:** Product, platform  

Related: `docs/product/HUMAN_BACKED_AGENT_PASSPORT.md`, `docs/architecture/CHAINED_PROOF_COMPOSITION.md`, `api/identity_roots.py`, `api/ppid.py`

---

## 1. Summary

**Agent Acting PPID (AAP)** is a single pairwise identifier the agent carries when it acts on a site — compressing the human-verified delegation chain into one wire principal, without collapsing the cryptographic guarantees underneath.

```text
L1  Verified human (isHuman)           → human site PPID (existing)
L2  Human-consented agent delegation    → delegation profile + agent key
L3  Site/API scoped access              → scope ceiling bound into AAP context
L4  Agent Ops (operators only)          → runtime authorize / kill (not in AAP)

Wire to relying site:  did:lemma:aap_<hash>  + PoP + compact signed bundle
Wire to operator:      same AAP + firewall / runtime_id linkage
```

**Integrator mental model:** issue once → agent gets an **acting ID** → site verifies locally like isHuman today.

**Not this:** a bare opaque string with no signature (that would be a replayable API key dressed as a PPID).

---

## 2. Problem

Today Lemma can answer four trust questions, but integrators must understand:

- human site PPID (`did:lemma:ppid_*`)
- delegated proof + `agent_key_id` + PoP
- permission lemma / site role
- wallet consent / runtime ops

For **agent identity** buyers, the desired UX is closer to:

1. Human verifies (isHuman) and approves an agent.
2. Agent receives **one ID** to use on recurring or one-shot actions.
3. Site stores/logs that ID and verifies with one SDK call.

OAuth gives a bearer token (user-shaped). Lemma can give an **agent-shaped pairwise principal** whose derivation context encodes the authorized delegation profile.

---

## 3. Two PPID families (do not conflate)

| Identifier | Prefix | Stable across | Answers |
|------------|--------|---------------|---------|
| **Human site PPID** | `did:lemma:ppid_` | Same human + same site hostname | “Verified human at this site” (L1) |
| **Agent Acting PPID (AAP)** | `did:lemma:aap_` | Same delegation **profile** until revoke/re-scope | “This authorized agent instance for this site + scope profile” (L1–L3 compressed) |

Human PPID derivation (canonical, already shipped):

```text
person_root → HMAC(person_root, "lemma.id/site-ppid/v1" || canonical_site) → did:lemma:ppid_*
```

AAP derivation (new, domain-separated):

```text
delegation_root = HMAC(person_root, "lemma.id/agent-delegation/v1")
context = canonical_json({ v, aud, profile_id, scope_h, consent_epoch })
aap = HMAC(delegation_root, "lemma.id/agent-acting-ppid/v1" || context) → did:lemma:aap_*
```

**Privacy:** `ppid_site` and `aap` are unlinkable to verifiers without person_root. Sites see only the AAP on agent traffic; human PPID stays in issuance / audit planes unless the site already bound a user row to it at signup.

---

## 4. Layer mapping (your L1 → L4 order)

### L1 — Verified human (isHuman)

- **Gate:** IDV-backed person root; trust tier ≥ policy floor (default T2 for signup-grade actions).
- **Output:** human site PPID embedded in L1 credential / presentation (not sent on every agent request if AAP mode is used).
- **End-of-loop:** optional **human re-stamp** on consequential outcomes (checkout, recovery, step-up) — same person root, fresh presentation, same human PPID.

### L2 — Human-consented delegation

- **Gate:** wallet unlocked / passkey consent anchor (`consent_epoch`).
- **Inputs to AAP context:** `profile_id`, `scope_h` (hash of ordered scope + resource_bounds).
- **Agent key:** `agent_key_id` + Ed25519 keypair for PoP (existing `authz_profile_v2` path).
- **Modes:**
  - **Recurring:** stable `profile_id` (e.g. `runtime_id`, `delegation_profile` UUID) → stable AAP across sessions until revoke or re-scope.
  - **One-shot:** `profile_id = jti` (random per grant) → unique AAP per issuance.

### L3 — Site / API access

- **Bound in AAP context:** `aud` (canonical hostname), `scope_h`, optional `resource_bounds` hash.
- **Issued artifact:** compact **Agent Acting Credential (AAC)** — VC-JWT or `authz_profile_v2` child whose **subject** is the AAP.
- **Site behavior:** treat AAP like a service account principal; verify AAC + PoP per protected request.

### L4 — Agent Ops (operators)

- **Not compressed into AAP** — runtime state is dynamic between actions.
- **Linkage:** `runtime_id` stored as `profile_id` or extension claim; firewall calls `authorize` / checks kill / taint epoch.
- **Relying sites:** optional; default verify path is L1–L3 local only.

---

## 5. Wire format

### 5.1 What the agent holds

```json
{
  "acting_ppid": "did:lemma:aap_…",
  "profile_id": "runtime_openclaw_01",
  "profile_mode": "recurring",
  "aud": "app.example.com",
  "agent_key_id": "agent_runtime_01",
  "agent_private_key": "(once, at issuance)",
  "credential": { "…": "Agent Acting Credential (AAC)" },
  "human_ppid_ref": "did:lemma:ppid_…",
  "trust_tier": "T2",
  "expires_at": 1710086400,
  "consent_epoch": 1710000000
}
```

Stored in agent runtime / CLI secrets — **not** in lemma wallet IndexedDB on the operator machine unless the operator uses browser wallet issuance.

### 5.2 What the agent sends per request (hot path)

Preferred (existing headers):

```http
X-Lemma-Agent-PPID: did:lemma:aap_…
X-Lemma-Proof: { … AAC as proof artifact … }
X-Lemma-PoP: { agent_key_id, signature, body_hash, … }
```

Compat bootstrap:

```http
X-Lemma-Credential: (AAC JWT)
```

Sites SHOULD NOT accept bare `acting_ppid` without cryptographic verify (same rule as human PPID on signup).

### 5.3 AAC minimal claims

```json
{
  "sub": "did:lemma:aap_…",
  "aud": "app.example.com",
  "iss": "lemma.id",
  "iat": 1710000000,
  "exp": 1710086400,
  "profile_id": "runtime_openclaw_01",
  "profile_mode": "recurring",
  "scope": ["read", "write"],
  "resource_bounds": { "api.call": ["/v1/orders/*"] },
  "agent_key_id": "agent_runtime_01",
  "human_trust_tier": "T2",
  "human_ppid_ref": "did:lemma:ppid_…",
  "consent_epoch": 1710000000,
  "scope_h": "sha256:…",
  "provenance": {
    "human_proof_id": "prf_…",
    "delegation_id": "dlg_…",
    "issuer_kid": "lemma_…"
  }
}
```

`scope_h` MUST match verifier-side hash of declared scope + bounds — detects credential tampering vs derivation context.

---

## 6. Issuance orchestrator

Single endpoint; outputs AAP + AAC + agent key (once).

```http
POST /api/agent-acting/issue
Authorization: (wallet session | X-Lemma-Unlock)
Content-Type: application/json

{
  "aud": "app.example.com",
  "profile_mode": "recurring",
  "profile_id": "runtime_openclaw_01",
  "requested_scope": ["read", "write"],
  "resource_bounds": { "api.call": ["/v1/orders/*"] },
  "human_trust_floor": "T2",
  "ttl_seconds": 28800,
  "runtime_id": "runtime_openclaw_01"
}
```

**Orchestrator steps (fail closed):**

| Step | Layer | Check |
|------|-------|-------|
| 1 | L2 | Wallet unlocked; record `consent_epoch` |
| 2 | L1 | isHuman T2+ for `aud`; derive human `ppid_site` |
| 3 | L3 | Resolve site role / permission ceiling; `requested_scope ⊆ ceiling` |
| 4 | L2 | Mint or reuse `agent_key_id`; bind to `profile_id` |
| 5 | L1–L3 | Compute AAP from person_root + context; issue AAC |
| 6 | L4 | Register `runtime_id` if Agent Ops enabled |

**Response:**

```json
{
  "acting_ppid": "did:lemma:aap_…",
  "credential": { … },
  "agent_key_id": "…",
  "agent_private_key": "…",
  "profile_id": "…",
  "profile_mode": "recurring",
  "expires_at": 1710086400,
  "human_ppid": "did:lemma:ppid_…"
}
```

**One-shot variant:** omit `profile_id` → server generates `jti`; `profile_mode: "one_shot"`.

**Recurring variant:** same `profile_id` + unchanged `scope_h` + fresh consent → **same AAP** (account continuity for the agent principal). Change scope or revoke profile → new AAP on re-issue.

---

## 7. Verification (local-first)

Single SDK entry (Python + Node), mirrors isHuman verify ergonomics:

```python
result = verify_agent_acting(
    acting_ppid="did:lemma:aap_…",
    credential=aac,
    pop=pop_header,
    request={
        "method": "POST",
        "path": "/v1/orders",
        "body_hash": "…",
        "aud": "app.example.com",
    },
    policy={
        "human_trust_floor": "T2",
        "required_scope": ["write"],
    },
    revocation_state=local_cache,
)
# result.allowed, result.reason_code, result.human_trust_tier
```

**Internal steps:**

1. Verify AAC signature + `exp` + `aud` + `sub == acting_ppid`.
2. Recompute `scope_h`; deny if mismatch (`AAP_SCOPE_MISMATCH`).
3. Verify PoP + `agent_key_id` binding (`AAP_POP_FAILED`).
4. Verify embedded human tier ≥ floor (`AAP_HUMAN_TIER_LOW`).
5. Optional: verify human presentation embedded in AAC or linked `human_proof_id` (T2 signup-grade).
6. Revocation: profile_id / `delegation_id` / AAP in revocation set (`AAP_REVOKED`).
7. Operator path (L4): if `runtime_id` present, call or cache `authorize` outcome (`AAP_RUNTIME_DENIED`).

**Reason codes (stable):**

| Code | Meaning |
|------|---------|
| `AAP_HUMAN_REQUIRED` | L1 missing or below tier |
| `AAP_CONSENT_STALE` | L2 consent older than policy window |
| `AAP_SCOPE_MISMATCH` | Scope/bounds hash or live scope check failed |
| `AAP_POP_FAILED` | PoP / agent key binding failed |
| `AAP_EXPIRED` | AAC expired |
| `AAP_REVOKED` | Profile or chain revoked |
| `AAP_AUDIENCE_MISMATCH` | `aud` ≠ verifier site |
| `AAP_RUNTIME_DENIED` | L4 kill / taint / step-up |

---

## 8. Revocation & lifecycle

| Action | Target | Effect |
|--------|--------|--------|
| Revoke one-shot grant | `delegation_id` / `profile_id` (jti) | That AAP denied |
| Revoke recurring agent | `profile_id` or `runtime_id` | All AAC with that profile denied |
| Revoke human | human `ppid_site` + bloom | All AAPs for that human at site (via issuance gate + revoke queue) |
| Kill runtime (L4) | `runtime_id` | `authorize` denies; firewall fails closed |
| Re-scope | issue new AAC | new `scope_h` → **new AAP** (recurring profile must re-approve if scope widens) |

**Site integrator pattern for recurring agents:**

1. User approves agent once → store `acting_ppid` on agent config row.
2. Agent refreshes AAC before expiry (re-consent if consent window exceeded).
3. Site API checks `acting_ppid` + verify on each call — no human PPID on hot path.

---

## 9. vs OAuth / MCP / HDP (one page)

| Need | OAuth MCP (WorkOS, Auth0) | HDP draft | Lemma AAP |
|------|---------------------------|-----------|-----------|
| Fast MCP OAuth | **Strong** | Weak | Bridge via `exchange-proof` only |
| Verified unique human (L1) | Weak (logged-in user) | App-defined `poh` | **Strong** (isHuman T2+) |
| Agent-shaped principal | User token | Session chain | **AAP** (`did:lemma:aap_`) |
| Per-request PoP | DIY | Hop signatures | **Built-in** |
| Recurring agent identity | Long-lived user token | Session-bound | **Stable profile_id → stable AAP** |
| Local verify full chain | JWT verify only | Offline chain | **AAC + optional human embed** |
| Runtime kill / explain (L4) | DIY | Out of scope | **Agent Ops** |
| Pairwise privacy | IdP correlates | Issuer-dependent | **Site + AAP pairwise** |

**Win narrative:** OAuth gives the **user’s** token to the agent. Lemma gives an **agent principal** cryptographically tied to a **verified human + consent + scope** — without making every API call look like the human user.

**Don’t compete:** default MCP authorization server UX; enterprise SSO replacement.

---

## 10. Relationship to HBAP

HBAP is the **full four-layer JSON passport** (audit / enterprise export). AAP is the **compressed wire identity** for integrators who want isHuman-simple ergonomics.

```text
HBAP.layers → canonical audit bundle
AAP + AAC   → default agent hot-path (what sites store and verify)
```

Implement AAP as a **profile** of HBAP issuance, not a second stack:

- `POST /api/agent-acting/issue` wraps the HBAP orchestrator.
- `verify_agent_acting()` wraps `verify_human_backed_passport()` with AAP-specific checks.

---

## 11. Implementation plan

| Phase | Deliverable | Depends on |
|-------|-------------|------------|
| **P0** | `derive_agent_acting_ppid()` in `api/ppid.py` + golden vectors | person_root path |
| **P0** | `POST /api/agent-acting/issue` orchestrator | isHuman T2 gate, `issue-proof` |
| **P0** | `verify_agent_acting` Python/Node SDK + reason codes | existing verifier + PoP |
| **P0** | Agent Ops UI: “Issue acting ID” (recurring / one-shot) | wallet issue flow |
| **P1** | `GET /api/agent-acting/list`, revoke by `profile_id` | delegations store |
| **P1** | OAuth export: AAC → `lm_at_*` for MCP hosts | `exchange-proof` |
| **P1** | L1 end-of-loop human re-stamp hook on high-risk site events | isHuman stamp API |
| **P2** | Selective disclosure on human layer | VC extensions |

**P0 definition of done:**

1. Recurring: two issuances with same `profile_id` + scope → identical `acting_ppid`.
2. One-shot: two issuances → different `acting_ppid`.
3. Issue → PoP request → allow; revoke profile → deny within SLA.
4. Relying-site doc page: “Agent acting ID” parallel to isHuman quickstart.

**Explicit non-goals (P0):**

- Bare AAP without AAC (never document as supported).
- Replacing human `ppid` on human-login flows.
- Customer webhook surface (isHuman guardrails unchanged).

---

## 12. Positioning

**isHuman** — proves the human.  
**Agent Acting PPID** — the ID the agent uses on your site, backed by that human’s consent and your scope.  
**Agent Ops** — kill, contain, and explain when the agent runs in your infrastructure.

One-liner for exploration conversations:

> **Give agents a site-private acting ID — not your user’s OAuth token — rooted in verified humanity and revocable delegation.**

---

## 13. Open questions

1. **Prefix:** `did:lemma:aap_` vs `did:lemma:ppid_agent_` — prefer `aap_` for unambiguous principal typing in logs and policy.
2. **Consent refresh:** widen recurring AAC TTL but narrow `consent_epoch` window — forces wallet re-tap without rotating AAP.
3. **Subagents:** child AAP with `parent_profile_id` + `delegation_depth` in context (P1).
4. **Site-issued vs Lemma-issued AAC:** default Lemma-issued; optional site co-signature for L3-native IAM.
