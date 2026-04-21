// translation-utils.js - Shared utilities for translation modals and matrices

/** Read JSON from a script/data element by id. Use across translation modules instead of duplicating. */
export function readJson(elementId, fallback) {
  try {
    const el = document.getElementById(elementId);
    if (!el || !el.textContent) return fallback;
    return JSON.parse(el.textContent);
  } catch (e) {
    return fallback;
  }
}

if (typeof window !== 'undefined') {
  window.readJson = readJson;
}

export const TranslationUtils = (() => {
  const readJsonFromElement = readJson;

  // Load supported languages and display names from the page JSON payload
  const translationData = readJsonFromElement('translation-data', {
    supportedLanguages: ['en'],
    languageDisplayNames: { en: 'English' }
  });

  const supportedLanguages = Array.isArray(translationData.supportedLanguages)
    ? translationData.supportedLanguages
    : ['en'];

  const languageDisplayNames = translationData.languageDisplayNames || { en: 'English' };

  function getTargetLanguages() {
    return supportedLanguages.filter(code => code !== 'en');
  }

  function showAutoTranslateError(button, originalText, errorMessage, optionsOrNodes) {
    try { console.error('Auto-translate error:', errorMessage); } catch (_) {}
    if (!button) return;

    const opts = (optionsOrNodes && !Array.isArray(optionsOrNodes) && typeof optionsOrNodes === 'object')
      ? optionsOrNodes
      : {};
    const explicitNodes = Array.isArray(optionsOrNodes)
      ? optionsOrNodes
      : (Array.isArray(opts.originalNodes) ? opts.originalNodes : null);
    const originalNodes = explicitNodes || Array.from(button.childNodes).map((n) => n.cloneNode(true));
    const restoreDelayMs = Number.isFinite(opts.restoreDelayMs) ? opts.restoreDelayMs : 3000;
    const alertOnError = opts.alertOnError !== false;

    const restore = () => {
      // Prefer restoring the original DOM nodes when possible; fall back to text.
      if (originalNodes.length > 0) {
        button.replaceChildren(...originalNodes.map((n) => n.cloneNode(true)));
      } else {
        button.textContent = String(originalText || '');
      }
    };
    button.replaceChildren();
    {
      const icon = document.createElement('i');
      icon.className = 'fas fa-exclamation-triangle w-4 h-4 mr-2 text-red-500';
      button.append(icon, document.createTextNode('Translation Failed'));
    }
    button.classList.add('bg-red-600', 'hover:bg-red-700');
    button.classList.remove('bg-green-600', 'hover:bg-green-700');
    setTimeout(() => {
      restore();
      button.disabled = false;
      button.classList.remove('bg-red-600', 'hover:bg-red-700');
      button.classList.add('bg-green-600', 'hover:bg-green-700');
    }, restoreDelayMs);
    if (alertOnError) {
      if (window.showAlert) window.showAlert('Translation failed: ' + errorMessage, 'error');
    }
  }

  function handleAutoTranslateResponse(response) {
    if (!response) {
      throw new Error('No response from translation service');
    }

    const parseJsonSafe = () =>
      response
        .clone()
        .json()
        .catch(() => ({}));

    if (!response.ok) {
      return parseJsonSafe().then(data => {
        const message =
          (data && data.message) ||
          `HTTP ${response.status}: ${response.statusText || 'Unknown error'}`;
        throw (window.httpErrorSync && window.httpErrorSync(response, message)) || new Error(message);
      });
    }

    const contentType = String(response.headers && response.headers.get && response.headers.get('content-type') || '').toLowerCase();
    if (!contentType.includes('application/json')) {
      // Commonly happens when a WAF/proxy returns an HTML block page.
      return response
        .text()
        .then(t => {
          const snippet = (t || '').slice(0, 200).replace(/\s+/g, ' ').trim();
          const msg = snippet ? `Auto-translate failed (non-JSON response): ${snippet}` : 'Auto-translate failed (non-JSON response)';
          throw new Error(msg);
        });
    }

    return response.json().then(data => {
      if (!data.success) {
        throw new Error(data.message || 'Translation failed');
      }
      return data;
    });
  }

  // Populate translation inputs within a modal for a given cssPrefix
  function populateFields(cssPrefix, translations, baseEnglishText = '', fieldSuffix = '') {
    const suffix = fieldSuffix ? `-${fieldSuffix}` : '';
    supportedLanguages.forEach(langCode => {
      if (langCode === 'en') return;
      const fieldId = `${cssPrefix}-translation${suffix}-${langCode}`;
      const field = document.getElementById(fieldId);
      if (field) field.value = (translations && translations[langCode]) || '';
    });
  }

  function collectFields(cssPrefix, fieldSuffix = '') {
    const translations = {};
    const suffix = fieldSuffix ? `-${fieldSuffix}` : '';
    supportedLanguages.forEach(langCode => {
      if (langCode === 'en') return;
      const fieldId = `${cssPrefix}-translation${suffix}-${langCode}`;
      const field = document.getElementById(fieldId);
      if (field) translations[langCode] = field.value || '';
    });
    return translations;
  }

  function clearFields(cssPrefix, fieldSuffix = '') {
    const suffix = fieldSuffix ? `-${fieldSuffix}` : '';
    supportedLanguages.forEach(langCode => {
      if (langCode === 'en') return;
      const fieldId = `${cssPrefix}-translation${suffix}-${langCode}`;
      const field = document.getElementById(fieldId);
      if (field) field.value = '';
    });
  }

  function generateMatrixCells(translations = {}) {
    return supportedLanguages
      .filter(code => code !== 'en')
      .map(code => {
        const displayName = languageDisplayNames[code] || code.toUpperCase();
        const value = translations[code] || '';
        return (
          `<td class="px-4 py-2 border-r border-gray-300">` +
          `<textarea class="w-full text-sm border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500" rows="2" data-language="${code}" placeholder="${displayName} translation">${value}</textarea>` +
          `</td>`
        );
      })
      .join('');
  }

  const api = {
    supportedLanguages,
    languageDisplayNames,
    getTargetLanguages,
    showAutoTranslateError,
    handleAutoTranslateResponse,
    populateFields,
    collectFields,
    clearFields,
    generateMatrixCells
  };

  // Keep legacy global for existing consumers
  try { window.TranslationModalUtils = api; } catch (_) {}

  return api;
})();

export default TranslationUtils;
