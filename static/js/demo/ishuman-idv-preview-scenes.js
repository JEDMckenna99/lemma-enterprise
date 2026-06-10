(function () {
  'use strict';

  function formatSiteLabel(site) {
    const raw = String(site || '').trim();
    if (!raw || raw === 'customer site') return 'this site';
    return raw.replace(/^www\./i, '');
  }

  const CONSUMER = {
    documentTitle: "Confirm you're human — Lemma.id",
    eyebrow: 'Secured by Lemma.id',
    headline: "Prove you're human once",
    privacy:
      'Your ID documents are used only to create your human proof. After your proof is created, your documents and photos are removed from the verification provider. Lemma.id only stores your human proof, not your ID.',
    cancel: 'Not now',
    steps: [
      'Secure this device with Face ID, Touch ID, or your passkey',
      'Complete a one-time identity check, usually under a minute',
      'Return to the site. They see a private proof, not your documents',
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
      verifyOnce(site) {
        const s = formatSiteLabel(site);
        return `Create your lemma.id to prove you\u2019re a real person without sharing your ID with ${s}. Your lemma.id is stored in your browser, so you can skip repeat checks on other sites that use Lemma.id.`;
      },
      unlockReturning(site) {
        const s = formatSiteLabel(site);
        return `Welcome back. Unlock your lemma.id with your passkey to continue on ${s}.`;
      },
      siteProof(site) {
        const s = formatSiteLabel(site);
        return `${s} needs to know you\u2019re a real person. Unlock your lemma.id and we\u2019ll share a private proof \u2014 not your documents.`;
      },
      claim:
        'You\u2019re verified. Save your lemma.id on this device with a passkey so you can use it again.',
      freshBlocked(site) {
        const s = formatSiteLabel(site);
        return `${s} asked for a fresh check before you continue. Verify once more \u2014 your ID still stays out of their hands.`;
      },
      freshRevoked:
        'Your previous verification was reset. Verify once more to continue. Sites still never see your ID documents.',
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
      error: 'Something went wrong. Please try again.',
      returnFailed: 'Couldn\u2019t return to the site. Try again.',
      directOpen: 'Open this from the site you\u2019re signing in to.',
    },
  };

  const INTRO_VERIFY_ONCE = CONSUMER.intro.verifyOnce('this site');
  const INTRO_SITE_PROOF = CONSUMER.intro.siteProof('this site');
  const INTRO_CLAIM = CONSUMER.intro.claim;
  const INTRO_FRESH_REVOKED = CONSUMER.intro.freshRevoked;
  const INTRO_FRESH_BLOCKED = CONSUMER.intro.freshBlocked('this site');
  const INTRO_MOBILE = CONSUMER.intro.mobileHandoff;

  /** @type {Record<string, object>} */
  const SCENES = {
    verify_once: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: CONSUMER.status.ready, tone: 'info' },
      primary: { text: CONSUMER.primary.create, visible: true },
      cancel: CONSUMER.cancel,
    },
    unlock_lemma: {
      intro: CONSUMER.intro.unlockReturning('this site'),
      status: { message: CONSUMER.status.ready, tone: 'info' },
      primary: { text: CONSUMER.primary.unlock, visible: true },
      cancel: CONSUMER.cancel,
    },
    claim_lemma: {
      intro: INTRO_CLAIM,
      status: { message: CONSUMER.status.claimReady, tone: 'info' },
      primary: { text: CONSUMER.primary.claim, visible: true },
      cancel: CONSUMER.cancel,
    },
    verify_ready: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: CONSUMER.status.ready, tone: 'info' },
      primary: { text: CONSUMER.primary.verifyIdentity, visible: true },
      cancel: CONSUMER.cancel,
    },
    loading_check_wallet: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: CONSUMER.status.checking, tone: 'loading' },
      primary: { visible: false },
      cancel: CONSUMER.cancel,
    },
    loading_unlock: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: CONSUMER.status.unlocking, tone: 'loading' },
      primary: { visible: false },
      cancel: CONSUMER.cancel,
    },
    loading_idv: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: CONSUMER.status.openingIdv, tone: 'loading' },
      primary: { visible: false },
      cancel: CONSUMER.cancel,
    },
    loading_finalize: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: CONSUMER.status.finalizing, tone: 'loading' },
      primary: { visible: false },
      cancel: CONSUMER.cancel,
    },
    site_proof: {
      intro: INTRO_SITE_PROOF,
      status: { message: CONSUMER.status.ready, tone: 'info' },
      primary: { visible: false },
      cancel: CONSUMER.cancel,
    },
    site_proof_needs_idv: {
      intro: INTRO_SITE_PROOF,
      status: { message: CONSUMER.status.siteProofPending, tone: 'info' },
      primary: { text: CONSUMER.primary.create, visible: true },
      cancel: CONSUMER.cancel,
    },
    site_proof_unlock: {
      intro: INTRO_SITE_PROOF,
      status: { message: CONSUMER.status.siteProofPending, tone: 'info' },
      primary: { text: CONSUMER.primary.unlock, visible: true },
      cancel: CONSUMER.cancel,
    },
    site_proof_claim: {
      intro: INTRO_SITE_PROOF,
      status: { message: CONSUMER.status.siteProofPending, tone: 'info' },
      primary: { text: CONSUMER.primary.claim, visible: true },
      cancel: CONSUMER.cancel,
    },
    site_proof_verify: {
      intro: INTRO_SITE_PROOF,
      status: { message: CONSUMER.status.siteProofPending, tone: 'info' },
      primary: { text: CONSUMER.primary.verifyIdentity, visible: true },
      cancel: CONSUMER.cancel,
    },
    site_proof_issuing: {
      intro: INTRO_SITE_PROOF,
      status: { message: CONSUMER.status.siteProofIssuing, tone: 'loading' },
      primary: { visible: false },
      cancel: CONSUMER.cancel,
    },
    site_proof_success: {
      intro: INTRO_SITE_PROOF,
      status: { message: CONSUMER.status.siteProofSuccess, tone: 'success' },
      primary: { visible: false },
      cancel: CONSUMER.cancel,
    },
    fresh_idv_blocked: {
      intro: INTRO_FRESH_BLOCKED,
      status: { message: CONSUMER.status.ready, tone: 'info' },
      primary: { visible: false },
      cancel: CONSUMER.cancel,
    },
    fresh_idv_revoked: {
      intro: INTRO_FRESH_REVOKED,
      status: { message: CONSUMER.status.ready, tone: 'info' },
      primary: { visible: false },
      cancel: CONSUMER.cancel,
    },
    fresh_idv_success: {
      intro: INTRO_FRESH_REVOKED,
      status: { message: CONSUMER.status.freshSuccess, tone: 'success' },
      primary: { visible: false },
      cancel: CONSUMER.cancel,
    },
    mobile_handoff: {
      intro: INTRO_MOBILE,
      status: { message: CONSUMER.status.mobileReady, tone: 'success' },
      primary: { visible: false },
      cancel: CONSUMER.primary.closeTab,
    },
    return_unlock: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: CONSUMER.status.returnUnlock, tone: 'info' },
      primary: { text: CONSUMER.primary.unlockFinish, visible: true },
      cancel: CONSUMER.cancel,
    },
    already_provisioned: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: CONSUMER.status.alreadyVerified, tone: 'success' },
      primary: { visible: false },
      cancel: CONSUMER.cancel,
    },
    master_stored: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: CONSUMER.status.stored, tone: 'success' },
      primary: { visible: false },
      cancel: CONSUMER.cancel,
    },
    error: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: CONSUMER.status.error, tone: 'error' },
      primary: { text: CONSUMER.primary.tryAgain, visible: true },
      cancel: CONSUMER.cancel,
    },
  };

  const SECTIONS = [
    {
      title: 'Getting started',
      description: 'First screen most people see.',
      scenes: [
        { id: 'verify_once', label: 'New — Create my lemma.id' },
        { id: 'unlock_lemma', label: 'Returning — Unlock my lemma.id' },
        { id: 'claim_lemma', label: 'Verified elsewhere — Claim my lemma.id' },
        { id: 'verify_ready', label: 'Continue — Verify identity' },
      ],
    },
    {
      title: 'In progress',
      scenes: [
        { id: 'loading_check_wallet', label: 'One moment…' },
        { id: 'loading_unlock', label: 'Unlocking with passkey…' },
        { id: 'loading_idv', label: 'Opening identity check…' },
        { id: 'loading_finalize', label: 'Almost done…' },
      ],
    },
    {
      title: 'Confirming on a site',
      scenes: [
        { id: 'site_proof', label: 'Ready — auto confirm' },
        { id: 'site_proof_needs_idv', label: 'Needs check — Create my lemma.id' },
        { id: 'site_proof_unlock', label: 'Needs check — Unlock my lemma.id' },
        { id: 'site_proof_claim', label: 'Needs check — Claim my lemma.id' },
        { id: 'site_proof_verify', label: 'Needs check — Verify identity' },
        { id: 'site_proof_issuing', label: 'Confirming…' },
        { id: 'site_proof_success', label: 'Verified for this site' },
      ],
    },
    {
      title: 'Verify again',
      scenes: [
        { id: 'fresh_idv_blocked', label: 'Site requested re-check' },
        { id: 'fresh_idv_revoked', label: 'Previous verification reset' },
        { id: 'fresh_idv_success', label: 'Verified again' },
      ],
    },
    {
      title: 'Phone & finish',
      scenes: [
        { id: 'mobile_handoff', label: 'Saved on this phone' },
        { id: 'return_unlock', label: 'Return — Unlock & finish' },
        { id: 'already_provisioned', label: 'Already verified' },
        { id: 'master_stored', label: 'All set' },
        { id: 'error', label: 'Something went wrong' },
      ],
    },
  ];

  window.LemmaIdvConsumerCopy = CONSUMER;
  window.LemmaIdvFormatSiteLabel = formatSiteLabel;
  window.LemmaIdvPreviewScenes = SCENES;
  window.LemmaIdvPreviewSections = SECTIONS;
})();
