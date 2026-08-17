/**
 * First-import staging for dynamic indicators.
 *
 * applyLayoutToSection clones .form-item-block nodes into flex wrappers and
 * discards the originals. addPendingDynamicIndicatorForImport must return the
 * in-document clone so Excel import can write values on the first pass.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

const initializeFieldListeners = vi.fn();

vi.mock('../../../app/static/js/forms/modules/form-item-utils.js', () => ({
    initializeFieldListeners: (...args) => initializeFieldListeners(...args),
}));

vi.mock('../../../app/static/js/forms/modules/layout.js', () => ({
    applyLayoutToSection: vi.fn((sectionContainer) => {
        if (!sectionContainer) return;
        const fields = Array.from(sectionContainer.querySelectorAll('.form-item-block'));
        fields.forEach((field) => {
            if (!field.parentElement) return;
            field.replaceWith(field.cloneNode(true));
        });
    }),
}));

async function importModule() {
    return import('../../../app/static/js/forms/modules/dynamic-indicators.js');
}

beforeEach(() => {
    document.body.innerHTML = '';
    initializeFieldListeners.mockClear();
    delete window.availableIndicatorsData;
    delete window.getFetch;
    delete window.reinitializeDisaggregationCalculator;
    delete window.cleanupInputValues;
    delete window.responseAsResult;
});

describe('addPendingDynamicIndicatorForImport', () => {
    it('returns the live layout clone after the original insert node is discarded', async () => {
        document.body.innerHTML = `
            <input name="csrf_token" value="t">
            <form id="focalDataEntryForm"></form>
            <div id="section-container-8" data-aes-id="1564" data-section-type="dynamic_indicators">
                <div data-collapsible-content>
                    <div id="dynamic-indicator-interface-8"></div>
                </div>
            </div>`;
        window.availableIndicatorsData = { 8: [{ id: 42, name: 'People reached' }] };
        window.getFetch = () => async () => ({
            ok: true,
            headers: { get: () => 'application/json' },
            json: async () => ({
                success: true,
                html: `<div class="form-item-block" data-item-type="indicator" data-assignment-id="from-server">
                    <input name="dynamic_from-server_total_value">
                </div>`,
            }),
        });

        const { addPendingDynamicIndicatorForImport } = await importModule();
        const returned = await addPendingDynamicIndicatorForImport(8, 42);

        expect(returned).toBeTruthy();
        expect(returned.isConnected).toBe(true);
        expect(returned.getAttribute('data-indicator-bank-id')).toBe('42');
        expect(returned.getAttribute('data-pending-assignment-id')).toMatch(/^pending_/);
        expect(initializeFieldListeners).toHaveBeenCalledWith(returned);
        expect(document.querySelectorAll('.form-item-block')).toHaveLength(1);
        expect(document.querySelector('.form-item-block')).toBe(returned);
    });

    it('finds an already-added field by data-indicator-bank-id without a propose button', async () => {
        document.body.innerHTML = `
            <div id="section-container-8" data-aes-id="1564">
                <div class="form-item-block" data-item-type="indicator"
                     data-assignment-id="pending_1" data-indicator-bank-id="42">
                    <input name="dynamic_pending_1_total_value">
                </div>
            </div>`;

        const { addPendingDynamicIndicatorForImport, findDynamicIndicatorFormBlock } = await importModule();
        const container = document.getElementById('section-container-8');

        expect(findDynamicIndicatorFormBlock(container, 42)).toBe(container.querySelector('.form-item-block'));
        await expect(addPendingDynamicIndicatorForImport(8, 42)).resolves.toBeNull();
    });
});
