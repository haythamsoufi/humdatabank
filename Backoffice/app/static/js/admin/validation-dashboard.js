/**
 * Validation Dashboard — indicator flags preview and generate questions.
 */
(function () {
    'use strict';

    var config = window.validationDashboardConfig || {};
    var t = window.VD_GRID_TRANSLATIONS || {};
    var csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    var feedbackEl = document.getElementById('vd-feedback');
    var state = {
        templateId: null,
        period: null,
        countries: [],
        selectedCountry: null,
        indicatorsApi: null,
    };

    function el(id) { return document.getElementById(id); }

    function esc(s) {
        if (s == null) return '';
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function showFeedback(message, type) {
        if (!feedbackEl) return;
        feedbackEl.textContent = message;
        feedbackEl.className = 'mb-4 rounded-md px-4 py-3 text-sm border ';
        var classes = type === 'error' ? ['bg-red-50', 'border-red-200', 'text-red-800']
            : type === 'success' ? ['bg-green-50', 'border-green-200', 'text-green-800']
            : ['bg-blue-50', 'border-blue-200', 'text-blue-800'];
        feedbackEl.classList.add.apply(feedbackEl.classList, classes);
        feedbackEl.classList.remove('hidden');
    }

    function setActionButtonsEnabled(enabled) {
        ['vd-generate-country', 'vd-send'].forEach(function (id) {
            var btn = el(id);
            if (btn) btn.disabled = !enabled;
        });
        var allBtn = el('vd-generate-all');
        if (allBtn) allBtn.disabled = !state.countries.length;
    }

    function badge(text, cls) {
        return '<span class="inline-flex px-2 py-0.5 rounded-full text-xs font-medium ' + cls + '">' + esc(text) + '</span>';
    }

    function indicatorColumnDefs() {
        return [
            {
                field: 'flagged',
                headerName: t.flagged || 'Flagged',
                width: 90,
                filter: 'customSetFilter',
                cellRenderer: function (p) {
                    return p.value ? badge('Yes', 'bg-red-100 text-red-800') : badge('—', 'bg-gray-100 text-gray-600');
                },
            },
            { field: 'kpi_code', headerName: t.kpiCode || 'KPI', width: 130, filter: 'agTextColumnFilter' },
            { field: 'indicator_label', headerName: t.indicator || 'Indicator', flex: 1, minWidth: 160, filter: 'agTextColumnFilter' },
            { field: 'current_value', headerName: t.value || 'Value', width: 110, filter: 'agTextColumnFilter' },
            { field: 'rule_code', headerName: t.rule || 'Rule', width: 140, filter: 'agTextColumnFilter' },
            {
                field: 'severity',
                headerName: t.severity || 'Severity',
                width: 100,
                filter: 'customSetFilter',
                cellRenderer: function (p) {
                    var map = { error: 'bg-red-100 text-red-800', warning: 'bg-amber-100 text-amber-800', info: 'bg-blue-100 text-blue-800' };
                    return p.value ? badge(p.value, map[p.value] || 'bg-gray-100 text-gray-800') : '—';
                },
            },
            {
                field: 'question_preview',
                headerName: t.questionPreview || 'Question preview',
                flex: 1.2,
                minWidth: 180,
                wrapText: true,
                autoHeight: true,
                filter: 'agTextColumnFilter',
            },
        ];
    }

    function initIndicatorsGrid(rows) {
        if (state.indicatorsApi) {
            state.indicatorsApi.setGridOption('rowData', rows);
            return;
        }
        var result = AgGridHelper.create('validationIndicatorsGrid', 'admin-validation-indicators', indicatorColumnDefs(), rows, {
            columnVisibilityOptions: { buttonPlaceholderId: 'vd-indicators-col-vis', enableExport: true },
        });
        state.indicatorsApi = result.api;
    }

    function populateCountrySelect(countries) {
        var countryEl = el('vd-country');
        if (!countryEl) return;
        if (!countries.length) {
            countryEl.innerHTML = '<option value="">' + esc('No countries with assignments') + '</option>';
            countryEl.disabled = true;
            return;
        }
        countryEl.innerHTML = '<option value="">' + esc('Select country') + '</option>' +
            countries.map(function (c) {
                return '<option value="' + c.country_id + '" data-period="' + esc(c.period_name) + '">' + esc(c.country_name) + '</option>';
            }).join('');
        countryEl.disabled = false;
    }

    function onCountrySelected() {
        var countryEl = el('vd-country');
        var countryId = countryEl?.value;
        if (!countryId) {
            state.selectedCountry = null;
            setActionButtonsEnabled(false);
            el('vd-selected-country').textContent = '';
            initIndicatorsGrid([]);
            return;
        }
        var opt = countryEl.options[countryEl.selectedIndex];
        state.selectedCountry = state.countries.find(function (c) { return String(c.country_id) === String(countryId); }) || {
            country_id: +countryId,
            country_name: opt.textContent,
            period_name: opt.getAttribute('data-period') || state.period,
        };
        setActionButtonsEnabled(true);
        loadIndicatorPreview(state.selectedCountry.country_id, state.selectedCountry.country_name);
    }

    async function loadPeriods() {
        var templateId = el('vd-template')?.value;
        var periodEl = el('vd-period');
        if (!periodEl) return;
        if (!templateId) {
            periodEl.innerHTML = '<option value="">' + esc(t.selectTemplatePeriod || 'Select template first') + '</option>';
            periodEl.disabled = true;
            return;
        }
        periodEl.disabled = true;
        try {
            var resp = await fetch(config.periodsUrl + '?template_id=' + encodeURIComponent(templateId), {
                headers: { Accept: 'application/json' },
                credentials: 'same-origin',
            });
            var data = await resp.json();
            var periods = data.periods || [];
            periodEl.innerHTML = '<option value="">' + esc('Choose period') + '</option>' +
                periods.map(function (p) { return '<option value="' + esc(p) + '">' + esc(p) + '</option>'; }).join('');
            periodEl.disabled = !periods.length;
        } catch (err) {
            console.error(err);
        }
    }

    async function loadDashboard() {
        var templateId = el('vd-template')?.value;
        var period = el('vd-period')?.value;
        if (!templateId || !period) {
            showFeedback(t.selectTemplatePeriod || 'Select template and period.', 'error');
            return;
        }
        state.templateId = templateId;
        state.period = period;
        state.selectedCountry = null;
        setActionButtonsEnabled(false);
        el('vd-selected-country').textContent = '';
        initIndicatorsGrid([]);

        try {
            var resp = await fetch(
                config.countriesUrl + '?template_id=' + encodeURIComponent(templateId) + '&period=' + encodeURIComponent(period),
                { headers: { Accept: 'application/json' }, credentials: 'same-origin' }
            );
            var data = await resp.json();
            if (!resp.ok) throw new Error(data.error || t.loadFailed);
            state.countries = data.countries || [];
            populateCountrySelect(state.countries);
            var allBtn = el('vd-generate-all');
            if (allBtn) allBtn.disabled = !state.countries.length;
            showFeedback('Loaded ' + state.countries.length + ' countries. Select one to preview flags.', 'info');
        } catch (err) {
            console.error(err);
            showFeedback(t.loadFailed || 'Load failed', 'error');
        }
    }

    async function loadIndicatorPreview(countryId, countryName) {
        el('vd-selected-country').textContent = countryName ? '— ' + countryName : '';
        try {
            var url = config.previewUrl + '?template_id=' + encodeURIComponent(state.templateId) +
                '&period=' + encodeURIComponent(state.period) + '&country_id=' + encodeURIComponent(countryId);
            var resp = await fetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
            var data = await resp.json();
            if (!resp.ok) throw new Error(data.error || t.previewFailed);
            var rows = (data.preview && data.preview.indicators) || [];
            initIndicatorsGrid(rows);
            var flagged = rows.filter(function (r) { return r.flagged; }).length;
            showFeedback(flagged + ' automatic flag(s) for ' + countryName + '.', flagged ? 'info' : 'success');
        } catch (err) {
            console.error(err);
            showFeedback(t.previewFailed || 'Preview failed', 'error');
        }
    }

    async function runChecks(countryIds) {
        var resp = await fetch(config.runChecksUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, Accept: 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({
                template_id: +state.templateId,
                period_name: state.period,
                country_ids: countryIds,
            }),
        });
        var data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Generate failed');
        showFeedback(data.message || 'Questions generated.', data.has_errors ? 'error' : 'success');
        await loadDashboard();
        if (state.selectedCountry) {
            onCountrySelected();
        }
    }

    async function sendDispatch() {
        if (!state.selectedCountry) return;
        var resp = await fetch(config.sendUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, Accept: 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({
                template_id: +state.templateId,
                period_name: state.selectedCountry.period_name || state.period,
                country_id: state.selectedCountry.country_id,
                channels: ['in_app', 'email'],
            }),
        });
        var data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Send failed');
        showFeedback('Validation questions sent to focal points.', 'success');
    }

    el('vd-template')?.addEventListener('change', loadPeriods);
    el('vd-load')?.addEventListener('click', loadDashboard);
    el('vd-country')?.addEventListener('change', onCountrySelected);
    el('vd-generate-country')?.addEventListener('click', function () {
        if (!state.selectedCountry || !window.confirm(t.generateConfirm || 'Generate questions?')) return;
        runChecks([state.selectedCountry.country_id]).catch(function (e) { showFeedback(e.message, 'error'); });
    });
    el('vd-generate-all')?.addEventListener('click', function () {
        if (!state.countries.length || !window.confirm(t.generateAllConfirm || 'Generate for all countries?')) return;
        runChecks(state.countries.map(function (c) { return c.country_id; })).catch(function (e) { showFeedback(e.message, 'error'); });
    });
    el('vd-send')?.addEventListener('click', function () {
        if (!state.selectedCountry || !window.confirm(t.sendConfirm || 'Send to focal points?')) return;
        sendDispatch().catch(function (e) { showFeedback(e.message, 'error'); });
    });

    initIndicatorsGrid([]);
    setActionButtonsEnabled(false);
})();
