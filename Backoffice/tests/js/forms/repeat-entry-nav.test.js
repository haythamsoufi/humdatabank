/**
 * Regression tests for repeat-entry-nav.js sidebar labels.
 *
 * Repeat entries that use a dropdown as the section title relocate that
 * <select> into .repeat-entry__label. Reading labelEl.textContent then
 * concatenates every <option> ("Select...Other (please specify)...") into
 * the sections pane. Nav labels must use only the selected option (or
 * Entry #N when nothing is chosen).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
    debugLog: vi.fn(),
    debugWarn: vi.fn(),
    debugError: vi.fn(),
}));

async function loadNav() {
    vi.resetModules();
    return import('../../../app/static/js/forms/modules/repeat-entry-nav.js');
}

function mountTitleDropdownRepeat({
    sectionId = '12',
    selectedValue = '',
    options = [
        { value: '', text: 'Select...' },
        { value: 'appeal-a', text: 'Appeal A' },
        { value: 'appeal-b', text: 'Appeal B' },
        { value: '__other__', text: 'Other (please specify)...' },
    ],
} = {}) {
    const optionHtml = options
        .map(({ value, text }) => {
            const selected = value === selectedValue ? ' selected' : '';
            return `<option value="${value}"${selected}>${text}</option>`;
        })
        .join('');

    document.body.innerHTML = `
        <div id="section-container-${sectionId}"
             data-collapsible-id="${sectionId}"
             data-show-entries-in-navigation="true">
            <ul class="repeat-entry-nav-list" data-repeat-section-id="${sectionId}"></ul>
            <div id="repeat-entries-${sectionId}">
                <div class="repeat-entry" id="repeat-entry-${sectionId}-1" data-repeat-instance="1">
                    <h5 class="repeat-entry__label repeat-entry__label--title-dropdown">
                        <div class="repeat-entry__title-select-wrap">
                            <select data-use-as-repeat-entry-title="true" data-field-item-id="77">
                                ${optionHtml}
                            </select>
                        </div>
                    </h5>
                </div>
            </div>
        </div>`;
}

describe('repeat-entry-nav title dropdown labels', () => {
    beforeEach(() => {
        window.REPEAT_SECTION_LABELS = { entry: 'Entry' };
    });

    afterEach(() => {
        document.body.innerHTML = '';
        delete window.REPEAT_SECTION_LABELS;
        delete window.syncRepeatEntryNavigation;
        delete window.syncAllRepeatEntryNavigation;
    });

    it('does not dump every dropdown option into the sections pane when nothing is selected', async () => {
        mountTitleDropdownRepeat();
        const { syncRepeatEntryNavigation } = await loadNav();

        syncRepeatEntryNavigation('12');

        const label = document.querySelector('.repeat-entry-nav-label');
        expect(label).toBeTruthy();
        expect(label.textContent).toBe('Entry #1');
        expect(label.textContent).not.toContain('Select...');
        expect(label.textContent).not.toContain('Appeal A');
        expect(label.textContent).not.toContain('Other (please specify)');
    });

    it('uses only the selected option as the nav label', async () => {
        mountTitleDropdownRepeat({ selectedValue: 'appeal-b' });
        const { syncRepeatEntryNavigation } = await loadNav();

        syncRepeatEntryNavigation('12');

        expect(document.querySelector('.repeat-entry-nav-label').textContent).toBe('Appeal B');
    });
});
