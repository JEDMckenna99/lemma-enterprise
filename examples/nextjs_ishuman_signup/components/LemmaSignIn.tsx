"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Script from "next/script";

declare global {
  interface Window {
    ProofVerifier?: new (opts: { siteId: string }) => {
      verifyForBackend: (opts: {
        autoProvision?: boolean;
        requiredAssurance?: string;
      }) => Promise<{
        ok: boolean;
        presentation?: unknown;
        ppid?: string;
        assurance?: string;
        reason?: string;
        timeMs?: number;
      }>;
    };
    LemmaSignInElement?: typeof HTMLElement;
  }
}

export type LemmaSignInSuccessDetail = {
  presentation: unknown;
  ppid: string;
  assurance: string;
  timeMs?: number;
};

export type LemmaSignInErrorDetail = {
  reason: string;
  message?: string;
  ppid?: string | null;
  assurance?: string | null;
  timeMs?: number;
};

type LemmaSignInProps = {
  siteId: string;
  requiredAssurance?: "passkey" | "ishuman";
  autoProvision?: boolean;
  label?: string;
  disabled?: boolean;
  onSuccess?: (detail: LemmaSignInSuccessDetail) => void | Promise<void>;
  onError?: (detail: LemmaSignInErrorDetail) => void;
  className?: string;
};

export default function LemmaSignIn({
  siteId,
  requiredAssurance = "passkey",
  autoProvision = true,
  label = "Sign in with lemma.id",
  disabled = false,
  onSuccess,
  onError,
  className,
}: LemmaSignInProps) {
  const ref = useRef<HTMLElement | null>(null);
  const [sdkReady, setSdkReady] = useState(false);

  const handleSuccess = useCallback(
    async (event: Event) => {
      const detail = (event as CustomEvent<LemmaSignInSuccessDetail>).detail;
      await onSuccess?.(detail);
    },
    [onSuccess],
  );

  const handleError = useCallback(
    (event: Event) => {
      const detail = (event as CustomEvent<LemmaSignInErrorDetail>).detail;
      onError?.(detail);
    },
    [onError],
  );

  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    el.addEventListener("lemma-signin-success", handleSuccess);
    el.addEventListener("lemma-signin-error", handleError);
    return () => {
      el.removeEventListener("lemma-signin-success", handleSuccess);
      el.removeEventListener("lemma-signin-error", handleError);
    };
  }, [handleSuccess, handleError, sdkReady]);

  return (
    <>
      <Script
        src="https://lemma.id/sdk/proof-verifier.js"
        strategy="afterInteractive"
        onLoad={() => setSdkReady(true)}
      />
      <Script
        src="https://lemma.id/sdk/lemma-signin.js"
        strategy="afterInteractive"
      />
      {/* @ts-expect-error custom element */}
      <lemma-signin
        ref={ref}
        class={className}
        site-id={siteId}
        required-assurance={requiredAssurance}
        auto-provision={autoProvision ? "true" : "false"}
        label={label}
        disabled={disabled || !sdkReady ? true : undefined}
      />
    </>
  );
}
