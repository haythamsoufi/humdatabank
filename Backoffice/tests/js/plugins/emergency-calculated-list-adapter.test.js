/**
 * Emergency operations calculated-list adapter: appeal metadata written
 * beside the select. The core runtime only calls syncSelection.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
    debugLog: vi.fn(),
    debugWarn: vi.fn(),
    debugError: vi.fn(),
}));

vi.mock('../../../app/static/js/forms/modules/field-management.js', () => ({
    getFieldValue: vi.fn((id) => document.getElementById(`field-${id}`)?.value ?? null),
    getCurrentFieldValue: vi.fn((id) => document.getElementById(`field-${id}`)?.value ?? null),
}));

vi.mock('../../../app/static/js/forms/modules/question-other-option.js', () => ({
    appendOtherOptionToSelect: vi.fn(),
    appendOtherOptionToMultiDropdown: vi.fn(),
    restoreOtherSelectionForCalculatedList: vi.fn(),
}));

class IdleIntersectionObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
}

async function loadAdapter() {
    vi.resetModules();
    const adapterMod = await import('../../../plugins/emergency_operations/static/js/calculated_list_adapter.js');
    return adapterMod.calculatedListAdapter;
}

function hiddenInputs(root = document.querySelector('form') || document) {
    return [...root.querySelectorAll('input[type="hidden"]')];
}

function createSelect({
    id = 'field-42',
    name = 'field_value[42]',
    lookupListId = 'emergency_operations',
    fieldItemId,
    inForm = true,
} = {}) {
    const select = document.createElement('select');
    select.id = id;
    select.name = name;
    if (lookupListId != null) select.dataset.lookupListId = lookupListId;
    if (fieldItemId != null) select.dataset.fieldItemId = String(fieldItemId);

    const empty = document.createElement('option');
    empty.value = '';
    select.appendChild(empty);

    if (inForm) {
        const form = document.createElement('form');
        form.appendChild(select);
        document.body.appendChild(form);
    } else {
        document.body.appendChild(select);
    }
    return select;
}

function addOption(select, { value, emergencyName, emergencyCode, selected = false } = {}) {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = value;
    if (emergencyName != null) option.dataset.emergencyName = emergencyName;
    if (emergencyCode != null) option.dataset.emergencyCode = emergencyCode;
    select.appendChild(option);
    if (selected) select.value = value;
    return option;
}

describe('emergency calculated list adapter', () => {
    beforeEach(() => {
        document.body.innerHTML = '';
        vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network disabled'))));
        vi.stubGlobal('IntersectionObserver', IdleIntersectionObserver);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        document.body.innerHTML = '';
    });

    it('does not write metadata for a different lookup', async () => {
        const adapter = await loadAdapter();
        const select = createSelect({ lookupListId: 'reporting_currency' });
        addOption(select, { value: 'Flood (MDRXX001)', selected: true });

        adapter.syncSelection(select);

        expect(hiddenInputs()).toHaveLength(0);
    });

    it('creates field_disagg_metadata from the selected option', async () => {
        const adapter = await loadAdapter();
        const select = createSelect({ id: 'field-42', name: 'field_value[42]' });
        addOption(select, {
            value: 'Cyclone (MDRPH001)',
            emergencyName: 'Cyclone',
            emergencyCode: 'MDRPH001',
            selected: true,
        });

        adapter.syncSelection(select);

        const hidden = hiddenInputs()[0];
        expect(hidden.name).toBe('field_disagg_metadata[42]');
        expect(JSON.parse(hidden.value)).toEqual({ name: 'Cyclone', code: 'MDRPH001' });
    });

    it('parses Name (CODE) when the option has no appeal datasets', async () => {
        const adapter = await loadAdapter();
        const select = createSelect({ id: 'field-13' });
        addOption(select, { value: 'Flood Response Operation (MDRXX001)', selected: true });

        adapter.syncSelection(select);

        expect(JSON.parse(hiddenInputs()[0].value)).toEqual({
            name: 'Flood Response Operation',
            code: 'MDRXX001',
        });
    });

    it('parses Other please-specify text including the appeal code', async () => {
        const adapter = await loadAdapter();
        const select = createSelect({
            id: 'repeat-title-select',
            name: 'repeat_5_1_field_0',
        });
        addOption(select, { value: '__other__', selected: true });
        const wrap = document.createElement('div');
        wrap.className = 'repeat-entry__title-select-wrap';
        select.parentElement.appendChild(wrap);
        wrap.appendChild(select);
        const other = document.createElement('input');
        other.className = 'other-text-input';
        other.value = 'Bangladesh Population Movement (MDRBD018)';
        wrap.appendChild(other);

        adapter.syncSelection(select);

        expect(JSON.parse(hiddenInputs()[0].value)).toEqual({
            name: 'Bangladesh Population Movement',
            code: 'MDRBD018',
        });
    });

    it('attaches through the core runtime and defers the first fetch', async () => {
        vi.resetModules();
        window.existingData = {};
        document.body.innerHTML = `
            <form>
                <select id="field-30"
                    name="field_value[30]"
                    data-options-source="calculated"
                    data-lookup-list-id="emergency_operations"
                    data-display-column="name"
                    data-list-filters="[]">
                    <option value=""></option>
                    <option value="Flood (MDRXX001)">Flood (MDRXX001)</option>
                </select>
            </form>`;

        const runtime = await import('../../../app/static/js/forms/modules/calculated-lists-runtime.js');
        const { calculatedListAdapter } = await import('../../../plugins/emergency_operations/static/js/calculated_list_adapter.js');
        runtime.registerCalculatedListAdapter(calculatedListAdapter);
        runtime.initCalculatedLists();

        const select = document.getElementById('field-30');
        expect(select.dataset.emergencyMetadataListenerAttached).toBe('true');
        expect(fetch).not.toHaveBeenCalled();

        select.value = 'Flood (MDRXX001)';
        select.dispatchEvent(new Event('change', { bubbles: true }));

        expect(JSON.parse(hiddenInputs()[0].value)).toEqual({
            name: 'Flood',
            code: 'MDRXX001',
        });
    });
});
