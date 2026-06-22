export const VariableAutocompleteMixin = {
    setupVariableAutocomplete: function() {
        // Use event delegation since modal might not be visible when this runs
        document.addEventListener('input', (e) => {
            // Check if the input allows template variables (e.g. labels, default value inputs)
            const allowVariables = (e.target?.dataset?.enableVariables === 'true');

            // Check if the input is a label field (legacy behavior)
            const isLabelField = e.target.hasAttribute('data-field-type') &&
                                e.target.getAttribute('data-field-type') === 'label';
            const isLabelFieldById = ['item-indicator-label', 'item-question-label',
                                     'item-document-label', 'item-matrix-label',
                                     'item-plugin-label'].includes(e.target.id);

            if (!allowVariables && !isLabelField && !isLabelFieldById) return;

            // Check if input is in the item modal
            const modal = e.target.closest('#item-modal');
            if (!modal) return;

            const input = e.target;
            const cursorPos = input.selectionStart;
            const text = input.value;

            // Check if user is typing a variable (starts with [)
            const textBeforeCursor = text.substring(0, cursorPos);
            const lastBracket = textBeforeCursor.lastIndexOf('[');

            if (lastBracket !== -1) {
                const textAfterBracket = textBeforeCursor.substring(lastBracket + 1);
                // Check if we're still inside brackets (no closing bracket yet)
                if (!textAfterBracket.includes(']')) {
                    // Show variable suggestions
                    this.showVariableSuggestions(input, textAfterBracket, lastBracket, modal);
                } else {
                    this.hideVariableSuggestions(modal);
                }
            } else {
                this.hideVariableSuggestions(modal);
            }
        });

        // Handle clicks outside to close suggestions
        document.addEventListener('click', (e) => {
            const modal = e.target.closest('#item-modal');
            if (!modal) {
                // Close suggestions in all modals
                document.querySelectorAll('#item-modal .variable-suggestions').forEach(s => s.remove());
                return;
            }
            const suggestions = modal.querySelectorAll('.variable-suggestions');
            suggestions.forEach(suggestion => {
                if (!suggestion.contains(e.target)) {
                    suggestion.remove();
                }
            });
        });
    },

    showVariableSuggestions: function(input, partialMatch, bracketPos, modal) {
        // Remove existing suggestions
        this.hideVariableSuggestions(modal);

        // Get available variables: metadata, manual template variables, plugin label variables
        const templateVariables = window.templateVariables || {};
        const variableNames = Object.keys(templateVariables);
        const metadata = Array.isArray(window.builtInMetadataVariables) ? window.builtInMetadataVariables : [];
        const pluginVars = Array.isArray(window.pluginLabelVariables) ? window.pluginLabelVariables : [];

        const suggestionsSource = [
            ...metadata.map(m => ({ key: String(m.key || ''), label: String(m.label || ''), kind: 'metadata' })),
            ...variableNames.map(name => ({ key: String(name), label: String(templateVariables?.[name]?.display_name || ''), kind: 'variable' })),
            ...pluginVars.map(p => ({ key: String(p.key || ''), label: String(p.label || ''), kind: 'plugin' })),
        ].filter(s => s.key);

        // Filter variables that match the partial text
        const matches = suggestionsSource.filter(s =>
            s.key.toLowerCase().startsWith(String(partialMatch || '').toLowerCase())
        );

        if (matches.length === 0) return;

        // Create suggestions dropdown
        const suggestions = document.createElement('div');
        suggestions.className = 'variable-suggestions absolute z-50 bg-white border border-gray-300 rounded-md shadow-lg max-h-48 overflow-y-auto';

        matches.slice(0, 50).forEach(({ key, label, kind }) => {
            const item = document.createElement('div');
            item.className = 'px-3 py-2 hover:bg-blue-100 cursor-pointer text-sm';
            const suffix = kind === 'metadata' ? ` — ${label || key}` : (label ? ` — ${label}` : '');
            item.textContent = `[${key}]${suffix}`;
            item.addEventListener('click', () => {
                const text = input.value;
                const textBeforeBracket = text.substring(0, bracketPos);
                const textAfterCursor = text.substring(input.selectionStart);
                input.value = textBeforeBracket + `[${key}]` + textAfterCursor;
                input.focus();
                input.setSelectionRange(bracketPos + key.length + 2, bracketPos + key.length + 2);
                suggestions.remove();
            });
            suggestions.appendChild(item);
        });

        // Position relative to input field
        const inputRect = input.getBoundingClientRect();
        const modalRect = modal.getBoundingClientRect();
        suggestions.style.position = 'absolute';
        suggestions.style.top = (inputRect.bottom - modalRect.top + modal.scrollTop) + 'px';
        suggestions.style.left = (inputRect.left - modalRect.left) + 'px';
        suggestions.style.minWidth = inputRect.width + 'px';
        suggestions.style.maxWidth = '400px';

        modal.appendChild(suggestions);
    },

    hideVariableSuggestions: function(modal) {
        if (!modal) return;
        const suggestions = modal.querySelectorAll('.variable-suggestions');
        suggestions.forEach(suggestion => suggestion.remove());
    },
};
