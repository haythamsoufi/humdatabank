/**
 * Multiselect Dropdown Component
 * A reusable searchable multiselect dropdown component for any data type
 *
 * Usage:
 * const multiselect = new MultiselectDropdown({
 *     containerId: 'my-container',
 *     name: 'my-field',
 *     placeholder: 'Select items...',
 *     searchPlaceholder: 'Search items...',
 *     data: [
 *         { value: '1', label: 'Item 1', sublabel: 'Optional sublabel' },
 *         { value: '2', label: 'Item 2' }
 *     ],
 *     selectedValues: ['1'],
 *     onSelectionChange: (selectedValues, selectedItems) => {
 *         console.log('Selection changed:', selectedValues, selectedItems);
 *     }
 * });
 */

class MultiselectDropdown {
    constructor(options = {}) {
        this.options = {
            containerId: null,
            name: 'multiselect',
            placeholder: 'Select items...',
            searchPlaceholder: 'Search items...',
            data: [],
            selectedValues: [],
            onSelectionChange: null,
            showSelectAll: true,
            maxHeight: '240px', // max-h-60 equivalent
            searchable: true,
            /** When true, only one option may be selected (e.g. single-ID filters). */
            singleSelect: false,
            ...options
        };

        this.container = null;
        this.elements = {};
        this.selectedValues = new Set(this.options.selectedValues || []);

        this.init();
    }

    init() {
        this.container = document.getElementById(this.options.containerId);
        if (!this.container) {
            console.error(`MultiselectDropdown: Container with id '${this.options.containerId}' not found`);
            return;
        }

        this.render();
        this.bindEvents();
        this.updateSelectedText();
    }

    render() {
        // Build dropdown structure using DOM construction
        const wrapper = document.createElement('div');
        wrapper.className = 'relative';

        const toggleBtn = document.createElement('button');
        toggleBtn.type = 'button';
        toggleBtn.className = 'multiselect-toggle w-full bg-white border border-gray-300 rounded-md shadow-sm px-3 py-2 text-left text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 hover:border-gray-400';

        const selectedText = document.createElement('span');
        selectedText.className = 'multiselect-selected-text';
        selectedText.textContent = this.options.placeholder;

        const chevronSpan = document.createElement('span');
        chevronSpan.className = 'absolute inset-y-0 right-0 flex items-center pr-2 pointer-events-none';
        const chevronSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        chevronSvg.setAttribute('class', 'h-5 w-5 text-gray-400');
        chevronSvg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
        chevronSvg.setAttribute('viewBox', '0 0 20 20');
        chevronSvg.setAttribute('fill', 'currentColor');
        const chevronPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        chevronPath.setAttribute('fill-rule', 'evenodd');
        chevronPath.setAttribute('d', 'M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z');
        chevronPath.setAttribute('clip-rule', 'evenodd');
        chevronSvg.appendChild(chevronPath);
        chevronSpan.appendChild(chevronSvg);

        toggleBtn.appendChild(selectedText);
        toggleBtn.appendChild(chevronSpan);

        const dropdown = document.createElement('div');
        dropdown.className = 'multiselect-dropdown hidden absolute z-10 mt-1 w-full bg-white border border-gray-300 rounded-md shadow-lg overflow-hidden';
        dropdown.style.maxHeight = this.options.maxHeight;
        dropdown.style.overflowY = 'auto';

        const dropdownInner = document.createElement('div');
        dropdownInner.className = 'p-2';

        if (this.options.searchable) {
            const searchInput = document.createElement('input');
            searchInput.type = 'text';
            searchInput.className = 'multiselect-search w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 mb-2';
            searchInput.placeholder = this.options.searchPlaceholder;
            dropdownInner.appendChild(searchInput);
        }

        const optionsContainer = document.createElement('div');
        optionsContainer.className = 'multiselect-options space-y-1';
        this.renderOptionsToContainer(optionsContainer);
        dropdownInner.appendChild(optionsContainer);

        if (this.options.showSelectAll) {
            const selectAllDiv = document.createElement('div');
            selectAllDiv.className = 'border-t border-gray-200 mt-2 pt-2';
            const buttonsDiv = document.createElement('div');
            buttonsDiv.className = 'flex space-x-2';

            const selectAllBtn = document.createElement('button');
            selectAllBtn.type = 'button';
            selectAllBtn.className = 'multiselect-select-all text-xs text-blue-600 hover:text-blue-800 font-medium';
            selectAllBtn.textContent = 'Select All';

            const deselectAllBtn = document.createElement('button');
            deselectAllBtn.type = 'button';
            deselectAllBtn.className = 'multiselect-deselect-all text-xs text-blue-600 hover:text-blue-800 font-medium';
            deselectAllBtn.textContent = 'Deselect All';

            buttonsDiv.appendChild(selectAllBtn);
            buttonsDiv.appendChild(deselectAllBtn);
            selectAllDiv.appendChild(buttonsDiv);
            dropdownInner.appendChild(selectAllDiv);
        }

        dropdown.appendChild(dropdownInner);
        wrapper.appendChild(toggleBtn);
        wrapper.appendChild(dropdown);

        this.container.replaceChildren();
        this.container.appendChild(wrapper);
        this.getElements();
    }

    renderOptions() {
        // Legacy method that returns HTML string (kept for compatibility if needed)
        return this.options.data.map(item => {
            const isSelected = this.selectedValues.has(item.value);
            const label = document.createElement('label');
            label.className = 'multiselect-option flex items-center hover:bg-gray-50 p-1 rounded cursor-pointer';
            label.setAttribute('data-value', item.value);

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.name = this.options.name;
            checkbox.value = item.value;
            checkbox.className = 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded multiselect-checkbox';
            checkbox.checked = isSelected;

            const labelSpan = document.createElement('span');
            labelSpan.className = 'ml-2 text-sm text-gray-700';

            const labelText = document.createElement('span');
            labelText.className = 'font-medium multiselect-label';
            labelText.textContent = item.label;
            labelSpan.appendChild(labelText);

            if (item.sublabel) {
                const br = document.createElement('br');
                const sublabelSpan = document.createElement('span');
                sublabelSpan.className = 'text-xs text-gray-500';
                sublabelSpan.textContent = item.sublabel;
                labelSpan.appendChild(br);
                labelSpan.appendChild(sublabelSpan);
            }

            label.appendChild(checkbox);
            label.appendChild(labelSpan);

            // Convert to HTML string for backward compatibility
            const tempDiv = document.createElement('div');
            tempDiv.appendChild(label.cloneNode(true));
            return tempDiv.innerHTML;
        }).join('');
    }

    renderOptionsToContainer(container) {
        // New method that directly appends DOM nodes
        container.replaceChildren();
        this.options.data.forEach(item => {
            const isSelected = this.selectedValues.has(item.value);
            const label = document.createElement('label');
            label.className = 'multiselect-option flex items-center hover:bg-gray-50 p-1 rounded cursor-pointer';
            label.setAttribute('data-value', item.value);

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.name = this.options.name;
            checkbox.value = item.value;
            checkbox.className = 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded multiselect-checkbox';
            checkbox.checked = isSelected;

            const labelSpan = document.createElement('span');
            labelSpan.className = 'ml-2 text-sm text-gray-700';

            const labelText = document.createElement('span');
            labelText.className = 'font-medium multiselect-label';
            labelText.textContent = item.label;
            labelSpan.appendChild(labelText);

            if (item.sublabel) {
                const br = document.createElement('br');
                const sublabelSpan = document.createElement('span');
                sublabelSpan.className = 'text-xs text-gray-500';
                sublabelSpan.textContent = item.sublabel;
                labelSpan.appendChild(br);
                labelSpan.appendChild(sublabelSpan);
            }

            label.appendChild(checkbox);
            label.appendChild(labelSpan);
            container.appendChild(label);
        });
    }

    getElements() {
        this.elements = {
            toggle: this.container.querySelector('.multiselect-toggle'),
            dropdown: this.container.querySelector('.multiselect-dropdown'),
            selectedText: this.container.querySelector('.multiselect-selected-text'),
            search: this.container.querySelector('.multiselect-search'),
            options: this.container.querySelector('.multiselect-options'),
            selectAll: this.container.querySelector('.multiselect-select-all'),
            deselectAll: this.container.querySelector('.multiselect-deselect-all'),
            checkboxes: () => this.container.querySelectorAll('.multiselect-checkbox'),
            optionElements: () => this.container.querySelectorAll('.multiselect-option')
        };
    }

    bindEvents() {
        // Toggle dropdown
        this.elements.toggle.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggleDropdown();
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (!this.container.contains(e.target)) {
                this.closeDropdown();
            }
        });

        // Search functionality
        if (this.elements.search) {
            this.elements.search.addEventListener('input', (e) => {
                this.filterOptions(e.target.value);
            });

            // Prevent dropdown from closing when clicking on search input
            this.elements.search.addEventListener('click', (e) => {
                e.stopPropagation();
            });
        }

        // Checkbox change events
        this.elements.options.addEventListener('change', (e) => {
            if (e.target.classList.contains('multiselect-checkbox')) {
                this.handleCheckboxChange(e.target);
            }
        });

        // Select/Deselect all buttons
        if (this.elements.selectAll) {
            this.elements.selectAll.addEventListener('click', (e) => {
                e.stopPropagation();
                this.selectAllVisible();
            });
        }

        if (this.elements.deselectAll) {
            this.elements.deselectAll.addEventListener('click', (e) => {
                e.stopPropagation();
                this.deselectAllVisible();
            });
        }
    }

    toggleDropdown() {
        const isHidden = this.elements.dropdown.classList.contains('hidden');
        if (isHidden) {
            this.openDropdown();
        } else {
            this.closeDropdown();
        }
    }

    openDropdown() {
        this.elements.dropdown.classList.remove('hidden');
        if (this.elements.search) {
            this.elements.search.focus();
        }
    }

    closeDropdown() {
        this.elements.dropdown.classList.add('hidden');
    }

    filterOptions(searchTerm) {
        const term = searchTerm.toLowerCase();
        const options = this.elements.optionElements();

        options.forEach(option => {
            const label = option.querySelector('.multiselect-label').textContent.toLowerCase();
            const sublabel = option.querySelector('.text-xs')?.textContent.toLowerCase() || '';

            if (label.includes(term) || sublabel.includes(term)) {
                option.style.display = 'flex';
            } else {
                option.style.display = 'none';
            }
        });
    }

    handleCheckboxChange(checkbox) {
        const value = checkbox.value;

        if (this.options.singleSelect && checkbox.checked) {
            this.selectedValues.clear();
            this.elements.checkboxes().forEach((cb) => {
                if (cb !== checkbox) {
                    cb.checked = false;
                }
            });
            this.selectedValues.add(value);
        } else if (checkbox.checked) {
            this.selectedValues.add(value);
        } else {
            this.selectedValues.delete(value);
        }

        this.updateSelectedText();
        this.triggerSelectionChange();
    }

    selectAllVisible() {
        const visibleCheckboxes = Array.from(this.elements.checkboxes()).filter(cb => {
            return cb.closest('.multiselect-option').style.display !== 'none';
        });

        if (this.options.singleSelect && visibleCheckboxes.length > 0) {
            const first = visibleCheckboxes[0];
            this.selectedValues.clear();
            this.elements.checkboxes().forEach((cb) => {
                cb.checked = cb === first;
            });
            this.selectedValues.add(first.value);
            this.updateSelectedText();
            this.triggerSelectionChange();
            return;
        }

        visibleCheckboxes.forEach(checkbox => {
            if (!checkbox.checked) {
                checkbox.checked = true;
                this.selectedValues.add(checkbox.value);
            }
        });

        this.updateSelectedText();
        this.triggerSelectionChange();
    }

    deselectAllVisible() {
        const visibleCheckboxes = Array.from(this.elements.checkboxes()).filter(cb => {
            return cb.closest('.multiselect-option').style.display !== 'none';
        });

        visibleCheckboxes.forEach(checkbox => {
            if (checkbox.checked) {
                checkbox.checked = false;
                this.selectedValues.delete(checkbox.value);
            }
        });

        this.updateSelectedText();
        this.triggerSelectionChange();
    }

    updateSelectedText() {
        const selectedCount = this.selectedValues.size;

        if (selectedCount === 0) {
            this.elements.selectedText.textContent = this.options.placeholder;
        } else if (selectedCount === 1) {
            const selectedValue = Array.from(this.selectedValues)[0];
            const selectedItem = this.options.data.find(item => item.value === selectedValue);
            this.elements.selectedText.textContent = selectedItem ? selectedItem.label : selectedValue;
        } else {
            this.elements.selectedText.textContent = `${selectedCount} items selected`;
        }
    }

    triggerSelectionChange() {
        if (this.options.onSelectionChange) {
            const selectedItems = this.getSelectedItems();
            this.options.onSelectionChange(Array.from(this.selectedValues), selectedItems);
        }
    }

    // Public methods
    getSelectedValues() {
        return Array.from(this.selectedValues);
    }

    getSelectedItems() {
        return this.options.data.filter(item => this.selectedValues.has(item.value));
    }

    setSelectedValues(values) {
        this.selectedValues = new Set(values || []);

        // Update checkboxes
        this.elements.checkboxes().forEach(checkbox => {
            checkbox.checked = this.selectedValues.has(checkbox.value);
        });

        this.updateSelectedText();
        this.triggerSelectionChange();
    }

    updateData(newData) {
        this.options.data = newData;
        this.renderOptionsToContainer(this.elements.options);
        this.updateSelectedText();
    }

    destroy() {
        if (this.container) {
            this.container.replaceChildren();
        }
        this.elements = {};
        this.selectedValues.clear();
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MultiselectDropdown;
} else if (typeof window !== 'undefined') {
    window.MultiselectDropdown = MultiselectDropdown;
}
