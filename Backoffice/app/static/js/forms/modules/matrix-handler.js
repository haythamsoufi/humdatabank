/**
 * Matrix Handler Module
 * Handles matrix table interactions, calculations, and data management
 */

import { debugLog, debugError, debugWarn } from './debug.js';

function _mhFetch(url, opts = {}) {
    const fn = (window.getFetch && window.getFetch()) || fetch;
    return fn(url, opts);
}

// Locale-aware integer formatter for totals
const __matrixIntegerFormatter = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
function __formatInteger(value) {
    try {
        const num = Number(value || 0);
        if (!isFinite(num)) return '0';
        return __matrixIntegerFormatter.format(Math.round(num));
    } catch (e) {
        return String(Math.round(Number(value || 0)) || 0);
    }
}

/** Coerce a stored cell value to a number for totals (handles variable column { original, modified } objects). */
function __cellValueToNumber(value) {
    if (value == null || value === '') return 0;
    if (typeof value === 'number' && isFinite(value)) return value;
    const toUnformattedNumber = (v) => {
        if (v == null) return 0;
        const s = String(v).trim();
        if (!s) return 0;
        const plain = (typeof window !== 'undefined' && typeof window.__numericUnformat === 'function')
            ? window.__numericUnformat(s)
            : s;
        const num = Number(plain);
        return isFinite(num) ? num : 0;
    };
    if (typeof value === 'object' && value.original !== undefined) {
        const display = value.modified != null ? value.modified : value.original;
        return toUnformattedNumber(display);
    }
    return toUnformattedNumber(value);
}

/**
 * Coerce config flags that may be stored as boolean/number/string.
 * Treats "true"/"1"/"yes"/"on" as true and "false"/"0"/"no"/"off" as false.
 * Uses defaultWhenMissing only when value is null/undefined.
 */
function __configFlag(value, defaultWhenMissing = false) {
    if (value === undefined || value === null) return defaultWhenMissing;
    if (typeof value === 'boolean') return value;
    if (typeof value === 'number') return value === 1;
    if (typeof value === 'string') {
        const v = value.trim().toLowerCase();
        if (v === 'true' || v === '1' || v === 'yes' || v === 'y' || v === 'on') return true;
        if (v === 'false' || v === '0' || v === 'no' || v === 'n' || v === 'off') return false;
    }
    return Boolean(value);
}

/**
 * Normalize matrix payload before saving.
 * Removes non-cell metadata keys that should not be persisted.
 * @param {Object} data - Matrix data object
 * @returns {Object} Sanitized object safe to persist
 */
function __reorderMatrixData(data) {
    if (!data || typeof data !== 'object') {
        return data;
    }

    const reordered = {};

    // Keep insertion order of actual cell keys, but drop internal metadata keys.
    Object.keys(data).forEach(key => {
        if (!String(key).startsWith('_')) {
            reordered[key] = data[key];
        }
    });

    return reordered;
}

function __serializeMatrixData(data) {
    const sanitized = __reorderMatrixData(data || {});
    if (!sanitized || typeof sanitized !== 'object') return '';
    return Object.keys(sanitized).length > 0 ? JSON.stringify(sanitized) : '';
}

class MatrixHandler {
    constructor() {
        this.matrices = new Map();
        this.collapsedDropdownGroups = new Map(); // fieldId -> Set(group names)
        this.searchTimeout = null;
        this.debounceTimers = new Map();
        this.DEBOUNCE_DELAY = 100;
        this.validationErrors = new Map();
        this.currentFocusedCell = null;
        this.rowsBeingRemoved = new Set(); // Track rows currently being removed
        this.repositionDebounceTimer = null;
        this.scrollRafId = null; // RequestAnimationFrame ID for scroll repositioning
        this.pendingVariableResolution = new Map(); // Track fieldIds with pending variable resolution
        this.variableResolutionDebounceTimers = new Map(); // Debounce timers for batch variable resolution
        this.batchOperationsInProgress = new Set(); // Track fieldIds currently in batch operations (restore/auto-load)

        // Initialization diagnostics/state (used by the entry form loader heuristics)
        this.__initState = {
            state: 'new', // 'new' | 'initializing' | 'ready' | 'error'
            initCalls: 0,
            initStartedAt: null,
            initCompletedAt: null,
            stage: null,
            matrixContainersFound: null,
            matricesRegistered: null,
            lastError: null
        };
    }

    /**
     * Ensure a matrix is registered in `this.matrices` from its DOM container.
     * This is important for matrices that are injected into the DOM after the initial `init()`
     * (e.g., repeat sections / dynamic section rendering).
     *
     * @param {HTMLElement} container - `.matrix-container` element
     * @param {string|number|null} fieldIdOverride - optional fieldId to register under
     * @returns {{container: HTMLElement, config: Object, data: Object}|null}
     */
    _registerMatrixFromDom(container, fieldIdOverride = null) {
        try {
            if (!container) return null;

            const fieldId = String(fieldIdOverride || container.dataset.fieldId || '');
            if (!fieldId) return null;

            const configData = container.dataset.matrixConfig || '{}';
            let parsed;
            try {
                parsed = JSON.parse(configData);
            } catch (e) {
                debugWarn('matrix-handler', '[REGISTER MATRIX] Failed to parse data-matrix-config', {
                    fieldId,
                    error: e,
                    configDataSnippet: String(configData || '').slice(0, 200)
                });
                return null;
            }

            // Handle nested matrix_config structure (some contexts wrap it)
            const matrixConfig = parsed.matrix_config
                ? { ...parsed.matrix_config, is_required: parsed.is_required }
                : parsed;

            const existingData = this.parseExistingData(container);

            const matrixInfo = { container, config: matrixConfig, data: existingData };
            this.matrices.set(fieldId, matrixInfo);
            return matrixInfo;
        } catch (e) {
            // Never throw from a recovery helper
            debugWarn('matrix-handler', '[REGISTER MATRIX] Unexpected error', { error: e });
            return null;
        }
    }

    /**
     * Extract row ID from various sources (helper method)
     * Priority: providedId > rowData._id > rowData.id > rowLabel (for manual mode)
     *
     * @param {Object} rowData - Row data object from lookup list or API
     * @param {string} rowLabel - Row label/name (used as ID for manual mode)
     * @param {string|null} providedId - Explicitly provided row ID
     * @returns {string} Row ID to use for cell keys
     * @throws {Error} If no valid ID can be determined
     */
    extractRowId(rowData, rowLabel, providedId = null) {
        // Priority: providedId > rowData._id > rowData.id > rowLabel
        // For manual mode, rowLabel is used as the ID (labels are unique within a matrix)
        // For list library mode, we should always have an ID from the lookup list
        const rowId = providedId || rowData?._id || rowData?.id || rowLabel;

        if (!rowId || (typeof rowId !== 'string' && typeof rowId !== 'number')) {
            debugError('matrix-handler', 'Cannot extract valid row ID', { rowData, rowLabel, providedId });
            throw new Error(`Invalid row ID: cannot determine ID for row "${rowLabel}"`);
        }

        return String(rowId);
    }

    /**
     * Remove non-cell metadata keys from matrix data.
     */
    sanitizeMatrixData(matrix) {
        if (!matrix || !matrix.data || typeof matrix.data !== 'object') return;
        Object.keys(matrix.data).forEach((key) => {
            if (String(key).startsWith('_')) {
                delete matrix.data[key];
            }
        });
    }

    /**
     * Initialize matrix handling.
     * Returns a Promise that resolves when sync and async init (restore rows, auto-load, variable lookups) are done.
     */
    async init() {
        this.__initState.initCalls += 1;

        // Make init idempotent: this module is auto-initialized and also called from forms/main.js
        if (this.__initState.state === 'ready') {
            debugLog('matrix-handler', 'init() called but already initialized', { initCalls: this.__initState.initCalls });
            return Promise.resolve();
        }
        if (this.__initState.state === 'initializing') {
            debugLog('matrix-handler', 'init() called while initializing (ignored)', { initCalls: this.__initState.initCalls });
            return Promise.resolve();
        }

        this.__initState.state = 'initializing';
        this.__initState.initStartedAt = Date.now();
        this.__initState.stage = 'start';
        this.__initState.lastError = null;

        debugLog('matrix-handler', 'Initializing matrix handling', { initCalls: this.__initState.initCalls });

        try {
            this.__initState.stage = 'setupEventListeners';
            this.setupEventListeners();

            this.__initState.stage = 'initializeMatrices';
            await this.initializeMatrices();

            this.__initState.stage = 'calculateAllMatrices';
            this.calculateAllMatrices();

            this.__initState.stage = 'finalize';
            this.__initState.matrixContainersFound = document.querySelectorAll('.matrix-container').length;
            this.__initState.matricesRegistered = (this.matrices && typeof this.matrices.size === 'number') ? this.matrices.size : null;
            this.__initState.initCompletedAt = Date.now();
            this.__initState.state = 'ready';
            this.__initState.stage = 'ready';
        } catch (e) {
            this.__initState.state = 'error';
            this.__initState.initCompletedAt = Date.now();
            this.__initState.lastError = {
                message: (e && e.message) ? e.message : String(e),
                name: (e && e.name) ? e.name : undefined,
                stage: this.__initState.stage
            };
            debugError('matrix-handler', 'init() failed', { error: e, status: this.getInitStatus() });
            throw e;
        }
    }

    /**
     * Lightweight status snapshot for loader/debugging.
     * @returns {Object}
     */
    getInitStatus() {
        try {
            return { ...this.__initState };
        } catch (e) {
            // Avoid throwing from diagnostics
            return { state: 'unknown', error: String(e) };
        }
    }

    /**
     * Setup event listeners for matrix interactions
     */
    setupEventListeners() {
        // Listen for matrix input changes (including variable text inputs)
        document.addEventListener('input', (e) => {
            if (e.target.matches('.matrix-container input[type="number"], .matrix-container input[data-numeric="true"]') ||
                e.target.matches('.matrix-container input[type="checkbox"]') ||
                e.target.matches('.matrix-container input[data-column-type="variable"]')) {
                this.handleMatrixInputChange(e.target);
            }
        });

        // Also listen for change events (for better compatibility)
        document.addEventListener('change', (e) => {
            if (e.target.matches('.matrix-container input[type="number"], .matrix-container input[data-numeric="true"]') ||
                e.target.matches('.matrix-container input[type="checkbox"]') ||
                e.target.matches('.matrix-container input[data-column-type="variable"]')) {
                this.handleMatrixInputChange(e.target);
            } else if (e.target.matches('input[name*="_data_not_available"], input[name*="_not_applicable"]')) {
                this.handleDataAvailabilityChange(e.target);
            }
        });

        // Listen for keyboard navigation
        document.addEventListener('keydown', (e) => {
            if (e.target.matches('.matrix-container input[type="number"], .matrix-container input[data-numeric="true"]')) {
                this.handleKeyboardNavigation(e);
            }
        });

        // Listen for form submission to collect matrix data
        document.addEventListener('submit', (e) => {
            if (e.target.matches('form')) {
                this.collectMatrixData();
                this.validateAllMatrices();
            }
        });

        // Listen for blur events for validation
        document.addEventListener('blur', (e) => {
            if (e.target.matches('.matrix-container input[type="number"], .matrix-container input[data-numeric="true"]') ||
                e.target.matches('.matrix-container input[data-column-type="variable"]')) {
                this.validateMatrixInput(e.target);
            }
        }, true);

        // Listen for advanced matrix functionality
        document.addEventListener('click', (e) => {
            if (e.target.closest('.remove-matrix-row-btn')) {
                e.preventDefault();
                e.stopPropagation();
                this.handleRemoveRowClick(e.target.closest('.remove-matrix-row-btn'));
            }
            if (e.target.closest('.matrix-search-option')) {
                this.selectRowOption(e.target.closest('.matrix-search-option'));
            }
        });

        // Listen for search input and focus/blur events
        // Check if input is the matrix search input (works with repeat sections too)
        document.addEventListener('input', (e) => {
            debugLog('matrix-handler', '[SEARCH EVENT] Input event triggered', {
                targetType: e.target.type,
                targetId: e.target.id,
                hasMatrixAddRowInterface: !!e.target.closest('.matrix-add-row-interface'),
                hasMatrixContainer: !!e.target.closest('.matrix-container'),
                targetClasses: e.target.className
            });
            if (e.target.type === 'text' && e.target.closest('.matrix-add-row-interface') &&
                e.target.closest('.matrix-container')) {
                debugLog('matrix-handler', '[SEARCH EVENT] Matched input event - calling handleSearchInput');
                this.handleSearchInput(e.target);
            }
        });

        document.addEventListener('focus', (e) => {
            debugLog('matrix-handler', '[SEARCH EVENT] Focus event triggered', {
                targetType: e.target.type,
                targetId: e.target.id,
                targetTagName: e.target.tagName,
                hasMatrixAddRowInterface: !!e.target.closest('.matrix-add-row-interface'),
                hasMatrixContainer: !!e.target.closest('.matrix-container'),
                targetClasses: e.target.className,
                parentElement: e.target.parentElement?.tagName,
                closestMatrixAddRow: e.target.closest('.matrix-add-row-interface')?.tagName
            });
            if (e.target.type === 'text' && e.target.closest('.matrix-add-row-interface') &&
                e.target.closest('.matrix-container')) {
                debugLog('matrix-handler', '[SEARCH EVENT] Matched focus event - calling showSearchDropdown');
                this.showSearchDropdown(e.target);
            } else {
                debugLog('matrix-handler', '[SEARCH EVENT] Focus event did not match', {
                    isText: e.target.type === 'text',
                    hasAddRowInterface: !!e.target.closest('.matrix-add-row-interface'),
                    hasMatrixContainer: !!e.target.closest('.matrix-container')
                });
            }
        }, true);

        document.addEventListener('blur', (e) => {
            debugLog('matrix-handler', '[SEARCH EVENT] Blur event triggered', {
                targetType: e.target.type,
                targetId: e.target.id,
                hasMatrixAddRowInterface: !!e.target.closest('.matrix-add-row-interface'),
                hasMatrixContainer: !!e.target.closest('.matrix-container')
            });
            if (e.target.type === 'text' && e.target.closest('.matrix-add-row-interface') &&
                e.target.closest('.matrix-container')) {
                setTimeout(() => {
                    const fieldId = e.target.dataset.fieldId;
                    const resultsContainer = fieldId ? this._findResultsContainer(fieldId) : null;
                    const hoveringDropdown = !!(resultsContainer && resultsContainer.matches(':hover'));
                    if ((!document.activeElement || !document.activeElement.closest('.matrix-add-row-interface')) && !hoveringDropdown) {
                        this.hideSearchDropdown(e.target);
                    }
                }, 300);
            }
        }, true);

        // Close dropdown when clicking outside
        document.addEventListener('mousedown', (e) => {
            if (!e.target.closest('.matrix-add-row-interface')
                && !e.target.closest('.matrix-search-option')
                && !e.target.closest('.matrix-group-header')
                && !e.target.closest('.matrix-group-items')) {
                document.querySelectorAll('.matrix-container .matrix-add-row-interface input[type="text"]').forEach(input => {
                    this.hideSearchDropdown(input);
                });
            }
        });

        // Handle scroll and resize to reposition dropdowns
        // Use requestAnimationFrame for smooth updates during scroll
        const handleScroll = () => {
            // Cancel any pending animation frame
            if (this.scrollRafId !== null) {
                cancelAnimationFrame(this.scrollRafId);
            }
            // Use requestAnimationFrame for smooth repositioning during scroll
            this.scrollRafId = requestAnimationFrame(() => {
                this.repositionVisibleDropdowns();
                this.scrollRafId = null;
            });
        };

        // Listen to scroll on window (main page scroll) - this is the most common case
        window.addEventListener('scroll', handleScroll, { passive: true });

        // Also listen to scroll events in capture phase to catch scrolls in any scrollable container
        // This ensures we catch scroll events from divs, sections, or any other scrollable elements
        document.addEventListener('scroll', handleScroll, { passive: true, capture: true });

        window.addEventListener('resize', () => {
            if (this.repositionDebounceTimer) {
                clearTimeout(this.repositionDebounceTimer);
            }
            this.repositionDebounceTimer = setTimeout(() => {
                this.repositionVisibleDropdowns();
            }, 150);
        });
    }

    /**
     * Initialize all matrices on the page.
     * Returns a Promise that resolves when all matrix async work (restore rows, auto-load, variable lookups) is done.
     */
    initializeMatrices() {
        const matrixContainers = document.querySelectorAll('.matrix-container');
        debugLog('matrix-handler', `Found ${matrixContainers.length} matrix containers`);
        const matrixPromises = [];

        matrixContainers.forEach((container, index) => {
            const fieldId = container.dataset.fieldId;
            const configData = container.dataset.matrixConfig || '{}';
            let config = JSON.parse(configData);

            // Handle nested matrix_config structure
            let matrixConfig;
            if (config.matrix_config) {
                matrixConfig = { ...config.matrix_config, is_required: config.is_required };
            } else {
                matrixConfig = config;
            }

            // Parse existing data
            const existingData = this.parseExistingData(container);

            // Find and store hidden field reference
            const hiddenField = container.querySelector('input[type="hidden"][name^="field_value"]') ||
                                container.querySelector('input[type="hidden"]');

            this.matrices.set(fieldId, {
                container,
                config: matrixConfig,
                data: existingData,
                hiddenField: hiddenField
            });

            // For advanced mode matrices, restore dynamic rows from saved data
            if (matrixConfig.row_mode === 'list_library') {
                const autoLoadEnabled = __configFlag(matrixConfig.auto_load_entities, false);
                const listLibraryPromise = this.restoreDynamicRows(fieldId).then(() => {
                    // Apply highlighting to existing rows after restoration
                    this.applyManualRowHighlighting(fieldId);
                    // Run auto-load after restore completes so DOM and variable resolution are stable
                    // (with variable columns + row totals, a fixed 100ms timeout could run before restore finished)
                    if (autoLoadEnabled) {
                        const delay = 50; // Allow template variables script to have executed
                        return new Promise((resolve) => {
                            setTimeout(() => {
                                this.autoLoadEntities(fieldId).then(() => {
                                    this.applyManualRowHighlighting(fieldId);
                                    resolve();
                                }).catch((err) => {
                                    debugError('matrix-handler', 'autoLoadEntities failed', err);
                                    resolve();
                                });
                            }, delay);
                        });
                    }
                });
                matrixPromises.push(listLibraryPromise);
            } else {
                // For static matrices, restore cell values directly
                this.restoreStaticMatrixValues(fieldId);
            }

            // Apply highlighting for non-list_library or when auto-load is not enabled
            if (matrixConfig.row_mode !== 'list_library' || !__configFlag(matrixConfig.auto_load_entities, false)) {
                setTimeout(() => {
                    this.applyManualRowHighlighting(fieldId);
                }, 50);
            }

            // Note: Event listeners are handled via event delegation in setupEventListeners
            // No need to add per-input listeners to avoid duplicate event firing

            debugLog('matrix-handler', `Initialized matrix for field ${fieldId}`, config);
        });

        return Promise.all(matrixPromises);
    }

    /**
     * Parse existing matrix data from the hidden field
     */
    parseExistingData(container) {
        const hiddenField = container.querySelector('input[type="hidden"]');
        if (hiddenField && hiddenField.value) {
            try {
                const data = JSON.parse(hiddenField.value);
                // Keep only data keys that represent matrix cells.
                if (data && typeof data === 'object') {
                    Object.keys(data).forEach((key) => {
                        if (String(key).startsWith('_')) delete data[key];
                    });
                }
                return data;
            } catch (e) {
                debugError('MatrixHandler: Error parsing existing matrix data', e);
                return {};
            }
        }
        return {};
    }

    /**
     * Handle matrix input changes
     */
    handleMatrixInputChange(input) {
        const container = input.closest('.matrix-container');
        const fieldId = container?.dataset?.fieldId;

        debugLog('matrix-handler', `Handling input change for field ${fieldId}`, input);

        if (!fieldId) {
            debugError('matrix-handler', 'Could not find fieldId for input', input);
            return;
        }

        // Ignore changes from disabled inputs (shouldn't happen, but safety check)
        if (input.disabled) {
            debugLog('matrix-handler', `Ignoring change from disabled input`, input);
            return;
        }

        // Clear any existing validation errors for this input
        this.clearInputError(input);

        // Debounce the calculation
        if (this.debounceTimers.has(fieldId)) {
            clearTimeout(this.debounceTimers.get(fieldId));
        }

        this.debounceTimers.set(fieldId, setTimeout(() => {
            // Check if matrix still exists before processing
            let matrix = this.matrices.get(fieldId);

            // If matrix not found, try to ensure it's registered (for dynamically added matrices)
            if (!matrix) {
                debugLog('matrix-handler', `Matrix ${fieldId} not found in registry, attempting to register from container`);
                const container = document.querySelector(`.matrix-container[data-field-id="${fieldId}"]`);
                if (container) {
                    const registered = this._registerMatrixFromDom(container, fieldId);
                    if (registered) {
                        matrix = this.matrices.get(fieldId);
                        // Initialize hidden field reference
                        if (matrix) {
                            matrix.hiddenField = container.querySelector('input[type="hidden"][name^="field_value"]') ||
                                                  container.querySelector('input[type="hidden"]');
                        }
                        debugLog('matrix-handler', `Successfully registered matrix ${fieldId} from container`);
                    } else {
                        debugError('matrix-handler', `Failed to register matrix ${fieldId} from container`);
                    }
                } else {
                    debugError('matrix-handler', `Matrix container for field ${fieldId} not found in DOM`);
                }
            }

            if (!matrix) {
                debugError('matrix-handler', `Matrix ${fieldId} not found after registration attempt, skipping update`);
                this.debounceTimers.delete(fieldId);
                return;
            }

            if (!matrix.container.isConnected) {
                debugLog('matrix-handler', `Matrix container for ${fieldId} is no longer in DOM, cleaning up`);
                this.cleanupMatrix(fieldId);
                this.debounceTimers.delete(fieldId);
                return;
            }

            this.updateMatrixData(fieldId, input);
            // Use requestAnimationFrame to ensure DOM is updated before calculation
            requestAnimationFrame(() => {
                // Double-check matrix still exists before calculating
                if (this.matrices.has(fieldId) && this.matrices.get(fieldId).container.isConnected) {
                    this.calculateMatrixTotals(fieldId);
                }
            });
        }, this.DEBOUNCE_DELAY));
    }

    /**
     * Update matrix data when input changes
     */
    updateMatrixData(fieldId, input) {
        const matrix = this.matrices.get(fieldId);
        if (!matrix) {
            debugError('matrix-handler', `Matrix not found for field ${fieldId}`);
            return;
        }

        // Check if container is still in DOM (prevent errors if matrix was removed)
        if (!matrix.container.isConnected) {
            debugLog('matrix-handler', `Matrix container for ${fieldId} is no longer in DOM, cleaning up`);
            this.cleanupMatrix(fieldId);
            return;
        }

        const cellKey = input.dataset.cellKey;
        const columnType = input.dataset.columnType || 'number';
        const isVariable = columnType === 'variable';

        debugLog('matrix-handler', `updateMatrixData for field ${fieldId}: cellKey="${cellKey}", columnType="${columnType}", input.value="${input.value}", input.type="${input.type}"`);

        // For variable columns, check if value should be saved
        if (isVariable) {
            const saveValue = input.dataset.variableSaveValue === 'true';
            if (!saveValue) {
                // Don't save variable values that are marked as not saved
                if (matrix.data[cellKey] !== undefined) {
                    delete matrix.data[cellKey];
                    debugLog('matrix-handler', `Removed variable cell ${cellKey} from data (save_value=false)`);
                }
                return;
            }
        }

        // Handle different input types
        let value;
        if (input.type === 'checkbox') {
            // Handle tick columns (both regular and variable tick)
            value = input.checked ? 1 : 0;

            // For variable tick columns, also handle modification tracking
            if (isVariable) {
                const originalValueAttr = input.getAttribute('data-original-value');
                const originalValue = originalValueAttr !== null ? originalValueAttr : '';
                const originalChecked = originalValue === '1' || originalValue === 1 || originalValue === 'true';
                const isModified = input.checked !== originalChecked && originalValue !== '';

                debugLog('matrix-handler', `Variable tick modification check: checked=${input.checked}, original="${originalValue}", isModified=${isModified}`);

                // Update visual indicator (always call to ensure styling is correct)
                this.updateVariableModificationIndicator(input, isModified, originalValue);

                // Store both original and modified values if changed
                if (cellKey) {
                    const existingData = matrix.data[cellKey];
                    const valueStr = String(value);
                    if (existingData && typeof existingData === 'object' && existingData.original !== undefined) {
                        // Update existing structure
                        matrix.data[cellKey] = {
                            original: existingData.original,
                            modified: valueStr,
                            isModified: isModified
                        };
                    } else {
                        // Create new structure with original value
                        matrix.data[cellKey] = {
                            original: originalValue || valueStr,
                            modified: valueStr,
                            isModified: isModified
                        };
                    }
                }
            }
        } else if (isVariable) {
            // For variable number columns, store as string (don't parse as number)
            value = String(input.value || '').trim();

            // Check if value has been modified from original (normalize so "168711" and "168,711" compare equal)
            const originalValueAttr = input.getAttribute('data-original-value');
            const originalValue = originalValueAttr !== null ? originalValueAttr : '';
            const normalizeForCompare = (s) => {
                if (s === '' || s == null) return '';
                return (typeof window.__numericUnformat === 'function') ? window.__numericUnformat(s) : String(s);
            };
            const isModified = normalizeForCompare(value) !== normalizeForCompare(originalValue) && originalValue !== '';

            debugLog('matrix-handler', `Variable modification check: value="${value}", original="${originalValue}", isModified=${isModified}`);

            // Update visual indicator (always call to ensure styling is correct)
            this.updateVariableModificationIndicator(input, isModified, originalValue);

            // Store both original and modified values if changed
            if (cellKey) {
                const existingData = matrix.data[cellKey];
                if (existingData && typeof existingData === 'object' && existingData.original !== undefined) {
                    // Update existing structure
                    matrix.data[cellKey] = {
                        original: existingData.original,
                        modified: value,
                        isModified: isModified
                    };
                } else {
                    // Create new structure with original value
                    matrix.data[cellKey] = {
                        original: originalValue || value,
                        modified: value,
                        isModified: isModified
                    };
                }
            }
        } else {
            const rawString = (window.__numericUnformat ? window.__numericUnformat(input.value) : String(input.value || ''));
            value = parseFloat(rawString) || 0;
        }

        debugLog('matrix-handler', `Input value: "${input.value}", checked: ${input.checked}, parsed: ${value}, cellKey: ${cellKey}, columnType: ${columnType}`);

        // Update the data object using the cell key (for non-variable columns, use simple value)
        if (cellKey && columnType !== 'variable') {
            matrix.data[cellKey] = value;
            debugLog('matrix-handler', `Updated matrix ${fieldId} cell ${cellKey} = ${value}`);
        } else if (cellKey && columnType === 'variable') {
            // Variable columns already handled above with modification tracking
            debugLog('matrix-handler', `Updated matrix ${fieldId} variable cell ${cellKey}`, matrix.data[cellKey]);
        }

        if (cellKey) {
            // Remove metadata keys before persisting hidden payload.
            this.sanitizeMatrixData(matrix);

            // Refresh hidden field reference (may have changed or been removed)
            // Try to find the hidden field with name starting with field_value first, fallback to any hidden input
            matrix.hiddenField = matrix.container.querySelector('input[type="hidden"][name^="field_value"]') ||
                                  matrix.container.querySelector('input[type="hidden"]');

            // Update the hidden field immediately
            if (matrix.hiddenField) {
                const serializedData = __serializeMatrixData(matrix.data);
                matrix.hiddenField.value = serializedData;
                debugLog('matrix-handler', `Updated hidden field for matrix ${fieldId}:`, matrix.data);
                debugLog('matrix-handler', `Hidden field value for matrix ${fieldId}:`, serializedData);
            } else {
                debugError('matrix-handler', `Hidden field not found for matrix ${fieldId} in container`, matrix.container);
            }
        } else {
            debugWarn('matrix-handler', 'No cell key found for input', input);
            debugWarn('matrix-handler', 'Input attributes:', {
                cellKey: input.dataset.cellKey,
                row: input.dataset.row,
                column: input.dataset.column,
                name: input.name
            });
        }
    }

    /**
     * Calculate totals for a specific matrix
     */
    calculateMatrixTotals(fieldId) {
        const matrix = this.matrices.get(fieldId);
        if (!matrix) {
            debugError(`MatrixHandler: Matrix not found for field ${fieldId}`);
            return;
        }

        // Check if container is still in DOM
        if (!matrix.container.isConnected) {
            debugLog('matrix-handler', `Matrix container for ${fieldId} is no longer in DOM, cleaning up and skipping calculation`);
            this.cleanupMatrix(fieldId);
            return;
        }

        const container = matrix.container;
        const config = matrix.config;
        const data = matrix.data; // Use stored data instead of reading from DOM

        // For advanced mode, get rows from DOM; for manual mode, use config
        let rows;
        let rowIdMap = new Map(); // Map row labels to row IDs for ID-based cell keys
        if (config.row_mode === 'list_library') {
            // Get dynamic rows from DOM with both label and ID
            const rowElements = container.querySelectorAll('tr.matrix-data-row');
            rows = Array.from(rowElements).map(tr => {
                const rowLabel = tr.getAttribute('data-row-label');
                const rowId = tr.getAttribute('data-row-id');

                if (!rowId) {
                    debugWarn('matrix-handler', `Row missing data-row-id attribute: ${rowLabel}`);
                    // Fallback to label for backward compatibility, but log warning
                    const fallbackId = rowLabel;
                    if (rowLabel) {
                        rowIdMap.set(rowLabel, fallbackId);
                    }
                    return rowLabel || tr.querySelector('td[role="rowheader"]')?.textContent?.trim();
                }

                if (rowLabel && rowId) {
                    rowIdMap.set(rowLabel, rowId);
                }
                return rowLabel || tr.querySelector('td[role="rowheader"]')?.textContent?.trim();
            }).filter(Boolean);
        } else {
            // Use static rows from config
            // For manual mode, row label IS the row ID (labels are unique within a matrix)
            rows = config.rows || [];
            rows.forEach(row => {
                rowIdMap.set(row, row); // In manual mode, label = ID
            });
        }

        const columns = config.columns || [];
        const showRowTotals = config.show_row_totals !== false; // Default to true
        const showColumnTotals = config.show_column_totals !== false; // Default to true

        debugLog('matrix-handler', `Calculating totals for matrix ${fieldId}`, { rows, columns, showRowTotals, showColumnTotals, data });
        debugLog('matrix-handler', `Matrix data keys:`, Object.keys(data));
        debugLog('matrix-handler', `Matrix data values:`, Object.values(data));

        // Calculate row totals
        if (showRowTotals) {
            rows.forEach((row, rowIndex) => {
                let rowTotal = 0;

                // Get row ID (standardized: always use ID-based keys)
                const rowId = rowIdMap.get(row);
                if (!rowId) {
                    debugWarn('matrix-handler', `No row ID found for row: ${row}, skipping total calculation`);
                    return;
                }

                // Calculate row total by iterating through columns for this row
                columns.forEach((column, colIndex) => {
                    const columnName = typeof column === 'object' ? column.name : column;
                    const columnType = typeof column === 'object' ? column.type : 'number';
                    // Always use ID-based cell key: rowId_columnName
                    const cellKey = `${rowId}_${columnName}`;
                    const rawValue = data[cellKey];
                    const value = __cellValueToNumber(rawValue);

                    if (columnType === 'tick') {
                        // For tick columns, count checked items (1) as 1, unchecked (0) as 0
                        rowTotal += value;
                    } else {
                        // For number columns, sum the values
                        rowTotal += value;
                    }

                    debugLog('matrix-handler', `Row ${rowIndex}, Col ${colIndex} (${columnType}) = ${value}, running row total = ${rowTotal}`);
                    debugLog('matrix-handler', `Looking for cellKey: "${cellKey}", found value: ${value}`);
                });

                // Find row total element by row ID (standardized)
                const totalElement = container.querySelector(`.matrix-row-total[data-row-id="${rowId}"]`);
                debugLog('matrix-handler', `Looking for row total element with selector: .matrix-row-total[data-row-id="${rowId}"]`);
                debugLog('matrix-handler', `Found element:`, totalElement);
                if (totalElement) {
                    const newValue = __formatInteger(rowTotal);
                    totalElement.textContent = newValue;
                    totalElement.style.display = 'block';
                    totalElement.style.visibility = 'visible';

                    // Announce to screen readers
                    this.announceTotalUpdate(fieldId, 'row', newValue, row);

                    debugLog('matrix-handler', `Set row total for ${row} (ID: ${rowId}) = ${rowTotal}`);
                } else {
                    debugLog('matrix-handler', `Row total element not found for ${row} (ID: ${rowId})`);
                }
            });
        }

        // Calculate column totals (optimized: build column map once)
        if (showColumnTotals) {
            // Build a map of column values for efficient lookup
            const columnValuesMap = new Map();
            Object.keys(data).forEach((key) => {
                // Skip metadata fields
                if (key.startsWith('_')) {
                    return;
                }

                // Keys are in format: "rowId_columnName" (standardized to ID-only)
                const lastUnderscore = key.lastIndexOf('_');
                if (lastUnderscore > 0) {
                    const columnName = key.substring(lastUnderscore + 1);
                    const value = data[key] || 0;

                    if (!columnValuesMap.has(columnName)) {
                        columnValuesMap.set(columnName, []);
                    }
                    columnValuesMap.get(columnName).push(value);
                }
            });

            columns.forEach((column, colIndex) => {
                const columnName = typeof column === 'object' ? column.name : column;
                const columnType = typeof column === 'object' ? column.type : 'number';
                let columnTotal = 0;

                // Sum values from the pre-built map (use numeric coercion for variable column objects)
                const values = columnValuesMap.get(columnName) || [];
                values.forEach((rawValue) => {
                    const value = __cellValueToNumber(rawValue);
                    if (columnType === 'tick') {
                        // For tick columns, count checked items (1) as 1, unchecked (0) as 0
                        columnTotal += value;
                    } else {
                        // For number columns, sum the values
                        columnTotal += value;
                    }
                });

                // Ensure we're searching within the correct matrix container
                const totalElement = container.querySelector(`.matrix-column-total[data-column="${columnName}"]`);
                debugLog('matrix-handler', `Looking for column total element with selector: .matrix-column-total[data-column="${columnName}"] in container for field ${fieldId}`);
                debugLog('matrix-handler', `Container:`, container);
                debugLog('matrix-handler', `Found element:`, totalElement);
                if (totalElement) {
                    debugLog('matrix-handler', `Element parent:`, totalElement.parentElement);
                    debugLog('matrix-handler', `Element current text:`, totalElement.textContent);
                }
                if (totalElement) {
                    const newValue = __formatInteger(columnTotal);
                    totalElement.textContent = newValue;
                    totalElement.style.display = 'block';
                    totalElement.style.visibility = 'visible';

                    // Announce to screen readers
                    this.announceTotalUpdate(fieldId, 'column', newValue, this.getColumnDisplayName(column));

                    debugLog('matrix-handler', `Set column total for ${column} = ${columnTotal} (formatted: ${newValue})`);
                } else {
                    debugLog('matrix-handler', `Column total element not found for ${column}`);
                }
            });
        }

        // Calculate grand total (only if both row and column totals are shown)
        if (showRowTotals && showColumnTotals) {
            let grandTotal = 0;
            // Skip metadata fields when calculating grand total
            Object.entries(data).forEach(([key, value]) => {
                if (key.startsWith('_')) {
                    return; // Skip metadata fields
                }
                grandTotal += __cellValueToNumber(value);
            });

            const grandTotalElement = container.querySelector('.matrix-grand-total');
            if (grandTotalElement) {
                const newValue = __formatInteger(grandTotal);
                grandTotalElement.textContent = newValue;
                grandTotalElement.style.display = 'block';
                grandTotalElement.style.visibility = 'visible';

                // Announce to screen readers
                this.announceTotalUpdate(fieldId, 'grand', grandTotal.toFixed(0), '');

                debugLog(`MatrixHandler: Set grand total = ${grandTotal}`);
            } else {
                debugLog(`MatrixHandler: Grand total element not found`);
            }
        }

        debugLog(`MatrixHandler: Completed totals calculation for matrix ${fieldId}`);
    }


    /**
     * Calculate totals for all matrices
     */
    calculateAllMatrices() {
        this.matrices.forEach((matrix, fieldId) => {
            this.calculateMatrixTotals(fieldId);
        });
    }

    /**
     * Handle data availability checkbox changes
     */
    handleDataAvailabilityChange(checkbox) {
        const container = checkbox.closest('.matrix-container');
        if (!container) return;

        const fieldId = container.dataset.fieldId;
        const matrix = this.matrices.get(fieldId);
        if (!matrix) return;

        // Disable/enable matrix inputs based on data availability
        const inputs = container.querySelectorAll('input[type="number"], input[data-numeric="true"]');
        const isDisabled = checkbox.checked;

        inputs.forEach(input => {
            input.disabled = isDisabled;
            if (isDisabled) {
                input.value = '';
            }
        });

        // Clear totals when disabled
        if (isDisabled) {
            this.clearMatrixTotals(fieldId);
        } else {
            this.calculateMatrixTotals(fieldId);
        }

        debugLog(`MatrixHandler: Data availability changed for matrix ${fieldId} - Disabled: ${isDisabled}`);
    }

    /**
     * Clear matrix totals
     */
    clearMatrixTotals(fieldId) {
        const matrix = this.matrices.get(fieldId);
        if (!matrix) return;

        const container = matrix.container;

        // Clear row totals
        const rowTotals = container.querySelectorAll('.matrix-row-total');
        rowTotals.forEach(total => {
            total.textContent = '0';
        });

        // Clear column totals
        const columnTotals = container.querySelectorAll('.matrix-column-total');
        columnTotals.forEach(total => {
            total.textContent = '0';
        });

        // Clear grand total
        const grandTotal = container.querySelector('.matrix-grand-total');
        if (grandTotal) {
            grandTotal.textContent = '0';
        }
    }

    /**
     * Collect matrix data for form submission
     */
    collectMatrixData() {
        this.matrices.forEach((matrix, fieldId) => {
            // Skip if container is no longer in DOM
            if (!matrix.container.isConnected) {
                debugLog('matrix-handler', `Matrix container for ${fieldId} is no longer in DOM, cleaning up and skipping collection`);
                this.cleanupMatrix(fieldId);
                return;
            }

            // Remove metadata keys before collection.
            this.sanitizeMatrixData(matrix);

            // Filter out variable columns that shouldn't be saved
            const dataToSave = { ...matrix.data };
            const config = matrix.config;
            const columns = config.columns || [];

            // Remove variable columns that have variable_save_value: false
            columns.forEach(column => {
                const columnName = typeof column === 'object' ? column.name : column;
                const columnType = typeof column === 'object' ? column.type : 'number';
                // Check if this is a variable column (new structure: is_variable, or legacy: type === 'variable')
                const isVariable = typeof column === 'object' && (column.is_variable === true || column.type === 'variable');

                if (isVariable) {
                    const variableSaveValue = typeof column === 'object' ? (column.variable_save_value !== false) : true;

                    if (!variableSaveValue) {
                        // Remove all cell keys for this column
                        Object.keys(dataToSave).forEach(cellKey => {
                            if (cellKey.endsWith(`_${columnName}`)) {
                                delete dataToSave[cellKey];
                                debugLog('matrix-handler', `Excluded variable column ${columnName} from saved data (save_value=false)`);
                            }
                        });
                    }
                }
            });

            // Refresh hidden field reference (may have changed)
            matrix.hiddenField = matrix.container.querySelector('input[type="hidden"]');

            if (matrix.hiddenField) {
                // Update the hidden field with filtered matrix data
                matrix.hiddenField.value = __serializeMatrixData(dataToSave);
                debugLog(`MatrixHandler: Collected data for matrix ${fieldId}`, dataToSave);
            }
        });
    }

    /**
     * Reset matrix data
     */
    resetMatrix(fieldId) {
        const matrix = this.matrices.get(fieldId);
        if (!matrix) return;

        const container = matrix.container;

        // Clear all inputs
        const inputs = container.querySelectorAll('input[type="number"], input[data-numeric="true"]');
        inputs.forEach(input => {
            input.value = '';
        });

        // Clear data
        matrix.data = {};

        // Clear totals
        this.clearMatrixTotals(fieldId);

        // Cache hidden field reference if not already cached
        if (!matrix.hiddenField) {
            matrix.hiddenField = container.querySelector('input[type="hidden"]');
        }

        // Update hidden field
        if (matrix.hiddenField) {
            matrix.hiddenField.value = '';
        }

        debugLog(`MatrixHandler: Reset matrix ${fieldId}`);
    }

    /**
     * Get matrix data for a specific field
     */
    getMatrixData(fieldId) {
        const matrix = this.matrices.get(fieldId);
        return matrix ? matrix.data : {};
    }

    /**
     * Set matrix data for a specific field
     */
    setMatrixData(fieldId, data) {
        const matrix = this.matrices.get(fieldId);
        if (!matrix) return;

        matrix.data = data;

        // Update inputs
        const container = matrix.container;
        Object.entries(data).forEach(([cellKey, value]) => {
            if (cellKey.startsWith('_')) return;
            const input = container.querySelector(`input[data-cell-key="${cellKey}"]`);
            if (input) {
                const displayValue = (typeof value === 'object' && value != null && 'original' in value)
                    ? (value.modified != null ? value.modified : value.original)
                    : value;
                if (input.type === 'checkbox') {
                    const checked = displayValue === '1' || displayValue === 1 || displayValue === 'true' || displayValue === true;
                    input.checked = checked;
                } else {
                    input.value = displayValue != null ? String(displayValue) : '';
                    if (typeof window.__numericFormatInPlace === 'function') window.__numericFormatInPlace(input);
                }
            }
        });

        // Recalculate totals
        this.calculateMatrixTotals(fieldId);

        // Remove metadata keys before writing hidden field.
        this.sanitizeMatrixData(matrix);

        // Cache hidden field reference if not already cached
        if (!matrix.hiddenField) {
            matrix.hiddenField = container.querySelector('input[type="hidden"]');
        }

        // Update hidden field
        if (matrix.hiddenField) {
            matrix.hiddenField.value = __serializeMatrixData(matrix.data);
        }

        debugLog(`MatrixHandler: Set data for matrix ${fieldId}`, matrix.data);
    }

    /**
     * Handle keyboard navigation in matrix
     * Supports both manual mode (config.rows) and list library mode (dynamic rows from DOM)
     */
    handleKeyboardNavigation(e) {
        const input = e.target;
        const container = input.closest('.matrix-container');
        if (!container) return;

        const fieldId = container.dataset.fieldId;
        const matrix = this.matrices.get(fieldId);
        if (!matrix) return;

        const config = matrix.config;
        const columns = config.columns || [];

        // Get rows from DOM for both modes (supports dynamic rows)
        const rowElements = container.querySelectorAll('tr.matrix-data-row');
        const rows = Array.from(rowElements).map(tr => {
            return tr.getAttribute('data-row-label') || tr.querySelector('td[role="rowheader"]')?.textContent?.trim();
        }).filter(Boolean);

        // Fallback to config rows if DOM has no rows (shouldn't happen, but safety check)
        const availableRows = rows.length > 0 ? rows : (config.rows || []);

        const currentRow = input.dataset.row;
        const currentColumn = input.dataset.column;

        let newRow = currentRow;
        let newColumn = currentColumn;
        let handled = false;

        switch (e.key) {
            case 'ArrowUp':
                e.preventDefault();
                const currentRowIndex = availableRows.indexOf(currentRow);
                if (currentRowIndex > 0) {
                    newRow = availableRows[currentRowIndex - 1];
                    handled = true;
                }
                break;

            case 'ArrowDown':
                e.preventDefault();
                const currentRowIndexDown = availableRows.indexOf(currentRow);
                if (currentRowIndexDown < availableRows.length - 1) {
                    newRow = availableRows[currentRowIndexDown + 1];
                    handled = true;
                }
                break;

            case 'ArrowLeft':
                e.preventDefault();
                const currentColIndex = columns.map(col => typeof col === 'object' ? col.name : col).indexOf(currentColumn);
                if (currentColIndex > 0) {
                    newColumn = columns[currentColIndex - 1];
                    newColumn = typeof newColumn === 'object' ? newColumn.name : newColumn;
                    handled = true;
                }
                break;

            case 'ArrowRight':
                e.preventDefault();
                const currentColIndexRight = columns.map(col => typeof col === 'object' ? col.name : col).indexOf(currentColumn);
                if (currentColIndexRight < columns.length - 1) {
                    newColumn = columns[currentColIndexRight + 1];
                    newColumn = typeof newColumn === 'object' ? newColumn.name : newColumn;
                    handled = true;
                }
                break;

            case 'Tab':
                // Let default tab behavior handle this
                break;

            case 'Enter':
                e.preventDefault();
                // Move to next row, same column
                const currentRowIndexEnter = availableRows.indexOf(currentRow);
                if (currentRowIndexEnter < availableRows.length - 1) {
                    newRow = availableRows[currentRowIndexEnter + 1];
                    handled = true;
                }
                break;
        }

        if (handled && (newRow !== currentRow || newColumn !== currentColumn)) {
            const newInput = container.querySelector(`input[data-row="${newRow}"][data-column="${newColumn}"]`);
            if (newInput) {
                newInput.focus();
                newInput.select();
                this.currentFocusedCell = newInput;
            } else {
                debugWarn('matrix-handler', `Could not find input for row="${newRow}", column="${newColumn}"`);
            }
        }
    }

    /**
     * Validate a single matrix input
     */
    validateMatrixInput(input) {
        const container = input.closest('.matrix-container');
        const fieldId = container?.dataset?.fieldId;
        if (!fieldId) return;

        const matrix = this.matrices.get(fieldId);
        if (!matrix) return;

        const value = parseFloat(window.__numericUnformat ? window.__numericUnformat(input.value) : input.value);
        const errors = [];

        // Check if value is valid number
        if (input.value && isNaN(value)) {
            errors.push('Please enter a valid number');
        }

        // Check if value is negative
        if (!isNaN(value) && value < 0) {
            errors.push('Value cannot be negative');
        }

        // Check if value is too large (optional)
        if (!isNaN(value) && value > 999999999) {
            errors.push('Value is too large');
        }

        if (errors.length > 0) {
            this.showInputError(input, errors[0]);
            return false;
        }

        this.clearInputError(input);
        return true;
    }

    /**
     * Validate all matrices
     */
    validateAllMatrices() {
        let allValid = true;

        this.matrices.forEach((matrix, fieldId) => {
            // Skip validation if container is no longer in DOM
            if (!matrix.container.isConnected) {
                debugLog('matrix-handler', `Matrix container for ${fieldId} is no longer in DOM, cleaning up and skipping validation`);
                this.cleanupMatrix(fieldId);
                return;
            }

            const container = matrix.container;
            const inputs = container.querySelectorAll('input[type="number"], input[data-numeric="true"]');
            let matrixValid = true;

            inputs.forEach(input => {
                if (!this.validateMatrixInput(input)) {
                    matrixValid = false;
                    allValid = false;
                }
            });

            // Check if required matrix has any data
            if (matrix.config.is_required) {
                const hasData = this.hasMatrixData(fieldId);
                if (!hasData) {
                    this.showMatrixError(fieldId, 'This field is required. Please enter at least one value.');
                    allValid = false;
                } else {
                    this.clearMatrixError(fieldId);
                }
            } else {
                this.clearMatrixError(fieldId);
            }
        });

        return allValid;
    }

    /**
     * Check if matrix has any data
     */
    hasMatrixData(fieldId) {
        const matrix = this.matrices.get(fieldId);
        if (!matrix) return false;

        const data = matrix.data;
        return Object.values(data).some(value => value && value > 0);
    }

    /**
     * Show error for a specific input
     */
    showInputError(input, message) {
        input.classList.add('border-red-500', 'focus:ring-red-500', 'focus:border-red-500');
        input.classList.remove('focus:ring-blue-500', 'focus:border-blue-500');

        // Add error message near the input
        let errorElement = input.parentNode.querySelector('.input-error-message');
        if (!errorElement) {
            errorElement = document.createElement('div');
            errorElement.className = 'input-error-message text-red-600 text-xs mt-1';
            input.parentNode.appendChild(errorElement);
        }
        errorElement.textContent = message;
        errorElement.style.display = 'block';
    }

    /**
     * Clear error for a specific input
     */
    clearInputError(input) {
        input.classList.remove('border-red-500', 'focus:ring-red-500', 'focus:border-red-500');
        input.classList.add('focus:ring-blue-500', 'focus:border-blue-500');

        const errorElement = input.parentNode.querySelector('.input-error-message');
        if (errorElement) {
            errorElement.style.display = 'none';
        }
    }

    /**
     * Show error for entire matrix
     */
    showMatrixError(fieldId, message) {
        const matrix = this.matrices.get(fieldId);
        if (!matrix) return;

        const container = matrix.container;
        const errorElement = container.querySelector('#matrix-error-' + fieldId);
        if (errorElement) {
            errorElement.textContent = message;
            errorElement.style.display = 'block';
        }
    }

    /**
     * Clear error for entire matrix
     */
    clearMatrixError(fieldId) {
        const matrix = this.matrices.get(fieldId);
        if (!matrix) return;

        const container = matrix.container;
        const errorElement = container.querySelector('#matrix-error-' + fieldId);
        if (errorElement) {
            errorElement.style.display = 'none';
        }
    }

    /**
     * Announce total updates to screen readers
     */
    announceTotalUpdate(fieldId, type, value, context) {
        const matrix = this.matrices.get(fieldId);
        if (!matrix) return;

        const container = matrix.container;
        const announceElement = container.querySelector('#matrix-totals-announce-' + fieldId);
        if (announceElement) {
            let message = '';
            switch (type) {
                case 'row':
                    message = `Row ${context} total: ${value}`;
                    break;
                case 'column':
                    message = `Column ${context} total: ${value}`;
                    break;
                case 'grand':
                    message = `Matrix grand total: ${value}`;
                    break;
            }
            announceElement.textContent = message;
        }
    }

    /**
     * Helper: Find results container for a given fieldId (works with repeat sections)
     */
    _findResultsContainer(fieldId) {
        debugLog('matrix-handler', '[FIND RESULTS] Looking for results container', { fieldId });

        // First try by ID directly
        let resultsContainer = document.getElementById(`matrix-search-results-${fieldId}`);
        debugLog('matrix-handler', '[FIND RESULTS] Direct ID search', {
            searchedId: `matrix-search-results-${fieldId}`,
            found: !!resultsContainer,
            foundId: resultsContainer?.id
        });

        if (!resultsContainer) {
            // Find via matrix container (works with repeat sections where IDs are transformed)
            const matrix = this.matrices.get(fieldId);
            debugLog('matrix-handler', '[FIND RESULTS] Checking matrix map', {
                fieldId,
                hasMatrix: !!matrix,
                hasContainer: !!(matrix && matrix.container),
                containerId: matrix?.container?.id
            });

            if (matrix && matrix.container) {
                // The results container is a direct child of .matrix-container (position:absolute).
                // For repeat sections the ID is transformed, so fall back to a query.
                resultsContainer = matrix.container.querySelector('[id*="matrix-search-results-"]');

                debugLog('matrix-handler', '[FIND RESULTS] Container query result', {
                    found: !!resultsContainer,
                    foundId: resultsContainer?.id
                });
            }
        }

        return resultsContainer;
    }

    /**
     * Helper: Find search input for a given fieldId (works with repeat sections)
     */
    _findSearchInput(fieldId) {
        // First try by ID directly
        let searchInput = document.getElementById(`matrix-row-search-${fieldId}`);

        if (!searchInput) {
            // Find via matrix container (works with repeat sections where IDs are transformed)
            const matrix = this.matrices.get(fieldId);
            if (matrix && matrix.container) {
                searchInput = matrix.container.querySelector('.matrix-add-row-interface input[type="text"]');
            }
        }

        return searchInput;
    }

    /**
     * Show search dropdown
     */
    showSearchDropdown(searchInput) {
        const fieldId = searchInput.dataset.fieldId;
        const resultsContainer = fieldId ? this._findResultsContainer(fieldId) : null;

        if (resultsContainer) {
            this._positionAndShowDropdown(searchInput, resultsContainer);
            if (!searchInput.value.trim()) {
                this.loadInitialSearchResults(searchInput);
            }
        } else {
            debugWarn('matrix-handler', '[SHOW DROPDOWN] Results container not found', { fieldId });
        }
    }

    /**
     * Position and show dropdown (helper method).
     *
     * The results container is position:absolute inside the position:relative
     * .matrix-container, so it grows the page height instead of overlaying
     * content as a fixed overlay.  The user can scroll the page to see both
     * the matrix and the full list at the same time.
     */
    _positionAndShowDropdown(searchInput, resultsContainer) {
        const matrixContainer = searchInput.closest('.matrix-container');
        if (!matrixContainer) {
            resultsContainer.classList.remove('hidden');
            return;
        }

        const inputRect = searchInput.getBoundingClientRect();
        const containerRect = matrixContainer.getBoundingClientRect();

        // Coordinates are relative to .matrix-container (which is position:relative).
        // Always place below the search input — never flip above.
        const top = inputRect.bottom - containerRect.top + 2;
        const left = inputRect.left - containerRect.left;

        resultsContainer.style.position = 'absolute';
        resultsContainer.style.top = `${top}px`;
        resultsContainer.style.left = `${left}px`;
        resultsContainer.style.width = `${inputRect.width}px`;
        resultsContainer.style.bottom = '';
        resultsContainer.style.maxHeight = '';
        resultsContainer.style.overflowY = '';

        resultsContainer.classList.remove('hidden');
    }

    /**
     * Re-render dropdown results after a selection (keeps dropdown open)
     */
    _refreshDropdownResults(searchInput, fieldId) {
        const resultsContainer = fieldId ? this._findResultsContainer(fieldId) : null;
        if (resultsContainer) {
            this._positionAndShowDropdown(searchInput, resultsContainer);
        }
        // Re-run the same search the user had active; fall back to loading all.
        if (searchInput.value.trim()) {
            this.handleSearchInput(searchInput);
        } else {
            this.loadInitialSearchResults(searchInput);
        }
    }

    /**
     * Hide search dropdown
     */
    hideSearchDropdown(searchInput) {
        const fieldId = searchInput.dataset.fieldId;
        const resultsContainer = fieldId ? this._findResultsContainer(fieldId) : null;
        if (resultsContainer) {
            resultsContainer.classList.add('hidden');
        }
    }

    /**
     * Reposition visible dropdowns on scroll/resize.
     *
     * With position:absolute inside the matrix-container the dropdown follows
     * the page scroll automatically.  We only need to recalculate left/top/width
     * (e.g. after a window resize changes the layout).
     */
    repositionVisibleDropdowns() {
        const visibleDropdowns = document.querySelectorAll('[id*="matrix-search-results-"]:not(.hidden)');

        visibleDropdowns.forEach(dropdown => {
            const matrixContainer = dropdown.closest('.matrix-container');
            if (!matrixContainer) return;

            const searchInput = matrixContainer.querySelector('.matrix-add-row-interface input[type="text"]');
            if (!searchInput) return;

            const inputRect = searchInput.getBoundingClientRect();
            const containerRect = matrixContainer.getBoundingClientRect();

            dropdown.style.top = `${inputRect.bottom - containerRect.top + 2}px`;
            dropdown.style.left = `${inputRect.left - containerRect.left}px`;
            dropdown.style.width = `${inputRect.width}px`;
        });
    }

    /**
     * Load initial search results when dropdown opens
     */
    async loadInitialSearchResults(searchInput) {
        const fieldId = searchInput.dataset.fieldId;
        const lookupListId = searchInput.dataset.lookupListId;
        const displayColumn = searchInput.dataset.displayColumn;
        const filters = JSON.parse(searchInput.dataset.filters || '[]');

        if (!lookupListId || !displayColumn) {
            this.showDropdownMessage(fieldId, 'Matrix configuration is incomplete');
            return;
        }

        this.showDropdownMessage(fieldId, 'Loading...', true);
        await this.searchListOptions(fieldId, lookupListId, displayColumn, filters, '');
    }

    /**
     * Handle search input for row selection
     */
    async handleSearchInput(searchInput) {
        const fieldId = searchInput.dataset.fieldId;
        const lookupListId = searchInput.dataset.lookupListId;
        const displayColumn = searchInput.dataset.displayColumn;
        const filters = JSON.parse(searchInput.dataset.filters || '[]');
        const searchTerm = searchInput.value.trim();

        // Show dropdown if hidden
        this.showSearchDropdown(searchInput);

        // Debounce search
        clearTimeout(this.searchTimeout);
        this.searchTimeout = setTimeout(() => {
            this.searchListOptions(fieldId, lookupListId, displayColumn, filters, searchTerm);
        }, 300);
    }

    /**
     * Search list options via API
     */
    async searchListOptions(fieldId, lookupListId, displayColumn, filters, searchTerm) {
        if (!lookupListId || !displayColumn) {
            debugError('matrix-handler', 'Missing required parameters for search', { lookupListId, displayColumn });
            this.showDropdownMessage(fieldId, 'Matrix configuration is incomplete');
            return;
        }

        const csrfToken = this.getCsrfToken();
        if (!csrfToken) {
            debugError('matrix-handler', 'CSRF token missing for API request');
            this.showDropdownMessage(fieldId, 'Authentication error. Please refresh the page.');
            return;
        }

        try {
            // Get assignment entity status ID for country-aware plugins (e.g., emergency_operations)
            const assignmentEntityStatusId = this.getAssignmentEntityStatusId();

            // Get plugin configuration from matrix config if available
            let matrix = this.matrices.get(fieldId);

            // If matrix not found, try to re-initialize it from the container
            if (!matrix) {
                const container = document.querySelector(`.matrix-container[data-field-id="${fieldId}"]`);
                if (container) {
                    // Re-initialize this specific matrix
                    const configData = container.dataset.matrixConfig || '{}';
                    let config = JSON.parse(configData);
                    let matrixConfig;
                    if (config.matrix_config) {
                        matrixConfig = { ...config.matrix_config, is_required: config.is_required };
                    } else {
                        matrixConfig = config;
                    }
                    const existingData = this.parseExistingData(container);
                    const hiddenField = container.querySelector('input[type="hidden"][name^="field_value"]') ||
                                        container.querySelector('input[type="hidden"]');
                    matrix = {
                        container,
                        config: matrixConfig,
                        data: existingData,
                        hiddenField: hiddenField
                    };
                    this.matrices.set(fieldId, matrix);
                }
            }

            const pluginConfig = (matrix && matrix.config && matrix.config.plugin_config) ? matrix.config.plugin_config : null;

            const requestBody = {
                lookup_list_id: lookupListId,
                display_column: displayColumn,
                filters: filters,
                search_term: searchTerm,
                existing_rows: this.getExistingRows(fieldId)
            };

            // Include assignment_entity_status_id if available (for country filtering)
            if (assignmentEntityStatusId) {
                requestBody.assignment_entity_status_id = assignmentEntityStatusId;
            }

            // Include plugin_config if available (for plugin-specific filtering)
            if (pluginConfig) {
                requestBody.plugin_config = pluginConfig;
            }

            const response = await _mhFetch('/forms/matrix/search-rows', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify(requestBody)
            });

            if (!response.ok) {
                throw (window.httpErrorSync && window.httpErrorSync(response)) || new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();

            if (data.success) {
                this.renderSearchResults(fieldId, data.options);
            } else {
                const errorMsg = data.message || 'Error loading options';
                debugError('matrix-handler', 'API returned error:', errorMsg);
                this.showDropdownMessage(fieldId, errorMsg);
            }
        } catch (error) {
            debugError('matrix-handler', 'Error searching list options:', error);
            this.showDropdownMessage(fieldId, 'Error loading options. Please try again.');
        }
    }

    /**
     * Render search results in dropdown
     */
    renderSearchResults(fieldId, options) {
        const resultsContainer = this._findResultsContainer(fieldId);
        const fieldIdStr = String(fieldId || '');

        if (!resultsContainer) {
            debugWarn('matrix-handler', `Results container not found for field ${fieldId}`);
            return;
        }

        if (options.length === 0) {
            this.showDropdownMessage(fieldId, 'No options found');
            return;
        }

        // Snapshot/merge collapsed groups so state survives async refreshes (e.g. loading message).
        const collapsedGroups = new Set(this.collapsedDropdownGroups.get(fieldIdStr) || []);
        resultsContainer.querySelectorAll('.matrix-group-header').forEach(header => {
            const groupItems = header.nextElementSibling;
            if (groupItems && groupItems.classList.contains('matrix-group-items') && groupItems.classList.contains('hidden')) {
                collapsedGroups.add((header.querySelector('span')?.textContent ?? '').trim());
            }
        });
        this.collapsedDropdownGroups.set(fieldIdStr, collapsedGroups);

        resultsContainer.replaceChildren();

        const matrix = this.matrices.get(fieldId);
        const groupByColumn = matrix?.config?.group_by_column;
        const groupDropdownEnabled = matrix?.config?.group_dropdown_enabled !== false;

        // Build a reference to the live table body so we can mark already-added rows.
        const matrixContainer = matrix?.container || document.querySelector(`[data-field-id="${String(fieldId || '')}"]`);
        let tbody = document.getElementById(`matrix-tbody-${fieldId}`);
        if (!tbody && matrixContainer) {
            tbody = matrixContainer.querySelector('tbody[id*="matrix-tbody-"]') || matrixContainer.querySelector('tbody');
        }

        const createOptionEl = (option) => {
            const optionData = option.data || {};
            if (!optionData._id && !optionData.id && option.id) {
                optionData._id = option.id;
                optionData.id = option.id;
            }
            const item = document.createElement('div');
            item.className = 'p-3 hover:bg-blue-50 cursor-pointer border-b border-gray-100 matrix-search-option';
            item.dataset.fieldId = String(fieldId || '');
            item.dataset.optionValue = String(option.value || '');
            try { item.dataset.optionData = JSON.stringify(optionData); }
            catch (e) { item.dataset.optionData = JSON.stringify({}); }

            const title = document.createElement('div');
            title.className = 'font-medium text-sm flex items-center';
            title.textContent = String(option.value || '');
            item.appendChild(title);

            if (option.description) {
                const desc = document.createElement('div');
                desc.className = 'text-xs text-gray-600 mt-1';
                desc.textContent = String(option.description || '');
                item.appendChild(desc);
            }

            // Mark rows that are already in the matrix table.
            if (tbody) {
                const optionId = String(optionData._id || optionData.id || '');
                const label = String(option.value || '');
                const alreadyAdded = Array.from(tbody.querySelectorAll('tr.matrix-data-row')).some(tr =>
                    (optionId && tr.dataset.rowId === optionId) || tr.dataset.rowLabel === label
                );
                if (alreadyAdded) {
                    item.classList.add('opacity-50', 'pointer-events-none');
                    const checkIcon = document.createElement('i');
                    checkIcon.className = 'fas fa-check text-green-600 ml-2 flex-shrink-0';
                    title.appendChild(checkIcon);
                }
            }

            return item;
        };

        if (groupByColumn && groupDropdownEnabled) {
            const groups = new Map();
            options.forEach(option => {
                const groupVal = (option.data && option.data[groupByColumn]) || 'Other';
                if (!groups.has(groupVal)) groups.set(groupVal, []);
                groups.get(groupVal).push(option);
            });

            groups.forEach((groupOptions, groupName) => {
                const groupNameKey = String(groupName || '').trim();
                const header = document.createElement('div');
                header.className = 'px-3 py-2 bg-gray-100 text-xs font-semibold text-gray-700 cursor-pointer flex items-center justify-between sticky top-0 matrix-group-header';
                header.innerHTML = `<span>${this._escapeHtml(groupName)}</span><i class="fas fa-chevron-down text-gray-400 transition-transform duration-200"></i>`;
                const groupContainer = document.createElement('div');
                groupContainer.className = 'matrix-group-items';
                groupOptions.forEach(option => groupContainer.appendChild(createOptionEl(option)));

                header.addEventListener('click', () => {
                    const isHidden = groupContainer.classList.toggle('hidden');
                    header.querySelector('i').classList.toggle('rotate-180', !isHidden);
                    const currentCollapsedGroups = this.collapsedDropdownGroups.get(fieldIdStr) || new Set();
                    if (isHidden) {
                        currentCollapsedGroups.add(groupNameKey);
                    } else {
                        currentCollapsedGroups.delete(groupNameKey);
                    }
                    this.collapsedDropdownGroups.set(fieldIdStr, currentCollapsedGroups);
                });

                resultsContainer.appendChild(header);
                resultsContainer.appendChild(groupContainer);
            });

            // Restore group collapse state from before the re-render.
            if (collapsedGroups.size > 0) {
                resultsContainer.querySelectorAll('.matrix-group-header').forEach(header => {
                    const label = (header.querySelector('span')?.textContent ?? '').trim();
                    if (collapsedGroups.has(label)) {
                        header.nextElementSibling?.classList.add('hidden');
                        header.querySelector('i')?.classList.remove('rotate-180');
                    }
                });
            }
        } else {
            options.forEach(option => resultsContainer.appendChild(createOptionEl(option)));
        }
    }

    _escapeHtml(str) {
        if (str == null) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    /**
     * Show message in dropdown
     */
    showDropdownMessage(fieldId, message, isLoading = false) {
        const resultsContainer = this._findResultsContainer(fieldId);
        if (resultsContainer) {
            resultsContainer.replaceChildren();
            const wrap = document.createElement('div');
            wrap.className = 'p-3 text-gray-500 text-sm text-center';
            if (isLoading) {
                const icon = document.createElement('i');
                icon.className = 'fas fa-spinner fa-spin mr-2';
                wrap.appendChild(icon);
            }
            wrap.appendChild(document.createTextNode(String(message || '')));
            resultsContainer.appendChild(wrap);
        }
    }

    /**
     * Select row option from search results
     */
    selectRowOption(optionItem) {
        const fieldId = optionItem.dataset.fieldId;
        const optionValue = optionItem.dataset.optionValue;
        const optionData = JSON.parse(optionItem.dataset.optionData);

        // Get row ID from optionData using helper method
        const rowId = this.extractRowId(optionData, optionValue);

        // Debug logging
        debugLog('matrix-handler', `Selecting row option:`, {
            fieldId,
            optionValue,
            optionData,
            extractedRowId: rowId,
            has_id: !!optionData?.id,
            has__id: !!optionData?._id
        });

        // Add row to matrix with ID (manually added, so isAutoLoaded=false)
        debugLog('matrix-handler', '[SELECT ROW OPTION] About to call addDynamicRow', {
            fieldId,
            optionValue,
            rowId,
            optionDataKeys: Object.keys(optionData)
        });
        this.addDynamicRow(fieldId, optionValue, optionData, rowId, false);
        debugLog('matrix-handler', '[SELECT ROW OPTION] addDynamicRow completed');

        // Sort rows alphabetically after manual add, then reposition dropdown after reflow
        setTimeout(() => {
            this.sortMatrixRows(fieldId);
            this.applyManualRowHighlighting(fieldId);
            this.updateLegendVisibility(fieldId);
            // Wait for the browser to reflow the taller table before repositioning
            requestAnimationFrame(() => this.repositionVisibleDropdowns());
        }, 50);

        // Mark selected item visually and keep dropdown open for multi-select
        optionItem.classList.add('opacity-50', 'pointer-events-none');
        optionItem.insertAdjacentHTML('beforeend', '<i class="fas fa-check text-green-600 ml-auto"></i>');

        const searchInput = this._findSearchInput(fieldId);
        if (searchInput) {
            // Do NOT clear the input — preserve the user's search term so the
            // dropdown re-renders the same filtered list after selection.
            this._refreshDropdownResults(searchInput, fieldId);
            // Re-focus so the blur handler's active-element check passes and the
            // dropdown stays open for multi-select without requiring another click.
            searchInput.focus();
        }
    }

    /**
     * Add dynamic row to matrix
     * @param {string} fieldId - Matrix field ID
     * @param {string} rowLabel - Row label/name
     * @param {Object} rowData - Row data object
     * @param {string|null} rowId - Row ID (optional)
     * @param {boolean} isAutoLoaded - Whether this row was auto-loaded (default: false)
     */
    addDynamicRow(fieldId, rowLabel, rowData, rowId = null, isAutoLoaded = false) {
        const fieldIdStr = String(fieldId || '');
        const container = document.querySelector(`[data-field-id="${fieldIdStr}"]`);

        // Find tbody - try by ID first, then via container (works with repeat sections)
        let tbody = document.getElementById(`matrix-tbody-${fieldIdStr}`);
        if (!tbody && container) {
            // Find tbody within container (works with repeat sections where IDs are transformed)
            tbody = container.querySelector('tbody[id*="matrix-tbody-"]') || container.querySelector('tbody');
        }

        // Ensure matrix is registered (important when matrices are injected after initial init)
        let matrixInfo = this.matrices.get(fieldIdStr);
        if (container && (!matrixInfo || !matrixInfo.config || !matrixInfo.config.columns)) {
            matrixInfo = this._registerMatrixFromDom(container, fieldIdStr) || matrixInfo;
        }
        // If we have a matrix record but the container changed (dynamic DOM), keep it in sync
        if (matrixInfo && container && matrixInfo.container !== container) {
            matrixInfo.container = container;
        }

        debugLog('matrix-handler', '[ADD DYNAMIC ROW] Finding elements', {
            fieldId: fieldIdStr,
            hasContainer: !!container,
            foundTbody: !!tbody,
            tbodyId: tbody?.id,
            hasMatrixInfo: !!matrixInfo,
            hasColumns: !!(matrixInfo && matrixInfo.config && matrixInfo.config.columns)
        });

        if (!tbody || !matrixInfo || !matrixInfo.config.columns) {
            debugWarn('matrix-handler', '[ADD DYNAMIC ROW] Missing required elements', {
                hasTbody: !!tbody,
                hasMatrixInfo: !!matrixInfo,
                hasColumns: !!(matrixInfo && matrixInfo.config && matrixInfo.config.columns),
                containerId: container?.id
            });
            return;
        }

        const columns = matrixInfo.config.columns;

        // Get row ID from rowData using helper method
        const finalRowId = this.extractRowId(rowData, rowLabel, rowId);

        // Debug logging
        debugLog('matrix-handler', `Adding dynamic row:`, {
            fieldId,
            rowLabel,
            providedRowId: rowId,
            rowData_id: rowData?.id,
            rowData__id: rowData?._id,
            finalRowId
        });

        // Check if row already exists (by ID if available, otherwise by label)
        const existingRow = finalRowId !== rowLabel
            ? tbody.querySelector(`tr[data-row-id="${finalRowId}"]`)
            : tbody.querySelector(`tr[data-row-label="${rowLabel}"]`);
        if (existingRow) {
            debugLog('matrix-handler', `Row already exists, skipping: ${rowLabel} (ID: ${finalRowId})`);
            return;
        }

        // Create new row
        const row = document.createElement('tr');
        row.className = 'matrix-data-row group';
        row.setAttribute('role', 'row');
        row.setAttribute('data-row-label', rowLabel);
        row.setAttribute('data-row-id', finalRowId);
        row.setAttribute('data-row-data', JSON.stringify(rowData));
        row.setAttribute('data-is-auto-loaded', isAutoLoaded ? 'true' : 'false');
        const groupByCol = matrixInfo.config?.group_by_column;
        if (groupByCol && rowData && rowData[groupByCol]) {
            row.setAttribute('data-group', rowData[groupByCol]);
        }

        // Create row header cell
        const headerCell = document.createElement('td');
        headerCell.className = 'border border-gray-300 font-medium text-gray-700 bg-gray-50';
        headerCell.setAttribute('role', 'rowheader');
        headerCell.setAttribute('scope', 'row');
        // Set dynamic width constraints: min-width for small content, max-width threshold for text wrapping
        // Width will grow naturally based on content and available space, but wrap at 400px threshold
        headerCell.style.minWidth = '80px';
        headerCell.style.maxWidth = '400px';
        headerCell.style.wordWrap = 'break-word';
        headerCell.style.overflowWrap = 'break-word';
        headerCell.style.whiteSpace = 'normal';
        headerCell.style.verticalAlign = 'middle';

        // Apply beige highlight to row header if this is a manually added row and highlighting is enabled
        const matrix = this.matrices.get(fieldIdStr);
        const autoLoadEnabled = __configFlag(matrix?.config?.auto_load_entities, false);
        const highlightManualRows = __configFlag(matrix?.config?.highlight_manual_rows, autoLoadEnabled);
        if (matrix && matrix.config && highlightManualRows && !isAutoLoaded) {
            headerCell.style.backgroundColor = '#f5f5dc'; // Beige color
            headerCell.classList.add('matrix-manual-row-header');
        }

        // Create a wrapper div for the row label and button to ensure proper layout
        const labelWrapper = document.createElement('div');
        labelWrapper.style.display = 'flex';
        labelWrapper.style.alignItems = 'center';
        labelWrapper.style.flexWrap = 'wrap';
        labelWrapper.style.gap = '4px';

        const labelSpan = document.createElement('span');
        labelSpan.textContent = rowLabel;
        labelSpan.style.wordWrap = 'break-word';
        labelSpan.style.overflowWrap = 'break-word';
        labelWrapper.appendChild(labelSpan);

        // Only add remove button for manually added rows (not auto-loaded)
        if (!isAutoLoaded) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'remove-matrix-row-btn ml-2 text-red-600 hover:text-red-800 text-xs opacity-0 group-hover:opacity-100 transition-opacity duration-200 flex-shrink-0';
            btn.title = 'Remove row';

            const icon = document.createElement('i');
            icon.className = 'fas fa-times w-3 h-3';
            btn.appendChild(icon);

            labelWrapper.appendChild(btn);
        }

        headerCell.appendChild(labelWrapper);
        row.appendChild(headerCell);

        // Create data cells
        columns.forEach((column, columnIndex) => {
            const columnName = typeof column === 'object' ? column.name : column;
            const columnType = typeof column === 'object' ? column.type : 'number';
            const columnDisplayName = this.getColumnDisplayName(column);
            // Check if this is a variable column (new structure: is_variable, or legacy: type === 'variable')
            const isVariable = typeof column === 'object' && (column.is_variable === true || column.type === 'variable');

            // Determine if this is a readonly variable column
            const isReadonlyVariable = isVariable &&
                (typeof column === 'object' ? (column.variable_readonly !== false) : true);

            const cell = document.createElement('td');
            cell.className = `border border-gray-300 px-2 py-1${columnType === 'tick' ? ' text-center' : ''}${isReadonlyVariable ? ' bg-gray-100' : ''}`;
            cell.setAttribute('role', 'gridcell');

            // Use row ID instead of row label for the cell key
            const cellKey = `${finalRowId}_${columnName}`;
            const input = document.createElement('input');

            if (isVariable) {
                // Variable column - type can be number or tick, will be resolved via API
                const variableName = typeof column === 'object' ? (column.variable || column.variable_name) : null;
                const variableReadonly = typeof column === 'object' ? (column.variable_readonly !== false) : true;
                const variableSaveValue = typeof column === 'object' ? (column.variable_save_value !== false) : true;

                if (columnType === 'tick') {
                    // Variable tick column
                    input.type = 'checkbox';
                    input.className = `w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500 mx-auto${variableReadonly ? ' opacity-50' : ''}`;
                    input.value = '1';
                    input.disabled = variableReadonly; // Use disabled for checkboxes (readOnly doesn't work)
                    input.setAttribute('data-column-type', 'variable');
                    input.setAttribute('data-variable-name', variableName || '');
                    input.setAttribute('data-variable-save-value', variableSaveValue ? 'true' : 'false');
                    input.setAttribute('data-variable-readonly', variableReadonly ? 'true' : 'false');
                    input.setAttribute('aria-label', `Variable tick for ${rowLabel} and ${columnDisplayName}`);
                } else {
                    // Variable number column
                    input.type = 'number';
                input.className = variableReadonly
                    ? 'w-full px-2 py-1 border-0 bg-transparent focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500'
                    : 'w-full px-2 py-1 border-0 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500';
                    input.min = '0';
                    input.step = '0.01';
                input.value = '';
                input.disabled = variableReadonly; // Use disabled to prevent editing (readOnly can sometimes be bypassed)
                input.setAttribute('data-column-type', 'variable');
                input.setAttribute('data-variable-name', variableName || '');
                input.setAttribute('data-variable-save-value', variableSaveValue ? 'true' : 'false');
                input.setAttribute('data-variable-readonly', variableReadonly ? 'true' : 'false');
                input.setAttribute('aria-label', `Variable value for ${rowLabel} and ${columnDisplayName}`);
                }
            } else if (columnType === 'tick') {
                input.type = 'checkbox';
                input.className = 'w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500 mx-auto';
                input.value = '1';
                input.setAttribute('data-column-type', 'tick');
                input.setAttribute('aria-label', `Tick for ${rowLabel} and ${columnDisplayName}`);
            } else {
                input.type = 'number';
                input.className = 'w-full px-2 py-1 border-0 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500';
                input.min = '0';
                input.step = '0.01';
                input.value = '';
                input.setAttribute('data-column-type', 'number');
                input.setAttribute('aria-label', `Value for ${rowLabel} and ${columnDisplayName}`);
            }

            input.setAttribute('data-row', rowLabel);
            input.setAttribute('data-row-id', finalRowId);
            input.setAttribute('data-column', columnName);
            input.setAttribute('data-cell-key', cellKey);

            cell.appendChild(input);
            row.appendChild(cell);
        });

        // Create total cell if needed
        if (matrixInfo.config.show_row_totals !== false) {
            const totalCell = document.createElement('td');
            totalCell.className = 'border border-gray-300 px-2 py-1 bg-gray-100';
            totalCell.setAttribute('role', 'gridcell');

            const totalSpan = document.createElement('span');
            totalSpan.className = 'matrix-row-total inline-block w-full px-2 py-1 text-center text-sm font-medium';
            totalSpan.setAttribute('data-row', rowLabel);
            totalSpan.setAttribute('data-row-id', finalRowId);
            totalSpan.setAttribute('aria-label', `Total for row ${rowLabel}`);
            totalSpan.textContent = '0';

            totalCell.appendChild(totalSpan);
            row.appendChild(totalCell);
        }

        // Insert row before search interface, totals row, or at end
        const searchInterface = tbody.querySelector('.matrix-add-row-interface');
        const totalsRow = tbody.querySelector('tr .matrix-column-total')?.closest('tr');

        if (searchInterface) {
            // Insert before search interface (last row)
            tbody.insertBefore(row, searchInterface);
        } else if (totalsRow) {
            // Insert before totals row
            tbody.insertBefore(row, totalsRow);
        } else {
            tbody.appendChild(row);
        }

        // Update totals and hidden data
        this.calculateMatrixTotals(fieldIdStr);

        // Defer variable resolution to batch with other rows
        // This prevents individual API calls for each row
        this.scheduleVariableResolution(fieldIdStr);

        debugLog('matrix-handler', `Added dynamic row "${rowLabel}" to matrix ${fieldIdStr}`);
    }

    /**
     * Schedule variable resolution for a matrix (batched)
     * This debounces resolution so multiple rows added quickly are resolved in one batch
     */
    scheduleVariableResolution(fieldId) {
        // Don't schedule if a batch operation is in progress (restore/auto-load)
        // The batch operation will resolve all rows at the end
        if (this.batchOperationsInProgress.has(fieldId)) {
            return;
        }

        // Verify matrix exists before scheduling (it might have been removed)
        const matrix = this.matrices.get(fieldId);
        if (!matrix || !matrix.container) {
            debugLog('matrix-handler', '[BATCH VARIABLE RESOLUTION] Matrix not found, skipping schedule', { fieldId });
            return;
        }

        // Clear existing timer for this field (if any)
        if (this.variableResolutionDebounceTimers.has(fieldId)) {
            clearTimeout(this.variableResolutionDebounceTimers.get(fieldId));
        }

        // Mark that this field has pending resolution
        this.pendingVariableResolution.set(fieldId, true);

        // Schedule batch resolution after a short delay
        // This allows multiple rows to be added quickly before resolving
        // The timer is reset each time a new row is added, so only the last timer fires
        this.variableResolutionDebounceTimers.set(fieldId, setTimeout(async () => {
            // Double-check we still have pending resolution and no batch operation started
            if (this.pendingVariableResolution.has(fieldId) && !this.batchOperationsInProgress.has(fieldId)) {
                this.pendingVariableResolution.delete(fieldId);
                this.variableResolutionDebounceTimers.delete(fieldId);
                await this.resolveVariablesForAllRows(fieldId);
            }
        }, 200)); // 200ms debounce - allows multiple rows to be added quickly before resolving
    }

    /**
     * Batch resolve variables for all rows in a matrix (optimized)
     */
    async resolveVariablesForAllRows(fieldId) {
        const matrix = this.matrices.get(fieldId);
        if (!matrix || !matrix.container) {
            // Matrix may have been removed (e.g., form reset, page navigation)
            // This is normal and not an error, so use debug log instead of warning
            debugLog('matrix-handler', '[BATCH VARIABLE RESOLUTION] Matrix not found (may have been removed)', { fieldId });
            return;
        }

        // Get assignment entity status ID and template ID
        const assignmentEntityStatusId = this.getAssignmentEntityStatusId();
        const templateId = this.getTemplateId();

        if (!assignmentEntityStatusId || !templateId) {
            debugWarn('matrix-handler', '[BATCH VARIABLE RESOLUTION] Missing required context', {
                assignmentEntityStatusId,
                templateId
            });
            return;
        }

        // Collect all rows that have variable columns
        const dataRows = matrix.container.querySelectorAll('tr.matrix-data-row');
        const rowsToResolve = [];

        dataRows.forEach(row => {
            const rowId = row.getAttribute('data-row-id');
            const variableInputs = row.querySelectorAll('input[data-column-type="variable"]');

            if (variableInputs.length > 0 && rowId) {
                // Extract entity ID from row
                let entityId = null;
                const rowDataAttr = row.getAttribute('data-row-data');
                if (rowDataAttr) {
                    try {
                        const parsed = JSON.parse(rowDataAttr);
                        entityId = parsed.id || parsed._id || null;
                    } catch (e) {
                        // Ignore parse errors
                    }
                }

                if (!entityId) {
                    entityId = rowId;
                }

                rowsToResolve.push({
                    rowId: rowId,
                    entityId: parseInt(entityId),
                    rowElement: row,
                    variableInputs: Array.from(variableInputs)
                });
            }
        });

        if (rowsToResolve.length === 0) {
            return;
        }

        try {
            const rowEntityIds = rowsToResolve.map(r => r.entityId);

            const requestBody = {
                assignment_entity_status_id: assignmentEntityStatusId,
                template_id: templateId,
                row_entity_ids: rowEntityIds
            };

            // Call batch API
            const response = await _mhFetch('/api/v1/variables/resolve', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify(requestBody)
            });

            if (!response.ok) {
                const errorText = await response.text();
                debugError('matrix-handler', '[BATCH VARIABLE RESOLUTION] API error', {
                    status: response.status,
                    errorText
                });
                throw (window.httpErrorSync && window.httpErrorSync(response, `API error: ${response.status} ${response.statusText} - ${errorText}`)) || new Error(`API error: ${response.status} ${response.statusText} - ${errorText}`);
            }

            const data = await response.json();
            const batchResults = data.results || {};

            // Process results for each row
            rowsToResolve.forEach(rowInfo => {
                const resolvedVariables = batchResults[rowInfo.entityId] || {};
                this._applyResolvedVariablesToRow(fieldId, rowInfo.rowId, rowInfo.rowElement, rowInfo.variableInputs, resolvedVariables);
            });

            // Update matrix data and totals once after all rows are processed
            this.calculateMatrixTotals(fieldId);

        } catch (error) {
            debugError('matrix-handler', '[BATCH VARIABLE RESOLUTION] Error in batch resolution:', {
                error,
                message: error.message
            });
            // Fallback to individual resolution if batch fails
            for (const rowInfo of rowsToResolve) {
                await this.resolveVariablesForRow(fieldId, rowInfo.rowId, null);
            }
        }
    }

    /**
     * Apply resolved variables to a row's inputs (helper method)
     */
    _applyResolvedVariablesToRow(fieldId, rowEntityId, rowElement, variableInputs, resolvedVariables) {
        const matrix = this.matrices.get(fieldId);

        variableInputs.forEach((input) => {
            const variableName = input.getAttribute('data-variable-name');
            const cellKey = input.getAttribute('data-cell-key');
            const saveValue = input.getAttribute('data-variable-save-value') === 'true';

            // Check if there's a saved value and if it's been modified by the user
            let hasSavedValue = false;
            let savedIsModified = false;
            let savedDisplayValue = null;
            let savedOriginalValue = null;

            if (saveValue && cellKey && matrix && matrix.data && matrix.data[cellKey] !== undefined) {
                const savedValue = matrix.data[cellKey];
                hasSavedValue = true;

                if (typeof savedValue === 'object' && savedValue.original !== undefined) {
                    savedDisplayValue = savedValue.modified || savedValue.original;
                    savedOriginalValue = savedValue.original;
                    savedIsModified = savedValue.isModified || false;
                } else {
                    savedDisplayValue = String(savedValue || '');
                    savedOriginalValue = savedDisplayValue;
                    savedIsModified = false;
                }

                if (savedIsModified) {
                    if (input.type === 'checkbox') {
                        const checkedValue = savedDisplayValue === '1' || savedDisplayValue === 1 || savedDisplayValue === 'true' || savedDisplayValue === true;
                        input.checked = checkedValue;
                        input.setAttribute('data-original-value', savedOriginalValue);
                    } else {
                        input.value = savedDisplayValue;
                        input.setAttribute('data-original-value', savedOriginalValue);
                        if (typeof window.__numericFormatInPlace === 'function') window.__numericFormatInPlace(input);
                    }
                    this.updateVariableModificationIndicator(input, true, savedOriginalValue);
                    return; // Skip resolution, preserve user modification
                }
            }

            if (variableName && resolvedVariables.hasOwnProperty(variableName)) {
                const resolvedValue = resolvedVariables[variableName];
                const displayValue = resolvedValue !== null && resolvedValue !== undefined ? String(resolvedValue) : '';

                if (input.type === 'checkbox') {
                    const checkedValue = displayValue === '1' || displayValue === 'true' || resolvedValue === true || resolvedValue === 1;
                    input.checked = checkedValue;
                    input.setAttribute('data-original-value', checkedValue ? '1' : '0');
                } else {
                    input.value = displayValue;
                    input.setAttribute('data-original-value', displayValue);
                    if (typeof window.__numericFormatInPlace === 'function') window.__numericFormatInPlace(input);
                }

                const isUpdatingSavedValue = hasSavedValue && !savedIsModified;

                if (saveValue && cellKey && matrix) {
                    let storedValue;
                    if (input.type === 'checkbox') {
                        storedValue = input.checked ? '1' : '0';
                    } else {
                        storedValue = displayValue;
                    }

                    if (isUpdatingSavedValue && savedOriginalValue !== null) {
                        matrix.data[cellKey] = {
                            original: storedValue,
                            modified: storedValue,
                            isModified: false
                        };
                    } else {
                        matrix.data[cellKey] = {
                            original: storedValue,
                            modified: storedValue,
                            isModified: false
                        };
                    }

                    if (matrix.hiddenField) {
                        matrix.hiddenField.value = __serializeMatrixData(matrix.data);
                    }
                }
            } else {
                if (hasSavedValue && savedDisplayValue !== null) {
                    if (input.type === 'checkbox') {
                        const checkedValue = savedDisplayValue === '1' || savedDisplayValue === 1 || savedDisplayValue === 'true' || savedDisplayValue === true;
                        input.checked = checkedValue;
                        input.setAttribute('data-original-value', savedOriginalValue || (checkedValue ? '1' : '0'));
                    } else {
                        input.value = savedDisplayValue;
                        input.setAttribute('data-original-value', savedOriginalValue || savedDisplayValue);
                        if (typeof window.__numericFormatInPlace === 'function') window.__numericFormatInPlace(input);
                    }

                    if (savedIsModified) {
                        this.updateVariableModificationIndicator(input, true, savedOriginalValue);
                    }
                }
            }
        });
    }

    /**
     * Resolve variables for a specific matrix row
     */
    async resolveVariablesForRow(fieldId, rowEntityId, rowData = null) {
        const matrix = this.matrices.get(fieldId);
        if (!matrix || !matrix.container) {
            debugWarn('matrix-handler', '[VARIABLE RESOLUTION] Matrix not found or container missing', { fieldId });
            return;
        }

        // Get assignment entity status ID from the form context
        const assignmentEntityStatusId = this.getAssignmentEntityStatusId();
        if (!assignmentEntityStatusId) {
            debugWarn('matrix-handler', '[VARIABLE RESOLUTION] Cannot resolve variables: assignment_entity_status_id not found');
            return;
        }

        // Get template ID from the form context
        const templateId = this.getTemplateId();
        if (!templateId) {
            debugWarn('matrix-handler', '[VARIABLE RESOLUTION] Cannot resolve variables: template_id not found');
            return;
        }

        // Find all variable columns in this row
        const rowElement = matrix.container.querySelector(`tr[data-row-id="${rowEntityId}"]`);
        if (!rowElement) {
            debugWarn('matrix-handler', '[VARIABLE RESOLUTION] Row element not found', { rowEntityId });
            return;
        }

        const variableInputs = rowElement.querySelectorAll('input[data-column-type="variable"]');
        if (variableInputs.length === 0) {
            return;
        }

        // Extract entity ID from row data (for country list, this would be the country ID)
        // Try to get from rowData first, then from row element data attribute
        let entityId = null;
        if (rowData) {
            entityId = rowData.id || rowData._id || null;
        }
        if (!entityId && rowElement) {
            const rowDataAttr = rowElement.getAttribute('data-row-data');
            if (rowDataAttr) {
                try {
                    const parsed = JSON.parse(rowDataAttr);
                    entityId = parsed.id || parsed._id || null;
                } catch (e) {
                    debugWarn('matrix-handler', '[VARIABLE RESOLUTION] Failed to parse row data', e);
                }
            }
        }

        // If we still don't have entity ID, try using rowEntityId directly (it might be the entity ID)
        if (!entityId) {
            entityId = rowEntityId;
        }

        try {
            const requestBody = {
                assignment_entity_status_id: assignmentEntityStatusId,
                template_id: templateId,
                row_entity_id: entityId ? parseInt(entityId) : null
            };

            // Call API to resolve variables
            const response = await _mhFetch('/api/v1/variables/resolve', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestBody)
            });

            if (!response.ok) {
                const errorText = await response.text();
                debugError('matrix-handler', '[VARIABLE RESOLUTION] API error response', {
                    status: response.status,
                    statusText: response.statusText,
                    errorText
                });
                throw (window.httpErrorSync && window.httpErrorSync(response, `API error: ${response.status} ${response.statusText} - ${errorText}`)) || new Error(`API error: ${response.status} ${response.statusText} - ${errorText}`);
            }

            const data = await response.json();
            const resolvedVariables = data.variables || {};

            // Update each variable input with resolved value
            variableInputs.forEach((input, index) => {
                const variableName = input.getAttribute('data-variable-name');
                const cellKey = input.getAttribute('data-cell-key');
                const saveValue = input.getAttribute('data-variable-save-value') === 'true';
                const matrix = this.matrices.get(fieldId);


                // Check if there's a saved value and if it's been modified by the user
                let hasSavedValue = false;
                let savedIsModified = false;
                let savedDisplayValue = null;
                let savedOriginalValue = null;

                if (saveValue && cellKey && matrix && matrix.data && matrix.data[cellKey] !== undefined) {
                    const savedValue = matrix.data[cellKey];
                    hasSavedValue = true;

                    // Handle new structure with original/modified tracking
                    if (typeof savedValue === 'object' && savedValue.original !== undefined) {
                        savedDisplayValue = savedValue.modified || savedValue.original;
                        savedOriginalValue = savedValue.original;
                        savedIsModified = savedValue.isModified || false;
                    } else {
                        // Legacy structure - treat as unmodified
                        savedDisplayValue = String(savedValue || '');
                        savedOriginalValue = savedDisplayValue;
                        savedIsModified = false;
                    }

                    // If the saved value has been modified by the user, preserve it and skip resolution
                    if (savedIsModified) {
                        // Handle both number and tick variable inputs
                        if (input.type === 'checkbox') {
                            // For tick inputs, set checked state
                            const checkedValue = savedDisplayValue === '1' || savedDisplayValue === 1 || savedDisplayValue === 'true' || savedDisplayValue === true;
                            input.checked = checkedValue;
                            input.setAttribute('data-original-value', savedOriginalValue);
                        } else {
                            // For number inputs, set value
                            input.value = savedDisplayValue;
                            input.setAttribute('data-original-value', savedOriginalValue);
                        }

                        // Update visual indicator
                        this.updateVariableModificationIndicator(input, true, savedOriginalValue);

                        return; // Skip resolution, preserve user modification
                    }
                    // If not modified, continue to resolve from source (will update if source changed)
                }

                if (variableName && resolvedVariables.hasOwnProperty(variableName)) {
                    const resolvedValue = resolvedVariables[variableName];
                    const displayValue = resolvedValue !== null && resolvedValue !== undefined ? String(resolvedValue) : '';

                    // Handle both number and tick variable inputs
                    if (input.type === 'checkbox') {
                        // For tick inputs, set checked state based on resolved value
                        const checkedValue = displayValue === '1' || displayValue === 'true' || resolvedValue === true || resolvedValue === 1;
                        input.checked = checkedValue;
                        input.setAttribute('data-original-value', checkedValue ? '1' : '0');
                    } else {
                        // For number inputs, set value and apply thousand-separator formatting
                        input.value = displayValue;
                        input.setAttribute('data-original-value', displayValue);
                        if (typeof window.__numericFormatInPlace === 'function') window.__numericFormatInPlace(input);
                    }

                    // Determine if this is an update to an existing saved value
                    const isUpdatingSavedValue = hasSavedValue && !savedIsModified;

                    // If save_value is enabled, manually update matrix data
                    if (saveValue && cellKey && matrix) {
                        // For variable columns, store value based on input type
                        let storedValue;
                        if (input.type === 'checkbox') {
                            // For tick inputs, store as '1' or '0'
                            storedValue = input.checked ? '1' : '0';
                        } else {
                            // For number inputs, store as string
                            storedValue = displayValue;
                        }

                        // If updating an existing saved value that wasn't modified, update the structure
                        if (isUpdatingSavedValue && savedOriginalValue !== null) {
                            // Update the saved value structure with new resolved value
                            matrix.data[cellKey] = {
                                original: storedValue, // New resolved value becomes the original
                                modified: storedValue,
                                isModified: false
                            };
                        } else {
                            // Store original value structure for tracking modifications
                            matrix.data[cellKey] = {
                                original: storedValue,
                                modified: storedValue,
                                isModified: false
                            };
                        }

                        // Update hidden field
                        if (matrix.hiddenField) {
                            matrix.hiddenField.value = __serializeMatrixData(matrix.data);
                        }
                    }
                } else {
                    // Variable not found in resolved variables
                    // If we have a saved value (even if unmodified), use it as fallback
                    if (hasSavedValue && savedDisplayValue !== null) {
                        // Handle both number and tick variable inputs
                        if (input.type === 'checkbox') {
                            const checkedValue = savedDisplayValue === '1' || savedDisplayValue === 1 || savedDisplayValue === 'true' || savedDisplayValue === true;
                            input.checked = checkedValue;
                            input.setAttribute('data-original-value', savedOriginalValue || (checkedValue ? '1' : '0'));
                        } else {
                            input.value = savedDisplayValue;
                            input.setAttribute('data-original-value', savedOriginalValue || savedDisplayValue);
                            if (typeof window.__numericFormatInPlace === 'function') window.__numericFormatInPlace(input);
                        }

                        // Update visual indicator if it was modified
                        if (savedIsModified) {
                            this.updateVariableModificationIndicator(input, true, savedOriginalValue);
                        }

                    } else {
                        debugWarn('matrix-handler', `[VARIABLE RESOLUTION] Variable ${variableName} not found in resolved variables`, {
                            variableName,
                            availableVariables: Object.keys(resolvedVariables),
                            resolvedVariables
                        });
                    }
                }
            });

            // Update matrix data and totals
            this.calculateMatrixTotals(fieldId);

        } catch (error) {
            debugError('matrix-handler', `[VARIABLE RESOLUTION] Error resolving variables for row ${rowEntityId}:`, {
                error,
                message: error.message,
                stack: error.stack
            });
        }
    }

    /**
     * Get assignment entity status ID from form context
     */
    getAssignmentEntityStatusId() {
        // Try to get from hidden input or data attribute
        const hiddenInput = document.querySelector('input[name="assignment_entity_status_id"]');
        if (hiddenInput) {
            const value = parseInt(hiddenInput.value);
            debugLog('matrix-handler', '[VARIABLE RESOLUTION] Found assignment_entity_status_id from hidden input', { value });
            return value;
        }

        // Try to get from form data attribute
        const form = document.querySelector('form[data-assignment-entity-status-id]');
        if (form) {
            const value = parseInt(form.dataset.assignmentEntityStatusId);
            debugLog('matrix-handler', '[VARIABLE RESOLUTION] Found assignment_entity_status_id from form data attribute', { value });
            return value;
        }

        // Try to extract from URL
        const urlMatch = window.location.pathname.match(/\/forms\/assignment\/(\d+)/);
        if (urlMatch) {
            const value = parseInt(urlMatch[1]);
            debugLog('matrix-handler', '[VARIABLE RESOLUTION] Found assignment_entity_status_id from URL', { value, url: window.location.pathname });
            return value;
        }

        debugWarn('matrix-handler', '[VARIABLE RESOLUTION] Could not find assignment_entity_status_id', {
            url: window.location.pathname,
            hasHiddenInput: !!hiddenInput,
            hasForm: !!form
        });
        return null;
    }

    /**
     * Get template ID from form context
     */
    getTemplateId() {
        // Try to get from hidden input or data attribute
        const hiddenInput = document.querySelector('input[name="template_id"]');
        if (hiddenInput && hiddenInput.value) {
            const value = parseInt(hiddenInput.value);
            if (!isNaN(value)) {
                debugLog('matrix-handler', '[VARIABLE RESOLUTION] Found template_id from hidden input', { value });
                return value;
            }
        }

        // Try to get from form data attribute
        const form = document.querySelector('form[data-template-id]');
        if (form && form.dataset.templateId) {
            const value = parseInt(form.dataset.templateId);
            if (!isNaN(value)) {
                debugLog('matrix-handler', '[VARIABLE RESOLUTION] Found template_id from form data attribute', { value });
                return value;
            }
        }

        // Try to get from any form element (check main form)
        const mainForm = document.querySelector('form#focalDataEntryForm, form[method="POST"]');
        if (mainForm && mainForm.dataset.templateId) {
            const value = parseInt(mainForm.dataset.templateId);
            if (!isNaN(value)) {
                debugLog('matrix-handler', '[VARIABLE RESOLUTION] Found template_id from main form data attribute', { value });
                return value;
            }
        }

        // Try to get from matrix container data
        const matrixContainer = document.querySelector('.matrix-container[data-template-id]');
        if (matrixContainer && matrixContainer.dataset.templateId) {
            const value = parseInt(matrixContainer.dataset.templateId);
            if (!isNaN(value)) {
                debugLog('matrix-handler', '[VARIABLE RESOLUTION] Found template_id from matrix container', { value });
                return value;
            }
        }

        debugWarn('matrix-handler', '[VARIABLE RESOLUTION] Could not find template_id', {
            hasHiddenInput: !!hiddenInput,
            hiddenInputValue: hiddenInput ? hiddenInput.value : null,
            hasForm: !!form,
            formValue: form ? form.dataset.templateId : null,
            hasMainForm: !!mainForm,
            mainFormValue: mainForm ? mainForm.dataset.templateId : null,
            hasMatrixContainer: !!matrixContainer,
            matrixContainerValue: matrixContainer ? matrixContainer.dataset.templateId : null
        });
        return null;
    }

    /**
     * Clean up tooltip event listeners and scroll handlers for a row
     */
    cleanupRowTooltips(row) {
        if (!row) return;

        // Find all cells in the row that might have tooltip handlers
        const cells = row.querySelectorAll('td');
        cells.forEach(cell => {
            // Remove event listeners if they exist
            if (cell._variableTooltipMouseEnter) {
                cell.removeEventListener('mouseenter', cell._variableTooltipMouseEnter);
                delete cell._variableTooltipMouseEnter;
            }
            if (cell._variableTooltipMouseLeave) {
                cell.removeEventListener('mouseleave', cell._variableTooltipMouseLeave);
                delete cell._variableTooltipMouseLeave;
            }
            if (cell._variableTooltipMouseMove) {
                cell.removeEventListener('mousemove', cell._variableTooltipMouseMove);
                delete cell._variableTooltipMouseMove;
            }

            // Remove scroll handler if it exists
            if (cell._variableTooltipScrollHandler) {
                window.removeEventListener('scroll', cell._variableTooltipScrollHandler, true);
                delete cell._variableTooltipScrollHandler;
            }

            // Clean up stored references
            delete cell._variableOriginalValue;
            delete cell._variableInput;

            // Find and remove associated tooltip from DOM
            const input = cell.querySelector('input[data-cell-key]');
            if (input) {
                const cellKey = input.getAttribute('data-cell-key');
                if (cellKey) {
                    const tooltipId = `variable-tooltip-${cellKey}`;
                    const tooltip = document.getElementById(tooltipId);
                    if (tooltip) {
                        tooltip.remove();
                    }
                }
            }
        });
    }

    /**
     * Handle remove row button click
     */
    handleRemoveRowClick(button) {
        const row = button.closest('tr');

        // Check if row is actually connected to the DOM
        if (!row || !row.parentElement || !row.isConnected) {
            debugLog('matrix-handler', 'Row is detached or already being processed - ignoring click');
            return;
        }

        const rowLabel = row.getAttribute('data-row-label');
        const rowId = row.getAttribute('data-row-id');

        if (!rowId) {
            debugError('matrix-handler', 'Cannot remove row: missing data-row-id attribute', { rowLabel });
            if (window.showAlert) {
                window.showAlert('Error: Cannot remove row. Please refresh the page and try again.', 'error');
            } else {
                console.warn('Error: Cannot remove row. Please refresh the page and try again.');
            }
            return;
        }

        // Check if this row is already being removed
        if (this.rowsBeingRemoved.has(rowId)) {
            debugLog('matrix-handler', `Row "${rowLabel}" (ID: ${rowId}) is already being removed - ignoring duplicate click`);
            return;
        }

        // Mark row as being removed
        this.rowsBeingRemoved.add(rowId);

        const container = row.closest('.matrix-container');
        const fieldId = container?.dataset?.fieldId;

        if (!container) {
            this.rowsBeingRemoved.delete(rowId); // Clean up tracking
            debugError('matrix-handler', 'Cannot find .matrix-container parent', {
                button, row, rowLabel, rowId
            });
            return;
        }

        if (!fieldId) {
            this.rowsBeingRemoved.delete(rowId); // Clean up tracking
            debugError('matrix-handler', 'Could not find fieldId', { row, container, fieldId });
            return;
        }

        const performRemove = () => {
            // Clean up tooltip event listeners and handlers before removing row
            this.cleanupRowTooltips(row);

            // Get matrix info
            const matrix = this.matrices.get(fieldId);

            // Remove all cell data for this row from matrix.data
            if (matrix && matrix.data) {
                // Get all cell keys that belong to this row
                // Cell keys are standardized to format: "rowId_columnName"
                const cellKeysToRemove = [];
                Object.keys(matrix.data).forEach(cellKey => {
                    // Skip metadata fields
                    if (cellKey.startsWith('_')) {
                        return;
                    }

                    // Check if this cell key belongs to the removed row
                    const parts = cellKey.split('_');
                    if (parts.length >= 2) {
                        const cellRowId = parts.slice(0, -1).join('_'); // Rejoin in case row ID contains underscores
                        // Match by row ID only (standardized)
                        if (cellRowId === String(rowId)) {
                            cellKeysToRemove.push(cellKey);
                        }
                    }
                });

                // Remove all cell keys for this row
                cellKeysToRemove.forEach(cellKey => {
                    delete matrix.data[cellKey];
                    debugLog('matrix-handler', `Removed cell data: ${cellKey}`);
                });

                // Cache hidden field reference if not already cached
                if (!matrix.hiddenField) {
                    matrix.hiddenField = container.querySelector('input[type="hidden"]');
                }

                // Update hidden field
                if (matrix.hiddenField) {
                    this.sanitizeMatrixData(matrix);
                    matrix.hiddenField.value = __serializeMatrixData(matrix.data);
                    debugLog('matrix-handler', `Updated hidden field after row removal:`, matrix.data);
                }
            }

            // Remove the DOM element
            row.remove();
            this.calculateMatrixTotals(fieldId);

            // Reapply duplicate highlighting after removal (in case removal fixed duplicates)
            this.applyDuplicateEntityHighlighting(fieldId);

            // Update legend visibility after removing row
            this.updateLegendVisibility(fieldId);

            debugLog('matrix-handler', `Removed row "${rowLabel}" (ID: ${rowId}) from matrix ${fieldId}`);
        };

        // Confirm removal (avoid native confirm)
        const confirmMessage = `Are you sure you want to remove the row "${rowLabel}"?`;
        const cleanupTracking = () => this.rowsBeingRemoved.delete(rowId);
        const onConfirm = () => {
            try {
                performRemove();
            } finally {
                cleanupTracking();
            }
        };
        const onCancel = () => cleanupTracking();

        if (window.showDangerConfirmation) {
            window.showDangerConfirmation(confirmMessage, onConfirm, onCancel, 'Remove', 'Cancel', 'Remove Row?');
            return;
        }
        if (window.showConfirmation) {
            window.showConfirmation(confirmMessage, onConfirm, onCancel, 'Remove', 'Cancel', 'Remove Row?');
            return;
        }

        console.warn('Confirmation dialog not available:', confirmMessage);
        cleanupTracking();
        return;
    }


    /**
     * Get existing rows in matrix
     */
    getExistingRows(fieldId) {
        // Find tbody - try by ID first, then via container (works with repeat sections)
        let tbody = document.getElementById(`matrix-tbody-${fieldId}`);
        if (!tbody) {
            const container = document.querySelector(`[data-field-id="${fieldId}"]`);
            if (container) {
                tbody = container.querySelector('tbody[id*="matrix-tbody-"]') || container.querySelector('tbody');
            }
        }
        if (!tbody) return [];

        return Array.from(tbody.querySelectorAll('tr[data-row-label]'))
            .map(row => row.getAttribute('data-row-label'));
    }

    /**
     * Extract row information from saved data
     * Only accepts ID-based cell keys (standardized format: rowId_columnName)
     */
    extractRowInfoFromData(data, config) {
        const rowInfoMap = new Map(); // Map of rowId -> {rowId, rowName, cellKeys, values}

        Object.keys(data).forEach(cellKey => {
            // Skip metadata fields
            if (cellKey.startsWith('_')) {
                return;
            }

            const parts = cellKey.split('_');
            if (parts.length >= 2) {
                // Rejoin all parts except the last one as the row ID
                const rowId = parts.slice(0, -1).join('_');
                const columnName = parts[parts.length - 1];

                // Verify this column exists in the configuration
                const columnExists = config.columns && config.columns.some(column => {
                    const configColumnName = typeof column === 'object' ? column.name : column;
                    return configColumnName === columnName;
                });

                if (columnExists) {
                    if (!rowInfoMap.has(rowId)) {
                        // All cell keys are now ID-based (standardized)
                        rowInfoMap.set(rowId, {
                            rowId: rowId,
                            rowName: null, // Will be resolved from lookup list if needed
                            cellKeys: [],
                            values: {}
                        });
                    }
                    rowInfoMap.get(rowId).cellKeys.push(cellKey);
                    rowInfoMap.get(rowId).values[cellKey] = data[cellKey];
                }
            }
        });

        return rowInfoMap;
    }

    /**
     * Resolve row IDs to names from lookup list
     */
    async resolveRowIdsToNames(rowInfoMap, lookupListId, displayColumn) {
        if (!lookupListId || !displayColumn) return;

        // Check if any rows are ID-based
        const idBasedRows = Array.from(rowInfoMap.entries()).filter(([id, info]) => info.rowId !== null);

        if (idBasedRows.length === 0) return;

        try {
            // Fetch all options from the lookup list to resolve IDs to names
            const response = await _mhFetch(`/api/forms/lookup-lists/${lookupListId}/options?filters=[]`, {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (response.ok) {
                const json = await response.json();
                if (json.success && json.rows) {
                    // Create a map of ID -> name and full row data
                    const idToNameMap = new Map();
                    const idToDataMap = new Map();
                    json.rows.forEach(row => {
                        const rowId = String(row._id || row.id || '');
                        const rowName = row[displayColumn];
                        if (rowId && rowName) {
                            idToNameMap.set(rowId, rowName);
                            idToDataMap.set(rowId, row);
                        }
                    });

                    // Update rowInfoMap with resolved names
                    idBasedRows.forEach(([rowId, info]) => {
                        const resolvedName = idToNameMap.get(rowId);
                        const resolvedData = idToDataMap.get(rowId);
                        if (resolvedName) {
                            info.rowName = resolvedName;
                            info.rowData = resolvedData;
                        } else {
                            // Fallback: use ID as name if resolution fails
                            info.rowName = rowId;
                            info.rowData = { _id: rowId, id: rowId };
                        }
                    });
                }
            }
        } catch (error) {
            debugError('matrix-handler', 'Error resolving row IDs to names:', error);
            // Fallback: use IDs as names
            idBasedRows.forEach(([rowId, info]) => {
                if (!info.rowName) {
                    info.rowName = rowId;
                    info.rowData = { _id: rowId, id: rowId };
                }
            });
        }
    }

    /**
     * Update visual indicator for modified variable fields
     */
    updateVariableModificationIndicator(input, isModified, originalValue) {
        if (!input) return;

        // Find the parent cell (td) to attach tooltip to
        const cell = input.closest('td');
        if (!cell) return;

        // Remove existing tooltip if any (from body)
        const existingTooltipId = `variable-tooltip-${input.getAttribute('data-cell-key')}`;
        const existingTooltip = document.getElementById(existingTooltipId);
        if (existingTooltip) {
            existingTooltip.remove();
        }

        // Remove existing event listeners (store them first if needed)
        const existingMouseEnter = cell._variableTooltipMouseEnter;
        const existingMouseLeave = cell._variableTooltipMouseLeave;
        const existingMouseMove = cell._variableTooltipMouseMove;
        if (existingMouseEnter) {
            cell.removeEventListener('mouseenter', existingMouseEnter);
        }
        if (existingMouseLeave) {
            cell.removeEventListener('mouseleave', existingMouseLeave);
        }
        if (existingMouseMove) {
            cell.removeEventListener('mousemove', existingMouseMove);
        }

        if (isModified) {
            // Check if this is a checkbox (tick column)
            const isCheckbox = input.type === 'checkbox';
            // Check if checkbox is editable (not readonly)
            const isEditable = !input.disabled && input.getAttribute('data-variable-readonly') !== 'true';

            if (isCheckbox && isEditable) {
                // For editable checkboxes: full opacity and orange color
                input.style.setProperty('opacity', '1', 'important');
                input.style.setProperty('accent-color', '#ff9800', 'important'); // Orange color
                // Remove any opacity classes that might be applied
                input.classList.remove('opacity-50', 'opacity-75');
                input.classList.add('variable-modified', 'variable-modified-checkbox');

                // Also style the cell background with orange tint for better visibility
                if (cell) {
                    cell.style.setProperty('background-color', '#fff3e0', 'important'); // Light orange background
                }

                debugLog('matrix-handler', `Applying orange styling to modified editable variable checkbox: ${input.getAttribute('data-cell-key')}, original="${originalValue}", current="${input.checked}"`);
            } else if (isCheckbox && !isEditable) {
                // For readonly checkboxes: keep existing behavior (green background like number inputs)
                input.style.setProperty('background-color', '#d4edda', 'important');
                input.classList.add('variable-modified');

                debugLog('matrix-handler', `Applying green highlight to modified readonly variable checkbox: ${input.getAttribute('data-cell-key')}, original="${originalValue}", current="${input.checked}"`);
            } else {
                // For number inputs: light green background (existing behavior)
                input.style.setProperty('background-color', '#d4edda', 'important');
                input.classList.add('variable-modified');

                debugLog('matrix-handler', `Applying green highlight to modified variable cell: ${input.getAttribute('data-cell-key')}, original="${originalValue}", current="${input.value}"`);
            }

            // Store original value on the cell for tooltip recreation
            cell._variableOriginalValue = originalValue;
            cell._variableInput = input;

            // Create or get tooltip element - keep it in DOM for reuse
            let tooltip = document.getElementById(existingTooltipId);
            const applyTooltipStyles = (el) => {
                el.style.cssText = `
                    position: fixed;
                    padding: 8px 12px;
                    background-color: #333;
                    color: white;
                    border-radius: 4px;
                    font-size: 12px;
                    white-space: nowrap;
                    z-index: 10000;
                    opacity: 0;
                    pointer-events: auto;
                    transition: opacity 0.2s;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
                `;
            };
            const attachTooltipHoverListeners = (tipEl) => {
                if (tipEl._variableTooltipListenersAttached) return;
                tipEl._variableTooltipListenersAttached = true;
                tipEl._variableCell = cell;
                tipEl.addEventListener('mouseenter', () => {
                    if (cell._variableTooltipHideTimeout) {
                        clearTimeout(cell._variableTooltipHideTimeout);
                        cell._variableTooltipHideTimeout = null;
                    }
                });
                tipEl.addEventListener('mouseleave', () => {
                    const t = document.getElementById(existingTooltipId);
                    if (t) t.style.opacity = '0';
                });
            };
            if (!tooltip) {
                tooltip = document.createElement('div');
                tooltip.id = existingTooltipId;
                tooltip.className = 'variable-modification-tooltip';
                applyTooltipStyles(tooltip);
                attachTooltipHoverListeners(tooltip);
                document.body.appendChild(tooltip);
            }

            // Update tooltip content and position function
            const updateTooltip = () => {
                // Check if cell and input still exist
                if (!cell.isConnected || !input.isConnected) {
                    return;
                }
                const currentInput = cell._variableInput || input;
                if (!currentInput) {
                    return;
                }
                const currentOriginalValue = cell._variableOriginalValue !== undefined ? cell._variableOriginalValue : originalValue;

                // Update content - show original value or "empty" if it was empty
                const originalDisplay = (currentOriginalValue !== null && currentOriginalValue !== undefined && currentOriginalValue !== '')
                    ? this.escapeHtml(currentOriginalValue)
                    : '(empty)';
                if (tooltip) {
                    tooltip.replaceChildren();
                    const title = document.createElement('div');
                    title.style.fontWeight = 'bold';
                    title.style.marginBottom = '4px';
                    title.textContent = 'Modified Value';

                    const originalRow = document.createElement('div');
                    originalRow.appendChild(document.createTextNode('Original: '));
                    // `originalDisplay` already escaped HTML; append as text to avoid parsing.
                    // We can safely display the underlying value by using the raw value instead.
                    const originalText =
                        (currentOriginalValue !== null && currentOriginalValue !== undefined && currentOriginalValue !== '')
                            ? String(currentOriginalValue)
                            : '(empty)';
                    originalRow.appendChild(document.createTextNode(originalText));

                    const currentRow = document.createElement('div');
                    currentRow.appendChild(document.createTextNode('Current: '));
                    currentRow.appendChild(document.createTextNode(String(currentInput.type === 'checkbox' ? (currentInput.checked ? '1' : '0') : (currentInput.value || '(empty)'))));

                    const restoreRow = document.createElement('div');
                    restoreRow.style.marginTop = '6px';
                    restoreRow.style.paddingTop = '4px';
                    restoreRow.style.borderTop = '1px solid rgba(255,255,255,0.3)';
                    const restoreBtn = document.createElement('button');
                    restoreBtn.type = 'button';
                    restoreBtn.setAttribute('aria-label', 'Restore original value');
                    restoreBtn.style.cssText = 'background:#555;color:white;border:none;border-radius:3px;padding:4px 8px;font-size:11px;cursor:pointer;display:inline-flex;align-items:center;gap:4px;';
                    restoreBtn.innerHTML = '↩ Restore original';
                    restoreBtn.addEventListener('click', (e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        const inp = cell._variableInput;
                        const orig = cell._variableOriginalValue;
                        if (!inp || !inp.isConnected) return;
                        const container = inp.closest('.matrix-container') || inp.closest('[data-field-id]');
                        const fieldId = container ? (container.getAttribute('data-field-id') || '') : '';
                        const cellKey = inp.getAttribute('data-cell-key');
                        const matrix = fieldId ? this.matrices.get(fieldId) : null;
                        if (inp.type === 'checkbox') {
                            inp.checked = (orig === 1 || orig === '1' || orig === true || orig === 'true');
                        } else {
                            inp.value = (orig !== null && orig !== undefined) ? String(orig) : '';
                        }
                        // Sync data-original-value to the value we just set (so modification check matches)
                        const restoredDisplay = inp.type === 'checkbox' ? (inp.checked ? '1' : '0') : String(inp.value || '').trim();
                        inp.setAttribute('data-original-value', restoredDisplay);
                        if (matrix && cellKey) {
                            matrix.data[cellKey] = { original: restoredDisplay, modified: restoredDisplay, isModified: false };
                            this.sanitizeMatrixData(matrix);
                            if (matrix.hiddenField) {
                                matrix.hiddenField.value = __serializeMatrixData(matrix.data);
                            }
                        }
                        // Clear green/tooltip without dispatching (dispatch would re-run handler and can re-apply green if display differs)
                        this.updateVariableModificationIndicator(inp, false, restoredDisplay);
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                    });
                    restoreRow.appendChild(restoreBtn);
                    tooltip.append(title, originalRow, currentRow, restoreRow);

                    // Calculate position based on cell's bounding box
                    const cellRect = cell.getBoundingClientRect();
                    const tooltipRect = tooltip.getBoundingClientRect();

                    // Position above the cell, centered horizontally
                    let top = cellRect.top - tooltipRect.height - 5;
                    let left = cellRect.left + (cellRect.width / 2) - (tooltipRect.width / 2);

                    // Adjust if tooltip would go off screen
                    if (left < 10) {
                        left = 10;
                    } else if (left + tooltipRect.width > window.innerWidth - 10) {
                        left = window.innerWidth - tooltipRect.width - 10;
                    }

                    // If tooltip would go above viewport, show below instead
                    if (top < 10) {
                        top = cellRect.bottom + 5;
                    }

                    tooltip.style.top = `${top}px`;
                    tooltip.style.left = `${left}px`;
                }
            };

            // Create event handlers
            const mouseEnterHandler = () => {
                if (!cell.isConnected) return;
                if (cell._variableTooltipHideTimeout) {
                    clearTimeout(cell._variableTooltipHideTimeout);
                    cell._variableTooltipHideTimeout = null;
                }
                // Ensure tooltip exists in DOM (in case it was removed)
                if (!document.getElementById(existingTooltipId)) {
                    const newTooltip = document.createElement('div');
                    newTooltip.id = existingTooltipId;
                    newTooltip.className = 'variable-modification-tooltip';
                    applyTooltipStyles(newTooltip);
                    attachTooltipHoverListeners(newTooltip);
                    document.body.appendChild(newTooltip);
                    tooltip = newTooltip;
                } else {
                    tooltip = document.getElementById(existingTooltipId);
                }
                if (tooltip) {
                    updateTooltip(); // Calculate position and update content
                    tooltip.style.opacity = '1';
                }
            };
            const mouseMoveHandler = () => {
                // Check if cell still exists
                if (!cell.isConnected) {
                    return;
                }
                // Update position on mouse move in case of scrolling
                const currentTooltip = document.getElementById(existingTooltipId);
                if (currentTooltip && currentTooltip.style.opacity === '1') {
                    tooltip = currentTooltip;
                    updateTooltip();
                }
            };
            const mouseLeaveHandler = () => {
                if (!cell.isConnected) return;
                if (cell._variableTooltipHideTimeout) clearTimeout(cell._variableTooltipHideTimeout);
                // Delay hide so moving cursor to tooltip keeps it visible
                cell._variableTooltipHideTimeout = setTimeout(() => {
                    cell._variableTooltipHideTimeout = null;
                    const currentTooltip = document.getElementById(existingTooltipId);
                    if (currentTooltip) currentTooltip.style.opacity = '0';
                }, 150);
            };

            // Store handlers for cleanup
            cell._variableTooltipMouseEnter = mouseEnterHandler;
            cell._variableTooltipMouseMove = mouseMoveHandler;
            cell._variableTooltipMouseLeave = mouseLeaveHandler;

            // Show tooltip on hover
            cell.addEventListener('mouseenter', mouseEnterHandler);
            cell.addEventListener('mousemove', mouseMoveHandler);
            cell.addEventListener('mouseleave', mouseLeaveHandler);

            // Also handle scroll to update position
            const scrollHandler = () => {
                // Check if cell and tooltip still exist before updating
                if (!cell.isConnected) {
                    // Cell was removed, clean up
                    window.removeEventListener('scroll', scrollHandler, true);
                    delete cell._variableTooltipScrollHandler;
                    return;
                }
                const currentTooltip = document.getElementById(existingTooltipId);
                if (currentTooltip && currentTooltip.style.opacity === '1') {
                    updateTooltip();
                }
            };
            window.addEventListener('scroll', scrollHandler, true);
            cell._variableTooltipScrollHandler = scrollHandler;
        } else {
            // Remove modification styling
            const isCheckbox = input.type === 'checkbox';

            if (isCheckbox) {
                // Remove checkbox-specific styling
                input.style.removeProperty('opacity');
                input.style.removeProperty('accent-color');
                input.classList.remove('variable-modified', 'variable-modified-checkbox');

                // Remove cell background styling
                if (cell) {
                    cell.style.removeProperty('background-color');
                }
            } else {
                // Remove number input styling
                input.style.removeProperty('background-color');
                input.classList.remove('variable-modified');
            }

            // Remove tooltip if it exists
            const tooltipToRemove = document.getElementById(existingTooltipId);
            if (tooltipToRemove) {
                tooltipToRemove.remove();
            }

            // Remove scroll handler if exists
            const scrollHandler = cell._variableTooltipScrollHandler;
            if (scrollHandler) {
                window.removeEventListener('scroll', scrollHandler, true);
                delete cell._variableTooltipScrollHandler;
            }

            // Clean up stored references
            delete cell._variableOriginalValue;
            delete cell._variableInput;
        }
    }

    /**
     * Escape HTML for tooltip display
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Restore cell values for a row
     * Cell keys are already in standardized format (rowId_columnName)
     * Note: Variable columns are restored if variable_save_value is true, otherwise they are resolved fresh
     */
    restoreRowData(fieldId, rowId, rowInfo) {
        const updatedMatrix = this.matrices.get(fieldId);
        if (!updatedMatrix) {
            debugWarn('matrix-handler', `Matrix not found for field ${fieldId} when restoring row data`);
            return;
        }

        const config = updatedMatrix.config;
        const columns = config.columns || [];

        rowInfo.cellKeys.forEach(cellKey => {
            // Cell keys are already in format: rowId_columnName (standardized)
            // Verify the cell key matches the row ID
            const parts = cellKey.split('_');
            if (parts.length < 2) {
                debugWarn('matrix-handler', `Invalid cell key format: ${cellKey}`);
                return;
            }

            const cellRowId = parts.slice(0, -1).join('_');
            if (cellRowId !== rowId) {
                debugWarn('matrix-handler', `Cell key row ID mismatch: expected ${rowId}, got ${cellRowId}`);
                return;
            }

            // Check if this is a variable column
            const columnName = parts[parts.length - 1];
            const column = columns.find(col => {
                const colName = typeof col === 'object' ? col.name : col;
                return colName === columnName;
            });

            // Check if this is a variable column (new structure: is_variable, or legacy: type === 'variable')
            const isVariable = column && typeof column === 'object' && (column.is_variable === true || column.type === 'variable');

            if (isVariable) {
                // Check if variable should be restored (variable_save_value: true)
                const variableSaveValue = column.variable_save_value !== false; // Default to true
                if (!variableSaveValue) {
                    // This is a variable column that shouldn't be restored - it will be resolved fresh
                    debugLog('matrix-handler', `Skipping restoration of variable column: ${cellKey} (variable_save_value=false, will be resolved fresh)`);
                // Remove from matrix data if it exists (it was saved but shouldn't be restored)
                if (updatedMatrix.data[cellKey] !== undefined) {
                    delete updatedMatrix.data[cellKey];
                }
                return;
                }
                // If variable_save_value is true, continue to restore the saved value
                debugLog('matrix-handler', `Restoring variable column: ${cellKey} (variable_save_value=true)`);
            }

            const value = rowInfo.values[cellKey];

            if (value !== undefined && value !== null) {
                // Handle variable column data structure (with original/modified tracking)
                let displayValue = value;
                let originalValue = null;
                let isModified = false;

                if (isVariable) {
                    if (typeof value === 'object' && value.original !== undefined) {
                        // New structure with modification tracking
                        displayValue = value.modified || value.original;
                        originalValue = value.original;
                        isModified = value.isModified || false;
                        updatedMatrix.data[cellKey] = value; // Keep full structure
                    } else {
                        // Legacy structure - convert to new format
                        displayValue = String(value);
                        originalValue = displayValue;
                        isModified = false;
                        updatedMatrix.data[cellKey] = {
                            original: displayValue,
                            modified: displayValue,
                            isModified: false
                        };
                    }
                } else {
                    // Non-variable column - use simple value
                updatedMatrix.data[cellKey] = value;
                }

                // Update the input value if it exists
                const input = updatedMatrix.container.querySelector(`input[data-cell-key="${cellKey}"]`);
                if (input) {
                    if (input.type === 'checkbox') {
                        const checkedValue = displayValue == '1' || displayValue == 1 || displayValue === 'true' || displayValue === true;
                        input.checked = checkedValue;
                        // Store original value for variable tick columns
                        if (isVariable && originalValue !== null) {
                            input.setAttribute('data-original-value', originalValue);
                            // Update visual indicator
                            this.updateVariableModificationIndicator(input, isModified, originalValue);
                        }
                    } else {
                        input.value = displayValue;
                        if (typeof window.__numericFormatInPlace === 'function') window.__numericFormatInPlace(input);
                        // Store original value for variable number columns
                        if (isVariable && originalValue !== null) {
                            input.setAttribute('data-original-value', originalValue);
                            // Update visual indicator
                            this.updateVariableModificationIndicator(input, isModified, originalValue);
                        }
                    }

                    // Ensure disabled state is set for readonly variable columns
                    if (isVariable && column) {
                        const variableReadonly = typeof column === 'object' ? (column.variable_readonly !== false) : true;
                        input.disabled = variableReadonly;
                    }
                } else {
                    debugLog('matrix-handler', `Input not found for cell key: ${cellKey}`);
                }
            }
        });
    }

    /**
     * Restore cell values for static matrices (non-dynamic rows)
     */
    restoreStaticMatrixValues(fieldId) {
        const matrix = this.matrices.get(fieldId);
        if (!matrix || !matrix.data) return;

        const data = matrix.data;
        const config = matrix.config;
        const columns = config.columns || [];
        const container = matrix.container;

        debugLog('matrix-handler', `Restoring static matrix values for field ${fieldId}`, data);

        // Iterate through all saved cell values
        Object.keys(data).forEach(cellKey => {
            // Skip metadata keys
            if (cellKey.startsWith('_')) {
                return;
            }

            // Parse cell key to get column name
            const parts = cellKey.split('_');
            if (parts.length < 2) {
                return;
            }

            const columnName = parts[parts.length - 1];
            const column = columns.find(col => {
                const colName = typeof col === 'object' ? col.name : col;
                return colName === columnName;
            });

            // Check if this is a variable column (new structure: is_variable, or legacy: type === 'variable')
            const isVariable = column && typeof column === 'object' && (column.is_variable === true || column.type === 'variable');

            if (isVariable) {
                // Check if variable should be restored (variable_save_value: true)
                const variableSaveValue = column.variable_save_value !== false; // Default to true
                if (!variableSaveValue) {
                    // Skip restoration for variables that shouldn't be saved/restored
                    debugLog('matrix-handler', `Skipping restoration of variable column: ${cellKey} (variable_save_value=false)`);
                    return;
                }
                debugLog('matrix-handler', `Restoring variable column: ${cellKey} (variable_save_value=true)`);
            }

            const value = data[cellKey];
            if (value !== undefined && value !== null) {
                // Handle variable column data structure (with original/modified tracking)
                let displayValue = value;
                let originalValue = null;
                let isModified = false;

                if (isVariable) {
                    if (typeof value === 'object' && value.original !== undefined) {
                        // New structure with modification tracking
                        displayValue = value.modified || value.original;
                        originalValue = value.original;
                        isModified = value.isModified || false;
                    } else {
                        // Legacy structure - convert to new format
                        displayValue = String(value);
                        originalValue = displayValue;
                        isModified = false;
                        // Update data structure
                        data[cellKey] = {
                            original: displayValue,
                            modified: displayValue,
                            isModified: false
                        };
                    }
                }

                // Find the input field for this cell
                const input = container.querySelector(`input[data-cell-key="${cellKey}"]`);
                if (input) {
                    if (input.type === 'checkbox') {
                        const checkedValue = displayValue == '1' || displayValue == 1 || displayValue === 'true' || displayValue === true;
                        input.checked = checkedValue;
                        // Store original value for variable tick columns
                        if (isVariable && originalValue !== null) {
                            input.setAttribute('data-original-value', originalValue);
                            // Update visual indicator
                            this.updateVariableModificationIndicator(input, isModified, originalValue);
                        }
                    } else {
                        input.value = displayValue;
                        if (typeof window.__numericFormatInPlace === 'function') window.__numericFormatInPlace(input);
                        // Store original value for variable number columns
                        if (isVariable && originalValue !== null) {
                            input.setAttribute('data-original-value', originalValue);
                            // Update visual indicator
                            this.updateVariableModificationIndicator(input, isModified, originalValue);
                        }
                    }

                    // Set disabled state for readonly variable columns
                    if (isVariable && column) {
                        const variableReadonly = typeof column === 'object' ? (column.variable_readonly !== false) : true;
                        input.disabled = variableReadonly;
                    }

                    debugLog('matrix-handler', `Restored value for cell ${cellKey}: ${displayValue}${isModified ? ' (modified)' : ''}`);
                } else {
                    debugLog('matrix-handler', `Input not found for cell key: ${cellKey}`);
                }
            }
        });

        // Recalculate totals after restoring values
        this.calculateMatrixTotals(fieldId);
    }

    /**
     * Restore dynamic rows from saved data
     */
    async restoreDynamicRows(fieldId) {
        // Mark that we're in a batch operation to prevent scheduled resolutions
        this.batchOperationsInProgress.add(fieldId);

        // Cancel any pending scheduled variable resolution immediately
        // We'll batch resolve all rows at the end
        if (this.variableResolutionDebounceTimers.has(fieldId)) {
            clearTimeout(this.variableResolutionDebounceTimers.get(fieldId));
            this.variableResolutionDebounceTimers.delete(fieldId);
        }
        this.pendingVariableResolution.delete(fieldId);

        const matrix = this.matrices.get(fieldId);
        if (!matrix || !matrix.data) {
            this.batchOperationsInProgress.delete(fieldId);
            return;
        }

        const data = matrix.data;
        const config = matrix.config;

        debugLog('matrix-handler', `Restoring dynamic rows for matrix ${fieldId}`, data);

        // Extract row information from saved data
        const rowInfoMap = this.extractRowInfoFromData(data, config);

        debugLog('matrix-handler', `Found ${rowInfoMap.size} dynamic rows to restore:`, Array.from(rowInfoMap.keys()));

        // Resolve row IDs to names if needed
        await this.resolveRowIdsToNames(rowInfoMap, config.lookup_list_id, config.list_display_column);

        // Track which rows were auto-loaded (if auto_load_entities was enabled)
        // When restoring rows, we initially mark them as not auto-loaded.
        // If auto_load_entities is enabled, the autoLoadEntities function will later
        // mark matching rows as auto-loaded. Rows that don't match will remain as manually added.
        // This way, only rows that are truly manually added (not in the auto-load list) get highlighted.
        const isAutoLoaded = false; // Restored rows start as manually added, will be updated by autoLoadEntities if they match

        // Batch all row restoration operations
        const restorePromises = [];

        // Create rows for each unique row
        for (const [rowId, rowInfo] of rowInfoMap.entries()) {
            // rowId is now always the key (standardized)
            if (!rowInfo.rowId || rowInfo.rowId !== rowId) {
                debugWarn('matrix-handler', `Row info mismatch: key=${rowId}, rowInfo.rowId=${rowInfo.rowId}`);
                continue;
            }

            const rowName = rowInfo.rowName || rowId;
            const rowData = rowInfo.rowData || { _id: rowId, id: rowId };

            try {
                // Create the row using addDynamicRow which handles ID-based keys
                // Mark as not auto-loaded since we're restoring from saved data
                this.addDynamicRow(fieldId, rowName, rowData, rowId, isAutoLoaded);

                // Batch restore cell values (wait for DOM to be ready)
                restorePromises.push(
                    new Promise(resolve => {
                        setTimeout(() => {
                            try {
                                this.restoreRowData(fieldId, rowId, rowInfo);
                            } catch (error) {
                                debugError('matrix-handler', `Error restoring row data for ${rowId}:`, error);
                            }
                            resolve();
                        }, 50);
                    })
                );
            } catch (error) {
                debugError('matrix-handler', `Error adding dynamic row ${rowId}:`, error);
                // Continue with other rows even if one fails
            }
        }

        // Wait for all restorations to complete, then update hidden field and recalculate
        try {
            await Promise.all(restorePromises);
            const updatedMatrix = this.matrices.get(fieldId);
            if (updatedMatrix) {
                // Cancel any pending scheduled variable resolution (we'll batch resolve all at once)
                if (this.variableResolutionDebounceTimers.has(fieldId)) {
                    clearTimeout(this.variableResolutionDebounceTimers.get(fieldId));
                    this.variableResolutionDebounceTimers.delete(fieldId);
                }
                this.pendingVariableResolution.delete(fieldId);

                // Remove metadata keys before writing hidden field.
                this.sanitizeMatrixData(updatedMatrix);

                // Invalidate cache and refresh hidden field reference (DOM may have changed)
                updatedMatrix.hiddenField = updatedMatrix.container.querySelector('input[type="hidden"]');

                // Update hidden field
                if (updatedMatrix.hiddenField) {
                    updatedMatrix.hiddenField.value = __serializeMatrixData(updatedMatrix.data);
                }

                // Recalculate totals after all rows are restored
                this.calculateMatrixTotals(fieldId);

                // Sort rows alphabetically after restoration
                this.sortMatrixRows(fieldId);

                // Batch resolve variables for all restored rows (optimized)
                await this.resolveVariablesForAllRows(fieldId);

                // Check for and highlight duplicates
                this.applyDuplicateEntityHighlighting(fieldId);

                // Update legend visibility after restoration
                this.updateLegendVisibility(fieldId);
            }
        } catch (error) {
            debugError('matrix-handler', 'Error restoring dynamic rows:', error);
        } finally {
            // Clear batch operation flag
            this.batchOperationsInProgress.delete(fieldId);
        }
    }


    /**
     * Auto-load entities from saved matrix data based on variable configurations
     */
    async autoLoadEntities(fieldId) {
        // Mark that we're in a batch operation to prevent scheduled resolutions
        this.batchOperationsInProgress.add(fieldId);

        // Cancel any pending scheduled variable resolution immediately
        // We'll batch resolve all rows at the end
        if (this.variableResolutionDebounceTimers.has(fieldId)) {
            clearTimeout(this.variableResolutionDebounceTimers.get(fieldId));
            this.variableResolutionDebounceTimers.delete(fieldId);
        }
        this.pendingVariableResolution.delete(fieldId);

        const matrix = this.matrices.get(fieldId);
        if (!matrix || !matrix.config) {
            this.batchOperationsInProgress.delete(fieldId);
            debugWarn('matrix-handler', `Cannot auto-load entities: matrix ${fieldId} not found`);
            return;
        }

        // Get variable configurations from matrix columns
        const variableColumns = (matrix.config.columns || []).filter(col => col.is_variable === true);
        if (variableColumns.length === 0) {
            debugLog('matrix-handler', `No variable columns found for auto-load in matrix ${fieldId}`);
            return;
        }

        // Get variable configurations from template variables
        // Wait a bit for template variables to be available (they might load asynchronously)
        let templateVariables = window.templateVariables || {};
        let retries = 0;
        const maxRetries = 5;

        while ((!templateVariables || Object.keys(templateVariables).length === 0) && retries < maxRetries) {
            await new Promise(resolve => setTimeout(resolve, 100));
            templateVariables = window.templateVariables || {};
            retries++;
        }

        if (!templateVariables || Object.keys(templateVariables).length === 0) {
            debugWarn('matrix-handler', 'Template variables not available for auto-load after waiting');
            return;
        }

        // Resolve variable configs for all variable columns (used for entity scope and source)
        const variableConfigsByColumn = [];
        for (const col of variableColumns) {
            const colVariableName = col.variable || col.variable_name;
            if (!colVariableName) continue;
            const colVariableConfig = templateVariables[colVariableName];
            if (!colVariableConfig) continue;
            variableConfigsByColumn.push({ column: col, variableName: colVariableName, variableConfig: colVariableConfig });
        }
        if (variableConfigsByColumn.length === 0) {
            debugWarn('matrix-handler', `No variable configuration found for any column in matrix ${fieldId}`);
            return;
        }

        // Use first variable's entity_scope for lookup mode (reverse vs forward)
        const firstVariableColumn = variableConfigsByColumn[0];
        const variableName = firstVariableColumn.variableName;
        const variableConfig = firstVariableColumn.variableConfig;
        const entityScope = variableConfig.entity_scope;
        const isReverseLookup = entityScope === 'entities_containing';

        // Get assignment_entity_status_id from hidden input
        const assignmentStatusInput = document.querySelector('input[name="assignment_entity_status_id"]');
        if (!assignmentStatusInput || !assignmentStatusInput.value) {
            debugWarn('matrix-handler', 'assignment_entity_status_id not found in form');
            return;
        }

        const assignmentEntityStatusId = parseInt(assignmentStatusInput.value, 10);
        if (isNaN(assignmentEntityStatusId)) {
            debugWarn('matrix-handler', `Invalid assignment_entity_status_id: ${assignmentStatusInput.value}`);
            return;
        }

        // Get template ID for variable resolution
        const templateId = this.getTemplateId();
        if (!templateId) {
            debugWarn('matrix-handler', 'template_id not found for variable resolution');
            return;
        }

        debugLog('matrix-handler', `Auto-loading entities for matrix ${fieldId}`, {
            variableColumnCount: variableConfigsByColumn.length,
            entityScope,
            isReverseLookup,
            assignmentEntityStatusId,
            templateId
        });

        // Get tick variable column names for filtering (needed for both forward and reverse lookup)
        // Use matrix_column_name from variable config, not the column label
        const tickVariableColumns = variableColumns.filter(col => {
            const colType = typeof col === 'object' ? col.type : 'number';
            return colType === 'tick';
        });
        const tickColumnNames = tickVariableColumns.map(col => {
            // Get the variable name for this column
            const colVariableName = col.variable || col.variable_name;
            if (colVariableName && templateVariables[colVariableName]) {
                const colVariableConfig = templateVariables[colVariableName];
                // Use matrix_column_name from variable config if available, otherwise fall back to column name
                if (colVariableConfig.matrix_column_name) {
                    return colVariableConfig.matrix_column_name;
                }
            }
            // Fallback to column name if no variable config or no matrix_column_name
            return typeof col === 'object' ? col.name : col;
        });

        let entities = [];
        let entityType = null;

        try {
            if (isReverseLookup) {
                // For reverse lookup (entities_containing), use variable resolution once and collect entities from ALL variable columns
                debugLog('matrix-handler', '[AUTO-LOAD] Using reverse lookup via variable resolution (all variable columns)');

                const response = await _mhFetch('/api/v1/variables/resolve', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        assignment_entity_status_id: assignmentEntityStatusId,
                        template_id: templateId
                    })
                });

                if (!response.ok) {
                    const errorText = await response.text();
                    debugError('matrix-handler', `[AUTO-LOAD] Variable resolution failed: ${response.status}`, {
                        status: response.status,
                        errorText
                    });
                    return;
                }

                const data = await response.json();
                const resolvedVariables = data.variables || {};
                const entityMapById = new Map(); // entity_id -> { entity_id, entity_type } for deduplication

                for (const { variableName: colVarName } of variableConfigsByColumn) {
                    const variableValue = resolvedVariables[colVarName];
                    debugLog('matrix-handler', `[AUTO-LOAD] Variable ${colVarName} resolved to:`, variableValue);

                    if (!variableValue) {
                        debugLog('matrix-handler', `[AUTO-LOAD] Variable ${colVarName} not found in resolved variables, skipping`);
                        continue;
                    }

                    try {
                        const parsed = typeof variableValue === 'string' ? JSON.parse(variableValue) : variableValue;
                        if (parsed && parsed.entities && Array.isArray(parsed.entities)) {
                            if (parsed.entity_type && !entityType) entityType = parsed.entity_type;
                            for (const ent of parsed.entities) {
                                const eid = ent.entity_id != null ? ent.entity_id : ent.id;
                                const etype = ent.entity_type || parsed.entity_type || entityType;
                                if (eid != null && etype) {
                                    entityMapById.set(String(eid), { entity_id: eid, entity_type: etype });
                                }
                            }
                            debugLog('matrix-handler', `[AUTO-LOAD] Parsed ${parsed.entities.length} entities from variable ${colVarName}`);
                        } else {
                            debugLog('matrix-handler', `[AUTO-LOAD] Variable ${colVarName} value is not in auto_load_format, skipping`);
                        }
                    } catch (parseError) {
                        debugWarn('matrix-handler', `[AUTO-LOAD] Failed to parse variable ${colVarName} as JSON:`, parseError);
                    }
                }

                entities = Array.from(entityMapById.values());
                debugLog('matrix-handler', `[AUTO-LOAD] Merged ${entities.length} unique entities from ${variableConfigsByColumn.length} variable column(s)`);
            } else {
                // For forward lookup (same, any, specific), call backend for EACH variable column and merge entities
                const entityMapById = new Map();
                for (const { variableName: colVarName, variableConfig: colVarConfig } of variableConfigsByColumn) {
                    const sourceTemplateId = colVarConfig.source_template_id;
                    const sourceAssignmentPeriod = colVarConfig.source_assignment_period;
                    const sourceFormItemId = colVarConfig.source_form_item_id;

                    if (!sourceTemplateId || !sourceAssignmentPeriod || !sourceFormItemId) {
                        debugLog('matrix-handler', `[AUTO-LOAD] Incomplete variable configuration for ${colVarName}, skipping`);
                        continue;
                    }

                    const requireTickValue1 = tickColumnNames.length > 0;
                    const response = await _mhFetch('/api/v1/matrix/auto-load-entities', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.getCsrfToken()
                        },
                        body: JSON.stringify({
                            source_template_id: sourceTemplateId,
                            source_assignment_period: sourceAssignmentPeriod,
                            source_form_item_id: sourceFormItemId,
                            assignment_entity_status_id: assignmentEntityStatusId,
                            require_tick_value_1: requireTickValue1,
                            tick_column_names: tickColumnNames
                        })
                    });

                    if (!response.ok) {
                        debugWarn('matrix-handler', `[AUTO-LOAD] Failed to fetch auto-load entities for ${colVarName}: ${response.status}`);
                        continue;
                    }

                    const data = await response.json();
                    const colEntities = data.entities || [];
                    if (data.entity_type && !entityType) entityType = data.entity_type;
                    for (const ent of colEntities) {
                        const eid = ent.entity_id != null ? ent.entity_id : ent.id;
                        const etype = ent.entity_type || data.entity_type || entityType;
                        if (eid != null && etype) {
                            entityMapById.set(String(eid), { entity_id: eid, entity_type: etype });
                        }
                    }
                    debugLog('matrix-handler', `[AUTO-LOAD] Got ${colEntities.length} entities from variable ${colVarName}`);
                }
                entities = Array.from(entityMapById.values());
                debugLog('matrix-handler', `[AUTO-LOAD] Merged ${entities.length} unique entities from ${variableConfigsByColumn.length} variable column(s) (forward lookup)`);
            }

            if (entities.length === 0) {
                return;
            }

            // Filter entities: only include those with at least one tick variable column = 1

            // For forward lookup, backend already filters entities by tick columns
            // For reverse lookup, we need to filter in the frontend
            if (tickVariableColumns.length > 0 && isReverseLookup) {
                debugLog('matrix-handler', `[AUTO-LOAD] Filtering entities by tick columns (reverse lookup): ${tickVariableColumns.length} tick variable columns found`);

                // Filter entities based on tick column values using variable resolution
                const filteredEntities = [];
                const originalCount = entities.length;

                for (const entity of entities) {
                    // For reverse lookup, resolve variable for this entity to check if it's ticked
                    // The variable resolution will return 1 if ticked, 0 if not
                    let hasTickedBox = false;

                    try {
                        const resolveResponse = await _mhFetch('/api/v1/variables/resolve', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({
                                assignment_entity_status_id: assignmentEntityStatusId,
                                template_id: templateId,
                                row_entity_id: entity.entity_id
                            })
                        });

                        if (resolveResponse.ok) {
                            const resolveData = await resolveResponse.json();
                            const resolvedVariables = resolveData.variables || {};
                            // Entity is included if ANY variable column is ticked for this entity
                            hasTickedBox = variableConfigsByColumn.some(({ variableName: vn }) => {
                                const v = resolvedVariables[vn];
                                return v === 1 || v === '1' || v === true;
                            });
                        }
                    } catch (error) {
                        debugError('matrix-handler', `[AUTO-LOAD] Error checking tick status for entity ${entity.entity_id}:`, error);
                    }

                    if (hasTickedBox) {
                        filteredEntities.push(entity);
                    } else {
                        debugLog('matrix-handler', `[AUTO-LOAD] Filtered out entity ${entity.entity_id} - no ticked boxes`);
                    }
                }

                entities = filteredEntities;
                debugLog('matrix-handler', `[AUTO-LOAD] Filtered entities: ${entities.length} entities have at least one ticked box (from ${originalCount} total)`);
            } else if (tickVariableColumns.length > 0 && !isReverseLookup) {
                debugLog('matrix-handler', `[AUTO-LOAD] Forward lookup - backend will filter entities by tick columns`);
            } else {
                debugLog('matrix-handler', `[AUTO-LOAD] No tick variable columns found, skipping tick filter`);
            }

            if (entities.length === 0) {
                debugLog('matrix-handler', '[AUTO-LOAD] No entities found after filtering by tick columns');
                return;
            }

            debugLog('matrix-handler', `Found ${entities.length} entities to auto-load`, { entities, entityType });

            // Auto-populate matrix rows with entities
            const lookupListId = matrix.config.lookup_list_id;
            const displayColumn = matrix.config.list_display_column || 'name';
            const filters = matrix.config.list_filters || [];
            const autoLoadEnabled = __configFlag(matrix.config.auto_load_entities, false);
            const highlightManualRows = __configFlag(matrix.config.highlight_manual_rows, autoLoadEnabled);

            if (!lookupListId) {
                debugWarn('matrix-handler', 'No lookup_list_id found in matrix config for auto-load');
                return;
            }

            // Verify entity types match (entities should all have the same entity_type)
            // The lookup_list_id should correspond to this entity_type (e.g., country_map for "country")
            const uniqueEntityTypes = [...new Set(entities.map(e => e.entity_type))];
            if (uniqueEntityTypes.length > 1) {
                debugWarn('matrix-handler', `[AUTO-LOAD] Multiple entity types found: ${uniqueEntityTypes.join(', ')}. All entities should have the same type.`);
            }
            debugLog('matrix-handler', `[AUTO-LOAD] Entity type: ${entityType || uniqueEntityTypes[0] || 'unknown'}. Lookup list ID: ${lookupListId}. The lookup list should contain entities of this type.`);

            // Fetch entity names from lookup list
            // The lookup list should match the entity_type (e.g., country_map for "country", national_society list for "national_society")
            // Normalize entity IDs to strings for consistent matching
            const entityIdSet = new Set(entities.map(e => String(e.entity_id)));
            const entityDataMap = new Map();

            debugLog('matrix-handler', '[AUTO-LOAD] Looking up entity names', {
                entityCount: entities.length,
                entityIds: Array.from(entityIdSet),
                entityTypes: uniqueEntityTypes,
                lookupListId,
                displayColumn,
                filters,
                note: `Lookup list ${lookupListId} should contain entities of type: ${entityType || uniqueEntityTypes[0] || 'unknown'}`
            });

            try {
                // Call search endpoint to get entity data with names
                // Request up to 200 options to reduce chance of missing entities
                const response = await _mhFetch('/forms/matrix/search-rows', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    body: JSON.stringify({
                        lookup_list_id: lookupListId,
                        display_column: displayColumn,
                        filters: filters,
                        search_term: '', // Empty search to get all
                        existing_rows: [],
                        limit: 200 // Request up to 200 options
                    })
                });

                if (response.ok) {
                    const data = await response.json();
                    debugLog('matrix-handler', '[AUTO-LOAD] Lookup API response', {
                        success: data.success,
                        optionCount: data.options ? data.options.length : 0,
                        hasOptions: !!data.options
                    });

                    if (data.success && data.options) {
                        // Track which entity IDs are found in the options
                        const foundEntityIds = [];
                        const notFoundEntityIds = [];

                        // Map entity IDs to their data
                        for (const option of data.options) {
                            const entityId = option.id || option.data?.id || option.data?._id;
                            // Normalize to string for consistent matching
                            const normalizedEntityId = entityId ? String(entityId) : null;

                            if (normalizedEntityId && entityIdSet.has(normalizedEntityId)) {
                                foundEntityIds.push(normalizedEntityId);
                                entityDataMap.set(normalizedEntityId, {
                                    id: entityId,
                                    _id: entityId,
                                    ...option.data,
                                    name: option.value // Use the display value as name
                                });
                            }
                        }

                        // Find which entity IDs were not found
                        entityIdSet.forEach(id => {
                            if (!entityDataMap.has(id)) {
                                notFoundEntityIds.push(id);
                            }
                        });

                        debugLog('matrix-handler', '[AUTO-LOAD] Entity matching results', {
                            foundCount: foundEntityIds.length,
                            foundIds: foundEntityIds,
                            notFoundCount: notFoundEntityIds.length,
                            notFoundIds: notFoundEntityIds,
                            totalOptions: data.options.length,
                            sampleOptions: data.options.slice(0, 5).map(opt => ({
                                id: opt.id,
                                data_id: opt.data?.id,
                                data__id: opt.data?._id,
                                value: opt.value
                            }))
                        });

                        // Special logging for entity 192
                        if (notFoundEntityIds.includes('192')) {
                            debugLog('matrix-handler', '[AUTO-LOAD] Entity 192 not found - checking all options', {
                                lookingFor: '192',
                                entityIdSetHas192: entityIdSet.has('192'),
                                totalOptions: data.options.length,
                                optionsWith192: data.options.filter(opt => {
                                    const optId = String(opt.id || opt.data?.id || opt.data?._id || '');
                                    return optId === '192' || optId.includes('192');
                                }).map(opt => ({
                                    id: opt.id,
                                    data_id: opt.data?.id,
                                    data__id: opt.data?._id,
                                    value: opt.value,
                                    fullOption: opt
                                }))
                            });
                        }

                        // Fetch missing entities individually (they might be beyond pagination limit)
                        if (notFoundEntityIds.length > 0) {
                            debugLog('matrix-handler', '[AUTO-LOAD] Fetching missing entities individually', {
                                missingCount: notFoundEntityIds.length,
                                missingIds: notFoundEntityIds
                            });

                            // Try to fetch each missing entity by filtering by ID
                            for (const missingId of notFoundEntityIds) {
                                debugLog('matrix-handler', `[AUTO-LOAD] Attempting to fetch missing entity ${missingId}`, {
                                    missingId,
                                    lookupListId,
                                    displayColumn
                                });

                                try {
                                    // Try filtering by ID - backend expects 'column' not 'field'
                                    const idFilter = Array.isArray(filters) ? [...filters] : [];
                                    // Add ID filter - backend expects column name in row_data
                                    // For system lists, row_data has '_id' and 'id' keys
                                    idFilter.push({
                                        column: '_id',  // Use 'column' not 'field'
                                        operator: 'equals',
                                        value: String(missingId)  // Backoffice does string comparison with .lower()
                                    });

                                    debugLog('matrix-handler', `[AUTO-LOAD] Fetching entity ${missingId} with filter:`, {
                                        filter: idFilter,
                                        requestBody: {
                                            lookup_list_id: lookupListId,
                                            display_column: displayColumn,
                                            filters: idFilter,
                                            search_term: '',
                                            existing_rows: []
                                        }
                                    });

                                    const searchResponse = await _mhFetch('/forms/matrix/search-rows', {
                                        method: 'POST',
                                        headers: {
                                            'Content-Type': 'application/json',
                                            'X-CSRFToken': this.getCsrfToken()
                                        },
                                        body: JSON.stringify({
                                            lookup_list_id: lookupListId,
                                            display_column: displayColumn,
                                            filters: idFilter,
                                            search_term: '', // Empty search, rely on filter
                                            existing_rows: [],
                                            limit: 10  // Small limit since we're filtering by ID
                                        })
                                    });

                                    debugLog('matrix-handler', `[AUTO-LOAD] Fallback API response for ${missingId}:`, {
                                        status: searchResponse.status,
                                        ok: searchResponse.ok
                                    });

                                    if (searchResponse.ok) {
                                        const searchData = await searchResponse.json();
                                        debugLog('matrix-handler', `[AUTO-LOAD] Fallback API data for ${missingId}:`, {
                                            success: searchData.success,
                                            optionCount: searchData.options ? searchData.options.length : 0,
                                            options: searchData.options
                                        });

                                        if (searchData.success && searchData.options) {
                                            // Look for the exact entity ID in the search results
                                            for (const option of searchData.options) {
                                                const entityId = option.id || option.data?.id || option.data?._id;
                                                const normalizedEntityId = entityId ? String(entityId) : null;

                                                debugLog('matrix-handler', `[AUTO-LOAD] Checking option for ${missingId}:`, {
                                                    optionId: entityId,
                                                    normalizedId: normalizedEntityId,
                                                    missingId,
                                                    matches: normalizedEntityId === missingId,
                                                    optionValue: option.value
                                                });

                                                if (normalizedEntityId === missingId) {
                                                    entityDataMap.set(normalizedEntityId, {
                                                        id: entityId,
                                                        _id: entityId,
                                                        ...option.data,
                                                        name: option.value
                                                    });
                                                    debugLog('matrix-handler', `[AUTO-LOAD] ✓ Found missing entity ${missingId} via ID filter`, {
                                                        entityId: missingId,
                                                        name: option.value,
                                                        rowData: option.data
                                                    });
                                                    break; // Found it, move to next missing entity
                                                }
                                            }

                                            // If still not found, try alternative filter format with 'id' column
                                            if (!entityDataMap.has(missingId)) {
                                                debugLog('matrix-handler', `[AUTO-LOAD] Entity ${missingId} not found with _id filter, trying 'id' column`);

                                                const altFilter = Array.isArray(filters) ? [...filters] : [];
                                                altFilter.push({
                                                    column: 'id',  // Use 'column' not 'field'
                                                    operator: 'equals',
                                                    value: String(missingId)  // Backoffice does string comparison
                                                });

                                                const altResponse = await _mhFetch('/forms/matrix/search-rows', {
                                                    method: 'POST',
                                                    headers: {
                                                        'Content-Type': 'application/json',
                                                        'X-CSRFToken': this.getCsrfToken()
                                                    },
                                                    body: JSON.stringify({
                                                        lookup_list_id: lookupListId,
                                                        display_column: displayColumn,
                                                        filters: altFilter,
                                                        search_term: '',
                                                        existing_rows: [],
                                                        limit: 10
                                                    })
                                                });

                                                if (altResponse.ok) {
                                                    const altData = await altResponse.json();
                                                    debugLog('matrix-handler', `[AUTO-LOAD] Alternative filter response for ${missingId}:`, {
                                                        success: altData.success,
                                                        optionCount: altData.options ? altData.options.length : 0,
                                                        options: altData.options
                                                    });

                                                    if (altData.success && altData.options) {
                                                        for (const option of altData.options) {
                                                            const entityId = option.id || option.data?.id || option.data?._id;
                                                            const normalizedEntityId = entityId ? String(entityId) : null;

                                                            if (normalizedEntityId === missingId) {
                                                                entityDataMap.set(normalizedEntityId, {
                                                                    id: entityId,
                                                                    _id: entityId,
                                                                    ...option.data,
                                                                    name: option.value
                                                                });
                                                                debugLog('matrix-handler', `[AUTO-LOAD] ✓ Found missing entity ${missingId} via alternative ID filter`, {
                                                                    entityId: missingId,
                                                                    name: option.value
                                                                });
                                                                break;
                                                            }
                                                        }
                                                    }
                                                } else {
                                                    debugWarn('matrix-handler', `[AUTO-LOAD] Alternative filter request failed for ${missingId}:`, {
                                                        status: altResponse.status,
                                                        statusText: altResponse.statusText
                                                    });
                                                }
                                            }
                                        } else {
                                            debugWarn('matrix-handler', `[AUTO-LOAD] Fallback API did not return success or options for ${missingId}`, {
                                                success: searchData.success,
                                                hasOptions: !!searchData.options,
                                                responseData: searchData
                                            });
                                        }
                                    } else {
                                        debugWarn('matrix-handler', `[AUTO-LOAD] Fallback API request failed for ${missingId}:`, {
                                            status: searchResponse.status,
                                            statusText: searchResponse.statusText
                                        });
                                    }
                                } catch (error) {
                                    debugError('matrix-handler', `[AUTO-LOAD] Error fetching entity ${missingId}:`, error);
                                }
                            }
                        }
                    } else {
                        debugWarn('matrix-handler', '[AUTO-LOAD] Lookup API did not return success or options', {
                            success: data.success,
                            hasOptions: !!data.options,
                            responseData: data
                        });
                    }
                } else {
                    debugError('matrix-handler', '[AUTO-LOAD] Lookup API request failed', {
                        status: response.status,
                        statusText: response.statusText
                    });
                }
            } catch (error) {
                debugError('matrix-handler', 'Error fetching entity names for auto-load:', error);
            }

            // Track which entity IDs were auto-loaded
            const autoLoadedEntityIds = new Set();

            // Add each entity as a row
            for (const entity of entities) {
                // Normalize entity ID to string for consistent lookup
                const normalizedEntityId = String(entity.entity_id);
                autoLoadedEntityIds.add(normalizedEntityId);

                // Check if row already exists (from restoration)
                const existingRow = matrix.container.querySelector(`tr[data-row-id="${normalizedEntityId}"]`);
                if (existingRow) {
                    // Mark existing row as auto-loaded (it was restored but is actually an auto-loaded entity)
                    existingRow.setAttribute('data-is-auto-loaded', 'true');
                    const headerCell = existingRow.querySelector('td[role="rowheader"]');
                    if (headerCell) {
                        headerCell.style.backgroundColor = '';
                        headerCell.classList.remove('matrix-manual-row-header');
                        // Remove remove button if it exists (auto-loaded rows shouldn't have remove button)
                        const removeButton = headerCell.querySelector('.remove-matrix-row-btn');
                        if (removeButton) {
                            removeButton.remove();
                        }
                    }
                    debugLog('matrix-handler', `Marked existing row ${normalizedEntityId} as auto-loaded`);
                    continue;
                }

                // Get entity data from map, or create minimal data
                let rowData = entityDataMap.get(normalizedEntityId);
                if (!rowData) {
                    // Fallback: create minimal row data if not found in lookup list
                    debugLog('matrix-handler', '[AUTO-LOAD] Entity not found in map', {
                        entityId: entity.entity_id,
                        normalizedEntityId,
                        mapSize: entityDataMap.size,
                        mapKeys: Array.from(entityDataMap.keys()),
                        entityIdSetHas: entityIdSet.has(normalizedEntityId)
                    });
                    rowData = {
                        id: entity.entity_id,
                        _id: entity.entity_id,
                        entity_type: entity.entity_type,
                        name: `Entity ${entity.entity_id}`
                    };
                    debugWarn('matrix-handler', `Entity ${entity.entity_id} not found in lookup list, using fallback name`);
                } else {
                    debugLog('matrix-handler', '[AUTO-LOAD] Entity found in map', {
                        entityId: entity.entity_id,
                        normalizedEntityId,
                        rowDataName: rowData.name
                    });
                }

                // Use the display name from rowData, or fallback to entity_id
                const rowLabel = rowData[displayColumn] || rowData.name || `Entity ${entity.entity_id}`;
                const rowId = String(entity.entity_id);

                debugLog('matrix-handler', `Auto-adding entity row: ${rowLabel} (ID: ${rowId}, Type: ${entity.entity_type})`);

                // Add row using the existing addDynamicRow method (mark as auto-loaded)
                this.addDynamicRow(fieldId, rowLabel, rowData, rowId, true);
            }

            // Mark any other existing rows that match auto-loaded entities as auto-loaded
            // This handles the case where rows were restored before auto-load ran
            const allDataRows = matrix.container.querySelectorAll('tr.matrix-data-row');
            allDataRows.forEach(row => {
                const rowId = row.getAttribute('data-row-id');
                if (rowId && autoLoadedEntityIds.has(rowId)) {
                    row.setAttribute('data-is-auto-loaded', 'true');
                    const headerCell = row.querySelector('td[role="rowheader"]');
                    if (headerCell) {
                        headerCell.style.backgroundColor = '';
                        headerCell.classList.remove('matrix-manual-row-header');
                        // Remove remove button if it exists (auto-loaded rows shouldn't have remove button)
                        const removeButton = headerCell.querySelector('.remove-matrix-row-btn');
                        if (removeButton) {
                            removeButton.remove();
                        }
                    }
                }
            });

            // Recalculate totals after adding rows
            // Note: addDynamicRow already calls calculateMatrixTotals, but we call it again to be safe
            setTimeout(async () => {
                // Cancel any pending scheduled variable resolution (we'll batch resolve all at once)
                if (this.variableResolutionDebounceTimers.has(fieldId)) {
                    clearTimeout(this.variableResolutionDebounceTimers.get(fieldId));
                    this.variableResolutionDebounceTimers.delete(fieldId);
                }
                this.pendingVariableResolution.delete(fieldId);

                this.calculateMatrixTotals(fieldId);
                // Batch resolve variables for all auto-loaded rows (optimized)
                await this.resolveVariablesForAllRows(fieldId);
                // Sort rows alphabetically after auto-loading
                this.sortMatrixRows(fieldId);
                // Check for and highlight duplicates
                this.applyDuplicateEntityHighlighting(fieldId);
                // Update legend visibility after auto-load
                this.updateLegendVisibility(fieldId);
            }, 100);

        } catch (error) {
            debugError('matrix-handler', 'Error auto-loading entities:', error);
        } finally {
            // Clear batch operation flag
            this.batchOperationsInProgress.delete(fieldId);
        }
    }

    /**
     * Sort matrix rows alphabetically by row label
     */
    sortMatrixRows(fieldId) {
        const matrix = this.matrices.get(fieldId);
        if (!matrix || !matrix.container) {
            return;
        }

        let tbody = document.getElementById(`matrix-tbody-${fieldId}`);
        if (!tbody && matrix.container) {
            tbody = matrix.container.querySelector('tbody[id*="matrix-tbody-"]') || matrix.container.querySelector('tbody');
        }
        if (!tbody) {
            return;
        }

        // Remove any existing group header rows
        tbody.querySelectorAll('.matrix-group-header-row').forEach(h => h.remove());

        const dataRows = Array.from(tbody.querySelectorAll('tr.matrix-data-row'));
        if (dataRows.length <= 1 && !matrix.config?.group_by_column) {
            return;
        }

        const searchInterface = tbody.querySelector('.matrix-add-row-interface');
        const totalsRow = tbody.querySelector('tr .matrix-column-total')?.closest('tr');
        const groupByColumn = matrix.config?.group_by_column;
        const groupTableEnabled = matrix.config?.group_table_enabled !== false;
        const effectiveGroupByColumn = (groupByColumn && groupTableEnabled) ? groupByColumn : null;

        dataRows.sort((a, b) => {
            if (effectiveGroupByColumn) {
                const gA = (a.getAttribute('data-group') || 'zzz').toLowerCase();
                const gB = (b.getAttribute('data-group') || 'zzz').toLowerCase();
                if (gA !== gB) return gA.localeCompare(gB);
            }
            const labelA = (a.getAttribute('data-row-label') || '').toLowerCase().trim();
            const labelB = (b.getAttribute('data-row-label') || '').toLowerCase().trim();
            return labelA.localeCompare(labelB);
        });

        dataRows.forEach(row => row.remove());

        const colCount = matrix.config?.columns?.length || 1;
        const totalCols = colCount + 2;
        let lastGroup = null;

        dataRows.forEach(row => {
            if (effectiveGroupByColumn) {
                const group = row.getAttribute('data-group') || 'Other';
                if (group !== lastGroup) {
                    lastGroup = group;
                    const headerRow = document.createElement('tr');
                    headerRow.className = 'matrix-group-header-row bg-gray-100 cursor-pointer';
                    headerRow.dataset.group = group;
                    const td = document.createElement('td');
                    td.colSpan = totalCols;
                    td.className = 'px-3 py-2 text-xs font-semibold text-gray-700';
                    td.innerHTML = `<i class="fas fa-chevron-down text-gray-400 mr-2 transition-transform duration-200"></i>${this._escapeHtml(group)}`;
                    headerRow.appendChild(td);
                    headerRow.addEventListener('click', () => {
                        const icon = headerRow.querySelector('i');
                        let next = headerRow.nextElementSibling;
                        while (next && next.classList.contains('matrix-data-row') && next.getAttribute('data-group') === group) {
                            next.classList.toggle('hidden');
                            next = next.nextElementSibling;
                        }
                        icon.classList.toggle('rotate-180');
                    });
                    if (searchInterface) tbody.insertBefore(headerRow, searchInterface);
                    else if (totalsRow) tbody.insertBefore(headerRow, totalsRow);
                    else tbody.appendChild(headerRow);
                }
            }
            if (searchInterface) tbody.insertBefore(row, searchInterface);
            else if (totalsRow) tbody.insertBefore(row, totalsRow);
            else tbody.appendChild(row);
        });

        this.applyManualRowHighlighting(fieldId);
        debugLog('matrix-handler', `Sorted ${dataRows.length} rows for matrix ${fieldId}${effectiveGroupByColumn ? ' with grouping by ' + effectiveGroupByColumn : ''}`);
    }

    /**
     * Detect and highlight duplicate entities with light red
     */
    applyDuplicateEntityHighlighting(fieldId) {
        const matrix = this.matrices.get(fieldId);
        if (!matrix || !matrix.container) {
            return;
        }

        // Track row IDs and their occurrences
        const rowIdCount = new Map();
        const rowIdRows = new Map();

        const dataRows = matrix.container.querySelectorAll('tr.matrix-data-row');
        dataRows.forEach(row => {
            const rowId = row.getAttribute('data-row-id');
            if (rowId) {
                const count = (rowIdCount.get(rowId) || 0) + 1;
                rowIdCount.set(rowId, count);

                if (!rowIdRows.has(rowId)) {
                    rowIdRows.set(rowId, []);
                }
                rowIdRows.get(rowId).push(row);
            }
        });

        // Find duplicate row IDs (count > 1)
        const duplicateRowIds = Array.from(rowIdCount.entries())
            .filter(([rowId, count]) => count > 1)
            .map(([rowId]) => rowId);

        // Apply red highlighting to all rows with duplicate IDs
        dataRows.forEach(row => {
            const rowId = row.getAttribute('data-row-id');
            const headerCell = row.querySelector('td[role="rowheader"]');

            if (headerCell && rowId && duplicateRowIds.includes(rowId)) {
                // Apply light red background (but preserve beige if it's also manually added)
                const isManual = headerCell.classList.contains('matrix-manual-row-header');
                if (!isManual) {
                    // Only apply red if not already beige (manual takes precedence visually)
                    headerCell.style.backgroundColor = '#ffcccc'; // Light red
                    headerCell.classList.add('matrix-duplicate-row-header');
                } else {
                    // If it's both manual and duplicate, keep beige but add duplicate class for tracking
                    headerCell.classList.add('matrix-duplicate-row-header');
                }
            } else if (headerCell) {
                // Remove duplicate highlighting if not a duplicate
                if (headerCell.classList.contains('matrix-duplicate-row-header') &&
                    !headerCell.classList.contains('matrix-manual-row-header')) {
                    headerCell.style.backgroundColor = '';
                    headerCell.classList.remove('matrix-duplicate-row-header');
                } else if (headerCell.classList.contains('matrix-duplicate-row-header') &&
                           headerCell.classList.contains('matrix-manual-row-header')) {
                    // Keep beige but remove duplicate class if no longer duplicate
                    if (!duplicateRowIds.includes(rowId)) {
                        headerCell.classList.remove('matrix-duplicate-row-header');
                    }
                }
            }
        });

        debugLog('matrix-handler', `Applied duplicate entity highlighting for matrix ${fieldId}`, {
            duplicateCount: duplicateRowIds.length,
            duplicateIds: duplicateRowIds
        });

        return duplicateRowIds.length > 0;
    }

    /**
     * Apply beige highlighting to manually added row headers based on config
     */
    applyManualRowHighlighting(fieldId) {
        const matrix = this.matrices.get(fieldId);
        if (!matrix || !matrix.container || !matrix.config) {
            return;
        }

        const autoLoadEnabled = __configFlag(matrix.config.auto_load_entities, false);
        // Default to highlighting when auto-load is enabled (unless explicitly disabled)
        const highlightManualRows = __configFlag(matrix.config.highlight_manual_rows, autoLoadEnabled);
        if (!highlightManualRows) {
            // If highlighting is disabled, remove any existing highlights
            const allHeaderCells = matrix.container.querySelectorAll('tr.matrix-data-row td[role="rowheader"]');
            allHeaderCells.forEach(headerCell => {
                headerCell.style.backgroundColor = '';
                headerCell.classList.remove('matrix-manual-row-header');
                headerCell.classList.remove('matrix-duplicate-row-header');
            });
            // Hide legend if highlighting is disabled
            this.updateLegendVisibility(fieldId);
            return;
        }

        // Apply highlighting to row headers that are not auto-loaded
        const dataRows = matrix.container.querySelectorAll('tr.matrix-data-row');
        dataRows.forEach(row => {
            const headerCell = row.querySelector('td[role="rowheader"]');
            const isAutoLoaded = row.getAttribute('data-is-auto-loaded') === 'true';
            if (headerCell) {
                if (!isAutoLoaded) {
                    headerCell.style.backgroundColor = '#f5f5dc'; // Beige color
                    headerCell.classList.add('matrix-manual-row-header');
                } else {
                    // Ensure auto-loaded rows don't have the highlight
                    headerCell.style.backgroundColor = '';
                    headerCell.classList.remove('matrix-manual-row-header');
                }
            }
        });

        // Also check for duplicates
        this.applyDuplicateEntityHighlighting(fieldId);

        // Update legend visibility after applying highlighting
        this.updateLegendVisibility(fieldId);

        debugLog('matrix-handler', `Applied manual row header highlighting for matrix ${fieldId} (enabled: ${highlightManualRows})`);
    }

    /**
     * Update legend visibility based on whether there are highlighted rows
     */
    updateLegendVisibility(fieldId) {
        const matrix = this.matrices.get(fieldId);
        if (!matrix || !matrix.container || !matrix.config) {
            return;
        }

        const autoLoadEnabled = __configFlag(matrix.config.auto_load_entities, false);
        const highlightManualRows = __configFlag(matrix.config.highlight_manual_rows, autoLoadEnabled);
        if (!highlightManualRows) {
            // Hide legend if highlighting is disabled
            const legend = matrix.container.querySelector('.matrix-legend');
            if (legend) {
                legend.style.display = 'none';
            }
            return;
        }

        // Check if legend should be hidden
        const legendHide = __configFlag(matrix.config.legend_hide, false);
        if (legendHide) {
            // Hide legend if configured to be hidden
            const legend = matrix.container.querySelector('.matrix-legend');
            if (legend) {
                legend.style.display = 'none';
            }
            return;
        }

        // Check if there are any highlighted rows (manual or duplicate)
        const highlightedRows = matrix.container.querySelectorAll('tr.matrix-data-row td.matrix-manual-row-header');
        const duplicateRows = matrix.container.querySelectorAll('tr.matrix-data-row td.matrix-duplicate-row-header');
        const hasHighlightedRows = highlightedRows.length > 0;
        const hasDuplicateRows = duplicateRows.length > 0;

        // Show legend if there are any highlights or duplicates
        const shouldShowLegend = hasHighlightedRows || hasDuplicateRows;

        // Get or create legend element
        let legend = matrix.container.querySelector('.matrix-legend');
        if (!legend) {
            legend = document.createElement('div');
            legend.className = 'matrix-legend mb-2 p-2 bg-gray-50 border border-gray-200 rounded text-xs';
            legend.style.display = 'none';

            // Insert legend before the table
            const table = matrix.container.querySelector('table');
            if (table) {
                table.parentNode.insertBefore(legend, table);
            } else {
                // If no table yet, append to container
                matrix.container.insertBefore(legend, matrix.container.firstChild);
            }
        }

        // Clear existing legend content
        legend.replaceChildren();

        // Create legend items container
        const legendItemsContainer = document.createElement('div');
        legendItemsContainer.className = 'flex flex-col gap-2';

        // Add beige legend item if there are manually added rows
        if (hasHighlightedRows) {
            const legendItem = document.createElement('div');
            legendItem.className = 'flex items-center space-x-2';

            const legendColor = document.createElement('div');
            legendColor.className = 'w-4 h-4 border border-gray-300 rounded';
            legendColor.style.backgroundColor = '#f5f5dc'; // Beige color
            legendColor.setAttribute('aria-label', 'Beige highlight color');

            const legendTextSpan = document.createElement('span');
            legendTextSpan.className = 'text-gray-700 matrix-legend-text';
            let legendText = matrix.config.legend_text || 'Manually added row';

            // Try to get translated version if translations exist
            if (matrix.config.legend_text_translations) {
                const currentLanguage = this.getCurrentLanguage();
                if (currentLanguage && matrix.config.legend_text_translations[currentLanguage]) {
                    legendText = matrix.config.legend_text_translations[currentLanguage];
                }
            }
            legendTextSpan.textContent = legendText;

            legendItem.appendChild(legendColor);
            legendItem.appendChild(legendTextSpan);
            legendItemsContainer.appendChild(legendItem);
        }

        // Add red legend item if there are duplicate entities
        if (hasDuplicateRows) {
            const legendItem = document.createElement('div');
            legendItem.className = 'flex items-center space-x-2';

            const legendColor = document.createElement('div');
            legendColor.className = 'w-4 h-4 border border-gray-300 rounded';
            legendColor.style.backgroundColor = '#ffcccc'; // Light red color
            legendColor.setAttribute('aria-label', 'Red highlight color for duplicates');

            const legendTextSpan = document.createElement('span');
            legendTextSpan.className = 'text-gray-700 matrix-legend-text';
            legendTextSpan.textContent = 'Duplicate entity';

            legendItem.appendChild(legendColor);
            legendItem.appendChild(legendTextSpan);
            legendItemsContainer.appendChild(legendItem);
        }

        legend.appendChild(legendItemsContainer);

        // Show or hide legend based on whether there are highlighted rows or duplicates
        if (shouldShowLegend) {
            legend.style.display = 'block';
        } else {
            legend.style.display = 'none';
        }

        debugLog('matrix-handler', `Updated legend visibility for matrix ${fieldId}: ${shouldShowLegend ? 'shown' : 'hidden'}`, {
            hasHighlightedRows,
            hasDuplicateRows
        });
    }

    /**
     * Get current user language from session or document
     */
    getCurrentLanguage() {
        // Try to get from meta tag or data attribute
        const languageMeta = document.querySelector('meta[name="language"]');
        if (languageMeta) {
            const raw = String(languageMeta.getAttribute('content') || '').trim();
            return raw.split('_', 1)[0].split('-', 1)[0] || 'en';
        }

        // Try to get from document data attribute
        const docLanguage = document.documentElement.getAttribute('lang');
        if (docLanguage) {
            const raw = String(docLanguage || '').trim();
            return raw.split('_', 1)[0].split('-', 1)[0] || 'en'; // e.g., 'en' from 'en-US' or 'en_US'
        }

        // Try to get from body data attribute
        const bodyLanguage = document.body.getAttribute('data-language');
        if (bodyLanguage) {
            const raw = String(bodyLanguage || '').trim();
            return raw.split('_', 1)[0].split('-', 1)[0] || 'en';
        }

        // Default to English
        return 'en';
    }

    /**
     * Resolve the display label for a matrix column for the current language.
     * IMPORTANT: This does NOT change the column key used for data storage (still `column.name`).
     */
    getColumnDisplayName(column) {
        try {
            const baseName = (typeof column === 'object')
                ? String(column?.name || '')
                : String(column || '');
            if (!baseName) return '';

            if (typeof column === 'object' && column && column.name_translations && typeof column.name_translations === 'object') {
                const lang = this.getCurrentLanguage();
                const cand = column.name_translations[lang] || column.name_translations.en;
                if (typeof cand === 'string' && cand.trim()) {
                    return cand.trim();
                }
            }
            return baseName;
        } catch (_e) {
            return (typeof column === 'object') ? String(column?.name || '') : String(column || '');
        }
    }

    /**
     * Clean up resources for a matrix (call when matrix is removed from DOM)
     */
    cleanupMatrix(fieldId) {
        // Clear any pending debounce timers
        if (this.debounceTimers.has(fieldId)) {
            clearTimeout(this.debounceTimers.get(fieldId));
            this.debounceTimers.delete(fieldId);
        }

        // Remove matrix from map
        const matrix = this.matrices.get(fieldId);
        if (matrix) {
            // Clean up all tooltip event listeners and handlers for all rows in this matrix
            if (matrix.container) {
                const rows = matrix.container.querySelectorAll('tr.matrix-data-row');
                rows.forEach(row => {
                    this.cleanupRowTooltips(row);
                });
            }

            // Clear cached references
            matrix.hiddenField = null;
            this.matrices.delete(fieldId);
            debugLog('matrix-handler', `Cleaned up matrix ${fieldId}`);
        }
    }

    /**
     * Get CSRF token for API requests
     * @returns {string} CSRF token or empty string if not found
     * @throws {Error} If token is required but not found (for critical operations)
     */
    getCsrfToken() {
        // Try meta tag first (most common in this codebase)
        const metaToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        if (metaToken) {
            return metaToken;
        }

        // Try form inputs
        const csrfInput = document.querySelector('input[name="csrf_token"]');
        if (csrfInput && csrfInput.value) {
            return csrfInput.value;
        }

        // Try global variable
        if (window.rawCsrfTokenValue) {
            return window.rawCsrfTokenValue;
        }

        debugWarn('matrix-handler', 'No CSRF token found - API requests may fail');
        return '';
    }
}

// Create and export singleton instance
export const matrixHandler = new MatrixHandler();

// Make it available globally for debugging
window.matrixHandler = matrixHandler;

// Add global test function
window.testMatrixCalculation = () => {
    debugLog('MatrixHandler: Manual test calculation triggered');
    matrixHandler.calculateAllMatrices();
};

// Add function to check what's actually visible on the page
window.checkMatrixTotals = () => {
    console.log('=== MATRIX TOTALS CHECK ===');
    document.querySelectorAll('.matrix-row-total, .matrix-column-total').forEach((el, index) => {
        console.log(`Element ${index + 1}:`, {
            className: el.className,
            textContent: el.textContent,
            innerHTML: el.innerHTML,
            dataRow: el.dataset.row,
            dataColumn: el.dataset.column,
            visible: el.offsetParent !== null,
            computedStyle: window.getComputedStyle(el).display
        });
    });
    console.log('=== END CHECK ===');
};

// Do NOT auto-initialize here. Layout (initLayout) replaces section content via
// replaceChildren(), so matrix containers are recreated. Initialization must
// happen only from main.js after initLayout() so we bind to the final DOM.
// Otherwise we store refs to pre-layout nodes that get detached, causing
// "Matrix container no longer in DOM" and "Cannot auto-load entities".
