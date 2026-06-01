// indicator-bank-translations.js — translation modals for indicator bank add/edit forms

const TRANSLATION_FIELDS = [
  {
    openButtonId: 'indicator-name-translations-btn',
    modalId: 'indicator-name-translations-modal',
    cssPrefix: 'indicator-name',
    fieldPrefix: 'name',
    englishFieldId: 'name',
  },
  {
    openButtonId: 'indicator-aggregated-label-translations-btn',
    modalId: 'indicator-aggregated-label-translations-modal',
    cssPrefix: 'indicator-aggregated-label',
    fieldPrefix: 'aggregated_label',
    englishFieldId: 'aggregated_label',
  },
];

function collectTranslationsFromHidden(fieldPrefix) {
  const translations = {};
  document.querySelectorAll(`input[type="hidden"][name^="${fieldPrefix}_"]`).forEach((inp) => {
    const code = inp.name.slice(fieldPrefix.length + 1);
    if (code && code !== 'en') {
      translations[code] = inp.value || '';
    }
  });
  return translations;
}

function syncHiddenFields(fieldPrefix, collected) {
  Object.keys(collected || {}).forEach((code) => {
    const field = document.querySelector(`input[type="hidden"][name="${fieldPrefix}_${code}"]`);
    if (field) {
      field.value = collected[code] || '';
    }
  });
}

function showSavedFeedback(btnId) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  const originalNodes = Array.from(btn.childNodes).map((n) => n.cloneNode(true));
  btn.replaceChildren();
  const icon = document.createElement('i');
  icon.className = 'fas fa-check w-4 h-4';
  icon.setAttribute('aria-hidden', 'true');
  btn.append(icon);
  btn.classList.add('text-green-600');
  setTimeout(() => {
    btn.replaceChildren(...originalNodes.map((n) => n.cloneNode(true)));
    btn.classList.remove('text-green-600');
  }, 2000);
}

function attachIndicatorBankTranslationField(cfg) {
  if (!document.getElementById(cfg.openButtonId) || !window.TranslationModal) {
    return;
  }

  window.TranslationModal.attach({
    openButtonId: cfg.openButtonId,
    modalId: cfg.modalId,
    cssPrefix: cfg.cssPrefix,
    resolveEnglishText: () => {
      const el = document.getElementById(cfg.englishFieldId);
      return el ? String(el.value || '').trim() : '';
    },
    onSaveHiddenFields: (collected) => {
      syncHiddenFields(cfg.fieldPrefix, collected);
      showSavedFeedback(cfg.openButtonId);
    },
    autoTranslateType: 'form_item',
    onModalOpen: () => {
      const translations = collectTranslationsFromHidden(cfg.fieldPrefix);
      if (window.TranslationModalUtils) {
        window.TranslationModalUtils.populateFields(cfg.cssPrefix, translations);
      }
    },
  });
}

export function initIndicatorBankTranslations() {
  TRANSLATION_FIELDS.forEach(attachIndicatorBankTranslationField);
}
