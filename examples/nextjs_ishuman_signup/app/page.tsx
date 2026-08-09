"use client";

import { useCallback, useEffect, useState } from "react";
import Script from "next/script";

declare global {
  interface Window {
    ProofVerifier: new (opts: { siteId: string }) => {
      verifyForBackend: (opts: {
        autoProvision?: boolean;
        requiredAssurance?: string;
      }) => Promise<{ ok: boolean; presentation?: unknown; reason?: string }>;
    };
  }
}

const SITE_ID = process.env.NEXT_PUBLIC_SITE_ID || "localhost";
const REQUIRED = process.env.NEXT_PUBLIC_REQUIRED_ASSURANCE || "passkey";

export default function SignInPage() {
  const [status, setStatus] = useState("Loading…");
  const [signedIn, setSignedIn] = useState(false);

  const refresh = useCallback(async () => {
    const me = await fetch("/api/me", { credentials: "include" });
    if (me.ok) {
      const data = await me.json();
      setStatus(`Signed in as ${data.ppid}`);
      setSignedIn(true);
      return;
    }
    setStatus("Not signed in");
    setSignedIn(false);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function onSignIn() {
    if (!window.ProofVerifier) {
      setStatus("SDK not loaded");
      return;
    }
    setStatus("Opening lemma.id…");
    const verifier = new window.ProofVerifier({ siteId: SITE_ID });
    const { ok, presentation, reason } = await verifier.verifyForBackend({
      autoProvision: true,
      requiredAssurance: REQUIRED,
    });
    if (!ok) {
      setStatus(reason || "not_verified");
      return;
    }
    const resp = await fetch("/api/login", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ presentation }),
    });
    if (!resp.ok) {
      setStatus("Server denied login");
      return;
    }
    await refresh();
  }

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 480 }}>
      <Script src="https://lemma.id/sdk/proof-verifier.js" strategy="afterInteractive" />
      <h1>Verify a lemma proof</h1>
      <p>{status}</p>
      {!signedIn && (
        <button type="button" onClick={onSignIn}>
          Sign in with lemma.id
        </button>
      )}
      <p>
        <a href="/api/logout">Logout</a>
      </p>
    </main>
  );
}
