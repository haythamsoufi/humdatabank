// translation-page.js - Wires translation components on the form builder page

import { TranslationModal } from '/static/js/components/translation-modal.js';
import { TranslationMatrix } from '/static/js/components/translation-matrix.js';
import '/static/js/components/translation-utils.js';

function attachQuestionModal() {
  if (!window.TranslationModal || !document.getElementById('question-translations-btn')) return;
  window.TranslationModal.attach({
    openButtonId: 'question-translations-btn',
    modalId: 'translation-modal',
    cssPrefix: 'translation',
    resolveEnglishText: () => (document.getElementById('item-question-label')?.value || ''),
    // Provide per-tab resolvers
    resolveTextsByTab: () => ({
      labels: document.getElementById('item-question-label')?.value || '',
      definitions: document.getElementById('item-question-definition')?.value || ''
    }),
    onSaveHiddenFields: (collectedByTab) => {
      const translationsInput = document.getElementById('item-modal-shared-label-translations');
      const definitionTranslationsInput = document.getElementById('item-modal-definition-translations');
      if (translationsInput) translationsInput.value = JSON.stringify(collectedByTab.labels || {});
      if (definitionTranslationsInput) definitionTranslationsInput.value = JSON.stringify(collectedByTab.definitions || {});
      const translationBtn = document.getElementById('question-translations-btn');
      if (translationBtn) {
        const originalNodes = Array.from(translationBtn.childNodes).map((n) => n.cloneNode(true));
        const restore = () => {
          translationBtn.replaceChildren(...originalNodes.map((n) => n.cloneNode(true)));
        };
        translationBtn.replaceChildren();
        {
          const icon = document.createElement('i');
          icon.className = 'fas fa-check w-4 h-4 mr-1';
          translationBtn.append(icon, document.createTextNode('Saved'));
        }
        translationBtn.classList.add('text-green-600');
        setTimeout(() => { restore(); translationBtn.classList.remove('text-green-600'); }, 2000);
      }
    },
    autoTranslateType: 'form_item',
    tabSuffixes: ['labels', 'definitions'],
    defaultTabSuffix: 'labels',
    // Add custom logic to load existing translations when modal opens
    onModalOpen: () => {
      // Load existing translations from hidden inputs
      const labelTranslationsInput = document.getElementById('item-modal-shared-label-translations');
      const definitionTranslationsInput = document.getElementById('item-modal-definition-translations');

      let labelTranslations = {};
      let definitionTranslations = {};

      if (labelTranslationsInput && labelTranslationsInput.value) {
        try {
          labelTranslations = JSON.parse(labelTranslationsInput.value);
        } catch (e) {
          console.warn('Failed to parse label translations:', e);
        }
      }

      if (definitionTranslationsInput && definitionTranslationsInput.value) {
        try {
          definitionTranslations = JSON.parse(definitionTranslationsInput.value);
        } catch (e) {
          console.warn('Failed to parse definition translations:', e);
        }
      }

      // Populate the modal fields with existing translations
      if (window.TranslationModalUtils) {
        window.TranslationModalUtils.populateFields('translation', labelTranslations, '', 'labels');
        window.TranslationModalUtils.populateFields('translation', definitionTranslations, '', 'definitions');
      }
    }
  });
}

function attachIndicatorModal() {
  if (!window.TranslationModal || !document.getElementById('indicator-translations-btn')) return;
  window.TranslationModal.attach({
    openButtonId: 'indicator-translations-btn',
    modalId: 'translation-modal',
    cssPrefix: 'translation',
    resolveEnglishText: () => (document.getElementById('item-indicator-label')?.value || ''),
    resolveTextsByTab: () => ({
      labels: document.getElementById('item-indicator-label')?.value || '',
      definitions: document.getElementById('item-indicator-definition')?.value || ''
    }),
    onSaveHiddenFields: (collectedByTab) => {
      const labelTranslationsInput = document.getElementById('item-modal-shared-label-translations');
      const definitionTranslationsInput = document.getElementById('item-modal-definition-translations');
      if (labelTranslationsInput) labelTranslationsInput.value = JSON.stringify(collectedByTab.labels || {});
      if (definitionTranslationsInput) definitionTranslationsInput.value = JSON.stringify(collectedByTab.definitions || {});
      const btn = document.getElementById('indicator-translations-btn');
      if (btn) {
        const originalNodes = Array.from(btn.childNodes).map((n) => n.cloneNode(true));
        const restore = () => {
          btn.replaceChildren(...originalNodes.map((n) => n.cloneNode(true)));
        };
        btn.replaceChildren();
        {
          const icon = document.createElement('i');
          icon.className = 'fas fa-check w-4 h-4 mr-1';
          btn.append(icon, document.createTextNode('Saved'));
        }
        btn.classList.add('text-green-600');
        setTimeout(() => { restore(); btn.classList.remove('text-green-600'); }, 2000);
      }
    },
    autoTranslateType: 'form_item',
    tabSuffixes: ['labels', 'definitions'],
    defaultTabSuffix: 'labels',
    onModalOpen: () => {
      const labelTranslationsInput = document.getElementById('item-modal-shared-label-translations');
      const definitionTranslationsInput = document.getElementById('item-modal-definition-translations');
      let labelTranslations = {};
      let definitionTranslations = {};
      if (labelTranslationsInput && labelTranslationsInput.value) {
        try { labelTranslations = JSON.parse(labelTranslationsInput.value); } catch(e) {}
      }
      if (definitionTranslationsInput && definitionTranslationsInput.value) {
        try { definitionTranslations = JSON.parse(definitionTranslationsInput.value); } catch(e) {}
      }
      if (window.TranslationModalUtils) {
        window.TranslationModalUtils.populateFields('translation', labelTranslations, '', 'labels');
        window.TranslationModalUtils.populateFields('translation', definitionTranslations, '', 'definitions');
      }
    }
  });
}

function attachSectionModal() {
  if (!window.TranslationModal || !document.getElementById('section-translation-modal')) return;
  window.TranslationModal.attach({
    openButtonId: 'section-name-translations-btn',
    modalId: 'section-translation-modal',
    cssPrefix: 'section',
    hiddenInputSelector: 'input#section-name-translations',
    resolveEnglishText: () => (document.getElementById('section-name-input')?.value || ''),
    autoTranslateType: 'section_name'
  });
}

function attachTemplateNameModal() {
  if (!window.TranslationModal || !document.getElementById('template-name-translations-modal')) return;

  const readJson = window.readJson || function readJson(elementId, fallback) {
    try {
      const el = document.getElementById(elementId);
      if (!el || !el.textContent) return fallback;
      return JSON.parse(el.textContent);
    } catch (e) {
      return fallback;
    }
  };

  // Get existing translations from JavaScript data
  const templateData = readJson('template-data', {});
  const existingTranslations = templateData.templateNameTranslations || {};

  window.TranslationModal.attach({
    openButtonId: 'template-name-translations-btn',
    modalId: 'template-name-translations-modal',
    cssPrefix: 'template-name',
    hiddenInputSelector: 'input#template-name-translations',
    resolveEnglishText: () => (document.querySelector('#template-details-form input[name="name"]')?.value || ''),
    onSaveHiddenFields: (collected) => {
      // Update the consolidated hidden field with ISO code keyed translations
      const hiddenField = document.getElementById('template-name-translations');
      if (hiddenField) {
        hiddenField.value = JSON.stringify(collected);
      }
    },
    onModalOpen: () => {
      // Load existing translations from JavaScript data
      if (window.TranslationModalUtils && existingTranslations) {
        window.TranslationModalUtils.populateFields('template-name', existingTranslations);
      }
    },
    autoTranslateType: 'template_name'
  });
}

function attachDocumentModal() {
  if (!window.TranslationModal || !document.getElementById('document-translation-modal')) return;
  window.TranslationModal.attach({
    openButtonId: 'document-translations-btn',
    modalId: 'document-translation-modal',
    cssPrefix: 'document',
    resolveEnglishText: () => (document.getElementById('item-document-label')?.value || ''),
    onSaveHiddenFields: (collectedByTab) => {
      const labelTranslationsInput = document.getElementById('item-modal-shared-label-translations');
      const descriptionTranslationsInput = document.getElementById('item-modal-shared-description-translations');
      if (labelTranslationsInput) labelTranslationsInput.value = JSON.stringify(collectedByTab.labels || {});
      if (descriptionTranslationsInput) descriptionTranslationsInput.value = JSON.stringify(collectedByTab.descriptions || {});
    },
    autoTranslateType: 'document_field',
    tabSuffixes: ['labels', 'descriptions'],
    defaultTabSuffix: 'labels',
    onModalOpen: () => {
      // Load existing translations from shared hidden inputs
      const labelTranslationsInput = document.getElementById('item-modal-shared-label-translations');
      const descriptionTranslationsInput = document.getElementById('item-modal-shared-description-translations');

      let labelTranslations = {};
      let descriptionTranslations = {};

      if (labelTranslationsInput && labelTranslationsInput.value) {
        try { labelTranslations = JSON.parse(labelTranslationsInput.value); } catch (_e) {}
      }
      if (descriptionTranslationsInput && descriptionTranslationsInput.value) {
        try { descriptionTranslations = JSON.parse(descriptionTranslationsInput.value); } catch (_e) {}
      }

      if (window.TranslationModalUtils) {
        window.TranslationModalUtils.populateFields('document', labelTranslations, '', 'labels');
        window.TranslationModalUtils.populateFields('document', descriptionTranslations, '', 'descriptions');
      }
    }
  });
}

function attachMatrixLabelModal() {
  // Use dedicated matrix translation modal
  if (!window.TranslationModal || !document.getElementById('matrix-translations-btn')) return;
  window.TranslationModal.attach({
    openButtonId: 'matrix-translations-btn',
    modalId: 'matrix-translation-modal',
    cssPrefix: 'matrix',
    resolveEnglishText: () => (document.getElementById('item-matrix-label')?.value || ''),
    onSaveHiddenFields: (collectedByTab) => {
      const labelTranslationsInput = document.getElementById('item-modal-shared-label-translations');
      const descriptionTranslationsInput = document.getElementById('item-modal-shared-description-translations');
      if (labelTranslationsInput) labelTranslationsInput.value = JSON.stringify(collectedByTab.labels || {});
      if (descriptionTranslationsInput) descriptionTranslationsInput.value = JSON.stringify(collectedByTab.descriptions || {});
    },
    autoTranslateType: 'form_item',
    tabSuffixes: ['labels', 'descriptions'],
    defaultTabSuffix: 'labels',
    onModalOpen: () => {
      // Load existing translations from shared hidden inputs
      const labelTranslationsInput = document.getElementById('item-modal-shared-label-translations');
      const descriptionTranslationsInput = document.getElementById('item-modal-shared-description-translations');

      let labelTranslations = {};
      let descriptionTranslations = {};

      if (labelTranslationsInput && labelTranslationsInput.value) {
        try { labelTranslations = JSON.parse(labelTranslationsInput.value); } catch (_e) {}
      }
      if (descriptionTranslationsInput && descriptionTranslationsInput.value) {
        try { descriptionTranslations = JSON.parse(descriptionTranslationsInput.value); } catch (_e) {}
      }

      if (window.TranslationModalUtils) {
        window.TranslationModalUtils.populateFields('matrix', labelTranslations, '', 'labels');
        window.TranslationModalUtils.populateFields('matrix', descriptionTranslations, '', 'descriptions');
      }
    }
  });
}

function attachMatrixLegendTextModal() {
  // Translation modal for matrix legend text
  if (!window.TranslationModal || !document.getElementById('matrix-legend-text-translations-btn')) return;
  window.TranslationModal.attach({
    openButtonId: 'matrix-legend-text-translations-btn',
    modalId: 'matrix-legend-text-translation-modal',
    cssPrefix: 'matrix-legend-text',
    resolveEnglishText: () => (document.getElementById('matrix-legend-text')?.value || 'Manually added row'),
    onSaveHiddenFields: (collected) => {
      const legendTextTranslationsInput = document.getElementById('matrix-legend-text-translations');
      if (legendTextTranslationsInput) {
        // Store translations (no tabs, just direct translations)
        legendTextTranslationsInput.value = JSON.stringify(collected || {});
      }
      const btn = document.getElementById('matrix-legend-text-translations-btn');
      if (btn) {
        const originalNodes = Array.from(btn.childNodes).map((n) => n.cloneNode(true));
        const restore = () => {
          btn.replaceChildren(...originalNodes.map((n) => n.cloneNode(true)));
        };
        btn.replaceChildren();
        {
          const icon = document.createElement('i');
          icon.className = 'fas fa-check w-4 h-4 mr-1';
          btn.append(icon, document.createTextNode('Saved'));
        }
        btn.classList.add('text-green-600');
        setTimeout(() => { restore(); btn.classList.remove('text-green-600'); }, 2000);
      }
    },
    autoTranslateType: 'form_item',
    onModalOpen: () => {
      const legendTextTranslationsInput = document.getElementById('matrix-legend-text-translations');
      let legendTextTranslations = {};
      if (legendTextTranslationsInput && legendTextTranslationsInput.value) {
        try {
          legendTextTranslations = JSON.parse(legendTextTranslationsInput.value);
        } catch (e) {
          console.warn('Failed to parse legend text translations:', e);
        }
      }
      if (window.TranslationModalUtils) {
        window.TranslationModalUtils.populateFields('matrix-legend-text', legendTextTranslations);
      }
    }
  });
}

function attachMatrixColumnHeadersModal() {
  // Matrix-style modal for all column headers (using TranslationMatrix.attachOptions pattern)
  if (!window.TranslationMatrix) return;

  const tryAttach = () => {
    const openBtn = document.getElementById('matrix-column-headers-translations-matrix-btn');
    const modal = document.getElementById('matrix-column-headers-translation-matrix-modal');
    if (!openBtn || !modal) return false;

    // Check if already attached
    if (openBtn.dataset.translationMatrixAttached === 'true') return true;

    // Use the same pattern as attachOptions but adapted for column headers
    const tbodyId = 'matrix-column-headers-translation-matrix-tbody';
    const saveBtnId = 'save-column-headers-matrix-btn';
    const cssPrefix = 'column-headers-matrix';
    const tbody = document.getElementById(tbodyId);
    const saveBtn = document.getElementById(saveBtnId);
    if (!tbody) return false;

    function generateCells(translations = {}) {
      // Manually create cells to ensure proper table structure (more reliable than HTML string parsing)
      if (!window.TranslationModalUtils) return '';
      const supportedLanguages = window.TranslationModalUtils.supportedLanguages || [];
      const languageDisplayNames = window.TranslationModalUtils.languageDisplayNames || {};
      const cells = [];
      supportedLanguages.filter(code => code !== 'en').forEach(code => {
        const cell = document.createElement('td');
        cell.className = 'px-4 py-2 border-r border-gray-300';
        const textarea = document.createElement('textarea');
        textarea.className = 'w-full text-sm border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500';
        textarea.rows = 2;
        textarea.setAttribute('data-language', code);
        const displayName = languageDisplayNames[code] || code.toUpperCase();
        textarea.placeholder = `${displayName} translation`;
        textarea.value = translations[code] || '';
        if (['ar','fa','he','ur'].includes(code)) {
          textarea.dir = 'rtl';
          textarea.style.fontFamily = "'Tajawal', Arial, sans-serif";
        }
        cell.appendChild(textarea);
        cells.push(cell);
      });
      return cells;
    }

    function populate() {
      const columnsContainer = document.getElementById('matrix-columns-container');
      if (!columnsContainer || !tbody) {
        console.warn('Matrix column headers modal: missing container or tbody', {
          hasContainer: !!columnsContainer,
          hasTbody: !!tbody
        });
        return;
      }
      tbody.replaceChildren();

      const columnDivs = columnsContainer.querySelectorAll('.matrix-column');

      if (columnDivs.length === 0) {
        // Show a message in the table if no columns
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.colSpan = 100; // Span all columns
        cell.className = 'px-4 py-3 text-sm text-gray-500 text-center';
        cell.textContent = 'No columns found. Please add at least one column header first.';
        row.appendChild(cell);
        tbody.appendChild(row);
        return;
      }

      columnDivs.forEach((columnDiv, index) => {
        const textInput = columnDiv.querySelector('.column-text');
        const translationsInput = columnDiv.querySelector('.column-name-translations');
        const columnText = textInput ? textInput.value.trim() : '';
        if (!columnText) return; // Skip empty columns

        let translations = {};
        if (translationsInput && translationsInput.value) {
          try {
            translations = JSON.parse(translationsInput.value) || {};
          } catch (e) {
            translations = {};
          }
        }

        const row = document.createElement('tr');
        row.className = 'border-b border-gray-200 hover:bg-gray-50';
        row.dataset.columnIndex = index;
        const textTd = document.createElement('td');
        textTd.className = 'px-4 py-3 text-sm font-medium text-gray-900 border-r border-gray-300';
        textTd.textContent = columnText;
        row.appendChild(textTd);

        const cells = generateCells(translations);
        if (cells && Array.isArray(cells)) {
          // Append each cell directly to the row
          cells.forEach(cell => {
            row.appendChild(cell);
          });
        }
        tbody.appendChild(row);
      });
    }

    openBtn.addEventListener('click', function() {
      populate();
      modal.classList.remove('hidden');
    });

    if (saveBtn) {
      saveBtn.addEventListener('click', function() {
        const columnsContainer = document.getElementById('matrix-columns-container');
        const columnDivs = columnsContainer ? columnsContainer.querySelectorAll('.matrix-column') : [];
        const matrixRows = document.querySelectorAll(`#${tbodyId} tr`);

        matrixRows.forEach((matrixRow, index) => {
          const columnDiv = columnDivs[index];
          if (!columnDiv) return;

          const translationsInput = columnDiv.querySelector('.column-name-translations');
          if (!translationsInput) return;

          const translations = {};
          const textareas = matrixRow.querySelectorAll('textarea[data-language]');
          textareas.forEach(textarea => {
            const language = textarea.dataset.language;
            const value = textarea.value.trim();
            if (value) translations[language] = value;
          });

          translationsInput.value = JSON.stringify(translations);
        });

        // Trigger matrix config update
        try {
          const columnsContainer = document.getElementById('matrix-columns-container');
          if (columnsContainer) {
            const firstInput = columnsContainer.querySelector('.column-text');
            if (firstInput) {
              firstInput.dispatchEvent(new Event('change', { bubbles: true }));
            }
          }
        } catch (_e) {}

        modal.classList.add('hidden');
      });
    }

    // Clear all translations
    const clearBtn = document.getElementById(`clear-${cssPrefix}-btn`);
    if (clearBtn) {
      clearBtn.addEventListener('click', function() {
        const matrixRows = document.querySelectorAll(`#${tbodyId} tr`);
        matrixRows.forEach(row => {
          const textareas = row.querySelectorAll('textarea[data-language]');
          textareas.forEach(textarea => {
            textarea.value = '';
          });
        });
      });
    }

    // Auto-translate all column headers
    const autoBtn = document.getElementById(`auto-translate-${cssPrefix}-btn`);
    if (autoBtn) {
      autoBtn.addEventListener('click', function() {
        const columnsContainer = document.getElementById('matrix-columns-container');
        const columnDivs = columnsContainer ? columnsContainer.querySelectorAll('.matrix-column') : [];
        if (columnDivs.length === 0) return;

        const permissionContext = (modal && modal.dataset && modal.dataset.autoTranslatePermissionContext) ? modal.dataset.autoTranslatePermissionContext : '';
        const permissionCode = (modal && modal.dataset && modal.dataset.autoTranslatePermissionCode) ? modal.dataset.autoTranslatePermissionCode : '';

        const originalNodes = Array.from(autoBtn.childNodes).map((n) => n.cloneNode(true));
        const restoreOriginal = () => {
          autoBtn.replaceChildren(...originalNodes.map((n) => n.cloneNode(true)));
        };
        autoBtn.replaceChildren();
        {
          const icon = document.createElement('i');
          icon.className = 'fas fa-spinner fa-spin w-4 h-4 mr-2';
          autoBtn.append(icon, document.createTextNode('Translating...'));
        }
        autoBtn.disabled = true;

        const columnTexts = Array.from(columnDivs).map(div => {
          const input = div.querySelector('.column-text');
          return input ? (input.value || '').trim() : '';
        }).filter(text => text.trim());

        if (columnTexts.length === 0) {
          restoreOriginal();
          autoBtn.disabled = false;
          return;
        }

        Promise.all(columnTexts.map(columnText =>
          (window.AutoTranslateService && typeof window.AutoTranslateService.translate === 'function'
            ? window.AutoTranslateService.translate({
                type: 'form_item',
                permission_context: permissionContext,
                permission_code: permissionCode,
                text: columnText,
                target_languages: window.TranslationModalUtils ? window.TranslationModalUtils.getTargetLanguages() : []
              })
            : Promise.reject(new Error('AutoTranslateService not loaded'))
          ).catch(() => null)
        )).then(results => {
          const tbody = document.getElementById(tbodyId);
          const matrixRows = tbody ? tbody.querySelectorAll('tr') : [];
          results.forEach((data, index) => {
            if (!data) return;
            const row = matrixRows[index];
            if (!row) return;
            const translations = (data.translations && data.translations.label_translations) || data.translations || {};
            const textareas = row.querySelectorAll('textarea[data-language]');
            textareas.forEach(textarea => {
              const lang = textarea.dataset.language;
              if (translations[lang]) {
                textarea.value = translations[lang];
              }
            });
          });
          restoreOriginal();
          autoBtn.disabled = false;
        }).catch(error => {
          window.TranslationModalUtils.showAutoTranslateError(
            autoBtn,
            'Auto Translate All',
            error.message,
            { originalNodes }
          );
        });
      });
    }

    openBtn.dataset.translationMatrixAttached = 'true';
    return true;
  };

  // Try immediately
  tryAttach();

  // Expose for lazy attachment
  window.attachMatrixColumnHeadersModalLazy = tryAttach;
}

function attachMatrixModals() {
  if (window.TranslationMatrix) {
    window.TranslationMatrix.attachPages({
      openButtonId: 'page-translations-matrix-btn',
      modalId: 'page-translation-matrix-modal',
      tbodyId: 'page-translation-matrix-tbody',
      saveButtonId: 'save-pages-matrix-btn',
      cssPrefix: 'pages-matrix'
    });
    window.TranslationMatrix.attachOptions({
      openButtonId: 'question-options-translations-matrix-btn',
      modalId: 'question-options-translation-matrix-modal',
      tbodyId: 'question-options-translation-matrix-tbody',
      saveButtonId: 'save-options-matrix-btn',
      cssPrefix: 'options-matrix'
    });
  }
}

function wireAutoTranslatePageHooks() {
  if (!window.getPageSpecificTranslationCounts) {
    window.getPageSpecificTranslationCounts = function() { return {}; };
  }
  if (!window.performPageSpecificTranslation) {
    window.performPageSpecificTranslation = function() {
      const modal = window.autoTranslateModal;
      if (modal) {
        modal.logProgress('No items found that need translation', 'info');
        modal.translationState.isRunning = false;
      }
    };
  }
}

export function attachFormBuilderTranslation() {
  // Ensure we only wire these once even if the module is imported/loaded multiple times.
  if (window.__formBuilderTranslationWired) return;
  window.__formBuilderTranslationWired = true;

  document.addEventListener('DOMContentLoaded', function() {
    attachQuestionModal();
    attachIndicatorModal();
    attachSectionModal();
    attachTemplateNameModal();
    attachDocumentModal();
    attachMatrixLabelModal();
    attachMatrixLegendTextModal();
    attachMatrixColumnHeadersModal();
    attachMatrixModals();
    wireAutoTranslatePageHooks();
  });
}

attachFormBuilderTranslation();
