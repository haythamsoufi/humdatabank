/**
 * Apply disaggregation JSON payloads to entry-form DOM inputs.
 * Shared by UPR Excel import and AI opinion apply flows.
 */

function dispatchInputEvents(el) {
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
}

function disaggInputCandidates(base, mode, categoryKey) {
    const candidates = [];
    if (mode === 'sex_age') {
        candidates.push(`${base}_sexage_${categoryKey}`);
    } else if (mode === 'sex') {
        candidates.push(`${base}_sex_${categoryKey}`);
    } else if (mode === 'age') {
        candidates.push(`${base}_age_${categoryKey}`);
    } else if (mode === 'total' && categoryKey === 'direct') {
        candidates.push(`${base}_total_value`);
    }
    candidates.push(`${base}_${mode}_${categoryKey}`);
    candidates.push(`${base}_${categoryKey}`);
    return candidates;
}

function applyDisaggCategoryValue(block, base, mode, categoryKey, rawVal, trySetByName) {
    if (rawVal === null || rawVal === undefined || typeof rawVal === 'object') {
        return false;
    }
    for (const name of disaggInputCandidates(base, mode, categoryKey)) {
        if (trySetByName(name, rawVal)) {
            return true;
        }
    }
    const suffix = `_${categoryKey}`;
    const inputs = block.querySelectorAll(
        `input[name^="${base}_"][name*="${suffix}"]:not([disabled])`
    );
    for (const el of inputs) {
        if (el.type !== 'number' && el.dataset?.numeric !== 'true') {
            continue;
        }
        if (!String(el.name).endsWith(suffix) && !String(el.name).includes(`${suffix}_`)) {
            continue;
        }
        el.value = String(rawVal ?? '');
        dispatchInputEvents(el);
        return true;
    }
    return false;
}

function applyDisaggBreakdown(block, base, mode, breakdown, trySetByName) {
    let appliedAny = false;
    for (const [key, val] of Object.entries(breakdown || {})) {
        appliedAny = applyDisaggCategoryValue(block, base, mode, key, val, trySetByName) || appliedAny;
    }
    return appliedAny;
}

/**
 * Resolve the "{prefix}_{id}" field-name base for a form-item block.
 *
 * Reads the block's own data-* attributes rather than guessing from a sample
 * input name. This matters because dynamic-indicator ids are not always
 * numeric: a newly-added (not-yet-persisted) dynamic indicator is rendered
 * with a temporary id like "pending_1691700000000_ab12cd" (see
 * dynamic-indicators.js / forms_api.py render-pending), which a `\d+`-based
 * regex on a sample input name would fail to match.
 */
function resolveFieldBase(block) {
    const assignmentId = block.getAttribute('data-assignment-id');
    if (assignmentId) {
        return `dynamic_${assignmentId}`;
    }
    const itemId = block.getAttribute('data-item-id');
    if (itemId) {
        const itemType = String(block.getAttribute('data-item-type') || '').toLowerCase();
        const prefix = itemType === 'question' ? 'question' : 'indicator';
        return `${prefix}_${itemId}`;
    }
    // Fallback for blocks without the expected data-* attributes.
    const sampleNamedInput = block.querySelector('input[name], textarea[name], select[name]');
    const sampleName = sampleNamedInput ? String(sampleNamedInput.getAttribute('name') || '') : '';
    const m = sampleName.match(/^(indicator|dynamic|question)_(\d+)_/);
    return m ? `${m[1]}_${m[2]}` : null;
}

/**
 * Apply disagg_data { mode, values } to a form-item block.
 * @returns {boolean} true when at least one input was updated
 */
export function applyDisaggToBlock(block, disaggData) {
    if (!block || !disaggData || typeof disaggData !== 'object') return false;

    if (!disaggData.mode && !disaggData.values) {
        const itemId = String(block.getAttribute('data-item-id') || '').trim();
        const hidden = itemId
            ? block.querySelector(`input[type="hidden"][name="field_value[${itemId}]"]`)
            : null;
        if (hidden) {
            hidden.value = JSON.stringify(disaggData);
            dispatchInputEvents(hidden);
            return true;
        }
    }

    const base = resolveFieldBase(block);
    if (!base) return false;

    const mode = String(disaggData.mode || '').trim();
    const values = (disaggData.values && typeof disaggData.values === 'object') ? disaggData.values : null;
    if (!mode || !values) return false;

    const modeRadio = block.querySelector(
        `input[type="radio"][name="${base}_reporting_mode"][value="${mode}"]:not([disabled])`
    );
    if (modeRadio) {
        modeRadio.checked = true;
        dispatchInputEvents(modeRadio);
    }

    let appliedAny = false;
    const trySetByName = (name, val) => {
        const el = block.querySelector(`[name="${name}"]:not([disabled])`);
        if (!el) return false;
        el.value = String(val ?? '');
        dispatchInputEvents(el);
        return true;
    };

    if (Object.prototype.hasOwnProperty.call(values, 'total')) {
        appliedAny = trySetByName(`${base}_total_value`, values.total) || appliedAny;
    }
    if (Object.prototype.hasOwnProperty.call(values, 'indirect')) {
        appliedAny = trySetByName(`${base}_indirect_reach`, values.indirect) || appliedAny;
    }

    if (values.direct && typeof values.direct === 'object' && !Array.isArray(values.direct)) {
        appliedAny = applyDisaggBreakdown(block, base, mode, values.direct, trySetByName) || appliedAny;
    } else if (Object.prototype.hasOwnProperty.call(values, 'direct')) {
        appliedAny = applyDisaggCategoryValue(block, base, mode, 'direct', values.direct, trySetByName) || appliedAny;
    }

    for (const [key, rawVal] of Object.entries(values)) {
        if (key === 'total' || key === 'indirect' || key === 'direct') continue;
        if (typeof rawVal === 'object') continue;
        appliedAny = applyDisaggCategoryValue(block, base, mode, key, rawVal, trySetByName) || appliedAny;
    }

    return appliedAny;
}

/**
 * Apply yes/no checkbox pair from import payload (Excel Applicable -> yes).
 * @returns {boolean} true when a yes/no control was updated
 */
export function applyYesNoToBlock(block, value) {
    const yesNo = String(value ?? '').trim().toLowerCase();
    if (yesNo !== 'yes' && yesNo !== 'no') return false;

    const yesNoBoxes = Array.from(
        block.querySelectorAll('input[type="checkbox"][name*="_standard_value"]:not([disabled])')
    ).filter((cb) => {
        const option = String(cb.value || '').trim().toLowerCase();
        return option === 'yes' || option === 'no';
    });

    if (yesNoBoxes.length >= 2) {
        yesNoBoxes.forEach((cb) => {
            cb.checked = String(cb.value || '').trim().toLowerCase() === yesNo;
            dispatchInputEvents(cb);
        });
        return true;
    }

    const fallback = block.querySelector(
        `input[type="checkbox"][value="${yesNo}"][name*="_standard_value"]:not([disabled])`
    ) || block.querySelector(
        `input[type="checkbox"][value="${yesNo}"][name^="field_value"]:not([disabled])`
    );
    if (!fallback) return false;
    fallback.checked = true;
    dispatchInputEvents(fallback);
    return true;
}
