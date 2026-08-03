# Sign in with lemma.id — demo implementation outline

The demo covers the production relying-site contract in three hub concepts:

| Concept | What the demo shows |
| ------- | ------------------- |
| **Create** | Passkey-backed lemma.id; optional human proof slot when policy requires IDV |
| **Sign in** | Drop-in `<lemma-signin>` on relying sites; hub uses `verifyForBackend` for dual-site PPID compare; distinct PPIDs for two relying sites; signed presentation verification on the relying-site backend |
| **Enforce** | Set assurance level (`passkey` → `ishuman`, same PPID after step-up); site doubt + deliberate `verifyFreshForBackend()`; persistent site ban + authenticated site unblock |

Additional relying-site depth:

- 30-day credential renewal with stable PPID and rotated credential ID
- Unique presale code ledger keyed by `(drop_id, ppid)` on the tickets demo site at `/?tour=presale` (presence stamps, see presale script)

The demo must not expose API keys or local identity seeds (wallet_secret). Test IDV bypasses remain
disabled in production. Network-wide revocation controls and claims are retired;
legacy demo endpoints return HTTP 410 `network_revocation_retired`.
