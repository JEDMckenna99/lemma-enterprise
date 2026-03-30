export interface LemmaCredential {
  id?: string;
  subject?: string;
  sub?: string;
  claims?: Record<string, unknown>;
  credentialSubject?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface LemmaVerificationResult {
  valid: boolean;
  reason?: string;
  [key: string]: unknown;
}

export type VerifyCredentialFn = (
  credential: LemmaCredential
) => LemmaVerificationResult | Promise<LemmaVerificationResult>;

export interface LemmaAuthOptions {
  verifyCredential: VerifyCredentialFn;
  requiredSite?: string | null;
}

export interface LemmaPrincipal {
  ppid: string;
  credentialId: string | null;
  permissionId: string;
  scope: string[];
  siteBinding: string | null;
  rawCredential: LemmaCredential;
}

export interface LemmaErrorPayload {
  success: false;
  error: string;
  message: string;
}

export interface LemmaRequestLike {
  header(name: string): unknown;
  lemmaAuthError?: string;
  lemmaPrincipal?: LemmaPrincipal;
  [key: string]: unknown;
}

export interface LemmaResponseLike {
  status(code: number): LemmaResponseLike;
  json(body: unknown): unknown;
  [key: string]: unknown;
}

export type LemmaNextFunction = (error?: unknown) => void;

export type LemmaMiddleware = (
  req: LemmaRequestLike,
  res: LemmaResponseLike,
  next: LemmaNextFunction
) => unknown | Promise<unknown>;

export interface RequireLemmaOptions {
  scope?: string | null;
  siteBound?: boolean;
}

export interface LemmaAuth {
  attachPrincipal(): LemmaMiddleware;
  requireLemma(options?: RequireLemmaOptions): LemmaMiddleware;
  decodeLemmaHeader(rawHeader: string | null | undefined): LemmaCredential | null;
  extractPrincipal(credential: LemmaCredential): LemmaPrincipal | null;
}

export function createLemmaAuth(options: LemmaAuthOptions): LemmaAuth;
