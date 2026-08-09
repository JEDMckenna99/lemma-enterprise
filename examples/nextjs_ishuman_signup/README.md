# Next.js — verify a lemma proof

Runnable App Router example: browser SDK → verify presentation → optional HttpOnly session cookie.
## Run

```bash
cd examples/nextjs_ishuman_signup
npm install
npm run dev
```

Open http://localhost:5052

## Env

| Variable | Default |
|----------|---------|
| `SITE_ID` / `NEXT_PUBLIC_SITE_ID` | `localhost` |
| `REQUIRED_ASSURANCE` / `NEXT_PUBLIC_REQUIRED_ASSURANCE` | `passkey` |
| `SESSION_SECRET` | `dev-change-me` |

## Files

- `app/page.tsx` — client sign-in button + `ProofVerifier`
- `app/api/login/route.ts` — verify presentation, set session
- `app/api/me/route.ts` — auth guard demo
- `lib/verifier.ts` — local `@lemma.id/proof-verifier` wrapper

For isHuman step-up, set `REQUIRED_ASSURANCE=ishuman`.
