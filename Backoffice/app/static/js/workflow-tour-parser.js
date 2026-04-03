/**
 * Workflow Tour Parser
 *
 * Parses chatbot responses containing workflow data and dynamically registers
 * interactive tours with the InteractiveTour system.
 *
 * This enables LLM-generated workflow guides to be executed as step-by-step
 * interactive tours that highlight UI elements.
 *
 * Debug Logging:
 * - By default, debug logging is disabled
 * - To enable: window.WorkflowTourParser.setDebug(true)
 * - To disable: window.WorkflowTourParser.setDebug(false)
 * - Or set localStorage: localStorage.setItem('ngodb:debug:workflow-tour', '1')
 * - Or set global: window.WORKFLOW_TOUR_DEBUG = true (before script loads)
 */

class WorkflowTourParser {
    constructor() {
        this.registeredWorkflows = new Set();
        // Cache tours by "workflowId:language" key for multi-language support
        this.tourCache = {};
        // Debug logging flag - can be controlled via localStorage or global variable
        this._debugEnabled = this._getDebugFlag();
    }

    /**
     * Get debug flag from localStorage or global variable.
     *
     * @returns {boolean} - True if debug logging is enabled
     */
    _getDebugFlag() {
        try {
            // Check localStorage first
            const stored = localStorage.getItem('ngodb:debug:workflow-tour');
            if (stored !== null) {
                return stored === '1' || stored === 'true';
            }
            // Check global variable
            if (typeof window !== 'undefined' && window.WORKFLOW_TOUR_DEBUG !== undefined) {
                return Boolean(window.WORKFLOW_TOUR_DEBUG);
            }
        } catch (e) {
            // localStorage might not be available
        }
        // Default to disabled
        return false;
    }

    /**
     * Enable or disable debug logging.
     *
     * @param {boolean} enabled - Whether to enable debug logging
     */
    setDebug(enabled) {
        this._debugEnabled = Boolean(enabled);
        try {
            localStorage.setItem('ngodb:debug:workflow-tour', enabled ? '1' : '0');
        } catch (e) {
            // localStorage might not be available
        }
        console.log(`[WorkflowTourParser] Debug logging ${enabled ? 'enabled' : 'disabled'}`);
    }

    /**
     * Check if debug logging is enabled.
     *
     * @returns {boolean} - True if debug logging is enabled
     */
    isDebugEnabled() {
        return this._debugEnabled;
    }

    /**
     * Conditional log method - only logs if debug is enabled.
     *
     * @param {...any} args - Arguments to pass to console.log
     */
    _log(...args) {
        if (this._debugEnabled) {
            console.log(...args);
        }
    }

    /**
     * Conditional warn method - only logs if debug is enabled.
     *
     * @param {...any} args - Arguments to pass to console.warn
     */
    _warn(...args) {
        if (this._debugEnabled) {
            console.warn(...args);
        }
    }

    /**
     * Get the user's preferred language from the chatbot.
     * Falls back to 'en' if not available.
     *
     * @returns {string} - Language code (e.g., 'en', 'fr', 'ar', 'es')
     */
    getUserLanguage() {
        // Try to get language from chatbot instance
        if (window.ngodbChatbot && window.ngodbChatbot.preferredLanguage) {
            return window.ngodbChatbot.preferredLanguage;
        }
        // Fallback to localStorage
        const stored = localStorage.getItem('chatbot_language');
        if (stored) {
            return stored;
        }
        // Default to English
        return 'en';
    }

    /**
     * Get cache key for a workflow in a specific language.
     *
     * @param {string} workflowId - The workflow identifier
     * @param {string} language - The language code
     * @returns {string} - Cache key
     */
    getCacheKey(workflowId, language) {
        return `${workflowId}:${language}`;
    }

    /**
     * Parse a chatbot response for workflow/tour data.
     * Looks for tour trigger links and data attributes.
     *
     * @param {string} responseHtml - The HTML response from chatbot
     * @returns {Object|null} - Parsed workflow data or null
     */
    parseResponse(responseHtml) {
        if (!responseHtml || typeof responseHtml !== 'string') {
            return null;
        }

        // Look for tour trigger links with workflow data
        const tourLinkPattern = /chatbot-tour=([a-zA-Z0-9-]+)/;
        const match = responseHtml.match(tourLinkPattern);

        if (match) {
            const workflowId = match[1];
            return {
                type: 'tour_trigger',
                workflowId: workflowId
            };
        }

        return null;
    }

    /**
     * Fetch workflow tour configuration from the API.
     *
     * @param {string} workflowId - The workflow identifier
     * @returns {Promise<Object|null>} - Tour configuration or null
     */
    async fetchTourConfig(workflowId) {
        const language = this.getUserLanguage();
        const cacheKey = this.getCacheKey(workflowId, language);

        this._log(`[WorkflowTourParser] Fetching tour config for: ${workflowId} (lang: ${language})`);

        // Check cache first (language-aware)
        if (this.tourCache[cacheKey]) {
            this._log(`[WorkflowTourParser] Found in cache for ${language}`);
            return this.tourCache[cacheKey];
        }

        try {
            // Include language parameter in the API request
            const url = `/api/ai/documents/workflows/${workflowId}/tour?lang=${encodeURIComponent(language)}`;
            this._log(`[WorkflowTourParser] Fetching from: ${url}`);

            const fn = (window.getFetch && window.getFetch()) || fetch;
            const response = await fn(url, {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin'
            });

            this._log(`[WorkflowTourParser] Response status: ${response.status}`);

            if (!response.ok) {
                this._warn(`[WorkflowTourParser] Failed to fetch tour for ${workflowId}: ${response.status}`);
                return null;
            }

            const contentType = (response.headers.get('Content-Type') || '').toLowerCase();
            const text = await response.text();
            if (!contentType.includes('application/json') || !text.trim().startsWith('{')) {
                this._warn(`[WorkflowTourParser] Tour API returned non-JSON (e.g. login page) for ${workflowId}`);
                return null;
            }

            let data;
            try {
                data = JSON.parse(text);
            } catch (parseError) {
                this._warn(`[WorkflowTourParser] Invalid JSON for ${workflowId}:`, parseError);
                return null;
            }

            const actualLanguage = data.language || 'en';
            this._log(`[WorkflowTourParser] Response data (lang: ${actualLanguage}):`, data);

            if (data.success && data.tour) {
                // Cache with the actual language returned (may differ if translation not available)
                const actualCacheKey = this.getCacheKey(workflowId, actualLanguage);
                this.tourCache[actualCacheKey] = data.tour;

                // Also cache with requested language if different (to avoid refetching)
                if (actualLanguage !== language) {
                    this.tourCache[cacheKey] = data.tour;
                }

                return data.tour;
            }

            this._warn(`[WorkflowTourParser] Tour data not found in response`);
            return null;
        } catch (error) {
            this._warn(`[WorkflowTourParser] Error fetching tour config for ${workflowId}:`, error);
            return null;
        }
    }

    /**
     * Build InteractiveTour step configuration from API response.
     *
     * @param {string} workflowId - The workflow identifier
     * @param {Array} steps - Array of step objects from API
     * @returns {Object} - Tour configuration for InteractiveTour.registerTour
     */
    buildTourConfig(workflowId, steps) {
        if (!steps || !Array.isArray(steps) || steps.length === 0) {
            return null;
        }

        const tourSteps = steps.map((step, index) => {
            const isLastStep = index === steps.length - 1;
            const nextStep = index + 1;

            return {
                page: step.page || window.location.pathname,
                selector: step.selector,
                help: step.help,
                action: isLastStep
                    ? () => {
                        if (window.InteractiveTour) {
                            window.InteractiveTour.end(workflowId);
                        }
                    }
                    : () => {
                        // Navigate to next step
                        const nextStepData = steps[nextStep];
                        const currentPath = window.location.pathname;

                        if (nextStepData && nextStepData.page) {
                            // Check if we're already on a matching page (exact or prefix match)
                            const isExactMatch = currentPath === nextStepData.page;
                            const isPrefixMatch = currentPath.startsWith(nextStepData.page + '/');
                            const isAlreadyOnPage = isExactMatch || isPrefixMatch;

                            if (isAlreadyOnPage) {
                                // Already on correct page, just advance step
                                if (window.InteractiveTour) {
                                    window.InteractiveTour.advanceStep(workflowId, nextStep + 1);
                                }
                            } else {
                                // Need to navigate - but only if next page looks like a complete URL
                                // Don't navigate to partial paths like "/forms/assignment" that need an ID
                                const looksLikePartialPath = /\/(assignment|user|template)$/.test(nextStepData.page);
                                if (looksLikePartialPath) {
                                    // Can't auto-navigate to partial path
                                    // User must click the highlighted element to navigate
                                    // Show a brief hint
                                    const tooltip = document.querySelector('.chatbot-spotlight-tooltip');
                                    if (tooltip) {
                                        const helpText = tooltip.querySelector('.tooltip-text, p');
                                        if (helpText) {
                                            const originalText = helpText.textContent;
                                            helpText.innerHTML = '<strong style="color: #dc2626;">👆 Click on the highlighted element above to continue</strong>';
                                            setTimeout(() => {
                                                helpText.textContent = originalText;
                                            }, 3000);
                                        }
                                    }
                                    // Don't advance - user must click the actual link
                                    return;
                                } else {
                                    window.location.href = `${nextStepData.page}#chatbot-tour=${workflowId}&step=${nextStep + 1}`;
                                }
                            }
                        } else if (window.InteractiveTour) {
                            window.InteractiveTour.advanceStep(workflowId, nextStep + 1);
                        }
                    },
                actionText: step.actionText || (isLastStep ? 'Got it' : 'Next')
            };
        });

        return {
            name: workflowId,
            steps: tourSteps
        };
    }

    /**
     * Register a workflow tour dynamically from API data.
     *
     * @param {string} workflowId - The workflow identifier
     * @returns {Promise<boolean>} - True if registration successful
     */
    async registerTour(workflowId) {
        this._log(`[WorkflowTourParser] registerTour called for: ${workflowId}`);

        if (this.registeredWorkflows.has(workflowId)) {
            this._log(`[WorkflowTourParser] Already in registeredWorkflows set`);
            return true; // Already registered
        }

        if (typeof window.InteractiveTour === 'undefined' || !window.InteractiveTour.registerTour) {
            this._warn('[WorkflowTourParser] InteractiveTour not available');
            return false;
        }

        const tourData = await this.fetchTourConfig(workflowId);
        this._log(`[WorkflowTourParser] Tour data received:`, tourData);

        if (!tourData || !tourData.steps) {
            this._warn(`[WorkflowTourParser] No tour data/steps found for workflow: ${workflowId}`);
            return false;
        }

        this._log(`[WorkflowTourParser] Building tour config with ${tourData.steps.length} steps`);
        const tourConfig = this.buildTourConfig(workflowId, tourData.steps);
        this._log(`[WorkflowTourParser] Tour config built:`, tourConfig);

        if (!tourConfig) {
            this._warn(`[WorkflowTourParser] Failed to build tour config`);
            return false;
        }

        try {
            this._log(`[WorkflowTourParser] Registering tour with InteractiveTour...`);
            window.InteractiveTour.registerTour(workflowId, tourConfig);
            this.registeredWorkflows.add(workflowId);
            this._log(`[WorkflowTourParser] Registered dynamic tour: ${workflowId}`);
            return true;
        } catch (error) {
            console.error(`[WorkflowTourParser] Failed to register tour ${workflowId}:`, error);
            return false;
        }
    }

    /**
     * Handle a tour trigger link click.
     * Fetches tour config if needed and starts the tour.
     *
     * @param {string} workflowId - The workflow identifier
     * @param {string} targetPage - The page to start on
     */
    async handleTourTrigger(workflowId, targetPage) {
        // Close chatbot before starting tour
        if (window.ngodbChatbot && typeof window.ngodbChatbot.toggleChat === 'function') {
            window.ngodbChatbot.toggleChat(false);
        } else {
            // Fallback: try to close by hiding widget directly
            const chatWidget = document.getElementById('aiChatWidget');
            if (chatWidget) {
                chatWidget.classList.add('hidden');
            }
        }

        const registered = await this.registerTour(workflowId);

        if (registered) {
            // Small delay to let chatbot close animation complete
            setTimeout(() => {
                // Navigate to target page with tour hash
                if (targetPage && targetPage !== window.location.pathname) {
                    window.location.href = `${targetPage}#chatbot-tour=${workflowId}&step=1`;
                } else {
                    // Start tour on current page
                    if (window.InteractiveTour && window.InteractiveTour.start) {
                        window.InteractiveTour.start(workflowId);
                    }
                }
            }, 300);
        } else {
            this._warn(`Could not start tour: ${workflowId}`);
        }
    }

    /**
     * Process a chatbot message element for tour triggers.
     * Sets up click handlers for tour trigger buttons/links.
     *
     * @param {HTMLElement} messageElement - The message container element
     */
    processMessage(messageElement) {
        if (!messageElement) return;

        // Find all tour trigger elements
        const tourTriggers = messageElement.querySelectorAll('.chatbot-tour-trigger, a[href*="chatbot-tour="]');

        tourTriggers.forEach(trigger => {
            // Avoid double-binding
            if (trigger.dataset.tourBound) return;
            trigger.dataset.tourBound = 'true';

            trigger.addEventListener('click', async (e) => {
                e.preventDefault();
                e.stopPropagation();

                // Extract workflow ID from href or data attribute
                let workflowId = trigger.dataset.workflow;
                if (!workflowId) {
                    const href = trigger.getAttribute('href') || '';
                    const match = href.match(/chatbot-tour=([a-zA-Z0-9-]+)/);
                    if (match) {
                        workflowId = match[1];
                    }
                }

                if (!workflowId) {
                    console.warn('No workflow ID found in tour trigger');
                    return;
                }

                // Get target page from href
                const href = trigger.getAttribute('href') || '';
                const targetPage = href.split('#')[0] || window.location.pathname;

                await this.handleTourTrigger(workflowId, targetPage);
            });
        });
    }

    /**
     * Check URL for tour hash on page load.
     * If a tour hash is present but the tour isn't registered,
     * fetch and register it dynamically.
     */
    async checkUrlForDynamicTour() {
        const hash = window.location.hash || '';
        this._log('[WorkflowTourParser] Checking URL hash:', hash);
        const tourMatch = hash.match(/chatbot-tour=([a-zA-Z0-9-]+)/i);

        if (tourMatch) {
            const workflowId = tourMatch[1];
            this._log(`[WorkflowTourParser] Dynamic tour check for: ${workflowId}`);

            // Check if tour is already registered
            if (window.InteractiveTour && window.InteractiveTour.registeredTours) {
                this._log(`[WorkflowTourParser] InteractiveTour available, checking registered tours...`);
                const isRegistered = workflowId.toLowerCase() in window.InteractiveTour.registeredTours;
                this._log(`[WorkflowTourParser] Tour "${workflowId}" registered: ${isRegistered}`);

                if (!isRegistered) {
                    this._log(`[WorkflowTourParser] Fetching tour from API...`);
                    // Dynamically register before InteractiveTour processes the hash
                    const registered = await this.registerTour(workflowId);
                    this._log(`[WorkflowTourParser] registerTour result: ${registered}`);

                    if (registered) {
                        this._log(`[WorkflowTourParser] Tour "${workflowId}" registered, starting tour...`);
                        // Now the tour is registered, re-check URL hash to start it
                        // Use allowDynamic=false since tour is now registered
                        setTimeout(() => {
                            this._log(`[WorkflowTourParser] Calling InteractiveTour.checkUrlHash(false)...`);
                            if (window.InteractiveTour && window.InteractiveTour.checkUrlHash) {
                                window.InteractiveTour.checkUrlHash(false);
                            }
                        }, 100);
                    } else {
                        this._warn(`[WorkflowTourParser] Failed to register tour: ${workflowId}`);
                    }
                } else {
                    this._log(`[WorkflowTourParser] Tour "${workflowId}" already registered, starting...`);
                    // Tour is already registered, just start it
                    setTimeout(() => {
                        if (window.InteractiveTour && window.InteractiveTour.checkUrlHash) {
                            window.InteractiveTour.checkUrlHash(false);
                        }
                    }, 100);
                }
            } else {
                this._warn(`[WorkflowTourParser] InteractiveTour not available or no registeredTours`);
            }
        } else {
            this._log(`[WorkflowTourParser] No tour hash found in URL`);
        }
    }

    /**
     * List all available workflows from the API.
     *
     * @returns {Promise<Array>} - Array of workflow objects
     */
    async listWorkflows() {
        try {
            let data;
            const apiFn = (window.getApiFetch && window.getApiFetch());
            if (apiFn) {
                try {
                    data = await apiFn('/api/ai/documents/workflows');
                } catch {
                    return [];
                }
            } else {
                const fn = (window.getFetch && window.getFetch()) || fetch;
                const r = await fn('/api/ai/documents/workflows', {
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'same-origin'
                });
                if (!r.ok) return [];
                data = await r.json();
            }
            return (data && data.success) ? data.workflows : [];
        } catch (error) {
            console.error('Error fetching workflows:', error);
            return [];
        }
    }

    /**
     * Preload and register multiple workflows.
     * Useful for preloading common workflows on page load.
     *
     * @param {Array<string>} workflowIds - Array of workflow IDs to preload
     */
    async preloadWorkflows(workflowIds) {
        if (!workflowIds || !Array.isArray(workflowIds)) return;

        const promises = workflowIds.map(id => this.registerTour(id));
        await Promise.all(promises);
    }
}

// Create singleton instance
const workflowTourParser = new WorkflowTourParser();

// Make globally available
window.WorkflowTourParser = workflowTourParser;

// Auto-check URL for dynamic tours after DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        // Small delay to ensure InteractiveTour is initialized
        setTimeout(() => workflowTourParser.checkUrlForDynamicTour(), 300);
    });
} else {
    setTimeout(() => workflowTourParser.checkUrlForDynamicTour(), 300);
}
