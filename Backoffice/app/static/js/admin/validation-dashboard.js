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
        layout: 'comparison',
        search: '',
    };

    function el(id) { return document.getElementById(id); }

    var esc = window.esc || function (s) {
        if (s == null) return '';
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    };
    var scopeLoader = window.ValidationScopeLoader || {};

    function getTemplateId() {
        return el('vd-template')?.value || '';
    }

    function templateTabButtons() {
        return document.querySelectorAll('#vd-template-tabs .vd-template-tab');
    }

    function uprTemplateTabButtons() {
        return document.querySelectorAll('#vd-upr-template-tabs .vd-upr-template-tab');
    }

    function parseChildIds(btn) {
        var raw = btn && btn.getAttribute('data-child-ids');
        if (!raw) return [];
        return raw.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    }

    function findTemplateTabForId(templateId) {
        var target = String(templateId || '');
        var buttons = templateTabButtons();
        for (var i = 0; i < buttons.length; i++) {
            var btn = buttons[i];
            if (btn.getAttribute('data-template-id') === target) return btn;
            if (parseChildIds(btn).indexOf(target) !== -1) return btn;
        }
        return null;
    }

    function syncUprSubtabs(activeTemplateId) {
        var subtabs = el('vd-upr-subtabs');
        var parent = findTemplateTabForId(activeTemplateId);
        var childIds = parseChildIds(parent);
        var show = !!(subtabs && childIds.length);
        if (subtabs) subtabs.classList.toggle('hidden', !show);
        if (!show) return;
        var A = window.AdminUnderlineTabs;
        var target = String(activeTemplateId || '');
        uprTemplateTabButtons().forEach(function (btn) {
            var isActive = btn.getAttribute('data-template-id') === target;
            if (A) A.setStripButtonActive(btn, isActive);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });
    }

    function setTemplateId(templateId) {
        var target = templateId == null ? '' : String(templateId);
        var matchedTab = target ? findTemplateTabForId(target) : null;
        var matched = !!matchedTab;
        var A = window.AdminUnderlineTabs;
        templateTabButtons().forEach(function (btn) {
            var isActive = btn === matchedTab;
            if (A) A.setStripButtonActive(btn, isActive);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });
        if (!matched && target) return false;
        var hidden = el('vd-template');
        if (hidden) hidden.value = matched ? target : '';
        syncUprSubtabs(matched ? target : '');
        return matched || !target;
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
    function hideFeedback() {
        if (!feedbackEl) return;
        feedbackEl.textContent = '';
        feedbackEl.classList.add('hidden');
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
                layout: state.layout,
                flaggedOnly: state.flaggedOnly,
                search: state.search,
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

    function questionStatusLabel(status) {
        var map = {
            open: t.statusOpen || 'Open',
            answered: t.statusAnswered || 'Answered',
            waived: t.statusWaived || 'Waived',
            resolved: t.statusResolved || 'Resolved',
        };
        return map[status] || status;
    }

    function questionStatusHtml(row) {
        var status = row && row.question_status;
        if (status) {
            var variant = 'neutral';
            if (status === 'open') variant = 'warning';
            else if (status === 'answered' || status === 'resolved') variant = 'success';
            return badge(questionStatusLabel(status), variant);
        }
        if (row && row.flagged) {
            return badge(t.notGenerated || 'Not generated', 'neutral');
        }
        return '<span class="vd-muted">—</span>';
    }

    function sentHtml(row) {
        if (row && row.sent_at) return esc(formatIsoDate(row.sent_at));
        if (row && row.question_id && row.question_status === 'open') {
            return badge(t.notSent || 'Not sent', 'pending');
        }
        return '<span class="vd-muted">—</span>';
    }

    function textHtml(value) {
        if (value == null || value === '') return '<span class="vd-muted">—</span>';
        return '<div class="vd-multiline-text">' + esc(String(value)) + '</div>';
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
        renderIndicatorsTable();
        updateKpis();
        setActionButtonsEnabled(false);
        hideFeedback();
    }

    function updateKpis() {
        var preview = state.preview;
        var flagsEl = el('vd-kpi-flags');
        if (flagsEl) flagsEl.textContent = preview ? preview.flag_count : '—';
    }

    /* ——— Indicator table ——— */

    function rowSearchText(row) {
        if (!row) return '';
        return [
            row.indicator_label,
            row.kpi_code,
            automaticCheckLabel(row),
            row.question_preview,
        ].filter(Boolean).join(' ').toLowerCase();
    }

    function filteredIndicatorRows() {
        var query = (state.search || '').trim().toLowerCase();
        return state.rawIndicatorRows.filter(function (row) {
            if (state.flaggedOnly && !row.flagged) return false;
            if (!query) return true;
            return rowSearchText(row).indexOf(query) !== -1;
        });
    }

    var LAYOUTS = ['comparison', 'checks', 'questions'];

    function comparisonYears() {
        return (state.historyYears || []).slice(0, 3);
    }

    function currentComparisonYear() {
        var years = comparisonYears();
        return years.length ? years[0] : null;
    }

    function priorComparisonYear() {
        var years = comparisonYears();
        return years.length > 1 ? years[1] : null;
    }

    function displayedComparisonYears() {
        return comparisonYears().slice().reverse();
    }

    function yearValue(row, year) {
        var hv = (row && row.historical_values) || {};
        var raw = hv[String(year)];
        if ((raw == null || raw === '') && String(currentComparisonYear()) === String(year)) raw = row.current_value;
        return raw == null || raw === '' ? '' : formatNumericDisplay(raw);
    }

    function parseDisplayNumber(value) {
        if (value == null || value === '') return null;
        var num = Number(String(value).replace(/,/g, '').trim());
        return Number.isFinite(num) ? num : null;
    }

    function changeHtml(row) {
        var currentYear = currentComparisonYear();
        var priorYear = priorComparisonYear();
        if (currentYear == null || priorYear == null) return '<span class="vd-muted">—</span>';
        var current = parseDisplayNumber(yearValue(row, currentYear));
        var prior = parseDisplayNumber(yearValue(row, priorYear));
        if (current == null || prior == null || prior === 0) return '<span class="vd-muted">—</span>';
        var pct = ((current - prior) / Math.abs(prior)) * 100;
        var cls = pct > 0.05 ? 'vd-change-up' : (pct < -0.05 ? 'vd-change-down' : 'vd-change-flat');
        var sign = pct > 0 ? '+' : '';
        return '<span class="' + cls + '">' + sign + pct.toFixed(1) + '%</span>';
    }

    function checkHtml(row) {
        if (row && row.flagged) return badge(automaticCheckLabel(row), 'danger');
        return '<span class="vd-muted">—</span>';
    }

    function severityHtml(row) {
        if (!row || !row.severity) return '<span class="vd-muted">—</span>';
        var variant = row.severity === 'error' ? 'danger' : (row.severity === 'warning' ? 'warning' : (row.severity === 'info' ? 'info' : 'neutral'));
        return badge(row.severity, variant);
    }

    function answerHtml(row) {
        if (row && row.answer_preview) return textHtml(row.answer_preview);
        if (row && row.has_answer) return textHtml(t.answerReceived || 'Answer received');
        return '<span class="vd-muted">—</span>';
    }

    function headerCell(label, className) {
        return { text: label == null ? '' : String(label), className: className || '' };
    }

    function htmlCell(html, className) {
        return { html: html || '', className: className || '' };
    }

    function valueCell(display, className) {
        if (!display) return htmlCell('<span class="vd-muted">—</span>', className);
        return { text: String(display), className: className || '' };
    }

    function appendFragment(parent, html) {
        var parsed = new DOMParser().parseFromString('<div>' + (html || '') + '</div>', 'text/html');
        var wrapper = parsed.body.firstChild;
        if (!wrapper) return;
        while (wrapper.firstChild) parent.appendChild(wrapper.firstChild);
    }

    function appendCell(row, tag, spec) {
        var cell = document.createElement(tag);
        if (spec.className) cell.className = spec.className;
        if (spec.html) appendFragment(cell, spec.html);
        else cell.textContent = spec.text == null ? '' : String(spec.text);
        row.appendChild(cell);
    }

    function indicatorHeaderCells() {
        if (state.layout === 'checks') {
            return [
                headerCell(t.indicator || 'Indicator', 'vd-sticky'),
                headerCell(t.value || 'Value', 'vd-num'),
                headerCell(t.automaticCheck || 'Automatic check', 'vd-cell-wrap'),
                headerCell(t.severity || 'Severity'),
            ];
        }
        if (state.layout === 'questions') {
            return [
                headerCell(t.indicator || 'Indicator', 'vd-sticky'),
                headerCell(t.automaticCheck || 'Automatic check', 'vd-cell-wrap'),
                headerCell(t.severity || 'Severity'),
                headerCell(t.questionStatus || 'Question status'),
                headerCell(t.sent || 'Sent'),
                headerCell(t.answer || 'Answer', 'vd-cell-wrap'),
                headerCell(t.questionPreview || 'Question preview', 'vd-cell-wrap'),
            ];
        }
        var cells = [headerCell(t.indicator || 'Indicator', 'vd-sticky')];
        var displayed = displayedComparisonYears();
        var currentYear = currentComparisonYear();
        if (!displayed.length) cells.push(headerCell(t.value || 'Value', 'vd-num'));
        displayed.forEach(function (year) {
            if (String(year) === String(currentYear) && priorComparisonYear() != null) {
                var changeLabel = t.change || 'Change';
                changeLabel += ' vs ' + priorComparisonYear();
                cells.push(headerCell(changeLabel, 'vd-num'));
            }
            cells.push(headerCell(String(year), 'vd-num'));
        });
        cells.push(headerCell(t.automaticCheck || 'Automatic check', 'vd-cell-wrap'));
        return cells;
    }

    function indicatorBodyCells(row) {
        var name = { text: row.indicator_label || row.kpi_code || '', className: 'vd-sticky' };
        if (state.layout === 'checks') {
            return [
                name,
                valueCell(row.current_value ? formatNumericDisplay(row.current_value) : '', 'vd-num'),
                htmlCell(checkHtml(row), 'vd-cell-wrap'),
                htmlCell(severityHtml(row)),
            ];
        }
        if (state.layout === 'questions') {
            return [
                name,
                htmlCell(checkHtml(row), 'vd-cell-wrap'),
                htmlCell(severityHtml(row)),
                htmlCell(questionStatusHtml(row)),
                htmlCell(sentHtml(row)),
                htmlCell(answerHtml(row), 'vd-cell-wrap'),
                htmlCell(textHtml(row.question_preview), 'vd-cell-wrap'),
            ];
        }
        var cells = [name];
        var displayed = displayedComparisonYears();
        var currentYear = currentComparisonYear();
        if (!displayed.length) {
            cells.push(valueCell(row.current_value ? formatNumericDisplay(row.current_value) : '', 'vd-num'));
        }
        displayed.forEach(function (year) {
            if (String(year) === String(currentYear) && priorComparisonYear() != null) {
                cells.push(htmlCell(changeHtml(row), 'vd-num'));
            }
            cells.push(valueCell(yearValue(row, year), 'vd-num'));
        });
        cells.push(htmlCell(checkHtml(row), 'vd-cell-wrap'));
        return cells;
    }

    function layoutHint() {
        if (state.layout === 'checks') return t.layoutHintChecks || 'Automatic checks and severity for this round.';
        if (state.layout === 'questions') return t.layoutHintQuestions || 'Generated questions, whether they were sent, and focal-point answers.';
        return t.layoutHintComparison || 'This round beside the previous two reporting rounds.';
    }

    function syncLayoutControls() {
        document.querySelectorAll('[data-vd-layout]').forEach(function (btn) {
            var active = btn.getAttribute('data-vd-layout') === state.layout;
            btn.classList.toggle('is-active', active);
            btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        var hint = el('vd-layout-hint');
        if (hint) hint.textContent = layoutHint();
    }

    function renderIndicatorsTable() {
        var table = el('vd-indicators-table');
        var empty = el('vd-indicators-empty');
        syncLayoutControls();
        if (!table) return;
        var head = table.querySelector('thead');
        var body = table.querySelector('tbody');
        var rows = filteredIndicatorRows();
        if (head) head.replaceChildren();
        if (body) body.replaceChildren();
        if (rows.length && head && body) {
            var headRow = document.createElement('tr');
            indicatorHeaderCells().forEach(function (spec) { appendCell(headRow, 'th', spec); });
            head.appendChild(headRow);
            rows.forEach(function (row) {
                var tr = document.createElement('tr');
                if (row.flagged) tr.className = 'vd-row-flagged';
                indicatorBodyCells(row).forEach(function (spec) { appendCell(tr, 'td', spec); });
                body.appendChild(tr);
            });
        }
        if (empty) {
            var hasCountry = !!state.selectedCountry;
            var message = !hasCountry
                ? (t.selectCountry || 'Select a country to compare indicators.')
                : (t.noIndicators || 'No indicators match this view.');
            empty.textContent = message;
            empty.classList.toggle('hidden', rows.length > 0);
        }
        var scroll = table.closest('.vd-table-scroll');
        if (scroll) scroll.classList.toggle('hidden', !rows.length);
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
            renderIndicatorsTable();
            updateKpis();
            hideFeedback();
            saveScope();
            return;
        }
        var opt = countryEl.options[countryEl.selectedIndex];
        state.selectedCountry = state.countries.find(function (c) { return String(c.country_id) === String(countryId); }) || {
            country_id: +countryId,
            country_name: opt.textContent,
            period_name: opt.getAttribute('data-period') || state.period,
        };
        setActionButtonsEnabled(false);
        loadIndicatorPreview(state.selectedCountry.country_id);
        saveScope();
    }

    /* ——— Data loading ——— */

    async function loadPeriods(preferredPeriod) {
        var templateId = getTemplateId();
        var periodEl = el('vd-period');
        if (!periodEl) return;
        await scopeLoader.loadPeriodsIntoSelect({
            selectEl: periodEl,
            periodsUrl: config.periodsUrl,
            templateId: templateId,
            preferredPeriod: preferredPeriod,
            emptyLabel: t.selectTemplatePeriod || 'Select template first',
            chooseLabel: 'Choose period',
        });
        saveScope();
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
            state.countries = await scopeLoader.loadCountries({
                countriesUrl: config.countriesUrl,
                templateId: templateId,
                period: period,
            });
            return populateCountrySelect(state.countries, preferredCountryId);
        } catch (err) {
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
        renderIndicatorsTable();
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
            var data = await window.apiFetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
            state.preview = data.preview || null;
            state.rawIndicatorRows = (state.preview && state.preview.indicators) || [];
            state.historyYears = (state.preview && state.preview.history_years) || [];
            var checksEnabled = !!(state.preview && state.preview.validation_enabled !== false && state.preview.rule_pack);
            setActionButtonsEnabled(!!state.selectedCountry && checksEnabled);
            renderIndicatorsTable();
            updateKpis();
            if (state.preview && state.preview.validation_enabled === false && state.preview.message) {
                showFeedback(state.preview.message, 'info');
            } else {
                hideFeedback();
            }
        } catch (err) {
            setActionButtonsEnabled(false);
            showFeedback((err && err.message) || t.previewFailed || 'Preview failed', 'error');
        }
    }

    async function runChecks(countryIds) {
        var data = await window.apiFetch(config.runChecksUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, Accept: 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({
                template_id: +state.templateId,
                period_name: state.period,
                country_ids: countryIds,
            }),
        });
        showFeedback(data.message || 'Questions generated.', data.has_errors ? 'error' : 'success');
        var countryId = state.selectedCountry && state.selectedCountry.country_id;
        await loadDashboard(countryId);
    }

    /* ——— Event wiring ——— */

    function switchTemplate(id) {
        if (!id || id === getTemplateId()) {
            // Still sync UPR subtabs when re-clicking the parent product tab.
            syncUprSubtabs(getTemplateId());
            return;
        }
        setTemplateId(id);
        resetDashboardScope();
        applyScope(null, null).catch(function (err) { console.error(err); });
        if (window.validationDashboardTracker && window.validationDashboardTracker.onTemplateChanged) {
            window.validationDashboardTracker.onTemplateChanged(null).catch(function (err) { console.error(err); });
        }
    }

    templateTabButtons().forEach(function (btn) {
        btn.addEventListener('click', function () {
            var childIds = parseChildIds(btn);
            var current = getTemplateId();
            // Keep the active UPR child when re-selecting the product tab.
            var id = (childIds.length && childIds.indexOf(current) !== -1)
                ? current
                : btn.getAttribute('data-template-id');
            switchTemplate(id);
        });
    });

    uprTemplateTabButtons().forEach(function (btn) {
        btn.addEventListener('click', function () {
            switchTemplate(btn.getAttribute('data-template-id'));
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

    document.querySelectorAll('[data-vd-layout]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var layout = btn.getAttribute('data-vd-layout');
            if (LAYOUTS.indexOf(layout) === -1 || layout === state.layout) return;
            state.layout = layout;
            renderIndicatorsTable();
            saveScope();
        });
    });

    el('vd-flagged-only')?.addEventListener('change', function (e) {
        state.flaggedOnly = e.target.checked;
        renderIndicatorsTable();
        saveScope();
    });

    el('vd-indicator-search')?.addEventListener('input', function (e) {
        state.search = e.target.value || '';
        renderIndicatorsTable();
        saveScope();
    });

    el('vd-generate-country')?.addEventListener('click', function () {
        if (!state.selectedCountry || !window.confirm(t.generateConfirm || 'Generate questions?')) return;
        runChecks([state.selectedCountry.country_id]).catch(function (e) { showFeedback(e.message, 'error'); });
    });

    /* ——— Init ——— */

    renderIndicatorsTable();
    setActionButtonsEnabled(false);

    async function restoreSavedScope() {
        var saved = readSavedScope();
        if (saved) {
            if (LAYOUTS.indexOf(saved.layout) !== -1) state.layout = saved.layout;
            state.flaggedOnly = !!saved.flaggedOnly;
            state.search = typeof saved.search === 'string' ? saved.search : '';
            if (el('vd-flagged-only')) el('vd-flagged-only').checked = state.flaggedOnly;
            if (el('vd-indicator-search')) el('vd-indicator-search').value = state.search;
            syncLayoutControls();
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
