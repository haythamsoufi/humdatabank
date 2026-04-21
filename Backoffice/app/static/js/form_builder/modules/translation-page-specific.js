// translation-page-specific.js - Page-specific translation logic for form builder

import '/static/js/components/translation-utils.js';

/** Use centralized fetchJson from api-fetch.js (load before this module). */
const fetchJson = (url, options) => (window.fetchJson || window.apiFetch)(url, options);

/** Use readJson from translation-utils.js (loads first via import). */
const readJson = window.readJson || function readJson(id, fb) {
  try {
    const el = document.getElementById(id);
    return (el && el.textContent) ? JSON.parse(el.textContent) : fb;
  } catch (_) {
    return fb;
  }
};

function getEndpoints() {
  const defaults = { bulkUpdateTranslations: '/admin/api/bulk-update-translations' };
  return readJson('translation-endpoints', defaults) || defaults;
}

function getLangCodeFromName(languageName) {
  // First try template-data localeToTranslationKey if available
  const templateData = readJson('template-data', { localeToTranslationKey: {} });
  const map = templateData.localeToTranslationKey || {};
  for (const code in map) {
    if (Object.prototype.hasOwnProperty.call(map, code)) {
      if (map[code] === languageName) return code;
    }
  }
  // Fall back to translation-data languageDisplayNames (reverse lookup)
  const translationData = readJson('translation-data', { languageDisplayNames: {} });
  const displayNames = translationData.languageDisplayNames || {};
  for (const code in displayNames) {
    if (Object.prototype.hasOwnProperty.call(displayNames, code)) {
      if (displayNames[code] === languageName) return code;
    }
  }
  // If it's already a code (2-3 lowercase letters), return as-is
  if (/^[a-z]{2,3}$/i.test(languageName)) {
    return languageName.toLowerCase();
  }
  return languageName; // unknown; fall back to provided value
}

function computeCounts() {
  const templateData = readJson('template-data', { translatableLanguages: [], localeToTranslationKey: {} });
  const sectionsData = readJson('sections-with-items-data', []);
  const pagesData = readJson('all-template-pages-data', []);

  const counts = {};
  (templateData.translatableLanguages || []).forEach(langCode => {
    const key = (templateData.localeToTranslationKey || {})[langCode] || langCode;
    counts[key] = 0;
  });

  const templateNameTranslations = templateData.templateNameTranslations || {};
  const templateName = templateData.templateName || '';
  if (templateName && templateName.trim()) {
    Object.keys(counts).forEach(lang => {
      const code = getLangCodeFromName(lang);
      if (!templateNameTranslations[code] || !String(templateNameTranslations[code]).trim()) counts[lang]++;
    });
  }

  sectionsData.forEach(section => {
    const sectionText = section.name || '';
    const sectionTranslations = section.name_translations || {};
    if (sectionText && sectionText.trim()) {
      Object.keys(counts).forEach(lang => {
        const code = getLangCodeFromName(lang);
        const v = sectionTranslations[code];
        if (!v || !String(v).trim()) counts[lang]++;
      });
    }

    (section.questions || []).forEach(question => {
      const questionText = question.label || '';
      const translations = question.label_translations || {};
      if (questionText && questionText.trim()) {
        Object.keys(counts).forEach(lang => {
          const code = getLangCodeFromName(lang);
          const v = translations[code];
          if (!v || !String(v).trim()) counts[lang]++;
        });
      }
    });

    (section.document_fields || []).forEach(docField => {
      const docText = docField.label || '';
      const labelTranslations = docField.label_translations || {};
    if (docText && docText.trim()) {
      Object.keys(counts).forEach(lang => {
        const code = getLangCodeFromName(lang);
        const v = labelTranslations[code];
        if (!v || !String(v).trim()) counts[lang]++;
      });
    }
    });

    // Process matrix items from form_items array
    (section.form_items || []).forEach(formItem => {
      // Check if this is a matrix item
      if (formItem.item_type === 'matrix') {
        const matrixLabel = formItem.label || '';
        const labelTranslations = formItem.label_translations || {};
        if (matrixLabel && matrixLabel.trim()) {
          Object.keys(counts).forEach(lang => {
            const code = getLangCodeFromName(lang);
            const v = labelTranslations[code];
            if (!v || !String(v).trim()) counts[lang]++;
          });
        }
        // Also check description/definition translations for matrix items
        const matrixDescription = formItem.definition || formItem.description || '';
        const descriptionTranslations = formItem.description_translations || formItem.definition_translations || {};
        if (matrixDescription && matrixDescription.trim()) {
          Object.keys(counts).forEach(lang => {
            const code = getLangCodeFromName(lang);
            const v = descriptionTranslations[code];
            if (!v || !String(v).trim()) counts[lang]++;
          });
        }
      }
      // Process plugin items (item_type starts with 'plugin_')
      if (formItem.item_type && String(formItem.item_type).startsWith('plugin_')) {
        const pluginLabel = formItem.label || '';
        const labelTranslations = formItem.label_translations || {};
        if (pluginLabel && pluginLabel.trim()) {
          Object.keys(counts).forEach(lang => {
            const code = getLangCodeFromName(lang);
            const v = labelTranslations[code];
            if (!v || !String(v).trim()) counts[lang]++;
          });
        }
        const pluginDescription = formItem.definition || formItem.description || '';
        const descriptionTranslations = formItem.description_translations || formItem.definition_translations || {};
        if (pluginDescription && pluginDescription.trim()) {
          Object.keys(counts).forEach(lang => {
            const code = getLangCodeFromName(lang);
            const v = descriptionTranslations[code];
            if (!v || !String(v).trim()) counts[lang]++;
          });
        }
      }
    });
  });

  (pagesData || []).forEach(page => {
    const pageText = page.name || '';
    const pageTranslations = page.name_translations || {};
    if (pageText && pageText.trim()) {
      Object.keys(counts).forEach(lang => {
        const code = getLangCodeFromName(lang);
        const v = pageTranslations[code];
        if (!v || !String(v).trim()) counts[lang]++;
      });
    }
  });

  return counts;
}

function buildItemsToTranslate(selectedLanguages) {
  const templateData = readJson('template-data', {});
  const sectionsData = readJson('sections-with-items-data', []);
  const pagesData = readJson('all-template-pages-data', []);

  const counts = computeCounts();
  const languagesNeedingTranslation = selectedLanguages.filter(lang => (counts[lang] || 0) > 0);
  const items = [];

  sectionsData.forEach(section => {
    const sectionTranslations = section.name_translations || {};
    languagesNeedingTranslation.forEach(lang => {
      const code = getLangCodeFromName(lang);
      const v = sectionTranslations[code];
      if (!v || !String(v).trim()) {
        const text = section.name || '';
        if (text && text.trim()) items.push({ id: section.id, text, language: lang, type: 'section' });
      }
    });

    (section.questions || []).forEach(question => {
      const translations = question.label_translations || {};
      languagesNeedingTranslation.forEach(lang => {
        const code = getLangCodeFromName(lang);
        const v = translations[code];
        if (!v || !String(v).trim()) {
          const text = question.label || '';
          if (text && text.trim()) items.push({ id: question.id, text, definition: (question.definition || ''), language: lang, type: 'question' });
        }
      });
    });

    (section.document_fields || []).forEach(docField => {
      const labelTranslations = docField.label_translations || {};
      languagesNeedingTranslation.forEach(lang => {
        const code = getLangCodeFromName(lang);
        const v = labelTranslations[code];
        if (!v || !String(v).trim()) {
          const text = docField.label || '';
          if (text && text.trim()) items.push({ id: docField.id, text, description: (docField.description || ''), language: lang, type: 'document_field' });
        }
      });
    });

    // Process matrix items from form_items array
    (section.form_items || []).forEach(formItem => {
      // Check if this is a matrix item
      if (formItem.item_type === 'matrix') {
        const labelTranslations = formItem.label_translations || {};
        const descriptionTranslations = formItem.description_translations || formItem.definition_translations || {};
        const text = formItem.label || '';
        const description = formItem.definition || formItem.description || '';

        languagesNeedingTranslation.forEach(lang => {
          const code = getLangCodeFromName(lang);
          const labelTranslated = labelTranslations[code];
          const descTranslated = descriptionTranslations[code];

          // Check if either label or description needs translation
          const needsLabelTranslation = (text && text.trim() && (!labelTranslated || !String(labelTranslated).trim()));
          const needsDescTranslation = (description && description.trim() && (!descTranslated || !String(descTranslated).trim()));

          if (needsLabelTranslation || needsDescTranslation) {
            // Only add item if there's actual text to translate (at least label or description)
            if ((text && text.trim()) || (description && description.trim())) {
              // Create a single item with both text and description
              items.push({
                id: formItem.item_id,
                text: text || '',
                description: description || '',
                language: lang,
                type: 'matrix'
              });
            }
          }
        });
      }
      // Process plugin items (item_type starts with 'plugin_')
      if (formItem.item_type && String(formItem.item_type).startsWith('plugin_')) {
        const labelTranslations = formItem.label_translations || {};
        const descriptionTranslations = formItem.description_translations || formItem.definition_translations || {};
        const text = formItem.label || '';
        const description = formItem.definition || formItem.description || '';
        languagesNeedingTranslation.forEach(lang => {
          const code = getLangCodeFromName(lang);
          const labelTranslated = labelTranslations[code];
          const descTranslated = descriptionTranslations[code];
          const needsLabelTranslation = (text && text.trim() && (!labelTranslated || !String(labelTranslated).trim()));
          const needsDescTranslation = (description && description.trim() && (!descTranslated || !String(descTranslated).trim()));
          if (needsLabelTranslation || needsDescTranslation) {
            if ((text && text.trim()) || (description && description.trim())) {
              items.push({
                id: formItem.item_id,
                text: text || '',
                description: description || '',
                language: lang,
                type: formItem.item_type
              });
            }
          }
        });
      }
    });
  });

  (pagesData || []).forEach(page => {
    const pageTranslations = page.name_translations || {};
    languagesNeedingTranslation.forEach(lang => {
      const code = getLangCodeFromName(lang);
      const v = pageTranslations[code];
      if (!v || !String(v).trim()) {
        const text = page.name || '';
        if (text && text.trim()) items.push({ id: page.id, text, language: lang, type: 'page' });
      }
    });
  });

  const templateNameTranslations = templateData.templateNameTranslations || {};
  const templateName = templateData.templateName || '';
  const templateId = templateData.templateId;
  languagesNeedingTranslation.forEach(lang => {
    const code = getLangCodeFromName(lang);
    const v = templateNameTranslations[code];
    if (!v || !String(v).trim()) {
      if (templateName && templateName.trim()) items.push({ id: templateId, text: templateName, language: lang, type: 'template_name' });
    }
  });

  return { items, languagesNeedingTranslation };
}

function mapItemTypeToApi(type) {
  switch (type) {
    case 'section': return 'section_name';
    case 'page': return 'page_name';
    case 'template_name': return 'template_name';
    case 'question':
    case 'document_field':
    case 'indicator':
    case 'matrix':
    default: return 'form_item';
  }
}

function processItemsSequentially(items, index, selectedService, endpoints) {
  const modal = window.autoTranslateModal;
  if (!modal) return;
  if (index >= items.length || modal.translationState.shouldStop) {
    modal.translationState.isRunning = false;
    modal.logProgress('Translation completed!', 'success');
    jQuery('#auto-translate-pause-btn').addClass('hidden');
    jQuery('#auto-translate-resume-btn').addClass('hidden');
    jQuery('#auto-translate-stop-btn').addClass('hidden');
    jQuery('#auto-translate-close-btn').removeClass('hidden');
    if (modal.notifyCompletion) {
      modal.notifyCompletion();
    }
    return;
  }

  if (modal.translationState.isPaused) {
    setTimeout(() => processItemsSequentially(items, index, selectedService, endpoints), 400);
    return;
  }

  const item = items[index];
  const permissionContext = (window.autoTranslateModal && window.autoTranslateModal.config && window.autoTranslateModal.config.permission_context)
    ? window.autoTranslateModal.config.permission_context
    : '';
  const permissionCode = (window.autoTranslateModal && window.autoTranslateModal.config && window.autoTranslateModal.config.permission_code)
    ? window.autoTranslateModal.config.permission_code
    : '';
  // Convert language name to language code for API
  const langCode = getLangCodeFromName(item.language);
  // For matrix and document_field items, use description field; for others use definition
  // Only include definition if it has content (API handles empty definition, but cleaner to omit)
  const definitionText = item.definition || item.description || '';
  const requestPayload = {
    type: mapItemTypeToApi(item.type),
    permission_context: permissionContext,
    permission_code: permissionCode,
    text: item.text,
    target_languages: [langCode],
    translation_service: selectedService || 'ifrc'
  };
  // Only add definition if it has content
  if (definitionText && definitionText.trim()) {
    requestPayload.definition = definitionText;
  }

  // Encode payload to avoid WAF false positives on indicator text/definitions
  // (same pattern as auto-translate-service.js). Backend already supports { payload: b64 }.
  const _tpsPayloadB64 = btoa(unescape(encodeURIComponent(JSON.stringify(requestPayload))));
  fetchJson(window.autoTranslateModal.config.endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
      'X-CSRFToken': (document.querySelector('meta[name=csrf-token]')?.getAttribute('content') || '')
    },
    body: JSON.stringify({ payload: _tpsPayloadB64 })
  }).then(data => {
      modal.translationState.processedItems++;
      if (data.success && data.translations) {
        // Ensure ID is a number (parse if it's a string)
        const itemId = typeof item.id === 'string' ? parseInt(item.id, 10) : item.id;
        const itemToUpdate = { id: itemId, type: item.type, translations: {} };
        const langCode = getLangCodeFromName(item.language);
        if (item.type === 'section' || item.type === 'page' || item.type === 'template_name') {
          const translated = data.translations && data.translations[langCode];
          if (translated) {
            itemToUpdate.translations = { name_translations: { [langCode]: translated } };
          }
        } else {
          const labelMap = (data.translations && data.translations.label_translations) || {};
          const defMap = (data.translations && data.translations.definition_translations) || {};
          const labelVal = labelMap[langCode];
          const defVal = defMap[langCode];
          if (labelVal) {
            // Prefer nested maps so server merges cleanly
            itemToUpdate.translations.label_translations = { [langCode]: labelVal };
          }
          if (defVal) {
            const isPlugin = typeof item.type === 'string' && item.type.startsWith('plugin_');
            if (item.type === 'document_field' || item.type === 'matrix' || isPlugin) {
              itemToUpdate.translations.description_translations = { [langCode]: defVal };
            } else {
              itemToUpdate.translations.definition_translations = { [langCode]: defVal };
            }
          }
        }

        if (Object.keys(itemToUpdate.translations).length === 0) {
          modal.translationState.errorCount++;
          modal.logProgress(`No translations received for item ${item.id}`, 'error');
          modal.updateProgress();
          setTimeout(() => processItemsSequentially(items, index + 1, selectedService, endpoints), 80);
          return;
        }

        fetchJson(endpoints.bulkUpdateTranslations, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': (document.querySelector('meta[name=csrf-token]')?.getAttribute('content') || '')
          },
          body: JSON.stringify({ items: [itemToUpdate] })
        }).then(saveData => {
            if (saveData.success) {
              modal.translationState.successCount++;
              modal.logProgress(`Translated and saved item ${item.id} to ${item.language}`, 'success');
            } else {
              modal.translationState.errorCount++;
              const saveMsg = saveData.error || saveData.message || 'Unknown error';
              modal.translationState.errors.push(`Translated but failed to save item ${item.id} to ${item.language}: ${saveMsg}`);
              modal.logProgress(`Translated but failed to save item ${item.id} to ${item.language}: ${saveMsg}`, 'error');
            }
            modal.updateProgress();
            setTimeout(() => processItemsSequentially(items, index + 1, selectedService, endpoints), 80);
          })
          .catch(err => {
            modal.translationState.errorCount++;
            modal.translationState.errors.push(`Translated but network error saving item ${item.id}: ${err.message}`);
            modal.logProgress(`Translated but network error saving item ${item.id}: ${err.message}`, 'error');
            modal.updateProgress();
            setTimeout(() => processItemsSequentially(items, index + 1, selectedService, endpoints), 80);
          });
      } else {
        modal.translationState.errorCount++;
        const translateMsg = data.error || data.message || 'Unknown error';
        modal.translationState.errors.push(`Failed to translate item ${item.id} to ${item.language}: ${translateMsg}`);
        modal.logProgress(`Failed to translate item ${item.id} to ${item.language}: ${translateMsg}`, 'error');
        modal.updateProgress();
        setTimeout(() => processItemsSequentially(items, index + 1, selectedService, endpoints), 80);
      }
    })
    .catch(err => {
      modal.translationState.processedItems++;
      modal.translationState.errorCount++;
      modal.translationState.errors.push(`Network error for item ${item.id}: ${err.message}`);
      modal.logProgress(`Network error for item ${item.id}: ${err.message}`, 'error');
      modal.updateProgress();
      setTimeout(() => processItemsSequentially(items, index + 1, selectedService, endpoints), 100);
    });
}

function exposePageFunctions() {
  window.getPageSpecificTranslationCounts = function() {
    try { return computeCounts(); } catch (e) { return {}; }
  };

  window.performPageSpecificTranslation = function(selectedLanguages, selectedService) {
    const modal = window.autoTranslateModal;
    const endpoints = getEndpoints();
    const { items } = buildItemsToTranslate(selectedLanguages);
    if (!items.length) {
      modal.logProgress('No items found that need translation', 'info');
      modal.translationState.isRunning = false;
      jQuery('#auto-translate-pause-btn').addClass('hidden');
      jQuery('#auto-translate-resume-btn').addClass('hidden');
      jQuery('#auto-translate-stop-btn').addClass('hidden');
      jQuery('#auto-translate-close-btn').removeClass('hidden');
      return;
    }
    modal.translationState.totalItems = items.length;
    modal.updateProgress();
    processItemsSequentially(items, 0, selectedService, endpoints);
  };
}

document.addEventListener('DOMContentLoaded', exposePageFunctions);

export {};
