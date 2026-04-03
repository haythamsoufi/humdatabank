/**
 * Form Submit Guard - Prevents double form submissions
 *
 * This utility automatically prevents double submissions on forms by:
 * 1. Disabling submit buttons after first click
 * 2. Showing a loading spinner
 * 3. Re-enabling buttons on navigation or if the form is reset
 *
 * Usage:
 * - Include this script in your page
 * - Forms with class 'no-submit-guard' will be excluded
 * - Submit buttons with class 'no-submit-guard' will be excluded
 * - Call FormSubmitGuard.reset(form) to manually reset a form's submission state
 */

(function() {
    'use strict';

    const FormSubmitGuard = {
        _initialized: false,
        _submittingForms: new WeakSet(),

        /**
         * Initialize the form submit guard
         */
        init() {
            if (this._initialized) return;
            this._initialized = true;

            // Listen for form submissions in capture phase (runs first)
            document.addEventListener('submit', this._handleSubmit.bind(this), true);

            // Also listen in bubble phase to check if submission was prevented
            document.addEventListener('submit', this._handleSubmitPrevented.bind(this), false);

            // Re-enable buttons when page is shown from bfcache
            window.addEventListener('pageshow', this._handlePageShow.bind(this));

            // Reset forms when modal is closed (common pattern)
            document.addEventListener('click', this._handleModalClose.bind(this));
        },

        /**
         * Handle form submission
         * @param {Event} event
         */
        _handleSubmit(event) {
            const form = event.target;
            if (!(form instanceof HTMLFormElement)) return;

            // Skip if form has exclusion class
            if (form.classList.contains('no-submit-guard')) return;

            // Skip if submission was already prevented by another handler
            if (event.defaultPrevented) return;

            // If this form requires a confirmation dialog, don't mark it as "submitting"
            // until it's actually confirmed. Otherwise, the confirm flow typically triggers
            // a second submit (via requestSubmit), which would be incorrectly blocked as a duplicate.
            const hasConfirmMessage = (typeof window.hasConfirm === 'function' && window.hasConfirm(form)) ||
                form.hasAttribute('data-confirm') || form.hasAttribute('data-confirm-message') || form.hasAttribute('data-confirm-msg') || form.hasAttribute('data-confirm-text');
            const isConfirmed = form.dataset.confirmed === 'true';
            if (hasConfirmMessage && !isConfirmed) return;

            // Prevent double submission
            if (this._submittingForms.has(form)) {
                event.preventDefault();
                event.stopPropagation();
                console.warn('FormSubmitGuard: Prevented duplicate form submission');
                return;
            }

            // Find the submit button
            const submitButton = this._findSubmitButton(form, event);
            if (!submitButton) return;

            // Skip if button has exclusion class
            if (submitButton.classList.contains('no-submit-guard')) return;

            // Skip if already in loading state
            if (submitButton.dataset.submitGuardActive === '1') return;

            // Mark form as submitting
            this._submittingForms.add(form);

            // Apply loading state to button
            this._setButtonLoading(submitButton, true);
        },

        /**
         * Handle form submission in bubble phase - check if submission was prevented
         * @param {Event} event
         */
        _handleSubmitPrevented(event) {
            const form = event.target;
            if (!(form instanceof HTMLFormElement)) return;

            // Skip if form has exclusion class
            if (form.classList.contains('no-submit-guard')) return;

            // If submission was prevented, reset the button state
            if (event.defaultPrevented) {
                const submitButton = this._findSubmitButton(form, event);
                if (submitButton && submitButton.dataset.submitGuardActive === '1') {
                    // Submission was prevented (e.g., by validation), reset the button
                    this._submittingForms.delete(form);
                    this._setButtonLoading(submitButton, false);
                }
            }
        },

        /**
         * Find the submit button that triggered the submission
         * @param {HTMLFormElement} form
         * @param {Event} event
         * @returns {HTMLButtonElement|HTMLInputElement|null}
         */
        _findSubmitButton(form, event) {
            // Check for submitter (modern browsers)
            if (event.submitter && (event.submitter.type === 'submit' || event.submitter.tagName === 'BUTTON')) {
                return event.submitter;
            }

            // Fallback to first submit button
            return form.querySelector('button[type="submit"], input[type="submit"], button:not([type])');
        },

        /**
         * Set button loading state
         * @param {HTMLButtonElement|HTMLInputElement} button
         * @param {boolean} loading
         */
        _setButtonLoading(button, loading) {
            if (loading) {
                button.dataset.submitGuardActive = '1';
                button.dataset.originalText = button.innerHTML;
                button.disabled = true;
                button.classList.add('opacity-50', 'cursor-not-allowed');

                if (button.tagName.toLowerCase() === 'button') {
                    // Create loading content
                    const loadingText = button.dataset.loadingText || 'Saving...';
                    button.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>' + loadingText;
                }
            } else {
                delete button.dataset.submitGuardActive;
                button.disabled = false;
                button.classList.remove('opacity-50', 'cursor-not-allowed');

                // Restore original text
                if (button.dataset.originalText) {
                    button.innerHTML = button.dataset.originalText;
                    delete button.dataset.originalText;
                }
            }
        },

        /**
         * Handle page show (for back/forward cache)
         * @param {PageTransitionEvent} event
         */
        _handlePageShow(event) {
            if (event.persisted) {
                // Page was restored from bfcache, reset all buttons
                document.querySelectorAll('[data-submit-guard-active="1"]').forEach(button => {
                    this._setButtonLoading(button, false);
                });
                this._submittingForms = new WeakSet();
            }
        },

        /**
         * Handle modal close buttons to reset forms
         * @param {Event} event
         */
        _handleModalClose(event) {
            const target = event.target;

            // Check if this is a modal close action
            if (target.matches('[data-action="close-modal"], [data-bs-dismiss="modal"], [data-dismiss="modal"], .modal-close')) {
                // Find the parent modal
                const modal = target.closest('.modal, [role="dialog"], [aria-modal="true"]');
                if (modal) {
                    // Find any forms in the modal and reset them
                    modal.querySelectorAll('form').forEach(form => {
                        this.reset(form);
                    });
                }
            }
        },

        /**
         * Manually reset a form's submission state
         * @param {HTMLFormElement} form
         */
        reset(form) {
            if (!(form instanceof HTMLFormElement)) return;

            // Remove from submitting set
            this._submittingForms.delete(form);

            // Reset all submit buttons in the form
            form.querySelectorAll('button[type="submit"], input[type="submit"], button:not([type])').forEach(button => {
                if (button.dataset.submitGuardActive === '1') {
                    this._setButtonLoading(button, false);
                }
            });
        },

        /**
         * Manually reset a specific button
         * @param {HTMLButtonElement|HTMLInputElement} button
         */
        resetButton(button) {
            if (button.dataset.submitGuardActive === '1') {
                this._setButtonLoading(button, false);
            }

            // Also reset the form if we can find it
            const form = button.closest('form');
            if (form) {
                this._submittingForms.delete(form);
            }
        }
    };

    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => FormSubmitGuard.init());
    } else {
        FormSubmitGuard.init();
    }

    // Expose globally for manual control
    window.FormSubmitGuard = FormSubmitGuard;
})();
