/**
 * Initializes select-all/deselect-all for country-region checkbox groups.
 * Targets elements with data-country-region-select="true".
 */
(function () {
    'use strict';

    function initCountryRegionSelect(root) {
        const regionSelectAllCheckboxes = root.querySelectorAll('.region-select-all');
        const countryCheckboxes = root.querySelectorAll('.country-checkbox');
        const globalSelectAllCheckbox = root.querySelector('#select-all-countries');

        function updateRegionSelectAll(region) {
            const regionSelectAllCheckbox = root.querySelector('.region-select-all[data-region="' + region + '"]');
            const countriesInRegion = root.querySelectorAll('.region-countries[data-region="' + region + '"] .country-checkbox');
            const allChecked = countriesInRegion.length > 0 && Array.from(countriesInRegion).every(function (cb) { return cb.checked; });
            if (regionSelectAllCheckbox) {
                regionSelectAllCheckbox.checked = allChecked;
            }
        }

        function updateGlobalSelectAll() {
            const allCountryCheckboxes = root.querySelectorAll('.country-checkbox');
            const allChecked = allCountryCheckboxes.length > 0 && Array.from(allCountryCheckboxes).every(function (cb) { return cb.checked; });
            if (globalSelectAllCheckbox) {
                globalSelectAllCheckbox.checked = allChecked;
            }
        }

        if (globalSelectAllCheckbox) {
            globalSelectAllCheckbox.addEventListener('change', function () {
                const isChecked = this.checked;
                countryCheckboxes.forEach(function (countryCheckbox) {
                    countryCheckbox.checked = isChecked;
                });
                regionSelectAllCheckboxes.forEach(function (regionCheckbox) {
                    regionCheckbox.checked = isChecked;
                });
            });
        }

        regionSelectAllCheckboxes.forEach(function (regionCheckbox) {
            regionCheckbox.addEventListener('change', function () {
                const region = this.dataset.region;
                const isChecked = this.checked;
                const countriesInRegion = root.querySelectorAll('.region-countries[data-region="' + region + '"] .country-checkbox');
                countriesInRegion.forEach(function (countryCheckbox) {
                    countryCheckbox.checked = isChecked;
                });
                updateGlobalSelectAll();
            });
        });

        countryCheckboxes.forEach(function (countryCheckbox) {
            countryCheckbox.addEventListener('change', function () {
                const regionContainer = this.closest('.region-countries');
                if (regionContainer) {
                    updateRegionSelectAll(regionContainer.dataset.region);
                }
                updateGlobalSelectAll();
            });
        });

        const partOfMapEl = root.querySelector('[data-part-of-map]');
        let partOfMap = {};
        if (partOfMapEl) {
            try {
                partOfMap = JSON.parse(partOfMapEl.textContent || '{}');
            } catch (e) {
                partOfMap = {};
            }
        }
        root.addEventListener('change', function (event) {
            const box = event.target;
            if (!box.classList || !box.classList.contains('category-filter-checkbox')) return;
            const ids = partOfMap[box.dataset.category || box.value] || [];
            ids.forEach(function (id) {
                const country = root.querySelector('#country-' + id);
                if (!country || country.disabled) return;
                country.checked = box.checked;
                country.dispatchEvent(new Event('change', { bubbles: true }));
            });
        });

        updateGlobalSelectAll();
        regionSelectAllCheckboxes.forEach(function (regionCheckbox) {
            updateRegionSelectAll(regionCheckbox.dataset.region);
        });
    }

    function bindPartOfDropdowns() {
        if (document.body.dataset.partOfDropdownBound === 'true') return;
        document.body.dataset.partOfDropdownBound = 'true';

        document.addEventListener('click', function (event) {
            const toggle = event.target.closest('[data-part-of-toggle]');
            const dropdown = event.target.closest('[data-part-of-dropdown]');
            document.querySelectorAll('[data-part-of-dropdown]').forEach(function (root) {
                const panel = root.querySelector('[data-part-of-panel]');
                const button = root.querySelector('[data-part-of-toggle]');
                if (!panel || !button) return;
                if (toggle && root === toggle.closest('[data-part-of-dropdown]')) {
                    const willOpen = panel.classList.contains('hidden');
                    panel.classList.toggle('hidden', !willOpen);
                    button.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
                    return;
                }
                if (root !== dropdown) {
                    panel.classList.add('hidden');
                    button.setAttribute('aria-expanded', 'false');
                }
            });
        }, true);

        document.addEventListener('change', function (event) {
            const box = event.target;
            if (!box.classList || !box.classList.contains('category-filter-checkbox')) return;
            const dropdown = box.closest('[data-part-of-dropdown]');
            if (!dropdown) return;
            const label = dropdown.querySelector('[data-part-of-label]');
            if (!label) return;
            const count = dropdown.querySelectorAll('.category-filter-checkbox:checked').length;
            label.textContent = count
                ? (count === 1 ? '1 selected' : count + ' selected')
                : (label.dataset.emptyLabel || 'Any');
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        bindPartOfDropdowns();
        document.querySelectorAll('[data-country-region-select="true"]').forEach(initCountryRegionSelect);
    });
})();
