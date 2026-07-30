// Description + entry-form hint UI: optional toggles and hint panel placement.

const TYPE_FIELD_CONTAINER_IDS = {
    indicator: 'item-indicator-fields',
    question: 'item-question-fields',
    document_field: 'item-document-fields',
    matrix: 'item-matrix-fields',
    image: 'item-image-fields',
    discussion: 'item-discussion-fields',
};

const DESCRIPTION_TRANSLATION_TRIGGER_IDS = {
    indicator: 'indicator-translations-btn',
    question: 'question-translations-btn',
    document_field: 'document-translations-btn',
    matrix: 'matrix-translations-btn',
    image: 'image-translations-btn',
    discussion: 'discussion-translations-btn',
    plugin: 'plugin-translations-btn',
};

function stripHtml(html) {
    if (!html || typeof html !== 'string') return '';
    const tmp = document.createElement('div');
    tmp.innerHTML = html;
    return (tmp.textContent || tmp.innerText || '').trim();
}

function resolveItemTypeContainerId(itemType) {
    if (!itemType) return null;
    if (String(itemType).startsWith('plugin_')) return null;
    return TYPE_FIELD_CONTAINER_IDS[itemType] || null;
}

function resolveActiveDescriptionBlock(modalElement, itemType) {
    if (!modalElement) return null;
    if (itemType && String(itemType).startsWith('plugin_')) {
        return modalElement.querySelector('#item-plugin-fields .item-optional-description-block');
    }
    const containerId = resolveItemTypeContainerId(itemType);
    if (!containerId) return null;
    return modalElement.querySelector(`#${containerId} .item-optional-description-block`);
}

export function updateDescriptionWrapperVisibility(block) {
    if (!block) return;
    const toggle = block.querySelector('.item-show-description-toggle');
    const wrapper = block.querySelector('.item-description-content-wrapper');
    const translationsBtn = block.querySelector('.item-description-translations-btn');
    if (!toggle || !wrapper) return;
    const expanded = toggle.checked;
    wrapper.classList.toggle('hidden', !expanded);
    if (translationsBtn) translationsBtn.classList.toggle('hidden', !expanded);
    const modalElement = block.closest('#item-modal');
    if (modalElement) updateDescriptionHintSectionLayout(modalElement);
}

const COMPACT_LAYOUT_CLASSES = ['flex', 'flex-wrap', 'items-center', 'gap-x-6', 'gap-y-2'];
const STACKED_LAYOUT_CLASSES = ['flex', 'flex-col', 'gap-6'];
const ALL_LAYOUT_CLASSES = [...new Set([...COMPACT_LAYOUT_CLASSES, ...STACKED_LAYOUT_CLASSES])];

function applyDescriptionHintLayout(inner, compact) {
    ALL_LAYOUT_CLASSES.forEach((cls) => inner.classList.remove(cls));
    (compact ? COMPACT_LAYOUT_CLASSES : STACKED_LAYOUT_CLASSES).forEach((cls) => inner.classList.add(cls));

    inner.querySelectorAll('.item-optional-description-block, .item-description-hint-anchor, #item-entry-form-hint-panel').forEach((el) => {
        el.classList.toggle('w-full', !compact);
    });
}

export function updateDescriptionHintSectionLayout(modalElement) {
    if (!modalElement) return;
    modalElement.querySelectorAll('.item-description-hint-section').forEach((section) => {
        const inner = section.querySelector('.item-description-hint-section-inner');
        if (!inner) return;

        const descToggle = section.querySelector('.item-show-description-toggle');
        const hintToggle = section.querySelector('#item-show-entry-form-hint');
        const compact = !descToggle?.checked && !hintToggle?.checked;

        applyDescriptionHintLayout(inner, compact);
    });
}

export function syncDescriptionToggleLabels(_modalElement) {
    // Labels are fixed to "Description" / "Hint"; kept for call-site compatibility.
}

export function mountEntryFormHintPanel(modalElement, itemType) {
    if (!modalElement) return;
    const panel = modalElement.querySelector('#item-entry-form-hint-panel');
    const storage = modalElement.querySelector('#item-description-hint-panel-storage');
    if (!panel || !storage) return;

    let anchor = null;
    if (itemType && String(itemType).startsWith('plugin_')) {
        anchor = modalElement.querySelector('#item-plugin-fields .item-description-hint-anchor');
    } else {
        const containerId = resolveItemTypeContainerId(itemType);
        if (containerId) {
            anchor = modalElement.querySelector(`#${containerId} .item-description-hint-anchor`);
        }
    }

    if (anchor) {
        anchor.appendChild(panel);
        panel.classList.remove('hidden');
    } else {
        storage.appendChild(panel);
        panel.classList.add('hidden');
    }
    updateDescriptionHintSectionLayout(modalElement);
}

function itemHasDescriptionContent(itemData, itemType) {
    if (!itemData) return false;
    if (itemType === 'indicator' || itemType === 'question') {
        const def = itemData.definition;
        if (!def || !String(def).trim()) return false;
        if (itemType === 'question' && (itemData.question_type === 'blank' || window.ItemModal?.currentQuestionType === 'blank')) {
            return stripHtml(String(def)).length > 0;
        }
        return true;
    }
    return !!(itemData.description && String(itemData.description).trim());
}

export function populateDescriptionVisibility(modalElement, itemData) {
    if (!modalElement) return;
    const itemType = window.ItemModal?.currentItemType;
    const block = resolveActiveDescriptionBlock(modalElement, itemType);
    if (!block) return;

    const toggle = block.querySelector('.item-show-description-toggle');
    if (!toggle) return;

    toggle.checked = itemHasDescriptionContent(itemData, itemType);
    updateDescriptionWrapperVisibility(block);
    updateDescriptionHintSectionLayout(modalElement);
}

export function resetDescriptionVisibility(modalElement) {
    if (!modalElement) return;
    modalElement.querySelectorAll('.item-optional-description-block').forEach((block) => {
        const toggle = block.querySelector('.item-show-description-toggle');
        if (toggle) toggle.checked = false;
        updateDescriptionWrapperVisibility(block);
    });
    updateDescriptionHintSectionLayout(modalElement);
}

export function clearDisabledDescriptions(modalElement) {
    if (!modalElement) return;
    modalElement.querySelectorAll('.item-optional-description-block').forEach((block) => {
        const toggle = block.querySelector('.item-show-description-toggle');
        if (toggle?.checked) return;

        block.querySelectorAll('textarea').forEach((el) => {
            el.value = '';
        });
        const blankEditor = block.querySelector('#item-question-definition-editor');
        if (blankEditor) blankEditor.innerHTML = '';
    });
}

function openDescriptionTranslations(itemType) {
    const triggerId = String(itemType || '').startsWith('plugin_')
        ? DESCRIPTION_TRANSLATION_TRIGGER_IDS.plugin
        : DESCRIPTION_TRANSLATION_TRIGGER_IDS[itemType];
    if (!triggerId) return;
    const btn = document.getElementById(triggerId);
    if (btn) btn.click();
}

export function setupDescriptionHintUI(modalElement) {
    if (!modalElement || modalElement._descriptionHintUiWired) return;
    modalElement._descriptionHintUiWired = true;

    modalElement.addEventListener('change', (event) => {
        const toggle = event.target.closest('.item-show-description-toggle');
        if (toggle && modalElement.contains(toggle)) {
            const block = toggle.closest('.item-optional-description-block');
            updateDescriptionWrapperVisibility(block);
            return;
        }
        if (event.target.id === 'item-show-entry-form-hint') {
            updateDescriptionHintSectionLayout(modalElement);
        }
    });

    modalElement.addEventListener('click', (event) => {
        const btn = event.target.closest('.item-description-translations-btn');
        if (!btn || !modalElement.contains(btn)) return;
        event.preventDefault();
        openDescriptionTranslations(window.ItemModal?.currentItemType);
    });
}
