/**
 * Apply a UPR Country Reporting Excel import payload to the entry form DOM
 * without persisting — the user must click Save to write to the database.
 */

import { addPendingDynamicIndicatorForImport } from './dynamic-indicators.js';
import {
    addRepeatEntry,
    getEffectiveRepeatEntryMax,
    setSelectValueWithFallback,
    waitForCalculatedSelectOptions,
} from './repeat-sections.js';
import { applyDisaggToBlock, applyYesNoToBlock } from './disagg-dom-apply.js';
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

/**
 * @returns {boolean} true when a matching input was found and updated
 */
function applyFieldPayloadToBlock(block, fieldData) {
    if (!block || !fieldData) return false;

    if (fieldData.data_not_available) {
        const dna = block.querySelector('input[name*="_data_not_available"]');
        if (!dna) return false;
        if (!dna.checked) {
            dna.checked = true;
            dispatchInputEvents(dna);
        }
        return true;
    }

    if (fieldData.disagg_data) {
        return applyDisaggToBlock(block, fieldData.disagg_data);
    }

    const value = fieldData.value;
    if (value === 'yes' || value === 'no') {
        return applyYesNoToBlock(block, value);
    }

    const input = block.querySelector('input[name*="_standard_value"], textarea[name*="_standard_value"], select[name*="_standard_value"]')
        || block.querySelector(`input[name="field_value[${block.dataset.itemId}]"], textarea[name="field_value[${block.dataset.itemId}]"]`);
    if (!input) return false;

    if (input.type === 'checkbox') {
        input.checked = value === '1' || value === 1 || value === 'true' || value === true;
    } else {
        input.value = value ?? '';
    }
    dispatchInputEvents(input);
    return true;
}

function applyStaticFields(fields) {
    let count = 0;
    const warnings = [];
    for (const [itemId, fieldData] of Object.entries(fields || {})) {
        const block = findStaticFieldBlock(itemId);
        if (!block) {
            debugWarn(MODULE, `Static field block not found for item ${itemId}`);
            warnings.push(`Could not find field ${itemId} on the form — its imported value was not applied.`);
            continue;
        }
        if (!applyFieldPayloadToBlock(block, fieldData)) {
            debugWarn(MODULE, `Failed to apply imported value for field ${itemId}`);
            warnings.push(`Could not apply the imported value for field ${itemId} — please check it manually.`);
            continue;
        }
        count += 1;
    }
    return { count, warnings };
}

function applyMatrices(matrices) {
    let count = 0;
    const warnings = [];
    const entries = Object.entries(matrices || {});
    if (!entries.length) return { count, warnings };

    const handler = window.matrixHandler;
    if (!handler || typeof handler.setMatrixData !== 'function') {
        debugWarn(MODULE, 'Matrix handler not available');
        warnings.push('Could not apply imported matrix data — the matrix control is not available on this page.');
        return { count, warnings };
    }

    for (const [itemId, data] of entries) {
        const applied = handler.setMatrixData(String(itemId), data);
        if (!applied) {
            debugWarn(MODULE, `Matrix ${itemId} not found on the page; imported data not applied`);
            warnings.push(`Could not apply imported data for matrix ${itemId} — please check it manually.`);
            continue;
        }
        count += 1;
    }
    return { count, warnings };
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

/**
 * @returns {Promise<boolean>} true when the choice value was applied
 */
async function applyRepeatSlotChoice(repeatEntry, sectionId, slotNum, slot) {
    const choiceItemId = slot.choice_item_id;
    if (!choiceItemId || !repeatEntry) return false;

    const field = repeatEntry.querySelector(`[data-item-id="${choiceItemId}"]`);
    if (!field) {
        debugWarn(MODULE, `Emergency choice field ${choiceItemId} not found in repeat entry ${slotNum}`);
        return false;
    }

    const displayValue = slot.display_value || '';
    const select = field.querySelector('select');
    if (select) {
        // Calculated-list selects (e.g. the emergency-operation/MDR picker)
        // populate their <option>s asynchronously after being created, so a
        // freshly-added repeat entry's select is very likely empty at this
        // point — setting .value synchronously would silently no-op.
        if (select.dataset.optionsSource === 'calculated' && select.options.length <= 1) {
            await waitForCalculatedSelectOptions(select);
        }
        setSelectValueWithFallback(select, displayValue);
        dispatchInputEvents(select);
        return !displayValue || select.value !== '';
    }

    const textInput = field.querySelector('input[type="text"], input:not([type])');
    if (textInput) {
        textInput.value = displayValue;
        dispatchInputEvents(textInput);
        return true;
    }
    return false;
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
            const applied = await applyRepeatSlotChoice(repeatEntry, sectionId, slot.slot_num, slot);
            if (applied) {
                count += 1;
            } else if (slot.display_value) {
                warnings.push(
                    `Could not select "${describeEmergencySlot(slot)}" for emergency operation slot ${slot.slot_num} — please select it manually.`
                );
            }
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
            warnings.push(`Could not find indicator ${bankId} on the form — its imported value was not applied.`);
            continue;
        }

        const applied = applyFieldPayloadToBlock(block, {
            value: entry.value != null ? String(entry.value) : undefined,
            data_not_available: entry.data_not_available,
            disagg_data: entry.disagg_data,
        });
        if (!applied) {
            debugWarn(MODULE, `Failed to apply imported value for dynamic indicator ${bankId}`);
            warnings.push(`Could not apply the imported value for indicator ${bankId} — please check it manually.`);
            continue;
        }
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

    const staticResult = applyStaticFields(payload.fields);
    warnings.push(...(staticResult.warnings || []));
    const matrixResult = applyMatrices(payload.matrices);
    warnings.push(...(matrixResult.warnings || []));

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

    const staticCount = staticResult.count || 0;
    const matrixCount = matrixResult.count || 0;
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
