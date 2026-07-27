(function () {
  'use strict';

  function formatSiteLabel(site) {
    const raw = String(site || '').trim();
    if (!raw || raw === 'customer site') return 'this site';
    return raw.replace(/^www\./i, '');
  }

  const CONSUMER = {
    documentTitle: "Confirm you're human | Lemma.id",
    eyebrow: 'lemma.id',
    headline: "Prove you're human once",
    headlinePasskeySetup: 'Create your lemma.id',
    headlineUnlock: 'Unlock your lemma.id',
    headlineSiteContinuity: 'Unlock to continue',
    headlineFreshPasskey: 'Confirm presence',
    headlineBlocked: 'Access banned',
    documentTitlePasskeySetup: 'Create your lemma.id | Lemma.id',
    documentTitleUnlock: 'Unlock | Lemma.id',
    documentTitleSiteContinuity: 'Unlock to continue | Lemma.id',
    documentTitleFreshPasskey: 'Confirm presence | Lemma.id',
    documentTitleBlocked: 'Access banned | Lemma.id',
    privacy:
      'Your documents stay private and are deleted after verification. This site receives only your human proof.',
    privacyFreshDoubt:
      'Your humanity has been doubted. Please prove you\u2019re human to continue.',
    cancel: 'Not now',
    primary: {
      create: 'Create my lemma.id',
      unlock: 'Unlock my lemma.id',
      claim: 'Claim my lemma.id',
      verifyIdentity: 'Verify identity',
      confirmPresence: 'Confirm presence',
      tryAgain: 'Try again',
      unlockFinish: 'Unlock & finish',
      closeTab: 'Close',
    },
    intro: {
      passkeySetup:
        'Create a passkey wallet on this device. No identity check is needed at this step.',
      unlockOnly:
        'Unlock your existing lemma.id wallet with your passkey to continue.',
      verifyOnce(site) {
        const s = formatSiteLabel(site);
        return `Prove you\u2019re a real person to ${s} without sharing your ID.`;
      },
      unlockReturning(site) {
        const s = formatSiteLabel(site);
        return `Welcome back. Unlock your lemma.id with your passkey to continue on ${s}.`;
      },
      siteProof(site) {
        const s = formatSiteLabel(site);
        return `${s} needs a human proof. Complete a one-time identity check without sharing your ID with the site.`;
      },
      siteProofPasskey(site) {
        const s = formatSiteLabel(site);
        return `${s} needs a continuity proof from your lemma.id wallet. Unlock with your passkey.`;
      },
      claim:
        'You\u2019re verified. Save your lemma.id on this device with a passkey so you can use it again.',
      freshDoubt(site) {
        const s = formatSiteLabel(site);
        return `${s} asked for a fresh check. Verify again without sharing your ID with the site.`;
      },
      freshPasskey(site, action) {
        const s = formatSiteLabel(site);
        const requestedAction = String(action || 'continue').trim();
        return `${s} requires fresh holder presence before you ${requestedAction}. Confirm with your passkey.`;
      },
      blocked(site) {
        const s = formatSiteLabel(site);
        return `${s} has banned this lemma.id. No human proof will be issued for this site.`;
      },
      mobileHandoff:
        'You\u2019re verified. Save your lemma.id on this phone with a passkey.',
    },
    status: {
      ready: 'Takes about a minute. You can stop anytime.',
      checking: 'One moment\u2026',
      unlocking: 'Unlocking with your passkey\u2026',
      openingIdv: 'Opening secure identity check\u2026',
      finalizing: 'Almost done\u2026',
      waitingVerification: 'Finishing your verification\u2026',
      siteProofPending: 'One quick identity check, then we\u2019ll confirm you\u2019re human here.',
      siteProofIssuing: 'Confirming you\u2019re human\u2026',
      siteProofSuccess: 'You\u2019re verified for this site.',
      firstHumanSuccess: 'You\u2019re a human',
      freshStarting: 'Starting a fresh verification\u2026',
      freshRetry: 'That didn\u2019t finish. Let\u2019s try again.',
      freshSuccess: 'You\u2019re a human',
      freshPasskeyReady: 'Use Face ID, Touch ID, Windows Hello, or your passkey to confirm your presence.',
      freshPasskeyWorking: 'Confirming your presence\u2026',
      freshPasskeySuccess: 'Presence confirmed.',
      blocked: 'This PPID is banned on this site.',
      stored: 'You\u2019re all set.',
      alreadyVerified: 'You\u2019re already verified.',
      claimReady: 'Almost done. Secure your lemma.id on this device.',
      mobileReady: 'Your lemma.id is ready on this device.',
      returnUnlock: 'Unlock to finish where you left off.',
      passkeySetupReady: 'Tap below. Windows Hello, Touch ID, or your passkey will ask once.',
      unlockReady: 'Enter your passkey to unlock.',
      error: 'Something went wrong. Please try again.',
      returnFailed: 'Couldn\u2019t return to the site. Try again.',
      directOpen: 'Open this from the site you\u2019re signing in to.',
    },
  };

  window.LemmaIdvConsumerCopy = CONSUMER;
  window.LemmaIdvFormatSiteLabel = formatSiteLabel;
})();
