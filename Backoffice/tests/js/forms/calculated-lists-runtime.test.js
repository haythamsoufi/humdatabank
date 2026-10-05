/**
 * Calculated-list runtime: readiness, window helpers, and adapter delegation.
 * Lookup-specific behaviour lives in the plugin adapter tests.
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

function createSelect({
    id = 'field-42',
    name = 'field_value[42]',
    lookupListId = 'example_list',
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
    delete window.syncCalculatedListSelection;
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

    describe('syncCalculatedListSelection', () => {
        it('calls the adapter registered for that lookup and ignores other lookups', async () => {
            const { registerCalculatedListAdapter, syncCalculatedListSelection } = await loadRuntime();
            const syncSelection = vi.fn();
            registerCalculatedListAdapter({ id: 'example_list', syncSelection });

            const matched = createSelect({ lookupListId: 'example_list' });
            const other = createSelect({ id: 'field-43', lookupListId: 'other_list' });
            syncCalculatedListSelection(matched);
            syncCalculatedListSelection(other);

            expect(syncSelection).toHaveBeenCalledTimes(1);
            expect(syncSelection).toHaveBeenCalledWith(matched);
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
            expect(typeof window.syncCalculatedListSelection).toBe('function');
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

    describe('resolveCalculatedListModuleUrl', () => {
        it('loads plugin adapters from the page origin, not the static CDN that served this module', async () => {
            const { resolveCalculatedListModuleUrl } = await loadRuntime();
            expect(resolveCalculatedListModuleUrl('/plugins/static/example_plugin/js/adapter.js'))
                .toBe(`${window.location.origin}/plugins/static/example_plugin/js/adapter.js`);
            expect(resolveCalculatedListModuleUrl('https://cdn.example/adapter.js'))
                .toBe('https://cdn.example/adapter.js');
        });
    });
});
