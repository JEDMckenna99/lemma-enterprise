/**
 * CDP-backed virtual authenticator for lemma.id passkey tests.
 *
 * The private key is generated inside the test browser profile and dies with
 * it, so no real passkey or unlock gesture is ever involved. The ceremonies are
 * spec-valid: real signatures, real authenticator data, real UV/BE/BS flags, so
 * server-side verification runs unmodified.
 *
 * Chrome scopes an authenticator to one frame tree, so a popup opened by
 * ProofVerifier starts with an empty one. This helper mirrors every credential
 * into a shared vault and replays the vault into each new page, so a passkey
 * created in one popup is still usable in the next.
 */
import type { BrowserContext, Page } from '@playwright/test';

export interface VirtualAuthenticatorOptions {
  protocol?: 'ctap2' | 'u2f';
  transport?: 'usb' | 'nfc' | 'ble' | 'cable' | 'internal';
  hasResidentKey?: boolean;
  hasUserVerification?: boolean;
  hasPrf?: boolean;
  isUserVerified?: boolean;
  automaticPresenceSimulation?: boolean;
  defaultBackupEligibility?: boolean;
  defaultBackupState?: boolean;
}

export interface VirtualCredential {
  credentialId: string;
  isResidentCredential: boolean;
  rpId?: string;
  privateKey: string;
  userHandle?: string;
  signCount: number;
  largeBlob?: string;
  backupEligibility?: boolean;
  backupState?: boolean;
}

/**
 * Models a platform authenticator (Touch ID / Windows Hello) that satisfies
 * everything lemma-wallet.js asks for. `hasPrf` is mandatory: the wallet
 * derives its at-rest storage key from the PRF extension and throws
 * `prf_required_for_encrypted_storage` without it.
 */
export const LEMMA_PLATFORM_AUTHENTICATOR: Required<VirtualAuthenticatorOptions> = {
  protocol: 'ctap2',
  transport: 'internal',
  hasResidentKey: true,
  hasUserVerification: true,
  hasPrf: true,
  isUserVerified: true,
  automaticPresenceSimulation: true,
  defaultBackupEligibility: false,
  defaultBackupState: false,
};

/** Playwright types `send` against its bundled protocol union; WebAuthn needs a raw escape hatch. */
interface RawCdpSession {
  send(method: string, params?: Record<string, unknown>): Promise<any>;
  on(event: string, handler: (payload: any) => void): void;
  detach(): Promise<void>;
}

interface Attachment {
  page: Page;
  cdp: RawCdpSession;
  authenticatorId: string;
}

export class VirtualAuthenticator {
  private readonly attachments: Attachment[] = [];
  private readonly vault = new Map<string, VirtualCredential>();
  private closed = false;

  constructor(
    private readonly context: BrowserContext,
    readonly options: Required<VirtualAuthenticatorOptions>,
  ) {}

  async start(): Promise<void> {
    this.context.on('page', (page) => {
      // A popup could in principle reach navigator.credentials before this
      // resolves. In practice /verify does server round-trips first, and
      // waitForAttachment() below lets a test close the gap explicitly.
      void this.attach(page).catch(() => {});
    });
    for (const page of this.context.pages()) {
      await this.attach(page);
    }
  }

  async attach(page: Page): Promise<void> {
    if (this.closed || page.isClosed()) return;
    if (this.attachments.some((a) => a.page === page)) return;

    const cdp = (await this.context.newCDPSession(page)) as unknown as RawCdpSession;
    await cdp.send('WebAuthn.enable', { enableUI: false });
    const { authenticatorId } = await cdp.send('WebAuthn.addVirtualAuthenticator', {
      options: this.options,
    });

    cdp.on('WebAuthn.credentialAdded', ({ credential }) => this.remember(credential));
    cdp.on('WebAuthn.credentialAsserted', ({ credential }) => this.remember(credential));

    const attachment: Attachment = { page, cdp, authenticatorId };
    this.attachments.push(attachment);

    for (const credential of this.vault.values()) {
      await cdp.send('WebAuthn.addCredential', { authenticatorId, credential });
    }
  }

  /** Resolves once the page has an authenticator, for popups that race the `page` event. */
  async waitForAttachment(page: Page, timeoutMs = 5_000): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (this.attachments.some((a) => a.page === page)) return;
      await page.waitForTimeout(25);
    }
    await this.attach(page);
  }

  /** Every credential this authenticator has seen, across pages and popups. */
  credentials(): VirtualCredential[] {
    return [...this.vault.values()];
  }

  /** Live read from one page's authenticator, rather than the mirrored vault. */
  async credentialsOn(page: Page): Promise<VirtualCredential[]> {
    const attachment = this.attachmentFor(page);
    const { credentials } = await attachment.cdp.send('WebAuthn.getCredentials', {
      authenticatorId: attachment.authenticatorId,
    });
    return credentials as VirtualCredential[];
  }

  /**
   * Flips whether user verification succeeds. Use this to prove the server
   * rejects an assertion with the UV flag clear.
   */
  async setUserVerified(isUserVerified: boolean): Promise<void> {
    for (const { cdp, authenticatorId } of this.attachments) {
      await cdp.send('WebAuthn.setUserVerified', { authenticatorId, isUserVerified });
    }
  }

  /** Simulates a device the user no longer has: keys gone, server records intact. */
  async clearCredentials(): Promise<void> {
    this.vault.clear();
    for (const { cdp, authenticatorId } of this.attachments) {
      await cdp.send('WebAuthn.clearCredentials', { authenticatorId });
    }
  }

  async dispose(): Promise<void> {
    this.closed = true;
    for (const { page, cdp, authenticatorId } of this.attachments) {
      if (page.isClosed()) continue;
      try {
        await cdp.send('WebAuthn.removeVirtualAuthenticator', { authenticatorId });
        await cdp.send('WebAuthn.disable');
        await cdp.detach();
      } catch {
        // Page torn down mid-test; the authenticator went with it.
      }
    }
    this.attachments.length = 0;
  }

  private attachmentFor(page: Page): Attachment {
    const attachment = this.attachments.find((a) => a.page === page);
    if (!attachment) throw new Error('No virtual authenticator attached to this page');
    return attachment;
  }

  private remember(credential: VirtualCredential): void {
    const existing = this.vault.get(credential.credentialId);
    if (existing && existing.signCount > credential.signCount) return;
    this.vault.set(credential.credentialId, credential);
  }
}

export async function installVirtualAuthenticator(
  context: BrowserContext,
  overrides: VirtualAuthenticatorOptions = {},
): Promise<VirtualAuthenticator> {
  const authenticator = new VirtualAuthenticator(context, {
    ...LEMMA_PLATFORM_AUTHENTICATOR,
    ...overrides,
  });
  await authenticator.start();
  return authenticator;
}
