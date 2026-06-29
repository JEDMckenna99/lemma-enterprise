# isHuman demo implementation outline

The demo covers the production relying-site contract:

- browser verification with canonical-hostname `siteId`;
- signed presentation verification on the relying-site backend;
- distinct PPIDs for two relying sites;
- persistent site block and authenticated site unblock;
- separate site doubt and deliberate `verifyFreshForBackend()` flow;
- same-PPID doubt clearing without cross-site effects;
- 30-day credential renewal with stable PPID and rotated credential ID.

The demo must not expose API keys or wallet secrets. Test IDV bypasses remain
disabled in production. Network-wide revocation controls and claims are retired;
legacy demo endpoints return HTTP 410 `network_revocation_retired`.
