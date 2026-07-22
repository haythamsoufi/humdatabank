/**
 * Shared carry-forward config UI for all form item types.
 */

const CURRENT_SENTINEL = '__current__';

function parseCarryForwardSources(raw) {
    if (Array.isArray(raw)) return raw;
    if (typeof raw === 'string' && raw.trim()) {
        try {
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed : [];
        } catch (_e) {
            return [];
        }
    }
    return [];
}

function isCurrentSentinel(value) {
    if (value == null || value === '') return true;
    const normalized = String(value).trim().toLowerCase();
    return normalized === CURRENT_SENTINEL || normalized === 'current' || normalized === 'this';
}

function toggleCarryForwardSources(modalElement, enabled) {
    if (!modalElement) return;
    const wrapper = modalElement.querySelector('#item-carry-forward-sources-wrapper');
    if (!wrapper) return;
    wrapper.classList.toggle('hidden', !enabled);
}

function updateCarryForwardPriorityHelp(modalElement) {
    if (!modalElement) return;
    const help = modalElement.querySelector('#item-carry-forward-priority-help');
    const select = modalElement.querySelector('#item-carry-forward-priority');
    if (!help || !select) return;

    if (select.value === 'assignment') {
        help.textContent = 'Data sources: the most recently submitted assignment among all sources below wins.';
    } else {
        help.textContent = 'Data sources: checked in list order — first source with data wins.';
    }
}

function syncSourceRowInputs(row) {
    const templateInput = row.querySelector('.carry-forward-source-template-id');
    const itemInput = row.querySelector('.carry-forward-source-item-id');
    const useCurrentTemplate = row.querySelector('.carry-forward-source-use-current-template');
    const useCurrentItem = row.querySelector('.carry-forward-source-use-current-item');

    if (templateInput && useCurrentTemplate) {
        templateInput.disabled = useCurrentTemplate.checked;
        if (useCurrentTemplate.checked) {
            templateInput.value = '';
        }
    }
    if (itemInput && useCurrentItem) {
        itemInput.disabled = useCurrentItem.checked;
        if (useCurrentItem.checked) {
            itemInput.value = '';
        }
    }
}

function buildCarryForwardSourceRow(source = {}) {
    const row = document.createElement('div');
    row.className = 'carry-forward-source-row flex flex-wrap items-end gap-3 border border-gray-200 rounded-md p-3';

    const templateWrap = document.createElement('div');
    templateWrap.className = 'flex flex-col gap-1';
    const templateLabel = document.createElement('label');
    templateLabel.className = 'text-xs text-gray-600';
    templateLabel.textContent = 'Template ID';
    const templateInput = document.createElement('input');
    templateInput.type = 'number';
    templateInput.min = '1';
    templateInput.step = '1';
    templateInput.placeholder = 'e.g. 22';
    templateInput.className = 'carry-forward-source-template-id w-28 shadow-sm focus:ring-orange-500 focus:border-orange-500 sm:text-sm border-gray-300 rounded-md';
    if (!isCurrentSentinel(source.template_id)) {
        templateInput.value = source.template_id != null ? String(source.template_id) : '';
    }
    const useCurrentTemplateLabel = document.createElement('label');
    useCurrentTemplateLabel.className = 'inline-flex items-center gap-1 text-xs text-gray-600';
    const useCurrentTemplate = document.createElement('input');
    useCurrentTemplate.type = 'checkbox';
    useCurrentTemplate.className = 'carry-forward-source-use-current-template form-checkbox h-3.5 w-3.5 text-orange-600 border-gray-300 rounded focus:ring-orange-500';
    useCurrentTemplate.checked = isCurrentSentinel(source.template_id);
    useCurrentTemplateLabel.append(useCurrentTemplate, document.createTextNode('This template'));
    templateWrap.append(templateLabel, templateInput, useCurrentTemplateLabel);

    const itemWrap = document.createElement('div');
    itemWrap.className = 'flex flex-col gap-1';
    const itemLabel = document.createElement('label');
    itemLabel.className = 'text-xs text-gray-600';
    itemLabel.textContent = 'Item ID';
    const itemInput = document.createElement('input');
    itemInput.type = 'number';
    itemInput.min = '1';
    itemInput.step = '1';
    itemInput.placeholder = 'e.g. 1314';
    itemInput.className = 'carry-forward-source-item-id w-28 shadow-sm focus:ring-orange-500 focus:border-orange-500 sm:text-sm border-gray-300 rounded-md';
    if (!isCurrentSentinel(source.item_id)) {
        itemInput.value = source.item_id != null ? String(source.item_id) : '';
    }
    const useCurrentItemLabel = document.createElement('label');
    useCurrentItemLabel.className = 'inline-flex items-center gap-1 text-xs text-gray-600';
    const useCurrentItem = document.createElement('input');
    useCurrentItem.type = 'checkbox';
    useCurrentItem.className = 'carry-forward-source-use-current-item form-checkbox h-3.5 w-3.5 text-orange-600 border-gray-300 rounded focus:ring-orange-500';
    useCurrentItem.checked = isCurrentSentinel(source.item_id);
    useCurrentItemLabel.append(useCurrentItem, document.createTextNode('This item'));
    itemWrap.append(itemLabel, itemInput, useCurrentItemLabel);

    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'carry-forward-source-remove text-xs text-red-600 hover:underline mb-1';
    removeBtn.textContent = 'Remove';

    row.append(templateWrap, itemWrap, removeBtn);
    syncSourceRowInputs(row);
    return row;
}

export function renderCarryForwardSources(modalElement, sources) {
    if (!modalElement) return;
    const list = modalElement.querySelector('#item-carry-forward-sources-list');
    if (!list) return;
    list.replaceChildren();
    const normalized = parseCarryForwardSources(sources);
    if (normalized.length === 0) {
        list.appendChild(buildCarryForwardSourceRow({
            template_id: CURRENT_SENTINEL,
            item_id: CURRENT_SENTINEL,
        }));
    } else {
        normalized.forEach((source) => {
            list.appendChild(buildCarryForwardSourceRow(source));
        });
    }
    serializeCarryForwardSources(modalElement);
}

export function serializeCarryForwardSources(modalElement) {
    if (!modalElement) return '[]';
    const hidden = modalElement.querySelector('#item-carry-forward-sources-json');
    const list = modalElement.querySelector('#item-carry-forward-sources-list');
    if (!hidden || !list) return '[]';

    const sources = [];
    list.querySelectorAll('.carry-forward-source-row').forEach((row) => {
        const templateInput = row.querySelector('.carry-forward-source-template-id');
        const itemInput = row.querySelector('.carry-forward-source-item-id');
        const useCurrentTemplate = row.querySelector('.carry-forward-source-use-current-template');
        const useCurrentItem = row.querySelector('.carry-forward-source-use-current-item');

        let templateId = CURRENT_SENTINEL;
        if (!useCurrentTemplate?.checked) {
            const parsedTemplateId = templateInput ? parseInt(String(templateInput.value || '').trim(), 10) : NaN;
            if (!Number.isFinite(parsedTemplateId) || parsedTemplateId <= 0) {
                return;
            }
            templateId = parsedTemplateId;
        }

        let itemId = CURRENT_SENTINEL;
        if (!useCurrentItem?.checked) {
            const parsedItemId = itemInput ? parseInt(String(itemInput.value || '').trim(), 10) : NaN;
            if (!Number.isFinite(parsedItemId) || parsedItemId <= 0) {
                return;
            }
            itemId = parsedItemId;
        }

        sources.push({ template_id: templateId, item_id: itemId });
    });
    hidden.value = JSON.stringify(sources);
    return hidden.value;
}

export function resetCarryForwardState(modalElement) {
    if (!modalElement) return;
    const checkbox = modalElement.querySelector('#item-carry-forward');
    const hidden = modalElement.querySelector('#item-carry-forward-sources-json');
    const prioritySelect = modalElement.querySelector('#item-carry-forward-priority');
    if (checkbox) checkbox.checked = false;
    if (hidden) hidden.value = '[]';
    if (prioritySelect) prioritySelect.value = 'source';
    renderCarryForwardSources(modalElement, []);
    toggleCarryForwardSources(modalElement, false);
    updateCarryForwardPriorityHelp(modalElement);
}

export function populateCarryForwardFields(modalElement, itemData) {
    if (!modalElement) return;
    const checkbox = modalElement.querySelector('#item-carry-forward');
    if (!checkbox) return;

    const config = (itemData && itemData.config && typeof itemData.config === 'object') ? itemData.config : {};
    const enabled = config.carry_forward === true || config.carry_forward === 'true';
    checkbox.checked = enabled;

    const prioritySelect = modalElement.querySelector('#item-carry-forward-priority');
    if (prioritySelect) {
        const priority = (config.carry_forward_priority || 'source').toString().toLowerCase();
        prioritySelect.value = priority === 'assignment' ? 'assignment' : 'source';
    }

    renderCarryForwardSources(modalElement, config.carry_forward_sources || []);
    toggleCarryForwardSources(modalElement, enabled);
    updateCarryForwardPriorityHelp(modalElement);
}

export function setupCarryForwardListeners(modalElement) {
    if (!modalElement || modalElement.dataset.carryForwardBound === 'true') return;
    modalElement.dataset.carryForwardBound = 'true';

    const checkbox = modalElement.querySelector('#item-carry-forward');
    const addBtn = modalElement.querySelector('#item-carry-forward-add-source');
    const list = modalElement.querySelector('#item-carry-forward-sources-list');
    const prioritySelect = modalElement.querySelector('#item-carry-forward-priority');

    if (prioritySelect) {
        prioritySelect.addEventListener('change', () => {
            updateCarryForwardPriorityHelp(modalElement);
        });
    }

    if (checkbox) {
        checkbox.addEventListener('change', () => {
            toggleCarryForwardSources(modalElement, checkbox.checked);
            if (checkbox.checked && list && list.children.length === 0) {
                list.appendChild(buildCarryForwardSourceRow({
                    template_id: CURRENT_SENTINEL,
                    item_id: CURRENT_SENTINEL,
                }));
            }
            serializeCarryForwardSources(modalElement);
        });
    }

    if (addBtn && list) {
        addBtn.addEventListener('click', () => {
            list.appendChild(buildCarryForwardSourceRow({}));
            toggleCarryForwardSources(modalElement, true);
            if (checkbox) checkbox.checked = true;
            serializeCarryForwardSources(modalElement);
        });
    }

    if (list) {
        list.addEventListener('input', (event) => {
            const row = event.target.closest('.carry-forward-source-row');
            if (row) syncSourceRowInputs(row);
            serializeCarryForwardSources(modalElement);
        });
        list.addEventListener('change', (event) => {
            const row = event.target.closest('.carry-forward-source-row');
            if (row) syncSourceRowInputs(row);
            serializeCarryForwardSources(modalElement);
        });
        list.addEventListener('click', (event) => {
            const removeBtn = event.target.closest('.carry-forward-source-remove');
            if (!removeBtn || !list.contains(removeBtn)) return;
            const row = removeBtn.closest('.carry-forward-source-row');
            if (row) row.remove();
            serializeCarryForwardSources(modalElement);
        });
    }
}
