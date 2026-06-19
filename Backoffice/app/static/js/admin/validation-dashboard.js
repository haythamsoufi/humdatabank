/**
 * Validation Dashboard — flag KPI, indicator preview with history.
 */
(function () {
    'use strict';

    var config = window.validationDashboardConfig || {};
    var t = window.VD_GRID_TRANSLATIONS || {};
    var csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    var feedbackEl = document.getElementById('vd-feedback');
    var SCOPE_STORAGE_KEY = 'humdb_validation_dashboard_scope_v2';

    var state = {
        templateId: null,
        period: null,
        countries: [],
        selectedCountry: null,
        preview: null,
        rawIndicatorRows: [],
        historyYears: [],
        flaggedOnly: false,
        showHistorical: false,
        indicatorsApi: null,
    };

    function el(id) { return document.getElementById(id); }

    function getTemplateId() {
        return el('vd-template')?.value || '';
    }

    function templateTabButtons() {
        return document.querySelectorAll('#vd-template-tabs .vd-template-tab');
    }

    function setTemplateId(templateId) {
        var target = templateId == null ? '' : String(templateId);
        var matched = false;
        var A = window.AdminUnderlineTabs;
        templateTabButtons().forEach(function (btn) {
            var isActive = btn.getAttribute('data-template-id') === target;
            if (isActive) matched = true;
            if (A) A.setStripButtonActive(btn, isActive);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });
        if (!matched && target) return false;
        var hidden = el('vd-template');
        if (hidden) hidden.value = matched ? target : '';
        return matched || !target;
    }

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
    window.validationDashboardShowFeedback = showFeedback;

    function readSavedScope() {
        try {
            var raw = localStorage.getItem(SCOPE_STORAGE_KEY);
            return raw ? JSON.parse(raw) : null;
        } catch (err) {
            return null;
        }
    }

    function saveScope() {
        try {
            localStorage.setItem(SCOPE_STORAGE_KEY, JSON.stringify({
                templateId: getTemplateId(),
                period: el('vd-period')?.value || '',
                countryId: el('vd-country')?.value || '',
                showHistorical: state.showHistorical,
                flaggedOnly: state.flaggedOnly,
            }));
        } catch (err) { /* ignore */ }
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

    function badge(text, variant) {
        if (window.StatusLabels) {
            return window.StatusLabels.render(text, variant || 'neutral');
        }
        return '<span class="status-label status-label--' + (variant || 'neutral') + '">' + esc(text) + '</span>';
    }

    function automaticCheckLabel(row) {
        if (!row || !row.flagged) return '';
        var labels = row.triggered_rule_labels;
        if (labels && labels.length) return labels.join(', ');
        var rules = row.triggered_rules;
        if (rules && rules.length) return rules.join(', ');
        return row.rule_code || 'Yes';
    }

    function formatIsoDate(iso) {
        if (!iso) return '';
        return String(iso).slice(0, 10);
    }

    function formatNumericDisplay(value) {
        if (value == null || value === '') return '';
        var normalized = String(value).replace(/,/g, '').trim();
        if (!normalized) return '';
        var num = Number(normalized);
        if (!Number.isFinite(num)) return String(value);
        if (Number.isInteger(num)) {
            return num.toLocaleString(undefined, { maximumFractionDigits: 0 });
        }
        return num.toLocaleString(undefined, { maximumFractionDigits: 2 });
    }

    function numericValueFormatter(params) {
        return formatNumericDisplay(params.value);
    }

    function questionStatusLabel(status) {
        var map = {
            open: t.statusOpen || 'Open',
            answered: t.statusAnswered || 'Answered',
            waived: t.statusWaived || 'Waived',
            resolved: t.statusResolved || 'Resolved',
        };
        return map[status] || status;
    }

    function questionStatusRenderer(params) {
        var d = params.data || {};
        var status = d.question_status;
        if (status) {
            var variant = 'neutral';
            if (status === 'open') variant = 'warning';
            else if (status === 'answered') variant = 'success';
            else if (status === 'resolved') variant = 'success';
            return badge(questionStatusLabel(status), variant);
        }
        if (d.flagged) {
            return badge(t.notGenerated || 'Not generated', 'neutral');
        }
        return '';
    }

    function sentStatusRenderer(params) {
        var d = params.data || {};
        if (d.sent_at) return esc(formatIsoDate(d.sent_at));
        if (d.question_id && d.question_status === 'open') {
            return badge(t.notSent || 'Not sent', 'pending');
        }
        return '';
    }

    function multilineTextRenderer(params) {
        var val = params.value;
        if (val == null || val === '') {
            return '<span class="text-gray-400">—</span>';
        }
        return '<div class="vd-multiline-text text-sm text-gray-900">' + esc(String(val)) + '</div>';
    }

    function multilineColumnDef(overrides) {
        return Object.assign({
            wrapText: true,
            autoHeight: true,
            cellClass: 'vd-multiline-cell',
            cellRenderer: multilineTextRenderer,
            cellStyle: {
                whiteSpace: 'normal',
                lineHeight: '1.4',
                alignItems: 'flex-start',
            },
            filter: 'agTextColumnFilter',
        }, overrides);
    }

    function setActionButtonsEnabled(enabled) {
        var btn = el('vd-generate-country');
        if (btn) btn.disabled = !enabled;
    }

    function resetDashboardScope() {
        state.countries = [];
        state.selectedCountry = null;
        state.preview = null;
        state.rawIndicatorRows = [];
        state.historyYears = [];
        populateCountrySelect([]);
        initIndicatorsGrid([]);
        updateKpis();
        setActionButtonsEnabled(false);
    }

    function updateKpis() {
        var preview = state.preview;
        var flagsEl = el('vd-kpi-flags');
        if (flagsEl) flagsEl.textContent = preview ? preview.flag_count : '—';
    }

    /* ——— Grids ——— */

    function filteredIndicatorRows() {
        return state.rawIndicatorRows.filter(function (row) {
            return !(state.flaggedOnly && !row.flagged);
        });
    }

    function applyIndicatorFilters() {
        if (state.indicatorsApi) {
            state.indicatorsApi.setGridOption('rowData', filteredIndicatorRows());
        }
    }

    function historyColumnDefs() {
        if (!state.showHistorical || !state.historyYears.length) return [];
        return state.historyYears.map(function (year) {
            return {
                colId: 'hist_' + year,
                headerName: String(year),
                width: 100,
                minWidth: 100,
                filter: 'agTextColumnFilter',
                valueGetter: function (p) {
                    var hv = p.data && p.data.historical_values;
                    if (!hv) return '';
                    var v = hv[String(year)];
                    return v != null ? formatNumericDisplay(v) : '';
                },
                valueFormatter: numericValueFormatter,
            };
        });
    }

    function indicatorColumnDefs() {
        var base = [
            { field: 'indicator_label', headerName: t.indicator || 'Indicator', flex: 1, minWidth: 180, filter: 'agTextColumnFilter' },
        ];
        if (!state.showHistorical) {
            base.push({
                field: 'current_value',
                headerName: t.value || 'Value',
                width: 110,
                minWidth: 110,
                filter: 'agTextColumnFilter',
                valueFormatter: numericValueFormatter,
            });
        }
        base = base.concat(historyColumnDefs());
        base.push(
            {
                colId: 'automatic_check',
                headerName: t.automaticCheck || 'Automatic check',
                flex: 1,
                minWidth: 180,
                filter: 'agTextColumnFilter',
                valueGetter: function (p) { return automaticCheckLabel(p.data); },
                cellRenderer: function (p) {
                    if (p.data && p.data.flagged) {
                        return badge(automaticCheckLabel(p.data), 'danger');
                    }
                    return '';
                },
            },
            {
                field: 'severity',
                headerName: t.severity || 'Severity',
                width: 100,
                minWidth: 100,
                filter: 'customSetFilter',
                cellRenderer: function (p) {
                    if (!p.value) return '';
                    var variant = p.value === 'error' ? 'danger' : (p.value === 'warning' ? 'warning' : (p.value === 'info' ? 'info' : 'neutral'));
                    return badge(p.value, variant);
                },
            },
            {
                colId: 'question_status',
                field: 'question_status',
                headerName: t.questionStatus || 'Question status',
                width: 130,
                minWidth: 130,
                filter: 'customSetFilter',
                valueGetter: function (p) {
                    var d = p.data || {};
                    if (d.question_status) return questionStatusLabel(d.question_status);
                    if (d.flagged) return t.notGenerated || 'Not generated';
                    return '';
                },
                cellRenderer: questionStatusRenderer,
            },
            {
                colId: 'sent_at',
                headerName: t.sent || 'Sent',
                width: 110,
                minWidth: 110,
                filter: 'agTextColumnFilter',
                valueGetter: function (p) {
                    var d = p.data || {};
                    if (d.sent_at) return formatIsoDate(d.sent_at);
                    if (d.question_id && d.question_status === 'open') return t.notSent || 'Not sent';
                    return '';
                },
                cellRenderer: sentStatusRenderer,
            },
            multilineColumnDef({
                field: 'answer_preview',
                headerName: t.answer || 'Answer',
                flex: 1,
                minWidth: 180,
                valueGetter: function (p) {
                    var d = p.data || {};
                    if (d.answer_preview) return d.answer_preview;
                    if (d.has_answer) return t.answerReceived || 'Answer received';
                    return '';
                },
            }),
            multilineColumnDef({
                field: 'question_preview',
                headerName: t.questionPreview || 'Question preview',
                flex: 1.2,
                minWidth: 220,
            })
        );
        return base;
    }

    function rebuildIndicatorsGrid() {
        if (!state.indicatorsApi) {
            initIndicatorsGrid(filteredIndicatorRows());
            return;
        }
        state.indicatorsApi.setGridOption('columnDefs', indicatorColumnDefs());
        applyIndicatorFilters();
        AgGridHelper.enforceColumnMinWidths(state.indicatorsApi);
    }

    function initIndicatorsGrid(rows) {
        if (state.indicatorsApi) {
            state.indicatorsApi.setGridOption('columnDefs', indicatorColumnDefs());
            state.indicatorsApi.setGridOption('rowData', rows);
            if (typeof state.indicatorsApi.refreshHeader === 'function') {
                state.indicatorsApi.refreshHeader();
            }
            return;
        }
        var result = AgGridHelper.create('validationIndicatorsGrid', 'admin-validation-indicators', indicatorColumnDefs(), rows, {
            columnVisibilityOptions: { buttonPlaceholderId: 'vd-indicators-col-vis', enableExport: true },
            sizeColumnsToFitOnInit: false,
            sizeColumnsToFitOnRefresh: false,
            sizeColumnsToFitOnColumnChange: false,
            gridOptions: {
                defaultColDef: {
                    suppressSizeToFit: true,
                    wrapHeaderText: true,
                    autoHeaderHeight: true,
                },
                getRowClass: function (p) {
                    if (p.data && p.data.flagged) return 'vd-ag-row-flagged';
                    return '';
                },
                onFirstDataRendered: function (params) {
                    AgGridHelper.enforceColumnMinWidths(params.api);
                },
            },
        });
        state.indicatorsApi = result.api;
    }

    function populateCountrySelect(countries, preferredCountryId) {
        var countryEl = el('vd-country');
        if (!countryEl) return null;
        if (!countries.length) {
            countryEl.innerHTML = '<option value="">' + esc('No countries with assignments') + '</option>';
            countryEl.disabled = true;
            countryEl.value = '';
            return null;
        }
        countryEl.innerHTML = countries.map(function (c) {
            return '<option value="' + c.country_id + '" data-period="' + esc(c.period_name) + '">' + esc(c.country_name) + '</option>';
        }).join('');
        countryEl.disabled = false;
        var matched = preferredCountryId != null && selectOptionValue(countryEl, preferredCountryId);
        if (!matched) {
            countryEl.selectedIndex = 0;
        }
        return countryEl.value;
    }

    function onCountrySelected() {
        var countryEl = el('vd-country');
        var countryId = countryEl?.value;
        if (!countryId) {
            state.selectedCountry = null;
            state.preview = null;
            state.rawIndicatorRows = [];
            state.historyYears = [];
            setActionButtonsEnabled(false);
            initIndicatorsGrid([]);
            updateKpis();
            saveScope();
            return;
        }
        var opt = countryEl.options[countryEl.selectedIndex];
        state.selectedCountry = state.countries.find(function (c) { return String(c.country_id) === String(countryId); }) || {
            country_id: +countryId,
            country_name: opt.textContent,
            period_name: opt.getAttribute('data-period') || state.period,
        };
        setActionButtonsEnabled(true);
        loadIndicatorPreview(state.selectedCountry.country_id);
        saveScope();
    }

    /* ——— Data loading ——— */

    async function loadPeriods(preferredPeriod) {
        var templateId = getTemplateId();
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
            if (preferredPeriod) selectOptionValue(periodEl, preferredPeriod);
            if (!periodEl.value && periods.length) periodEl.value = periods[0];
            saveScope();
        } catch (err) {
            console.error(err);
        }
    }

    async function loadCountriesForPeriod(preferredCountryId) {
        var templateId = getTemplateId();
        var period = el('vd-period')?.value;
        if (!templateId || !period) {
            state.countries = [];
            populateCountrySelect([]);
            return null;
        }
        try {
            var resp = await fetch(
                config.countriesUrl + '?template_id=' + encodeURIComponent(templateId) + '&period=' + encodeURIComponent(period),
                { headers: { Accept: 'application/json' }, credentials: 'same-origin' }
            );
            var data = await resp.json();
            if (!resp.ok) throw new Error(data.error || t.loadFailed);
            state.countries = data.countries || [];
            return populateCountrySelect(state.countries, preferredCountryId);
        } catch (err) {
            console.error(err);
            showFeedback(t.loadFailed || 'Load failed', 'error');
            return null;
        }
    }

    async function applyScope(preferredPeriod, preferredCountryId) {
        await loadPeriods(preferredPeriod);
        if (!el('vd-period')?.value) return;
        await loadDashboard(preferredCountryId);
    }

    async function loadDashboard(preferredCountryId) {
        var templateId = getTemplateId();
        var period = el('vd-period')?.value;
        if (!templateId || !period) {
            showFeedback(t.selectTemplatePeriod || 'Select template and period.', 'error');
            return false;
        }
        var restoreCountryId = preferredCountryId != null
            ? preferredCountryId
            : (state.selectedCountry && state.selectedCountry.country_id);
        state.templateId = templateId;
        state.period = period;
        state.selectedCountry = null;
        state.preview = null;
        state.rawIndicatorRows = [];
        state.historyYears = [];
        setActionButtonsEnabled(false);
        initIndicatorsGrid([]);
        await loadCountriesForPeriod(restoreCountryId);
        if (el('vd-country')?.value) {
            onCountrySelected();
        }
        saveScope();
        return true;
    }

    async function loadIndicatorPreview(countryId) {
        try {
            var url = config.previewUrl + '?template_id=' + encodeURIComponent(state.templateId) +
                '&period=' + encodeURIComponent(state.period) + '&country_id=' + encodeURIComponent(countryId);
            var resp = await fetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
            var data = await resp.json();
            if (!resp.ok) throw new Error(data.error || t.previewFailed);
            state.preview = data.preview || null;
            state.rawIndicatorRows = (state.preview && state.preview.indicators) || [];
            state.historyYears = (state.preview && state.preview.history_years) || [];
            rebuildIndicatorsGrid();
            updateKpis();
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
        var countryId = state.selectedCountry && state.selectedCountry.country_id;
        await loadDashboard(countryId);
    }

    /* ——— Event wiring ——— */

    templateTabButtons().forEach(function (btn) {
        btn.addEventListener('click', function () {
            var id = btn.getAttribute('data-template-id');
            if (!id || id === getTemplateId()) return;
            setTemplateId(id);
            resetDashboardScope();
            applyScope(null, null).catch(function (err) { console.error(err); });
            if (window.validationDashboardTracker && window.validationDashboardTracker.onTemplateChanged) {
                window.validationDashboardTracker.onTemplateChanged(null).catch(function (err) { console.error(err); });
            }
        });
    });

    /* ——— Main view tabs (Tracker | Country Validation) ——— */

    function initMainTabs() {
        var A = window.AdminUnderlineTabs;
        if (!A) return;
        document.querySelectorAll('#vd-main-tabs .settings-tab').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var tabId = btn.getAttribute('data-tab');
                if (!tabId) return;
                A.activateStripTab('#vd-main-tabs', tabId, { panelSelector: '.vd-panel', panelIdPrefix: 'panel-' });
                document.dispatchEvent(new CustomEvent('vd-main-tab-activated', { detail: { tab: tabId } }));
                if (tabId === 'tracker' && window.validationDashboardTracker) {
                    window.validationDashboardTracker.invalidateMapSize();
                }
            });
        });
    }

    initMainTabs();

    el('vd-period')?.addEventListener('change', function () {
        saveScope();
        var countryId = state.selectedCountry && state.selectedCountry.country_id;
        loadDashboard(countryId).catch(function (err) { console.error(err); });
    });

    el('vd-country')?.addEventListener('change', onCountrySelected);

    el('vd-show-historical')?.addEventListener('change', function (e) {
        state.showHistorical = e.target.checked;
        rebuildIndicatorsGrid();
        saveScope();
    });

    el('vd-flagged-only')?.addEventListener('change', function (e) {
        state.flaggedOnly = e.target.checked;
        applyIndicatorFilters();
        saveScope();
    });

    el('vd-generate-country')?.addEventListener('click', function () {
        if (!state.selectedCountry || !window.confirm(t.generateConfirm || 'Generate questions?')) return;
        runChecks([state.selectedCountry.country_id]).catch(function (e) { showFeedback(e.message, 'error'); });
    });

    /* ——— Init ——— */

    initIndicatorsGrid([]);
    setActionButtonsEnabled(false);

    async function restoreSavedScope() {
        var saved = readSavedScope();
        if (saved) {
            state.showHistorical = !!saved.showHistorical;
            state.flaggedOnly = !!saved.flaggedOnly;
            if (el('vd-show-historical')) el('vd-show-historical').checked = state.showHistorical;
            if (el('vd-flagged-only')) el('vd-flagged-only').checked = state.flaggedOnly;
        }

        if (!saved || !saved.templateId) {
            if (getTemplateId()) await applyScope(null, null);
            return;
        }

        if (!setTemplateId(saved.templateId)) {
            if (getTemplateId()) await applyScope(null, null);
            return;
        }

        await applyScope(saved.period, saved.countryId);
    }

    restoreSavedScope().catch(function (err) { console.error(err); });
})();
