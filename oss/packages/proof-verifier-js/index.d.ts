export type AssuranceTier = "passkey" | "ishuman";

export interface VerifyResult {
  ok: boolean;
  reason?: string;
  ppid?: string;
  assurance?: AssuranceTier;
  credentialId?: string | null;
  boundSiteId?: string;
  [key: string]: unknown;
}

export interface Presentation {
  credential?: Record<string, unknown>;
  session_assertion?: Record<string, unknown>;
  session_signature?: string;
  [key: string]: unknown;
}

export interface VerifierOptions {
  siteId: string;
  lemmaOrigin?: string;
  refreshMs?: number;
  maxSessionAgeSeconds?: number;
  requireSessionAssertion?: boolean;
  requiredAssurance?: AssuranceTier;
  maxActionAgeSeconds?: number;
  nonceStoreMode?: "optional" | "required";
  freshPasskeyMaxAgeSeconds?: number;
  networkRootPubkeys?: string[] | null;
  fetch?: typeof fetch;
}

export interface LemmaVerifier {
  verify(presentation: Presentation): Promise<VerifyResult>;
  refresh(): Promise<void>;
}

export function createVerifier(options: VerifierOptions): LemmaVerifier;

export function canonicalizeSiteHostname(value: string): string;

export function assuranceMeetsPolicy(
  actual: string | undefined,
  required: AssuranceTier | string,
): boolean;

export function verifyPresentation(
  presentation: Presentation,
  options: VerifierOptions,
): Promise<VerifyResult>;

export function verifyWithPolicy(
  presentation: Presentation,
  options: VerifierOptions,
): Promise<VerifyResult>;

export function verifyStamp(
  stamp: unknown,
  options: VerifierOptions & { durable?: boolean },
): Promise<VerifyResult>;

export function verifyActionStamp(
  stamp: unknown,
  options: VerifierOptions,
): Promise<VerifyResult>;
