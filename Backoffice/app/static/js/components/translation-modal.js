// translation-modal.js - Reusable controller for translation modals rendered by translation_modal macro

export const TranslationModal = {
  /**
   * Attach modal behavior to a specific modal instance.
   * @param {Object} config
   * @param {string} config.openButtonId - ID of the button that opens the modal
   * @param {string} config.modalId - ID of the modal element
   * @param {string} config.cssPrefix - Prefix used by the modal fields, e.g. 'template-name'
   * @param {string} [config.hiddenInputSelector] - Selector for the hidden input storing consolidated JSON (simple, non-tab modals)
   * @param {function(): string} config.resolveEnglishText - Returns the English base text (outside modal)
   * @param {function(Object|Object<string,Object>): void} [config.onSaveHiddenFields] - Called with collected translations; if tabbed, receives { [suffix]: translations }
   * @param {string} [config.autoTranslateType] - API type for auto-translate (e.g. 'template_name', 'section_name', 'form_item')
   * @param {string[]} [config.tabSuffixes] - For tabbed modals, e.g. ['labels','definitions'] or ['labels','descriptions']
   * @param {string} [config.defaultTabSuffix] - Default tab to activate on open when tabbed
   * @param {function(): void} [config.onModalOpen] - Called when modal opens, for custom loading logic
   * @param {function(): Object|Object<string,string>} [config.resolveTextsByTab] - Optional, allows per-tab English text resolution.
   */
  attach(config) {
    const {
      openButtonId,
      modalId,
      cssPrefix,
      hiddenInputSelector,
      resolveEnglishText,
      onSaveHiddenFields,
      autoTranslateType,
      tabSuffixes,
      defaultTabSuffix,
      onModalOpen,
      // NEW: allow callers to provide per-tab English texts, e.g., { labels, definitions }
      resolveTextsByTab
    } = config || {};
    const isTabbedModal = Array.isArray(tabSuffixes) && tabSuffixes.length > 0;

    const openBtn = document.getElementById(openButtonId);
    const modal = document.getElementById(modalId);
    const hiddenInput = hiddenInputSelector ? document.querySelector(hiddenInputSelector) : null;
    const saveBtn = document.getElementById(`save-${cssPrefix}-translations-btn`);
    const autoBtn = document.getElementById(`auto-translate-${cssPrefix}-btn`);
    const clearBtn = document.getElementById(`clear-${cssPrefix}-btn`);

    if (!openBtn || !modal) return;

    // Scope future actions to the opener instance to prevent duplicate listeners fighting
    openBtn.addEventListener('click', function() {
      try { modal.dataset.activeOpenButton = openButtonId; } catch (_) {}
    });

    // Wire tab switching if tabbed
    if (isTabbedModal) {
      try {
        tabSuffixes.forEach(suffix => {
          const tabBtn = document.getElementById(`${cssPrefix}-tab-${suffix}`);
          if (!tabBtn) return;
          tabBtn.addEventListener('click', function() {
            // Toggle active class on buttons
            tabSuffixes.forEach(sfx => {
              const btn = document.getElementById(`${cssPrefix}-tab-${sfx}`);
              if (btn) {
                if (sfx === suffix) {
                  btn.classList.add('bg-blue-100','text-blue-700','border-b-2','border-blue-500','active-tab');
                  btn.classList.remove('text-gray-500','hover:text-gray-700');
                } else {
                  btn.classList.remove('bg-blue-100','text-blue-700','border-b-2','border-blue-500','active-tab');
                  btn.classList.add('text-gray-500','hover:text-gray-700');
                }
              }
            });
            // Show/hide tab contents
            tabSuffixes.forEach(sfx => {
              const panel = document.getElementById(`${cssPrefix}-${sfx}-tab-content`);
              if (panel) {
                if (sfx === suffix) panel.classList.remove('hidden');
                else panel.classList.add('hidden');
              }
            });
          });
        });
      } catch (_) { /* non-fatal */ }
    }

    function getLanguagesFromDom(suffix = '') {
      const baseId = suffix ? `${cssPrefix}-translation-${suffix}-` : `${cssPrefix}-translation-`;
      const selector = `[id^='${baseId}']`;
      const nodes = Array.from(modal.querySelectorAll(selector));
      const codes = nodes.map(n => {
        const id = n.id || '';
        if (id.startsWith(baseId)) {
          return id.slice(baseId.length);
        }
        const parts = id.split('-');
        return parts[parts.length - 1];
      }).filter(code => code && code !== 'en');
      return Array.from(new Set(codes));
    }

    function populateFieldsFallback(translations = {}, suffix = '') {
      const languages = getLanguagesFromDom(suffix);
      languages.forEach(code => {
        const id = suffix ? `${cssPrefix}-translation-${suffix}-${code}` : `${cssPrefix}-translation-${code}`;
        const field = document.getElementById(id);
        if (field) field.value = translations[code] || '';
      });
    }

    function collectFieldsFallback(suffix = '') {
      const collected = {};
      const languages = getLanguagesFromDom(suffix);
      languages.forEach(code => {
        const id = suffix ? `${cssPrefix}-translation-${suffix}-${code}` : `${cssPrefix}-translation-${code}`;
        const field = document.getElementById(id);
        collected[code] = field ? field.value : '';
      });
      return collected;
    }

    function clearFieldsFallback(suffix = '') {
      const languages = getLanguagesFromDom(suffix);
      languages.forEach(code => {
        const id = suffix ? `${cssPrefix}-translation-${suffix}-${code}` : `${cssPrefix}-translation-${code}`;
        const field = document.getElementById(id);
        if (field) field.value = '';
      });
    }

    function getActiveTabSuffix() {
      if (!isTabbedModal) return '';
      // Find the tab button with .active-tab class (no default-tab bias)
      const activeBtn = modal.querySelector('[id^="' + cssPrefix + '-tab-"].active-tab');
      if (activeBtn && activeBtn.id) {
        const prefix = `${cssPrefix}-tab-`;
        if (activeBtn.id.startsWith(prefix)) {
          return activeBtn.id.slice(prefix.length);
        }
      }
      // Fallback: visible tab panel
      for (const suffix of tabSuffixes) {
        const panel = document.getElementById(`${cssPrefix}-${suffix}-tab-content`);
        if (panel && !panel.classList.contains('hidden')) {
          return suffix;
        }
      }
      return defaultTabSuffix || tabSuffixes[0] || '';
    }

    function parseExistingTranslations() {
      // Prefer current hidden input value, else data-existing-translations attribute
      let translations = {};
      if (hiddenInput) {
        const raw = hiddenInput.value || '';
        if (raw && raw.trim() && raw.trim() !== '{}') {
          try {
            translations = JSON.parse(raw);
            return translations || {};
          } catch (e) {
            // fall through
          }
        }
        const dataAttr = hiddenInput.getAttribute('data-existing-translations') || '';
        if (dataAttr && dataAttr.trim() && dataAttr.trim() !== '{}') {
          try {
            const unescaped = dataAttr
              .replace(/&quot;/g, '"')
              .replace(/&#39;/g, "'")
              .replace(/&amp;/g, '&')
              .replace(/&lt;/g, '<')
              .replace(/&gt;/g, '>');
            translations = JSON.parse(unescaped);
          } catch (e) {
            translations = {};
          }
        }
      }
      return translations || {};
    }

    const modalController = (window.ModalUtils && window.ModalUtils.makeModal(modal, {
      closeSelector: '.close-modal',
      onClose: () => {
        try { delete modal.dataset.activeOpenButton; } catch (_) {}
      }
    })) || {
      openModal: () => modal.classList.remove('hidden'),
      closeModal: () => { modal.classList.add('hidden'); try { delete modal.dataset.activeOpenButton; } catch (_) {} }
    };

    function closeModal() {
      modalController.closeModal();
    }

    // Open modal
    openBtn.addEventListener('click', function() {
      if (isTabbedModal) {
        // Activate default tab if requested
        if (defaultTabSuffix) {
          const tabBtn = document.getElementById(`${cssPrefix}-tab-${defaultTabSuffix}`);
          if (tabBtn) {
            try { tabBtn.click(); } catch (e) {}
          }
        }
        // Call custom modal open logic if provided
        if (typeof onModalOpen === 'function') {
          onModalOpen();
        }
        // Otherwise, leave fields as-is; per-page code may prefill
      } else {
        const existing = parseExistingTranslations();
        if (window.TranslationModalUtils) {
          window.TranslationModalUtils.populateFields(cssPrefix, existing);
        } else {
          populateFieldsFallback(existing);
        }
        // Call custom modal open logic if provided
        if (typeof onModalOpen === 'function') {
          onModalOpen();
        }
      }
      modalController.openModal();
    });

    // Save
    if (saveBtn) {
      saveBtn.addEventListener('click', function() {
        const hasUtils = !!window.TranslationModalUtils;
        if (isTabbedModal) {
          const collectedByTab = {};
          tabSuffixes.forEach(suffix => {
            collectedByTab[suffix] = hasUtils
              ? window.TranslationModalUtils.collectFields(cssPrefix, suffix)
              : collectFieldsFallback(suffix);
          });
          if (typeof onSaveHiddenFields === 'function') onSaveHiddenFields(collectedByTab);
        } else {
          const collected = hasUtils
            ? window.TranslationModalUtils.collectFields(cssPrefix)
            : collectFieldsFallback();
          if (hiddenInput) hiddenInput.value = JSON.stringify(collected);
          if (typeof onSaveHiddenFields === 'function') onSaveHiddenFields(collected);
        }
        closeModal();
      });
    }

    // Auto-translate
    if (autoBtn && window.TranslationModalUtils) {
      // Prevent duplicate attachment when attach() is called twice for the same opener.
      // Multiple openers may share one modal + cssPrefix (e.g. indicator vs question → same
      // translation-modal); each needs its own listener, so the guard MUST include openButtonId.
      const guardAttr = `data-tm-attached-${cssPrefix}-${openButtonId}`;
      if (autoBtn.getAttribute(guardAttr) === 'true') {
        try { console.debug('[TranslationModal] Skipping duplicate auto-translate binding', { cssPrefix, openButtonId }); } catch (_) {}
      } else {
        autoBtn.setAttribute(guardAttr, 'true');
        autoBtn.addEventListener('click', function() {
          // Ensure only the handler for the active opener runs
          if (modal && modal.dataset && modal.dataset.activeOpenButton && modal.dataset.activeOpenButton !== openButtonId) {
            return; // Not the active opener's handler
          }

          // Gather English texts
          let englishLabel = '';
          let englishDefinition = '';
          let englishDescription = '';
          const englishBySuffix = {};

          if (typeof resolveTextsByTab === 'function') {
            try {
              const byTab = resolveTextsByTab() || {};
              if (isTabbedModal) {
                tabSuffixes.forEach(suffix => {
                  const raw = byTab[suffix];
                  const text = raw === undefined || raw === null ? '' : String(raw);
                  const trimmed = text.trim();
                  englishBySuffix[suffix] = trimmed;
                  if (suffix === 'labels') englishLabel = trimmed;
                  if (suffix === 'definitions') englishDefinition = trimmed;
                  if (suffix === 'descriptions') englishDescription = trimmed;
                });
              } else {
                englishLabel = (byTab.labels || '').trim();
                englishDefinition = (byTab.definitions || '').trim();
              }
            } catch (e) {
              try { console.warn('[TranslationModal] resolveTextsByTab failed', { cssPrefix, error: e }); } catch (_) {}
            }
          }

          if (!isTabbedModal) {
            // Fallback to single resolver
            if (!englishLabel) {
              englishLabel = (typeof resolveEnglishText === 'function') ? (resolveEnglishText() || '') : '';
              englishLabel = englishLabel.trim();
            }
          } else {
            // Ensure we at least seed labels from the single resolver when tabs are present
            if (!englishBySuffix.labels) {
              englishLabel = (typeof resolveEnglishText === 'function') ? (resolveEnglishText() || '') : '';
              englishLabel = englishLabel.trim();
              englishBySuffix.labels = englishLabel;
            }
            tabSuffixes.forEach(suffix => {
              if (typeof englishBySuffix[suffix] !== 'string') {
                englishBySuffix[suffix] = '';
              }
            });
            englishDefinition = englishBySuffix.definitions || englishDefinition;
            englishDescription = englishBySuffix.descriptions || englishDescription;
          }

          try { console.log('[TranslationModal] Auto translate invoked', { cssPrefix, hasTabbed: isTabbedModal, englishLabel, englishDefinition, englishDescription }); } catch (_) {}

          // Determine if we have anything to translate
          const nothingToTranslate = isTabbedModal
            ? tabSuffixes.every(suffix => !englishBySuffix[suffix])
            : (!englishLabel);
          if (nothingToTranslate) {
            try { console.warn('[TranslationModal] Nothing to translate', { cssPrefix, hasTabbed: isTabbedModal, englishLabel, englishDefinition, englishDescription }); } catch (_) {}
            if (window.showAlert) window.showAlert('Please enter text to translate', 'warning');
            return;
          }

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

          // Helper to perform a single translate call (uses AutoTranslateService when available)
          function translateOne(text, tag) {
            try { console.log('[TranslationModal] Translating', { cssPrefix, tag, text }); } catch (_) {}
            const permissionContext = (modal && modal.dataset && modal.dataset.autoTranslatePermissionContext) ? modal.dataset.autoTranslatePermissionContext : '';
            const permissionCode = (modal && modal.dataset && modal.dataset.autoTranslatePermissionCode) ? modal.dataset.autoTranslatePermissionCode : '';
            const targetLangs = window.TranslationModalUtils ? window.TranslationModalUtils.getTargetLanguages() : [];
            if (window.AutoTranslateService && typeof window.AutoTranslateService.translate === 'function') {
              return window.AutoTranslateService.translate({
                type: autoTranslateType || 'template_name',
                permission_context: permissionContext,
                permission_code: permissionCode,
                text: text,
                target_languages: targetLangs
              });
            }
            return Promise.reject(new Error('AutoTranslateService not loaded'));
          }

          // If not tabbed, single request using englishLabel
          if (!isTabbedModal) {
            translateOne(englishLabel, 'labels')
              .then(data => {
                const flat = (autoTranslateType === 'form_item' && data.translations.label_translations)
                  ? data.translations.label_translations
                  : data.translations;
                try { console.log('[TranslationModal] Populate flat result', { cssPrefix, flat }); } catch (_) {}
                if (window.TranslationModalUtils) {
                  window.TranslationModalUtils.populateFields(cssPrefix, flat);
                } else {
                  populateFieldsFallback(flat);
                }
                // Auto-save to hidden if callback provided
                if (typeof onSaveHiddenFields === 'function') {
                  try { onSaveHiddenFields(flat); } catch (_) {}
                }
                autoBtn.replaceChildren();
                {
                  const icon = document.createElement('i');
                  icon.className = 'fas fa-check w-4 h-4 mr-2';
                  autoBtn.append(icon, document.createTextNode('Translated!'));
                }
                setTimeout(() => {
                  restoreOriginal();
                  autoBtn.disabled = false;
                }, 1500);
              })
              .catch(error => {
                window.TranslationModalUtils.showAutoTranslateError(
                  autoBtn,
                  originalNodes.map(n => n.textContent).join(''),
                  error.message,
                  { originalNodes }
                );
              });
            return;
          }

          // Tabbed: translate all tabs that have non-empty English text
          const promises = [];
          const results = {};
          tabSuffixes.forEach(suffix => {
            results[suffix] = {};
          });

          const tabErrors = {};
          tabSuffixes.forEach(suffix => {
            const englishText = englishBySuffix[suffix];
            if (!englishText) return;
            promises.push(
              translateOne(englishText, suffix).then(data => {
                const payload = data && typeof data === 'object'
                  ? (data.translations || data)
                  : {};
                results[suffix] = payload || {};
                try {
                  console.log('[TranslationModal] Tab promise result', {
                    cssPrefix,
                    suffix,
                    payload,
                    keys: Object.keys(payload || {})
                  });
                } catch (_) {}
              }).catch(err => {
                tabErrors[suffix] = err;
                try { console.warn('[TranslationModal] Tab translate failed', { cssPrefix, suffix, error: err && err.message }); } catch (_) {}
              })
            );
          });

          Promise.all(promises)
            .then(() => {
              // If every tab with text failed, surface the first error
              const attempedSuffixes = tabSuffixes.filter(s => !!englishBySuffix[s]);
              const anySuccess = attempedSuffixes.some(s => results[s] && Object.keys(results[s]).length > 0);
              if (!anySuccess && Object.keys(tabErrors).length > 0) {
                const firstErr = tabErrors[attempedSuffixes.find(s => tabErrors[s])];
                throw firstErr;
              }
              try { console.log('[TranslationModal] Translation results', { cssPrefix, results }); } catch (_) {}

              // Extractor to normalize nested API shapes into flat code->text maps per tab
              function extractMapForSuffix(obj, suffix) {
                if (!obj || typeof obj !== 'object') {
                  try { console.log('[TranslationModal] extractMapForSuffix empty', { suffix, obj }); } catch (_) {}
                  return {};
                }
                // Labels priority
                if (suffix === 'labels') {
                  const extracted = obj.labels
                    || obj.label_translations
                    || obj.translations
                    || obj;
                  try { console.log('[TranslationModal] extractMapForSuffix labels', { obj, extracted, keys: Object.keys(extracted || {}) }); } catch (_) {}
                  return extracted;
                }
                // Definitions/descriptions priority; fallback to label_translations if API doesn't separate
                if (suffix === 'definitions' || suffix === 'descriptions') {
                  // Try direct properties first
                  let extracted = obj.definitions || obj.descriptions;

                  // If not found, try nested structures
                  if (!extracted || (typeof extracted === 'object' && Object.keys(extracted).length === 0)) {
                    extracted = obj.definition_translations || obj.description_translations;
                  }

                  // If still not found, try label_translations (API might return same structure for both)
                  if (!extracted || (typeof extracted === 'object' && Object.keys(extracted).length === 0)) {
                    extracted = obj.label_translations;
                  }

                  // If still not found, try translations (flat map)
                  if (!extracted || (typeof extracted === 'object' && Object.keys(extracted).length === 0)) {
                    extracted = obj.translations;
                  }

                  // Last resort: use obj itself if it's a flat map
                  if (!extracted || (typeof extracted === 'object' && Object.keys(extracted).length === 0)) {
                    // Check if obj itself is a flat map (has language codes as keys)
                    const hasLangCodes = obj && typeof obj === 'object' && Object.keys(obj).some(k => k.length === 2 || k === 'ar' || k === 'es' || k === 'fr');
                    if (hasLangCodes) {
                      extracted = obj;
                    } else {
                      extracted = {};
                    }
                  }

                  try { console.log('[TranslationModal] extractMapForSuffix definitions', {
                    obj,
                    extracted,
                    keys: Object.keys(extracted || {}),
                    extractedType: typeof extracted,
                    extractedIsArray: Array.isArray(extracted)
                  }); } catch (_) {}
                  return extracted || {};
                }
                return obj;
              }

              // Populate each tab that has results (fields exist in DOM even if tab is hidden)
              tabSuffixes.forEach(suffix => {
                const rawSource = results[suffix] || {};
                if (!rawSource || (typeof rawSource === 'object' && Object.keys(rawSource).length === 0)) return;
                const source = extractMapForSuffix(rawSource, suffix);
                try { console.log('[TranslationModal] Populate tab', { cssPrefix, suffix, source, sourceKeys: Object.keys(source || {}) }); } catch (_) {}

                if (window.TranslationModalUtils) {
                  window.TranslationModalUtils.populateFields(cssPrefix, source, '', suffix);
                } else {
                  populateFieldsFallback(source, suffix);
                }
              });
              if (typeof onSaveHiddenFields === 'function') {
                const normalized = {};
                tabSuffixes.forEach(suffix => {
                  if (results[suffix] && Object.keys(results[suffix]).length > 0) {
                    normalized[suffix] = extractMapForSuffix(results[suffix], suffix);
                  }
                });
                try { onSaveHiddenFields(normalized); } catch (_) {}
              }
              const hasPartialErrors = Object.keys(tabErrors).length > 0;
              autoBtn.replaceChildren();
              {
                const icon = document.createElement('i');
                icon.className = `fas ${hasPartialErrors ? 'fa-exclamation-circle' : 'fa-check'} w-4 h-4 mr-2`;
                autoBtn.append(icon, document.createTextNode(hasPartialErrors ? 'Partially Translated' : 'Translated!'));
              }
              if (hasPartialErrors) {
                const failedTabs = Object.keys(tabErrors).join(', ');
                if (window.showAlert) window.showAlert(`Some tabs could not be translated: ${failedTabs}`, 'warning');
              }
              setTimeout(() => {
                restoreOriginal();
                autoBtn.disabled = false;
              }, 1500);
            })
            .catch(error => {
              window.TranslationModalUtils.showAutoTranslateError(
                autoBtn,
                originalNodes.map(n => n.textContent).join(''),
                error.message,
                { originalNodes }
              );
            });
        });
      }
    }

    // Clear translations
    if (clearBtn) {
      clearBtn.addEventListener('click', function() {
        if (isTabbedModal) {
          // Clear only the currently active tab
          const activeSuffix = getActiveTabSuffix();
          if (window.TranslationModalUtils) {
            window.TranslationModalUtils.clearFields(cssPrefix, activeSuffix);
          } else {
            clearFieldsFallback(activeSuffix);
          }
        } else {
          // Clear simple modal
          if (window.TranslationModalUtils) {
            window.TranslationModalUtils.clearFields(cssPrefix);
          } else {
            clearFieldsFallback();
          }
        }
      });
    }
  }
};
