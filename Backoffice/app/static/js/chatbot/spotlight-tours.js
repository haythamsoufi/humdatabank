/**
 * Chatbot SpotlightTours module
 * @module chatbot/spotlight-tours
 */

export const SpotlightToursMixin = {
    _preloadCommonWorkflowToursOnce() {
        /**
         * Lazily warm the InteractiveTour cache for a few common workflows.
         *
         * Previously this ran unconditionally whenever the AI chat FAB was present
         * on the page (i.e. on every admin page navigation for AI-beta users), firing
         * 3 background API calls each time regardless of whether the chatbot was ever
         * opened. Most sessions never open it, so this was pure waste and a source of
         * avoidable load on Gunicorn workers.
         *
         * Now it only runs the first time the chat widget is actually opened
         * (see widget-ui.js#toggleChat), and only once per browser tab via a
         * sessionStorage flag. workflow-tour-parser.js further caches the fetched
         * tour JSON in localStorage, so repeat visits skip the network entirely
         * until the app is redeployed (ASSET_VERSION bump) or the cache expires.
         */
        if (this._toursPreloadTriggered) return;
        this._toursPreloadTriggered = true;

        let alreadyPreloaded = false;
        try {
            alreadyPreloaded = sessionStorage.getItem('humdb:chatTours:preloaded') === '1';
        } catch (_) {
            // sessionStorage unavailable (private mode, etc.) - fall through and preload anyway
        }
        if (alreadyPreloaded) return;

        if (typeof window.InteractiveTour === 'undefined' || !window.InteractiveTour.registerTour) {
            // InteractiveTour not loaded yet, wait for it
            const retry = () => {
                this._toursPreloadTriggered = false;
                this._preloadCommonWorkflowToursOnce();
            };
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', retry);
            } else {
                setTimeout(retry, 100);
            }
            return;
        }

        if (!window.WorkflowTourParser) return;

        // Tours are fetched from workflow documentation (static/CDN first, API fallback)
        const commonWorkflows = ['add-user', 'submit-data', 'view-assignments'];
        window.WorkflowTourParser.preloadWorkflows(commonWorkflows)
            .then(() => {
                try { sessionStorage.setItem('humdb:chatTours:preloaded', '1'); } catch (_) {}
            })
            .catch(e => {
                console.debug('Failed to preload workflows:', e);
            });
    },

    _getSpotlightTooltipPosition(tourId) {
        try {
            const raw = localStorage.getItem('chatbot_tooltip_positions');
            const list = raw ? JSON.parse(raw) : [];
            let item = list.find(entry => entry.id === tourId);
            if (!item) {
                const legacy = localStorage.getItem('chatbot_tooltip_pos_' + tourId);
                if (legacy) {
                    const pos = JSON.parse(legacy);
                    this._setSpotlightTooltipPosition(tourId, pos);
                    try { localStorage.removeItem('chatbot_tooltip_pos_' + tourId); } catch (_) {}
                    return pos;
                }
            }
            return item ? item.pos : null;
        } catch (_) {
            return null;
        }
    },

    _setSpotlightTooltipPosition(tourId, pos) {
        try {
            const raw = localStorage.getItem('chatbot_tooltip_positions');
            const list = raw ? JSON.parse(raw) : [];
            const filtered = list.filter(entry => entry.id !== tourId);
            filtered.push({ id: tourId, pos });
            const trimmed = filtered.slice(-10);
            localStorage.setItem('chatbot_tooltip_positions', JSON.stringify(trimmed));
        } catch (_) {}
    },

    runSpotlightFromHash() {
        /**
         * Supports deep-links that trigger a lightweight spotlight or multi-step tour, e.g.:
         *   /admin/users#chatbot-spotlight=add-new-user (single spotlight)
         *   /admin/users#chatbot-tour=add-user (multi-step tour)
         */
        try {
            const hash = window.location.hash || '';

            // Check for tour first (multi-step) - delegate to InteractiveTour
            const tourMatch = hash.match(/chatbot-tour=([^&]+)/i);
            if (tourMatch) {
                // InteractiveTour will handle this via checkUrlHash()
                // Use allowDynamic=true so WorkflowTourParser can register dynamic tours
                if (window.InteractiveTour && typeof window.InteractiveTour.checkUrlHash === 'function') {
                    window.InteractiveTour.checkUrlHash(true);
                    return;
                }
            }

            // Check for single spotlight (still handled by chatbot)
            const spotlightMatch = hash.match(/chatbot-spotlight=([^&]+)/i);
            if (spotlightMatch) {
                const spotlightId = decodeURIComponent(spotlightMatch[1] || '').trim();
                if (spotlightId) {
                    // Clear hash to avoid re-running on refresh/back navigation.
                    try {
                        window.history.replaceState(null, document.title, window.location.pathname + window.location.search);
                    } catch (_) {}

                    // Delay to allow late-rendered page header/actions to appear.
                    setTimeout(() => this.spotlightById(spotlightId), 250);
                }
            }
        } catch (_) {}
    },

    spotlightById(spotlightId) {
        const id = String(spotlightId || '').trim().toLowerCase();
        if (!id) return;

        // Map spotlight IDs to selectors + helper copy.
        const map = {
            'add-new-user': {
                selector: 'a[href="/admin/users/new"]',
                help: 'Click “Add New User” to create a new account.',
            },
        };

        const cfg = map[id];
        if (!cfg || !cfg.selector) return;

        this._spotlightSelector(cfg.selector, cfg.help || '');
    },

    _spotlightSelector(selector, helpText, options = {}) {
        // Retry briefly in case the DOM renders late (AG Grid, macros, etc.)
        const maxAttempts = 30;
        const delayMs = 200;

        const attempt = (n) => {
            const el = document.querySelector(selector);
            if (el) {
                this._spotlightElement(el, helpText, options);
                return;
            }
            if (n >= maxAttempts) return;
            setTimeout(() => attempt(n + 1), delayMs);
        };

        attempt(0);
    },

    _spotlightElement(el, helpText, options = {}) {
        this._clearSpotlight();

        try {
            // Check if we're in a tour (declare once at the top)
            const currentTour = (window.InteractiveTour && window.InteractiveTour.currentTour) || this._currentTour;

            // Scroll into view
            try {
                el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
            } catch (_) {}

            // Apply highlight class
            el.classList.add('chatbot-spotlight-target');

            // Click interception for tours is now handled by InteractiveTour
            // Single spotlights (non-tour) don't need click interception

            // Skip backdrop for tours (no dimming) - only add for single spotlights
            if (!currentTour) {
                // Add a subtle backdrop (does not block clicks) for single spotlights only
                const backdrop = document.createElement('div');
                backdrop.id = 'chatbotSpotlightBackdrop';
                backdrop.className = 'chatbot-spotlight-backdrop';
                document.body.appendChild(backdrop);
            }

            // Build tooltip content
            const hasAction = options.action && typeof options.action === 'function';
            const showEndTour = options.showEndTour === true;
            const actionText = options.actionText || 'Next';

            let tooltipContent = `
                <div class="chatbot-spotlight-tooltip__row">
                    <div class="chatbot-spotlight-tooltip__text">${this.escapeHtml(helpText || 'Here it is.')}</div>
                    <button type="button" class="chatbot-spotlight-tooltip__close" aria-label="Close spotlight">×</button>
                </div>
            `;

            if (hasAction || showEndTour) {
                tooltipContent += '<div class="chatbot-spotlight-tooltip__actions">';
                if (hasAction) {
                    tooltipContent += `<button type="button" class="chatbot-spotlight-tooltip__action-btn" data-action="next">${this.escapeHtml(actionText)}</button>`;
                }
                if (showEndTour) {
                    const endTourText = this.escapeHtml(this._uiString('endTour') || 'End Tour');
                    tooltipContent += `<button type="button" class="chatbot-spotlight-tooltip__end-tour-btn" data-action="end">${endTourText}</button>`;
                }
                tooltipContent += '</div>';
            }

            // Tooltip
            const tip = document.createElement('div');
            tip.id = 'chatbotSpotlightTooltip';
            tip.className = 'chatbot-spotlight-tooltip';
            tip.innerHTML = tooltipContent;
            document.body.appendChild(tip);

            // Check if user has manually positioned this tooltip before (for tours)
            let manualPosition = null;
            if (currentTour) {
                const tourId = currentTour.id || (currentTour.id || '');
                manualPosition = this._getSpotlightTooltipPosition(tourId);
            }

            const positionTip = (useManualPos = false) => {
                try {
                    // If user manually positioned, use that (unless forced to recalculate)
                    if (useManualPos && manualPosition) {
                        tip.style.top = `${manualPosition.top}px`;
                        tip.style.left = `${manualPosition.left}px`;
                        return;
                    }

                    const rect = el.getBoundingClientRect();
                    const tipRect = tip.getBoundingClientRect();
                    const margin = 12;
                    const viewportWidth = window.innerWidth;
                    const viewportHeight = window.innerHeight;

                    const clamp = (v, min, max) => Math.max(min, Math.min(v, max));
                    const maxLeft = Math.max(margin, viewportWidth - tipRect.width - margin);
                    const maxTop = Math.max(margin, viewportHeight - tipRect.height - margin);

                    const centeredLeft = rect.left + (rect.width - tipRect.width) / 2;
                    const centeredTop = rect.top + (rect.height - tipRect.height) / 2;

                    // Candidate positions (prefer bottom, then top, then right/left), but score them
                    // so we keep the tooltip close to the target and avoid overlap when possible.
                    const candidates = [
                        { top: rect.bottom + margin, left: centeredLeft, side: 'bottom' },
                        { top: rect.top - tipRect.height - margin, left: centeredLeft, side: 'top' },
                        { top: centeredTop, left: rect.right + margin, side: 'right' },
                        { top: centeredTop, left: rect.left - tipRect.width - margin, side: 'left' },
                    ];

                    const inflatedTarget = {
                        left: rect.left - margin,
                        right: rect.right + margin,
                        top: rect.top - margin,
                        bottom: rect.bottom + margin,
                    };

                    const intersectionArea = (a, b) => {
                        const x = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
                        const y = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
                        return x * y;
                    };

                    let best = null;
                    let bestScore = Infinity;

                    for (const c of candidates) {
                        const clampedLeft = clamp(c.left, margin, maxLeft);
                        const clampedTop = clamp(c.top, margin, maxTop);

                        const tipBox = {
                            left: clampedLeft,
                            right: clampedLeft + tipRect.width,
                            top: clampedTop,
                            bottom: clampedTop + tipRect.height,
                        };

                        const overlap = intersectionArea(tipBox, inflatedTarget);
                        const moved = Math.abs(clampedLeft - c.left) + Math.abs(clampedTop - c.top);

                        // Strongly prefer not overlapping; secondarily keep it close to the ideal anchor.
                        const score = overlap * 1000 + moved;

                        if (score < bestScore) {
                            bestScore = score;
                            best = { left: clampedLeft, top: clampedTop, side: c.side };
                        }
                    }

                    tip.style.top = `${Math.round((best && best.top) || margin)}px`;
                    tip.style.left = `${Math.round((best && best.left) || margin)}px`;
                } catch (_) {}
            };

            // First position after it renders
            setTimeout(() => positionTip(!!manualPosition), 0);

            // Make tooltip draggable
            let isDragging = false;
            let dragStartX = 0;
            let dragStartY = 0;
            let dragStartLeft = 0;
            let dragStartTop = 0;

            const handleMouseDown = (e) => {
                // Don't start drag if clicking on buttons or close button
                if (e.target.closest('button') || e.target.closest('.chatbot-spotlight-tooltip__close')) {
                    return;
                }

                isDragging = true;
                const rect = tip.getBoundingClientRect();
                dragStartX = e.clientX;
                dragStartY = e.clientY;
                dragStartLeft = rect.left;
                dragStartTop = rect.top;

                tip.classList.add('chatbot-spotlight-tooltip--dragging');
                tip.style.cursor = 'grabbing';

                e.preventDefault();
            };

            const handleMouseMove = (e) => {
                if (!isDragging) return;

                const deltaX = e.clientX - dragStartX;
                const deltaY = e.clientY - dragStartY;

                let newLeft = dragStartLeft + deltaX;
                let newTop = dragStartTop + deltaY;

                // Clamp to viewport
                const tipRect = tip.getBoundingClientRect();
                const margin = 10;
                newLeft = Math.max(margin, Math.min(newLeft, window.innerWidth - tipRect.width - margin));
                newTop = Math.max(margin, Math.min(newTop, window.innerHeight - tipRect.height - margin));

                tip.style.left = `${newLeft}px`;
                tip.style.top = `${newTop}px`;

                // Store manual position for tours (max 10 entries)
                if (currentTour) {
                    const tourId = currentTour.id || '';
                    manualPosition = { left: newLeft, top: newTop };
                    this._setSpotlightTooltipPosition(tourId, manualPosition);
                }
            };

            const handleMouseUp = () => {
                if (isDragging) {
                    isDragging = false;
                    tip.classList.remove('chatbot-spotlight-tooltip--dragging');
                    tip.style.cursor = '';
                }
            };

            // Add drag handlers
            tip.addEventListener('mousedown', handleMouseDown);
            document.addEventListener('mousemove', handleMouseMove);
            document.addEventListener('mouseup', handleMouseUp);

            // Store handlers for cleanup
            this._spotlightDragHandlers = {
                mousedown: handleMouseDown,
                mousemove: handleMouseMove,
                mouseup: handleMouseUp
            };

            // Reposition on resize/scroll (but respect manual position)
            this._spotlightRepositionHandler = () => {
                if (!isDragging && !manualPosition) {
                    positionTip(false);
                }
            };
            window.addEventListener('resize', this._spotlightRepositionHandler, { passive: true });
            window.addEventListener('scroll', this._spotlightRepositionHandler, { passive: true });

            // Close handlers
            tip.querySelector('.chatbot-spotlight-tooltip__close')?.addEventListener('click', () => {
                if (currentTour) {
                    if (window.InteractiveTour && typeof window.InteractiveTour.end === 'function') {
                        window.InteractiveTour.end();
                    } else {
                        this._endTour();
                    }
                } else {
                    this._clearSpotlight();
                }
            });

            // Action button handler
            if (hasAction) {
                tip.querySelector('.chatbot-spotlight-tooltip__action-btn')?.addEventListener('click', () => {
                    if (options.action) {
                        options.action();
                    }
                });
            }

            // End tour button handler
            if (showEndTour) {
                tip.querySelector('.chatbot-spotlight-tooltip__end-tour-btn')?.addEventListener('click', () => {
                    if (window.InteractiveTour && typeof window.InteractiveTour.end === 'function') {
                        window.InteractiveTour.end();
                    } else {
                        this._endTour();
                    }
                });
            }

            this._spotlightEscHandler = (evt) => {
                if (evt && evt.key === 'Escape') {
                    if (currentTour) {
                        if (window.InteractiveTour && typeof window.InteractiveTour.end === 'function') {
                            window.InteractiveTour.end();
                        } else {
                            this._endTour();
                        }
                    } else {
                        this._clearSpotlight();
                    }
                }
            };
            window.addEventListener('keydown', this._spotlightEscHandler);

            // Auto-clear after a while so the UI doesn't stay "stuck" (only for single spotlights, not tours)
            if (!currentTour) {
                this._spotlightTimeout = setTimeout(() => this._clearSpotlight(), 15000);
            }
        } catch (e) {
            console.warn('Failed to spotlight element:', e);
            this._clearSpotlight();
        }
    },

    startTour(tourId, initialStep = null) {
        /**
         * Start a multi-step tour - delegates to InteractiveTour system
         * @param {string} tourId - The ID of the tour to start
         * @param {number|null} initialStep - Optional 0-based step index to start from
         */
        if (window.InteractiveTour && typeof window.InteractiveTour.start === 'function') {
            window.InteractiveTour.start(tourId, initialStep);
        } else {
            console.warn('InteractiveTour not available');
        }
    },

    _showTourStep() {
        // Delegated to InteractiveTour - kept for compatibility
        if (window.InteractiveTour && window.InteractiveTour.currentTour) {
            // Tour is managed by InteractiveTour
            return;
        }
    },

    _advanceTourStep(tourId, stepNumber) {
        /**
         * Advance to a specific step - delegates to InteractiveTour
         */
        if (window.InteractiveTour && typeof window.InteractiveTour.advanceStep === 'function') {
            window.InteractiveTour.advanceStep(tourId, stepNumber);
        }
    },

    _endTour(tourId) {
        /**
         * End the current tour - delegates to InteractiveTour
         */
        if (window.InteractiveTour && typeof window.InteractiveTour.end === 'function') {
            window.InteractiveTour.end(tourId);
        }
    },

    _clearSpotlight() {
        try {
            if (this._spotlightTimeout) {
                clearTimeout(this._spotlightTimeout);
                this._spotlightTimeout = null;
            }
        } catch (_) {}

        try {
            document.querySelectorAll('.chatbot-spotlight-target').forEach((n) => n.classList.remove('chatbot-spotlight-target'));
        } catch (_) {}

        try {
            document.getElementById('chatbotSpotlightBackdrop')?.remove();
            document.getElementById('chatbotSpotlightTooltip')?.remove();
        } catch (_) {}

        try {
            if (this._spotlightRepositionHandler) {
                window.removeEventListener('resize', this._spotlightRepositionHandler);
                window.removeEventListener('scroll', this._spotlightRepositionHandler);
                this._spotlightRepositionHandler = null;
            }
            if (this._spotlightEscHandler) {
                window.removeEventListener('keydown', this._spotlightEscHandler);
                this._spotlightEscHandler = null;
            }
            // Clean up drag handlers
            if (this._spotlightDragHandlers) {
                const tip = document.getElementById('chatbotSpotlightTooltip');
                if (tip) {
                    tip.removeEventListener('mousedown', this._spotlightDragHandlers.mousedown);
                }
                document.removeEventListener('mousemove', this._spotlightDragHandlers.mousemove);
                document.removeEventListener('mouseup', this._spotlightDragHandlers.mouseup);
                this._spotlightDragHandlers = null;
            }
            // Clean up click intercept handlers
            if (this._spotlightClickHandlers) {
                this._spotlightClickHandlers.forEach(({ element, handler }) => {
                    try {
                        element.removeEventListener('click', handler, { capture: true });
                    } catch (_) {}
                });
                this._spotlightClickHandlers = null;
            }
        } catch (_) {}
    },
    // AI service integration method
    // Routes requests through the backend API (OpenAI-only).
};
