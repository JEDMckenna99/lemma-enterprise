import { test, expect } from '@playwright/test';
import { installVirtualAuthenticator, type VirtualAuthenticator } from './helpers/virtual-authenticator';
import * as wallet from './helpers/wallet';

test.describe('lemma.id passkey sign-in', () => {
  let authenticator: VirtualAuthenticator;

  test.beforeEach(async ({ context, page }) => {
    void page; // ensure the default page exists before the authenticator attaches
    authenticator = await installVirtualAuthenticator(context);
  });

  test.afterEach(async () => {
    await authenticator?.dispose();
  });

  test('first-device enrollment creates a passkey and binds the PRF at-rest key', async ({ page }) => {
    await wallet.openWalletPage(page);

    const result = await wallet.enroll(page);

    expect(result.success).toBe(true);
    expect(result.walletId).toBeTruthy();
    expect(result.credentialId).toBeTruthy();

    // Without the PRF key bound, every encrypted store read fails closed.
    expect(await wallet.atRestKeyBound(page)).toBe(true);
    const stored = await wallet.storedPasskey(page);
    expect(stored.prfEnabled).toBe(true);
    expect(stored.credentialId).toBe(result.credentialId);

    const credentials = await authenticator.credentialsOn(page);
    expect(credentials).toHaveLength(1);
    expect(credentials[0].rpId).toBe('localhost');
    expect(credentials[0].isResidentCredential).toBe(true);
  });

  test('a reload inside the session window costs no second passkey prompt', async ({ page }) => {
    await wallet.openWalletPage(page);
    const enrolled = await wallet.enroll(page);
    const signCountAfterEnroll = (await authenticator.credentialsOn(page))[0].signCount;

    // Reload drops the in-memory session and at-rest key; the daily-unlock
    // bundle is what makes one passkey cover the rest of the session window.
    await wallet.openWalletPage(page);
    const unlocked = await wallet.unlock(page);

    expect(unlocked.success).toBe(true);
    expect(unlocked.cached).toBe(true);
    expect(unlocked.walletId).toBe(enrolled.walletId);
    expect(await wallet.atRestKeyBound(page)).toBe(true);

    // No assertion means no ceremony: the counter is the proof.
    const [credential] = await authenticator.credentialsOn(page);
    expect(credential.signCount).toBe(signCountAfterEnroll);
  });

  test('a forced re-auth runs a real assertion the server verifies', async ({ page }) => {
    await wallet.openWalletPage(page);
    const enrolled = await wallet.enroll(page);
    const signCountAfterEnroll = (await authenticator.credentialsOn(page))[0].signCount;

    await wallet.openWalletPage(page);
    const unlocked = await wallet.unlock(page, { force: true });

    expect(unlocked.success).toBe(true);
    expect(unlocked.cached).toBeFalsy();
    expect(unlocked.walletId).toBe(enrolled.walletId);

    const [credential] = await authenticator.credentialsOn(page);
    expect(credential.signCount).toBeGreaterThan(signCountAfterEnroll);
  });

  test('PPIDs are stable per site and unlinkable across sites', async ({ page }) => {
    await wallet.openWalletPage(page);
    const { walletId } = await wallet.enroll(page);

    const first = await wallet.derivePPID(page, 'app.example.com');
    const again = await wallet.derivePPID(page, 'app.example.com');
    const otherSite = await wallet.derivePPID(page, 'other.example.org');

    expect(first).toMatch(/^did:lemma:ppid_[0-9a-f]{32,}$/);
    expect(again).toBe(first);
    expect(otherSite).not.toBe(first);
    // The site never sees anything the wallet id can be recovered from.
    expect(first).not.toContain(String(walletId));
  });

  test('site ids canonicalize by case, port and www, but not by subdomain', async ({ page }) => {
    await wallet.openWalletPage(page);
    await wallet.enroll(page);

    const canonical = await wallet.derivePPID(page, 'app.example.com');

    expect(await wallet.derivePPID(page, 'APP.EXAMPLE.COM')).toBe(canonical);
    expect(await wallet.derivePPID(page, 'app.example.com:8443')).toBe(canonical);
    expect(await wallet.derivePPID(page, 'www.app.example.com')).toBe(canonical);

    // No suffix matching: a neighbouring subdomain must not inherit the PPID.
    expect(await wallet.derivePPID(page, 'other.example.com')).not.toBe(canonical);
    expect(await wallet.derivePPID(page, 'app.example.com.evil.test')).not.toBe(canonical);
  });

  test('a wiped device loses the local identity even though the passkey survives', async ({ page }) => {
    await wallet.openWalletPage(page);
    const enrolled = await wallet.enroll(page);

    await wallet.purgeDevice(page);
    await wallet.openWalletPage(page);

    const info = await wallet.walletInfo(page);
    expect(info.hasWallet).toBeFalsy();

    // The authenticator still holds the credential; recovery is a server-side
    // concern, so an unlock attempt must not silently resurrect the wallet.
    expect(authenticator.credentials().length).toBeGreaterThan(0);
    const attempt = await wallet.attempt(() => wallet.unlock(page));
    if (attempt.ok) {
      expect(attempt.value.success).toBeFalsy();
    }
    expect(await wallet.walletInfo(page)).not.toMatchObject({ walletId: enrolled.walletId });
  });
});
