/**
 * Shared loader for validation scope API (periods / countries).
 * Depends on: api-fetch.js, html-escape.js
 */
(function () {
    'use strict';

    function esc(value) {
        if (window.esc) return window.esc(value);
        if (value == null) return '';
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function selectOptionValue(selectEl, value) {
        if (!selectEl || value == null || value === '') return false;
        var target = String(value);
        var found = Array.prototype.some.call(selectEl.options, function (opt) {
            return opt.value === target;
        });
        if (found) selectEl.value = target;
        return found;
    }

    /**
     * Fetch periods and populate a <select>.
     * @returns {Promise<{periods: string[], selected: string|null}>}
     */
    async function loadPeriodsIntoSelect(options) {
        var selectEl = options.selectEl;
        var periodsUrl = options.periodsUrl;
        var templateId = options.templateId;
        var preferredPeriod = options.preferredPeriod;
        var emptyLabel = options.emptyLabel || 'Select template first';
        var chooseLabel = options.chooseLabel || 'Choose period';
        var onError = options.onError;

        if (!selectEl) return { periods: [], selected: null };
        if (!templateId) {
            selectEl.innerHTML = '<option value="">' + esc(emptyLabel) + '</option>';
            selectEl.disabled = true;
            return { periods: [], selected: null };
        }

        selectEl.disabled = true;
        try {
            var data = await window.apiFetch(
                periodsUrl + '?template_id=' + encodeURIComponent(templateId),
                { headers: { Accept: 'application/json' }, credentials: 'same-origin' }
            );
            var periods = data.periods || [];
            selectEl.innerHTML = '<option value="">' + esc(chooseLabel) + '</option>' +
                periods.map(function (p) {
                    return '<option value="' + esc(p) + '">' + esc(p) + '</option>';
                }).join('');
            selectEl.disabled = !periods.length;

            if (preferredPeriod) {
                selectOptionValue(selectEl, preferredPeriod);
            }
            if (!selectEl.value && periods.length) {
                selectEl.value = periods[0];
            }
            return { periods: periods, selected: selectEl.value || null };
        } catch (err) {
            if (typeof onError === 'function') onError(err);
            else console.error(err);
            return { periods: [], selected: null };
        }
    }

    /**
     * Fetch countries for template + period.
     * @returns {Promise<Array>}
     */
    async function loadCountries(options) {
        var countriesUrl = options.countriesUrl;
        var templateId = options.templateId;
        var period = options.period;
        var onError = options.onError;

        if (!templateId || !period) return [];
        try {
            var data = await window.apiFetch(
                countriesUrl + '?template_id=' + encodeURIComponent(templateId) +
                    '&period=' + encodeURIComponent(period),
                { headers: { Accept: 'application/json' }, credentials: 'same-origin' }
            );
            return data.countries || [];
        } catch (err) {
            if (typeof onError === 'function') onError(err);
            else console.error(err);
            throw err;
        }
    }

    window.ValidationScopeLoader = {
        loadPeriodsIntoSelect: loadPeriodsIntoSelect,
        loadCountries: loadCountries,
        selectOptionValue: selectOptionValue,
    };
})();
