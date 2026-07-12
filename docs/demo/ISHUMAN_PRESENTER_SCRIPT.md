# isHuman demo presenter script

1. Verify once and show two distinct site-private PPIDs for ticketing and
   trials.
2. Block the ticketing PPID and show ticketing denied while trials remains
   valid.
3. Explain that the block survives credential renewal, wallet recovery,
   document renewal, and fresh IDV until ticketing explicitly unblocks it.
4. Create a temporary site doubt and invoke `verifyFreshForBackend()`.
5. Show that matching fresh IDV clears only the ticketing doubt; it never clears
   a site block or touches trials.
6. Show local backend presentation verification and the privacy-safe billing
   event fields.
7. On the tickets demo site, claim a unique presale code once; a second claim
   with the same wallet is denied with `allocation_already_claimed`.

Do not describe or demonstrate network-wide user enumeration or revocation.
Those legacy endpoints are retired and return HTTP 410.
