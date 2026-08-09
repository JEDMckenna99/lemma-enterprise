/**
 * The relying-site path: a site drops in ProofVerifier, the ceremony happens in
 * the lemma.id-hosted /verify popup, and the site gets a presentation back.
 *
 * Chrome gives each popup its own authenticator, so this is also what proves the
 * helper's credential vault works: signing in a second time reuses the passkey
 * created in the first popup.
 */
import { test, expect, type Page } from '@playwright/test';
import { installVirtualAuthenticator, type VirtualAuthenticator } from './helpers/virtual-authenticator';

async function openDemo(page: Page): Promise<string[]> {
  const problems: string[] = [];
  page.on('pageerror', (err) => problems.push(`pageerror: ${err.message}`));
  await page.goto('/demo');
  await page.waitForFunction(() => typeof (window as any).ProofVerifier === 'function');
  // Real SDK, not the /demo/mock design-review driver.
  await expect(page.locator('#sf-root')).toHaveAttribute('data-mock', '0');
  return problems;
}

test.describe('Sign in with lemma.id (demo relying site)', () => {
  let authenticator: VirtualAuthenticator;

  test.beforeEach(async ({ context, page }) => {
    void page;
    authenticator = await installVirtualAuthenticator(context);
  });

  test.afterEach(async () => {
    await authenticator?.dispose();
  });

  test('creating a lemma.id in the popup signs the user in to the site', async ({ page, context }) => {
    const problems = await openDemo(page);

    const popupPromise = context.waitForEvent('page');
    await page.locator('#sf-create-btn').click();

    const popup = await popupPromise;
    await authenticator.waitForAttachment(popup);
    expect(new URL(popup.url()).pathname).toBe('/verify');

    await expect(page.locator('#sf-state-manager')).toBeVisible({ timeout: 45_000 });

    // One passkey was created, and it lives in the popup's authenticator.
    expect(authenticator.credentials()).toHaveLength(1);
    expect(authenticator.credentials()[0].rpId).toBe('localhost');
    expect(problems).toEqual([]);
  });

  test('signing in again reuses the existing passkey in a fresh popup', async ({ page, context }) => {
    await openDemo(page);

    const firstPopup = context.waitForEvent('page');
    await page.locator('#sf-create-btn').click();
    await authenticator.waitForAttachment(await firstPopup);
    await expect(page.locator('#sf-state-manager')).toBeVisible({ timeout: 45_000 });

    const created = authenticator.credentials();
    expect(created).toHaveLength(1);

    await page.locator('#sf-signout-btn').click();
    await expect(page.locator('#sf-signin-btn')).toBeVisible({ timeout: 20_000 });

    const secondPopup = context.waitForEvent('page');
    await page.locator('#sf-signin-btn').click();
    await authenticator.waitForAttachment(await secondPopup);
    await expect(page.locator('#sf-state-manager')).toBeVisible({ timeout: 45_000 });

    // Same credential, asserted again rather than replaced.
    const after = authenticator.credentials();
    expect(after).toHaveLength(1);
    expect(after[0].credentialId).toBe(created[0].credentialId);
    expect(after[0].signCount).toBeGreaterThan(created[0].signCount);
  });
});
