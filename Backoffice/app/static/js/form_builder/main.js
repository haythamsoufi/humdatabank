// main.js - Main entry point for the form builder

// Import utils.js to make Utils available globally
import './modules/utils.js';

// Utils is now available globally from utils.js
import { CsrfHandler } from './modules/csrf-handler.js';
import { DataManager } from './modules/data-manager.js';
import { ItemModal } from './modules/item-modal.js';
import { CalculatedLists } from './modules/calculated-lists.js';
import RuleBuilder from './modules/conditions.js';
import { serializeRuleForSubmit } from './modules/form-serialization.js';
import { DynamicSections } from './modules/dynamic-sections.js';
import { FormSubmitUI } from './modules/form-submit-ui.js';
import { initFormBuilderDebug } from './modules/debug.js';
import { TranslationModal } from '../components/translation-modal.js';
import { TranslationMatrix } from '../components/translation-matrix.js';

// Expose key modules for AJAX refresh hooks (safe in this admin-only page).
window.DataManager = DataManager;
window.DynamicSections = DynamicSections;

// Initialize everything when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Enabled in code (no URL flags / console steps needed)
    initFormBuilderDebug({ global: true });

    // Initialize modules
    CsrfHandler.init();
    DataManager.init();
    ItemModal.init();
    CalculatedLists.init();
    DynamicSections.init();
    // Submit UI helper (idempotent)
    FormSubmitUI.init && FormSubmitUI.init();

    // Initialize Select2
    initializeSelect2();

    // Initialize page-specific functionality
    initializePageManagement();
    initializeTemplateDetails();
    initializeSectionManagement();
    initializeItemManagement();
    initializeItemTypePickerModal();
    initializeModalHandlers();
    initializeRuleDisplays();
    initializeSectionFormSerialization();

    // Re-bind handlers after AJAX DOM swaps (idempotent initializers).
    if (!window.__fbDomUpdatedListenerAttached) {
        window.__fbDomUpdatedListenerAttached = true;
        document.addEventListener('formBuilder:domUpdated', function() {
            try { initializePageManagement(); } catch (_e) {}
            try { initializeTemplateDetails(); } catch (_e) {}
        });
    }

    // Template Name Translation modal is handled by translation-page.js

    // Wire Document Field Translation modal via reusable component (tabbed: labels/descriptions)
    try {
        TranslationModal.attach({
            openButtonId: 'document-translations-btn',
            modalId: 'document-translation-modal',
            cssPrefix: 'document',
            // Document modal uses tabbed fields; no single hidden JSON input in modal
            resolveEnglishText: () => {
                const label = document.getElementById('item-document-label');
                const desc = document.getElementById('item-document-description');
                return (label && label.value ? label.value : '') || (desc && desc.value ? desc.value : '');
            },
            tabSuffixes: ['labels','descriptions'],
            defaultTabSuffix: 'labels',
            autoTranslateType: 'document_field',
            onSaveHiddenFields: (byTab) => {
                // Update the shared hidden inputs used by item modal submit
                const itemModal = document.getElementById('item-modal');
                if (itemModal) {
                    const labelInput = itemModal.querySelector('#item-modal-shared-label-translations') || itemModal.querySelector('#item-document-label-translations');
                    const descInput = itemModal.querySelector('#item-modal-shared-description-translations') || itemModal.querySelector('#item-document-description-translations');
                    if (labelInput) labelInput.value = JSON.stringify(byTab.labels || {});
                    if (descInput) descInput.value = JSON.stringify(byTab.descriptions || {});
                }
            }
        });
    } catch (e) {
        // Optional on pages without document translation modal
    }

    // Wire Indicator Translation modal (Labels/Definitions)
    try {
        TranslationModal.attach({
            openButtonId: 'indicator-translations-btn',
            modalId: 'translation-modal',
            cssPrefix: 'translation',
            resolveEnglishText: () => (document.getElementById('item-indicator-label')?.value || ''),
            resolveTextsByTab: () => {
                const lbl = document.getElementById('item-indicator-label')?.value || '';
                const def = document.getElementById('item-indicator-definition')?.value || '';
                if (window.formBuilderDebug && window.formBuilderDebug.isEnabled && window.formBuilderDebug.isEnabled('translation')) {
                    window.formBuilderDebug.log('translation', '[IndicatorTranslate] resolveTextsByTab', { label: lbl, definition: def });
                }
                return { labels: lbl, definitions: def };
            },
            tabSuffixes: ['labels','definitions'],
            defaultTabSuffix: 'labels',
            autoTranslateType: 'form_item',
            onModalOpen: () => {
                const labelTr = document.getElementById('item-modal-shared-label-translations');
                const defTr = document.getElementById('item-modal-definition-translations');
                let lt = {}; let dt = {};
                try { if (labelTr && labelTr.value) lt = JSON.parse(labelTr.value); } catch(_) {}
                try { if (defTr && defTr.value) dt = JSON.parse(defTr.value); } catch(_) {}
                const lbl = document.getElementById('item-indicator-label')?.value || '';
                const def = document.getElementById('item-indicator-definition')?.value || '';
                try { console.log('[IndicatorTranslate] onModalOpen', { englishLabel: lbl, englishDefinition: def, existingLabelTranslations: lt, existingDefinitionTranslations: dt }); } catch (_) {}
                if (window.TranslationModalUtils) {
                    window.TranslationModalUtils.populateFields('translation', lt, '', 'labels');
                    window.TranslationModalUtils.populateFields('translation', dt, '', 'definitions');
                }
            },
            onSaveHiddenFields: (byTab) => {
                const labelTr = document.getElementById('item-modal-shared-label-translations');
                const defTr = document.getElementById('item-modal-definition-translations');
                if (labelTr) labelTr.value = JSON.stringify(byTab.labels || {});
                if (defTr) defTr.value = JSON.stringify(byTab.definitions || {});
                if (window.formBuilderDebug && window.formBuilderDebug.isEnabled && window.formBuilderDebug.isEnabled('translation')) {
                    window.formBuilderDebug.log('translation', '[IndicatorTranslate] onSaveHiddenFields', { saved: byTab });
                }
            }
        });
    } catch (e) {}

    // Wire Question Translation modal (Labels/Definitions)
    try {
        TranslationModal.attach({
            openButtonId: 'question-translations-btn',
            modalId: 'translation-modal',
            cssPrefix: 'translation',
            resolveEnglishText: () => (document.getElementById('item-question-label')?.value || ''),
            resolveTextsByTab: () => ({
                labels: document.getElementById('item-question-label')?.value || '',
                definitions: document.getElementById('item-question-definition')?.value || ''
            }),
            tabSuffixes: ['labels','definitions'],
            defaultTabSuffix: 'labels',
            autoTranslateType: 'form_item',
            onModalOpen: () => {
                const labelTr = document.getElementById('item-modal-shared-label-translations');
                const defTr = document.getElementById('item-modal-definition-translations');
                let lt = {}; let dt = {};
                try { if (labelTr && labelTr.value) lt = JSON.parse(labelTr.value); } catch(_) {}
                try { if (defTr && defTr.value) dt = JSON.parse(defTr.value); } catch(_) {}
                if (window.TranslationModalUtils) {
                    window.TranslationModalUtils.populateFields('translation', lt, '', 'labels');
                    window.TranslationModalUtils.populateFields('translation', dt, '', 'definitions');
                }
            },
            onSaveHiddenFields: (byTab) => {
                const labelTr = document.getElementById('item-modal-shared-label-translations');
                const defTr = document.getElementById('item-modal-definition-translations');
                if (labelTr) labelTr.value = JSON.stringify(byTab.labels || {});
                if (defTr) defTr.value = JSON.stringify(byTab.definitions || {});
            }
        });
    } catch (e) {}

    // Wire Section Name Translation modal via reusable component (single, no tabs)
    try {
        TranslationModal.attach({
            openButtonId: 'section-name-translations-btn',
            modalId: 'section-translation-modal',
            cssPrefix: 'section',
            hiddenInputSelector: '#section-name-translations',
            resolveEnglishText: () => {
                const editName = document.getElementById('edit-section-name-input');
                const addName = document.getElementById('section-name-input') || document.getElementById('name');
                return (editName && editName.value) || (addName && addName.value) || '';
            },
            autoTranslateType: 'section_name',
            onSaveHiddenFields: (collected) => {
                // Update hidden input already handled by hiddenInputSelector
            }
        });
    } catch (e) {
        // Optional on pages without section modal
    }

    // Question Translation modal is now handled by translation-page.js

    // Wire Page Translation Matrix modal
    try {
        TranslationMatrix.attachPages({
            openButtonId: 'page-translations-matrix-btn',
            modalId: 'page-translation-matrix-modal',
            tbodyId: 'page-translation-matrix-tbody',
            saveButtonId: 'save-pages-matrix-btn'
        });
    } catch (e) {}

    // Wire Question Options Translation Matrix modal
    try {
        TranslationMatrix.attachOptions({
            openButtonId: 'question-options-translations-matrix-btn',
            modalId: 'question-options-translation-matrix-modal',
            tbodyId: 'question-options-translation-matrix-tbody',
            saveButtonId: 'save-options-matrix-btn'
        });
    } catch (e) {}

    Utils.setDebugModule('form-builder-loader');
    Utils.debugLog('Form builder initialized');
});

// Initialize Select2 dropdowns
function initializeSelect2() {
    if (window.jQuery && window.jQuery.fn.select2) {
        // Initialize Select2 for item modal
        setTimeout(() => {
            const $bank = $('#item-indicator-bank-select');
            $bank.select2({
                dropdownParent: $('#item-modal'),
                width: '100%',
                theme: "default"
            })
            // Ensure our change handler runs when a selection is made via Select2
            .on('select2:select', function() {
                const el = $bank.get(0);
                if (el) {
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }
            });
        }, 100);
    }
}

// Initialize page management
function initializePageManagement() {
    const paginatedCheckbox = document.querySelector('input[name="is_paginated"]');
    const managePagesContainer = Utils.getElementById('manage-pages-fields-container');

    if (!managePagesContainer) return;

    const updateVisibility = () => {
        if (paginatedCheckbox && paginatedCheckbox.checked) {
            Utils.showElement(managePagesContainer);
        } else if (!paginatedCheckbox) {
            // If checkbox doesn't exist, check if container should be visible based on template state
            const pagesListContainer = Utils.getElementById('pages-list-container');
            if (pagesListContainer && pagesListContainer.children.length > 0) {
                Utils.showElement(managePagesContainer);
            } else {
                Utils.hideElement(managePagesContainer);
            }
        } else {
            Utils.hideElement(managePagesContainer);
        }
    };

    if (paginatedCheckbox) {
        if (paginatedCheckbox.dataset.fbWired !== '1') {
            paginatedCheckbox.dataset.fbWired = '1';
            paginatedCheckbox.addEventListener('change', updateVisibility);
        }
    }
    updateVisibility();

    // Add page functionality
    const addPageBtn = Utils.getElementById('add-page-btn');
    const pagesListContainer = Utils.getElementById('pages-list-container');

    if (addPageBtn && pagesListContainer) {
        if (addPageBtn.dataset.fbWired !== '1') {
            addPageBtn.dataset.fbWired = '1';
            addPageBtn.addEventListener('click', function() {
            const existingOrders = Array.from(pagesListContainer.querySelectorAll('input[name="page_orders"]'))
                .map(input => parseInt(input.value) || 0);
            const nextOrder = existingOrders.length > 0 ? Math.max(...existingOrders) + 1 : 1;

            const newPageRow = document.createElement('div');
            newPageRow.className = 'flex items-center space-x-2 page-row bg-white p-2 rounded';
            newPageRow.draggable = true;
            newPageRow.dataset.order = nextOrder;

            const pageRowFrag = document.createRange().createContextualFragment(`
                <div class="drag-handle cursor-move text-gray-400 hover:text-gray-600">
                    <i class="fas fa-grip-vertical"></i>
                </div>
                <input type="hidden" name="page_ids" value="">
                <input type="text" name="page_names" placeholder="Page name" class="shadow-sm focus:ring-blue-500 focus:border-blue-500 w-full text-sm border-gray-300 rounded-md">
                <input type="hidden" name="page_orders" value="${nextOrder}">
                <input type="hidden" name="page_name_translations" value="{}">
                <button type="button" class="move-up-btn text-gray-600 hover:text-gray-800 p-1" title="Move Up"><i class="fas fa-chevron-up w-4 h-4"></i></button>
                <button type="button" class="move-down-btn text-gray-600 hover:text-gray-800 p-1" title="Move Down"><i class="fas fa-chevron-down w-4 h-4"></i></button>
                <button type="button" class="remove-page-btn text-red-600 hover:text-red-800 p-1" title="Remove Page"><i class="fas fa-trash w-4 h-4"></i></button>
            `);
            newPageRow.appendChild(pageRowFrag);

            const removeBtn = newPageRow.querySelector('.remove-page-btn');
            removeBtn.addEventListener('click', function() {
                newPageRow.remove();
                updatePageOrders();
            });

            const moveUpBtn = newPageRow.querySelector('.move-up-btn');
            moveUpBtn.addEventListener('click', function() {
                const pageRow = moveUpBtn.closest('.page-row');
                const prevRow = pageRow.previousElementSibling;
                if (prevRow && prevRow.classList.contains('page-row')) {
                    pagesListContainer.insertBefore(pageRow, prevRow);
                    updatePageOrders();
                }
            });

            const moveDownBtn = newPageRow.querySelector('.move-down-btn');
            moveDownBtn.addEventListener('click', function() {
                const pageRow = moveDownBtn.closest('.page-row');
                const nextRow = pageRow.nextElementSibling;
                if (nextRow && nextRow.classList.contains('page-row')) {
                    pagesListContainer.insertBefore(nextRow, pageRow);
                    updatePageOrders();
                }
            });

            pagesListContainer.appendChild(newPageRow);
            initializeDragForPage(newPageRow);
            });
        }

        // Add remove functionality to existing remove buttons
        pagesListContainer.querySelectorAll('.remove-page-btn').forEach(btn => {
            if (btn.dataset.fbWired === '1') return;
            btn.dataset.fbWired = '1';
            btn.addEventListener('click', function() {
                btn.closest('.page-row').remove();
                updatePageOrders();
            });
        });

        // Add move up/down functionality to existing buttons
        pagesListContainer.querySelectorAll('.move-up-btn').forEach(btn => {
            if (btn.dataset.fbWired === '1') return;
            btn.dataset.fbWired = '1';
            btn.addEventListener('click', function() {
                const pageRow = btn.closest('.page-row');
                const prevRow = pageRow.previousElementSibling;
                if (prevRow && prevRow.classList.contains('page-row')) {
                    pagesListContainer.insertBefore(pageRow, prevRow);
                    updatePageOrders();
                }
            });
        });

        pagesListContainer.querySelectorAll('.move-down-btn').forEach(btn => {
            if (btn.dataset.fbWired === '1') return;
            btn.dataset.fbWired = '1';
            btn.addEventListener('click', function() {
                const pageRow = btn.closest('.page-row');
                const nextRow = pageRow.nextElementSibling;
                if (nextRow && nextRow.classList.contains('page-row')) {
                    pagesListContainer.insertBefore(nextRow, pageRow);
                    updatePageOrders();
                }
            });
        });

        // Initialize drag and drop for existing pages
        initializePageDragAndDrop();
    }
}

// Drag and drop functionality for pages
let draggedPage = null;
let draggedPageInitialY = 0;
let dropTarget = null;

function initializePageDragAndDrop() {
    const pagesListContainer = Utils.getElementById('pages-list-container');
    if (!pagesListContainer) return;

    const pages = pagesListContainer.getElementsByClassName('page-row');
    Array.from(pages).forEach(page => initializeDragForPage(page));
}

function initializeDragForPage(page) {
    if (!page) return;
    if (page.dataset.fbDragWired === '1') return;
    page.dataset.fbDragWired = '1';
    const handle = page.querySelector('.drag-handle');
    if (!handle) return;

    handle.addEventListener('mousedown', () => {
        page.draggable = true;
    });

    handle.addEventListener('mouseup', () => {
        page.draggable = false;
    });

    page.addEventListener('dragstart', (e) => {
        draggedPage = page;
        draggedPageInitialY = e.clientY;
        page.classList.add('dragging');

        // Create a custom drag image
        const dragImage = page.cloneNode(true);
        dragImage.style.opacity = '0.5';
        document.body.appendChild(dragImage);
        e.dataTransfer.setDragImage(dragImage, 0, 0);
        setTimeout(() => document.body.removeChild(dragImage), 0);
    });

    page.addEventListener('dragend', () => {
        page.classList.remove('dragging');
        draggedPage = null;
        dropTarget = null;
        updatePageOrders();
    });

    page.addEventListener('dragover', (e) => {
        e.preventDefault();
        if (page === draggedPage) return;

        const rect = page.getBoundingClientRect();
        const midpoint = rect.top + rect.height / 2;

        // Determine if we're dropping before or after based on mouse position
        const position = e.clientY < midpoint ? 'before' : 'after';

        // Remove existing drop indicators
        page.classList.remove('drop-above', 'drop-below');

        // Add new drop indicator
        page.classList.add(position === 'before' ? 'drop-above' : 'drop-below');

        dropTarget = { page, position };
    });

    page.addEventListener('dragleave', () => {
        page.classList.remove('drop-above', 'drop-below');
        if (dropTarget?.page === page) {
            dropTarget = null;
        }
    });

    page.addEventListener('drop', (e) => {
        e.preventDefault();
        page.classList.remove('drop-above', 'drop-below');

        if (!draggedPage || draggedPage === page) return;

        const position = dropTarget?.position || 'after';
        const pagesListContainer = Utils.getElementById('pages-list-container');

        if (position === 'before') {
            pagesListContainer.insertBefore(draggedPage, page);
        } else {
            pagesListContainer.insertBefore(draggedPage, page.nextSibling);
        }

        updatePageOrders();
    });
}

function updatePageOrders() {
    const pagesListContainer = Utils.getElementById('pages-list-container');
    if (!pagesListContainer) return;

    const pages = Array.from(pagesListContainer.getElementsByClassName('page-row'));
    pages.forEach((page, index) => {
        const order = index + 1;
        page.dataset.order = order;
        page.querySelector('input[name="page_orders"]').value = order;
    });
}

// Initialize template details editing
function initializeTemplateDetails() {
    const editBtn = Utils.getElementById('edit-template-details-btn');
    if (!editBtn) return;

    // Delegated + dynamic element resolution so this keeps working after AJAX refresh swaps
    if (editBtn.dataset.fbWired === '1') return;
    editBtn.dataset.fbWired = '1';

    // Store original chrome so we can restore it after toggling
    editBtn.dataset.originalHtml = editBtn.dataset.originalHtml || editBtn.innerHTML;
    editBtn.dataset.originalClass = editBtn.dataset.originalClass || editBtn.className;

    function enterEditMode() {
        const displaySection = Utils.getElementById('template-details-display');
        const formContainer = Utils.getElementById('edit-template-details-form-container');
        const topSaveBtn = Utils.getElementById('save-template-details-top-btn');
        const bottomButtons = Utils.getElementById('template-details-bottom-buttons');
        if (displaySection) Utils.hideElement(displaySection);
        if (formContainer) Utils.showElement(formContainer);
        if (topSaveBtn) Utils.showElement(topSaveBtn);
        if (bottomButtons) Utils.hideElement(bottomButtons);
        editBtn.replaceChildren();
        const icon = document.createElement('i');
        icon.className = 'fas fa-times w-4 h-4 mr-2';
        editBtn.append(icon, document.createTextNode('Cancel'));
        editBtn.className = 'inline-flex items-center bg-gray-300 hover:bg-gray-400 text-gray-700 font-semibold py-2 px-4 rounded-lg shadow text-sm transition duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-400';
    }

    function exitEditMode() {
        const displaySection = Utils.getElementById('template-details-display');
        const formContainer = Utils.getElementById('edit-template-details-form-container');
        const topSaveBtn = Utils.getElementById('save-template-details-top-btn');
        const bottomButtons = Utils.getElementById('template-details-bottom-buttons');
        if (displaySection) Utils.showElement(displaySection);
        if (formContainer) Utils.hideElement(formContainer);
        if (topSaveBtn) {
            Utils.hideElement(topSaveBtn);
            // Reset loading state (top save is outside form, so FormSubmitGuard.reset(form) doesn't reach it)
            try {
                if (window.FormSubmitGuard && typeof window.FormSubmitGuard.resetButton === 'function') {
                    window.FormSubmitGuard.resetButton(topSaveBtn);
                }
            } catch (_e) {}
        }
        if (bottomButtons) Utils.showElement(bottomButtons);
        editBtn.replaceChildren();
        editBtn.appendChild(document.createRange().createContextualFragment(editBtn.dataset.originalHtml || ''));
        editBtn.className = editBtn.dataset.originalClass || editBtn.className;
    }

    // Expose for AJAX success handler (form-submit-ui.js) to exit edit mode after save
    window.exitTemplateDetailsEditMode = exitEditMode;

    editBtn.addEventListener('click', function() {
        const formContainer = Utils.getElementById('edit-template-details-form-container');
        const isHidden = !formContainer || formContainer.classList.contains('hidden') || formContainer.style.display === 'none';
        if (isHidden) {
            enterEditMode();
        } else {
            exitEditMode();
        }
    });

    // Cancel button is inside the swapped container, so delegate it
    document.addEventListener('click', function(e) {
        const cancel = e.target.closest('#cancel-edit-template-details');
        if (!cancel) return;
        e.preventDefault();
        exitEditMode();
    });
}

// Initialize section management
// Helper function to calculate the next available section order
function calculateNextSectionOrder() {
    // Top-level sections only (parent_section_id is empty)
    let maxOrder = 0;
    document.querySelectorAll('.edit-section-btn').forEach((btn) => {
        const parentId = (btn.dataset.parentSectionId || '').trim();
        if (parentId) return;
        const raw = (btn.dataset.sectionOrder || '').trim();
        const n = parseInt(String(raw).split('.')[0], 10);
        if (!Number.isNaN(n) && n > maxOrder) maxOrder = n;
    });
    return maxOrder === 0 ? 1 : maxOrder + 1;
}

function calculateNextChildSectionOrder(parentSectionId) {
    const pid = String(parentSectionId || '').trim();
    if (!pid) return 1;

    let maxChild = 0;
    document.querySelectorAll(`tr.bg-teal-50[data-parent-section-id="${CSS.escape(pid)}"]`).forEach((row) => {
        // Prefer the displayed child order number (works for both legacy 4.1 and new integer scheme)
        const orderSpan = row.querySelector('td:first-child span');
        const rawText = (orderSpan ? orderSpan.textContent : row.getAttribute('data-subsection-order')) || '';
        // If legacy stored value is like "4.1", take the part after the dot; else integer
        const s = String(rawText).trim();
        const maybeChild = s.includes('.') ? parseInt(s.split('.')[1], 10) : parseInt(s, 10);
        if (!Number.isNaN(maybeChild) && maybeChild > maxChild) maxChild = maybeChild;
    });

    return maxChild === 0 ? 1 : maxChild + 1;
}

function populateSectionParentDropdown({ currentSectionId = null, selectedParentId = null } = {}) {
    const selectEl = Utils.getElementById('section-parent-section-id');
    if (!selectEl) return null;

    // Capture current selection so we can preserve it if needed
    const preferred = selectedParentId != null ? String(selectedParentId) : String(selectEl.value || '');

    // Clear and add "no parent"
    selectEl.replaceChildren();
    {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = selectEl.dataset.noneText || 'No parent (top-level section)';
        selectEl.appendChild(opt);
    }

    // Build options from existing top-level sections in the DOM (prevents deeper nesting)
    const topLevel = [];
    document.querySelectorAll('.section-item').forEach((container) => {
        const editBtn = container.querySelector('.edit-section-btn');
        if (!editBtn) return;
        const parentId = (editBtn.dataset.parentSectionId || '').trim();
        if (parentId) return; // only top-level sections can be parents

        const id = (editBtn.dataset.sectionId || '').trim();
        const name = (editBtn.dataset.sectionName || '').trim();
        const rawOrder = (editBtn.dataset.sectionOrder || '').trim();
        const orderNum = parseInt(String(rawOrder).split('.')[0], 10);
        if (!id || !name) return;
        topLevel.push({ id, name, order: Number.isNaN(orderNum) ? 0 : orderNum });
    });

    topLevel.sort((a, b) => (a.order - b.order) || a.name.localeCompare(b.name));

    topLevel.forEach(({ id, name, order }) => {
        // Prevent selecting itself as parent
        if (currentSectionId && String(currentSectionId) === String(id)) return;
        const opt = document.createElement('option');
        opt.value = String(id);
        opt.textContent = order ? `${order}. ${name}` : name;
        selectEl.appendChild(opt);
    });

    // Restore selection if possible
    selectEl.value = preferred;
    return selectEl;
}

function initializeSectionManagement() {
    const sectionForm = document.getElementById('section-form');
    if (sectionForm) {
        sectionForm.addEventListener('submit', async function(e) {
            e.preventDefault();

            const submitButton = this.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.replaceChildren();
                {
                    const icon = document.createElement('i');
                    icon.className = 'fas fa-spinner fa-spin mr-2';
                    submitButton.append(icon, document.createTextNode('Processing...'));
                }
            }

            try {
                const payload = window.formDataToJson ? window.formDataToJson(sectionForm) : null;
                const fetchFn = (window.getFetch && window.getFetch()) || fetch;
                const action = sectionForm.getAttribute('action') || window.location.href;
                const resp = await fetchFn(action, {
                    method: 'POST',
                    body: payload ? JSON.stringify(payload) : new FormData(sectionForm),
                    credentials: 'same-origin',
                    headers: payload
                        ? { 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/json' }
                        : { 'X-Requested-With': 'XMLHttpRequest' }
                });
                if (resp.redirected) {
                    window.location.href = resp.url;
                    return;
                }
                const ct = (resp.headers.get('content-type') || '').toLowerCase();
                if (ct.includes('application/json')) {
                    const result = await resp.json();
                    if (result.redirect_url) {
                        window.location.href = result.redirect_url;
                        return;
                    }
                }
                window.location.reload();
            } catch (err) {
                console.error('Section save failed:', err);
                if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.textContent = 'Save';
                }
            }
        });
    }

    // Add section modal
    const addSectionBtn = Utils.getElementById('add-section-btn');

    if (addSectionBtn) {
        addSectionBtn.addEventListener('click', function() {
            showSectionModal('add');
        });
    }

    // Section relevance rule handling is managed by the general toggle-rule-builder event handler

    // Edit section / add subsection handlers (delegated, works after AJAX refresh)
    if (!window.__fbSectionDelegatesAttached) {
        window.__fbSectionDelegatesAttached = true;
        document.addEventListener('click', function(e) {
            const editBtn = e.target.closest('.edit-section-btn');
            if (editBtn) {
                e.preventDefault();
                const dataset = editBtn.dataset;
                const sectionId = dataset.sectionId;
                const sectionName = dataset.sectionName;
                const sectionOrder = dataset.sectionOrder;
                const parentSectionId = dataset.parentSectionId;
                const parentPageId = dataset.parentPageId;
                const sectionType = dataset.sectionType;
                const pageId = dataset.pageId;
                const maxDynamicIndicators = dataset.maxDynamicIndicators;
                const addIndicatorNote = dataset.addIndicatorNote;
                const maxEntries = dataset.maxEntries;
                const nameTranslations = dataset.nameTranslations;
                const relevanceCondition = dataset.relevanceCondition;

                showSectionModal('edit', {
                    id: sectionId,
                    name: sectionName,
                    order: sectionOrder,
                    parent_section_id: parentSectionId,
                    parent_page_id: parentPageId,
                    section_type: sectionType,
                    page_id: pageId,
                    max_dynamic_indicators: maxDynamicIndicators,
                    add_indicator_note: addIndicatorNote,
                    max_entries: maxEntries,
                    name_translations: nameTranslations,
                    relevance_condition: relevanceCondition
                });
                return;
            }

            const addSubBtn = e.target.closest('.add-subsection-btn');
            if (addSubBtn) {
                e.preventDefault();
                const dataset = addSubBtn.dataset;
                const parentSectionId = dataset.sectionId;
                const pageId = dataset.pageId || '';
                const nextSubsectionOrder = calculateNextChildSectionOrder(parentSectionId);
                showSectionModal('add', {
                    parent_section_id: parentSectionId,
                    order: nextSubsectionOrder,
                    page_id: pageId
                });
            }
        });
    }

}

// Initialize item management
function initializeItemManagement() {
    // Add item buttons: open type picker modal first; tile selection then opens item config
    document.addEventListener('click', function(e) {
        const btn = e.target.closest('.add-item-to-section-btn');
        if (!btn) return;
        e.preventDefault();
        const sectionId = btn.dataset.sectionId;
        const sectionName = btn.dataset.sectionName || '';
        if (sectionId) {
            showItemTypePickerModal(sectionId, sectionName, 'add');
        }
    });

    // Item modal: "Select Item Type" button opens tiles picker to change type
    document.addEventListener('click', function(e) {
        const trigger = e.target.closest('#item-type-trigger-btn');
        if (!trigger) return;
        e.preventDefault();
        const sectionIdEl = document.getElementById('item-modal-section-id');
        const sectionNameEl = document.getElementById('item-modal-section-name');
        const sectionId = sectionIdEl ? sectionIdEl.value : '';
        const sectionName = sectionNameEl ? (sectionNameEl.textContent || '').trim() : '';
        showItemTypePickerModal(sectionId, sectionName, 'change_type');
    });


    // Edit item buttons (delegated, works after AJAX refresh)
    if (!window.__fbItemEditDelegatesAttached) {
        window.__fbItemEditDelegatesAttached = true;
        document.addEventListener('click', function(e) {
            const indBtn = e.target.closest('.edit-indicator-btn');
            if (indBtn) {
                e.preventDefault();
                const dataset = indBtn.dataset;
                const itemData = {
                    id: dataset.indicatorId,
                    indicator_bank_id: dataset.indicatorBankId,
                    bank_label: dataset.indicatorBankLabel || '',
                    bank_definition: dataset.indicatorBankDefinition || '',
                    section_id: dataset.currentSectionId,
                    order: dataset.indicatorOrder,
                    is_required: dataset.isRequired === 'true',
                    allowed_disaggregation_options: dataset.allowedDisaggregationOptions ? dataset.allowedDisaggregationOptions.split(',') : [],
                    age_groups_config: dataset.ageGroupsConfig,
                    unit: dataset.indicatorUnit,
                    relevance_condition: dataset.relevanceCondition,
                    validation_condition: dataset.validationCondition,
                    validation_message: dataset.validationMessage,
                    allow_data_not_available: ['true','1','yes'].includes((dataset.allowDataNotAvailable || '').toLowerCase()),
                    allow_not_applicable: ['true','1','yes'].includes((dataset.allowNotApplicable || '').toLowerCase()),
                    indirect_reach: ['true','1','yes'].includes((dataset.indirectReach || '').toLowerCase()),
                    layout_column_width: dataset.layoutColumnWidth,
                    layout_break_after: dataset.layoutBreakAfter === 'true',
                    label: dataset.indicatorLabel,
                    definition: dataset.indicatorDefinition,
                    privacy: dataset.privacy,
                    label_translations: dataset.labelTranslations ? JSON.parse(dataset.labelTranslations) : {},
                    definition_translations: dataset.definitionTranslations ? JSON.parse(dataset.definitionTranslations) : {},
                    config: dataset.config ? JSON.parse(dataset.config) : {}
                };
                ItemModal.showEditModal(dataset.indicatorId, 'indicator', itemData);
                return;
            }

            const qBtn = e.target.closest('.edit-question-btn');
            if (qBtn) {
                e.preventDefault();
                const dataset = qBtn.dataset;
                const itemData = {
                    id: dataset.questionId,
                    label: dataset.questionLabel,
                    question_type: dataset.questionType,
                    unit: dataset.questionUnit,
                    definition: dataset.questionDefinition,
                    options_json: dataset.questionOptions,
                    section_id: dataset.currentSectionId,
                    order: dataset.questionOrder,
                    is_required: dataset.isRequired === 'true',
                    relevance_condition: dataset.relevanceCondition,
                    validation_condition: dataset.validationCondition,
                    validation_message: dataset.validationMessage,
                    allow_data_not_available: ['true','1','yes'].includes((dataset.allowDataNotAvailable || '').toLowerCase()),
                    allow_not_applicable: ['true','1','yes'].includes((dataset.allowNotApplicable || '').toLowerCase()),
                    indirect_reach: ['true','1','yes'].includes((dataset.indirectReach || '').toLowerCase()),
                    layout_column_width: dataset.layoutColumnWidth,
                    layout_break_after: dataset.layoutBreakAfter === 'true',
                    options_source: dataset.optionsSource || 'manual',
                    lookup_list_id: dataset.lookupListId || '',
                    list_display_column: dataset.displayColumn || '',
                    list_filters_json: dataset.filtersJson || '[]',
                    privacy: dataset.privacy,
                    label_translations: dataset.labelTranslations ? JSON.parse(dataset.labelTranslations) : {},
                    definition_translations: dataset.definitionTranslations ? JSON.parse(dataset.definitionTranslations) : {},
                    options_translations: dataset.optionsTranslations ? JSON.parse(dataset.optionsTranslations) : [],
                    config: dataset.config ? JSON.parse(dataset.config) : {}
                };
                ItemModal.showEditModal(dataset.questionId, 'question', itemData);
                return;
            }

            const docBtn = e.target.closest('.edit-document-field-btn');
            if (docBtn) {
                e.preventDefault();
                const dataset = docBtn.dataset;
                const itemData = {
                    id: dataset.documentFieldId,
                    label: dataset.documentFieldLabel,
                    description: dataset.documentFieldDescription,
                    section_id: dataset.currentSectionId || null,
                    order: dataset.documentFieldOrder,
                    is_required: dataset.documentFieldRequired === 'true',
                    relevance_condition: dataset.relevanceCondition,
                    layout_column_width: dataset.layoutColumnWidth,
                    layout_break_after: dataset.layoutBreakAfter === 'true',
                    privacy: dataset.privacy,
                    label_translations: JSON.parse(dataset.labelTranslations || '{}'),
                    description_translations: JSON.parse(dataset.descriptionTranslations || '{}'),
                    config: JSON.parse(dataset.config || '{}')
                };
                ItemModal.showEditModal(dataset.documentFieldId, 'document_field', itemData);
                return;
            }

            const pluginBtn = e.target.closest('.edit-plugin-item-btn');
            if (pluginBtn) {
                e.preventDefault();
                const dataset = pluginBtn.dataset;
                const itemData = {
                    id: dataset.pluginItemId,
                    item_type: dataset.pluginItemType,
                    label: dataset.pluginItemLabel,
                    description: dataset.pluginItemDescription,
                    section_id: (dataset.currentSectionId && dataset.currentSectionId.trim()) ? dataset.currentSectionId : null,
                    order: dataset.pluginItemOrder,
                    is_required: dataset.pluginItemRequired === 'true',
                    relevance_condition: dataset.relevanceCondition,
                    validation_condition: dataset.validationCondition,
                    validation_message: dataset.validationMessage,
                    allow_data_not_available: ['true','1','yes'].includes((dataset.allowDataNotAvailable || '').toLowerCase()),
                    allow_not_applicable: ['true','1','yes'].includes((dataset.allowNotApplicable || '').toLowerCase()),
                    indirect_reach: ['true','1','yes'].includes((dataset.indirectReach || '').toLowerCase()),
                    layout_column_width: dataset.layoutColumnWidth,
                    layout_break_after: dataset.layoutBreakAfter === 'true',
                    privacy: dataset.privacy,
                    plugin_config: dataset.pluginConfig ? JSON.parse(dataset.pluginConfig) : {}
                };
                ItemModal.showEditModal(dataset.pluginItemId, dataset.pluginItemType, itemData);
                return;
            }

            const matrixBtn = e.target.closest('.edit-matrix-item-btn');
            if (matrixBtn) {
                e.preventDefault();
                const dataset = matrixBtn.dataset;
                const itemData = {
                    id: dataset.matrixItemId,
                    label: dataset.matrixItemLabel,
                    description: dataset.matrixItemDescription,
                    section_id: dataset.currentSectionId || null,
                    order: dataset.matrixItemOrder,
                    is_required: dataset.matrixItemRequired === 'true',
                    relevance_condition: dataset.relevanceCondition,
                    layout_column_width: dataset.layoutColumnWidth,
                    layout_break_after: dataset.layoutBreakAfter === 'true',
                    privacy: dataset.privacy,
                    label_translations: JSON.parse(dataset.labelTranslations || '{}'),
                    description_translations: JSON.parse(dataset.descriptionTranslations || '{}'),
                    config: dataset.matrixConfig ? JSON.parse(dataset.matrixConfig) : { type: 'matrix', rows: [], columns: [] }
                };
                ItemModal.showEditModal(dataset.matrixItemId, 'matrix', itemData);
            }
        });
    }

}

// Add option field
function addOptionField(container, value = '') {
    const template = document.getElementById('item-question-option-template');
    if (!template) return null;

    const newRow = template.content.cloneNode(true);
    const textInput = newRow.querySelector('.option-text');
    if (textInput) {
        textInput.value = value;
    }

    container.appendChild(newRow);

    // The event listeners are delegated, so no need to add them here.
    if(window.updateOptionsJson) {
        window.updateOptionsJson(container);
    }

    // Return the actual DOM element that was added
    return container.lastElementChild;
}
window.addOptionField = addOptionField; // Expose to global scope

// Update options JSON
function updateOptionsJson(container) {
    const optionsList = container.querySelectorAll('.option-text');
    const options = Array.from(optionsList).map(input => input.value.trim()).filter(Boolean);
    const jsonInput = document.getElementById('item-question-options-json');
    if (jsonInput) {
        jsonInput.value = JSON.stringify(options);
    }
}
window.updateOptionsJson = updateOptionsJson; // Expose to global scope

// Initialize options from JSON
function initializeOptionsFromJson(container, optionsData) {
    if (!container) return;
    container.replaceChildren(); // Clear existing
    if (optionsData && Array.isArray(optionsData) && optionsData.length > 0) {
        optionsData.forEach(optionValue => {
            if (window.addOptionField) {
                window.addOptionField(container, optionValue);
            }
        });
    } else {
        // Add one empty field if no options exist
        if (window.addOptionField) {
            window.addOptionField(container, '');
        }
    }
    if (window.updateOptionsJson) {
        window.updateOptionsJson(container);
    }
}
window.initializeOptionsFromJson = initializeOptionsFromJson; // Expose to global scope

// Initialize modal handlers
function initializeModalHandlers() {
    // General close modal buttons
    document.addEventListener('click', function(event) {
        if (event.target.closest('.close-modal')) {
            // Find the immediate modal that contains the close button
            const closeButton = event.target.closest('.close-modal');
            // Find the modal that directly contains this close button
            const modal = closeButton.closest('[id$="-modal"]');
            if (modal && modal.classList.contains('fixed') && modal.classList.contains('inset-0')) {
                modal.classList.add('hidden');
            }
        }
    });

    // Event delegation for manual options functionality
    document.addEventListener('click', function(event) {
        // Add option button
        if (event.target.closest('.add-option-btn')) {
            event.preventDefault();
            const optionRow = event.target.closest('.option-row');
            const optionsList = optionRow.parentElement;
            if (window.addOptionField) {
                const newRow = window.addOptionField(optionsList, '');
                // Focus on the new input if the row was created successfully
                if (newRow) {
                    const newInput = newRow.querySelector('.option-text');
                    if (newInput) {
                        newInput.focus();
                    }
                }
            }
        }

        // Remove option button
        if (event.target.closest('.remove-option-btn')) {
            event.preventDefault();
            const optionRow = event.target.closest('.option-row');
            const optionsList = optionRow.parentElement;
            optionRow.remove();
            if (window.updateOptionsJson) {
                window.updateOptionsJson(optionsList);
            }
        }

        // Move up button
        if (event.target.closest('.move-up-btn')) {
            event.preventDefault();
            const optionRow = event.target.closest('.option-row');
            const optionsList = optionRow.parentElement;
            const prev = optionRow.previousElementSibling;
            if (prev) {
                prev.before(optionRow);
                if (window.updateOptionsJson) {
                    window.updateOptionsJson(optionsList);
                }
            }
        }

        // Move down button
        if (event.target.closest('.move-down-btn')) {
            event.preventDefault();
            const optionRow = event.target.closest('.option-row');
            const optionsList = optionRow.parentElement;
            const next = optionRow.nextElementSibling;
            if (next) {
                next.after(optionRow);
                if (window.updateOptionsJson) {
                    window.updateOptionsJson(optionsList);
                }
            }
        }
    });

    // Event delegation for option text input changes
    document.addEventListener('input', function(event) {
        if (event.target.classList.contains('option-text')) {
            const optionsList = event.target.closest('#item-question-options-list');
            if (optionsList && window.updateOptionsJson) {
                window.updateOptionsJson(optionsList);
            }
        }
    });

    // Rule builder toggle buttons
    document.addEventListener('click', function(event) {
        if (event.target.closest('.toggle-rule-builder')) {
            const button = event.target.closest('.toggle-rule-builder');
            const targetSelector = button.dataset.target;
            const targetElement = document.querySelector(targetSelector);

            if (targetElement) {
                const isVisible = !targetElement.classList.contains('hidden');

                if (isVisible) {
                    // Hide the rule section
                    Utils.hideElement(targetElement);
                    button.replaceChildren();
                    {
                        const icon = document.createElement('i');
                        icon.className = 'fas fa-plus-circle mr-1';
                        button.append(icon, document.createTextNode(' Add Relevance Rule'));
                    }

                    // Hide the right half if no rules are visible
                    const modal = targetElement.closest('.modal-grid-container');
                    if (modal) {
                        const rightHalf = modal.querySelector('.modal-right-half');
                        const visibleRules = rightHalf ? rightHalf.querySelectorAll('.rule-section:not(.hidden), div[id$="-rule-section"]:not(.hidden)') : [];
                        if (visibleRules.length === 0) {
                            Utils.hideElement(rightHalf);
                            modal.classList.remove('md:grid-cols-2');
                            // Revert modal width when no rule sections are visible
                            const modalContent = modal.closest('.relative.p-6');
                            if (modalContent) {
                                modalContent.classList.remove('max-w-4xl');
                                modalContent.classList.remove('max-w-6xl');
                                modalContent.classList.remove('max-w-lg');
                                modalContent.classList.add('max-w-xl');
                            }
                        }
                    }
                } else {
                    // Show the rule section
                    Utils.showElement(targetElement);
                    button.replaceChildren();
                    {
                        const icon = document.createElement('i');
                        icon.className = 'fas fa-minus-circle mr-1';
                        button.append(icon, document.createTextNode(' Hide Relevance Rule'));
                    }

                    // Show the right half and switch to two-column layout
                    const modal = targetElement.closest('.modal-grid-container');
                    if (modal) {
                        const rightHalf = modal.querySelector('.modal-right-half');
                        if (rightHalf) {
                            Utils.showElement(rightHalf);
                            modal.classList.add('md:grid-cols-2');
                            // Expand modal width when a rule section is shown
                            const modalContent = modal.closest('.relative.p-6');
                            if (modalContent) {
                                modalContent.classList.remove('max-w-lg', 'max-w-xl', 'max-w-4xl');
                                modalContent.classList.add('max-w-6xl');
                            }
                        }
                    }

                    // Initialize rule builder if not already initialized
                    const ruleBuilder = targetElement.querySelector('.rule-builder') || targetElement.querySelector('[id$="-rule-builder"]');

                    if (ruleBuilder) {
                        // Only initialize if the rule builder is empty or not marked as initialized
                        const needsInitialization = ruleBuilder.innerHTML.trim() === '' || !targetElement.hasAttribute('data-initialized');

                        if (needsInitialization) {
                            const ruleType = targetSelector.includes('validation') ? 'validation' : 'relevance';

                            // Attempt to retrieve pre-existing rule JSON stored on the element
                            let existingRuleJson = ruleBuilder.getAttribute('data-rule-json');

                            if (existingRuleJson && existingRuleJson.trim() !== '' && existingRuleJson !== 'null' && existingRuleJson !== '{}') {
                                try {
                                    // Ensure parsable JSON
                                    JSON.parse(existingRuleJson);
                            } catch (parseError) {
                                existingRuleJson = null;
                            }
                            } else {
                                existingRuleJson = null;
                            }

                            // Get current item ID from ItemModal and convert to prefixed format
                            let currentItemId = null;
                            if (window.ItemModal && window.ItemModal.currentItemId) {
                                const numericId = window.ItemModal.currentItemId;
                                const itemType = window.ItemModal.currentItemType || 'question';

                                // Convert to prefixed format based on item type
                                if (itemType === 'indicator') {
                                    currentItemId = `indicator_${numericId}`;
                                } else if (itemType === 'question') {
                                    currentItemId = `question_${numericId}`;
                                } else if (itemType === 'document_field') {
                                    currentItemId = `document_field_${numericId}`;
                                } else if (itemType === 'matrix') {
                                    currentItemId = `matrix_${numericId}`;
                                } else if (itemType && itemType.startsWith('plugin_')) {
                                    currentItemId = `plugin_${numericId}`;
                                } else {
                                    // Try to find the item in allTemplateItems to get the correct prefix
                                    const allItems = DataManager.getData('allTemplateItems') || [];
                                    const foundItem = allItems.find(item => {
                                        const match = item.id && item.id.match(/^.+_(\d+)$/);
                                        return match && parseInt(match[1], 10) === parseInt(numericId, 10);
                                    });
                                    if (foundItem) {
                                        currentItemId = foundItem.id;
                                    } else {
                                        // Fallback to question_ prefix
                                        currentItemId = `question_${numericId}`;
                                    }
                                }
                            }

                            try {
                                RuleBuilder.renderRuleBuilder(ruleBuilder, existingRuleJson, ruleType, currentItemId);
                                targetElement.setAttribute('data-initialized', 'true');
                            } catch (error) {
                                // Silently handle rule builder initialization errors
                            }
                        }
                    }
                }
            }
        }
    });
}

// Initialize rule displays
function initializeRuleDisplays() {
    RuleBuilder.initializeRuleDisplays();
}

// Add form serialization for section modal
function initializeSectionFormSerialization() {
    // Handle section modal form submission
    const sectionForm = Utils.getElementById('section-form');
    if (sectionForm) {
        sectionForm.addEventListener('submit', function(e) {
            const relevanceRuleBuilder = document.querySelector('#section-relevance-rule-builder');
            const relevanceConditionInput = Utils.getElementById('section-relevance-condition');

            if (relevanceRuleBuilder && relevanceConditionInput) {
                const value = serializeRuleForSubmit(relevanceRuleBuilder);
                relevanceConditionInput.value = value || '';
            }
        });
    }
}

// Modal helper functions

// Stored on first init so we can restore picker title when switching back from change_type
let itemTypePickerTitleOriginalHtml = '';

// Item type picker: show modal with section context; tile click opens item config or changes type
// context: 'add' = adding new item (tile opens item modal); 'change_type' = item modal open (tile switches type)
function showItemTypePickerModal(sectionId, sectionName, context) {
    const modal = Utils.getElementById('item-type-picker-modal');
    const titleEl = modal ? modal.querySelector('#item-type-picker-title') : null;
    const sectionIdInput = Utils.getElementById('item-type-picker-section-id');
    const sectionNameInput = Utils.getElementById('item-type-picker-section-name-input');
    if (!modal || !sectionIdInput) return;
    context = context || 'add';
    modal.setAttribute('data-picker-context', context);
    sectionIdInput.value = sectionId || '';
    if (sectionNameInput) sectionNameInput.value = sectionName || '';
    if (context === 'change_type') {
        if (titleEl) titleEl.textContent = (typeof _ !== 'undefined' && _('Change item type')) ? _('Change item type') : 'Change item type';
    } else {
        if (titleEl && itemTypePickerTitleOriginalHtml) {
            titleEl.innerHTML = itemTypePickerTitleOriginalHtml;
            const sectionNameEl = document.getElementById('item-type-picker-section-name');
            if (sectionNameEl) sectionNameEl.textContent = sectionName || '';
        }
    }
    Utils.showElement(modal);
}

function closeItemTypePickerModal() {
    const modal = Utils.getElementById('item-type-picker-modal');
    if (modal) Utils.hideElement(modal);
    hideItemTypePickerTooltip();
}

function hideItemTypePickerTooltip() {
    const tooltip = Utils.getElementById('item-type-picker-tooltip');
    if (tooltip) {
        tooltip.classList.remove('is-visible');
        tooltip.setAttribute('aria-hidden', 'true');
    }
}

function initializeItemTypePickerModal() {
    const modal = Utils.getElementById('item-type-picker-modal');
    const tooltip = Utils.getElementById('item-type-picker-tooltip');
    const tooltipText = tooltip ? tooltip.querySelector('.item-type-picker-tooltip__body') : null;
    const titleEl = modal ? modal.querySelector('#item-type-picker-title') : null;
    if (!modal || !tooltip || !tooltipText) return;
    if (titleEl && !itemTypePickerTitleOriginalHtml) itemTypePickerTitleOriginalHtml = titleEl.innerHTML;

    modal.querySelectorAll('.item-type-picker-close').forEach(btn => {
        btn.addEventListener('click', closeItemTypePickerModal);
    });
    modal.addEventListener('click', function(e) {
        if (e.target === modal) closeItemTypePickerModal();
    });

    const TOOLTIP_GAP = 8;
    const TOOLTIP_HEIGHT_ESTIMATE = 100;

    modal.querySelectorAll('.item-type-tile').forEach(tile => {
        tile.addEventListener('mouseenter', function() {
            const copyEl = this.querySelector('.item-type-tooltip-copy');
            const text = copyEl ? (copyEl.textContent || '').trim() : '';
            if (!text) return;
            tooltipText.textContent = text;
            const rect = this.getBoundingClientRect();
            const centerX = rect.left + rect.width / 2;
            const showAbove = (rect.bottom + TOOLTIP_HEIGHT_ESTIMATE + TOOLTIP_GAP) > window.innerHeight;

            tooltip.style.left = centerX + 'px';
            tooltip.style.top = '';
            tooltip.style.bottom = '';
            if (showAbove) {
                tooltip.style.bottom = (window.innerHeight - rect.top + TOOLTIP_GAP) + 'px';
                tooltip.classList.remove('is-below');
                tooltip.classList.add('is-above');
            } else {
                tooltip.style.top = (rect.bottom + TOOLTIP_GAP) + 'px';
                tooltip.classList.remove('is-above');
                tooltip.classList.add('is-below');
            }
            tooltip.classList.add('is-visible');
            tooltip.setAttribute('aria-hidden', 'false');
        });

        tile.addEventListener('mouseleave', function() {
            hideItemTypePickerTooltip();
        });

        tile.addEventListener('click', function(e) {
            e.preventDefault();
            const itemType = this.getAttribute('data-item-type');
            const questionType = this.getAttribute('data-question-type');
            const context = modal.getAttribute('data-picker-context') || 'add';
            closeItemTypePickerModal();
            if (context === 'change_type') {
                if (itemType) {
                    ItemModal.switchItemType(itemType, questionType || null);
                    if (ItemModal.syncSharedToUI) setTimeout(() => ItemModal.syncSharedToUI(), 50);
                }
                return;
            }
            const sectionIdInput = Utils.getElementById('item-type-picker-section-id');
            const sectionNameInput = Utils.getElementById('item-type-picker-section-name-input');
            const sectionNameEl = Utils.getElementById('item-type-picker-section-name');
            const sectionId = sectionIdInput ? sectionIdInput.value : '';
            const sectionName = (sectionNameInput && sectionNameInput.value) ? sectionNameInput.value : (sectionNameEl ? sectionNameEl.textContent : '');
            if (sectionId && itemType) {
                ItemModal.showAddModal(sectionId, sectionName, itemType, questionType || null);
            }
        });
    });
}

function showAddItemModal(sectionId, sectionName, itemType) {
    const modal = Utils.getElementById('add-item-modal');
    const sectionNameElement = Utils.getElementById('add-item-modal-section-name');
    const sectionIdInput = Utils.getElementById('add_item_modal_actual_section_id');

    if (modal && sectionNameElement && sectionIdInput) {
        sectionNameElement.textContent = sectionName;
        sectionIdInput.value = sectionId;
        Utils.showElement(modal);
    }
}

function showAddDocumentFieldModal(sectionId, sectionName) {
    const modal = Utils.getElementById('add-document-field-modal');
    const sectionNameElement = Utils.getElementById('add-document-field-modal-section-name');
    const sectionIdInput = Utils.getElementById('add_document_field_modal_actual_section_id');

    if (modal && sectionNameElement && sectionIdInput) {
        sectionNameElement.textContent = sectionName;
        sectionIdInput.value = sectionId;
        Utils.showElement(modal);
    }
}

function showSectionModal(mode, sectionData = null) {
    const modal = Utils.getElementById('section-modal');
    const form = Utils.getElementById('section-form');
    const title = Utils.getElementById('section-modal-text');
    const icon = Utils.getElementById('section-modal-icon');
    const submitBtn = Utils.getElementById('section-submit-btn');
    const nameInput = Utils.getElementById('section-name-input');
    const orderInput = Utils.getElementById('section-order-input');
    const pageInput = document.getElementById('section-page-id-input');
    const typeRadios = modal.querySelectorAll('input[name="section-section_type"]');
    const translationsInput = Utils.getElementById('section-name-translations');
    const relevanceConditionInput = Utils.getElementById('section-relevance-condition');
    const relevanceRuleSection = Utils.getElementById('section-relevance-rule-section');
    const relevanceRuleBtn = modal.querySelector('[data-target="#section-relevance-rule-section"]');
    const parentSectionIdInput = Utils.getElementById('section-parent-section-id'); // now a select

    if (!modal || !form || !nameInput || !orderInput) {
        return;
    }

    // Enforce integer-only section order in the UI (no decimals)
    if (!orderInput.dataset.integerOnlyWired) {
        orderInput.dataset.integerOnlyWired = 'true';
        const normalizeInteger = (value) => {
            const s = String(value ?? '').trim();
            if (!s) return '';
            // Strip everything after a decimal separator, then keep digits only
            const noDecimal = s.split(/[.,]/, 1)[0];
            const digits = noDecimal.replace(/[^\d]/g, '');
            if (!digits) return '';
            let n = parseInt(digits, 10);
            if (Number.isNaN(n)) return '';
            if (n < 0) n = 0;
            return String(n);
        };

        orderInput.addEventListener('input', () => {
            const next = normalizeInteger(orderInput.value);
            if (orderInput.value !== next) orderInput.value = next;
        });
        orderInput.addEventListener('blur', () => {
            orderInput.value = normalizeInteger(orderInput.value);
        });
        orderInput.addEventListener('paste', () => {
            // Let paste happen, then normalize
            setTimeout(() => {
                orderInput.value = normalizeInteger(orderInput.value);
            }, 0);
        });
    }

    // Track current mode on modal so shared handlers don't capture stale closures
    try {
        modal.dataset.sectionModalMode = mode;
    } catch (_e) {
        // no-op
    }

    // Reset modal state
    Utils.hideElement(relevanceRuleSection);
    if (relevanceRuleBtn) {
        relevanceRuleBtn.replaceChildren();
        {
            const iconEl = document.createElement('i');
            iconEl.className = 'fas fa-plus-circle mr-1';
            relevanceRuleBtn.append(iconEl, document.createTextNode(' Add Relevance Rule'));
        }
    }

    // Hide the right half initially
    const modalGrid = modal.querySelector('.modal-grid-container');
    if (modalGrid) {
        modalGrid.classList.remove('md:grid-cols-2');
        const rightHalf = modal.querySelector('.modal-right-half');
        if (rightHalf) {
            Utils.hideElement(rightHalf);
        }
        // Reset modal width
        const modalContent = modal.querySelector('.relative.p-6');
        if (modalContent) {
            modalContent.classList.remove('max-w-lg', 'max-w-4xl', 'max-w-6xl');
            modalContent.classList.add('max-w-xl');
        }
    }

    // Populate parent section dropdown every time (sections may have changed)
    const currentSectionId = sectionData && sectionData.id ? sectionData.id : null;
    const selectedParentId = sectionData && sectionData.parent_section_id ? sectionData.parent_section_id : '';
    populateSectionParentDropdown({ currentSectionId, selectedParentId });

    // Reset page field state (re-enable and hide subsection hint) so we can apply subsection logic when needed
    const pageFieldWrapper = document.getElementById('section-page-field-wrapper');
    const pageInheritedHint = document.getElementById('section-page-inherited-hint');
    if (pageInput) {
        pageInput.disabled = false;
        pageInput.removeAttribute('title');
    }
    const existingHidden = document.getElementById('section-page-id-hidden');
    if (existingHidden) {
        existingHidden.remove();
    }
    if (pageFieldWrapper) {
        pageFieldWrapper.removeAttribute('title');
    }
    if (pageInheritedHint) {
        Utils.hideElement(pageInheritedHint);
    }

    // Wire dropdown change behavior once
    if (parentSectionIdInput && !parentSectionIdInput.dataset.sectionParentWired) {
        parentSectionIdInput.dataset.sectionParentWired = 'true';
        parentSectionIdInput.addEventListener('change', () => {
            const isAddMode = (modal && modal.dataset && modal.dataset.sectionModalMode === 'add');
            const hasParent = (parentSectionIdInput.value || '').trim().length > 0;

            // Update modal chrome to reflect whether this is a subsection
            if (title && icon && submitBtn) {
                if (isAddMode) {
                    if (hasParent) {
                        title.textContent = 'Add Subsection';
                        icon.className = 'fas fa-indent w-6 h-6 mr-2 text-teal-600';
                        submitBtn.textContent = 'Add Subsection';
                        submitBtn.className = 'btn btn-success';
                    } else {
                        title.textContent = 'Add Section';
                        icon.className = 'fas fa-plus-circle w-6 h-6 mr-2 text-sky-600';
                        submitBtn.textContent = 'Add Section';
                        submitBtn.className = 'btn btn-success';
                    }
                }
            }

            // In add mode, auto-pick next integer order for the selected context
            if (isAddMode) {
                const pid = (parentSectionIdInput.value || '').trim();
                orderInput.value = pid ? calculateNextChildSectionOrder(pid) : calculateNextSectionOrder();
            }
        });
    }

    if (mode === 'add') {
        const isSubsection = parentSectionIdInput && parentSectionIdInput.value;

        // Configure for add mode
        if (isSubsection) {
            title.textContent = 'Add Subsection';
            icon.className = 'fas fa-indent w-6 h-6 mr-2 text-teal-600';
        } else {
            title.textContent = 'Add Section';
            icon.className = 'fas fa-plus-circle w-6 h-6 mr-2 text-sky-600';
        }

        // Get the template ID from the window object or form action
        const templateId = window.templateId || new URLSearchParams(window.location.search).get('template_id');
        if (templateId) {
            form.action = `/admin/templates/${templateId}/sections/new`;
        }

        if (isSubsection) {
            submitBtn.textContent = 'Add Subsection';
            submitBtn.className = 'btn btn-success';
        } else {
            submitBtn.textContent = 'Add Section';
            submitBtn.className = 'btn btn-success';
        }

        // Clear form fields
        nameInput.value = '';
        // Always default to integer orders
        if (parentSectionIdInput && parentSectionIdInput.value) {
            orderInput.value = calculateNextChildSectionOrder(parentSectionIdInput.value);
        } else {
            orderInput.value = calculateNextSectionOrder();
        }
        if (pageInput) {
            // If subsection has a page_id, use it; otherwise reset to first option
            if (isSubsection && sectionData.page_id) {
                pageInput.value = sectionData.page_id;
            } else {
                pageInput.selectedIndex = 0;
            }
        }

        // Reset translations
        if (translationsInput) {
            translationsInput.value = '{}';
        }

        // Reset section type to standard
        typeRadios.forEach(radio => {
            radio.checked = radio.value === 'standard';
        });

        // Hide max_entries field for new sections
        const maxEntriesContainer = Utils.getElementById('repeat-group-config');
        const maxEntriesInput = Utils.getElementById('section-max-entries-input');
        if (maxEntriesContainer) {
            Utils.hideElement(maxEntriesContainer);
        }
        if (maxEntriesInput) {
            maxEntriesInput.value = '';
        }

        // Clear relevance condition
        if (relevanceConditionInput) {
            relevanceConditionInput.value = '';
        }

        // Clear rule builder initialization
        if (relevanceRuleSection) {
            relevanceRuleSection.removeAttribute('data-initialized');
            const ruleBuilder = relevanceRuleSection.querySelector('#section-relevance-rule-builder');
            if (ruleBuilder) {
                ruleBuilder.replaceChildren();
            }
        }

    } else if (mode === 'edit' && sectionData) {
        // Configure for edit mode
        title.textContent = 'Edit Section';
        icon.className = 'fas fa-pen w-6 h-6 mr-2 text-blue-600';
        form.action = `/admin/sections/edit/${sectionData.id}`;
        submitBtn.textContent = 'Save Changes';
        submitBtn.className = 'btn btn-success';

        // Populate form fields with existing data
        nameInput.value = sectionData.name || '';
        // Clean integer-only setup:
        // - We do NOT infer parents from decimals anymore.
        // - The backend should store subsections with parent_section_id set and order as a whole number (child order).
        // - If a float sneaks through (e.g. "3.0"), we still display it as "3".
        const rawOrder = (sectionData.order ?? '').toString().trim();
        const n = parseInt(rawOrder, 10);
        orderInput.value = Number.isNaN(n) ? '' : String(Math.max(0, n));
        // Run the integer-only normalizer (handles pasted/odd strings)
        try { orderInput.dispatchEvent(new Event('input', { bubbles: true })); } catch (_e) {}

        // Set page: use section's page_id or parent's page (subsections inherit parent page)
        if (pageInput) {
            const effectivePageId = sectionData.page_id || sectionData.parent_page_id || '';
            if (effectivePageId) {
                pageInput.value = effectivePageId;
            }
        }

        // Set translations if they exist
        if (translationsInput && sectionData.name_translations) {
            try {
                const translations = typeof sectionData.name_translations === 'string'
                    ? JSON.parse(sectionData.name_translations)
                    : sectionData.name_translations;
                translationsInput.value = JSON.stringify(translations);
            } catch (e) {
                translationsInput.value = '{}';
            }
        } else if (translationsInput) {
            translationsInput.value = '{}';
        }

        // Map section type enum values to radio button values
        let radioValue = sectionData.section_type;
        if (sectionData.section_type === 'Dynamic Indicators') {
            radioValue = 'dynamic_indicators';
        } else if (sectionData.section_type === 'Standard') {
            radioValue = 'standard';
        } else if (sectionData.section_type === 'Repeat') {
            radioValue = 'repeat';
        } else {
            radioValue = 'standard';
        }

        // Set the correct radio button
        typeRadios.forEach(radio => {
            radio.checked = radio.value === radioValue;
        });

        // Show/hide max_entries field based on section type
        const maxEntriesContainer = Utils.getElementById('repeat-group-config');
        const maxEntriesInput = Utils.getElementById('section-max-entries-input');
        if (maxEntriesContainer && maxEntriesInput) {
            if (radioValue === 'repeat') {
                Utils.showElement(maxEntriesContainer);
                // Populate max_entries if editing
                if (sectionData.max_entries) {
                    maxEntriesInput.value = sectionData.max_entries;
                } else {
                    maxEntriesInput.value = '';
                }
            } else {
                Utils.hideElement(maxEntriesContainer);
                maxEntriesInput.value = '';
            }
        }

        // Handle relevance condition for section skip logic
        if (relevanceConditionInput && relevanceRuleSection && relevanceRuleBtn) {
            if (sectionData.relevance_condition && sectionData.relevance_condition.trim()) {
                // Populate existing relevance condition in hidden input
                relevanceConditionInput.value = sectionData.relevance_condition;

                // Show the rule section and update button text for existing rules
                Utils.showElement(relevanceRuleSection);
                relevanceRuleBtn.replaceChildren();
                {
                    const iconEl = document.createElement('i');
                    iconEl.className = 'fas fa-minus-circle mr-1';
                    relevanceRuleBtn.append(iconEl, document.createTextNode(' Hide Relevance Rule'));
                }

                // Show the right half and switch to two-column layout for the modal
                if (modalGrid) {
                    const rightHalf = modal.querySelector('.modal-right-half');
                    if (rightHalf) {
                        Utils.showElement(rightHalf);
                        modalGrid.classList.add('md:grid-cols-2');
                        // Expand modal width when rule section is shown
                        const modalContent = modal.querySelector('.relative.p-6');
                        if (modalContent) {
                            modalContent.classList.remove('max-w-lg', 'max-w-xl', 'max-w-4xl');
                            modalContent.classList.add('max-w-6xl');
                        }
                    }
                }

                // Initialize and populate the rule builder with existing data
                const ruleBuilder = relevanceRuleSection.querySelector('#section-relevance-rule-builder');
                if (ruleBuilder) {
                    // Set the data attribute and initialize immediately
                    ruleBuilder.setAttribute('data-rule-json', sectionData.relevance_condition);
                    RuleBuilder.renderRuleBuilder(ruleBuilder, sectionData.relevance_condition, 'relevance');
                    relevanceRuleSection.setAttribute('data-initialized', 'true');
                }
            } else {
                // No existing relevance condition
                relevanceConditionInput.value = '';
                Utils.hideElement(relevanceRuleSection);
                relevanceRuleBtn.replaceChildren();
                {
                    const iconEl = document.createElement('i');
                    iconEl.className = 'fas fa-plus-circle mr-1';
                    relevanceRuleBtn.append(iconEl, document.createTextNode(' Add Relevance Rule'));
                }

                // Clear the rule builder initialization
                relevanceRuleSection.removeAttribute('data-initialized');
                const ruleBuilder = relevanceRuleSection.querySelector('#section-relevance-rule-builder');
                if (ruleBuilder) {
                    ruleBuilder.replaceChildren();
                    ruleBuilder.removeAttribute('data-rule-json');
                }
            }
        }
    }

    // When editing or adding a subsection, make Page read-only and show tooltip (page is inherited from parent)
    const isSubsection = (mode === 'add' && parentSectionIdInput && (parentSectionIdInput.value || '').trim().length > 0) ||
        (mode === 'edit' && sectionData && (sectionData.parent_section_id || '').toString().trim().length > 0);
    if (isSubsection && pageInput) {
        const effectivePageId = (sectionData && (sectionData.page_id || sectionData.parent_page_id)) || (parentSectionIdInput && pageInput.value) || '';
        if (effectivePageId) {
            pageInput.value = effectivePageId;
        }
        pageInput.disabled = true;
        pageInput.setAttribute('title', 'Page is inherited from the parent section.');
        const hiddenInput = document.createElement('input');
        hiddenInput.type = 'hidden';
        hiddenInput.name = 'section-page_id';
        hiddenInput.id = 'section-page-id-hidden';
        hiddenInput.value = pageInput.value;
        form.appendChild(hiddenInput);
        if (pageFieldWrapper) {
            pageFieldWrapper.setAttribute('title', 'Page is inherited from the parent section.');
        }
        if (pageInheritedHint) {
            Utils.showElement(pageInheritedHint);
        }
    }

    Utils.showElement(modal);
}

// Legacy edit modal helpers removed - item modal handles editing

function closeAllModals() {
    const modals = document.querySelectorAll('.fixed.inset-0.bg-gray-800');
    modals.forEach(modal => {
        Utils.hideElement(modal);
    });
}

// Item modal handler - wrapper for ItemModal module
function showItemModal(mode, sectionId, sectionName, itemType = 'indicator', itemData = null, initialQuestionType = null) {
    if (mode === 'add') {
        ItemModal.showAddModal(sectionId, sectionName, itemType, initialQuestionType);
    } else if (mode === 'edit') {
        ItemModal.showEditModal(itemData.id, itemType, itemData);
    }
}

// Switch item type fields - wrapper for ItemModal
function switchItemTypeFields(itemType) {
    ItemModal.switchItemType(itemType);
}

// Helper functions are now provided by ItemModal module

// Additional helper functions for template compatibility

// Toggle options input visibility for question types
function toggleOptionsInputVisibility(questionType, optionsContainer, optionsInput) {
    const questionTypesRequiringOptions = ['single_choice', 'multiple_choice'];

    if (questionTypesRequiringOptions.includes(questionType)) {
        if (optionsContainer) {
            Utils.showElement(optionsContainer);
        }
        if (optionsInput) {
            optionsInput.required = true;
        }
    } else {
        if (optionsContainer) {
            Utils.hideElement(optionsContainer);
        }
        if (optionsInput) {
            optionsInput.required = false;
            optionsInput.value = '';
        }
    }
}

// Toggle disaggregation fields visibility
function toggleDisaggregationFieldsVisibility(selectedUnit, disaggOptionsWrapper, ageGroupsWrapper, checkboxes, selectedType) {
    const shouldShowDisaggregation = selectedUnit &&
                                   (selectedUnit.toLowerCase().includes('number') ||
                                    selectedUnit.toLowerCase().includes('count') ||
                                    selectedUnit.toLowerCase().includes('percentage') ||
                                    selectedType === 'Number' ||
                                    selectedType === 'Count' ||
                                    selectedType === 'Percentage');

    if (disaggOptionsWrapper) {
        if (shouldShowDisaggregation) {
            Utils.showElement(disaggOptionsWrapper);
        } else {
            Utils.hideElement(disaggOptionsWrapper);
            // Uncheck all disaggregation checkboxes if hiding options
            if (checkboxes) {
                checkboxes.forEach(cb => {
                    if (cb.value !== 'total') {
                        cb.checked = false;
                    }
                });
            }
        }
    }

    // Show/hide age groups based on checkbox selections
    if (ageGroupsWrapper && checkboxes) {
        toggleAgeGroupsVisibilityOnCheckboxChange(checkboxes, ageGroupsWrapper);
    }
}

// Toggle age groups visibility on checkbox change
function toggleAgeGroupsVisibilityOnCheckboxChange(checkboxesArray, ageGroupsWrapper) {
    const ageGroupsCheckbox = Array.from(checkboxesArray).find(cb => cb.value === 'age_groups');
    if (ageGroupsCheckbox && ageGroupsWrapper) {
        if (ageGroupsCheckbox.checked) {
            Utils.showElement(ageGroupsWrapper);
        } else {
            Utils.hideElement(ageGroupsWrapper);
        }
    }
}

// Export main functions for global access
window.showItemModal = showItemModal;
window.showAddItemModal = showAddItemModal;
window.showAddDocumentFieldModal = showAddDocumentFieldModal;
window.showSectionModal = showSectionModal;
window.closeAllModals = closeAllModals;
window.toggleOptionsInputVisibility = toggleOptionsInputVisibility;
window.toggleDisaggregationFieldsVisibility = toggleDisaggregationFieldsVisibility;
window.ItemModal = ItemModal;

// Test function for debugging matrix functionality
window.testMatrix = function() {
    if (typeof ItemModal !== 'undefined') {
        ItemModal.switchItemType('matrix');
    }
};
window.toggleAgeGroupsVisibilityOnCheckboxChange = toggleAgeGroupsVisibilityOnCheckboxChange;
window.initializeRuleDisplays = initializeRuleDisplays;
window.addOptionField = addOptionField;
window.updateOptionsJson = updateOptionsJson;
window.initializeOptionsFromJson = initializeOptionsFromJson;
