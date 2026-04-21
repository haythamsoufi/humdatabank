/**
 * Enhanced Search Dropdown Component
 * A reusable searchable dropdown with keyboard navigation for any data type
 */

class EnhancedSearchDropdown {
    constructor(options = {}) {
        this.options = {
            searchInputId: 'search_input',
            dropdownId: 'search_dropdown',
            listId: 'search_list',
            noResultsId: 'no_results',
            formId: 'search_form',
            selectId: 'search_select',
            clearSearchId: 'clear_search',
            onItemSelect: null,
            ...options
        };

        this.elements = {};
        this.selectedItemId = null;
        this.selectedItemName = null;

        this.init();
    }

    init() {
        this.getElements();
        if (!this.elements.searchInput || !this.elements.dropdown) {
            console.warn('EnhancedSearchDropdown: Required elements not found');
            return;
        }

        this.setInitialValue();
        this.bindEvents();
        this.updateClearButton();
    }

    getElements() {
        this.elements = {
            searchInput: document.getElementById(this.options.searchInputId),
            dropdown: document.getElementById(this.options.dropdownId),
            list: document.getElementById(this.options.listId),
            noResults: document.getElementById(this.options.noResultsId),
            form: document.getElementById(this.options.formId),
            select: document.getElementById(this.options.selectId),
            clearSearch: document.getElementById(this.options.clearSearchId)
        };
    }

    setInitialValue() {
        const selectedOption = document.querySelector('.dropdown-option[data-selected="true"]');
        if (selectedOption) {
            this.selectedItemId = selectedOption.getAttribute('data-item-id');
            this.selectedItemName = selectedOption.getAttribute('data-item-name');
            this.elements.searchInput.value = this.selectedItemName;
        }
    }

    bindEvents() {
        // Show dropdown on focus
        this.elements.searchInput.addEventListener('focus', () => {
            this.showDropdown();
        });

        // Hide dropdown when clicking outside
        document.addEventListener('click', (event) => {
            if (!this.elements.searchInput.contains(event.target) &&
                !this.elements.dropdown.contains(event.target)) {
                this.hideDropdown();
            }
        });

        // Search functionality
        this.elements.searchInput.addEventListener('input', () => {
            this.filterItems();
            this.updateClearButton();
        });

        // Clear search functionality
        if (this.elements.clearSearch) {
            this.elements.clearSearch.addEventListener('click', () => {
                this.clearSearch();
            });
        }

        // Keyboard navigation
        this.elements.searchInput.addEventListener('keydown', (event) => {
            this.handleKeyboardNavigation(event);
        });

        // Click handlers for dropdown options
        this.elements.list.addEventListener('click', (event) => {
            const option = event.target.closest('.dropdown-option');
            if (option) {
                this.selectItem(option);
            }
        });

        // Hover effects for keyboard navigation
        this.elements.list.addEventListener('mouseover', (event) => {
            const option = event.target.closest('.dropdown-option');
            if (option) {
                this.highlightOption(option);
            }
        });
    }

    showDropdown() {
        this.elements.dropdown.classList.remove('hidden');
        this.filterItems();

        // Highlight first option if no search term
        if (this.elements.searchInput.value.trim() === '') {
            const firstOption = this.elements.list.querySelector('.dropdown-option:not(.hidden)');
            if (firstOption) {
                this.highlightOption(firstOption);
            }
        }
    }

    hideDropdown() {
        this.elements.dropdown.classList.add('hidden');
    }

    filterItems() {
        const searchTerm = this.elements.searchInput.value.toLowerCase().trim();
        const dropdownOptions = this.elements.list.querySelectorAll('.dropdown-option');
        let visibleCount = 0;

        dropdownOptions.forEach(option => {
            const itemName = option.getAttribute('data-item-name').toLowerCase();
            const matches = itemName.includes(searchTerm);

            if (matches) {
                option.classList.remove('hidden');
                visibleCount++;
            } else {
                option.classList.add('hidden');
            }
        });

        // Show/hide no results message
        if (visibleCount === 0 && searchTerm !== '') {
            this.elements.noResults.classList.remove('hidden');
        } else {
            this.elements.noResults.classList.add('hidden');
        }

        // Remove any existing highlights
        this.clearHighlights();
    }

    handleKeyboardNavigation(event) {
        const visibleOptions = this.elements.list.querySelectorAll('.dropdown-option:not(.hidden)');
        const currentIndex = Array.from(visibleOptions).findIndex(option =>
            option.classList.contains('highlighted')
        );

        switch(event.key) {
            case 'ArrowDown':
                event.preventDefault();
                if (visibleOptions.length === 0) return;

                if (currentIndex < visibleOptions.length - 1) {
                    if (currentIndex >= 0) visibleOptions[currentIndex].classList.remove('highlighted');
                    visibleOptions[currentIndex + 1].classList.add('highlighted');
                } else if (currentIndex === -1) {
                    visibleOptions[0].classList.add('highlighted');
                }
                break;

            case 'ArrowUp':
                event.preventDefault();
                if (visibleOptions.length === 0) return;

                if (currentIndex > 0) {
                    visibleOptions[currentIndex].classList.remove('highlighted');
                    visibleOptions[currentIndex - 1].classList.add('highlighted');
                } else if (currentIndex === 0) {
                    visibleOptions[currentIndex].classList.remove('highlighted');
                }
                break;

            case 'Enter':
                event.preventDefault();
                const highlightedOption = this.elements.list.querySelector('.dropdown-option.highlighted');
                if (highlightedOption) {
                    this.selectItem(highlightedOption);
                }
                break;

            case 'Escape':
                this.hideDropdown();
                this.elements.searchInput.blur();
                break;
        }
    }

    selectItem(option) {
        const itemId = option.getAttribute('data-item-id');
        const itemName = option.getAttribute('data-item-name');

        // Update selected state
        this.elements.list.querySelectorAll('.dropdown-option').forEach(opt => {
            opt.classList.remove('selected');
            opt.querySelector('svg')?.remove();
        });

        option.classList.add('selected');

        // Add checkmark to selected option
        const checkmark = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        checkmark.setAttribute('class', 'h-4 w-4 text-blue-600');
        checkmark.setAttribute('fill', 'currentColor');
        checkmark.setAttribute('viewBox', '0 0 20 20');
        const checkPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        checkPath.setAttribute('fill-rule', 'evenodd');
        checkPath.setAttribute('d', 'M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z');
        checkPath.setAttribute('clip-rule', 'evenodd');
        checkmark.appendChild(checkPath);
        option.appendChild(checkmark);

        // Update search input
        this.elements.searchInput.value = itemName;
        this.selectedItemId = itemId;
        this.selectedItemName = itemName;

        // Hide dropdown
        this.hideDropdown();

        // Call custom callback if provided
        if (this.options.onItemSelect) {
            this.options.onItemSelect(itemId, itemName, option);
        } else {
            // Default behavior: submit form
            this.submitForm(itemId);
        }
    }

    submitForm(itemId) {
        if (this.elements.select && this.elements.form) {
            this.elements.select.value = itemId;
            this.elements.form.submit();
        }
    }

    clearSearch() {
        this.elements.searchInput.value = '';
        this.elements.searchInput.focus();
        this.filterItems();
        this.updateClearButton();
    }

    updateClearButton() {
        if (this.elements.clearSearch) {
            if (this.elements.searchInput.value.trim() !== '') {
                this.elements.clearSearch.classList.remove('hidden');
            } else {
                this.elements.clearSearch.classList.add('hidden');
            }
        }
    }

    highlightOption(option) {
        this.clearHighlights();
        option.classList.add('highlighted');
    }

    clearHighlights() {
        this.elements.list.querySelectorAll('.dropdown-option.highlighted').forEach(option => {
            option.classList.remove('highlighted');
        });
    }

    // Public methods for external control
    setValue(itemId, itemName) {
        this.selectedItemId = itemId;
        this.selectedItemName = itemName;
        this.elements.searchInput.value = itemName || '';
        this.updateClearButton();
    }

    getValue() {
        return {
            id: this.selectedItemId,
            name: this.selectedItemName
        };
    }

    destroy() {
        // Remove event listeners and clean up
        // This is a basic cleanup - you might want to add more specific cleanup
        this.elements = {};
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = EnhancedSearchDropdown;
} else if (typeof window !== 'undefined') {
    window.EnhancedSearchDropdown = EnhancedSearchDropdown;
}
