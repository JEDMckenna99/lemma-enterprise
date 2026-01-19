/**
 * @lemma/wallet TypeScript Definitions
 */

export interface WalletOptions {
  debug?: boolean;
  autoSync?: boolean;
}

export interface AuthState {
  state: 'locked' | 'unlocked' | 'unlocked_today';
  authenticated: boolean;
  reason?: string;
  unlockedAt?: number;
  expiresAt?: number;
  unlockedToday?: boolean;
  timeRemaining?: number;
}

export interface RegisterResult {
  success: boolean;
  credentialId: string;
  walletId: string;
  walletSecret: string;
}

export interface UnlockResult {
  success: boolean;
  expiresAt: number;
  expiresIn: number;
  walletId: string;
  walletSecret: string;
}

export interface Credential {
  id: string;
  issuer: string;
  signature?: string;
  claims?: Record<string, any>;
  credentialSubject?: Record<string, any>;
  type?: string[];
  packageType?: string;
  storedAt?: number;
  expiresAt?: number | string;
  expirationDate?: string;
  proof?: {
    proofValue?: string;
    signatureValue?: string;
  };
}

export interface VerificationResult {
  valid: boolean;
  reason?: string;
}

export interface RevocationStatus {
  revoked: boolean;
  unchecked?: boolean;
  lastSynced?: number;
}

export interface RevocationInfo {
  synced: boolean;
  count: number;
  lastSynced?: number;
  age?: number;
}

export interface WalletInfo {
  hasPasskey: boolean;
  hasWalletSecret: boolean;
  isUnlocked: boolean;
  credentialCount: number;
  passkeyCredentialId: string | null;
}

export interface ExportData {
  credentials: Credential[];
  issuers: any[];
  exportedAt: number;
}

export declare class LemmaWallet {
  constructor(options?: WalletOptions);

  /** Initialize the wallet (open IndexedDB) */
  init(): Promise<LemmaWallet>;

  /** Register a passkey for local wallet unlock */
  registerPasskey(): Promise<RegisterResult>;

  /** Unlock the wallet using passkey (100% local) */
  unlock(): Promise<UnlockResult>;

  /** Lock the wallet */
  lock(): Promise<void>;

  /** Check if wallet is currently unlocked */
  isUnlocked(): boolean;

  /** Get current authentication state */
  getAuthState(): AuthState;

  /** Get wallet secret for PPID derivation */
  getWalletSecret(): Promise<string | null>;

  /** Get passkey credential ID */
  getPasskeyCredentialId(): Promise<string | null>;

  /** Store a credential in the wallet */
  storeCredential(credential: Credential): Promise<{ success: boolean; id: string }>;

  /** Get credentials from the wallet */
  getCredentials(type?: string): Promise<Credential[]>;

  /** Remove a credential from the wallet */
  removeCredential(credentialId: string): Promise<{ success: boolean }>;

  /** Verify a credential locally */
  verifyCredential(credential: Credential): Promise<VerificationResult>;

  /** Sync revocation list from server */
  syncRevocations(): Promise<{ success: boolean; count?: number; offline?: boolean }>;

  /** Check if a credential is revoked */
  isRevoked(credentialId: string): Promise<RevocationStatus>;

  /** Get revocation cache info */
  getRevocationInfo(): Promise<RevocationInfo>;

  /** Get wallet info */
  getWalletInfo(): Promise<WalletInfo>;

  /** Export wallet data for backup */
  export(): Promise<ExportData>;

  /** Import wallet data from backup */
  import(data: ExportData): Promise<{ success: boolean }>;

  /** Check if wallet is ready */
  readonly isReady: boolean;
}

export default LemmaWallet;
