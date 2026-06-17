import { debugLog } from './debug.js';

const MODULE = 'unique-section-options';

function getSectionRoot(element) {
    return element.closest('[data-collapsible-id]') || element.closest('[id^="section-container-"]');
}

function getFieldItemId(element) {
    const fromSelf = element.dataset.fieldItemId;
    if (fromSelf) return fromSelf;
    const block = element.closest('.form-item-block[data-item-id]');
    return block ? block.dataset.itemId : null;
}

function isUniqueControl(element) {
    return element && element.dataset.uniqueOptionsInSection === 'true';
}

function getChoiceControlsInSection(sectionEl, fieldItemId) {
    if (!sectionEl || !fieldItemId) return [];

    const controls = [];
    sectionEl.querySelectorAll(`[data-unique-options-in-section="true"][data-field-item-id="${fieldItemId}"]`).forEach(el => {
        if (el.tagName === 'SELECT') {
            controls.push({ type: 'single', el });
        } else if (el.matches('[data-options-source]')) {
            controls.push({ type: 'multi', el });
        }
    });
    return controls;
}

function getSelectedValues(control) {
    const values = new Set();
    if (control.type === 'single') {
        const v = control.el.value;
        if (v) values.add(v);
    } else {
        control.el.querySelectorAll('.multi-select-dropdown input[type="checkbox"]:checked').forEach(cb => {
            if (cb.value) values.add(cb.value);
        });
    }
    return values;
}

function getUsedValuesInSection(sectionEl, fieldItemId, excludeControlEl) {
    const used = new Set();
    getChoiceControlsInSection(sectionEl, fieldItemId).forEach(control => {
        if (control.el === excludeControlEl) return;
        getSelectedValues(control).forEach(v => used.add(v));
    });
    return used;
}

function applyToSelect(select) {
    if (!isUniqueControl(select)) return;

    const section = getSectionRoot(select);
    const fieldItemId = getFieldItemId(select);
    if (!section || !fieldItemId) return;

    const usedElsewhere = getUsedValuesInSection(section, fieldItemId, select);
    const current = select.value;

    Array.from(select.options).forEach(opt => {
        if (!opt.value) return;
        if (opt.dataset.staleSavedValue === 'true') {
            opt.disabled = false;
            opt.hidden = false;
            return;
        }
        const taken = usedElsewhere.has(opt.value);
        opt.disabled = taken;
        opt.hidden = taken;
    });

    if (current && usedElsewhere.has(current)) {
        const currentOpt = select.options[select.selectedIndex];
        if (currentOpt?.dataset.staleSavedValue === 'true') {
            return;
        }
        select.value = '';
        select.dispatchEvent(new Event('change', { bubbles: true }));
    }
}

function applyToMultiSelect(wrapper) {
    if (!isUniqueControl(wrapper)) return;

    const section = getSectionRoot(wrapper);
    const fieldItemId = getFieldItemId(wrapper);
    if (!section || !fieldItemId) return;

    const usedElsewhere = getUsedValuesInSection(section, fieldItemId, wrapper);
    const dropdown = wrapper.querySelector('.multi-select-dropdown');
    if (!dropdown) return;

    dropdown.querySelectorAll('.option-item input[type="checkbox"]').forEach(cb => {
        const taken = usedElsewhere.has(cb.value);
        const item = cb.closest('.option-item');
        if (taken && cb.checked) {
            cb.checked = false;
        }
        if (item) {
            item.style.display = taken ? 'none' : '';
        }
        cb.disabled = taken;
    });
}

export function applyUniqueSectionOptions(scopeElement) {
    const root = scopeElement || document;
    root.querySelectorAll('select[data-unique-options-in-section="true"]').forEach(applyToSelect);
    root.querySelectorAll('[data-unique-options-in-section="true"][data-options-source]').forEach(applyToMultiSelect);
}

export function initUniqueSectionOptions() {
    debugLog(MODULE, 'Initializing unique section options');

    applyUniqueSectionOptions(document);

    document.addEventListener('change', (e) => {
        const target = e.target;
        if (!target) return;

        if (target.tagName === 'SELECT' && isUniqueControl(target)) {
            const section = getSectionRoot(target);
            if (section) applyUniqueSectionOptions(section);
            return;
        }

        if (target.type === 'checkbox' && target.closest('.multi-select-dropdown')) {
            const wrapper = target.closest('[data-unique-options-in-section="true"]');
            if (wrapper) {
                const section = getSectionRoot(wrapper);
                if (section) applyUniqueSectionOptions(section);
            }
        }
    });

    document.addEventListener('repeatEntryAdded', (e) => {
        const container = e.detail && e.detail.container;
        if (container) {
            setTimeout(() => applyUniqueSectionOptions(container.closest('[data-collapsible-id]') || container), 0);
        }
    });

    window.applyUniqueSectionOptions = applyUniqueSectionOptions;
}
