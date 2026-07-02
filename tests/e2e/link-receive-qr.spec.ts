import { test, expect } from '@playwright/test';

const CRYPTO_FAILURE = /@noble|noble\/hashes|Failed to resolve module|404.*npm|X25519 load failed/i;

test.describe('Transfer QR generator (/link)', () => {
  test('vendor bundles use local relative imports only', async ({ request }) => {
    const vendorFiles = [
      '/static/js/vendor/noble-curves-ed25519.mjs',
      '/static/js/vendor/noble-hashes-sha512.mjs',
      '/static/js/vendor/noble-hashes-utils.mjs',
    ];

    for (const path of vendorFiles) {
      const res = await request.get(path);
      expect(res.ok(), `${path} should be served`).toBeTruthy();
      const body = await res.text();
      expect(body, `${path} must not import from /npm/`).not.toMatch(/from"\/npm\//);
      expect(body, `${path} must not import from /npm/`).not.toMatch(/import"\/npm\//);
    }

    const curves = await (await request.get('/static/js/vendor/noble-curves-ed25519.mjs')).text();
    expect(curves).toContain('./noble-hashes-sha512.mjs');
    expect(curves).toContain('./noble-hashes-utils.mjs');
  });

  test('LemmaKeys X25519 loads and generateEncryptionKeypair works', async ({ page }) => {
    const issues: string[] = [];
    page.on('console', (msg) => {
      const text = msg.text();
      if ((msg.type() === 'error' || msg.type() === 'warning') && CRYPTO_FAILURE.test(text)) {
        issues.push(text);
      }
    });
    page.on('pageerror', (err) => {
      if (CRYPTO_FAILURE.test(err.message)) issues.push(err.message);
    });

    await page.goto('/link');
    await page.waitForFunction(() => typeof (window as any).LemmaKeys !== 'undefined');

    const keypair = await page.evaluate(async () => {
      const keys = (window as any).LemmaKeys;
      const { privateKey, publicKey } = await keys.generateEncryptionKeypair();
      const shared = keys.base64urlEncode(publicKey);
      return {
        privateLen: privateKey?.length ?? 0,
        publicLen: publicKey?.length ?? 0,
        publicB64Len: shared.length,
      };
    });

    expect(keypair.privateLen).toBe(32);
    expect(keypair.publicLen).toBe(32);
    expect(keypair.publicB64Len).toBeGreaterThan(20);
    expect(issues, `crypto console errors: ${issues.join('; ')}`).toEqual([]);
  });

  test('Show QR Code renders receive QR with /link/send URL', async ({ page }) => {
    const issues: string[] = [];
    page.on('console', (msg) => {
      const text = msg.text();
      if ((msg.type() === 'error' || msg.type() === 'warning') && CRYPTO_FAILURE.test(text)) {
        issues.push(text);
      }
    });
    page.on('pageerror', (err) => {
      if (CRYPTO_FAILURE.test(err.message)) issues.push(err.message);
    });
    page.on('dialog', (dialog) => {
      issues.push(`alert: ${dialog.message()}`);
      void dialog.dismiss();
    });

    await page.goto('/link');
    await page.waitForFunction(() => typeof (window as any).LemmaWallet !== 'undefined');

    await page.getByRole('button', { name: 'Show QR Code' }).click();

    await expect(page.locator('#receive-qr-display')).toBeVisible();
    await expect(page.locator('#receive-qr-container img')).toBeVisible();

    const qrMeta = await page.evaluate(() => {
      const img = document.querySelector('#receive-qr-container img');
      return {
        hasImg: Boolean(img),
        srcLen: img?.getAttribute('src')?.length ?? 0,
      };
    });

    expect(qrMeta.hasImg).toBe(true);
    expect(qrMeta.srcLen).toBeGreaterThan(100);

    const beginResult = await page.evaluate(async () => {
      const wallet = new (window as any).LemmaWallet();
      await wallet.init();
      const result = await wallet.beginLinkReceive();
      return {
        transferId: result.transferId,
        qrUrl: result.qrUrl,
        expiresIn: result.expiresIn,
      };
    });

    expect(beginResult.transferId).toMatch(/^linkrecv_/);
    expect(beginResult.qrUrl).toMatch(/\/link\/send#/);
    expect(beginResult.expiresIn).toBe(300);
    expect(issues, `UI/crypto errors: ${issues.join('; ')}`).toEqual([]);
  });
});
