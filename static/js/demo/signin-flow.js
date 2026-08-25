/**
 * lemma.id proof continuity. Dogfooded demo flow state machine.
 *
 * States: create -> signin -> manager   plus a standalone `gate`
 * used when /app is opened without a session. After sign-in, open the manager
 * immediately (no interstitial success screen).
 *
 * The same markup runs in two modes:
 *   - mock mode (data-mock="1"): fake driver with realistic timing, no SDK,
 *     used for design review at /demo/mock.
 *   - real mode: ProofVerifier SDK (the same one relying sites integrate)
 *     plus POST /api/auth/session, which verifies the signed presentation
 *     server-side and mints the HttpOnly session that opens /app.
 */
(function () {
  'use strict';

  var root = document.getElementById('sf-root');
  if (!root) return;

  var MOCK = root.getAttribute('data-mock') === '1';
  var SITE_ID = root.getAttribute('data-site-id') || window.location.hostname;
  // Dev-only: local issuer's root pubkey so the SDK trusts the dev trust list.
  var DEV_ROOT_PUBKEY = root.getAttribute('data-dev-root-pubkey') || '';

  var SCREENS = {
    create: document.getElementById('sf-state-create'),
    signin: document.getElementById('sf-state-signin'),
    gate: document.getElementById('sf-state-gate'),
    manager: document.getElementById('sf-state-manager'),
  };

  function show(name) {
    Object.keys(SCREENS).forEach(function (key) {
      var el = SCREENS[key];
      if (!el) return;
      if (key === name) {
        el.hidden = false;
        el.classList.remove('sf-enter');
        // restart the enter animation
        void el.offsetWidth; // eslint-disable-line no-void
        el.classList.add('sf-enter');
      } else {
        el.hidden = true;
      }
    });
  }

  function setBusy(btn, busy) {
    if (!btn) return;
    btn.disabled = !!busy;
    btn.classList.toggle('sf-busy', !!busy);
    // Same working treatment as the popup: the brand mark's orbits pulse.
    var state = btn.closest ? btn.closest('.sf-state') : null;
    var mark = state ? state.querySelector('.sf-mark') : null;
    if (mark) mark.classList.toggle('is-working', !!busy);
  }

  function setStatus(id, message, isError) {
    var el = document.getElementById(id);
    if (!el) return;
    el.textContent = message || '';
    el.classList.toggle('sf-status-error', !!isError);
  }

  var PLAIN_OVERRIDES = {
    popup_blocked: 'Your browser blocked the lemma.id window. Allow popups for this site and try again.',
    popup_closed: 'The window was closed. Try again whenever you\u2019re ready.',
    passkey_unsupported: 'This browser doesn\u2019t support passkeys. Try Chrome, Edge, or Safari.',
    presentation_required: 'Something went wrong preparing your proof. Try again.',
  };

  function plain(reason) {
    if (reason && PLAIN_OVERRIDES[reason]) return PLAIN_OVERRIDES[reason];
    var p = window.LemmaDemoPlain;
    if (p && typeof p.reason === 'function' && reason) return p.reason(reason);
    return 'Something went wrong. Try again.';
  }

  function getCookie(name) {
    var match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : '';
  }

  function jsonHeaders() {
    var headers = { 'Content-Type': 'application/json' };
    var csrf = getCookie('lemma_csrf_token');
    if (csrf) headers['X-Lemma-CSRF'] = csrf;
    return headers;
  }

  /* ------------------------------------------------------------------ */
  /* Mock driver (design review only)                                    */
  /* ------------------------------------------------------------------ */

  function fillMockPanels() {
    var values = {
      'sf-ppid-self': 'lm_1kf3\u20269c21',
      'sf-assurance-label': 'Signed in with a passkey.',
      'sf-signin-time': 'Just now \u00b7 0.9s',
      'sf-ppid-lemma': 'lm_1kf3\u20269c21',
      'sf-ppid-shop': 'lm_8ax2\u2026e4d7',
      'sf-ppid-news': 'lm_q9m4\u202677b0',
    };
    Object.keys(values).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.textContent = values[id];
    });
  }

  var mockDriver = {
    hasLocalCredential: function () {
      return Promise.resolve(sessionStorage.getItem('sf-mock-created') === '1');
    },
    hasSession: function () {
      return Promise.resolve(sessionStorage.getItem('sf-mock-session') === '1');
    },
    create: function () {
      return new Promise(function (resolve) {
        setTimeout(function () {
          sessionStorage.setItem('sf-mock-created', '1');
          sessionStorage.setItem('sf-mock-session', '1');
          resolve({ ok: true, signedIn: true, timeMs: 900 });
        }, 900);
      });
    },
    signIn: function () {
      return new Promise(function (resolve) {
        setTimeout(function () {
          sessionStorage.setItem('sf-mock-session', '1');
          resolve({ ok: true, timeMs: 912 });
        }, 750);
      });
    },
    signOut: function () {
      sessionStorage.removeItem('sf-mock-session');
      return Promise.resolve({ ok: true });
    },
    openManager: function () {
      fillMockPanels();
      show('manager');
      window.scrollTo(0, 0);
    },
  };

  /* ------------------------------------------------------------------ */
  /* Real driver: ProofVerifier SDK + /api/auth/session                  */
  /* ------------------------------------------------------------------ */

  function waitForGlobal(name, timeoutMs) {
    return new Promise(function (resolve, reject) {
      var waited = 0;
      (function poll() {
        if (window[name]) return resolve(window[name]);
        waited += 50;
        if (waited >= (timeoutMs || 6000)) return reject(new Error(name + '_unavailable'));
        setTimeout(poll, 50);
      })();
    });
  }

  function verifyWithSdk() {
    return waitForGlobal('ProofVerifier').then(function (ProofVerifier) {
      var config = {
        siteId: SITE_ID,
        lemmaOrigin: window.location.origin,
        requiredAssurance: 'passkey',
      };
      if (DEV_ROOT_PUBKEY) config.networkRootPubkeys = [DEV_ROOT_PUBKEY];
      var verifier = new ProofVerifier(config);
      return verifier.verifyForBackend({
        autoProvision: true,
        requiredAssurance: 'passkey',
      });
    });
  }

  var realDriver = {
    hasSession: function () {
      return fetch('/api/auth/session', { credentials: 'same-origin' })
        .then(function (resp) { return resp.json(); })
        .then(function (data) { return !!data.signed_in; })
        .catch(function () { return false; });
    },
    hasLocalCredential: function () {
      return waitForGlobal('LemmaWallet')
        .then(function (LemmaWallet) {
          var wallet = window.globalLemmaWallet;
          if (!wallet) {
            wallet = new LemmaWallet();
            window.globalLemmaWallet = wallet;
          }
          var ready = wallet._initialized ? Promise.resolve() : wallet.init();
          return ready.then(function () {
            return wallet.getWalletInfo({ lite: true });
          });
        })
        .then(function (info) {
          return !!(info && (info.hasWallet || info.hasPasskey));
        })
        .catch(function () { return false; });
    },
    postSession: function (presentation, t0) {
      return fetch('/api/auth/session', {
        method: 'POST',
        credentials: 'same-origin',
        headers: jsonHeaders(),
        body: JSON.stringify({ presentation: presentation }),
      }).then(function (resp) {
        return resp.json().catch(function () { return {}; }).then(function (data) {
          if (!resp.ok || !data.success) {
            return { ok: false, reason: data.error || 'not_verified' };
          }
          var t1 = (window.performance && performance.now()) || Date.now();
          return { ok: true, signedIn: true, timeMs: Math.round(t1 - (t0 || t1)) };
        });
      });
    },
    create: function () {
      // One ceremony: create lemma.id (if needed), issue this site's proof,
      // then mint the platform session so the user lands signed in.
      var t0 = (window.performance && performance.now()) || Date.now();
      return verifyWithSdk().then(function (result) {
        if (!result || !result.ok || !result.presentation) {
          return { ok: false, reason: (result && result.reason) || 'unknown' };
        }
        return realDriver.postSession(result.presentation, t0);
      });
    },
    signIn: function () {
      var t0 = (window.performance && performance.now()) || Date.now();
      return verifyWithSdk().then(function (result) {
        if (!result || !result.ok || !result.presentation) {
          return { ok: false, reason: (result && result.reason) || 'not_verified' };
        }
        return realDriver.postSession(result.presentation, t0);
      });
    },
    signOut: function () {
      return fetch('/api/auth/session/logout', {
        method: 'POST',
        credentials: 'same-origin',
        headers: jsonHeaders(),
      }).then(function () { return { ok: true }; });
    },
    openManager: function () {
      window.location.href = '/app';
    },
  };

  function isLemmaRedirectReturn() {
    try {
      return new URLSearchParams(window.location.search).get('lemma_ishuman_return') === '1';
    } catch (_) {
      return false;
    }
  }

  /** Returning from relying-site demos / builder deep-links must not bounce to /app. */
  function wantsBuilderHub() {
    try {
      var p = new URLSearchParams(window.location.search);
      return p.get('lane') === 'builder' || p.has('from');
    } catch (_) {
      return false;
    }
  }

  function openBuilderHub() {
    var dest = '/demo/how-it-works?lane=builder';
    try {
      var p = new URLSearchParams(window.location.search);
      var from = p.get('from');
      if (from) dest += '&from=' + encodeURIComponent(from);
    } catch (_) { /* ignore */ }
    window.location.replace(dest);
  }

  var driver = MOCK ? mockDriver : realDriver;

  /* ------------------------------------------------------------------ */
  /* Wiring                                                              */
  /* ------------------------------------------------------------------ */

  var createBtn = document.getElementById('sf-create-btn');
  var signinBtn = document.getElementById('sf-signin-btn');
  var gateBtn = document.getElementById('sf-gate-signin-btn');
  var copyBtn = document.getElementById('sf-copy-ppid');
  var signoutBtn = document.getElementById('sf-signout-btn');

  if (createBtn) {
    createBtn.addEventListener('click', function () {
      setBusy(createBtn, true);
      setStatus('sf-create-status', 'Follow your device prompt\u2026');
      driver.create().then(function (result) {
        setBusy(createBtn, false);
        if (result && result.ok && result.signedIn) {
          setStatus('sf-create-status', '');
          driver.openManager();
          return;
        }
        if (result && result.ok) {
          // Local credential exists but session mint failed. Offer explicit sign-in.
          setStatus('sf-create-status', '');
          show('signin');
          return;
        }
        setStatus('sf-create-status', plain(result && result.reason), true);
      }).catch(function () {
        setBusy(createBtn, false);
        setStatus('sf-create-status', plain('unknown'), true);
      });
    });
  }

  function handleSignIn(btn, statusId, onSuccess) {
    setBusy(btn, true);
    setStatus(
      statusId,
      isLemmaRedirectReturn()
        ? 'Finishing sign-in\u2026'
        : 'Follow your device prompt\u2026'
    );
    driver.signIn().then(function (result) {
      setBusy(btn, false);
      if (result && result.ok) {
        setStatus(statusId, '');
        onSuccess(result);
      } else {
        setStatus(statusId, plain(result && result.reason), true);
      }
    }).catch(function () {
      setBusy(btn, false);
      setStatus(statusId, plain('unknown'), true);
    });
  }

  if (signinBtn) {
    signinBtn.addEventListener('click', function () {
      handleSignIn(signinBtn, 'sf-signin-status', function () {
        driver.openManager();
      });
    });
  }

  if (gateBtn) {
    gateBtn.addEventListener('click', function () {
      handleSignIn(gateBtn, 'sf-gate-status', function () {
        driver.openManager();
      });
    });
  }

  if (copyBtn) {
    copyBtn.addEventListener('click', function () {
      var full = copyBtn.getAttribute('data-full-ppid') || '';
      if (!full) return;
      if (navigator.clipboard) {
        navigator.clipboard.writeText(full).then(function () {
          copyBtn.textContent = 'Copied';
          setTimeout(function () { copyBtn.textContent = 'Copy'; }, 1400);
        });
      }
    });
  }

  if (signoutBtn) {
    signoutBtn.addEventListener('click', function () {
      driver.signOut().then(function () {
        if (MOCK) {
          show('create');
          window.scrollTo(0, 0);
        } else {
          window.location.href = '/demo';
        }
      });
    });
  }

  /* ------------------------------------------------------------------ */
  /* Initial screen resolution                                           */
  /* ------------------------------------------------------------------ */

  var forced = root.getAttribute('data-screen');
  var params = new URLSearchParams(window.location.search);
  var queryScreen = MOCK ? params.get('screen') : null;
  var initial = queryScreen || forced;

  // Mobile/same-tab return: the SDK deposited a site proof under request_nonce
  // and sent the user back here. Claim it, mint the session, open /app.
  // Must run before the forced-gate early return — /app without a session
  // always sets data-screen="gate", which would otherwise skip this.
  if (!MOCK && isLemmaRedirectReturn()) {
    var returnScreen = (forced === 'gate' && SCREENS.gate) ? 'gate' : 'signin';
    show(returnScreen);
    handleSignIn(
      returnScreen === 'gate' ? gateBtn : signinBtn,
      returnScreen === 'gate' ? 'sf-gate-status' : 'sf-signin-status',
      function () { driver.openManager(); }
    );
    return;
  }

  if (initial && SCREENS[initial]) {
    if (MOCK && initial === 'manager') fillMockPanels();
    show(initial);
    return;
  }

  // Old bookmarks and demo-site "Return to demo hub" links still hit /demo.
  // When they carry builder/return markers, send signed-in users to the hub
  // instead of the manager so the Create · Sign in · Enforce flow stays usable.
  if (!MOCK && wantsBuilderHub()) {
    openBuilderHub();
    return;
  }

  Promise.all([driver.hasSession(), driver.hasLocalCredential()]).then(function (results) {
    if (results[0]) {
      driver.openManager();
    } else if (results[1]) {
      show('signin');
    } else {
      show('create');
    }
  }).catch(function () {
    show('create');
  });
})();
