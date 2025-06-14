/**
 * Lemma Stripe Design System Components
 * Interactive JavaScript components following Stripe patterns
 */

// Initialize all components when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeStripeLikeComponents();
});

function initializeStripeLikeComponents() {
    initializeCopyToClipboard();
    initializeTabs();
    initializeAlerts();
    initializeSkeletonLoaders();
    initializeStepCheckmarks();
    initializeFormValidation();
    initializeTooltips();
}

/**
 * Copy-to-clipboard functionality for code blocks
 * Appears on hover, top-right, 24px icon
 */
function initializeCopyToClipboard() {
    const codeBlocks = document.querySelectorAll('.code-block');
    
    codeBlocks.forEach(block => {
        // Create copy button
        const copyButton = document.createElement('button');
        copyButton.className = 'copy-button';
        copyButton.innerHTML = `
            <svg class="icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                      d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
        `;
        
        copyButton.addEventListener('click', async () => {
            const code = block.textContent;
            try {
                await navigator.clipboard.writeText(code);
                
                // Show feedback
                copyButton.innerHTML = `
                    <svg class="icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                              d="M5 13l4 4L19 7" />
                    </svg>
                `;
                
                setTimeout(() => {
                    copyButton.innerHTML = `
                        <svg class="icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                                  d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                        </svg>
                    `;
                }, 2000);
            } catch (err) {
                console.error('Failed to copy text: ', err);
            }
        });
        
        block.appendChild(copyButton);
    });
}

/**
 * Tab functionality with bottom-border indicator
 * Active tab font-weight 500, 2px primary indicator
 */
function initializeTabs() {
    const tabContainers = document.querySelectorAll('.tabs');
    
    tabContainers.forEach(container => {
        const tabs = container.querySelectorAll('.tab');
        const panels = document.querySelectorAll('[data-tab-panel]');
        
        tabs.forEach(tab => {
            tab.addEventListener('click', (e) => {
                e.preventDefault();
                
                // Remove active class from all tabs
                tabs.forEach(t => t.classList.remove('active'));
                
                // Add active class to clicked tab
                tab.classList.add('active');
                
                // Handle tab panels if they exist
                const targetPanel = tab.getAttribute('data-tab-target');
                if (targetPanel) {
                    panels.forEach(panel => {
                        panel.style.display = 'none';
                    });
                    
                    const activePanel = document.querySelector(`[data-tab-panel="${targetPanel}"]`);
                    if (activePanel) {
                        activePanel.style.display = 'block';
                    }
                }
            });
        });
    });
}

/**
 * Alert/Toast functionality
 * Slide-in from bottom-right, auto-dismiss 4s
 */
function initializeAlerts() {
    // Auto-dismiss alerts
    const alerts = document.querySelectorAll('.alert');
    
    alerts.forEach(alert => {
        // Add auto-dismiss class if not present
        if (!alert.classList.contains('manual-dismiss')) {
            alert.classList.add('auto-dismiss');
            
            setTimeout(() => {
                alert.style.animation = 'fadeOut 250ms cubic-bezier(0.32, 0.72, 0.36, 0.95) forwards';
                setTimeout(() => {
                    alert.remove();
                }, 250);
            }, 4000);
        }
        
        // Add close button if needed
        const closeButton = alert.querySelector('.alert-close');
        if (closeButton) {
            closeButton.addEventListener('click', () => {
                alert.style.animation = 'fadeOut 250ms cubic-bezier(0.32, 0.72, 0.36, 0.95) forwards';
                setTimeout(() => {
                    alert.remove();
                }, 250);
            });
        }
    });
}

/**
 * Create and show toast notifications
 */
function showToast(message, type = 'info') {
    const flashContainer = document.querySelector('.flash-messages') || createFlashContainer();
    
    const toast = document.createElement('div');
    toast.className = `alert alert-${type} flash-message auto-dismiss`;
    toast.innerHTML = `
        <div class="flex items-center gap-3">
            ${getAlertIcon(type)}
            <span>${message}</span>
            <button class="alert-close ml-auto">
                <svg class="icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
            </button>
        </div>
    `;
    
    flashContainer.appendChild(toast);
    
    // Auto-dismiss
    setTimeout(() => {
        toast.style.animation = 'fadeOut 250ms cubic-bezier(0.32, 0.72, 0.36, 0.95) forwards';
        setTimeout(() => {
            toast.remove();
        }, 250);
    }, 4000);
    
    // Manual close
    const closeButton = toast.querySelector('.alert-close');
    closeButton.addEventListener('click', () => {
        toast.style.animation = 'fadeOut 250ms cubic-bezier(0.32, 0.72, 0.36, 0.95) forwards';
        setTimeout(() => {
            toast.remove();
        }, 250);
    });
}

function createFlashContainer() {
    const container = document.createElement('div');
    container.className = 'flash-messages';
    document.body.appendChild(container);
    return container;
}

function getAlertIcon(type) {
    const icons = {
        success: `<svg class="icon text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                  </svg>`,
        error: `<svg class="icon text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>`,
        warning: `<svg class="icon text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
                  </svg>`,
        info: `<svg class="icon text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                 <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
               </svg>`
    };
    return icons[type] || icons.info;
}

/**
 * Skeleton loaders with shimmer animation
 * Gray-200 bar with loadingShine keyframe
 */
function initializeSkeletonLoaders() {
    // This is mostly CSS-driven, but we can add dynamic skeleton creation
    window.createSkeleton = function(width = '100%', height = '20px') {
        const skeleton = document.createElement('div');
        skeleton.className = 'skeleton';
        skeleton.style.width = width;
        skeleton.style.height = height;
        return skeleton;
    };
}

/**
 * Step checkmarks with animation
 * Animated tick turns primary on completion
 */
function initializeStepCheckmarks() {
    const steps = document.querySelectorAll('[data-step]');
    
    steps.forEach(step => {
        const checkbox = step.querySelector('.step-check');
        const stepNumber = step.getAttribute('data-step');
        
        if (checkbox) {
            // Check if step is completed (you can customize this logic)
            const isCompleted = step.hasAttribute('data-completed');
            
            if (isCompleted) {
                markStepCompleted(checkbox);
            }
        }
    });
    
    // Function to mark step as completed
    window.markStepCompleted = function(stepElement) {
        if (typeof stepElement === 'string') {
            stepElement = document.querySelector(`[data-step="${stepElement}"] .step-check`);
        }
        
        if (stepElement) {
            stepElement.classList.add('completed');
            stepElement.innerHTML = `
                <svg class="icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                </svg>
            `;
        }
    };
}

/**
 * Form validation with Stripe-style error handling
 */
function initializeFormValidation() {
    const forms = document.querySelectorAll('form[data-stripe-validation]');
    
    forms.forEach(form => {
        const inputs = form.querySelectorAll('.form-input');
        
        inputs.forEach(input => {
            input.addEventListener('blur', validateInput);
            input.addEventListener('input', clearValidationError);
        });
        
        form.addEventListener('submit', (e) => {
            let isValid = true;
            
            inputs.forEach(input => {
                if (!validateInput({ target: input })) {
                    isValid = false;
                }
            });
            
            if (!isValid) {
                e.preventDefault();
            }
        });
    });
}

function validateInput(event) {
    const input = event.target;
    const value = input.value.trim();
    let isValid = true;
    let errorMessage = '';
    
    // Required validation
    if (input.hasAttribute('required') && !value) {
        isValid = false;
        errorMessage = 'This field is required';
    }
    
    // Email validation
    if (input.type === 'email' && value) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(value)) {
            isValid = false;
            errorMessage = 'Please enter a valid email address';
        }
    }
    
    // Custom validation
    const customValidation = input.getAttribute('data-validation');
    if (customValidation && value) {
        // Add custom validation logic here
    }
    
    if (!isValid) {
        showInputError(input, errorMessage);
    } else {
        clearInputError(input);
    }
    
    return isValid;
}

function showInputError(input, message) {
    clearInputError(input);
    
    input.classList.add('error');
    input.style.borderColor = 'var(--error)';
    
    const errorElement = document.createElement('div');
    errorElement.className = 'input-error';
    errorElement.style.cssText = 'color: var(--error); font-size: var(--font-size-sm); margin-top: var(--space-1);';
    errorElement.textContent = message;
    
    input.parentNode.insertBefore(errorElement, input.nextSibling);
}

function clearInputError(input) {
    input.classList.remove('error');
    input.style.borderColor = '';
    
    const errorElement = input.parentNode.querySelector('.input-error');
    if (errorElement) {
        errorElement.remove();
    }
}

function clearValidationError(event) {
    const input = event.target;
    if (input.classList.contains('error') && input.value.trim()) {
        clearInputError(input);
    }
}

/**
 * Tooltip functionality
 */
function initializeTooltips() {
    const tooltipTriggers = document.querySelectorAll('[data-tooltip]');
    
    tooltipTriggers.forEach(trigger => {
        let tooltip = null;
        
        trigger.addEventListener('mouseenter', () => {
            const text = trigger.getAttribute('data-tooltip');
            tooltip = createTooltip(text);
            document.body.appendChild(tooltip);
            positionTooltip(trigger, tooltip);
        });
        
        trigger.addEventListener('mouseleave', () => {
            if (tooltip) {
                tooltip.remove();
                tooltip = null;
            }
        });
    });
}

function createTooltip(text) {
    const tooltip = document.createElement('div');
    tooltip.className = 'tooltip';
    tooltip.style.cssText = `
        position: absolute;
        background: var(--gray-800);
        color: var(--white);
        padding: var(--space-2) var(--space-3);
        border-radius: 4px;
        font-size: var(--font-size-sm);
        z-index: 1000;
        pointer-events: none;
        opacity: 0;
        transition: opacity 150ms cubic-bezier(0.32, 0.72, 0.36, 0.95);
    `;
    tooltip.textContent = text;
    
    // Fade in
    setTimeout(() => {
        tooltip.style.opacity = '1';
    }, 10);
    
    return tooltip;
}

function positionTooltip(trigger, tooltip) {
    const triggerRect = trigger.getBoundingClientRect();
    const tooltipRect = tooltip.getBoundingClientRect();
    
    tooltip.style.left = `${triggerRect.left + (triggerRect.width / 2) - (tooltipRect.width / 2)}px`;
    tooltip.style.top = `${triggerRect.top - tooltipRect.height - 8}px`;
}

/**
 * Utility functions for common Stripe-like interactions
 */

// Focus management for accessibility
function manageFocus() {
    const focusableElements = document.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    
    focusableElements.forEach(element => {
        element.addEventListener('keydown', (e) => {
            if (e.key === 'Tab') {
                // Custom tab handling if needed
            }
        });
    });
}

// Loading states for buttons
function setButtonLoading(button, isLoading = true) {
    if (isLoading) {
        button.disabled = true;
        button.innerHTML = `
            <svg class="icon animate-spin" fill="none" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" class="opacity-25"></circle>
                <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" class="opacity-75"></path>
            </svg>
            Loading...
        `;
    } else {
        button.disabled = false;
        // Restore original button text (you may need to store this)
    }
}

// Animate elements into view
function animateIntoView(elements) {
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.animation = 'slideInFromBottom 250ms cubic-bezier(0.32, 0.72, 0.36, 0.95) forwards';
            }
        });
    });
    
    if (typeof elements === 'string') {
        elements = document.querySelectorAll(elements);
    }
    
    elements.forEach(el => observer.observe(el));
}

// Add slide in animation keyframes
const slideInAnimation = `
@keyframes slideInFromBottom {
    from {
        transform: translateY(20px);
        opacity: 0;
    }
    to {
        transform: translateY(0);
        opacity: 1;
    }
}
`;

// Inject animation styles
if (!document.querySelector('#stripe-animations')) {
    const style = document.createElement('style');
    style.id = 'stripe-animations';
    style.textContent = slideInAnimation;
    document.head.appendChild(style);
}

// Export functions for external use
window.LemmaStripeComponents = {
    showToast,
    markStepCompleted,
    setButtonLoading,
    animateIntoView,
    createSkeleton: window.createSkeleton
}; 