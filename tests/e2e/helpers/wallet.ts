/**
 * Page-side helpers for driving LemmaWallet directly.
 *
 * `/unlock` is the simplest same-origin page that loads lemma-keys.js,
 * wallet-at-rest-crypto.js and lemma-wallet.js, so the passkey ceremony happens
 * in the page under test rather than in a popup. Tests get their own wallet
 * instance and never touch the template's `wallet` global.
 */
import type { Page } from '@playwright/test';

/** WebAuthn needs a secure context, and Chrome grants that to localhost but not 127.0.0.1. */
export const WALLET_ORIGIN_HOST = 'localhost';
export const WALLET_PAGE = '/unlock';

export interface EnrollResult {
  success: boolean;
  credentialId?: string;
  walletId?: string;
  walletSecret?: string;
  method?: string;
}

export type Attempt<T> = { ok: true; value: T } | { ok: false; error: string };

/** Loads the wallet page and exposes a fresh, shared-per-page wallet instance. */
export async function openWalletPage(page: Page): Promise<void> {
  await page.goto(WALLET_PAGE);
  await page.waitForFunction(
    () => typeof (window as any).LemmaWallet === 'function'
      && typeof (window as any).WalletAtRestCrypto === 'object',
  );
  await page.evaluate(async () => {
    const w = window as any;
    w.__lemmaWallet = new w.LemmaWallet();
    await w.__lemmaWallet.init();
  });
}

/** Wipes IndexedDB and the lemma_/ishuman_ storage keys, so each test starts device-clean. */
export async function purgeDevice(page: Page): Promise<void> {
  await page.evaluate(async () => {
    const w = window as any;
    await w.LemmaWallet.purgeAllDeviceData(
      w.__lemmaWallet ? { instances: [w.__lemmaWallet] } : {},
    );
  });
}

/** First-device enrollment: navigator.credentials.create + server device-enroll. */
export function enroll(page: Page, options: Record<string, unknown> = {}): Promise<EnrollResult> {
  return page.evaluate(
    (opts) => (window as any).__lemmaWallet.registerPasskey(opts),
    options,
  );
}

/** Existing-device unlock: navigator.credentials.get + server session-unlock. */
export function unlock(page: Page, options: Record<string, unknown> = {}): Promise<any> {
  return page.evaluate((opts) => (window as any).__lemmaWallet.unlock(opts), options);
}

export function lock(page: Page): Promise<any> {
  return page.evaluate(() => (window as any).__lemmaWallet.lock());
}

export function walletInfo(page: Page): Promise<any> {
  return page.evaluate(() => (window as any).__lemmaWallet.getWalletInfo({ lite: true }));
}

export function derivePPID(page: Page, siteId: string): Promise<string> {
  return page.evaluate((site) => (window as any).__lemmaWallet.derivePPID(site), siteId);
}

/** True once the PRF-derived at-rest key is bound, which gates every encrypted read. */
export function atRestKeyBound(page: Page): Promise<boolean> {
  return page.evaluate(() => Boolean((window as any).__lemmaWallet._atRestKey));
}

/** Reads the locally stored passkey record without going through decryption. */
export function storedPasskey(page: Page): Promise<any> {
  return page.evaluate(() => (window as any).__lemmaWallet._get('passkey', 'primary'));
}

/**
 * Runs a wallet call and captures the failure instead of throwing, so negative
 * tests can assert on the exact error code the wallet or server produced.
 */
export async function attempt<T>(run: () => Promise<T>): Promise<Attempt<T>> {
  try {
    return { ok: true, value: await run() };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

// --- Raw enrollment ceremony -------------------------------------------------
// Negative tests need to send things the wallet would never send (a UV-clear
// credential, a replayed challenge), so they drive the two endpoints directly
// and reuse only the wallet's serialization.

export interface HttpResult {
  status: number;
  body: any;
}

export function beginRawEnroll(
  page: Page,
  walletId: string,
  deviceId: string,
): Promise<HttpResult> {
  return page.evaluate(async ([wallet_id, device_id]) => {
    const res = await fetch('/api/wallet/device-enroll/begin', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wallet_id, device_id, device_name: 'e2e' }),
    });
    return { status: res.status, body: await res.json().catch(() => ({})) };
  }, [walletId, deviceId]);
}

export function completeRawEnroll(page: Page, payload: Record<string, unknown>): Promise<HttpResult> {
  return page.evaluate(async (body) => {
    const res = await fetch('/api/wallet/device-enroll/complete', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return { status: res.status, body: await res.json().catch(() => ({})) };
  }, payload);
}

/** Runs navigator.credentials.create by hand and serializes it the way the wallet does. */
export function createRawCredential(
  page: Page,
  args: { challenge: string; rpId: string; walletId: string; userVerification?: string },
): Promise<any> {
  return page.evaluate(async ({ challenge, rpId, walletId, userVerification }) => {
    const w = window as any;
    const credential = await navigator.credentials.create({
      publicKey: {
        challenge: w.__lemmaWallet._base64urlToBuffer(challenge),
        rp: { name: 'lemma.id', id: rpId },
        user: {
          id: new TextEncoder().encode(walletId),
          name: 'lemma.id user',
          displayName: 'lemma.id',
        },
        pubKeyCredParams: [
          { alg: -7, type: 'public-key' },
          { alg: -257, type: 'public-key' },
        ],
        authenticatorSelection: {
          userVerification: userVerification || 'required',
          residentKey: 'preferred',
        },
        timeout: 60_000,
      },
    } as any);
    return w.__lemmaWallet._serializeCredential(credential);
  }, args);
}
