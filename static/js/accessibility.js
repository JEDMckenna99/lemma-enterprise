// Accessibility Enhancements for Lemma Enterprise
// Implements keyboard navigation, dark mode, and focus management

class AccessibilityManager {
    constructor() {
        this.darkModeEnabled = this.getDarkModePreference();
        this.init();
    }

    init() {
        this.setupDarkMode();
        this.setupKeyboardNavigation();
        this.setupFocusManagement();
        this.setupMobileNavigation();
        this.setupAriaLiveRegion();
    }

    getDarkModePreference() {
        const stored = localStorage.getItem('lemma-dark-mode');
        if (stored !== null) {
            return stored === 'true';
        }
        return window.matchMedia('(prefers-color-scheme: dark)').matches;
    }

    setupDarkMode() {
        const toggle = document.getElementById('dark-mode-toggle');
        if (!toggle) return;

        this.applyDarkMode(this.darkModeEnabled);
        this.updateDarkModeIcon(this.darkModeEnabled);

        toggle.addEventListener('click', () => {
            this.darkModeEnabled = !this.darkModeEnabled;
            this.applyDarkMode(this.darkModeEnabled);
            this.updateDarkModeIcon(this.darkModeEnabled);
            localStorage.setItem('lemma-dark-mode', this.darkModeEnabled.toString());
            
            this.announceToScreenReader(
                `Dark mode ${this.darkModeEnabled ? 'enabled' : 'disabled'}`
            );
        });
    }

    applyDarkMode(enabled) {
        if (enabled) {
            document.documentElement.setAttribute('data-theme', 'dark');
        } else {
            document.documentElement.removeAttribute('data-theme');
        }
    }

    updateDarkModeIcon(enabled) {
        const toggle = document.getElementById('dark-mode-toggle');
        if (!toggle) return;

        const icon = toggle.querySelector('svg');
        if (enabled) {
            icon.innerHTML = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>';
        } else {
            icon.innerHTML = `
                <circle cx="12" cy="12" r="5"></circle>
                <line x1="12" y1="1" x2="12" y2="3"></line>
                <line x1="12" y1="21" x2="12" y2="23"></line>
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
                <line x1="1" y1="12" x2="3" y2="12"></line>
                <line x1="21" y1="12" x2="23" y2="12"></line>
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
            `;
        }
    }

    setupKeyboardNavigation() {
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.handleEscapeKey();
            }

            if (e.key === 'Tab') {
                this.handleTabNavigation(e);
            }

            if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
                this.handleArrowNavigation(e);
            }

            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'D') {
                e.preventDefault();
                document.getElementById('dark-mode-toggle')?.click();
            }
        });
    }

    handleEscapeKey() {
        const openModal = document.querySelector('.modal[aria-hidden="false"]');
        if (openModal) {
            const closeBtn = openModal.querySelector('.modal-close, [data-dismiss="modal"]');
            closeBtn?.click();
            return;
        }

        const mobileMenu = document.querySelector('.mobile-menu.open');
        if (mobileMenu) {
            const menuButton = document.querySelector('[data-mobile-menu]');
            menuButton?.click();
            return;
        }
    }

    handleTabNavigation(e) {
        const modal = document.querySelector('.modal[aria-hidden="false"]');
        if (modal) {
            this.trapFocus(modal, e);
        }
    }

    handleArrowNavigation(e) {
        const target = e.target;
        
        if (target.closest('.navbar-nav, .dropdown-menu')) {
            e.preventDefault();
            this.navigateMenu(target, e.key);
        }
    }

    trapFocus(container, e) {
        const focusableElements = this.getFocusableElements(container);
        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (e.shiftKey) {
            if (document.activeElement === firstElement) {
                e.preventDefault();
                lastElement.focus();
            }
        } else {
            if (document.activeElement === lastElement) {
                e.preventDefault();
                firstElement.focus();
            }
        }
    }

    getFocusableElements(container) {
        const selector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
        return Array.from(container.querySelectorAll(selector))
            .filter(el => !el.disabled && !el.hidden && el.offsetParent !== null);
    }

    navigateMenu(currentElement, key) {
        const menu = currentElement.closest('.navbar-nav, .dropdown-menu');
        const items = Array.from(menu.querySelectorAll('a, button'));
        const currentIndex = items.indexOf(currentElement);

        let nextIndex;
        if (key === 'ArrowDown' || key === 'ArrowRight') {
            nextIndex = (currentIndex + 1) % items.length;
        } else if (key === 'ArrowUp' || key === 'ArrowLeft') {
            nextIndex = (currentIndex - 1 + items.length) % items.length;
        }

        if (nextIndex !== undefined) {
            items[nextIndex].focus();
        }
    }

    setupFocusManagement() {
        const skipLink = document.querySelector('.skip-link');
        if (skipLink) {
            skipLink.addEventListener('click', (e) => {
                e.preventDefault();
                const target = document.querySelector(skipLink.getAttribute('href'));
                if (target) {
                    target.focus();
                    target.scrollIntoView({ behavior: 'smooth' });
                }
            });
        }
    }

    setupMobileNavigation() {
        const mobileMenuBtn = document.querySelector('[data-mobile-menu]');
        const mobileMenu = document.getElementById('mobile-menu');
        
        if (mobileMenuBtn && mobileMenu) {
            mobileMenuBtn.addEventListener('click', () => {
                const isOpen = mobileMenu.classList.contains('open');
                
                if (isOpen) {
                    this.closeMobileMenu(mobileMenuBtn, mobileMenu);
                } else {
                    this.openMobileMenu(mobileMenuBtn, mobileMenu);
                }
            });
        }
    }

    openMobileMenu(button, menu) {
        menu.classList.add('open');
        button.setAttribute('aria-expanded', 'true');
        
        const firstMenuItem = menu.querySelector('a, button');
        if (firstMenuItem) {
            setTimeout(() => firstMenuItem.focus(), 100);
        }

        this.announceToScreenReader('Navigation menu opened');
    }

    closeMobileMenu(button, menu) {
        menu.classList.remove('open');
        button.setAttribute('aria-expanded', 'false');
        button.focus();
        
        this.announceToScreenReader('Navigation menu closed');
    }

    setupAriaLiveRegion() {
        this.liveRegion = document.getElementById('live-region');
        if (!this.liveRegion) {
            this.liveRegion = document.createElement('div');
            this.liveRegion.id = 'live-region';
            this.liveRegion.setAttribute('aria-live', 'polite');
            this.liveRegion.setAttribute('aria-atomic', 'true');
            this.liveRegion.className = 'sr-only';
            document.body.appendChild(this.liveRegion);
        }
    }

    announceToScreenReader(message) {
        if (this.liveRegion) {
            this.liveRegion.textContent = message;
            setTimeout(() => {
                this.liveRegion.textContent = '';
            }, 1000);
        }
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.accessibilityManager = new AccessibilityManager();
    console.log('[ACCESSIBILITY] Accessibility enhancements initialized');
}); 