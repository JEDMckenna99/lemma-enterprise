> **Unimplemented internal proposal — not shipped.** Do not use for integration planning. Shipped relying-site behavior is documented in public docs at [lemma.id/docs](https://lemma.id/docs).

# Human-Backed Agent Passport (HBAP)

**Status:** Product spec (draft, unimplemented)  
**Owner:** Lemma.id  
**Date:** 2026-06-16  
**Audience:** Product, platform  

Related: `docs/architecture/CHAINED_PROOF_COMPOSITION.md`, `docs/api/DEVELOPER_AUTH_CONTRACT_V1.md`

---

## 1. Summary

The **Human-Backed Agent Passport (HBAP)** is a single portable artifact that answers four trust questions in one verify call:


| Layer             | Trust question                                           | Inside the passport                                  |
| ----------------- | -------------------------------------------------------- | ---------------------------------------------------- |
| **L1 — Site**     | Does this principal have an account/role on this site?   | Permission lemma (site-scoped VC)                    |
| **L2 — Human**    | Is a unique verified human behind this delegation?       | isHuman credential (site-bound presentation)         |
| **L3 — Delegate** | What may this agent do, for how long, on what resources? | Delegated proof (`authz_profile_v2` child hop)       |
| **L4 — Auth**     | Did the human consent recently (passkey/wallet)?         | Consent anchor (wallet unlock / passkey session ref) |


**Integrator experience:** one issuance approval → one JSON passport → one local verify function.  
**Not four products, four admin screens, or four headers on every request.**

Transport on the hot path remains what we already ship:

- `X-Lemma-Proof` + `X-Lemma-PoP` for agent actions (preferred)
- `X-Lemma-Credential` for beginner / firewall bootstrap (compat)
- `X-Agent-Token` is **out of scope** for HBAP (legacy operator compat only)

---

## 2. Problem & buyers


| Buyer                                            | Pain today                                                                             | HBAP promise                                                     |
| ------------------------------------------------ | -------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| **Relying sites** (commerce, signup, APIs)       | Cannot distinguish human-authorized agents from bots; OAuth reveals full user identity | Verify human + scoped agent without KYC dossier on their backend |
| **Regulated enterprises**                        | Audit asks “who authorized the AI?” — logs are operator-controlled                     | Tamper-evident chain: human → delegate → action                  |
| **Agent operators** (OpenClaw, Cursor, internal) | Tokens work for APIs; no runtime kill / taint / provenance                             | Same passport powers Agent Ops control plane                     |
| **MCP / tool hosts**                             | OAuth 2.1 scopes are coarse; stolen bearer tokens replay                               | Key-bound PoP + monotonic scope narrowing                        |


**Non-buyers (do not optimize HBAP for):** teams that only need SSO + OAuth MCP gateway with no human-uniqueness requirement.

---

## 3. The passport object (wire format)

One JSON document. Verifiers parse once; layers are nested claims, not separate round-trips.

```json
{
  "version": "hbap_v1",
  "profile": "authz_profile_v2",
  "passport_id": "pss_…",
  "issued_at": 1710000000,
  "expires_at": 1710086400,
  "aud": "app.example.com",
  "org_id": "org_default",
  "environment": "prod",

  "layers": {
    "site": { "credential": { "…": "permission lemma VC" } },
    "human": { "credential": { "…": "isHuman site VC" }, "trust_tier": "T2" },
    "delegate": {
      "proof_artifact": { "…": "authz_profile_v2" },
      "agent_key_id": "agent_runtime_01",
      "scope": ["read", "write"],
      "resource_bounds": { "api.call": ["/v1/orders/*"] },
      "delegation_depth": 1
    },
    "auth": {
      "consent_method": "passkey_root",
      "consent_at": 1710000000,
      "wallet_session_ref": "wss_…"
    }
  },

  "provenance": {
    "root_grant_id": "rgr_…",
    "human_proof_id": "prf_human_…",
    "delegated_proof_id": "dpf_…",
    "issuer_kid": "lemma_…"
  }
}
```

**Privacy rule:** pairwise PPIDs per layer — verifiers MUST NOT receive a global correlatable user id unless the relying site already holds that relationship via L1.

---

## 4. Layer → API mapping (single surface per concern)

### 4.1 Issuance (control plane — one orchestrated endpoint)


| Step | Layer       | Canonical API (new)                       | Existing API (today)                             | Gate                                        |
| ---- | ----------- | ----------------------------------------- | ------------------------------------------------ | ------------------------------------------- |
| 1    | L4 Auth     | `POST /api/passport/issue` (orchestrator) | wallet unlock / `X-Lemma-Unlock`                 | Passkey-unlocked wallet session             |
| 2    | L2 Human    | *(embedded in orchestrator)*              | `POST /api/ishuman/derive-site-proof`, IDV popup | `human: true`, trust tier ≥ policy floor    |
| 3    | L1 Site     | *(embedded)*                              | permission lemma via site IAM                    | Site role resolved for PPID                 |
| 4    | L3 Delegate | *(embedded)*                              | `POST /api/wallet/runtimes/issue-proof`          | Scope ⊆ site role; optional runtime connect |


**Target orchestrator (P0 build):**

```http
POST /api/passport/issue
Authorization: (wallet session cookie | X-Lemma-Unlock)
Content-Type: application/json

{
  "aud": "app.example.com",
  "site_id": "app.example.com",
  "runtime_id": "agent_runtime_01",
  "requested_scope": ["read", "write"],
  "resource_bounds": { "api.call": ["/v1/*"] },
  "human_trust_floor": "T2",
  "ttl_seconds": 28800,
  "org_id": "org_default",
  "environment": "prod"
}
```

**Response:** full `hbap_v1` document + `agent_private_key` (once) for PoP signing.

**UX:** one browser approval (“Authorize agent for app.example.com”) — same mental model as World AgentKit, without fourLemma-specific steps.

### 4.2 Verification (data plane — one function, local-first)


| Concern                   | Canonical verify entry                         | Existing implementation                             |
| ------------------------- | ---------------------------------------------- | --------------------------------------------------- |
| **Whole passport**        | `verifyHumanBackedPassport(passport, context)` | *new thin wrapper*                                  |
| L1 + L3 chain             | proof-native allow/deny                        | `api/authz/verifier.py` → `evaluate_proof_native()` |
| L3 PoP                    | request binding                                | `api/authz/replay.py` → `validate_pop_replay()`     |
| L2 Human                  | site-bound human claim                         | `lemma_ishuman_verify.py` / `@lemma/ishuman-verify` |
| L1 Permission             | signed permission VC                           | existing lemma trust-core verify                    |
| Revocation                | fail-closed                                    | `GET /api/authz/revocation/delta` + local cache     |
| Runtime policy (operator) | kill / taint / step-up                         | `POST /api/wallet/runtimes/{id}/authorize`          |


**Target verify API (SDKs — Node + Python):**

```python
result = verify_human_backed_passport(
    passport=payload,
    request={
        "method": "POST",
        "path": "/v1/orders",
        "body_hash": "…",
        "aud": "app.example.com",
    },
    pop=pop_header,
    policy={
        "human_trust_floor": "T2",
        "required_scope": ["write"],
        "max_delegation_depth": 2,
    },
    revocation_state=local_cache,  # optional; fetches delta if stale
)
# result.allowed, result.reason_code, result.layers_verified
```

**HTTP verify (optional hosted helper for non-local verifiers):**

```http
POST /api/passport/verify
Content-Type: application/json

{ "passport": {…}, "pop": {…}, "request": {…}, "policy": {…} }
```

Prefer **local verify** for latency and privacy (matches isHuman integration model).

### 4.3 Revocation & lifecycle


| Action                         | API                                                    | Notes                          |
| ------------------------------ | ------------------------------------------------------ | ------------------------------ |
| Revoke passport / delegate hop | `POST /api/auth/revoke` (`jti` = `delegated_proof_id`) | Existing control plane         |
| Revoke human root              | isHuman bloom + site revoke queue                      | Existing trust & safety        |
| Kill runtime                   | `POST /api/wallet/runtimes/{id}/kill`                  | Agent Ops — denies authorize   |
| List active                    | `GET /api/passport/list` (wallet-auth)                 | *new*; wraps delegations store |


---

## 5. IETF / standards profile choice

**Decision:** ship `**hbap_v1` as a Lemma profile** that **composes** existing standards — do not pick a single IETF draft as the only wire format.


| Standard track                         | Role in HBAP                           | Rationale                                                                                                                                                                        |
| -------------------------------------- | -------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **W3C VC Data Model 2.0 + VC-JWT**     | L1 permission + L2 isHuman credentials | Interop with MCP+VC draft ([draft-diaconu-agents-authz-info-sharing](https://datatracker.ietf.org/doc/html/draft-diaconu-agents-authz-info-sharing-00)); portable across domains |
| **Lemma `authz_profile_v2`**           | L3 delegated proof + PoP               | Already implemented, tested, firewall-integrated (`DEVELOPER_AUTH_CONTRACT_V1.md`)                                                                                               |
| **HDP-style provenance** (informative) | `provenance` block + human hop at root | Answers “which human authorized this chain?” — gap OAuth txn tokens leave open; map to HDP semantics without requiring HDP registry                                              |
| **OAuth 2.1 + RFC 9396 RAR**           | **Bridge, not core**                   | `POST /api/auth/exchange-proof` emits `lm_at_`* for legacy MCP/OAuth consumers; RAR `authorization_details` maps from `resource_bounds`                                          |
| **IETF AAP**                           | **Claim naming alignment only**        | Reuse `act` / principal / task context field names in `provenance` for enterprise SIEM parity                                                                                    |
| **PEDIGREE / DRP**                     | **Phase 2**                            | Completion blocks + operator instruction hash (DRP) for regulated drift detection — defer until P1 passport ships                                                                |


**Why not OAuth-only:** market default for MCP, but weak on cross-domain VC portability, pairwise privacy, and offline human-provenance verification. HBAP uses OAuth as a **sunsetting compat export**, not the source of truth.

**Why not HDP-only:** strong provenance narrative, but greenfield protocol; Lemma already has VC issuance + verifier + Agent Ops. HBAP extends what exists.

---

## 6. Implementation status → build plan


| Component              | Today                                  | HBAP P0                          | HBAP P1                   |
| ---------------------- | -------------------------------------- | -------------------------------- | ------------------------- |
| L4 passkey gate        | ✅ wallet unlock                        | wrap in orchestrator             | —                         |
| L1 permission lemma    | ✅ `issue_permission_lemma`             | embed in passport                | site policy templates     |
| L3 delegated proof     | ✅ `issue-proof`, verifier, PoP         | embed in passport                | multi-hop attenuation     |
| L2 isHuman in chain    | ❌ parallel only                        | **gate issuance on T2+**         | selective disclosure      |
| Single passport object | ❌                                      | `**hbap_v1` schema + issue API** | hosted verify optional    |
| Orchestrator UI        | partial (Agent Ops + isHuman separate) | one “Issue passport” flow        | developer docs + SDK      |
| OAuth export           | ✅ `exchange-proof`                     | document mapping from passport   | RAR-shaped export         |
| Agent token path       | ✅ compat                               | explicit non-HBAP                | deprecate from product UX |


**P0 definition of done (8–12 weeks, internal pilot):**

1. `POST /api/passport/issue` returns `hbap_v1` when wallet unlocked + isHuman T2 satisfied.
2. Python + Node `verify_human_backed_passport()` matches server `evaluate_proof_native` outcomes on golden fixtures.
3. Agent Ops UI issues passport (already redirected to wallet issue-proof — extend with L2 gate).
4. One E2E: issue → protected action with PoP → revoke → deny within SLA.
5. Evidence bundle script (`lemma incident-bundle` or successor) includes passport + decision receipt.

**Explicit non-goals for P0:**

- Full DRP operator-instruction hash
- Ledger-anchored DIDs (arxiv multi-agent paper model)
- Replacing OAuth MCP gateways for enterprise SSO
- Customer webhook surface (isHuman guardrails unchanged)

---

## 7. Reason codes (verify contract)

Stable codes for integrators (extend existing auth taxonomy):


| Code                          | Layer | Meaning                                 |
| ----------------------------- | ----- | --------------------------------------- |
| `HBAP_HUMAN_REQUIRED`         | L2    | No human credential or tier below floor |
| `HBAP_SITE_ROLE_INSUFFICIENT` | L1    | Permission lemma lacks required scope   |
| `HBAP_DELEGATION_EXPIRED`     | L3    | Delegate hop expired                    |
| `HBAP_CHAIN_BROKEN`           | L3    | Parent/child proof mismatch             |
| `HBAP_POP_FAILED`             | L3    | PoP missing, replay, or wrong key       |
| `HBAP_REVOKED`                | any   | Ancestor in revocation set              |
| `HBAP_CONSENT_STALE`          | L4    | Wallet consent older than policy window |
| `HBAP_AUDIENCE_MISMATCH`      | L1/L3 | `aud` ≠ verifier site                   |


---

## 8. Success metrics


| Metric                          | Target (pilot)                                  |
| ------------------------------- | ----------------------------------------------- |
| Issuance UX                     | ≤ 2 user steps (unlock + approve)               |
| Local verify p95                | ≤ 5 ms (same budget as authz fast path)         |
| Revoke → deny                   | ≤ 5 s hard max (existing Agent Ops SLA)         |
| Integrator time-to-first-verify | ≤ 30 min (SDK + one API route)                  |
| False “human-backed” rate       | 0 on golden tests; shadow compare vs token path |


---

## 9. Positioning one-liner

**isHuman proves the human. Permission lemmas prove the account. Delegated proofs prove the agent. HBAP packages all three — plus fresh consent — into one verifiable passport for the agentic web.**

Operator-only surfaces (Firewall, runtime kill, CLI) consume the same passport; relying sites verify locally and never need Agent Ops UI.

---

## 10. Next engineering tickets (suggested)

1. **Schema:** `schemas/hbap_v1.json` + golden fixtures in `tests/fixtures/hbap/`
2. **API:** `POST /api/passport/issue`, `GET /api/passport/list` in `api/passport_api.py`
3. **Gate:** require isHuman T2+ in issuance orchestrator before `issue-proof`
4. **SDK:** `verify_human_backed_passport` in Python + Node (wrap existing verifiers)
5. **UI:** Agent Ops “Issue Proof” → “Issue passport”; link from `/admin/agent-delegation`
6. **Docs:** public integrator page at `/docs/passport` (when P0 ships)

