// translation-matrix.js - Reusable controller for translation matrix modals (pages/options)

export const TranslationMatrix = {
  attachPages(config) {
    const { openButtonId, modalId, tbodyId, saveButtonId, cssPrefix = 'pages-matrix' } = config || {};
    const openBtn = document.getElementById(openButtonId);
    const modal = document.getElementById(modalId);
    const saveBtn = document.getElementById(saveButtonId);

    if (!openBtn || !modal) return;

    function generateCells(translations = {}) {
      // Use server helper if present
      if (window.TranslationModalUtils && typeof window.TranslationModalUtils.generateMatrixCells === 'function') {
        return window.TranslationModalUtils.generateMatrixCells(translations);
      }
      return '';
    }

    function populate() {
      const tbody = document.getElementById(tbodyId);
      const pagesListContainer = document.getElementById('pages-list-container');
      if (!tbody || !pagesListContainer) return;
      tbody.replaceChildren();

      const pageRows = pagesListContainer.querySelectorAll('.page-row');
      pageRows.forEach((pageRow, index) => {
        const pageNameInput = pageRow.querySelector('input[name="page_names"]');
        const translationsInput = pageRow.querySelector('input[name="page_name_translations"]');
        const pageId = pageRow.dataset.pageId;

        const pageName = pageNameInput ? pageNameInput.value : '';
        let translations = {};
        if (translationsInput && translationsInput.dataset.translations && translationsInput.dataset.translations.trim() !== '') {
          try {
            const unescapedJson = translationsInput.dataset.translations
              .replace(/&quot;/g, '"')
              .replace(/&#39;/g, "'")
              .replace(/&amp;/g, '&')
              .replace(/&lt;/g, '<')
              .replace(/&gt;/g, '>');
            const parsedValue = JSON.parse(unescapedJson);
            translations = (typeof parsedValue === 'object' && parsedValue !== null) ? parsedValue : {};
          } catch (e) {
            translations = {};
          }
        }

        const row = document.createElement('tr');
        row.className = 'border-b border-gray-200 hover:bg-gray-50';
        row.dataset.pageId = pageId;
        row.dataset.pageIndex = index;
        const nameTd = document.createElement('td');
        nameTd.className = 'px-4 py-3 text-sm font-medium text-gray-900 border-r border-gray-300';
        nameTd.textContent = pageName;
        row.appendChild(nameTd);

        const cellsHtml = generateCells(translations);
        if (cellsHtml) {
          // Avoid innerHTML assignment; parse as a fragment and append.
          const frag = document.createRange().createContextualFragment(cellsHtml);
          row.appendChild(frag);
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
        const pagesListContainer = document.getElementById('pages-list-container');
        const pageRows = pagesListContainer ? pagesListContainer.querySelectorAll('.page-row') : [];
        const matrixRows = document.querySelectorAll(`#${tbodyId} tr`);

        matrixRows.forEach((matrixRow, index) => {
          const pageRow = pageRows[index];
          if (!pageRow) return;
          const translations = {};
          const textareas = matrixRow.querySelectorAll('textarea[data-language]');
          textareas.forEach(textarea => {
            const language = textarea.dataset.language;
            const value = textarea.value.trim();
            if (value) translations[language] = value;
          });
          const hiddenInput = pageRow.querySelector('input[name="page_name_translations"]');
          if (hiddenInput) {
            const jsonString = JSON.stringify(translations);
            const escapedJson = jsonString
              .replace(/"/g, '&quot;')
              .replace(/'/g, '&#39;')
              .replace(/&/g, '&amp;')
              .replace(/</g, '&lt;')
              .replace(/>/g, '&gt;');
            hiddenInput.value = jsonString;
            hiddenInput.dataset.translations = escapedJson;
          }
        });

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

    // Auto-translate all pages
    const autoBtn = document.getElementById(`auto-translate-${cssPrefix}-btn`);
    if (autoBtn) {
      autoBtn.addEventListener('click', function() {
        const permissionContext = (modal && modal.dataset && modal.dataset.autoTranslatePermissionContext) ? modal.dataset.autoTranslatePermissionContext : '';
        const permissionCode = (modal && modal.dataset && modal.dataset.autoTranslatePermissionCode) ? modal.dataset.autoTranslatePermissionCode : '';
        const pagesListContainer = document.getElementById('pages-list-container');
        const pageRows = pagesListContainer ? pagesListContainer.querySelectorAll('.page-row') : [];
        if (pageRows.length === 0) return;
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

        const pageNames = Array.from(pageRows).map(row => {
          const input = row.querySelector('input[name="page_names"]');
          return input ? (input.value || '') : '';
        }).filter(name => name.trim());
        if (pageNames.length === 0) {
          restoreOriginal();
          autoBtn.disabled = false;
          return;
        }

        Promise.all(pageNames.map(pageName =>
          (window.AutoTranslateService && typeof window.AutoTranslateService.translate === 'function'
            ? window.AutoTranslateService.translate({
                type: 'page_name',
                permission_context: permissionContext,
                permission_code: permissionCode,
                text: pageName,
                target_languages: window.TranslationModalUtils ? window.TranslationModalUtils.getTargetLanguages() : []
              })
            : Promise.reject(new Error('AutoTranslateService not loaded'))
          ).catch(() => null)
        ))
        .then(results => {
          const matrixRows = document.querySelectorAll(`#${tbodyId} tr`);
          let anySuccess = false;
          results.forEach((result, index) => {
            if (result && result.success && result.translations && matrixRows[index]) {
              anySuccess = true;
              const textareas = matrixRows[index].querySelectorAll('textarea[data-language]');
              textareas.forEach(textarea => {
                const language = textarea.dataset.language;
                if (result.translations[language]) textarea.value = result.translations[language];
              });
            }
          });
          autoBtn.replaceChildren();
          {
            const icon = document.createElement('i');
            icon.className = 'fas fa-check w-4 h-4 mr-2';
            autoBtn.append(icon, document.createTextNode('Translated!'));
          }
          setTimeout(() => { restoreOriginal(); autoBtn.disabled = false; }, 2000);
        })
        .catch(error => {
          window.TranslationModalUtils.showAutoTranslateError(
            autoBtn,
            '',
            error.message,
            { originalNodes }
          );
        });
      });
    }

    // Basic close handlers
    modal.querySelectorAll('.close-modal').forEach(btn => {
      btn.addEventListener('click', function() {
        modal.classList.add('hidden');
      });
    });
    modal.addEventListener('click', function(e) {
      if (e.target === modal) modal.classList.add('hidden');
    });
  },

  attachOptions(config) {
    const { openButtonId, modalId, tbodyId, saveButtonId, cssPrefix = 'options-matrix' } = config || {};
    const openBtn = document.getElementById(openButtonId);
    const modal = document.getElementById(modalId);
    const saveBtn = document.getElementById(saveButtonId);
    if (!openBtn || !modal) return;

    function generateCells(translations = {}) {
      if (window.TranslationModalUtils && typeof window.TranslationModalUtils.generateMatrixCells === 'function') {
        return window.TranslationModalUtils.generateMatrixCells(translations);
      }
      return '';
    }

    function populate() {
      const tbody = document.getElementById(tbodyId);
      const optionsList = document.getElementById('item-question-options-list');
      const translationsJsonInput = document.getElementById('item-question-options-translations-json');
      if (!tbody || !optionsList) return;
      tbody.replaceChildren();

      let existingTranslations = {};
      if (translationsJsonInput && translationsJsonInput.value) {
        try {
          const parsed = JSON.parse(translationsJsonInput.value);
          parsed.forEach(item => { existingTranslations[item.option_text] = item.translations; });
        } catch (e) {
          existingTranslations = {};
        }
      }

      const optionRows = optionsList.querySelectorAll('.option-row');
      optionRows.forEach((optionRow, index) => {
        const optionTextInput = optionRow.querySelector('input[type="text"]');
        const optionText = optionTextInput ? optionTextInput.value : '';
        let translations = {};
        if (optionRow.dataset.translations) {
          try { translations = JSON.parse(optionRow.dataset.translations); } catch (e) { translations = {}; }
        } else if (existingTranslations[optionText]) {
          translations = existingTranslations[optionText];
          optionRow.dataset.translations = JSON.stringify(translations);
        }
        const row = document.createElement('tr');
        row.className = 'border-b border-gray-200 hover:bg-gray-50';
        row.dataset.optionIndex = index;
        const textTd = document.createElement('td');
        textTd.className = 'px-4 py-3 text-sm font-medium text-gray-900 border-r border-gray-300';
        textTd.textContent = optionText;
        row.appendChild(textTd);

        const cellsHtml = generateCells(translations);
        if (cellsHtml) {
          const frag = document.createRange().createContextualFragment(cellsHtml);
          row.appendChild(frag);
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
        const optionsList = document.getElementById('item-question-options-list');
        const optionRows = optionsList ? optionsList.querySelectorAll('.option-row') : [];
        const matrixRows = document.querySelectorAll(`#${tbodyId} tr`);
        const translationsJsonInput = document.getElementById('item-question-options-translations-json');

        const allTranslations = [];
        matrixRows.forEach((matrixRow, index) => {
          const optionRow = optionRows[index];
          if (!optionRow) return;
          const optionTextInput = optionRow.querySelector('input[type="text"]');
          const optionText = optionTextInput ? optionTextInput.value : '';
          const translations = {};
          const textareas = matrixRow.querySelectorAll('textarea[data-language]');
          textareas.forEach(textarea => {
            const language = textarea.dataset.language;
            const value = textarea.value.trim();
            if (value) translations[language] = value;
          });
          if (Object.keys(translations).length > 0) {
            optionRow.dataset.translations = JSON.stringify(translations);
            allTranslations.push({ option_text: optionText, translations });
          } else {
            delete optionRow.dataset.translations;
          }
        });
        if (translationsJsonInput) translationsJsonInput.value = JSON.stringify(allTranslations);
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

    // Auto-translate all options
    const autoBtn = document.getElementById(`auto-translate-${cssPrefix}-btn`);
    if (autoBtn) {
      autoBtn.addEventListener('click', function() {
        const permissionContext = (modal && modal.dataset && modal.dataset.autoTranslatePermissionContext) ? modal.dataset.autoTranslatePermissionContext : '';
        const permissionCode = (modal && modal.dataset && modal.dataset.autoTranslatePermissionCode) ? modal.dataset.autoTranslatePermissionCode : '';
        const optionsList = document.getElementById('item-question-options-list');
        const optionRows = optionsList ? optionsList.querySelectorAll('.option-row') : [];
        if (optionRows.length === 0) return;
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

        const optionTexts = Array.from(optionRows).map(row => {
          const input = row.querySelector('input[type="text"]');
          return input ? (input.value || '') : '';
        }).filter(text => text.trim());
        if (optionTexts.length === 0) {
          restoreOriginal();
          autoBtn.disabled = false;
          return;
        }

        Promise.all(optionTexts.map(optionText =>
          (window.AutoTranslateService && typeof window.AutoTranslateService.translate === 'function'
            ? window.AutoTranslateService.translate({
                type: 'question_option',
                permission_context: permissionContext,
                permission_code: permissionCode,
                text: optionText,
                target_languages: window.TranslationModalUtils ? window.TranslationModalUtils.getTargetLanguages() : []
              })
            : Promise.reject(new Error('AutoTranslateService not loaded'))
          ).catch(() => null)
        ))
        .then(results => {
          const matrixRows = document.querySelectorAll(`#${tbodyId} tr`);
          let anySuccess = false;
          results.forEach((result, index) => {
            if (result && result.success && result.translations && matrixRows[index]) {
              anySuccess = true;
              const textareas = matrixRows[index].querySelectorAll('textarea[data-language]');
              textareas.forEach(textarea => {
                const language = textarea.dataset.language;
                if (result.translations[language]) textarea.value = result.translations[language];
              });
            }
          });
          autoBtn.replaceChildren();
          {
            const icon = document.createElement('i');
            icon.className = 'fas fa-check w-4 h-4 mr-2';
            autoBtn.append(icon, document.createTextNode('Translated!'));
          }
          setTimeout(() => { restoreOriginal(); autoBtn.disabled = false; }, 2000);
        })
        .catch(error => {
          window.TranslationModalUtils.showAutoTranslateError(
            autoBtn,
            '',
            error.message,
            { originalNodes }
          );
        });
      });
    }

    modal.querySelectorAll('.close-modal').forEach(btn => {
      btn.addEventListener('click', function() { modal.classList.add('hidden'); });
    });
    modal.addEventListener('click', function(e) { if (e.target === modal) modal.classList.add('hidden'); });
  }
};
