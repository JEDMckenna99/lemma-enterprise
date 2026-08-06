# Identity root secret backup and restore drill

Network-critical secrets: `LEMMA_IDENTITY_ROOT_PEPPER_*` and
`LEMMA_PERSON_ROOT_SALT_*`. A **loss** forks every user's identity on the next
re-verification. A **leak** lets an attacker with document claims recompute
person roots and PPIDs retroactively.

Versioned rotation is documented in
[OPERATIONAL_HARDENING.md](../architecture/OPERATIONAL_HARDENING.md) §3.1. This
runbook covers **offline backup custody** and a **restore verification drill**
— not rotation itself.

---

## What to back up

| Secret | Env var(s) | Notes |
|--------|------------|-------|
| Document-root pepper | `LEMMA_IDENTITY_ROOT_PEPPER_V1` (+ `_V2`, …) | >= 32 bytes each |
| Person-root salt | `LEMMA_PERSON_ROOT_SALT_V1` (+ `_V2`, …) | >= 32 bytes each |
| Per-issuer pepper (if used) | `LEMMA_IDENTITY_ROOT_PEPPER_DIDIT_V1`, etc. | Optional isolation |
| Active version pointer | `LEMMA_ACTIVE_ROOT_VERSION` | Which version new IDVs use |

Back up **every version currently in use**, not just the active one. V1 must
remain available until no active credential references it.

---

## Offline custody

1. Export secrets from Heroku (or your secret manager) into a local file **never
   committed to git**.
2. Encrypt the archive with **age** or **gpg** and store the ciphertext in **two
   independent places** (e.g. password manager + offline USB, or two cloud
   accounts with different credentials).
3. If a second operator exists: split custody (one holds ciphertext, one holds
   passphrase). If solo: record an explicit acknowledgment in the drill log
   below that single-operator custody applies.
4. Do **not** store plaintext peppers/salts in Slack, email, or issue trackers.

Example (age):

```powershell
# Create encrypted backup (run locally, never commit plaintext)
age -r <your-age-public-key> -o identity-root-secrets-V1.age.txt `
  identity-root-secrets-plain.txt
```

---

## Restore drill checklist

Run this at least once after provisioning production secrets, and again after
any rotation that adds a new version.

1. **Prepare a throwaway environment** — local shell or ephemeral staging dyno.
   Do not run against production traffic.
2. **Restore** pepper + salt env vars from the encrypted backup into the
   throwaway env (along with `LEMMA_ACTIVE_ROOT_VERSION` if non-default).
3. **Run the verification script** (fixed test vector — no production data):

   ```powershell
   python scripts/identity_root_backup_drill.py --verify
   ```

   Expected output: `RESTORE_DRILL_OK` and three stable hex lines (document
   root, person root, sample site PPID).
4. **Compare** against the expected vector printed by `--print-expected` (or
   record the output from your first successful drill and store it with the
   backup).
5. **Destroy** the throwaway env and any plaintext files created during the drill.
6. **Record** the drill date in the log table below.

---

## Drill log

| Date | Operator | Versions backed up | Restore drill result | Notes |
|------|----------|--------------------|----------------------|-------|
| _(fill after first drill)_ | | V1 | | |

---

## Related docs

- [OPERATIONAL_HARDENING.md](../architecture/OPERATIONAL_HARDENING.md) §3.1 —
  pepper/salt rotation runbook
- [ENVIRONMENT_CONFIG.md](ENVIRONMENT_CONFIG.md) — env var reference
- [tests/test_identity_root_versioning.py](../../tests/test_identity_root_versioning.py) —
  versioning behavior tests
