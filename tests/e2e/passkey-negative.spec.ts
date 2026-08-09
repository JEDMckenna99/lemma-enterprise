/**
 * The guarantees that matter are the refusals, and a virtual authenticator can
 * produce the malformed ceremonies a real one never would: user verification
 * skipped, no PRF support, a replayed challenge, a second device with no grant.
 */
import { test, expect } from '@playwright/test';
import { installVirtualAuthenticator, type VirtualAuthenticator } from './helpers/virtual-authenticator';
import * as wallet from './helpers/wallet';

const RP_ID = 'localhost';

test.describe('lemma.id passkey refusals', () => {
  let authenticator: VirtualAuthenticator;

  test.afterEach(async () => {
    await authenticator?.dispose();
  });

  test('the wallet refuses to enroll when the authenticator has no PRF support', async ({ context, page }) => {
    authenticator = await installVirtualAuthenticator(context, { hasPrf: false });
    await wallet.openWalletPage(page);

    const result = await wallet.attempt(() => wallet.enroll(page));

    // Without PRF there is no at-rest key, and storing the identity unencrypted
    // is not an acceptable fallback.
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain('prf_required_for_encrypted_storage');
    expect(await wallet.atRestKeyBound(page)).toBe(false);
  });

  test('the wallet refuses to enroll when user verification cannot succeed', async ({ context, page }) => {
    authenticator = await installVirtualAuthenticator(context, { isUserVerified: false });
    await wallet.openWalletPage(page);

    const result = await wallet.attempt(() => wallet.enroll(page));

    expect(result.ok).toBe(false);
    expect(await wallet.atRestKeyBound(page)).toBe(false);
    expect(await wallet.storedPasskey(page)).toBeFalsy();
  });

  test('the server rejects a registration whose user-verification flag is clear', async ({ context, page }) => {
    // An authenticator that cannot verify the user at all, asked for an
    // assertion that does not require it: a valid ceremony with UV clear.
    authenticator = await installVirtualAuthenticator(context, {
      hasUserVerification: false,
      isUserVerified: false,
    });
    await wallet.openWalletPage(page);

    const walletId = `wallet_uv_${Date.now()}`;
    const begun = await wallet.beginRawEnroll(page, walletId, 'device_uv');
    expect(begun.status).toBe(200);

    const credential = await wallet.createRawCredential(page, {
      challenge: begun.body.challenge,
      rpId: begun.body.rp_id,
      walletId,
      userVerification: 'discouraged',
    });

    const completed = await wallet.completeRawEnroll(page, {
      challenge_key: begun.body.challenge_key,
      credential,
      wallet_id: walletId,
      device_id: 'device_uv',
      pubkey: 'placeholder-pubkey',
      signature: 'placeholder-signature',
    });

    expect(completed.status).toBe(403);
    expect(completed.body.error).toBe('webauthn_registration_invalid');
  });

  test('an enrollment challenge is single-use even when the first attempt fails', async ({ context, page }) => {
    authenticator = await installVirtualAuthenticator(context, {
      hasUserVerification: false,
      isUserVerified: false,
    });
    await wallet.openWalletPage(page);

    const walletId = `wallet_replay_${Date.now()}`;
    const begun = await wallet.beginRawEnroll(page, walletId, 'device_replay');
    const credential = await wallet.createRawCredential(page, {
      challenge: begun.body.challenge,
      rpId: begun.body.rp_id,
      walletId,
      userVerification: 'discouraged',
    });
    const payload = {
      challenge_key: begun.body.challenge_key,
      credential,
      wallet_id: walletId,
      device_id: 'device_replay',
      pubkey: 'placeholder-pubkey',
      signature: 'placeholder-signature',
    };

    const first = await wallet.completeRawEnroll(page, payload);
    const replay = await wallet.completeRawEnroll(page, payload);

    // The challenge is consumed before verification, so a rejected attempt
    // cannot be retried as a verification oracle.
    expect(first.body.error).not.toBe('device_enroll_challenge_expired');
    expect(replay.status).toBe(401);
    expect(replay.body.error).toBe('device_enroll_challenge_expired');
  });

  test('a second device cannot enroll into an existing wallet without a grant', async ({ context, page }) => {
    authenticator = await installVirtualAuthenticator(context);
    await wallet.openWalletPage(page);

    const enrolled = await wallet.enroll(page);
    expect(enrolled.success).toBe(true);

    const hijack = await wallet.beginRawEnroll(page, String(enrolled.walletId), 'device_attacker');

    expect(hijack.status).toBe(403);
    expect(hijack.body.error).toBe('device_enrollment_authorization_required');
  });

  test('the browser refuses a ceremony for an RP the page does not own', async ({ context, page }) => {
    authenticator = await installVirtualAuthenticator(context);
    await wallet.openWalletPage(page);

    const walletId = `wallet_rp_${Date.now()}`;
    const begun = await wallet.beginRawEnroll(page, walletId, 'device_rp');
    expect(begun.body.rp_id).toBe(RP_ID);

    const result = await wallet.attempt(() =>
      wallet.createRawCredential(page, {
        challenge: begun.body.challenge,
        rpId: 'lemma.id',
        walletId,
      }),
    );

    // Guards _getRpIdForWebAuthn: a mismatched RP ID must never produce a
    // credential, so a passkey minted elsewhere cannot be replayed here.
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain('SecurityError');
  });
});
