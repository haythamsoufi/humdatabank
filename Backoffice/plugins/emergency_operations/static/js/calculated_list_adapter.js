/**
 * Calculated-list adapter for the emergency_operations lookup.
 *
 * The core runtime (calculated-lists-runtime.js) loads this module when a
 * question's lookup id is emergency_operations. It builds the list-data
 * request, formats "CODE Name (part of PARENT)", and writes the hidden
 * appeal metadata the form submits with the selection.
 */

const MODULE = 'calculated-lists-runtime';

function debugEnabled() {
    try {
        return window.localStorage?.getItem(`ifrc:debug:module:${MODULE}`) === '1';
    } catch (_err) {
        return false;
    }
}

function debugLog(_module, message, detail) {
    if (!debugEnabled()) return;
    if (detail !== undefined) {
        console.log(message, detail);
    } else {
        console.log(message);
    }
}

function traceEmOpsFilter(fieldId, step, detail) {
    const id = fieldId != null && fieldId !== '' ? String(fieldId) : '?';
    if (detail !== undefined) {
        debugLog(MODULE, `[EmOpsFilter] field=${id} | ${step}`, detail);
    } else {
        debugLog(MODULE, `[EmOpsFilter] field=${id} | ${step}`);
    }
}

function summarizeEmOpsTypes(rows) {
    const counts = {};
    (rows || []).forEach((row) => {
        const t = row && row.type != null ? String(row.type) : '(missing type)';
        counts[t] = (counts[t] || 0) + 1;
    });
    return counts;
}

function scalarDisplayText(value) {
    if (value == null || value === '') return '';
    if (typeof value === 'string') {
        const trimmed = value.trim();
        return trimmed === '[object Object]' ? '' : trimmed;
    }
    if (typeof value === 'number' || typeof value === 'boolean') return String(value);
    if (typeof value === 'object') {
        const name = scalarDisplayText(value.name ?? value.label ?? value.title);
        const code = scalarDisplayText(value.code ?? value.id);
        if (name && code) return `${name} (${code})`;
        return name || code || '';
    }
    const text = String(value);
    return text === '[object Object]' ? '' : text;
}

function formatEmergencyOperationLabel(row) {
    if (!row || typeof row !== 'object') return '';
    const name = scalarDisplayText(row.name);
    const code = scalarDisplayText(row.code);
    const partOf = scalarDisplayText(row.part_of);
    if (name || code) {
        let label = name && code ? `${code} ${name}` : (code || name);
        if (partOf && partOf.toUpperCase() !== String(code || '').toUpperCase()) {
            label = `${label} (part of ${partOf})`;
        }
        return label;
    }
    return scalarDisplayText(row.name_with_code);
}

function resolveAssignedCountryIso() {
    const ctx = window.metadataContext;
    if (ctx) {
        const fromCtx = String(ctx.country_iso2 || ctx.country_iso || '').trim();
        if (fromCtx) {
            return fromCtx.toUpperCase();
        }
    }

    const countryIsoElement = document.querySelector('[data-country-iso]');
    if (countryIsoElement && countryIsoElement.dataset.countryIso) {
        return countryIsoElement.dataset.countryIso.trim().toUpperCase();
    }

    const urlParams = new URLSearchParams(window.location.search);
    const countryParam = urlParams.get('country') || urlParams.get('iso');
    if (countryParam) {
        return countryParam.toUpperCase();
    }

    if (window.countryInfo) {
        const fromInfo = window.countryInfo.iso || window.countryInfo.iso3;
        if (fromInfo) {
            return String(fromInfo).toUpperCase();
        }
    }

    return null;
}

function parseEmergencyDisplayValue(value) {
    const text = String(value || '').trim();
    if (!text) return null;
    const partOfMatch = text.match(/^(.*?)\s+\(part of ([A-Za-z0-9]+)\)\s*$/i);
    const body = partOfMatch ? partOfMatch[1].trim() : text;
    const codeFirst = body.match(/^([A-Z][A-Z0-9]{4,})\s+(.+)$/);
    if (codeFirst) {
        return { name: codeFirst[2].trim(), code: codeFirst[1].trim() };
    }
    const nameFirst = body.match(/^(.+?)\s+\(([A-Z][A-Z0-9]{4,})\)\s*$/);
    if (nameFirst) {
        return { name: nameFirst[1].trim(), code: nameFirst[2].trim() };
    }
    return { name: text, code: '' };
}

function resolveCalculatedSelectFieldId(selectElement) {
    if (selectElement.dataset.fieldItemId) {
        return selectElement.dataset.fieldItemId;
    }
    const id = selectElement.id || '';
    const standardMatch = id.match(/^field-(\d+)$/);
    return standardMatch ? standardMatch[1] : null;
}

function getEmergencyMetadataHiddenInputName(selectElement) {
    const fieldId = resolveCalculatedSelectFieldId(selectElement);
    const selectName = selectElement.name || '';
    if (selectName.startsWith('repeat_')) {
        return selectName.replace(/_\d+$/, '_emergency_metadata');
    }
    return fieldId ? `field_disagg_metadata[${fieldId}]` : null;
}

function findOrCreateEmergencyMetadataHiddenInput(selectElement) {
    const name = getEmergencyMetadataHiddenInputName(selectElement);
    if (!name) return null;

    const form = selectElement.form || selectElement.closest('form');
    if (!form) return null;

    for (const input of form.querySelectorAll('input[type="hidden"]')) {
        if (input.name === name) return input;
    }

    const hidden = document.createElement('input');
    hidden.type = 'hidden';
    hidden.name = name;
    hidden.value = '';
    form.appendChild(hidden);
    return hidden;
}

function extractEmergencyMetadataFromOption(option) {
    if (!option?.value) return null;

    const name = option.dataset.emergencyName?.trim() || '';
    const code = option.dataset.emergencyCode?.trim() || '';
    if (name || code) {
        if (name === '[object Object]') return null;
        return { name, code };
    }
    return parseEmergencyDisplayValue(option.value);
}

function findEmergencyOtherTextInput(selectElement) {
    const titleWrap = selectElement.closest('.repeat-entry__title-select-wrap');
    if (titleWrap) {
        const fromWrap = titleWrap.querySelector('.other-text-input');
        if (fromWrap) return fromWrap;
    }
    const block = selectElement.closest('.form-item-block, .repeat-entry, .repeat-entry__title-select-wrap')
        || selectElement.parentElement;
    return block?.querySelector('.other-text-input') || null;
}

function syncSelection(selectElement) {
    if (!selectElement || selectElement.dataset.lookupListId !== 'emergency_operations') return;

    const hidden = findOrCreateEmergencyMetadataHiddenInput(selectElement);
    if (!hidden) return;

    if (!selectElement.value) {
        hidden.value = '';
        return;
    }

    if (selectElement.value === '__other__') {
        const otherInput = findEmergencyOtherTextInput(selectElement);
        const meta = parseEmergencyDisplayValue(otherInput?.value || '');
        hidden.value = meta && (meta.name || meta.code) && meta.name !== '__other__'
            ? JSON.stringify(meta)
            : '';
        return;
    }

    const option = selectElement.options[selectElement.selectedIndex];
    const meta = extractEmergencyMetadataFromOption(option);
    hidden.value = meta ? JSON.stringify(meta) : '';
}

function attach(selectElement) {
    if (selectElement.dataset.emergencyMetadataListenerAttached === 'true') return;
    selectElement.dataset.emergencyMetadataListenerAttached = 'true';
    selectElement.addEventListener('change', () => syncSelection(selectElement));
    const otherInput = findEmergencyOtherTextInput(selectElement);
    if (otherInput && otherInput.dataset.emergencyMetadataListenerAttached !== 'true') {
        otherInput.dataset.emergencyMetadataListenerAttached = 'true';
        otherInput.addEventListener('input', () => syncSelection(selectElement));
        otherInput.addEventListener('change', () => syncSelection(selectElement));
    }
}

function decorateOption(option, row, displayValue) {
    const name = scalarDisplayText(row?.name);
    const code = scalarDisplayText(row?.code);
    if (name) option.dataset.emergencyName = name;
    if (code) option.dataset.emergencyCode = code;
    if (!option.dataset.emergencyName && !option.dataset.emergencyCode && displayValue) {
        const parsed = parseEmergencyDisplayValue(scalarDisplayText(displayValue));
        if (parsed) {
            if (parsed.name) option.dataset.emergencyName = parsed.name;
            if (parsed.code) option.dataset.emergencyCode = parsed.code;
        }
    }
}

function buildRequestUrl({ selectElement, displayColumn, filters, origin }) {
    const url = new URL('/admin/plugins/emergency_operations/api/list-data', origin || window.location.origin);
    debugLog(MODULE, `Emergency Operations URL: ${url.toString()}`);

    const fieldIdForTrace = resolveCalculatedSelectFieldId(selectElement);
    traceEmOpsFilter(fieldIdForTrace, 'refresh start', {
        selectId: selectElement.id || null,
        displayColumn,
        listFilters: filters,
    });

    let pluginConfig = {};
    const rawCfgSelf = selectElement.dataset.pluginConfig;
    const rawCfgClosest = selectElement.closest('[data-plugin-config]')?.dataset.pluginConfig;
    const rawCfg = rawCfgSelf || rawCfgClosest || '{}';
    traceEmOpsFilter(fieldIdForTrace, 'data-plugin-config source', {
        fromSelect: Boolean(rawCfgSelf),
        fromAncestor: Boolean(!rawCfgSelf && rawCfgClosest),
        rawLength: rawCfg.length,
        rawPreview: rawCfg.length > 200 ? `${rawCfg.slice(0, 200)}…` : rawCfg,
    });
    try {
        pluginConfig = JSON.parse(rawCfg);
    } catch (parseErr) {
        traceEmOpsFilter(fieldIdForTrace, 'data-plugin-config parse FAILED', {
            error: parseErr && parseErr.message ? parseErr.message : String(parseErr),
            rawCfg,
        });
    }
    traceEmOpsFilter(fieldIdForTrace, 'parsed question_plugin_config', pluginConfig);

    let countryIso = null;
    const countrySource = pluginConfig.emops_country_source || 'assigned';
    if (countrySource === 'static' && pluginConfig.emops_static_country_iso) {
        countryIso = pluginConfig.emops_static_country_iso.trim().toUpperCase();
        debugLog(MODULE, `Using static country ISO from plugin config: ${countryIso}`);
    } else {
        countryIso = resolveAssignedCountryIso();
        if (countryIso) {
            debugLog(MODULE, `Found country ISO from assignment metadata: ${countryIso}`);
        }
    }

    if (countryIso) {
        url.searchParams.set('iso', countryIso);
    } else {
        debugLog(MODULE, 'No country ISO found, will return all operations');
    }

    const queryPayload = {};
    const timeframeMode = pluginConfig.emops_timeframe_mode || 'static';

    if (timeframeMode === 'assignment_period') {
        const periodStr = (window.metadataContext && window.metadataContext.assignment_period) || '';
        const yearMatch = periodStr.match(/\b(20\d{2})\b/);
        if (yearMatch) {
            const year = yearMatch[1];
            queryPayload.end_date__gte = `${year}-01-01`;
            traceEmOpsFilter(fieldIdForTrace, 'timeframe: assignment_period', {
                periodStr,
                effectiveEndDateGte: queryPayload.end_date__gte,
                note: 'Overrides emops_end_date_gt from form builder config',
                staticConfigEndDate: pluginConfig.emops_end_date_gt || null,
            });
            debugLog(MODULE, `Using assignment period year ${year} for timeframe filter`);
        } else {
            traceEmOpsFilter(fieldIdForTrace, 'timeframe: assignment_period (no year parsed)', {
                periodStr,
                metadataContext: window.metadataContext || null,
            });
            debugLog(MODULE, `Could not extract year from period "${periodStr}", no timeframe filter applied`);
        }
    } else {
        if (pluginConfig.emops_end_date_gt) {
            queryPayload.end_date__gte = pluginConfig.emops_end_date_gt;
        }
        traceEmOpsFilter(fieldIdForTrace, 'timeframe: static', {
            effectiveEndDateGte: queryPayload.end_date__gte || null,
        });
    }

    const extraFilters = [];
    const configTypes = pluginConfig.emops_operation_types;
    traceEmOpsFilter(fieldIdForTrace, 'emops_operation_types raw', {
        value: configTypes,
        typeof: typeof configTypes,
        isArray: Array.isArray(configTypes),
    });
    if (configTypes) {
        const types = Array.isArray(configTypes) ? configTypes : [configTypes];
        const hasAll = types.includes('All');
        if (!hasAll && types.length > 0) {
            extraFilters.push({ field: 'type', op: 'eq', value: types[0] });
            traceEmOpsFilter(fieldIdForTrace, 'type filter applied', {
                filter: extraFilters[extraFilters.length - 1],
                note: types.length > 1
                    ? `Only first of ${types.length} selected types is used (eq filter)`
                    : 'Single type selected',
            });
        } else {
            traceEmOpsFilter(fieldIdForTrace, 'type filter SKIPPED', {
                reason: hasAll ? 'includes All' : 'empty types array',
                types,
            });
        }
    } else {
        traceEmOpsFilter(fieldIdForTrace, 'type filter SKIPPED', {
            reason: 'emops_operation_types missing or falsy in plugin config',
        });
    }

    const showClosed = pluginConfig.emops_show_closed_operations;
    traceEmOpsFilter(fieldIdForTrace, 'emops_show_closed_operations', {
        value: showClosed,
        typeof: typeof showClosed,
        isArray: Array.isArray(showClosed),
    });
    const hideClosed = showClosed === false
        || showClosed === '0'
        || showClosed === 0
        || (Array.isArray(showClosed) && showClosed.length === 0);
    if (hideClosed) {
        extraFilters.push({ field: 'status', op: 'ne', value: 'Closed' });
        traceEmOpsFilter(fieldIdForTrace, 'status filter applied (hide closed)', extraFilters[extraFilters.length - 1]);
    } else {
        traceEmOpsFilter(fieldIdForTrace, 'status filter SKIPPED (showing closed ops)', { showClosed });
    }

    const allFilters = [...extraFilters, ...(filters || [])];
    traceEmOpsFilter(fieldIdForTrace, 'merged filters', {
        extraFilters,
        listFilters: filters,
        allFilters,
    });
    if (allFilters.length > 0) {
        queryPayload.filters = allFilters;
    }

    traceEmOpsFilter(fieldIdForTrace, 'query payload (pre-b64)', queryPayload);

    if (Object.keys(queryPayload).length > 0) {
        const queryB64 = btoa(unescape(encodeURIComponent(JSON.stringify(queryPayload))));
        url.searchParams.set('query_b64', queryB64);
    }

    traceEmOpsFilter(fieldIdForTrace, 'request URL', {
        iso: url.searchParams.get('iso'),
        hasQueryB64: url.searchParams.has('query_b64'),
        url: url.toString(),
    });

    return url;
}

function rowsFromResponse(json, { selectElement, fieldId } = {}) {
    const rows = json.data || [];
    const typeCounts = summarizeEmOpsTypes(rows);
    traceEmOpsFilter(fieldId, 'API response rows', {
        count: rows.length,
        typeCounts,
        sample: rows.slice(0, 5).map((r) => ({
            name: r.name,
            code: r.code,
            type: r.type,
            status: r.status,
            end_date: r.end_date,
        })),
    });
    const expectedTypeFilter = (() => {
        try {
            const raw = selectElement?.dataset.pluginConfig
                || selectElement?.closest('[data-plugin-config]')?.dataset.pluginConfig
                || '{}';
            const cfg = JSON.parse(raw);
            const types = cfg.emops_operation_types;
            const arr = Array.isArray(types) ? types : (types ? [types] : []);
            if (arr.length && !arr.includes('All')) return arr[0];
        } catch (_err) { /* no-op */ }
        return null;
    })();
    if (expectedTypeFilter) {
        const unexpected = rows.filter((r) => String(r.type || '') !== String(expectedTypeFilter));
        if (unexpected.length > 0) {
            traceEmOpsFilter(fieldId, 'UNEXPECTED types in response (filter may not be applied server-side)', {
                expectedType: expectedTypeFilter,
                unexpectedCount: unexpected.length,
                unexpectedTypes: summarizeEmOpsTypes(unexpected),
                examples: unexpected.slice(0, 3).map((r) => ({ name: r.name, type: r.type, status: r.status })),
            });
        } else {
            traceEmOpsFilter(fieldId, 'all rows match expected type filter', { expectedType: expectedTypeFilter });
        }
    }
    return rows;
}

export const calculatedListAdapter = {
    id: 'emergency_operations',
    deferInitialRefresh: true,
    buildRequestUrl,
    rowsFromResponse,
    formatRow(row) {
        return formatEmergencyOperationLabel(row);
    },
    decorateOption,
    syncSelection,
    attach,
};
