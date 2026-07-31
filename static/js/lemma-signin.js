/**
 * lemma-signin — drop-in "Sign in with lemma.id" web component.
 *
 * Loads ProofVerifier internally; sites listen for success/error events.
 *
 * Usage:
 *   <script src="https://lemma.id/sdk/proof-verifier.js"></script>
 *   <script src="https://lemma.id/sdk/lemma-signin.js"></script>
 *   <lemma-signin site-id="app.example.com"></lemma-signin>
 *
 *   document.querySelector('lemma-signin').addEventListener('lemma-signin-success', (e) => {
 *     fetch('/api/login', { method: 'POST', body: JSON.stringify({ presentation: e.detail.presentation }) });
 *   });
 */
(function () {
  'use strict';

  const STYLES = `
    :host { display: inline-block; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
    button {
      display: inline-flex; align-items: center; justify-content: center; gap: 0.5rem;
      min-height: 44px; padding: 0.625rem 1.25rem; border: none; border-radius: 8px;
      background: linear-gradient(180deg, #5a4899 0%, #4e3d8f 100%);
      color: #fff; font-size: 0.9375rem; font-weight: 600; cursor: pointer;
      box-shadow: 0 1px 2px rgba(0,0,0,.12);
    }
    button:hover:not(:disabled) { filter: brightness(1.05); }
    button:disabled { opacity: 0.65; cursor: wait; }
    .lemma-mark { font-weight: 700; letter-spacing: -0.02em; }
  `;

  function parseBool(value, defaultValue) {
    if (value == null || value === '') return defaultValue;
    const normalized = String(value).trim().toLowerCase();
    if (normalized === 'false' || normalized === '0') return false;
    if (normalized === 'true' || normalized === '1') return true;
    return defaultValue;
  }

  class LemmaSignIn extends HTMLElement {
    static get observedAttributes() {
      return ['site-id', 'required-assurance', 'auto-provision', 'disabled', 'label'];
    }

    connectedCallback() {
      if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
      this._render();
      if (!this._bound) {
        this._bound = true;
        this.shadowRoot.querySelector('button')?.addEventListener('click', () => this.signIn());
      }
    }

    attributeChangedCallback() {
      if (this.shadowRoot) this._render();
    }

    get siteId() {
      return (
        this.getAttribute('site-id')
        || this.getAttribute('siteId')
        || (typeof window !== 'undefined' ? window.location.hostname : '')
      );
    }

    get requiredAssurance() {
      return (this.getAttribute('required-assurance') || 'passkey').toLowerCase();
    }

    get autoProvision() {
      return parseBool(this.getAttribute('auto-provision'), true);
    }

    get buttonLabel() {
      return this.getAttribute('label') || 'Sign in with lemma.id';
    }

    _render() {
      const disabled = this.hasAttribute('disabled');
      this.shadowRoot.innerHTML = `
        <style>${STYLES}</style>
        <button type="button" part="button" ${disabled ? 'disabled' : ''}></button>
      `;
      const btn = this.shadowRoot.querySelector('button');
      if (btn) btn.textContent = this.buttonLabel;
    }

    _setBusy(busy) {
      const btn = this.shadowRoot?.querySelector('button');
      if (btn) btn.disabled = !!busy || this.hasAttribute('disabled');
    }

    async signIn() {
      if (typeof window === 'undefined' || typeof window.ProofVerifier !== 'function') {
        this.dispatchEvent(new CustomEvent('lemma-signin-error', {
          bubbles: true,
          composed: true,
          detail: { reason: 'sdk_not_loaded', message: 'Load /sdk/proof-verifier.js before lemma-signin.js' },
        }));
        return null;
      }
      this._setBusy(true);
      try {
        const verifier = new window.ProofVerifier({ siteId: this.siteId });
        const result = await verifier.verifyForBackend({
          autoProvision: this.autoProvision,
          requiredAssurance: this.requiredAssurance,
        });
        if (!result.ok) {
          this.dispatchEvent(new CustomEvent('lemma-signin-error', {
            bubbles: true,
            composed: true,
            detail: {
              reason: result.reason || 'not_verified',
              ppid: result.ppid || null,
              assurance: result.assurance || null,
              timeMs: result.timeMs,
            },
          }));
          return result;
        }
        this.dispatchEvent(new CustomEvent('lemma-signin-success', {
          bubbles: true,
          composed: true,
          detail: {
            presentation: result.presentation,
            ppid: result.ppid,
            assurance: result.assurance,
            timeMs: result.timeMs,
          },
        }));
        return result;
      } catch (err) {
        this.dispatchEvent(new CustomEvent('lemma-signin-error', {
          bubbles: true,
          composed: true,
          detail: { reason: 'signin_failed', message: err?.message || String(err) },
        }));
        return null;
      } finally {
        this._setBusy(false);
      }
    }
  }

  if (!customElements.get('lemma-signin')) {
    customElements.define('lemma-signin', LemmaSignIn);
  }

  window.LemmaSignInElement = LemmaSignIn;
})();
