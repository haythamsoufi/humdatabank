// Flash Messages Management JavaScript
//
// This file is loaded globally from `templates/core/layout.html`.
// It provides a centralized helper for adding flash-style messages from AJAX flows:
//   window.FlashMessages.add("Message", "success" | "warning" | "danger" | "info")

(function initGlobalFlashMessages() {
    const pending = [];

    function getScrollableContainer() {
        // Backoffice layout uses <main> with overflow-y:auto as the scroll container.
        // Scrolling the window in that layout can cause the "content disappears / blank space" bug.
        const mainElement =
            document.querySelector('main[style*="overflow-y"]') ||
            document.querySelector('main');

        if (mainElement) {
            const computed = window.getComputedStyle(mainElement);
            const overflowY = (computed.overflowY || '').toLowerCase();
            const canScroll = mainElement.scrollHeight > mainElement.clientHeight;
            const isScrollable = (overflowY === 'auto' || overflowY === 'scroll') && canScroll;

            // Even if computed style is inconclusive, fall back to measuring.
            if (isScrollable || canScroll) return mainElement;
        }

        return window;
    }

    function normalizeCategory(category) {
        const c = (category || '').toString().toLowerCase().trim();
        if (c === 'error') return 'danger';
        if (c === 'success' || c === 'warning' || c === 'danger' || c === 'info') return c;
        return 'info';
    }

    function ensureFlashWrapper() {
        // Prefer the standard container from layout.html
        const flashContainer = document.getElementById('flashMessagesContainer');
        let wrapper = flashContainer ? flashContainer.querySelector('.flash-messages') : null;

        if (!wrapper && flashContainer) {
            wrapper = document.createElement('div');
            wrapper.className = 'flash-messages';
            // Check if offline banner is active and apply class accordingly
            const offlineBanner = document.getElementById('auth-offline-status-banner');
            if (offlineBanner && offlineBanner.style.display !== 'none') {
                wrapper.classList.add('offline-banner-active');
            }
            flashContainer.appendChild(wrapper);
        }

        // Fallback: if page doesn't use layout.html for some reason
        if (!wrapper) {
            wrapper = document.querySelector('.flash-messages');
        }
        if (!wrapper) {
            wrapper = document.createElement('div');
            wrapper.className = 'flash-messages';
            // Check if offline banner is active and apply class accordingly
            const offlineBanner = document.getElementById('auth-offline-status-banner');
            if (offlineBanner && offlineBanner.style.display !== 'none') {
                wrapper.classList.add('offline-banner-active');
            }
            document.body.insertBefore(wrapper, document.body.firstChild);
        }

        return wrapper;
    }

    function dismissAlert(alertEl) {
        if (!alertEl) return;
        alertEl.classList.add('fade-out');
        setTimeout(() => {
            if (alertEl && alertEl.parentElement) {
                alertEl.remove();
            }
        }, 300);
    }

    function buildAlertElement(message, category) {
        const categoryClass = normalizeCategory(category);

        const alert = document.createElement('div');
        alert.className = `alert alert-${categoryClass}`;
        alert.setAttribute('role', 'alert');

        const iconDiv = document.createElement('div');
        iconDiv.className = 'alert-icon';

        // Create SVG icons using DOM construction (CSP-safe)
        function createSVGIcon(type) {
            const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
            svg.setAttribute('fill', 'none');
            svg.setAttribute('viewBox', '0 0 24 24');
            svg.setAttribute('stroke-width', type === 'info' ? '2' : '1.5');
            svg.setAttribute('stroke', 'currentColor');
            svg.setAttribute('class', 'w-6 h-6');

            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            path.setAttribute('stroke-linecap', 'round');
            path.setAttribute('stroke-linejoin', 'round');

            if (type === 'success') {
                path.setAttribute('d', 'M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z');
            } else if (type === 'warning') {
                path.setAttribute('d', 'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z');
            } else if (type === 'danger') {
                path.setAttribute('d', 'm9.75 9.75 4.5 4.5m0-4.5-4.5 4.5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z');
            } else { // info
                path.setAttribute('d', 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z');
            }

            svg.appendChild(path);
            return svg;
        }

        iconDiv.appendChild(createSVGIcon(categoryClass));

        const msgSpan = document.createElement('div');
        msgSpan.className = 'alert-message';
        // Security: treat message as plain text to avoid XSS
        msgSpan.textContent = message || '';

        const closeBtn = document.createElement('button');
        closeBtn.className = 'alert-close';
        closeBtn.setAttribute('type', 'button');
        const closeSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        closeSvg.setAttribute('class', 'w-4 h-4');
        closeSvg.setAttribute('fill', 'none');
        closeSvg.setAttribute('stroke', 'currentColor');
        closeSvg.setAttribute('viewBox', '0 0 24 24');
        const closePath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        closePath.setAttribute('stroke-linecap', 'round');
        closePath.setAttribute('stroke-linejoin', 'round');
        closePath.setAttribute('stroke-width', '2');
        closePath.setAttribute('d', 'M6 18L18 6M6 6l12 12');
        closeSvg.appendChild(closePath);
        closeBtn.appendChild(closeSvg);
        closeBtn.addEventListener('click', (e) => {
            e.preventDefault();
            dismissAlert(alert);
            if (window.adjustFABPosition) {
                setTimeout(() => window.adjustFABPosition(), 50);
            }
        });

        alert.appendChild(iconDiv);
        alert.appendChild(msgSpan);
        alert.appendChild(closeBtn);
        return alert;
    }

    function add(message, category = 'info') {
        // If DOM isn't ready yet, queue and flush on DOMContentLoaded
        if (document.readyState === 'loading') {
            pending.push({ message, category });
            return;
        }

        const wrapper = ensureFlashWrapper();
        const alertEl = buildAlertElement(message, category);
        wrapper.appendChild(alertEl);

        // Ensure user sees it
        try {
            const scrollContainer = getScrollableContainer();
            if (scrollContainer !== window) {
                scrollContainer.scrollTo({ top: 0, behavior: 'smooth' });
            } else {
                window.scrollTo({ top: 0, behavior: 'smooth' });
            }
        } catch (_) {
            // no-op
        }

        // Auto-dismiss after 5s (matches global flash behavior)
        setTimeout(() => {
            if (alertEl && alertEl.parentElement) {
                dismissAlert(alertEl);
                if (window.adjustFABPosition) {
                    setTimeout(() => window.adjustFABPosition(), 50);
                }
            }
        }, 5000);

        if (window.adjustFABPosition) {
            setTimeout(() => window.adjustFABPosition(), 50);
        }
    }

    /**
     * Safe wrapper: no-op if add is not available (e.g. script load order).
     * Use this instead of inline "if (FlashMessages && typeof FlashMessages.add === 'function')" checks.
     */
    function addSafe(message, category) {
        if (typeof add === 'function') {
            add(message, category);
        }
    }

    // Expose globally
    window.FlashMessages = window.FlashMessages || {};
    window.FlashMessages.add = add;
    window.FlashMessages.addSafe = addSafe;
    window.FlashMessages.normalizeCategory = normalizeCategory;

    /** Global helper: showFlashMessage(message, category). Use instead of local wrappers. */
    window.showFlashMessage = function (message, category) {
        if (typeof addSafe === 'function') {
            addSafe(message, category || 'info');
        }
    };

    // Flush any queued messages once DOM is ready
    document.addEventListener('DOMContentLoaded', () => {
        if (!pending.length) return;
        const toFlush = pending.splice(0, pending.length);
        toFlush.forEach((m) => add(m.message, m.category));
    });
})();

document.addEventListener('DOMContentLoaded', function() {
    const flashMessagesContainer = document.querySelector('.flash-messages') || (window.FlashMessages && window.FlashMessages.add ? (function(){ return document.querySelector('.flash-messages'); })() : null);
    const aiChatbotFAB = document.getElementById('aiChatbotFAB');

    // Ensure wrapper exists even if there were no server-rendered flashes (so AJAX flashes have a consistent home)
    if (window.FlashMessages && typeof window.FlashMessages.add === 'function') {
        // Calling ensure logic indirectly by adding/removing nothing isn't ideal; just create wrapper if missing.
        const container = document.getElementById('flashMessagesContainer');
        if (container && !container.querySelector('.flash-messages')) {
            const wrapper = document.createElement('div');
            wrapper.className = 'flash-messages';
            container.appendChild(wrapper);
        }
    }

    const getFlashWrapper = () => document.querySelector('#flashMessagesContainer .flash-messages') || document.querySelector('.flash-messages');

    // Function to calculate total height of flash messages
    const calculateFlashMessagesHeight = () => {
        const wrapper = getFlashWrapper();
        if (!wrapper) return 0;
        const messages = wrapper.querySelectorAll('.alert');
        let totalHeight = 0;
        messages.forEach(message => {
            const rect = message.getBoundingClientRect();
            totalHeight += rect.height;
        });
        // Add gaps between messages (0.75rem each)
        if (messages.length > 1) {
            totalHeight += (messages.length - 1) * 12; // 0.75rem = 12px
        }
        return totalHeight;
    };

    /**
     * True when the UI uses the compact corner FAB layout (matches CSS max-width: 768px rules
     * plus common phone-landscape viewports where width > 768 but we must not use the desktop
     * "push FAB up by flash height" path — that left the chatbot misaligned above #mobileMenuFAB).
     */
    const isCompactTouchFabLayout = () => {
        if (window.matchMedia('(max-width: 768px)').matches) return true;
        if (
            window.matchMedia('(orientation: landscape)').matches &&
            window.matchMedia('(max-height: 500px)').matches &&
            window.innerWidth <= 1024
        ) {
            return true;
        }
        return false;
    };

    // Function to adjust FAB position based on flash messages
    const adjustFABPosition = () => {
        if (!aiChatbotFAB) return;

        const messagesHeight = calculateFlashMessagesHeight();
        const baseBottomOffset = 24; // 1.5rem = 24px (desktop push-up math only)
        const extraPadding = 16; // Extra space for visual breathing room
        const isRTL = document.documentElement.getAttribute('dir') === 'rtl';
        const compact = isCompactTouchFabLayout();

        if (messagesHeight > 0) {
            if (compact) {
                // Keep the same bottom inset as #mobileMenuFAB (CSS + safe-area); nudge horizontally only
                aiChatbotFAB.style.removeProperty('bottom');
                if (isRTL) {
                    aiChatbotFAB.style.left = '96px'; // 6rem — clear centered flashes
                    aiChatbotFAB.style.right = 'auto';
                } else {
                    aiChatbotFAB.style.right = '96px';
                    aiChatbotFAB.style.left = 'auto';
                }
            } else {
                // Desktop: push FAB up by the height of messages plus padding
                const newBottom = baseBottomOffset + messagesHeight + extraPadding;
                aiChatbotFAB.style.bottom = `${newBottom}px`;
                if (isRTL) {
                    aiChatbotFAB.style.left = '1.5rem';
                    aiChatbotFAB.style.right = 'auto';
                } else {
                    aiChatbotFAB.style.right = '1.5rem';
                    aiChatbotFAB.style.left = 'auto';
                }
            }

            // Add bounce animation
            aiChatbotFAB.classList.add('pushed-by-messages');

            // Temporarily pause robot personality during bounce
            if (window.RobotPersonality) {
                window.RobotPersonality.pausePersonality();
            }

            setTimeout(() => {
                aiChatbotFAB.classList.remove('pushed-by-messages');

                // Resume robot personality after bounce, with excited expression
                if (window.RobotPersonality) {
                    setTimeout(() => {
                        window.RobotPersonality.resumePersonality();
                        window.RobotPersonality.triggerExpression('excited');
                    }, 200);
                }
            }, 600);
        } else {
            // Drop inline overrides so chatbot.css / responsive.css control bottom + safe-area (same as main menu FAB)
            aiChatbotFAB.style.removeProperty('bottom');
            aiChatbotFAB.style.removeProperty('left');
            aiChatbotFAB.style.removeProperty('right');
        }
    };

    // Make adjustFABPosition globally available
    window.adjustFABPosition = adjustFABPosition;

    // Observer to watch for changes in flash messages
    let flashMessageObserver;
    const wrapperForObserver = getFlashWrapper();
    if (wrapperForObserver) {
        flashMessageObserver = new MutationObserver((mutations) => {
            let shouldUpdate = false;
            let hasSuccessMessage = false;

            mutations.forEach((mutation) => {
                if (mutation.type === 'childList' ||
                    (mutation.type === 'attributes' && mutation.attributeName === 'class')) {
                    shouldUpdate = true;

                    // Check if a success message was added
                    if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                        mutation.addedNodes.forEach(node => {
                            if (node.nodeType === Node.ELEMENT_NODE &&
                                node.classList && node.classList.contains('alert-success')) {
                                hasSuccessMessage = true;
                            }
                        });
                    }
                }
            });

            if (shouldUpdate) {
                // Small delay to ensure DOM updates are complete
                setTimeout(adjustFABPosition, 50);

                // Make robot happy when success messages appear
                if (hasSuccessMessage && window.RobotPersonality && aiChatbotFAB) {
                    setTimeout(() => {
                        window.RobotPersonality.triggerExpression('happy');
                    }, 800);
                }
            }
        });

        flashMessageObserver.observe(wrapperForObserver, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['class']
        });
    }

    // Auto-dismiss flash messages
    const flashMessages = document.querySelectorAll('.alert');
    flashMessages.forEach(function(message) {
        // Set timeout to dismiss message after 5 seconds
        setTimeout(function() {
            message.classList.add('fade-out');
            // Remove the element after animation completes
            setTimeout(function() {
                message.remove();
                // FAB position will be adjusted automatically by the observer
            }, 300);
        }, 5000);
    });

    // Handle manual close button clicks
    document.querySelectorAll('.alert-close').forEach(function(button) {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const alert = this.closest('.alert');
            alert.classList.add('fade-out');
            setTimeout(function() {
                alert.remove();
                // FAB position will be adjusted automatically by the observer
            }, 300);
        });
    });

    // Initial adjustment for any existing flash messages
    if (aiChatbotFAB && getFlashWrapper()) {
        setTimeout(adjustFABPosition, 100);
    }
});
