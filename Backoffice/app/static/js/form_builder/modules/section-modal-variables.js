/**
 * Section Modal Variable Autocomplete
 *
 * Suggests template variables when typing "[" in the section name input.
 * Uses `window.templateVariables` (already present on the form builder page).
 *
 * CSP-safe: no inline handlers, no innerHTML assignment.
 */

function hideSuggestions(containerEl) {
  if (!containerEl) return;
  containerEl.querySelectorAll('.variable-suggestions').forEach((el) => el.remove());
}

function showSuggestions({ input, partialMatch, bracketPos, containerEl }) {
  hideSuggestions(containerEl);

  const templateVariables = window.templateVariables || {};
  const variableNames = Object.keys(templateVariables);
  const metadata = Array.isArray(window.builtInMetadataVariables) ? window.builtInMetadataVariables : [];
  const pluginVars = Array.isArray(window.pluginLabelVariables) ? window.pluginLabelVariables : [];

  const suggestionsSource = [
    ...metadata.map((m) => ({ key: String(m.key || ''), label: String(m.label || ''), kind: 'metadata' })),
    ...variableNames.map((name) => ({ key: String(name), label: String(templateVariables?.[name]?.display_name || ''), kind: 'variable' })),
    ...pluginVars.map((p) => ({ key: String(p.key || ''), label: String(p.label || ''), kind: 'plugin' })),
  ].filter((s) => s.key);

  if (suggestionsSource.length === 0) return;

  const matches = suggestionsSource
    .filter((s) => String(s.key).toLowerCase().startsWith(String(partialMatch || '').toLowerCase()))
    .slice(0, 50);

  if (matches.length === 0) return;

  const dropdown = document.createElement('div');
  dropdown.className =
    'variable-suggestions absolute z-50 bg-white border border-gray-300 rounded-md shadow-lg max-h-48 overflow-y-auto';

  matches.forEach(({ key, label, kind }) => {
    const item = document.createElement('div');
    item.className = 'px-3 py-2 hover:bg-blue-100 cursor-pointer text-sm';
    const suffix = kind === 'metadata' ? ` — ${label || key}` : (label ? ` — ${label}` : '');
    item.textContent = `[${key}]${suffix}`;
    item.addEventListener('click', () => {
      const text = input.value || '';
      const textBeforeBracket = text.substring(0, bracketPos);
      const textAfterCursor = text.substring(input.selectionStart || 0);
      input.value = textBeforeBracket + `[${key}]` + textAfterCursor;
      input.focus();
      const newPos = bracketPos + String(key).length + 2; // [ + name + ]
      try {
        input.setSelectionRange(newPos, newPos);
      } catch (_e) {
        // no-op
      }
      dropdown.remove();
    });
    dropdown.appendChild(item);
  });

  // Position within the modal content (relative container)
  const inputRect = input.getBoundingClientRect();
  const containerRect = containerEl.getBoundingClientRect();
  dropdown.style.top = `${inputRect.bottom - containerRect.top}px`;
  dropdown.style.left = `${inputRect.left - containerRect.left}px`;
  dropdown.style.minWidth = `${inputRect.width}px`;
  dropdown.style.maxWidth = '520px';

  containerEl.appendChild(dropdown);
}

function attachSectionModalVariableAutocomplete() {
  document.addEventListener('input', (e) => {
    const target = e.target;
    if (!(target instanceof HTMLInputElement)) return;
    if (target.id !== 'section-name-input') return;

    const modalOverlay = target.closest('#section-modal');
    if (!modalOverlay) return;
    if (modalOverlay.classList.contains('hidden')) return;

    const modalContent = modalOverlay.querySelector('#section-modal-content') || modalOverlay;

    const cursorPos = target.selectionStart ?? (target.value || '').length;
    const text = target.value || '';
    const textBeforeCursor = text.substring(0, cursorPos);

    const lastBracket = textBeforeCursor.lastIndexOf('[');
    if (lastBracket === -1) {
      hideSuggestions(modalContent);
      return;
    }

    const textAfterBracket = textBeforeCursor.substring(lastBracket + 1);
    // Still inside an opening bracket with no closing bracket yet
    if (!textAfterBracket.includes(']')) {
      showSuggestions({
        input: target,
        partialMatch: textAfterBracket,
        bracketPos: lastBracket,
        containerEl: modalContent,
      });
    } else {
      hideSuggestions(modalContent);
    }
  });

  // Click outside closes
  document.addEventListener('click', (e) => {
    const modalOverlay = e.target && e.target.closest ? e.target.closest('#section-modal') : null;
    if (!modalOverlay || modalOverlay.classList.contains('hidden')) {
      document.querySelectorAll('#section-modal .variable-suggestions').forEach((el) => el.remove());
      return;
    }

    const modalContent = modalOverlay.querySelector('#section-modal-content') || modalOverlay;
    const dropdown = modalContent.querySelector('.variable-suggestions');
    if (dropdown && !dropdown.contains(e.target)) {
      dropdown.remove();
    }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', attachSectionModalVariableAutocomplete, { once: true });
} else {
  attachSectionModalVariableAutocomplete();
}
