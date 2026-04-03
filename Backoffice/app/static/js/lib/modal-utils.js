/**
 * Centralized modal open/close utilities for Backoffice.
 * Wires existing modal elements with Escape key, backdrop click, and close buttons.
 *
 * Usage:
 *   const { openModal, closeModal, isOpen } = ModalUtils.makeModal('#my-modal', {
 *     closeSelector: '.close-modal, .close-modal-btn',
 *     onClose: () => { },
 *     onOpen: () => { }
 *   });
 */
(function() {
    'use strict';

    const HIDDEN_CLASS = 'hidden';

    /**
     * Wire an existing modal element for open/close with Escape and backdrop click.
     *
     * @param {HTMLElement|string} modalOrSelector - Modal element or CSS selector
     * @param {Object} [options]
     * @param {string} [options.closeSelector='.close-modal, .close-modal-btn'] - Selector for close buttons (scoped to modal)
     * @param {function} [options.onClose] - Called when closing, before adding hidden
     * @param {function} [options.onOpen] - Called when opening, after removing hidden
     * @returns {{ openModal: function, closeModal: function, isOpen: function }}
     */
    function makeModal(modalOrSelector, options = {}) {
        const modal = typeof modalOrSelector === 'string'
            ? document.querySelector(modalOrSelector)
            : modalOrSelector;
        if (!modal) {
            return {
                openModal: function() {},
                closeModal: function() {},
                isOpen: function() { return false; }
            };
        }

        const {
            closeSelector = '.close-modal, .close-modal-btn',
            onClose,
            onOpen
        } = options;

        let escapeHandler = null;

        function closeModal() {
            if (modal.classList.contains(HIDDEN_CLASS)) return;
            if (typeof onClose === 'function') onClose();
            modal.classList.add(HIDDEN_CLASS);
            if (escapeHandler) {
                document.removeEventListener('keydown', escapeHandler);
                escapeHandler = null;
            }
        }

        function openModal() {
            modal.classList.remove(HIDDEN_CLASS);
            if (typeof onOpen === 'function') onOpen();
            if (!escapeHandler) {
                escapeHandler = function(e) {
                    if (e.key === 'Escape' && !modal.classList.contains(HIDDEN_CLASS)) closeModal();
                };
                document.addEventListener('keydown', escapeHandler);
            }
        }

        function isOpen() {
            return modal && !modal.classList.contains(HIDDEN_CLASS);
        }

        // Wire close buttons
        modal.querySelectorAll(closeSelector).forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                closeModal();
            });
        });

        // Backdrop click (click on modal overlay, not inner content)
        modal.addEventListener('click', function(e) {
            if (e.target === modal) closeModal();
        });

        return { openModal, closeModal, isOpen };
    }

    if (typeof window !== 'undefined') {
        window.ModalUtils = { makeModal };
    }
})();
