/**
 * Accessibility Enhancements for Lemma Enterprise
 * Implements keyboard navigation, dark mode, and focus management
 */

class AccessibilityManager {
    constructor() {
        this.darkModeEnabled = this.getDarkModePreference();
        this.focusVisible = true;
        this.init();
    }

    init() {
        this.setupDarkMode();
        this.setupKeyboardNavigation();
        this.setupFocusManagement();
        this.setupAriaLiveRegion();
        this.setupReducedMotion();
        this.setupHighContrast();
        this.setupMobileNavigation();
    }

    // ===== DARK MODE FUNCTIONALITY =====
    
    getDarkModePreference() {
        // Check localStorage first, then system preference
        const stored = localStorage.getItem('lemma-dark-mode');
        if (stored !== null) {
            return stored === 'true';
        }
        return window.matchMedia('(prefers-color-scheme: dark)').matches;
    }

    setupDarkMode() {
        const toggle = document.getElementById('dark-mode-toggle');
        if (!toggle) return;

        // Set initial state
        this.applyDarkMode(this.darkModeEnabled);
        this.updateDarkModeIcon(this.darkModeEnabled);

        // Toggle event
        toggle.addEventListener('click', () => {
            this.darkModeEnabled = !this.darkModeEnabled;
            this.applyDarkMode(this.darkModeEnabled);
            this.updateDarkModeIcon(this.darkModeEnabled);
            localStorage.setItem('lemma-dark-mode', this.darkModeEnabled.toString());
            
            // Announce to screen readers
            this.announceToScreenReader(
                `Dark mode ${this.darkModeEnabled ? 'enabled' : 'disabled'}`
            );
        });

        // Listen for system preference changes
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            if (localStorage.getItem('lemma-dark-mode') === null) {
                this.darkModeEnabled = e.matches;
                this.applyDarkMode(this.darkModeEnabled);
                this.updateDarkModeIcon(this.darkModeEnabled);
            }
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
            // Moon icon for dark mode
            icon.innerHTML = `
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
            `;
        } else {
            // Sun icon for light mode
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

    // ===== KEYBOARD NAVIGATION =====

    setupKeyboardNavigation() {
        // Global keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Escape key handling
            if (e.key === 'Escape') {
                this.handleEscapeKey();
            }

            // Tab navigation improvements
            if (e.key === 'Tab') {
                this.handleTabNavigation(e);
            }

            // Arrow key navigation for menus
            if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
                this.handleArrowNavigation(e);
            }

            // Enter and Space for button activation
            if (e.key === 'Enter' || e.key === ' ') {
                this.handleActivationKeys(e);
            }

            // Dark mode toggle shortcut (Ctrl/Cmd + Shift + D)
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'D') {
                e.preventDefault();
                document.getElementById('dark-mode-toggle')?.click();
            }
        });

        // Focus visible detection
        document.addEventListener('mousedown', () => {
            this.focusVisible = false;
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Tab') {
                this.focusVisible = true;
            }
        });
    }

    handleEscapeKey() {
        // Close modals
        const openModal = document.querySelector('.modal[aria-hidden="false"]');
        if (openModal) {
            const closeBtn = openModal.querySelector('.modal-close, [data-dismiss="modal"]');
            closeBtn?.click();
            return;
        }

        // Close mobile menu
        const mobileMenu = document.querySelector('.mobile-menu.open');
        if (mobileMenu) {
            const menuButton = document.querySelector('[data-mobile-menu]');
            menuButton?.click();
            return;
        }

        // Close dropdowns
        const openDropdown = document.querySelector('.dropdown.open');
        if (openDropdown) {
            openDropdown.classList.remove('open');
        }
    }

    handleTabNavigation(e) {
        // Trap focus in modals
        const modal = document.querySelector('.modal[aria-hidden="false"]');
        if (modal) {
            this.trapFocus(modal, e);
        }
    }

    handleArrowNavigation(e) {
        const target = e.target;
        
        // Menu navigation
        if (target.closest('.navbar-nav, .dropdown-menu')) {
            e.preventDefault();
            this.navigateMenu(target, e.key);
        }

        // Tab navigation
        if (target.closest('.tabs')) {
            e.preventDefault();
            this.navigateTabs(target, e.key);
        }
    }

    handleActivationKeys(e) {
        const target = e.target;
        
        // Activate buttons with role="button"
        if (target.getAttribute('role') === 'button' && !target.disabled) {
            e.preventDefault();
            target.click();
        }

        // Activate links with role="link"
        if (target.getAttribute('role') === 'link') {
            e.preventDefault();
            target.click();
        }
    }

    // ===== FOCUS MANAGEMENT =====

    setupFocusManagement() {
        // Skip link functionality
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

        // Focus management for dynamic content
        this.setupDynamicFocusManagement();
    }

    setupDynamicFocusManagement() {
        // Observe DOM changes and manage focus
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.type === 'childList') {
                    mutation.addedNodes.forEach((node) => {
                        if (node.nodeType === Node.ELEMENT_NODE) {
                            this.manageFocusForNewContent(node);
                        }
                    });
                }
            });
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    manageFocusForNewContent(element) {
        // Auto-focus first interactive element in new modals
        if (element.classList?.contains('modal')) {
            const firstFocusable = this.getFocusableElements(element)[0];
            if (firstFocusable) {
                setTimeout(() => firstFocusable.focus(), 100);
            }
        }

        // Announce new content to screen readers
        if (element.classList?.contains('toast') || element.classList?.contains('alert')) {
            this.announceToScreenReader(element.textContent);
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

    // ===== MENU NAVIGATION =====

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

    navigateTabs(currentElement, key) {
        const tabList = currentElement.closest('.tabs');
        const tabs = Array.from(tabList.querySelectorAll('[role="tab"]'));
        const currentIndex = tabs.indexOf(currentElement);

        let nextIndex;
        if (key === 'ArrowRight') {
            nextIndex = (currentIndex + 1) % tabs.length;
        } else if (key === 'ArrowLeft') {
            nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
        }

        if (nextIndex !== undefined) {
            tabs[nextIndex].focus();
            tabs[nextIndex].click();
        }
    }

    // ===== ARIA LIVE REGION =====

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
            // Clear after announcement
            setTimeout(() => {
                this.liveRegion.textContent = '';
            }, 1000);
        }
    }

    // ===== REDUCED MOTION SUPPORT =====

    setupReducedMotion() {
        const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
        
        const handleReducedMotion = (e) => {
            if (e.matches) {
                document.body.classList.add('reduce-motion');
            } else {
                document.body.classList.remove('reduce-motion');
            }
        };

        handleReducedMotion(prefersReducedMotion);
        prefersReducedMotion.addEventListener('change', handleReducedMotion);
    }

    // ===== HIGH CONTRAST SUPPORT =====

    setupHighContrast() {
        const prefersHighContrast = window.matchMedia('(prefers-contrast: high)');
        
        const handleHighContrast = (e) => {
            if (e.matches) {
                document.body.classList.add('high-contrast');
            } else {
                document.body.classList.remove('high-contrast');
            }
        };

        handleHighContrast(prefersHighContrast);
        prefersHighContrast.addEventListener('change', handleHighContrast);
    }

    // ===== MOBILE NAVIGATION =====

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

            // Close on outside click
            document.addEventListener('click', (e) => {
                if (!mobileMenuBtn.contains(e.target) && !mobileMenu.contains(e.target)) {
                    this.closeMobileMenu(mobileMenuBtn, mobileMenu);
                }
            });
        }
    }

    openMobileMenu(button, menu) {
        menu.classList.add('open');
        button.setAttribute('aria-expanded', 'true');
        
        // Focus first menu item
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
}

// ===== FORM ENHANCEMENTS =====

class FormAccessibilityManager {
    constructor() {
        this.init();
    }

    init() {
        this.setupFormValidation();
        this.setupFormLabels();
        this.setupFormErrors();
    }

    setupFormValidation() {
        const forms = document.querySelectorAll('form');
        
        forms.forEach(form => {
            const inputs = form.querySelectorAll('input, textarea, select');
            
            inputs.forEach(input => {
                // Real-time validation
                input.addEventListener('blur', () => {
                    this.validateField(input);
                });

                input.addEventListener('input', () => {
                    if (input.classList.contains('error')) {
                        this.validateField(input);
                    }
                });
            });
        });
    }

    validateField(field) {
        const isValid = field.checkValidity();
        
        field.setAttribute('aria-invalid', !isValid);
        
        if (isValid) {
            field.classList.remove('error');
            field.classList.add('valid');
            this.clearFieldError(field);
        } else {
            field.classList.add('error');
            field.classList.remove('valid');
            this.showFieldError(field);
        }
    }

    showFieldError(field) {
        const errorId = `${field.id || field.name}-error`;
        let errorElement = document.getElementById(errorId);
        
        if (!errorElement) {
            errorElement = document.createElement('div');
            errorElement.id = errorId;
            errorElement.className = 'form-error';
            errorElement.setAttribute('role', 'alert');
            field.parentNode.appendChild(errorElement);
        }

        errorElement.textContent = field.validationMessage;
        field.setAttribute('aria-describedby', errorId);
    }

    clearFieldError(field) {
        const errorId = `${field.id || field.name}-error`;
        const errorElement = document.getElementById(errorId);
        
        if (errorElement) {
            errorElement.textContent = '';
            field.removeAttribute('aria-describedby');
        }
    }

    setupFormLabels() {
        // Ensure all form fields have proper labels
        const inputs = document.querySelectorAll('input, textarea, select');
        
        inputs.forEach(input => {
            if (!input.getAttribute('aria-label') && !input.getAttribute('aria-labelledby')) {
                const label = document.querySelector(`label[for="${input.id}"]`);
                if (!label && input.id) {
                    console.warn(`Form field ${input.id} is missing a label`);
                }
            }
        });
    }

    setupFormErrors() {
        // Handle server-side validation errors
        const errorMessages = document.querySelectorAll('.form-error, .field-error');
        
        errorMessages.forEach(error => {
            error.setAttribute('role', 'alert');
            
            // Associate with field if possible
            const field = error.previousElementSibling;
            if (field && (field.tagName === 'INPUT' || field.tagName === 'TEXTAREA' || field.tagName === 'SELECT')) {
                const errorId = error.id || `${field.id || field.name}-error`;
                error.id = errorId;
                field.setAttribute('aria-describedby', errorId);
                field.setAttribute('aria-invalid', 'true');
            }
        });
    }
}

// ===== INITIALIZATION =====

document.addEventListener('DOMContentLoaded', () => {
    // Initialize accessibility managers
    window.accessibilityManager = new AccessibilityManager();
    window.formAccessibilityManager = new FormAccessibilityManager();

    // Add focus-visible polyfill class
    document.body.classList.add('js-focus-visible');

    console.log('[ACCESSIBILITY] Accessibility enhancements initialized');
});

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { AccessibilityManager, FormAccessibilityManager };
} 