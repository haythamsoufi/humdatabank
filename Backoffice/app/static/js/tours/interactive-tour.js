/**
 * Interactive Tour System
 *
 * A reusable, multi-step tour system that can guide users through workflows
 * spanning multiple pages. Features include:
 * - Multi-page navigation support
 * - Draggable tooltips
 * - Smart positioning that avoids covering highlighted elements
 * - Click interception to continue tours automatically
 * - Persistent tooltip positions
 *
 * @example
 * // Define a tour
 * InteractiveTour.registerTour('my-tour', {
 *     name: 'My Workflow',
 *     steps: [
 *         {
 *             page: '/page1',
 *             selector: '#button1',
 *             help: 'Click this button to continue',
 *             action: () => window.location.href = '/page2#chatbot-tour=my-tour&step=2',
 *             actionText: 'Continue'
 *         }
 *     ]
 * });
 *
 * // Start the tour
 * InteractiveTour.start('my-tour');
 */

class InteractiveTour {
    constructor() {
        this.currentTour = null;
        this.registeredTours = {};
        this.spotlightTimeout = null;
        this.spotlightRepositionHandler = null;
        this.spotlightEscHandler = null;
        this.spotlightDragHandlers = null;
        this.spotlightClickHandlers = null;
    }

    /**
     * Check if the current language is RTL (right-to-left).
     * Currently supports Arabic.
     *
     * @returns {boolean} - True if RTL language is active
     * @private
     */
    _isRtlLanguage() {
        // Check chatbot's preferred language first
        if (window.humdatabankChatbot && window.humdatabankChatbot.preferredLanguage) {
            return window.humdatabankChatbot.preferredLanguage === 'ar';
        }
        // Fallback to localStorage
        const storedLang = localStorage.getItem('chatbot_language');
        if (storedLang) {
            return storedLang === 'ar';
        }
        // Check document direction
        const htmlDir = document.documentElement.getAttribute('dir');
        return htmlDir === 'rtl';
    }

    /**
     * Register a tour definition
     * @param {string} tourId - Unique identifier for the tour
     * @param {Object} tourConfig - Tour configuration
     * @param {string} tourConfig.name - Display name of the tour
     * @param {Array} tourConfig.steps - Array of step definitions
     */
    registerTour(tourId, tourConfig) {
        if (!tourId || !tourConfig || !tourConfig.steps || !Array.isArray(tourConfig.steps)) {
            console.warn('Invalid tour configuration:', tourId);
            return;
        }

        this.registeredTours[tourId.toLowerCase()] = {
            id: tourId.toLowerCase(),
            name: tourConfig.name || tourId,
            steps: tourConfig.steps
        };
    }

    /**
     * Start a tour
     * @param {string} tourId - The ID of the tour to start
     * @param {number|null} initialStep - Optional 0-based step index to start from (from URL hash)
     */
    start(tourId, initialStep = null) {
        const id = String(tourId || '').trim().toLowerCase();
        if (!id) {
            console.warn('Tour ID is required');
            return;
        }

        const tour = this.registeredTours[id];
        if (!tour || !tour.steps || tour.steps.length === 0) {
            console.warn(`Tour "${id}" not found or has no steps`);
            return;
        }

        // Store tour state
        this.currentTour = {
            id: id,
            name: tour.name,
            steps: tour.steps,
            currentStep: 0
        };

        // Use initialStep if provided (from URL hash), otherwise default to 0
        if (initialStep !== null && initialStep >= 0 && initialStep < tour.steps.length) {
            this.currentTour.currentStep = initialStep;
        }

        // Start the tour
        this._showStep();
    }

    /**
     * Show the current step of the tour
     * @private
     */
    _showStep() {
        if (!this.currentTour) return;

        const tour = this.currentTour;
        const step = tour.steps[tour.currentStep];
        if (!step) {
            this.end();
            return;
        }

        // Check if we're on the correct page
        // Support prefix matching: "/forms/assignment" matches "/forms/assignment/123"
        const currentPath = window.location.pathname;
        if (step.page) {
            const isExactMatch = currentPath === step.page;
            const isPrefixMatch = currentPath.startsWith(step.page + '/');

            if (!isExactMatch && !isPrefixMatch) {
                // Navigate to the correct page
                window.location.href = step.page + `#chatbot-tour=${tour.id}&step=${tour.currentStep + 1}`;
                return;
            }
        }

        // Clear any existing spotlight
        this._clearSpotlight();

        // Show the step
        this._spotlightSelector(step.selector, step.help || '', {
            action: step.action,
            actionText: step.actionText || 'Next',
            showEndTour: true
        });
    }

    /**
     * Advance to a specific step
     * @param {string} tourId - The tour ID (for validation)
     * @param {number} stepNumber - 1-based step number
     */
    advanceStep(tourId, stepNumber) {
        if (!this.currentTour || this.currentTour.id !== tourId.toLowerCase()) return;

        this.currentTour.currentStep = stepNumber - 1; // Convert to 0-based
        this._showStep();
    }

    /**
     * Go back to the previous step
     */
    goBack() {
        if (!this.currentTour) return;

        const tour = this.currentTour;
        if (tour.currentStep <= 0) return; // Already at first step

        // Decrement step
        tour.currentStep--;

        // Get the previous step
        const previousStep = tour.steps[tour.currentStep];
        if (!previousStep) return;

        // Check if we need to navigate to a different page
        const currentPath = window.location.pathname;
        if (previousStep.page) {
            // Use prefix matching - if current path starts with previous step's page, we're on the right page
            const isExactMatch = currentPath === previousStep.page;
            const isPrefixMatch = currentPath.startsWith(previousStep.page + '/');

            if (isExactMatch || isPrefixMatch) {
                // Stay on current page (preserving any ID in the URL), just show previous step
                this._showStep();
            } else {
                // Need to navigate to a different page
                // Use current path if it's a subpath, otherwise use the step's page
                window.location.href = previousStep.page + `#chatbot-tour=${tour.id}&step=${tour.currentStep + 1}`;
            }
        } else {
            // No page specified, just show previous step
            this._showStep();
        }
    }

    /**
     * End the current tour
     * @param {string} tourId - Optional tour ID for validation
     */
    end(tourId) {
        if (tourId && this.currentTour && this.currentTour.id !== tourId.toLowerCase()) return;

        const tourIdToClear = this.currentTour?.id || tourId;

        this._clearSpotlight();
        this.currentTour = null;

        // Clear tour state from localStorage
        try {
            localStorage.removeItem('chatbot_tour_state');
            // Clear stored tooltip position
            if (tourIdToClear) {
                localStorage.removeItem(`chatbot_tooltip_pos_${tourIdToClear}`);
            }
        } catch (_) {}
    }

    /**
     * Check for tour hash in URL and start tour if found
     * @param {boolean} allowDynamic - If true, don't clear hash if tour not registered (allows dynamic registration)
     */
    checkUrlHash(allowDynamic = false) {
        try {
            const hash = window.location.hash || '';

            // Check for tour hash
            const tourMatch = hash.match(/chatbot-tour=([^&]+)/i);
            if (tourMatch) {
                const tourId = decodeURIComponent(tourMatch[1] || '').trim();
                if (tourId) {
                    // Check if tour is registered
                    const tour = this.registeredTours[tourId.toLowerCase()];

                    // If tour not registered and we're allowing dynamic registration,
                    // don't clear hash - let WorkflowTourParser handle it
                    if (!tour && allowDynamic) {
                        console.debug(`Tour "${tourId}" not registered yet, waiting for dynamic registration...`);
                        return false;
                    }

                    // Extract step number from hash BEFORE clearing it
                    const stepMatch = hash.match(/step=(\d+)/i);
                    let initialStep = null;
                    if (stepMatch) {
                        const stepNum = parseInt(stepMatch[1], 10);
                        if (stepNum >= 1) {
                            initialStep = stepNum - 1; // Convert to 0-based index
                        }
                    }

                    // Clear hash to avoid re-running on refresh/back navigation
                    try {
                        window.history.replaceState(null, document.title, window.location.pathname + window.location.search);
                    } catch (_) {}

                    // Delay to allow late-rendered page header/actions to appear
                    setTimeout(() => this.start(tourId, initialStep), 250);
                    return true;
                }
            }
        } catch (_) {}
        return false;
    }

    /**
     * Spotlight an element by selector
     * @param {string} selector - CSS selector for the element to spotlight
     * @param {string} helpText - Help text to display
     * @param {Object} options - Additional options
     * @private
     */
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
    }

    /**
     * Spotlight a specific element
     * @param {HTMLElement} el - Element to spotlight
     * @param {string} helpText - Help text to display
     * @param {Object} options - Additional options
     * @private
     */
    _spotlightElement(el, helpText, options = {}) {
        this._clearSpotlight();

        try {
            // DON'T change z-index or position of the element itself
            // This prevents overlap issues with fixed/sticky elements like pinned bottom bars
            // The element should maintain its natural stacking context
            // Only the helper layer (for dimming) and tooltip need high z-index

            // Apply highlight class (CSS handles visual styling only, no z-index changes)
            el.classList.add('chatbot-spotlight-target');

            // If this is part of a tour and the element is clickable, intercept clicks
            if (this.currentTour) {
                const tour = this.currentTour;
                const currentStep = tour.steps[tour.currentStep];

                // Find clickable element (could be the element itself or a parent link/button)
                let clickableEl = null;
                if (el.tagName === 'A' || el.tagName === 'BUTTON') {
                    clickableEl = el;
                } else {
                    clickableEl = el.closest('a, button');
                }

                if (clickableEl && clickableEl.tagName === 'A') {
                    const originalHref = clickableEl.getAttribute('href');
                    // Only intercept if it's a navigation link and doesn't already have tour hash
                    if (originalHref && !originalHref.includes('chatbot-tour=') && !originalHref.startsWith('#')) {
                        // Store reference to current step for the handler
                        const stepIndex = tour.currentStep;

                        const clickHandler = (e) => {
                            // Check if clicking this link should advance the tour
                            const nextStepIndex = stepIndex + 1;
                            if (nextStepIndex < tour.steps.length) {
                                const nextStep = tour.steps[nextStepIndex];
                                // If the link's destination matches the next step's page, intercept
                                if (nextStep && nextStep.page) {
                                    const linkPath = new URL(originalHref, window.location.origin).pathname;
                                    // Support prefix matching: step page "/forms/assignment" matches link "/forms/assignment/123"
                                    const isExactMatch = linkPath === nextStep.page;
                                    const isPrefixMatch = linkPath.startsWith(nextStep.page + '/');

                                    if (isExactMatch || isPrefixMatch) {
                                        e.preventDefault();
                                        e.stopPropagation();
                                        // Navigate to the actual link destination (not the step's partial page)
                                        // with tour hash to continue tour
                                        window.location.href = linkPath + `#chatbot-tour=${tour.id}&step=${nextStepIndex + 1}`;
                                        return false;
                                    }
                                }
                            }
                        };

                        // Add click handler (use capture phase to intercept early)
                        clickableEl.addEventListener('click', clickHandler, { capture: true });

                        // Store handler for cleanup
                        if (!this.spotlightClickHandlers) {
                            this.spotlightClickHandlers = [];
                        }
                        this.spotlightClickHandlers.push({
                            element: clickableEl,
                            handler: clickHandler
                        });
                    }
                }
            }

            // Function to create and position helper layer
            const createHelperLayer = () => {
                // Create helper layer positioned around the element (like Intro.js does)
                // This creates a cutout effect where the element isn't dimmed
                const helperLayer = document.createElement('div');
                helperLayer.className = 'chatbot-spotlight-helper-layer';
                helperLayer.id = 'chatbotSpotlightHelperLayer';

                // Position helper layer around the element
                const updateHelperLayer = () => {
                    try {
                        // Get fresh bounding rect - this ensures we get the current position
                        const rect = el.getBoundingClientRect();
                        const padding = 4; // Small padding around element

                        helperLayer.style.position = 'fixed';
                        helperLayer.style.top = `${rect.top - padding}px`;
                        helperLayer.style.left = `${rect.left - padding}px`;
                        helperLayer.style.width = `${rect.width + padding * 2}px`;
                        helperLayer.style.height = `${rect.height + padding * 2}px`;
                        helperLayer.style.pointerEvents = 'none';
                        helperLayer.style.zIndex = '2147480000';
                        helperLayer.style.borderRadius = '8px';
                        // Transparent background with huge box-shadow to dim everything else
                        helperLayer.style.background = 'transparent';
                        helperLayer.style.border = '2px solid rgba(197, 48, 48, 0.8)';
                        helperLayer.style.boxShadow = '0 0 0 9999px rgba(0, 0, 0, 0.4)';
                    } catch (_) {}
                };

                // Update on scroll/resize
                const updateHandler = () => updateHelperLayer();

                // Initial positioning - use requestAnimationFrame to ensure DOM is ready
                requestAnimationFrame(() => {
                    updateHelperLayer();
                    document.body.appendChild(helperLayer);

                    // Double-check position after scroll animation completes
                    // Smooth scroll typically takes ~500ms, but we'll check multiple times
                    let checkCount = 0;
                    const maxChecks = 10; // Check for up to 1 second
                    const checkInterval = setInterval(() => {
                        checkCount++;
                        const oldRect = el.getBoundingClientRect();
                        updateHelperLayer();
                        const newRect = el.getBoundingClientRect();

                        // If position hasn't changed significantly, we're done
                        if (checkCount >= maxChecks ||
                            (Math.abs(oldRect.top - newRect.top) < 1 && Math.abs(oldRect.left - newRect.left) < 1)) {
                            clearInterval(checkInterval);
                        }
                    }, 100);
                });

                window.addEventListener('scroll', updateHandler, { passive: true });
                window.addEventListener('resize', updateHandler, { passive: true });

                // Store handler for cleanup
                if (!this.spotlightHelperLayerUpdater) {
                    this.spotlightHelperLayerUpdater = updateHandler;
                }

                // For tours, fade out helper layer after 1.5 seconds
                if (this.currentTour) {
                    helperLayer.classList.add('chatbot-spotlight-helper-layer--temporary');
                    setTimeout(() => {
                        helperLayer.classList.add('chatbot-spotlight-helper-layer--fade-out');
                        // Remove from DOM after fade completes
                        setTimeout(() => {
                            helperLayer.remove();
                            window.removeEventListener('scroll', updateHandler);
                            window.removeEventListener('resize', updateHandler);
                            this.spotlightHelperLayerUpdater = null;
                        }, 300); // Match CSS transition duration
                    }, 1500); // Show for 1.5 seconds
                }
            };

            // Scroll into view first, then create helper layer after scroll completes
            try {
                el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
                // Wait for smooth scroll animation to complete (typically ~500ms)
                // Use multiple checks to ensure position is stable
                setTimeout(() => {
                    createHelperLayer();
                }, 600); // Give enough time for smooth scroll to complete
            } catch (_) {
                // If scrollIntoView fails, create helper layer immediately
                createHelperLayer();
            }

            // Build tooltip content
            const hasAction = options.action && typeof options.action === 'function';
            const showEndTour = options.showEndTour === true;
            const actionText = options.actionText || 'Next';

            // Check if we can go back (for tours)
            const canGoBack = this.currentTour && this.currentTour.currentStep > 0;

            let tooltipContent = `
                <div class="chatbot-spotlight-tooltip__row">
                    <div class="chatbot-spotlight-tooltip__text">${this._escapeHtml(helpText || 'Here it is.')}</div>
                    <button type="button" class="chatbot-spotlight-tooltip__close" aria-label="Close spotlight">×</button>
                </div>
            `;

            if (hasAction || showEndTour || canGoBack) {
                tooltipContent += '<div class="chatbot-spotlight-tooltip__actions">';

                // Next/Action button (primary action, appears on the left)
                if (hasAction) {
                    tooltipContent += `<button type="button" class="chatbot-spotlight-tooltip__action-btn" data-action="next">${this._escapeHtml(actionText)}</button>`;
                }

                // Back and End Tour buttons grouped on the right
                if (canGoBack || showEndTour) {
                    tooltipContent += '<div class="chatbot-spotlight-tooltip__actions-group">';

                    // Back button (only for tours with previous steps)
                    if (canGoBack) {
                        tooltipContent += `<button type="button" class="chatbot-spotlight-tooltip__back-btn" data-action="back">Back</button>`;
                    }

                    // End Tour button
                    if (showEndTour) {
                        tooltipContent += `<button type="button" class="chatbot-spotlight-tooltip__end-tour-btn" data-action="end">End Tour</button>`;
                    }

                    tooltipContent += '</div>';
                }

                tooltipContent += '</div>';
            }

            // Tooltip
            const tip = document.createElement('div');
            tip.id = 'chatbotSpotlightTooltip';
            tip.className = 'chatbot-spotlight-tooltip';
            tip.innerHTML = tooltipContent;

            // Check if RTL language (Arabic) is active
            const isRtl = this._isRtlLanguage();
            if (isRtl) {
                tip.setAttribute('dir', 'rtl');
                tip.classList.add('rtl');
            }

            document.body.appendChild(tip);

            // Check if user has manually positioned this tooltip before (for tours)
            let manualPosition = null;
            if (this.currentTour) {
                const storedPos = localStorage.getItem(`chatbot_tooltip_pos_${this.currentTour.id}`);
                if (storedPos) {
                    try {
                        manualPosition = JSON.parse(storedPos);
                    } catch (_) {}
                }
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
                    const margin = 15; // Increased margin
                    const viewportWidth = window.innerWidth;
                    const viewportHeight = window.innerHeight;

                    // Calculate positions for all 4 sides (top, bottom, left, right)
                    const positions = [
                        // Below element
                        {
                            top: rect.bottom + margin,
                            left: rect.left,
                            side: 'bottom'
                        },
                        // Above element
                        {
                            top: rect.top - tipRect.height - margin,
                            left: rect.left,
                            side: 'top'
                        },
                        // Right of element
                        {
                            top: rect.top,
                            left: rect.right + margin,
                            side: 'right'
                        },
                        // Left of element
                        {
                            top: rect.top,
                            left: rect.left - tipRect.width - margin,
                            side: 'left'
                        }
                    ];

                    // Find the best position that doesn't overlap with the element
                    let bestPos = null;
                    for (const pos of positions) {
                        // Check if this position overlaps with the element
                        const overlaps = (
                            pos.left < rect.right + margin &&
                            pos.left + tipRect.width > rect.left - margin &&
                            pos.top < rect.bottom + margin &&
                            pos.top + tipRect.height > rect.top - margin
                        );

                        // Check if position is within viewport
                        const inViewport = (
                            pos.top >= margin &&
                            pos.left >= margin &&
                            pos.top + tipRect.height <= viewportHeight - margin &&
                            pos.left + tipRect.width <= viewportWidth - margin
                        );

                        if (!overlaps && inViewport) {
                            bestPos = pos;
                            break;
                        }
                    }

                    // If no perfect position found, use the one that overlaps least
                    if (!bestPos) {
                        bestPos = positions[0]; // Default to below
                        // Clamp to viewport
                        bestPos.top = Math.max(margin, Math.min(bestPos.top, viewportHeight - tipRect.height - margin));
                        bestPos.left = Math.max(margin, Math.min(bestPos.left, viewportWidth - tipRect.width - margin));
                    }

                    tip.style.top = `${Math.round(bestPos.top)}px`;
                    tip.style.left = `${Math.round(bestPos.left)}px`;
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

                // Store manual position for tours
                if (this.currentTour) {
                    manualPosition = { left: newLeft, top: newTop };
                    try {
                        localStorage.setItem(`chatbot_tooltip_pos_${this.currentTour.id}`, JSON.stringify(manualPosition));
                    } catch (_) {}
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
            this.spotlightDragHandlers = {
                mousedown: handleMouseDown,
                mousemove: handleMouseMove,
                mouseup: handleMouseUp,
                tip: tip
            };

            // Reposition on resize/scroll (but respect manual position)
            this.spotlightRepositionHandler = () => {
                if (!isDragging && !manualPosition) {
                    positionTip(false);
                }
            };
            window.addEventListener('resize', this.spotlightRepositionHandler, { passive: true });
            window.addEventListener('scroll', this.spotlightRepositionHandler, { passive: true });

            // Close handlers
            tip.querySelector('.chatbot-spotlight-tooltip__close')?.addEventListener('click', () => {
                if (this.currentTour) {
                    this.end();
                } else {
                    this._clearSpotlight();
                }
            });

            // Back button handler (for tours)
            if (canGoBack) {
                tip.querySelector('.chatbot-spotlight-tooltip__back-btn')?.addEventListener('click', () => {
                    this.goBack();
                });
            }

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
                    this.end();
                });
            }

            this.spotlightEscHandler = (evt) => {
                if (evt && evt.key === 'Escape') {
                    if (this.currentTour) {
                        this.end();
                    } else {
                        this._clearSpotlight();
                    }
                }
            };
            window.addEventListener('keydown', this.spotlightEscHandler);

            // Auto-clear after a while so the UI doesn't stay "stuck" (only for single spotlights, not tours)
            if (!this.currentTour) {
                this.spotlightTimeout = setTimeout(() => this._clearSpotlight(), 15000);
            }
        } catch (e) {
            console.warn('Failed to spotlight element:', e);
            this._clearSpotlight();
        }
    }

    /**
     * Clear the current spotlight
     * @private
     */
    _clearSpotlight() {
        try {
            if (this.spotlightTimeout) {
                clearTimeout(this.spotlightTimeout);
                this.spotlightTimeout = null;
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
            if (this.spotlightRepositionHandler) {
                window.removeEventListener('resize', this.spotlightRepositionHandler);
                window.removeEventListener('scroll', this.spotlightRepositionHandler);
                this.spotlightRepositionHandler = null;
            }
            if (this.spotlightEscHandler) {
                window.removeEventListener('keydown', this.spotlightEscHandler);
                this.spotlightEscHandler = null;
            }
            // Clean up drag handlers
            if (this.spotlightDragHandlers) {
                const tip = this.spotlightDragHandlers.tip;
                if (tip) {
                    tip.removeEventListener('mousedown', this.spotlightDragHandlers.mousedown);
                }
                document.removeEventListener('mousemove', this.spotlightDragHandlers.mousemove);
                document.removeEventListener('mouseup', this.spotlightDragHandlers.mouseup);
                this.spotlightDragHandlers = null;
            }
            // Clean up click intercept handlers
            if (this.spotlightClickHandlers) {
                this.spotlightClickHandlers.forEach(({ element, handler }) => {
                    try {
                        element.removeEventListener('click', handler, { capture: true });
                    } catch (_) {}
                });
                this.spotlightClickHandlers = null;
            }
            // Clean up helper layer updater
            if (this.spotlightHelperLayerUpdater) {
                window.removeEventListener('scroll', this.spotlightHelperLayerUpdater);
                window.removeEventListener('resize', this.spotlightHelperLayerUpdater);
                this.spotlightHelperLayerUpdater = null;
            }
            // Remove helper layer
            try {
                const helperLayer = document.getElementById('chatbotSpotlightHelperLayer');
                if (helperLayer) {
                    helperLayer.remove();
                }
            } catch (_) {}
            // Reset any styles on highlighted elements
            try {
                document.querySelectorAll('.chatbot-spotlight-target').forEach((n) => {
                    n.style.filter = '';
                    // No z-index or position to restore - we don't modify them
                });
            } catch (_) {}
        } catch (_) {}
    }


    /**
     * Escape HTML to prevent XSS
     * @param {string} text - Text to escape
     * @returns {string} Escaped HTML
     * @private
     */
    _escapeHtml(text) {
        if (typeof text !== 'string') return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Create singleton instance
const interactiveTour = new InteractiveTour();

// Make globally available
window.InteractiveTour = interactiveTour;

// Auto-check URL hash on page load
// Use allowDynamic=true to let WorkflowTourParser handle unregistered tours
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        interactiveTour.checkUrlHash(true);
    });
} else {
    interactiveTour.checkUrlHash(true);
}
