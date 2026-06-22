/**
 * Variable Formatting Module
 * Handles formatting and display of [variable] patterns in the UI
 */

export class VariableFormatter {
    /**
     * Parse an internally-generated formatted HTML string into DOM nodes,
     * without assigning to element.innerHTML.
     *
     * The input is expected to be produced by `formatVariablesInText()` (not raw user HTML).
     */
    static _appendFormattedHtml(container, formattedHtml) {
        if (!container) return;
        if (typeof formattedHtml !== 'string' || !formattedHtml.trim()) return;

        const doc = new DOMParser().parseFromString(formattedHtml, 'text/html');
        const root = doc.body;
        if (!root) return;

        // Defensive: remove active content if ever introduced.
        root.querySelectorAll('script, iframe, object, embed').forEach((el) => el.remove());
        root.querySelectorAll('*').forEach((el) => {
            [...el.attributes].forEach((attr) => {
                const name = String(attr.name || '').toLowerCase();
                if (name.startsWith('on')) el.removeAttribute(attr.name);
            });
        });

        const fragment = document.createDocumentFragment();
        while (root.firstChild) fragment.appendChild(root.firstChild);
        container.appendChild(fragment);
    }

    /**
     * Checks if a text node is already inside a formatted variable span
     * @param {Text} textNode - The text node to check
     * @returns {boolean} - True if already inside formatted variable
     */
    static isInsideFormattedVariable(textNode) {
        let parent = textNode.parentNode;
        while (parent && parent !== document.body) {
            if (parent.classList && parent.classList.contains('variable-formatted')) {
                return true;
            }
            parent = parent.parentNode;
        }
        return false;
    }

    /**
     * Formats [variable] patterns and formulas like [[variable]+1] in text with purple badge style
     * @param {string} text - The text to format
     * @returns {string} - HTML string with formatted variables
     */
    static formatVariablesInText(text) {
        if (!text || typeof text !== 'string') return text;

        // First, match formulas like [[variable]+1], [[variable]*2], etc.
        // Pattern: [[variable_name] followed by operator and number, then closing bracket]
        const formulaPattern = /\[\[([a-zA-Z_][a-zA-Z0-9_]*)\]([+\-*/]\d+(?:\.\d+)?)\]/g;

        let result = text;

        // Replace formulas first
        result = result.replace(formulaPattern, (match, varName, formulaExpr) => {
            return `<span class="inline-flex items-center px-2 py-0.5 rounded-md bg-purple-100 text-purple-700 font-medium variable-formatted">
                <i class="fas fa-bolt w-3 h-3 mr-1"></i>
                <span>[[${varName}]${formulaExpr}]</span>
            </span>`;
        });

        // Then match simple [variable] patterns (variable name can contain letters, numbers, underscores)
        // But skip if already inside a formatted variable span (e.g., inside a formula we just formatted)
        const variablePattern = /\[([a-zA-Z_][a-zA-Z0-9_]*)\]/g;

        // We need to track which positions have already been processed as part of formulas
        // to avoid double-processing. Let's use a different approach: process matches in reverse
        // and check the context more carefully.
        const matches = [];
        let match;
        variablePattern.lastIndex = 0; // Reset regex
        while ((match = variablePattern.exec(result)) !== null) {
            matches.push({
                match: match[0],
                varName: match[1],
                offset: match.index,
                fullMatch: match
            });
        }

        // Process matches in reverse order to avoid offset issues
        for (let i = matches.length - 1; i >= 0; i--) {
            const { match: matchText, varName, offset } = matches[i];

            // Check if this [variable] is inside a formatted formula's inner span
            // Formula structure: <span class="variable-formatted"><i>...</i><span>[[variable]+1]</span></span>
            const beforeMatch = result.substring(0, offset);
            const fullText = result;

            let shouldSkip = false;

            // Find the last simple <span> (inner content span) before our match
            const lastSimpleSpanIndex = beforeMatch.lastIndexOf('<span>');
            if (lastSimpleSpanIndex !== -1) {
                // Check if this simple span is inside a variable-formatted span
                const beforeSimpleSpan = beforeMatch.substring(0, lastSimpleSpanIndex);
                const lastVarFormattedSpan = beforeSimpleSpan.lastIndexOf('<span');
                if (lastVarFormattedSpan !== -1) {
                    const spanTag = beforeSimpleSpan.substring(lastVarFormattedSpan);
                    if (spanTag.includes('variable-formatted')) {
                        // Extract the content of the inner span to verify it's a formula
                        const innerSpanStart = lastSimpleSpanIndex + 6; // +6 for '<span>'
                        const innerSpanContent = fullText.substring(innerSpanStart);
                        const innerSpanEnd = innerSpanContent.indexOf('</span>');
                        if (innerSpanEnd !== -1) {
                            const innerContent = innerSpanContent.substring(0, innerSpanEnd);
                            // Remove HTML tags to get just the text
                            const textContent = innerContent.replace(/<[^>]*>/g, '');
                            // If the text starts with [[, it's a formula
                            if (textContent.trim().startsWith('[[')) {
                                // Check if our match position is inside this inner span
                                if (offset >= innerSpanStart && offset < innerSpanStart + innerSpanEnd) {
                                    shouldSkip = true;
                                }
                            }
                        }
                    }
                }
            }

            if (!shouldSkip) {
                const replacement = `<span class="inline-flex items-center px-2 py-0.5 rounded-md bg-purple-100 text-purple-700 font-medium variable-formatted">
                <i class="fas fa-bolt w-3 h-3 mr-1"></i>
                <span>[${varName}]</span>
            </span>`;
                result = result.substring(0, offset) + replacement + result.substring(offset + matchText.length);
            }
        }

        return result;
    }

    /**
     * Processes a text node and replaces variables with formatted HTML
     * @param {Text} textNode - The text node to process
     */
    static processTextNode(textNode) {
        // Skip if already inside a formatted variable
        if (this.isInsideFormattedVariable(textNode)) return;

        const text = textNode.textContent;
        // Check for both simple variables [variable] and formulas [[variable]+1]
        if (!text || !text.includes('[') || !text.includes(']')) return;

        // Check if text contains unformatted variables (not already in HTML)
        // Check for both simple variables and formulas
        const formulaPattern = /\[\[([a-zA-Z_][a-zA-Z0-9_]*)\]([+\-*/]\d+(?:\.\d+)?)\]/g;
        const variablePattern = /\[([a-zA-Z_][a-zA-Z0-9_]*)\]/g;
        const hasFormula = formulaPattern.test(text);
        const hasVariable = variablePattern.test(text);
        if (!hasFormula && !hasVariable) return;

        const formatted = this.formatVariablesInText(text);
        if (formatted === text) return;

        const parent = textNode.parentNode;
        if (!parent) return;

        // Skip if parent is already a formatted variable span
        if (parent.classList && parent.classList.contains('variable-formatted')) return;

        const tempDiv = document.createElement('div');
        this._appendFormattedHtml(tempDiv, formatted);

        // Insert all formatted nodes before the original text node
        while (tempDiv.firstChild) {
            parent.insertBefore(tempDiv.firstChild, textNode);
        }

        // Remove the original text node
        parent.removeChild(textNode);
    }

    /**
     * Processes all section names to format variables
     */
    static formatVariablesInSectionNames() {
        // Find all section name elements (main sections and subsections)
        // Main sections: h3 elements inside .section-item containers
        // Sub-sections: span elements with font-semibold class inside table rows with bg-teal-50
        const mainSectionNames = document.querySelectorAll('.section-item h3');
        const subSectionNames = document.querySelectorAll('tr.bg-teal-50 td span.font-semibold');
        const sectionNameElements = [...mainSectionNames, ...subSectionNames];

        sectionNameElements.forEach(element => {
            // Skip if already processed
            if (element.dataset.variablesFormatted === 'true') return;

            // Find all text nodes in the element
            const walker = document.createTreeWalker(
                element,
                NodeFilter.SHOW_TEXT,
                {
                    acceptNode: function(node) {
                        // Skip if already inside formatted variable
                        if (VariableFormatter.isInsideFormattedVariable(node)) {
                            return NodeFilter.FILTER_REJECT;
                        }
                        return NodeFilter.FILTER_ACCEPT;
                    }
                },
                false
            );

            const textNodes = [];
            let node;
            while (node = walker.nextNode()) {
                const text = node.textContent || '';
                // Check for both simple variables [variable] and formulas [[variable]+1]
                if (text.includes('[') && text.includes(']')) {
                    textNodes.push(node);
                }
            }

            // Process text nodes in reverse to avoid index issues
            textNodes.reverse().forEach(node => this.processTextNode(node));

            // Mark element as processed
            element.dataset.variablesFormatted = 'true';
        });
    }

    /**
     * Processes all item labels and configs to format variables
     */
    static formatVariablesInItemLabels() {
        // Find all table rows containing items
        const itemRows = document.querySelectorAll('table tbody tr');

        itemRows.forEach(row => {
            // Skip if row is already marked as processed
            if (row.dataset.variablesFormatted === 'true') return;

            // Process label column (second column, index 1)
            const labelCell = row.querySelector('td:nth-child(2)');
            if (labelCell && !labelCell.dataset.variablesFormatted) {
                // Find all text nodes in the label cell
                const walker = document.createTreeWalker(
                    labelCell,
                    NodeFilter.SHOW_TEXT,
                    {
                        acceptNode: function(node) {
                            // Skip if already inside formatted variable
                            if (VariableFormatter.isInsideFormattedVariable(node)) {
                                return NodeFilter.FILTER_REJECT;
                            }
                            return NodeFilter.FILTER_ACCEPT;
                        }
                    },
                    false
                );

                const textNodes = [];
                let node;
                while (node = walker.nextNode()) {
                    const text = node.textContent || '';
                    // Check for both simple variables [variable] and formulas [[variable]+1]
                    if ((text.includes('[') && text.includes(']')) ||
                        (text.includes('(') && text.includes('[') && text.includes(']') && text.includes(')'))) {
                        textNodes.push(node);
                    }
                }

                // Process text nodes in reverse to avoid index issues
                textNodes.reverse().forEach(node => this.processTextNode(node));

                // Mark cell as processed
                labelCell.dataset.variablesFormatted = 'true';
            }

            // Process details column (third column, index 2)
            const detailCell = row.querySelector('td:nth-child(3)');
            if (detailCell && !detailCell.dataset.variablesFormatted) {
                // Find all text nodes in the detail cell
                const walker = document.createTreeWalker(
                    detailCell,
                    NodeFilter.SHOW_TEXT,
                    {
                        acceptNode: function(node) {
                            // Skip if already inside formatted variable
                            if (VariableFormatter.isInsideFormattedVariable(node)) {
                                return NodeFilter.FILTER_REJECT;
                            }
                            return NodeFilter.FILTER_ACCEPT;
                        }
                    },
                    false
                );

                const textNodes = [];
                let node;
                while (node = walker.nextNode()) {
                    const text = node.textContent || '';
                    // Check for both simple variables [variable] and formulas [[variable]+1]
                    if ((text.includes('[') && text.includes(']')) ||
                        (text.includes('(') && text.includes('[') && text.includes(']') && text.includes(')'))) {
                        textNodes.push(node);
                    }
                }

                // Process text nodes in reverse to avoid index issues
                textNodes.reverse().forEach(node => this.processTextNode(node));

                // Mark cell as processed
                detailCell.dataset.variablesFormatted = 'true';
            }

            // Mark row as processed
            row.dataset.variablesFormatted = 'true';
        });
    }

    /**
     * Extracts variables from a text string (including formulas)
     * @param {string} text - The text to extract variables from
     * @returns {Array} - Array of unique variable names
     */
    static extractVariables(text) {
        if (!text || typeof text !== 'string') return [];

        const variables = new Set();

        // First, extract from formulas like [[variable]+1]
        const formulaPattern = /\[\[([a-zA-Z_][a-zA-Z0-9_]*)\]([+\-*/]\d+(?:\.\d+)?)\]/g;
        let match;
        while ((match = formulaPattern.exec(text)) !== null) {
            variables.add(match[1]);
        }

        // Then extract simple [variable] patterns
        const variablePattern = /\[([a-zA-Z_][a-zA-Z0-9_]*)\]/g;
        while ((match = variablePattern.exec(text)) !== null) {
            variables.add(match[1]);
        }

        return Array.from(variables); // Return unique variables
    }

    /**
     * Recursively extracts variables from any object/array/value
     * @param {*} obj - The object/array/value to search
     * @param {Set} variables - Set to collect variables
     */
    static extractVariablesFromObject(obj, variables, depth = 0) {
        if (!obj) return;

        // Limit depth to avoid infinite recursion
        if (depth > 10) return;

        if (typeof obj === 'string') {
            const found = this.extractVariables(obj);
            found.forEach(v => variables.add(v));
        } else if (Array.isArray(obj)) {
            obj.forEach((item, index) => {
                this.extractVariablesFromObject(item, variables, depth + 1);
            });
        } else if (typeof obj === 'object') {
            Object.entries(obj).forEach(([key, value]) => {
                // Skip certain keys that are unlikely to contain variables
                if (key === 'id' || key === 'order' || key === 'type' && typeof value !== 'string') {
                    return;
                }
                this.extractVariablesFromObject(value, variables, depth + 1);
            });
        }
    }

    /**
     * Extracts variables from matrix config and displays them
     */
    static displayMatrixVariables() {
        let itemsData = [];

        // Try to get items from all-template-items-data first
        const templateItemsData = document.getElementById('all-template-items-data');
        if (templateItemsData) {
            const rawData = JSON.parse(templateItemsData.textContent);

            // Handle different data structures
            if (Array.isArray(rawData)) {
                itemsData = rawData;
            } else if (rawData && Array.isArray(rawData.form_items)) {
                itemsData = rawData.form_items;
            } else if (rawData && typeof rawData === 'object') {
                // Try to find items in the object
                Object.values(rawData).forEach(value => {
                    if (Array.isArray(value)) {
                        itemsData = itemsData.concat(value);
                    }
                });
            }
        } else {
            // Fallback: try sections-with-items-data
            const sectionsData = document.getElementById('sections-with-items-data');
            if (sectionsData) {
                const sections = JSON.parse(sectionsData.textContent);
                sections.forEach(section => {
                    if (section.form_items) {
                        itemsData = itemsData.concat(section.form_items);
                    }
                    if (section.indicators) {
                        itemsData = itemsData.concat(section.indicators);
                    }
                    if (section.questions) {
                        itemsData = itemsData.concat(section.questions);
                    }
                    if (section.document_fields) {
                        itemsData = itemsData.concat(section.document_fields);
                    }
                });
            }
        }

        if (itemsData.length === 0) {
            return;
        }

        // Check for matrix items - could be 'matrix' or 'matrix_table' or in form_items
        const matrixItems = itemsData.filter(item => {
            const itemType = item.item_type || item.type || '';
            const hasMatrixConfig = item.config && (item.config.matrix_config || item.config.type === 'matrix');
            return itemType === 'matrix' || itemType === 'matrix_table' || hasMatrixConfig;
        });

        // Also try to find matrix items from DOM - look for edit-matrix-item-btn buttons
        const matrixEditButtons = document.querySelectorAll('.edit-matrix-item-btn');

        matrixEditButtons.forEach(button => {
            const itemId = button.getAttribute('data-matrix-item-id');
            if (!itemId) return;

            // Check if we already have this item
            const existingItem = matrixItems.find(item => item.id == itemId);
            if (!existingItem) {
                // Try to get config from data attribute
                const matrixConfigAttr = button.getAttribute('data-matrix-config');
                if (matrixConfigAttr) {
                    try {
                        const config = JSON.parse(matrixConfigAttr);
                        matrixItems.push({
                            id: itemId,
                            config: config
                        });
                    } catch (e) {
                        // Silently fail
                    }
                }
            }
        });

        matrixItems.forEach(matrixItem => {
            const itemId = matrixItem.id;
            const container = document.querySelector(`.matrix-variables-container[data-item-id="${itemId}"]`);

            if (!container) {
                return;
            }

            const variablesList = container.querySelector('.matrix-variables-list');
            if (!variablesList) {
                return;
            }

            const allVariables = new Set();

            // Extract variables from matrix config only (not label/description - those are shown inline)
            // Check both config.matrix_config and direct config
            if (matrixItem.config) {
                let configToSearch = matrixItem.config;

                // If config has matrix_config wrapper, use that
                if (matrixItem.config.matrix_config) {
                    configToSearch = matrixItem.config.matrix_config;
                }

                // Recursively extract from the entire config (for [variable] patterns in strings)
                this.extractVariablesFromObject(configToSearch, allVariables);

                // Also specifically check columns array for variable type columns
                if (configToSearch.columns && Array.isArray(configToSearch.columns)) {
                    configToSearch.columns.forEach((column) => {
                        // Check for variable type columns - they have variable or variable_name fields
                        if (column.type === 'variable') {
                            if (column.variable && typeof column.variable === 'string') {
                                allVariables.add(column.variable);
                            }
                            if (column.variable_name && typeof column.variable_name === 'string') {
                                allVariables.add(column.variable_name);
                            }
                        }

                        // Also recursively extract from column (for [variable] patterns)
                        this.extractVariablesFromObject(column, allVariables);
                    });
                }
            }

            // Display variables if any found
            if (allVariables.size > 0) {
                container.style.display = 'block';
                variablesList.replaceChildren();
                Array.from(allVariables).sort().forEach(varName => {
                    const li = document.createElement('li');
                    li.className = 'text-sm';
                    const badge = document.createElement('span');
                    badge.className = 'inline-flex items-center px-2 py-0.5 rounded-md bg-purple-100 text-purple-700 font-medium';

                    const icon = document.createElement('i');
                    icon.className = 'fas fa-bolt w-3 h-3 mr-1';

                    const text = document.createElement('span');
                    text.textContent = `[${varName}]`;

                    badge.append(icon, text);
                    li.appendChild(badge);
                    variablesList.appendChild(li);
                });
            }
        });
    }

    /**
     * Initialize variable formatting on page load
     */
    static init() {
        this.formatVariablesInSectionNames();
        this.formatVariablesInItemLabels();
        // Delay to ensure DOM is fully rendered
        setTimeout(() => {
            this.displayMatrixVariables();
        }, 500);

        // Set up live previews for label fields in modals (e.g. item modal, edit question, plugins)
        this.initLabelFieldPreviews();

        // Also run after any dynamic content is added (e.g., when items are added/edited)
        // Use MutationObserver to watch for changes, but be more selective
        let reformatTimeout = null;
        const observer = new MutationObserver((mutations) => {
            let shouldReformat = false;
            mutations.forEach((mutation) => {
                // Only process if new nodes were added (not attribute changes)
                if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                    mutation.addedNodes.forEach((node) => {
                        // Only reformat if it's a new row or table structure
                        if (node.nodeType === 1 && (
                            node.tagName === 'TR' ||
                            (node.tagName === 'TABLE' && !node.dataset.variablesFormatted)
                        )) {
                            shouldReformat = true;
                        }
                    });
                }
            });

            // Debounce reformatting to avoid multiple rapid calls
            if (shouldReformat) {
                clearTimeout(reformatTimeout);
                reformatTimeout = setTimeout(() => {
                    this.formatVariablesInSectionNames();
                    this.formatVariablesInItemLabels();
                    this.displayMatrixVariables();
                }, 500);
            }
        });

        const sectionsContainer = document.getElementById('sections-container');
        if (sectionsContainer) {
            observer.observe(sectionsContainer, {
                childList: true,
                subtree: true,
                attributes: false  // Don't watch attribute changes
            });
        }
    }

    /**
     * Initialize live variable highlighting previews for label input fields
     * Works for any field with data-field-type="label" (item modal, edit question modal, plugins, etc.)
     */
    static initLabelFieldPreviews() {
        const LABEL_SELECTOR = '[data-field-type="label"]';

        const updatePreview = (field) => {
            if (!field) return;
            // Find a nearby preview container in the same block
            const containerParent = field.closest('.mb-4') || field.parentElement;
            if (!containerParent) return;
            const preview = containerParent.querySelector('.label-variable-preview');
            if (!preview) return;

            const value = field.value || '';
            if (!value) {
                preview.replaceChildren();
                preview.style.display = 'none';
                return;
            }

            // Reuse the main formatter so [period] and [[period]+1] get purple styling
            const formatted = this.formatVariablesInText(value);
            preview.replaceChildren();
            this._appendFormattedHtml(preview, formatted);
            preview.style.display = 'block';
        };

        const scanAndInit = () => {
            const fields = document.querySelectorAll(LABEL_SELECTOR);
            fields.forEach((field) => {
                // Avoid repeated work
                if (field.dataset.labelPreviewInitialized === 'true') {
                    return;
                }
                field.dataset.labelPreviewInitialized = 'true';
                updatePreview(field);
            });
        };

        // Initial scan after DOM is ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', scanAndInit, { once: true });
        } else {
            scanAndInit();
        }

        // Live updates as the user types in any label field
        document.addEventListener('input', (event) => {
            const target = event.target;
            if (!target || !(target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement)) {
                return;
            }
            if (target.getAttribute('data-field-type') !== 'label') {
                return;
            }
            updatePreview(target);
        });
    }
}
