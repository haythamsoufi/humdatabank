/** Matrix fetch/API calls. */

import { debugLog, debugError, debugWarn } from '../debug.js';
import { _t } from './shared.js';
import {
    __formatLookupValueForInput,
    __formatSavedScalarForInput,
    __getSavedMatrixCellScalar,
    __persistVariableCellScalar,
    __readMatrixMaxDecimals,
    __savedVariableCellIsStaleLookupMirror,
    __setMatrixNumericCellDisplay,
    __variableCellDiffersFromLookup,
} from './formatting.js';

export function mhFetch(url, opts = {}) {
    const fn = (window.getFetch && window.getFetch()) || fetch;
    return fn(url, opts);
}

const GATEWAY_FAILURE_STATUSES = new Set([403, 502, 503, 504]);

export function isGatewayClassFailure(status) {
    return GATEWAY_FAILURE_STATUSES.has(Number(status));
}

export function isGatewayClassError(error) {
    if (!error) return false;
    if (isGatewayClassFailure(error.status)) return true;
    const msg = String(error.message || '');
    return /Unexpected token '<'/i.test(msg) || /non-JSON response/i.test(msg) || /Invalid JSON response/i.test(msg);
}

export function gatewayFailureMessage(status) {
    const code = Number(status);
    if (code === 403) return _t('Request was rejected. Refresh the page and try again.');
    if (code === 502 || code === 503) return _t('Server is temporarily unavailable. Please try again in a moment.');
    if (code === 504) return _t('Request timed out. Please try again.');
    return _t('Network error. Please refresh and try again.');
}

export async function mhResponseAsResult(response) {
    if (typeof window !== 'undefined' && typeof window.responseAsResult === 'function') {
        return window.responseAsResult(response);
    }
    if (!response.ok) {
        const msg = `HTTP ${response.status}: ${response.statusText || 'Unknown error'}`;
        const errBody = { error: msg };
        return { ok: false, status: response.status, data: errBody, payload: errBody };
    }
    const ct = response.headers.get('Content-Type') || '';
    if (!ct.includes('application/json')) {
        const errBody = { error: 'Non-JSON response' };
        return { ok: false, status: response.status, data: errBody, payload: errBody };
    }
    try {
        const body = await response.json();
        return { ok: true, status: response.status, data: body, payload: body };
    } catch (_) {
        const errBody = { error: 'Invalid JSON response' };
        return { ok: false, status: response.status, data: errBody, payload: errBody };
    }
}

function mhHttpError(result) {
    const message = (result.data && result.data.error) || gatewayFailureMessage(result.status);
    const err = new Error(message);
    err.status = result.status;
    err.response = result.response;
    return err;
}

/** mhFetch + safe JSON parse (Content-Type guard, bounded gateway errors). */
export async function mhFetchJson(url, opts = {}) {
    const response = await mhFetch(url, opts);
    const result = await mhResponseAsResult(response);
    if (!result.ok) {
        throw mhHttpError(result);
    }
    return result.data;
}

export const MATRIX_SEARCH_OPTIONS_FETCH_LIMIT = 5000;
// Cap on how many matching rows we render in the dropdown at once (mirrors the
// server's previous default limit so very large lookup lists don't flood the DOM).

export const MATRIX_SEARCH_OPTIONS_DISPLAY_LIMIT = 500;

export const matrixApiMixin = {
/**
 * Build a stable cache key for a matrix search-row lookup configuration.
 * Same lookup_list_id + display_column + filters + plugin/assignment context
 * always returns the same underlying rows for the lifetime of the page.
 */
_buildMatrixSearchCacheKey(lookupListId, displayColumn, filters, pluginConfig, assignmentEntityStatusId) {
    return JSON.stringify({
        l: lookupListId,
        d: displayColumn,
        f: filters || [],
        p: pluginConfig || null,
        a: assignmentEntityStatusId || null,
        lang: this.getCurrentLanguage()
    });
},

/**
 * Fetch (once) and cache the full set of matrix search-row options for a given
 * lookup configuration. Subsequent dropdown opens, keystrokes, and row selections
 * for the same fieldId/lookup config reuse this cached list and filter/exclude
 * locally instead of re-hitting /forms/matrix/search-rows every time.
 */
async _fetchMatrixSearchOptionsCached(lookupListId, displayColumn, filters, pluginConfig, assignmentEntityStatusId) {
    const cacheKey = this._buildMatrixSearchCacheKey(lookupListId, displayColumn, filters, pluginConfig, assignmentEntityStatusId);

    if (this.matrixSearchOptionsCache.has(cacheKey)) {
        return this.matrixSearchOptionsCache.get(cacheKey);
    }

    const fetchPromise = (async () => {
        const csrfToken = this.getCsrfToken();
        if (!csrfToken) {
            throw new Error('CSRF_TOKEN_MISSING');
        }

        const requestBody = {
            lookup_list_id: lookupListId,
            display_column: displayColumn,
            filters: filters || [],
            search_term: '',
            existing_rows: [],
            // Fetch the whole list once; search/exclusion happens client-side from the cache.
            limit: MATRIX_SEARCH_OPTIONS_FETCH_LIMIT
        };

        if (assignmentEntityStatusId) {
            requestBody.assignment_entity_status_id = assignmentEntityStatusId;
        }
        if (pluginConfig) {
            requestBody.plugin_config = pluginConfig;
        }

        const data = await mhFetchJson('/forms/matrix/search-rows', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(requestBody)
        });
        if (!data.success) {
            throw new Error(data.message || _t('Error loading options'));
        }

        return Array.isArray(data.options) ? data.options : [];
    })();

    // Cache the in-flight promise immediately so concurrent callers (e.g. a
    // focus event and an input event firing back-to-back) share one request.
    this.matrixSearchOptionsCache.set(cacheKey, fetchPromise);

    try {
        return await fetchPromise;
    } catch (error) {
        // Don't cache failures — allow retry on the next interaction.
        this.matrixSearchOptionsCache.delete(cacheKey);
        throw error;
    }
},

/**
 * Search list options via API (cached — see _fetchMatrixSearchOptionsCached)
 */
async searchListOptions(fieldId, lookupListId, displayColumn, filters, searchTerm) {
    if (!lookupListId || !displayColumn) {
        debugError('matrix-handler', 'Missing required parameters for search', { lookupListId, displayColumn });
        this.showDropdownMessage(fieldId, _t('Matrix configuration is incomplete'));
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

        // Fetched once per lookup_list_id/display_column/filters/plugin combination
        // and reused for every keystroke, dropdown open, and row selection below.
        const allOptions = await this._fetchMatrixSearchOptionsCached(
            lookupListId, displayColumn, filters, pluginConfig, assignmentEntityStatusId
        );

        // Apply the same exclusion/search-term rules the server used to apply,
        // but locally against the cached option list.
        const existingRows = this.getExistingRows(fieldId);
        const normalizedSearchTerm = (searchTerm || '').trim().toLowerCase();

        const filteredOptions = allOptions.filter((option) => {
            const rowValue = String(option?.value ?? '');
            if (!rowValue || existingRows.includes(rowValue)) return false;
            if (normalizedSearchTerm && !rowValue.toLowerCase().includes(normalizedSearchTerm)) return false;
            return true;
        }).slice(0, MATRIX_SEARCH_OPTIONS_DISPLAY_LIMIT);

        this.renderSearchResults(fieldId, filteredOptions);
    } catch (error) {
        if (error && error.message === 'CSRF_TOKEN_MISSING') {
            debugError('matrix-handler', 'CSRF token missing for API request');
            this.showDropdownMessage(fieldId, _t('Authentication error. Please refresh the page.'));
            return;
        }
        debugError('matrix-handler', 'Error searching list options:', error);
        this.showDropdownMessage(fieldId, _t('Error loading options. Please try again.'));
    }
},

/**
 * Get assignment entity status ID from form context
 */
getAssignmentEntityStatusId() {
    const jsContext = document.getElementById('entry-form-js-context');
    if (jsContext?.dataset?.assignmentEntityStatusId) {
        const value = parseInt(jsContext.dataset.assignmentEntityStatusId, 10);
        if (!isNaN(value)) {
            debugLog('matrix-handler', '[VARIABLE RESOLUTION] Found assignment_entity_status_id from entry-form-js-context', { value });
            return value;
        }
    }

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
},

/**
 * Return preview entity context { entity_id, entity_type, period_name } when in template
 * preview mode (no real AES), or null when in a normal assignment.
 */
_getPreviewEntityCtx() {
    const meta = window.metadataContext || {};
    const entityId = meta.entity_id ? parseInt(meta.entity_id) : null;
    const entityType = meta.entity_type || null;
    if (!entityId || !entityType) return null;
    return {
        entity_id: entityId,
        entity_type: entityType,
        period_name: String(meta.assignment_period || '')
    };
},

/**
 * Build the entity-context portion of a /api/v1/variables/resolve request body.
 * Uses the real AES id when available; falls back to preview context in preview mode.
 * Returns null if neither context is available.
 *
 * @param {object} extra  - Additional fields to merge into the body.
 * @returns {object|null}
 */
_buildVarsBody(extra) {
    const aesId = this.getAssignmentEntityStatusId();
    if (aesId) {
        return Object.assign({ assignment_entity_status_id: aesId }, extra);
    }
    const pvCtx = this._getPreviewEntityCtx();
    if (pvCtx) {
        return Object.assign({
            preview_entity_id: pvCtx.entity_id,
            preview_entity_type: pvCtx.entity_type,
            preview_period_name: pvCtx.period_name
        }, extra);
    }
    return null;
},

/**
 * Get template ID from form context
 */
getTemplateId() {
    const jsContext = document.getElementById('entry-form-js-context');
    if (jsContext?.dataset?.templateId) {
        const value = parseInt(jsContext.dataset.templateId, 10);
        if (!isNaN(value)) {
            debugLog('matrix-handler', '[VARIABLE RESOLUTION] Found template_id from entry-form-js-context', { value });
            return value;
        }
    }

    const metaTemplateId = window.metadataContext && window.metadataContext.template_id;
    if (metaTemplateId !== undefined && metaTemplateId !== null && metaTemplateId !== '') {
        const value = parseInt(metaTemplateId, 10);
        if (!isNaN(value)) {
            debugLog('matrix-handler', '[VARIABLE RESOLUTION] Found template_id from metadataContext', { value });
            return value;
        }
    }

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
},

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
},

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
        const result = await mhResponseAsResult(await mhFetch(`/api/forms/lookup-lists/${lookupListId}/options?filters=[]`, {
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        }));

        if (result.ok) {
            const json = result.data;
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
},

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
},

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

    // Get template ID and build request body (supports normal AES and preview mode)
    const templateId = this.getTemplateId();
    const requestBody = this._buildVarsBody({ template_id: templateId });

    if (!requestBody || !templateId) {
        debugWarn('matrix-handler', '[BATCH VARIABLE RESOLUTION] Missing required context', {
            hasRequestBody: !!requestBody,
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

        // Prefer entry-bootstrap resolved_variables when it covers every row.
        let batchResults = null;
        try {
            if (window.__entryBootstrapPromise) {
                await window.__entryBootstrapPromise;
            }
            const bootResolved = window.__entryBootstrap && window.__entryBootstrap.resolved_variables;
            if (bootResolved && typeof bootResolved === 'object') {
                const fromBoot = {};
                let allCovered = true;
                for (const eid of rowEntityIds) {
                    const vals = bootResolved[String(eid)] || bootResolved[eid];
                    if (!vals || typeof vals !== 'object') {
                        allCovered = false;
                        break;
                    }
                    fromBoot[eid] = vals;
                }
                if (allCovered) {
                    batchResults = fromBoot;
                    debugLog('matrix-handler', '[BATCH VARIABLE RESOLUTION] Using entry-bootstrap resolved_variables', {
                        fieldId,
                        rowCount: rowEntityIds.length,
                    });
                }
            }
        } catch (_) { /* fall through to API */ }

        if (!batchResults) {
            requestBody.row_entity_ids = rowEntityIds;

            // Call batch API
            const data = await mhFetchJson('/api/v1/variables/resolve', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify(requestBody)
            });
            batchResults = data.results || {};
        }

        // Process results for each row
        rowsToResolve.forEach(rowInfo => {
            const resolvedVariables = batchResults[rowInfo.entityId] || batchResults[String(rowInfo.entityId)] || {};
            this._applyResolvedVariablesToRow(fieldId, rowInfo.rowId, rowInfo.rowElement, rowInfo.variableInputs, resolvedVariables);
        });

        // Update matrix data and totals once after all rows are processed
        this.calculateMatrixTotals(fieldId);
        this.applyVariableLookupComparison(fieldId);
        this._lockMatrixContainerIfReadOnly(matrix.container);

    } catch (error) {
        debugError('matrix-handler', '[BATCH VARIABLE RESOLUTION] Error in batch resolution:', {
            error,
            message: error.message
        });
        if (isGatewayClassError(error)) {
            const msg = gatewayFailureMessage(error.status) || error.message;
            if (typeof this.showMatrixError === 'function') {
                this.showMatrixError(fieldId, msg);
            } else if (window.showAlert) {
                window.showAlert(msg, 'error');
            }
            return;
        }
        // Fallback to individual resolution only for non-gateway failures
        for (const rowInfo of rowsToResolve) {
            await this.resolveVariablesForRow(fieldId, rowInfo.rowId, null);
        }
    }
},

/**
 * Apply resolved variables to a row's inputs (helper method)
 */
_applyResolvedVariablesToRow(fieldId, rowEntityId, rowElement, variableInputs, resolvedVariables) {
    const matrix = this.matrices.get(fieldId);
    if (!matrix) return;
    if (!matrix.lookupRefs) matrix.lookupRefs = {};
    const labels = this.getVariableTooltipLabels(matrix.config);

    variableInputs.forEach((input) => {
        const variableName = input.getAttribute('data-variable-name');
        const cellKey = input.getAttribute('data-cell-key');
        const saveValue = input.getAttribute('data-variable-save-value') === 'true';

        let lookupValue = '';
        if (variableName && Object.prototype.hasOwnProperty.call(resolvedVariables, variableName)) {
            lookupValue = resolvedVariables[variableName];
        }
        lookupValue = __formatLookupValueForInput(input.type, lookupValue);
        if (cellKey) {
            matrix.lookupRefs[cellKey] = lookupValue;
            input.setAttribute('data-lookup-value', lookupValue);
        }

        if (!saveValue) {
            if (input.type === 'checkbox') {
                input.checked = lookupValue === '1';
            } else {
                __setMatrixNumericCellDisplay(input, lookupValue);
            }
            this.updateVariableModificationIndicator(input, '', '', labels);
            return;
        }

        const hasSaved = cellKey && matrix.data && matrix.data[cellKey] !== undefined;
        const savedRaw = hasSaved ? matrix.data[cellKey] : undefined;
        let savedScalar = hasSaved
            ? __getSavedMatrixCellScalar(savedRaw)
            : lookupValue;
        const staleUnmodifiedSave = hasSaved
            && lookupValue !== ''
            && __savedVariableCellIsStaleLookupMirror(savedRaw)
            && __variableCellDiffersFromLookup(
                lookupValue,
                savedScalar,
                input.type,
                __readMatrixMaxDecimals(input)
            );

        if (hasSaved && !staleUnmodifiedSave) {
            const display = __formatSavedScalarForInput(input.type, savedScalar);
            if (input.type === 'checkbox') {
                input.checked = display === '1';
            } else {
                __setMatrixNumericCellDisplay(input, display);
            }
        } else if (variableName && Object.prototype.hasOwnProperty.call(resolvedVariables, variableName)) {
            if (input.type === 'checkbox') {
                input.checked = lookupValue === '1';
            } else {
                __setMatrixNumericCellDisplay(input, lookupValue);
            }
            savedScalar = lookupValue;
            if (cellKey && saveValue) {
                matrix.data[cellKey] = __persistVariableCellScalar(
                    lookupValue,
                    __readMatrixMaxDecimals(input)
                );
            }
        }

        this.updateVariableModificationIndicator(input, lookupValue, savedScalar, labels);
    });
},

/**
 * Resolve variables for a specific matrix row
 */
async resolveVariablesForRow(fieldId, rowEntityId, rowData = null) {
    const matrix = this.matrices.get(fieldId);
    if (!matrix || !matrix.container) {
        debugWarn('matrix-handler', '[VARIABLE RESOLUTION] Matrix not found or container missing', { fieldId });
        return;
    }

    // Get template ID from the form context
    const templateId = this.getTemplateId();
    if (!templateId) {
        debugWarn('matrix-handler', '[VARIABLE RESOLUTION] Cannot resolve variables: template_id not found');
        return;
    }

    // Build entity context (supports normal AES and preview mode)
    const _baseBody = this._buildVarsBody({ template_id: templateId });
    if (!_baseBody) {
        debugWarn('matrix-handler', '[VARIABLE RESOLUTION] Cannot resolve variables: no entity context (AES or preview)');
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
        const requestBody = Object.assign({}, _baseBody, {
            row_entity_id: entityId ? parseInt(entityId) : null
        });

        // Call API to resolve variables
        const data = await mhFetchJson('/api/v1/variables/resolve', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody)
        });
        const resolvedVariables = data.variables || {};

        this._applyResolvedVariablesToRow(fieldId, rowEntityId, rowElement, variableInputs, resolvedVariables);

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
};
