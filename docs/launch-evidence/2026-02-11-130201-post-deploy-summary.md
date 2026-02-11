# Post-Deploy Launch Gate Summary

- Base URL: \$BaseUrl\
- Timestamp: 2026-02-11T13:02:05.4031790-05:00
- Artifacts:
  - \$smokeOut\
  - \$transportOut\
  - \$originOut\

## Pass Conditions

- Smoke script exits successfully.
- HTTP redirects to HTTPS, TLS <=1.1 handshake fails, TLS1.2 succeeds.
- Allowed origin returns ACAO for passkey auth begin, disallowed origin does not receive credentialed ACAO on POST.

## Manual Follow-up Required

- Browser/device matrix for passkey registration + algorithm capture.
- Revocation propagation test: revoke credential in deployed build, then verify deny behavior after sync.
