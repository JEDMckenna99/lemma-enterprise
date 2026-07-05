(function () {
  'use strict';

  function formatSiteLabel(site) {
    const raw = String(site || '').trim();
    if (!raw || raw === 'customer site') return 'this site';
    return raw.replace(/^www\./i, '');
  }

  const CONSUMER = {
    documentTitle: "Confirm you're human — Lemma.id",
    eyebrow: 'Lemma.id',
    headline: "Prove you're human once",
    headlinePasskeySetup: 'Create your lemma.id',
    headlineUnlock: 'Unlock your lemma.id',
    headlineSiteContinuity: 'Unlock to continue',
    documentTitlePasskeySetup: 'Create your lemma.id \u2014 Lemma.id',
    documentTitleUnlock: 'Unlock \u2014 Lemma.id',
    documentTitleSiteContinuity: 'Unlock to continue \u2014 Lemma.id',
    privacy:
      'Your ID documents are used only to create your human proof. After your proof is created, your documents and photos are removed from the verification provider. Lemma.id only stores your human proof, not your ID. Lemma does not use your verification data for advertising.',
    cancel: 'Not now',
    steps: [
      'Secure this device with Face ID, Touch ID, or your passkey',
      'Complete a one-time identity check, usually under a minute',
      'Return to the site. They see a private proof, not your documents',
    ],
    stepsContinuity: [
      'Unlock this device with Face ID, Touch ID, or your passkey',
      'Lemma issues a private site proof from your wallet \u2014 no ID check',
      'Return to the site. They see a continuity proof, not your documents',
    ],
    primary: {
      create: 'Create my lemma.id',
      unlock: 'Unlock my lemma.id',
      claim: 'Claim my lemma.id',
      verifyIdentity: 'Verify identity',
      tryAgain: 'Try again',
      unlockFinish: 'Unlock & finish',
      closeTab: 'Close',
    },
    intro: {
      passkeySetup:
        'Create a passkey wallet on this device. No identity check at this step \u2014 just a continuity proof you can use on demo sites.',
      unlockOnly:
        'Unlock your existing lemma.id wallet with your passkey to continue.',
      verifyOnce(site) {
        const s = formatSiteLabel(site);
        return `Create your lemma.id to prove you\u2019re a real person without sharing your ID with ${s}. Your lemma.id is stored privately in your browser, so you can skip repeat checks on other sites that use Lemma.id.`;
      },
      unlockReturning(site) {
        const s = formatSiteLabel(site);
        return `Welcome back. Unlock your lemma.id with your passkey to continue on ${s}.`;
      },
      siteProof(site) {
        const s = formatSiteLabel(site);
        return `${s} needs to know you\u2019re a real person. Unlock your lemma.id and we\u2019ll share a private proof \u2014 not your documents.`;
      },
      siteProofPasskey(site) {
        const s = formatSiteLabel(site);
        return `${s} only needs a continuity proof from your lemma.id wallet \u2014 unlock with your passkey. No identity check unless this site later requires human proof assurance.`;
      },
      claim:
        'You\u2019re verified. Save your lemma.id on this device with a passkey so you can use it again.',
      freshDoubt(site) {
        const s = formatSiteLabel(site);
        return `${s} asked for a fresh check before you continue. Verify once more \u2014 your ID still stays out of their hands.`;
      },
      mobileHandoff:
        'You\u2019re verified. Save your lemma.id on this phone \u2014 a passkey keeps it secure on this device only.',
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
      freshStarting: 'Starting a fresh verification\u2026',
      freshRetry: 'That didn\u2019t finish \u2014 let\u2019s try again.',
      freshSuccess: 'You\u2019re verified again.',
      stored: 'You\u2019re all set.',
      alreadyVerified: 'You\u2019re already verified.',
      claimReady: 'Almost done \u2014 secure your lemma.id on this device.',
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
