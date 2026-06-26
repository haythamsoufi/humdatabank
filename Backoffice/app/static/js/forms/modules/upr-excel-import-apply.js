/**
 * Apply a UPR Country Reporting Excel import payload to the entry form DOM
 * without persisting — the user must click Save to write to the database.
 */

import { addPendingDynamicIndicatorForImport } from './dynamic-indicators.js';
import { addRepeatEntry, getEffectiveRepeatEntryMax } from './repeat-sections.js';
import { debugLog, debugWarn } from './debug.js';

const MODULE = 'upr-excel-import';

function dispatchInputEvents(el) {
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
}

function findStaticFieldBlock(itemId) {
    const blocks = document.querySelectorAll(`.form-item-block[data-item-id="${itemId}"]`);
    return Array.from(blocks).find((block) => !block.closest('.repeat-entry'));
}

function applyDisaggToBlock(block, disaggData) {
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

    const sampleNamedInput = block.querySelector('input[name], textarea[name], select[name]');
    const sampleName = sampleNamedInput ? String(sampleNamedInput.getAttribute('name') || '') : '';
    const m = sampleName.match(/^(indicator|dynamic|question)_(\d+)_/);
    if (!m) return false;

    const base = `${m[1]}_${m[2]}`;
    const mode = String(disaggData.mode || '').trim();
    const values = (disaggData.values && typeof disaggData.values === 'object') ? disaggData.values : null;
    if (!mode || !values) return false;

    const modeRadio = block.querySelector(`input[type="radio"][name="${base}_reporting_mode"][value="${mode}"]:not([disabled])`);
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

    for (const [key, rawVal] of Object.entries(values)) {
        if (key === 'total' || key === 'indirect') continue;
        appliedAny = trySetByName(`${base}_${mode}_${key}`, rawVal) || appliedAny;
        appliedAny = trySetByName(`${base}_${key}`, rawVal) || appliedAny;
    }

    return appliedAny;
}

function applyFieldPayloadToBlock(block, fieldData) {
    if (!block || !fieldData) return;

    if (fieldData.data_not_available) {
        const dna = block.querySelector('input[name*="_data_not_available"]');
        if (dna && !dna.checked) {
            dna.checked = true;
            dispatchInputEvents(dna);
        }
        return;
    }

    if (fieldData.disagg_data) {
        applyDisaggToBlock(block, fieldData.disagg_data);
        return;
    }

    const value = fieldData.value;
    if (value === 'yes' || value === 'no') {
        const checkbox = block.querySelector(
            `input[type="checkbox"][value="${value}"][name*="_standard_value"]`
        ) || block.querySelector(`input[type="checkbox"][value="${value}"][name^="field_value"]`);
        if (checkbox && window.handleYesNoCheckbox) {
            window.handleYesNoCheckbox(checkbox, checkbox.name);
        } else if (checkbox) {
            checkbox.checked = true;
            dispatchInputEvents(checkbox);
        }
        return;
    }

    const input = block.querySelector('input[name*="_standard_value"], textarea[name*="_standard_value"], select[name*="_standard_value"]')
        || block.querySelector(`input[name="field_value[${block.dataset.itemId}]"], textarea[name="field_value[${block.dataset.itemId}]"]`);
    if (input) {
        if (input.type === 'checkbox') {
            input.checked = value === '1' || value === 1 || value === 'true' || value === true;
        } else {
            input.value = value ?? '';
        }
        dispatchInputEvents(input);
    }
}

function applyStaticFields(fields) {
    let count = 0;
    for (const [itemId, fieldData] of Object.entries(fields || {})) {
        const block = findStaticFieldBlock(itemId);
        if (!block) {
            debugWarn(MODULE, `Static field block not found for item ${itemId}`);
            continue;
        }
        applyFieldPayloadToBlock(block, fieldData);
        count += 1;
    }
    return count;
}

function applyMatrices(matrices) {
    let count = 0;
    const handler = window.matrixHandler;
    if (!handler || typeof handler.setMatrixData !== 'function') {
        debugWarn(MODULE, 'Matrix handler not available');
        return 0;
    }

    for (const [itemId, data] of Object.entries(matrices || {})) {
        handler.setMatrixData(String(itemId), data);
        count += 1;
    }
    return count;
}

async function ensureRepeatEntryCount(sectionId, targetCount) {
    const repeatContainer = document.getElementById(`repeat-entries-${sectionId}`);
    if (!repeatContainer) {
        debugWarn(MODULE, `Repeat container not found for section ${sectionId}`);
        return;
    }

    const maxEntries = getEffectiveRepeatEntryMax(sectionId);
    const cappedTarget = maxEntries != null ? Math.min(targetCount, maxEntries) : targetCount;

    let current = repeatContainer.querySelectorAll('.repeat-entry').length;
    while (current < cappedTarget) {
        const added = addRepeatEntry(sectionId, { silent: true });
        if (!added) break;
        await new Promise((resolve) => requestAnimationFrame(resolve));
        current = repeatContainer.querySelectorAll('.repeat-entry').length;
    }
}

function describeEmergencySlot(slot) {
    return slot.display_value
        || slot.appeal_name
        || slot.mdr_code
        || `Emergency ${slot.slot_num}`;
}

function partitionRepeatSlotsByLimit(sectionId, slots) {
    const maxEntries = getEffectiveRepeatEntryMax(sectionId);
    const sorted = [...slots].sort((a, b) => (Number(a.slot_num) || 0) - (Number(b.slot_num) || 0));
    if (maxEntries == null) {
        return { importable: sorted, skipped: [], maxEntries: null };
    }
    const importable = [];
    const skipped = [];
    for (const slot of sorted) {
        const slotNum = Number(slot.slot_num) || 0;
        if (slotNum > maxEntries) {
            skipped.push(slot);
        } else {
            importable.push(slot);
        }
    }
    return { importable, skipped, maxEntries };
}

function buildRepeatLimitWarning(sectionId, skippedSlots, maxEntries) {
    if (!skippedSlots.length || maxEntries == null) return null;
    const names = skippedSlots.map(describeEmergencySlot).join(', ');
    return `Could not import ${skippedSlots.length} emergency operation(s) — this section allows at most ${maxEntries} entries: ${names}.`;
}

function findRepeatEntry(sectionId, slotNum) {
    return document.getElementById(`repeat-entry-${sectionId}-${slotNum}`)
        || document.querySelector(`.repeat-entry[data-repeat-instance="${slotNum}"]`);
}

function applyRepeatSlotChoice(repeatEntry, sectionId, slotNum, slot) {
    const choiceItemId = slot.choice_item_id;
    if (!choiceItemId || !repeatEntry) return;

    const field = repeatEntry.querySelector(`[data-item-id="${choiceItemId}"]`);
    if (!field) {
        debugWarn(MODULE, `Emergency choice field ${choiceItemId} not found in repeat entry ${slotNum}`);
        return;
    }

    const displayValue = slot.display_value || '';
    const select = field.querySelector('select');
    if (select) {
        select.value = displayValue;
        if (!select.value && displayValue) {
            const options = Array.from(select.options);
            const match = options.find((opt) => opt.text.trim() === displayValue || opt.value === displayValue);
            if (match) select.value = match.value;
        }
        dispatchInputEvents(select);
        return;
    }

    const textInput = field.querySelector('input[type="text"], input:not([type])');
    if (textInput) {
        textInput.value = displayValue;
        dispatchInputEvents(textInput);
    }
}

async function applyRepeatSlots(repeatSlots) {
    if (!repeatSlots?.length) return { count: 0, warnings: [] };

    const bySection = new Map();
    for (const slot of repeatSlots) {
        const sectionId = slot.repeat_section_id;
        if (!sectionId) continue;
        if (!bySection.has(sectionId)) bySection.set(sectionId, []);
        bySection.get(sectionId).push(slot);
    }

    let count = 0;
    const warnings = [];
    for (const [sectionId, slots] of bySection.entries()) {
        const { importable, skipped, maxEntries } = partitionRepeatSlotsByLimit(sectionId, slots);
        const limitWarning = buildRepeatLimitWarning(sectionId, skipped, maxEntries);
        if (limitWarning) warnings.push(limitWarning);

        if (!importable.length) continue;

        const maxSlot = Math.max(...importable.map((s) => Number(s.slot_num) || 0));
        await ensureRepeatEntryCount(sectionId, maxSlot);

        for (const slot of importable) {
            const repeatEntry = findRepeatEntry(sectionId, slot.slot_num);
            applyRepeatSlotChoice(repeatEntry, sectionId, slot.slot_num, slot);
            count += 1;
        }
    }
    return { count, warnings };
}

function findDynamicIndicatorBlock(sectionId, entry) {
    const existingId = entry.existing_assignment_id;
    if (existingId) {
        const byAssignment = document.querySelector(
            `.form-item-block[data-assignment-id="${existingId}"]`
        );
        if (byAssignment) return byAssignment;
    }

    const repeatInstance = entry.repeat_instance_number;
    const containerId = repeatInstance != null
        ? `section-container-${sectionId}-ri-${repeatInstance}`
        : `section-container-${sectionId}`;
    const container = document.getElementById(containerId)
        || document.getElementById(`section-container-${sectionId}`);
    if (!container) return null;

    const proposeBtn = container.querySelector(
        `.propose-changes-btn[data-indicator-id="${entry.indicator_bank_id}"]`
    );
    return proposeBtn?.closest('.form-item-block') || null;
}

async function applyDynamicIndicators(dynamicEntries, repeatEntryMax = null) {
    if (!dynamicEntries?.length) return { count: 0, warnings: [] };

    let count = 0;
    const warnings = [];
    const skippedInstances = new Set();

    for (const entry of dynamicEntries) {
        const sectionId = entry.section_id;
        const repeatInstance = entry.repeat_instance_number ?? null;
        if (repeatInstance != null && repeatEntryMax != null && Number(repeatInstance) > repeatEntryMax) {
            skippedInstances.add(Number(repeatInstance));
            continue;
        }

        const bankId = entry.indicator_bank_id;

        let block = findDynamicIndicatorBlock(sectionId, entry);
        if (!block) {
            try {
                block = await addPendingDynamicIndicatorForImport(sectionId, bankId, repeatInstance);
            } catch (err) {
                debugWarn(MODULE, `Failed to add dynamic indicator ${bankId}:`, err);
                continue;
            }
        }

        if (!block) {
            block = findDynamicIndicatorBlock(sectionId, entry);
        }
        if (!block) {
            debugWarn(MODULE, `Dynamic indicator block not found for bank ${bankId}`);
            continue;
        }

        applyFieldPayloadToBlock(block, {
            value: entry.value != null ? String(entry.value) : undefined,
            data_not_available: entry.data_not_available,
            disagg_data: entry.disagg_data,
        });
        count += 1;
    }

    if (skippedInstances.size > 0 && repeatEntryMax != null) {
        const slots = [...skippedInstances].sort((a, b) => a - b).join(', ');
        warnings.push(
            `Skipped emergency indicator data for slot(s) ${slots} — this section allows at most ${repeatEntryMax} entries.`
        );
    }

    return { count, warnings };
}

/**
 * Apply a server-returned UPR Excel import payload to the form DOM.
 * @returns {Promise<{applied: number}>}
 */
export async function applyUprExcelImportPayload(payload) {
    if (!payload || typeof payload !== 'object') {
        throw new Error('Invalid import payload');
    }

    debugLog(MODULE, 'Applying UPR Excel import payload', payload);

    const warnings = [];

    const staticCount = applyStaticFields(payload.fields);
    const matrixCount = applyMatrices(payload.matrices);

    const repeatSectionId = (payload.repeat_slots || []).find((s) => s.repeat_section_id)?.repeat_section_id
        || null;
    const repeatEntryMax = repeatSectionId ? getEffectiveRepeatEntryMax(repeatSectionId) : null;

    const repeatResult = await applyRepeatSlots(payload.repeat_slots);
    warnings.push(...(repeatResult.warnings || []));

    const dynamicResult = await applyDynamicIndicators(
        payload.dynamic_indicators,
        repeatEntryMax
    );
    warnings.push(...(dynamicResult.warnings || []));

    const repeatCount = repeatResult.count || 0;
    const dynamicCount = dynamicResult.count || 0;
    const applied = staticCount + matrixCount + repeatCount + dynamicCount;
    debugLog(MODULE, `Applied ${applied} items (static=${staticCount}, matrix=${matrixCount}, repeat=${repeatCount}, dynamic=${dynamicCount})`);

    if (window.reinitializeDisaggregationCalculator) {
        window.reinitializeDisaggregationCalculator();
    }
    if (typeof window.requestRelevanceRecheck === 'function') {
        window.requestRelevanceRecheck('upr-excel-import');
    } else if (typeof window.checkAllRelevanceConditions === 'function') {
        window.checkAllRelevanceConditions({ reason: 'upr-excel-import' });
    }

    return { applied, warnings };
}
