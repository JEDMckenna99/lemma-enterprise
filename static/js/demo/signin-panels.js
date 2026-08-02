/**
 * Manager narration panels ( /app ).
 *
 * Fills the "What lemma.id learned about you" and "What other sites would see"
 * panels with the user's real data: the session PPID from the verified
 * sign-in, and locally derived per-site PPIDs (HMAC on-device, nothing sent
 * anywhere) once the lemma.id is unlocked.
 */
(function () {
  'use strict';

  var panels = document.getElementById('sf-manager-panels');
  if (!panels) return;

  var ASSURANCE_LABELS = {
    passkey: 'Signed in with a passkey.',
    ishuman: 'Verified human \u2014 one account per person.',
  };

  // Neutral example hostnames: pure per-site HMAC derivation (a *.lemma.id
  // subdomain would short-circuit to the platform credential's PPID).
  var COMPARE_SITES = {
    'sf-ppid-shop': 'a-ticket-shop.example',
    'sf-ppid-news': 'a-news-site.example',
  };

  function setText(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function truncatePpid(ppid) {
    if (!ppid) return '\u2026';
    var display = String(ppid).replace(/^did:lemma:/, '');
    if (display.length <= 16) return display;
    return display.slice(0, 9) + '\u2026' + display.slice(-4);
  }

  function relativeTime(epochSeconds) {
    if (!epochSeconds) return 'Just now';
    var deltaMin = Math.round((Date.now() / 1000 - epochSeconds) / 60);
    if (deltaMin < 1) return 'Just now';
    if (deltaMin === 1) return '1 minute ago';
    if (deltaMin < 60) return deltaMin + ' minutes ago';
    var hours = Math.round(deltaMin / 60);
    return hours === 1 ? '1 hour ago' : hours + ' hours ago';
  }

  function getCookie(name) {
    var match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : '';
  }

  /* ------------------------------------------------------------------ */
  /* Panel 1: session facts                                              */
  /* ------------------------------------------------------------------ */

  fetch('/api/auth/session', { credentials: 'same-origin' })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      if (!data.signed_in) return;
      setText('sf-ppid-self', truncatePpid(data.ppid));
      setText('sf-ppid-lemma', truncatePpid(data.ppid));
      setText('sf-assurance-label', ASSURANCE_LABELS[data.assurance] || ASSURANCE_LABELS.passkey);
      setText('sf-signin-time', relativeTime(data.signed_in_at));
      var copyBtn = document.getElementById('sf-copy-ppid');
      if (copyBtn) {
        copyBtn.setAttribute('data-full-ppid', data.ppid || '');
        copyBtn.addEventListener('click', function () {
          if (!navigator.clipboard) return;
          navigator.clipboard.writeText(data.ppid || '').then(function () {
            copyBtn.textContent = 'Copied';
            setTimeout(function () { copyBtn.textContent = 'Copy'; }, 1400);
          });
        });
      }
    })
    .catch(function () { /* panel stays in placeholder state */ });

  /* ------------------------------------------------------------------ */
  /* Panel 2: locally derived per-site PPIDs (after unlock)              */
  /* ------------------------------------------------------------------ */

  var derived = false;

  function tryDeriveSitePpids() {
    if (derived || !window.LemmaWallet) return Promise.resolve(false);
    var wallet = window.globalLemmaWallet;
    if (!wallet) {
      wallet = new window.LemmaWallet();
      window.globalLemmaWallet = wallet;
    }
    var ready = wallet._initialized ? Promise.resolve() : wallet.init();
    return ready
      .then(function () { return wallet.getWalletInfo({ lite: true }); })
      .then(function (info) {
        if (!info || !info.isUnlocked) return false;
        var ids = Object.keys(COMPARE_SITES);
        return Promise.all(ids.map(function (elId) {
          return wallet.derivePPID(COMPARE_SITES[elId]).then(function (ppid) {
            setText(elId, truncatePpid(ppid));
          });
        })).then(function () {
          derived = true;
          return true;
        });
      })
      .catch(function () { return false; });
  }

  function pollDerive() {
    tryDeriveSitePpids().then(function (done) {
      if (!done) {
        Object.keys(COMPARE_SITES).forEach(function (elId) {
          var el = document.getElementById(elId);
          if (el && (el.textContent === '\u2026' || !el.textContent)) {
            el.textContent = 'Unlock to reveal';
          }
        });
        setTimeout(pollDerive, 2500);
      }
    });
  }

  pollDerive();

  /* ------------------------------------------------------------------ */
  /* Sign out                                                            */
  /* ------------------------------------------------------------------ */

  var signoutBtn = document.getElementById('sf-signout-btn');
  if (signoutBtn) {
    signoutBtn.addEventListener('click', function () {
      var headers = { 'Content-Type': 'application/json' };
      var csrf = getCookie('lemma_csrf_token');
      if (csrf) headers['X-Lemma-CSRF'] = csrf;
      fetch('/api/auth/session/logout', {
        method: 'POST',
        credentials: 'same-origin',
        headers: headers,
      }).then(function () {
        window.location.href = '/demo';
      });
    });
  }
})();
