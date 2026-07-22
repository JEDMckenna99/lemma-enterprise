# Next.js isHuman signup (Section 10)

Client-only browser SDK + App Router API route that verifies presentations server-side.

## Client (`app/signup/page.tsx`)

```tsx
"use client";
import { useState } from "react";

declare global {
  interface Window {
    ProofVerifier: new (opts: { siteId: string }) => {
      verifyForBackend: (opts: { autoProvision?: boolean; requiredAssurance?: string }) => Promise<{
        ok: boolean;
        presentation?: unknown;
      }>;
    };
  }
}

export default function SignupPage() {
  const [status, setStatus] = useState("idle");
  async function onSubmit() {
    const verifier = new window.ProofVerifier({ siteId: "app.example.com" });
    const { ok, presentation } = await verifier.verifyForBackend({
      autoProvision: true,
      requiredAssurance: "ishuman",
    });
    if (!ok) {
      setStatus("denied");
      return;
    }
    const resp = await fetch("/api/signup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ presentation }),
    });
    setStatus(resp.ok ? "created" : "server_denied");
  }
  return (
    <main>
      <button type="button" onClick={onSubmit}>Sign up</button>
      <p>{status}</p>
      <script src="https://lemma.id/sdk/v1.9.2/proof-verifier.js" crossOrigin="anonymous" />
    </main>
  );
}
```

## Server route (`app/api/signup/route.ts`)

Use `@lemma/ishuman-verify` or call your Python/Node verifier service. Fail closed when `result.ok` is false.

Pin SDK URL from [`ISHUMAN_SDK_VERSIONS.json`](../../docs/sdk/ISHUMAN_SDK_VERSIONS.json).
