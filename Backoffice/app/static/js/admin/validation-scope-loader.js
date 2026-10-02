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
            if (typeof options.isCurrent === 'function' && !options.isCurrent()) {
                return { periods: [], selected: null };
            }
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

    function templateTabForId(templateId) {
        var target = String(templateId || '');
        var buttons = document.querySelectorAll('#vd-template-tabs .vd-template-tab');
        for (var i = 0; i < buttons.length; i++) {
            var btn = buttons[i];
            if (btn.getAttribute('data-template-id') === target) return btn;
            var raw = btn.getAttribute('data-child-ids') || '';
            if (raw.split(',').map(function (part) { return part.trim(); }).indexOf(target) !== -1) return btn;
        }
        return null;
    }

    function isRoundScope(templateId) {
        var id = templateId || (document.getElementById('vd-template') && document.getElementById('vd-template').value);
        var tab = templateTabForId(id);
        return !!(tab && tab.getAttribute('data-scope-mode') === 'round');
    }

    function selectedPeriod(selectEl) {
        if (!selectEl) return '';
        var opt = selectEl.options[selectEl.selectedIndex];
        if (opt && opt.getAttribute('data-period')) return opt.getAttribute('data-period');
        return selectEl.value || '';
    }

    function syncScopeFieldLabels() {
        var round = isRoundScope();
        var labelText = round
            ? ((window.VD_GRID_TRANSLATIONS && window.VD_GRID_TRANSLATIONS.round) || 'Round')
            : null;
        document.querySelectorAll('.vd-field-period .vd-field-label').forEach(function (label) {
            if (!label.dataset.periodLabel) label.dataset.periodLabel = label.textContent.trim();
            label.textContent = labelText || label.dataset.periodLabel;
        });
    }

    function commitRoundSelection(selectEl) {
        if (!selectEl) return;
        var opt = selectEl.options[selectEl.selectedIndex];
        if (!opt || !opt.getAttribute('data-round')) return;
        var templateId = opt.getAttribute('data-template-id');
        var hidden = document.getElementById('vd-template');
        if (templateId && hidden) hidden.value = templateId;
        var code = opt.getAttribute('data-round');
        document.querySelectorAll('#vd-period, #vd-tracker-period').forEach(function (other) {
            if (other === selectEl) return;
            Array.prototype.forEach.call(other.options, function (option) {
                if (option.getAttribute('data-round') === code) other.value = option.value;
            });
        });
    }

    var roundsRequest = null;

    function fetchRounds(roundsUrl) {
        if (!roundsRequest) {
            roundsRequest = window.apiFetch(roundsUrl, {
                headers: { Accept: 'application/json' },
                credentials: 'same-origin',
            }).then(function (data) {
                return data.rounds || [];
            }).catch(function (err) {
                roundsRequest = null;
                throw err;
            });
        }
        return roundsRequest;
    }

    function fillRoundSelect(selectEl, rounds, preferredPeriod, preferredTemplateId) {
        var chooseLabel = (window.VD_GRID_TRANSLATIONS && window.VD_GRID_TRANSLATIONS.chooseRound) || 'Choose round';
        selectEl.innerHTML = '<option value="">' + esc(chooseLabel) + '</option>' +
            rounds.map(function (round) {
                var value = String(round.template_id) + '::' + String(round.period_name);
                return '<option value="' + esc(value) + '"' +
                    ' data-round="' + esc(round.code) + '"' +
                    ' data-period="' + esc(round.period_name) + '"' +
                    ' data-template-id="' + esc(round.template_id) + '">' +
                    esc(round.label || round.code) + '</option>';
            }).join('');
        selectEl.disabled = !rounds.length;
        var matched = false;
        if (preferredPeriod) {
            matched = Array.prototype.some.call(selectEl.options, function (opt) {
                if (opt.getAttribute('data-period') !== String(preferredPeriod)) return false;
                if (preferredTemplateId && opt.getAttribute('data-template-id') !== String(preferredTemplateId)) return false;
                selectEl.value = opt.value;
                return true;
            });
        }
        if (!matched && rounds.length) {
            selectEl.selectedIndex = 1;
        }
        commitRoundSelection(selectEl);
    }

    async function loadRoundsIntoSelect(options) {
        var selectEl = options.selectEl;
        if (!selectEl) return { selected: null };
        selectEl.disabled = true;
        syncScopeFieldLabels();
        try {
            var rounds = await fetchRounds(options.roundsUrl);
            if (typeof options.isCurrent === 'function' && !options.isCurrent()) {
                return { selected: null };
            }
            fillRoundSelect(selectEl, rounds, options.preferredPeriod, options.preferredTemplateId);
            return { selected: selectedPeriod(selectEl) };
        } catch (err) {
            if (typeof options.onError === 'function') options.onError(err);
            else console.error(err);
            return { selected: null };
        }
    }

    window.ValidationScopeLoader = {
        loadPeriodsIntoSelect: loadPeriodsIntoSelect,
        loadRoundsIntoSelect: loadRoundsIntoSelect,
        loadCountries: loadCountries,
        selectOptionValue: selectOptionValue,
        selectedPeriod: selectedPeriod,
        isRoundScope: isRoundScope,
        commitRoundSelection: commitRoundSelection,
        syncScopeFieldLabels: syncScopeFieldLabels,
    };
})();
