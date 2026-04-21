/**
 * Documentation search functionality
 * Handles search input, filtering, and category expansion
 */

(function() {
    'use strict';

    const searchInput = document.getElementById('docs-search-input');
    const searchClear = document.getElementById('docs-search-clear');
    const searchIcon = document.getElementById('docs-search-icon');

    if (!searchInput || !searchClear) return;

    function performSearch(query) {
        const searchTerm = query.toLowerCase().trim();
        const navItems = document.querySelectorAll('.nav-item');
        const categories = document.querySelectorAll('.nav-category');

        if (searchTerm === '') {
            // Show all items and reset
            navItems.forEach(function(item) {
                item.classList.remove('hidden');
            });
            categories.forEach(function(category) {
                category.classList.remove('hidden');
            });
            searchClear.classList.remove('visible');
            if (searchIcon) searchIcon.style.display = 'block';
            return;
        }

        // Hide search icon, show clear button
        if (searchIcon) searchIcon.style.display = 'none';
        searchClear.classList.add('visible');

        let hasVisibleItems = false;

        // Filter items
        navItems.forEach(function(item) {
            const searchText = item.getAttribute('data-search-text') || '';
            if (searchText.includes(searchTerm)) {
                item.classList.remove('hidden');
                hasVisibleItems = true;
            } else {
                item.classList.add('hidden');
            }
        });

        // Show/hide categories based on visible items
        categories.forEach(function(category) {
            const categoryItems = category.querySelectorAll('.nav-item:not(.hidden)');
            const categoryHeader = category.querySelector('.nav-category-header');

            if (categoryItems.length > 0) {
                category.classList.remove('hidden');
                // Auto-expand categories with matching items
                const categoryItemsContainer = category.querySelector('.nav-category-items');
                const categoryIcon = category.querySelector('.nav-category-icon');
                if (categoryItemsContainer && categoryIcon) {
                    categoryItemsContainer.classList.add('expanded');
                    categoryIcon.classList.add('expanded');
                    if (categoryHeader) categoryHeader.classList.add('highlight');
                }
                hasVisibleItems = true;
            } else {
                category.classList.add('hidden');
                if (categoryHeader) {
                    categoryHeader.classList.remove('highlight');
                }
            }
        });
    }

    // Search input handler
    searchInput.addEventListener('input', function(e) {
        performSearch(e.target.value);
    });

    // Clear search handler
    searchClear.addEventListener('click', function() {
        searchInput.value = '';
        performSearch('');
        searchInput.focus();
    });

    // Keyboard shortcuts
    searchInput.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            searchInput.value = '';
            performSearch('');
        }
    });
})();
