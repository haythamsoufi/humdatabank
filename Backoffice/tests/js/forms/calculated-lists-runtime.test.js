/**
 * Exported / window-syncable behaviour of calculated-lists-runtime.js.
 *
 * Covers syncEmergencyOperationMetadata (hidden input name, placement, JSON)
 * and the parts of initCalculatedLists that run without a successful network
 * fetch: readiness retry, listener attach, and window helper assignment.
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

async function loadRuntime() {
    vi.resetModules();
    return import('../../../app/static/js/forms/modules/calculated-lists-runtime.js');
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

function resetWindowState() {
    document.body.innerHTML = '';
    delete window.existingData;
    delete window.metadataContext;
    delete window.countryInfo;
    delete window.CALCULATED_LIST_LABELS;
    delete window.getApiFetch;
    delete window.getFetch;
    delete window.responseAsResult;
    delete window.refreshCalculatedSelect;
    delete window.refreshCalculatedMultiSelect;
    delete window.preserveCalculatedSelectStaleValue;
    delete window.syncEmergencyOperationMetadata;
}

describe('calculated-lists-runtime', () => {
    beforeEach(() => {
        resetWindowState();
        vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network disabled'))));
        vi.stubGlobal('IntersectionObserver', IdleIntersectionObserver);
        delete window.requestIdleCallback;
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.unstubAllGlobals();
        resetWindowState();
    });

    describe('syncEmergencyOperationMetadata', () => {
        it('is a no-op unless lookupListId is emergency_operations', async () => {
            const { syncEmergencyOperationMetadata } = await loadRuntime();
            const select = createSelect({ lookupListId: 'reporting_currency' });
            addOption(select, { value: 'Flood (MDRXX001)', selected: true });

            syncEmergencyOperationMetadata(select);

            expect(hiddenInputs()).toHaveLength(0);
        });

        it('is a no-op when the select is not inside a form', async () => {
            const { syncEmergencyOperationMetadata } = await loadRuntime();
            const select = createSelect({ inForm: false });
            addOption(select, { value: 'Flood (MDRXX001)', selected: true });

            syncEmergencyOperationMetadata(select);

            expect(document.querySelector('input[type="hidden"]')).toBeNull();
        });

        it('is a no-op when the hidden input name cannot be resolved', async () => {
            const { syncEmergencyOperationMetadata } = await loadRuntime();
            const select = createSelect({ id: 'emops-orphan', name: 'not_a_field_pattern' });
            addOption(select, { value: 'Flood (MDRXX001)', selected: true });

            syncEmergencyOperationMetadata(select);

            expect(hiddenInputs()).toHaveLength(0);
        });

        it('creates field_disagg_metadata[id] from select#field-N and appends it to the form', async () => {
            const { syncEmergencyOperationMetadata } = await loadRuntime();
            const select = createSelect({ id: 'field-42', name: 'field_value[42]' });
            addOption(select, {
                value: 'Cyclone (MDRPH001)',
                emergencyName: 'Cyclone',
                emergencyCode: 'MDRPH001',
                selected: true,
            });

            syncEmergencyOperationMetadata(select);

            const hidden = hiddenInputs()[0];
            expect(hidden).toBeTruthy();
            expect(hidden.name).toBe('field_disagg_metadata[42]');
            expect(hidden.parentElement.tagName).toBe('FORM');
            expect(JSON.parse(hidden.value)).toEqual({ name: 'Cyclone', code: 'MDRPH001' });
        });

        it('uses data-field-item-id for the hidden input name when present', async () => {
            const { syncEmergencyOperationMetadata } = await loadRuntime();
            const select = createSelect({
                id: 'field-ignored',
                name: 'field_value[ignored]',
                fieldItemId: '99',
            });
            addOption(select, {
                value: 'Drought (MDRKE002)',
                emergencyName: 'Drought',
                emergencyCode: 'MDRKE002',
                selected: true,
            });

            syncEmergencyOperationMetadata(select);

            expect(hiddenInputs()[0].name).toBe('field_disagg_metadata[99]');
        });

        it('derives repeat_*_emergency_metadata from a trailing numeric suffix', async () => {
            const { syncEmergencyOperationMetadata } = await loadRuntime();
            const select = createSelect({
                id: 'repeat-title-select',
                name: 'repeat_5_1_field_3',
            });
            addOption(select, {
                value: 'Flood (MDRXX001)',
                emergencyName: 'Flood',
                emergencyCode: 'MDRXX001',
                selected: true,
            });

            syncEmergencyOperationMetadata(select);

            const hidden = hiddenInputs()[0];
            expect(hidden.name).toBe('repeat_5_1_field_emergency_metadata');
            expect(hidden.parentElement).toBe(select.form);
        });

        it('reuses an existing hidden input with the same name instead of creating another', async () => {
            const { syncEmergencyOperationMetadata } = await loadRuntime();
            const select = createSelect({ id: 'field-7' });
            const existing = document.createElement('input');
            existing.type = 'hidden';
            existing.name = 'field_disagg_metadata[7]';
            existing.value = '{"name":"old","code":"OLD"}';
            select.form.appendChild(existing);
            addOption(select, {
                value: 'Flood (MDRXX001)',
                emergencyName: 'Flood',
                emergencyCode: 'MDRXX001',
                selected: true,
            });

            syncEmergencyOperationMetadata(select);

            expect(hiddenInputs()).toHaveLength(1);
            expect(hiddenInputs()[0]).toBe(existing);
            expect(JSON.parse(existing.value)).toEqual({ name: 'Flood', code: 'MDRXX001' });
        });

        it('clears the hidden input when the select value is empty', async () => {
            const { syncEmergencyOperationMetadata } = await loadRuntime();
            const select = createSelect({ id: 'field-8' });
            const hidden = document.createElement('input');
            hidden.type = 'hidden';
            hidden.name = 'field_disagg_metadata[8]';
            hidden.value = '{"name":"Flood","code":"MDRXX001"}';
            select.form.appendChild(hidden);
            select.value = '';

            syncEmergencyOperationMetadata(select);

            expect(hidden.value).toBe('');
        });

        it('writes JSON {name, code} from data-emergency-name / data-emergency-code', async () => {
            const { syncEmergencyOperationMetadata } = await loadRuntime();
            const select = createSelect({ id: 'field-11' });
            addOption(select, {
                value: 'ignored display',
                emergencyName: '  Typhoon  ',
                emergencyCode: '  MDRPH099  ',
                selected: true,
            });

            syncEmergencyOperationMetadata(select);

            expect(JSON.parse(hiddenInputs()[0].value)).toEqual({
                name: 'Typhoon',
                code: 'MDRPH099',
            });
        });

        it('clears the hidden input when emergency name is [object Object]', async () => {
            const { syncEmergencyOperationMetadata } = await loadRuntime();
            const select = createSelect({ id: 'field-12' });
            addOption(select, {
                value: 'Flood (MDRXX001)',
                emergencyName: '[object Object]',
                emergencyCode: 'MDRXX001',
                selected: true,
            });

            syncEmergencyOperationMetadata(select);

            expect(hiddenInputs()[0].value).toBe('');
        });

        it('parses "Name (CODE)" from option.value when emergency datasets are absent', async () => {
            const { syncEmergencyOperationMetadata } = await loadRuntime();
            const select = createSelect({ id: 'field-13' });
            addOption(select, {
                value: 'Flood Response Operation (MDRXX001)',
                selected: true,
            });

            syncEmergencyOperationMetadata(select);

            expect(JSON.parse(hiddenInputs()[0].value)).toEqual({
                name: 'Flood Response Operation',
                code: 'MDRXX001',
            });
        });

        it('parses a bare option.value as {name, code: ""}', async () => {
            const { syncEmergencyOperationMetadata } = await loadRuntime();
            const select = createSelect({ id: 'field-14' });
            addOption(select, { value: 'Uncoded emergency', selected: true });

            syncEmergencyOperationMetadata(select);

            expect(JSON.parse(hiddenInputs()[0].value)).toEqual({
                name: 'Uncoded emergency',
                code: '',
            });
        });
    });

    describe('initCalculatedLists', () => {
        it('retries until window.existingData is an object, then assigns window helpers', async () => {
            vi.useFakeTimers();
            const { initCalculatedLists } = await loadRuntime();

            initCalculatedLists();
            expect(window.preserveCalculatedSelectStaleValue).toBeUndefined();

            await vi.advanceTimersByTimeAsync(80);
            expect(window.preserveCalculatedSelectStaleValue).toBeUndefined();

            window.existingData = {};
            await vi.advanceTimersByTimeAsync(50);

            expect(typeof window.preserveCalculatedSelectStaleValue).toBe('function');
            expect(typeof window.syncEmergencyOperationMetadata).toBe('function');
            expect(typeof window.refreshCalculatedSelect).toBe('function');
            expect(typeof window.refreshCalculatedMultiSelect).toBe('function');
        });

        it('exposes preserveCalculatedSelectStaleValue on window when existingData is already ready', async () => {
            window.existingData = {};
            const { initCalculatedLists } = await loadRuntime();

            initCalculatedLists();

            expect(typeof window.preserveCalculatedSelectStaleValue).toBe('function');
        });

        it('preserveCalculatedSelectStaleValue is a no-op for an empty saved value', async () => {
            window.existingData = {};
            const { initCalculatedLists } = await loadRuntime();
            initCalculatedLists();

            const select = createSelect({ id: 'field-21', lookupListId: 'countries' });
            window.preserveCalculatedSelectStaleValue(select, '');

            expect(select.options).toHaveLength(1);
            expect(select.dataset.staleSavedValue).toBeUndefined();
            expect(document.querySelector('.calculated-select-stale-indicator')).toBeNull();
        });

        it('preserveCalculatedSelectStaleValue appends a stale option and warning indicator', async () => {
            window.existingData = {};
            const { initCalculatedLists } = await loadRuntime();
            initCalculatedLists();

            const select = createSelect({ id: 'field-22', lookupListId: 'countries' });
            window.preserveCalculatedSelectStaleValue(select, 'Old Op (MDRZZ001)');

            const stale = select.querySelector('option[data-stale-saved-value="true"]');
            expect(stale).toBeTruthy();
            expect(stale.value).toBe('Old Op (MDRZZ001)');
            expect(select.value).toBe('Old Op (MDRZZ001)');
            expect(select.dataset.staleSavedValue).toBe('true');
            expect(select.classList.contains('calculated-select--stale-saved')).toBe(true);

            const indicator = select.nextElementSibling;
            expect(indicator.classList.contains('calculated-select-stale-indicator')).toBe(true);
            expect(indicator.getAttribute('role')).toBe('img');
        });

        it('attaches EmOps listeners without fetching until the field is visible', async () => {
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

            const { initCalculatedLists } = await loadRuntime();
            initCalculatedLists();

            const select = document.getElementById('field-30');
            expect(select.dataset.staleListenerAttached).toBe('true');
            expect(select.dataset.emergencyMetadataListenerAttached).toBe('true');
            expect(fetch).not.toHaveBeenCalled();

            select.value = 'Flood (MDRXX001)';
            select.dispatchEvent(new Event('change', { bubbles: true }));

            const hidden = hiddenInputs()[0];
            expect(hidden.name).toBe('field_disagg_metadata[30]');
            expect(JSON.parse(hidden.value)).toEqual({
                name: 'Flood',
                code: 'MDRXX001',
            });
        });

        it('attaches a dependency listener that refreshes the calculated select', async () => {
            window.existingData = {};
            document.body.innerHTML = `
                <form>
                    <input id="field-10" name="field_value[10]" value="KE">
                    <select id="field-20"
                        name="field_value[20]"
                        data-options-source="calculated"
                        data-lookup-list-id="countries"
                        data-display-column="name"
                        data-list-filters='[{"value_field_id":"10"}]'>
                        <option value=""></option>
                    </select>
                </form>`;

            const { initCalculatedLists } = await loadRuntime();
            initCalculatedLists();
            await Promise.resolve();

            expect(fetch).toHaveBeenCalled();
            const callsAfterInit = fetch.mock.calls.length;

            const dep = document.getElementById('field-10');
            dep.value = 'PH';
            dep.dispatchEvent(new Event('input', { bubbles: true }));
            await Promise.resolve();

            expect(fetch.mock.calls.length).toBeGreaterThan(callsAfterInit);
            expect(String(fetch.mock.calls.at(-1)[0])).toContain('/api/forms/lookup-lists/countries/options');
        });
    });
});
