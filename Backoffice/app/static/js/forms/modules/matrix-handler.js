/**
 * Matrix Handler Module
 * Handles matrix table interactions, calculations, and data management
 */

import { debugLog, debugError, debugWarn } from './debug.js';
import { _t, __canEditMatrixContainer } from './matrix/shared.js';
import {
    __formatInteger,
    __integerInputValue,
    __setMatrixNumericInputValue,
    __setMatrixNumericCellDisplay,
    __syncWholeNumberViolationHighlight,
    __parseMatrixNumericCellValue,
    __configFlag,
    __normalizeVariableCompareValue,
    __getSavedMatrixCellScalar,
    __savedVariableCellIsUserModified,
    __savedVariableCellIsStaleLookupMirror,
    __formatLookupValueForInput,
    __formatSavedScalarForInput,
    __persistVariableCellScalar,
    __variableCellDiffersFromLookup,
    __resolveMatrixLocalizedLabel,
    __serializeMatrixData,
    __getMatrixColumnNames,
    __parseMatrixCellKey,
    __readMatrixMaxDecimals,
    __rawValueHasNonZeroFraction,
    __cellValueToNumber,
    __reorderMatrixData,
    __normalizeVariableNumericValue,
    __toVariableTickValue,
    __formatNumberForDisplay,
    __resolveColumnMaxDecimals,
    __parseMatrixNumericValue,
    __isEmptyVariableValue,
} from './matrix/formatting.js';
import {
    __parseCarryForwardRef,
    __matrixCellValuesMatch,
    __inputValueForMatrixCompare,
    matrixCarryForwardMixin,
} from './matrix/carry-forward.js';
import {
    ROW_TOTAL_COLUMN_NAME,
    __rowTotalManualEnabled,
    __rowTotalValidation,
    __updateRowTotalConflict,
    __storedRowTotalManualScalar,
    __effectiveRowTotalValue,
    __ROW_TOTAL_INPUT_WRAPPER_CLASS,
    __ROW_TOTAL_INPUT_CLASS,
    __createRowTotalConflictIndicator,
    __rowTotalCellKey,
    __computedRowTotalFromData,
    __parseRowTotalManualValue,
    matrixTotalsMixin,
} from './matrix/totals.js';
import { matrixValidationMixin } from './matrix/validation.js';
import { mhFetch, MATRIX_SEARCH_OPTIONS_FETCH_LIMIT, MATRIX_SEARCH_OPTIONS_DISPLAY_LIMIT, matrixApiMixin } from './matrix/api.js';
import { matrixSearchUiMixin } from './matrix/search-ui.js';
import { matrixVariablesMixin } from './matrix/variables.js';
import { matrixDynamicRowsMixin } from './matrix/dynamic-rows.js';
import { matrixAutoLoadMixin } from './matrix/auto-load.js';

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
        // Cache of in-flight/resolved /forms/matrix/search-rows option lists, keyed by
        // lookup_list_id + display_column + filters + plugin_config + assignment context.
        // See _fetchMatrixSearchOptionsCached().
        this.matrixSearchOptionsCache = new Map();

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
            matrixInfo.carryForwardRef = __parseCarryForwardRef(container);
            matrixInfo.lookupRefs = {};
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
     * Whether matrix cell values may be edited (mirrors server can_edit / entry form POST availability).
     * @param {HTMLElement|null} container - `.matrix-container` element
     * @returns {boolean}
     */

    /**
     * Whether matrix cell values may be edited (mirrors server can_edit / entry form POST availability).
     * @param {HTMLElement|null} container - `.matrix-container` element
     * @returns {boolean}
     */
    _canEditMatrix(container) {
        return __canEditMatrixContainer(container);
    }

    /**
     * Apply disabled/readonly state to a matrix cell input.
     * @param {HTMLInputElement} input
     * @param {HTMLElement} container
     * @param {boolean} variableReadonly
     */

    /**
     * Apply disabled/readonly state to a matrix cell input.
     * @param {HTMLInputElement} input
     * @param {HTMLElement} container
     * @param {boolean} variableReadonly
     */
    _applyMatrixInputEditability(input, container, variableReadonly = false) {
        if (!input || !container) return;
        const shouldDisable = !this._canEditMatrix(container) || variableReadonly;
        input.disabled = shouldDisable;
        if (input.type !== 'checkbox') {
            if (shouldDisable) {
                input.setAttribute('readonly', 'readonly');
            } else {
                input.removeAttribute('readonly');
            }
        }
    }

    /**
     * Lock all matrix inputs when the form is view-only (submitted/approved/etc.).
     * @param {HTMLElement} container
     */

    /**
     * Lock all matrix inputs when the form is view-only (submitted/approved/etc.).
     * @param {HTMLElement} container
     */
    _lockMatrixContainerIfReadOnly(container) {
        if (!container || this._canEditMatrix(container)) return;

        container.querySelectorAll(
            'input[data-cell-key], input[data-is-row-total="true"], input.row-total-input'
        ).forEach((input) => {
            const variableReadonly = input.getAttribute('data-variable-readonly') === 'true';
            this._applyMatrixInputEditability(input, container, variableReadonly);
        });

        container.querySelectorAll('.remove-matrix-row-btn').forEach((btn) => {
            btn.hidden = true;
        });
    }

    _lockAllReadOnlyMatrices() {
        this.matrices.forEach((matrix) => {
            if (matrix?.container) {
                this._lockMatrixContainerIfReadOnly(matrix.container);
            }
        });
        document.querySelectorAll('.matrix-container[data-can-edit="false"]').forEach((container) => {
            this._lockMatrixContainerIfReadOnly(container);
        });
    }

    /**
     * Setup event listeners for matrix interactions
     */

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
            }
        });

        // Listen for blur events for validation and numeric finalization
        document.addEventListener('blur', (e) => {
            if (e.target.matches('.matrix-container input[type="number"], .matrix-container input[data-numeric="true"]') ||
                e.target.matches('.matrix-container input[data-column-type="variable"]')) {
                const container = e.target.closest('.matrix-container');
                const fieldId = container?.dataset?.fieldId;
                if (fieldId && e.target.matches('.matrix-container input[type="number"], .matrix-container input[data-numeric="true"]')) {
                    this.updateMatrixData(fieldId, e.target);
                    __setMatrixNumericCellDisplay(e.target);
                    requestAnimationFrame(() => {
                        if (this.matrices.has(fieldId)) {
                            this.calculateMatrixTotals(fieldId);
                        }
                    });
                }
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
            if (e.target.closest('.row-total-restore')) {
                e.preventDefault();
                this.handleRowTotalRestore(e.target.closest('.row-total-restore'));
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
                hiddenField: hiddenField,
                carryForwardRef: __parseCarryForwardRef(container),
                lookupRefs: {},
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
                                    this.applyWholeNumberViolationHighlighting(fieldId);
                                    this.applyPrefilledCellHighlighting(fieldId);
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
                // Resolve variable columns on load (read-only/closed forms need this too)
                if (this._matrixHasVariableColumns(matrixConfig)) {
                    matrixPromises.push(
                        Promise.resolve()
                            .then(() => this.resolveVariablesForAllRows(fieldId))
                            .then(() => {
                                this.applyWholeNumberViolationHighlighting(fieldId);
                                this.applyPrefilledCellHighlighting(fieldId);
                            })
                    );
                } else {
                    this.applyPrefilledCellHighlighting(fieldId);
                }
            }

            // Apply highlighting for static matrices only; list_library restores in restoreDynamicRows
            if (matrixConfig.row_mode !== 'list_library') {
                setTimeout(() => {
                    this.applyManualRowHighlighting(fieldId);
                    this.applyWholeNumberViolationHighlighting(fieldId);
                    this.applyPrefilledCellHighlighting(fieldId);
                }, 50);
            }

            // Note: Event listeners are handled via event delegation in setupEventListeners
            // No need to add per-input listeners to avoid duplicate event firing

            const tbody = container.querySelector('tbody');
            if (tbody) {
                this._ensureTotalsRowAtTop(tbody);
            }

            debugLog('matrix-handler', `Initialized matrix for field ${fieldId}`, config);
        });

        return Promise.all(matrixPromises).then(() => {
            this._lockAllReadOnlyMatrices();
        });
    }

    /**
     * Parse existing matrix data from the hidden field
     */

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

        if (container && !this._canEditMatrix(container)) {
            debugLog('matrix-handler', 'Ignoring change on read-only matrix', { fieldId });
            return;
        }

        // Ignore changes from disabled inputs (shouldn't happen, but safety check)
        if (input.disabled) {
            debugLog('matrix-handler', `Ignoring change from disabled input`, input);
            return;
        }

        // Clear any existing validation errors for this input
        this.clearInputError(input);

        if (input.type !== 'checkbox') {
            __syncWholeNumberViolationHighlight(input);
        }

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
            if (!input.getAttribute('data-whole-number-violation')) {
                this.applyPrefilledCellHighlighting(fieldId);
            }
            // Use requestAnimationFrame to ensure DOM is updated before calculation
            requestAnimationFrame(() => {
                // Double-check matrix still exists before calculating
                if (this.matrices.has(fieldId) && this.matrices.get(fieldId).container.isConnected) {
                    this.calculateMatrixTotals(fieldId);
                    this.applyPrefilledCellHighlighting(fieldId);
                }
            });
        }, this.DEBOUNCE_DELAY));
    }

    /**
     * Update matrix data when input changes
     */

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
        const isRowTotal = input.dataset.isRowTotal === 'true';

        debugLog('matrix-handler', `updateMatrixData for field ${fieldId}: cellKey="${cellKey}", columnType="${columnType}", input.value="${input.value}", input.type="${input.type}"`);

        if (isRowTotal && cellKey) {
            const autoSum = parseFloat(input.getAttribute('data-original-value')) || 0;
            const manualNum = __parseRowTotalManualValue(input.value);
            const isConflict = manualNum != null && manualNum !== autoSum;
            if (isConflict) {
                matrix.data[cellKey] = manualNum;
            } else if (matrix.data[cellKey] !== undefined) {
                delete matrix.data[cellKey];
            }
            __updateRowTotalConflict(input, autoSum, isConflict ? manualNum : '', __rowTotalValidation(matrix.config), isConflict);
            if (matrix.hiddenField) {
                matrix.hiddenField.value = __serializeMatrixData(matrix.data);
            }
            return;
        }

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
            value = input.checked ? 1 : 0;
            if (isVariable && cellKey) {
                matrix.data[cellKey] = input.checked ? '1' : '0';
                this.applyVariableLookupComparisonForInput(fieldId, input);
            }
        } else if (isVariable) {
            const maxDecimals = __readMatrixMaxDecimals(input);
            const rawValue = __inputValueForMatrixCompare(input);
            value = rawValue;
            if (cellKey) {
                matrix.data[cellKey] = __persistVariableCellScalar(rawValue, maxDecimals);
                this.applyVariableLookupComparisonForInput(fieldId, input);
            }
        } else {
            const maxDecimals = __readMatrixMaxDecimals(input);
            const trimmed = String(input.value || '').trim();
            if (trimmed === '') {
                value = 0;
            } else if (maxDecimals === 0 && __rawValueHasNonZeroFraction(input.value, maxDecimals)) {
                const unformatFn = typeof window.__numericUnformat === 'function' ? window.__numericUnformat : null;
                const rawString = unformatFn
                    ? unformatFn(trimmed, maxDecimals)
                    : trimmed.replace(/,/g, '');
                const parsed = parseFloat(rawString);
                value = isFinite(parsed) ? parsed : trimmed;
            } else {
                value = __parseMatrixNumericCellValue(input.value, maxDecimals);
            }
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

    /**
     * Handle data availability checkbox changes
     */
    handleDataAvailabilityChange(checkbox) {
        const container = checkbox.closest('.matrix-container');
        if (!container) return;

        if (!this._canEditMatrix(container)) return;

        const fieldId = container.dataset.fieldId;
        const matrix = this.matrices.get(fieldId);
        if (!matrix) return;

        // Disable/enable matrix inputs based on data availability
        const inputs = container.querySelectorAll('input[type="number"], input[data-numeric="true"]');
        const isDisabled = checkbox.checked;

        inputs.forEach(input => {
            if (isDisabled) {
                input.disabled = true;
                input.value = '';
            } else {
                const variableReadonly = input.getAttribute('data-variable-readonly') === 'true';
                this._applyMatrixInputEditability(input, container, variableReadonly);
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

    /**
     * Re-read all cell inputs into matrix.data before submit/draft save.
     * Display formatting alone does not update matrix.data — this ensures saved values
     * match what the user sees (including normalization of legacy mis-parsed numbers).
     */
    syncMatrixDataFromInputs(fieldId) {
        const matrix = this.matrices.get(fieldId);
        if (!matrix || !matrix.container?.isConnected) return;

        matrix.container.querySelectorAll('input[data-cell-key]').forEach((input) => {
            this.updateMatrixData(fieldId, input);
        });
    }

    /**
     * Collect matrix data for form submission
     */

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

            this.syncMatrixDataFromInputs(fieldId);

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
                    __setMatrixNumericCellDisplay(input, displayValue != null ? String(displayValue) : '');
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
        // Normalize config rows: may be plain strings or {text, ...} objects
        const configRowStrings = (config.rows || []).map(r => (r && typeof r === 'object' ? (r.text || '') : r)).filter(Boolean);
        const availableRows = rows.length > 0 ? rows : configRowStrings;

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
     * Return the first validation message for a matrix cell, or null if valid.
     */

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
     * Replace built-in metadata tokens like [assignment_period] in display text.
     */

    /**
     * Replace built-in metadata tokens like [assignment_period] in display text.
     */
    resolveMetadataVariablesInText(text) {
        if (!text || typeof text !== 'string' || !text.includes('[')) {
            return text;
        }
        const meta = window.metadataContext || {};
        return text.replace(/\[(\w+)\]/g, (match, tokenName) => {
            if (!Object.prototype.hasOwnProperty.call(meta, tokenName)) {
                return match;
            }
            const value = meta[tokenName];
            return (value === undefined || value === null) ? '' : String(value);
        });
    }

    /**
     * Resolve the display label for a matrix column for the current language.
     * IMPORTANT: This does NOT change the column key used for data storage (still `column.name`).
     */

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

            let displayName = baseName;
            if (typeof column === 'object' && column && column.name_translations && typeof column.name_translations === 'object') {
                const lang = this.getCurrentLanguage();
                const cand = column.name_translations[lang] || column.name_translations.en;
                if (typeof cand === 'string' && cand.trim()) {
                    displayName = cand.trim();
                }
            }
            return this.resolveMetadataVariablesInText(displayName);
        } catch (_e) {
            return (typeof column === 'object') ? String(column?.name || '') : String(column || '');
        }
    }

    /**
     * Clean up resources for a matrix (call when matrix is removed from DOM)
     */

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

    /**
     * After auth-drafts restores flat field values (including matrix hidden JSON),
     * re-parse hidden fields into matrix.data and repaint cells. Required because
     * initializeMatrices() ran before IndexedDB restore updated those inputs.
     */
    syncFromDraftRestore() {
        const matrixPromises = [];
        this.matrices.forEach((matrix, fieldId) => {
            const container = matrix.container;
            if (!container || !container.isConnected) return;
            const existingData = this.parseExistingData(container);
            matrix.data = existingData && typeof existingData === 'object' ? existingData : {};
            const config = matrix.config || {};
            if (config.row_mode === 'list_library') {
                matrixPromises.push(
                    this.restoreDynamicRows(fieldId).then(() => {
                        this.applyManualRowHighlighting(fieldId);
                    }).catch((err) => {
                        debugError('matrix-handler', 'syncFromDraftRestore restoreDynamicRows failed', err);
                    })
                );
            } else {
                this.restoreStaticMatrixValues(fieldId);
            }
        });
        return Promise.all(matrixPromises).then(() => {
            this._lockAllReadOnlyMatrices();
        });
    }
}

Object.assign(
    MatrixHandler.prototype,
    matrixTotalsMixin,
    matrixValidationMixin,
    matrixCarryForwardMixin,
    matrixApiMixin,
    matrixSearchUiMixin,
    matrixVariablesMixin,
    matrixDynamicRowsMixin,
    matrixAutoLoadMixin,
);
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
    (window.__clientLog || console.log)('=== MATRIX TOTALS CHECK ===');
    document.querySelectorAll('.matrix-row-total, .matrix-column-total').forEach((el, index) => {
        (window.__clientLog || console.log)(`Element ${index + 1}:`, {
            className: el.className,
            textContent: el.textContent,
            innerHTML: el.innerHTML,
            dataRow: el.dataset.row,
            dataColumn: el.dataset.column,
            visible: el.offsetParent !== null,
            computedStyle: window.getComputedStyle(el).display
        });
    });
    (window.__clientLog || console.log)('=== END CHECK ===');
};

// Do NOT auto-initialize here. Layout (initLayout) replaces section content via
// replaceChildren(), so matrix containers are recreated. Initialization must
// happen only from main.js after initLayout() so we bind to the final DOM.
// Otherwise we store refs to pre-layout nodes that get detached, causing
// stale refs and broken matrix behavior.
