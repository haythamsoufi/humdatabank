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
 * - Or set localStorage: localStorage.setItem('humdb:debug:workflow-tour', '1')
 * - Or set global: window.WORKFLOW_TOUR_DEBUG = true (before script loads)
 */

/**
 * Encode a workflow slug for use in URL path segments.
 * Azure WAF blocks slugs like "submit-data" that contain keywords matched by
 * OWASP injection rules. URL-safe base64 encodes the slug so the literal
 * string never appears in the path.
 *
 * @param {string} id - The workflow slug (e.g. "submit-data")
 * @returns {string} URL-safe base64 string with no padding characters
 */
function _encodeWorkflowId(id) {
    return btoa(id).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

class WorkflowTourParser {
    constructor() {
        this.registeredWorkflows = new Set();
        // Cache tours by "workflowId:language" key for multi-language support (in-memory, per page load)
        this.tourCache = {};
        // Debug logging flag - can be controlled via localStorage or global variable
        this._debugEnabled = this._getDebugFlag();
        // Persisted (localStorage) cache TTL - tour content only changes on deploy,
        // so a generous TTL is safe; ASSET_VERSION in the cache key invalidates it anyway.
        this._PERSIST_TTL_MS = 24 * 60 * 60 * 1000;
    }

    /**
     * Get debug flag from localStorage or global variable.
     *
     * @returns {boolean} - True if debug logging is enabled
     */
    _getDebugFlag() {
        try {
            // Check localStorage first
            const stored = localStorage.getItem('humdb:debug:workflow-tour');
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
            localStorage.setItem('humdb:debug:workflow-tour', enabled ? '1' : '0');
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
        if (window.humdatabankChatbot && window.humdatabankChatbot.preferredLanguage) {
            return window.humdatabankChatbot.preferredLanguage;
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
     * Build the localStorage key for a persisted tour, scoped to the current
     * app version so a deploy (ASSET_VERSION bump) automatically invalidates it.
     *
     * @param {string} workflowId
     * @param {string} language
     * @returns {string}
     */
    _persistKey(workflowId, language) {
        const version = (typeof window !== 'undefined' && window.ASSET_VERSION) || 'v1';
        return `humdb:tour:${version}:${workflowId}:${language}`;
    }

    /**
     * Read a previously persisted tour from localStorage, honoring the TTL.
     *
     * @param {string} workflowId
     * @param {string} language
     * @returns {Object|null}
     */
    _readPersistedTour(workflowId, language) {
        try {
            const raw = localStorage.getItem(this._persistKey(workflowId, language));
            if (!raw) return null;
            const parsed = JSON.parse(raw);
            if (!parsed || !parsed.data || !parsed.ts) return null;
            if (Date.now() - parsed.ts > this._PERSIST_TTL_MS) {
                localStorage.removeItem(this._persistKey(workflowId, language));
                return null;
            }
            return parsed.data;
        } catch (_) {
            return null;
        }
    }

    /**
     * Store a fetched tour in both the in-memory cache and localStorage.
     *
     * @param {string} workflowId
     * @param {string} language
     * @param {Object} tourData
     */
    _cacheTour(workflowId, language, tourData) {
        this.tourCache[this.getCacheKey(workflowId, language)] = tourData;
        try {
            localStorage.setItem(
                this._persistKey(workflowId, language),
                JSON.stringify({ data: tourData, ts: Date.now() })
            );
        } catch (_) {
            // localStorage full/unavailable - in-memory cache still works for this page load
        }
    }

    /**
     * Try to fetch a pre-generated tour JSON file from static/CDN storage.
     *
     * These files are produced by `flask workflows generate-static` (run on every
     * deploy) and served via the same STATIC_CDN_URL / ASSET_VERSION mechanism as
     * other static assets, so a hit here never touches a Gunicorn worker.
     *
     * @param {string} workflowId
     * @param {string} language
     * @returns {Promise<Object|null>}
     */
    async _fetchStaticTourConfig(workflowId, language) {
        try {
            if (typeof window.getStaticUrl !== 'function') return null;
            const url = window.getStaticUrl(`generated/tours/${workflowId}.${language}.json`);
            const fn = (window.getFetch && window.getFetch()) || fetch;
            const response = await fn(url, { method: 'GET', credentials: 'omit' });
            if (!response.ok) return null;

            const contentType = (response.headers.get('Content-Type') || '').toLowerCase();
            const text = await response.text();
            if (!contentType.includes('json') && !text.trim().startsWith('{')) return null;

            const data = JSON.parse(text);
            if (data && Array.isArray(data.steps) && data.steps.length) {
                this._log(`[WorkflowTourParser] Loaded ${workflowId} (${language}) from static/CDN`);
                return data;
            }
            return null;
        } catch (error) {
            this._log(`[WorkflowTourParser] Static tour fetch failed for ${workflowId}:`, error);
            return null;
        }
    }

    /**
     * Fetch workflow tour configuration.
     *
     * Resolution order: in-memory cache -> localStorage cache -> pre-generated
     * static/CDN file -> dynamic API (source of truth; also covers local dev
     * without generated files, and brand-new workflows not yet regenerated).
     *
     * @param {string} workflowId - The workflow identifier
     * @returns {Promise<Object|null>} - Tour configuration or null
     */
    async fetchTourConfig(workflowId) {
        const language = this.getUserLanguage();
        const cacheKey = this.getCacheKey(workflowId, language);

        this._log(`[WorkflowTourParser] Fetching tour config for: ${workflowId} (lang: ${language})`);

        if (this.tourCache[cacheKey]) {
            this._log(`[WorkflowTourParser] Found in memory cache for ${language}`);
            return this.tourCache[cacheKey];
        }

        const persisted = this._readPersistedTour(workflowId, language);
        if (persisted) {
            this._log(`[WorkflowTourParser] Found in localStorage cache for ${language}`);
            this.tourCache[cacheKey] = persisted;
            return persisted;
        }

        const staticTour = await this._fetchStaticTourConfig(workflowId, language);
        if (staticTour) {
            this._cacheTour(workflowId, language, staticTour);
            return staticTour;
        }

        try {
            // Include language parameter in the API request
            const url = `/api/ai/documents/workflows/${_encodeWorkflowId(workflowId)}/tour?lang=${encodeURIComponent(language)}`;
            this._log(`[WorkflowTourParser] Static file unavailable; fetching from: ${url}`);

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
                // Cache (memory + localStorage) with the actual language returned
                // (may differ from requested if a translation wasn't available)
                this._cacheTour(workflowId, actualLanguage, data.tour);
                if (actualLanguage !== language) {
                    this._cacheTour(workflowId, language, data.tour);
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
        if (window.humdatabankChatbot && typeof window.humdatabankChatbot.toggleChat === 'function') {
            window.humdatabankChatbot.toggleChat(false);
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
     * Remove #chatbot-tour=... from the URL without navigating.
     * Prevents sticky failed hashes from re-fetching the tour API on every refresh.
     */
    _clearChatbotTourHash() {
        try {
            const hash = window.location.hash || '';
            if (!/chatbot-tour=/i.test(hash)) return;
            window.history.replaceState(null, document.title, window.location.pathname + window.location.search);
        } catch (_) { /* ignore */ }
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
                        // Clear sticky #chatbot-tour= so every refresh does not re-hit the API.
                        this._clearChatbotTourHash();
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
                this._clearChatbotTourHash();
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
