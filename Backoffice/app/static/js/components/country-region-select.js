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

        updateGlobalSelectAll();
        regionSelectAllCheckboxes.forEach(function (regionCheckbox) {
            updateRegionSelectAll(regionCheckbox.dataset.region);
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-country-region-select="true"]').forEach(initCountryRegionSelect);
    });
})();
