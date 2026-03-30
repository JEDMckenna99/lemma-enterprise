# OpenClaw Key Rotation Drill

## Objective

Ensure key rotation does not break valid delegation verification and that retired keys are denied after cutoff.

## Steps

1. Capture current issuer key metadata.
2. Rotate issuer key material in controlled environment.
3. Validate:
   - newly issued token verifies with new key.
   - old-key token behavior matches policy during overlap window.
4. End overlap window and confirm old-key tokens are rejected.
5. Capture monitoring and audit outputs.

## Pass Criteria

- No verification outage during overlap window.
- Post-cutoff behavior is deterministic and logged.
- Recovery runbook tested.
