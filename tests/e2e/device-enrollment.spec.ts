import { test, expect } from '@playwright/test';

const CRYPTO_FAILURE = /@noble|noble\/hashes|Failed to resolve module|404.*npm|X25519 load failed/i;

test.describe('Device enrollment (/link seed transfer)', () => {
  test('Seed transfer tab renders transfer QR payload', async ({ page }) => {
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

    await page.getByRole('button', { name: 'Seed transfer' }).click();
    await expect(page.getByRole('heading', { name: 'Person-root seed transfer' })).toBeVisible();

    await page.getByRole('button', { name: 'Show transfer QR' }).click();
    await expect(page.locator('#sync-qr-display')).toBeVisible();
    await expect(page.locator('#sync-qr-container img')).toBeVisible();

    const transferMeta = await page.evaluate(async () => {
      const wallet = new (window as any).LemmaWallet();
      await wallet.init();
      const result = await wallet.beginDeviceTransfer();
      let parsed: Record<string, unknown> = {};
      try {
        parsed = JSON.parse(result.qrPayload);
      } catch {
        parsed = {};
      }
      return {
        transferId: result.transferId,
        qrPayloadKeys: Object.keys(parsed).sort(),
        hasEncPubkey: Boolean(result.newDeviceEncPubkeyB64),
        parsedV: parsed.v,
        parsedTransferId: parsed.transfer_id,
      };
    });

    expect(transferMeta.transferId).toMatch(/^transfer_/);
    expect(transferMeta.qrPayloadKeys).toEqual(['new_device_enc_pubkey', 'transfer_id', 'v']);
    expect(transferMeta.parsedV).toBe(1);
    expect(transferMeta.parsedTransferId).toBe(transferMeta.transferId);
    expect(transferMeta.hasEncPubkey).toBe(true);
    expect(issues, `UI/crypto errors: ${issues.join('; ')}`).toEqual([]);
  });
});
