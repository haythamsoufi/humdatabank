/**
 * Validation Questions — AG Grid (all questions + country summary tab).
 */
(function () {
    'use strict';

    var config = window.validationQuestionsGridConfig || {};
    var t = window.VQ_GRID_TRANSLATIONS || {};
    var csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    var feedbackEl = document.getElementById('vq-feedback');
    var gridApi = null;
    var gridHelper = null;
    var summaryApi = null;
    var questionsChart = null;
    var summaryCountries = [];
    var editModalCtrl = null;
    var followUpModalCtrl = null;
    var editingRow = null;
    var rowStore = {};
    var VQ_DEBUG = true;

    function vqLog(label, payload) {
        if (!VQ_DEBUG) return;
        if (payload === undefined) {
            console.log('[VQ Grid]', label);
        } else {
            console.log('[VQ Grid]', label, payload);
        }
    }

    function pickTextField(row, snakeCaseKey, excelKey, fallbackKey) {
        if (!row) return '';
        if (row[snakeCaseKey] != null && row[snakeCaseKey] !== '') {
            return String(row[snakeCaseKey]);
        }
        if (excelKey && row[excelKey] != null && row[excelKey] !== '') {
            return String(row[excelKey]);
        }
        if (fallbackKey && row[fallbackKey] != null && row[fallbackKey] !== '') {
            return String(row[fallbackKey]);
        }
        return '';
    }

    function normalizeListRow(row) {
        if (!row || typeof row !== 'object') return row;
        return Object.assign({}, row, {
            question_text: pickTextField(row, 'question_text', 'Question', 'question'),
            answer_text: pickTextField(row, 'answer_text', 'Answer Text', 'answer'),
            definition_text: pickTextField(row, 'definition_text', 'Definition', 'definition'),
        });
    }

    function indexRowStore(rows) {
        rowStore = {};
        (rows || []).forEach(function (row) {
            if (row && row.id != null) {
                rowStore[row.id] = row;
            }
        });
    }

    function getStoredRowField(data, fieldName) {
        if (!data) return '';
        if (data[fieldName] != null && data[fieldName] !== '') {
            return String(data[fieldName]);
        }
        var stored = rowStore[data.id];
        if (stored && stored[fieldName] != null && stored[fieldName] !== '') {
            return String(stored[fieldName]);
        }
        return '';
    }

    var CHART_COLORS = {
        open: 'rgba(245, 158, 11, 0.85)',
        answered: 'rgba(59, 130, 246, 0.85)',
        waived: 'rgba(156, 163, 175, 0.85)',
        resolved: 'rgba(16, 185, 129, 0.85)',
    };

    function esc(s) {
        if (s == null) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function showFeedback(message, type) {
        if (!feedbackEl) return;
        feedbackEl.textContent = message;
        feedbackEl.className = 'mb-4 rounded-md px-4 py-3 text-sm border ';
        if (type === 'error') {
            feedbackEl.classList.add('bg-red-50', 'border-red-200', 'text-red-800');
        } else if (type === 'success') {
            feedbackEl.classList.add('bg-green-50', 'border-green-200', 'text-green-800');
        } else {
            feedbackEl.classList.add('bg-blue-50', 'border-blue-200', 'text-blue-800');
        }
        feedbackEl.classList.remove('hidden');
    }

    function badge(text, cls) {
        return '<span class="inline-flex px-2 py-0.5 rounded-full text-xs font-medium ' + cls + '">' + esc(text) + '</span>';
    }

    function severityRenderer(params) {
        var map = { error: 'bg-red-100 text-red-800', warning: 'bg-amber-100 text-amber-800', info: 'bg-blue-100 text-blue-800' };
        var sev = params.value || '';
        return badge(sev, map[sev] || 'bg-gray-100 text-gray-800');
    }

    function statusRenderer(params) {
        var map = {
            open: 'bg-orange-100 text-orange-800',
            answered: 'bg-green-100 text-green-800',
            waived: 'bg-gray-100 text-gray-700',
            resolved: 'bg-slate-100 text-slate-700',
        };
        var st = params.value || '';
        return badge(st, map[st] || 'bg-gray-100 text-gray-800');
    }

    function createMultilineTextRenderer(fieldName) {
        var logCount = 0;
        return function (params) {
            var val = getStoredRowField(params.data, fieldName);
            if (VQ_DEBUG && logCount < 5) {
                logCount += 1;
                vqLog('cellRenderer ' + fieldName + ' #' + logCount, {
                    colId: params.column && params.column.getColId && params.column.getColId(),
                    rowId: params.data && params.data.id,
                    paramsValue: params.value,
                    resolvedValue: val,
                    dataKeys: params.data ? Object.keys(params.data) : [],
                });
            }

            if (!val) {
                var dash = document.createElement('span');
                dash.className = 'text-gray-400';
                dash.textContent = '—';
                return dash;
            }

            var wrap = document.createElement('div');
            wrap.className = 'vq-multiline-text text-sm text-gray-900';
            wrap.textContent = val;
            return wrap;
        };
    }

    function multilineColumnDef(field, headerName, flex, minWidth) {
        return {
            field: field,
            colId: field,
            headerName: headerName,
            flex: flex,
            minWidth: minWidth,
            filter: 'agTextColumnFilter',
            wrapText: true,
            autoHeight: true,
            cellClass: 'vq-multiline-cell',
            valueGetter: function (params) {
                return getStoredRowField(params.data, field);
            },
            cellRenderer: createMultilineTextRenderer(field),
            cellStyle: {
                whiteSpace: 'normal',
                lineHeight: '1.4',
                alignItems: 'flex-start',
            },
        };
    }

    function inspectQuestionColumnDebug(api, phase) {
        if (!VQ_DEBUG || !api) return;
        setTimeout(function () {
            var storageKey = 'ag-grid-column-visibility-admin-validation-questions';
            var saved = null;
            try {
                saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
            } catch (err) {
                saved = { parseError: String(err) };
            }

            var col = typeof api.getColumn === 'function' ? api.getColumn('question_text') : null;
            var colDefs = typeof api.getColumnDefs === 'function' ? api.getColumnDefs() : [];
            var qDef = colDefs.find(function (c) { return c.field === 'question_text'; });
            var samples = [];

            api.forEachNode(function (node, idx) {
                if (idx >= 5) return;
                samples.push({
                    rowIndex: idx,
                    id: node.data && node.data.id,
                    question_text: node.data && node.data.question_text,
                    answer_text: node.data && node.data.answer_text,
                });
            });

            var cells = document.querySelectorAll('#validationQuestionsGrid .ag-cell[col-id="question_text"]');
            var cellInfo = Array.prototype.slice.call(cells, 0, 5).map(function (cell, i) {
                var style = window.getComputedStyle(cell);
                return {
                    index: i,
                    offsetHeight: cell.offsetHeight,
                    offsetWidth: cell.offsetWidth,
                    innerHTML: cell.innerHTML.slice(0, 300),
                    textContent: cell.textContent.slice(0, 200),
                    display: style.display,
                    visibility: style.visibility,
                    opacity: style.opacity,
                    color: style.color,
                    overflow: style.overflow,
                };
            });

            vqLog(phase + ' — saved question_text column state', saved && saved.question_text);
            vqLog(phase + ' — all column ids', typeof api.getColumns === 'function'
                ? api.getColumns().map(function (c) {
                    return {
                        colId: c.getColId(),
                        field: c.getColDef().field,
                        visible: c.isVisible(),
                        width: c.getActualWidth(),
                    };
                })
                : 'getColumns unavailable');
            vqLog(phase + ' — question_text AG Grid column', {
                found: !!col,
                visible: col && col.isVisible(),
                width: col && col.getActualWidth(),
                pinned: col && col.getPinned(),
                colDefHasRenderer: !!(qDef && qDef.cellRenderer),
                colDefRendererType: qDef && typeof qDef.cellRenderer,
            });
            vqLog(phase + ' — sample row data', samples);
            vqLog(phase + ' — question_text DOM cells (' + cells.length + ')', cellInfo);
        }, phase === 'onReady' ? 450 : 150);
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

    function resetCountrySelect() {
        var countryEl = document.getElementById('vqs-country');
        if (!countryEl) return;
        summaryCountries = [];
        countryEl.innerHTML = '<option value="">' + esc(t.loadSummaryFirst || 'Load summary first') + '</option>';
        countryEl.disabled = true;
        countryEl.value = '';
        setSendEnabled(false);
    }

    function populateCountrySelect(countries, preferredCountryId) {
        var countryEl = document.getElementById('vqs-country');
        if (!countryEl) return null;
        summaryCountries = countries || [];
        if (!summaryCountries.length) {
            countryEl.innerHTML = '<option value="">' + esc('No countries with assignments') + '</option>';
            countryEl.disabled = true;
            countryEl.value = '';
            setSendEnabled(false);
            return null;
        }
        countryEl.innerHTML = summaryCountries.map(function (c) {
            return '<option value="' + c.country_id + '" data-period="' + esc(c.period_name) + '">' + esc(c.country_name) + '</option>';
        }).join('');
        countryEl.disabled = false;
        var matched = preferredCountryId != null && selectOptionValue(countryEl, preferredCountryId);
        if (!matched) {
            countryEl.selectedIndex = 0;
        }
        setSendEnabled(!!countryEl.value);
        return countryEl.value;
    }

    function setSendEnabled(enabled) {
        var sendBtn = document.getElementById('vqs-send');
        if (sendBtn) sendBtn.disabled = !enabled;
    }

    function getSelectedSummaryCountry() {
        var countryEl = document.getElementById('vqs-country');
        var countryId = countryEl?.value;
        if (!countryId) return null;
        var opt = countryEl.options[countryEl.selectedIndex];
        return summaryCountries.find(function (c) { return String(c.country_id) === String(countryId); }) || {
            country_id: +countryId,
            country_name: opt.textContent,
            period_name: opt.getAttribute('data-period') || document.getElementById('vqs-period')?.value || '',
        };
    }

    function selectSummaryCountry(countryId) {
        var countryEl = document.getElementById('vqs-country');
        if (!countryEl || countryId == null) return;
        if (selectOptionValue(countryEl, countryId)) {
            setSendEnabled(true);
        }
    }

    async function sendOpenQuestions() {
        var templateId = document.getElementById('vqs-template')?.value;
        var country = getSelectedSummaryCountry();
        if (!templateId || !country) return;
        var resp = await fetch(config.sendUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, Accept: 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({
                template_id: +templateId,
                period_name: country.period_name || document.getElementById('vqs-period')?.value,
                country_id: country.country_id,
                channels: ['in_app', 'email'],
            }),
        });
        var data = await resp.json();
        if (!resp.ok) throw new Error(data.error || t.sendFailed || 'Send failed');
        showFeedback(t.sendSuccess || 'Validation questions sent to focal points.', 'success');
    }

    function buildColumnDefs() {
        return [
            { field: 'entity_name', headerName: t.country || 'Country', flex: 1, minWidth: 160, filter: 'customSetFilter' },
            { field: 'template_name', headerName: t.template || 'Template', flex: 1, minWidth: 140, filter: 'customSetFilter' },
            { field: 'period_name', headerName: t.period || 'Period', width: 110, minWidth: 110, filter: 'customSetFilter' },
            { field: 'rule_code', headerName: t.rule || 'Rule', width: 150, minWidth: 150, filter: 'agTextColumnFilter' },
            {
                field: 'indicator_name',
                headerName: t.indicator || 'Indicator',
                flex: 1,
                minWidth: 180,
                filter: 'agTextColumnFilter',
            },
            {
                field: 'follow_up_round',
                headerName: t.followUpRound || 'Follow-up',
                width: 95,
                minWidth: 95,
                filter: 'agNumberColumnFilter',
                valueFormatter: function (p) {
                    var round = p.value || 0;
                    return round ? String(round) : '—';
                },
            },
            { field: 'severity', headerName: t.severity || 'Severity', width: 110, minWidth: 110, filter: 'customSetFilter', cellRenderer: severityRenderer },
            { field: 'status', headerName: t.status || 'Status', width: 110, minWidth: 110, filter: 'customSetFilter', cellRenderer: statusRenderer },
            multilineColumnDef('question_text', t.question || 'Question', 1.4, 280),
            multilineColumnDef('answer_text', t.answer || 'Answer', 1.2, 200),
            { field: 'sent_at', headerName: t.sent || 'Sent', width: 110, minWidth: 110, valueFormatter: function (p) { return p.value ? String(p.value).slice(0, 10) : '—'; } },
            { field: 'source', headerName: t.source || 'Source', width: 95, minWidth: 95, filter: 'customSetFilter' },
            {
                colId: 'actions',
                headerName: t.actions || 'Actions',
                width: 220,
                minWidth: 220,
                pinned: 'right',
                sortable: false,
                filter: false,
                cellRenderer: function (params) {
                    var d = params.data || {};
                    if (!d.id) return '';
                    var parts = [
                        '<button type="button" class="text-sm text-ifrc-navy hover:underline vq-edit" data-id="' + d.id + '">' + esc(t.edit || 'Edit') + '</button>',
                    ];
                    if (d.can_follow_up) {
                        parts.push('<button type="button" class="text-sm text-ifrc-navy hover:underline vq-follow-up ml-2" data-id="' + d.id + '">' + esc(t.followUp || 'Follow up') + '</button>');
                    }
                    if (d.status === 'open') {
                        parts.push('<button type="button" class="text-sm text-ifrc-navy hover:underline vq-waive ml-2" data-id="' + d.id + '">' + esc(t.waive || 'Waive') + '</button>');
                    } else if (d.status === 'waived' || d.status === 'answered') {
                        parts.push('<button type="button" class="text-sm text-ifrc-navy hover:underline vq-reopen ml-2" data-id="' + d.id + '">' + esc(t.reopen || 'Reopen') + '</button>');
                    }
                    return parts.join('');
                },
            },
        ];
    }

    function buildSummaryColumnDefs() {
        return [
            { field: 'country_name', headerName: t.country || 'Country', flex: 1, minWidth: 180, filter: 'customSetFilter' },
            { field: 'period_name', headerName: t.period || 'Period', width: 120, minWidth: 120, filter: 'customSetFilter' },
            { field: 'open_questions', headerName: t.openQuestions || 'Open questions', width: 130, minWidth: 130, filter: 'agNumberColumnFilter' },
            { field: 'answered_questions', headerName: t.answered || 'Answered', width: 110, minWidth: 110, filter: 'agNumberColumnFilter' },
            { field: 'waived_questions', headerName: t.waived || 'Waived', width: 100, minWidth: 100, filter: 'agNumberColumnFilter' },
            { field: 'resolved_questions', headerName: t.resolved || 'Resolved', width: 110, minWidth: 110, filter: 'agNumberColumnFilter' },
            { field: 'total_questions', headerName: t.totalQuestions || 'Total questions', width: 130, minWidth: 130, filter: 'agNumberColumnFilter' },
        ];
    }

    function aggregateQuestionTotals(rows) {
        return rows.reduce(function (acc, row) {
            acc.open += row.open_questions || 0;
            acc.answered += row.answered_questions || 0;
            acc.waived += row.waived_questions || 0;
            acc.resolved += row.resolved_questions || 0;
            return acc;
        }, { open: 0, answered: 0, waived: 0, resolved: 0 });
    }

    function updateQuestionStatusChart(rows) {
        if (typeof Chart === 'undefined') return;
        var canvas = document.getElementById('vqs-chart-questions');
        if (!canvas) return;

        if (questionsChart) {
            questionsChart.destroy();
            questionsChart = null;
        }

        var totals = aggregateQuestionTotals(rows);
        var values = [totals.open, totals.answered, totals.waived, totals.resolved];
        var sum = values.reduce(function (a, b) { return a + b; }, 0);
        var metaEl = document.getElementById('vqs-chart-meta');
        if (metaEl) {
            metaEl.textContent = sum
                ? rows.length + ' ' + (t.countriesLabel || 'countries')
                : '';
        }

        questionsChart = new Chart(canvas.getContext('2d'), {
            type: 'doughnut',
            data: {
                labels: [
                    t.chartOpen || 'Open',
                    t.chartAnswered || 'Answered',
                    t.chartWaived || 'Waived',
                    t.chartResolved || 'Resolved',
                ],
                datasets: [{
                    data: sum ? values : [1],
                    backgroundColor: sum
                        ? [CHART_COLORS.open, CHART_COLORS.answered, CHART_COLORS.waived, CHART_COLORS.resolved]
                        : ['rgba(209, 213, 219, 0.5)'],
                    borderWidth: 0,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
                    tooltip: { enabled: sum > 0 },
                },
            },
        });
    }

    function activateTab(tabId) {
        var tabs = document.querySelectorAll('#vq-tabs [role="tab"]');
        var A = window.AdminUnderlineTabs;
        tabs.forEach(function (btn) {
            var active = btn.getAttribute('data-tab') === tabId;
            if (A) A.setStripButtonActive(btn, active);
            btn.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        document.querySelectorAll('.vq-panel').forEach(function (panel) {
            panel.classList.toggle('hidden', panel.id !== 'panel-' + tabId);
        });
    }

    async function loadRows() {
        try {
            var listUrl = config.listUrl + (config.listUrl.indexOf('?') >= 0 ? '&' : '?') + '_=' + Date.now();
            var resp = await fetch(listUrl, {
                headers: { Accept: 'application/json' },
                credentials: 'same-origin',
                cache: 'no-store',
            });
            var rawText = await resp.text();
            var data = JSON.parse(rawText || '{}');
            if (!resp.ok) throw new Error(data.error || t.loadFailed);
            var rows = (data.rows || []).map(normalizeListRow);
            indexRowStore(rows);
            vqLog('loadRows API response', {
                ok: resp.ok,
                rowCount: rows.length,
                rawHasQuestionTextKey: rawText.indexOf('"question_text"') >= 0,
                withQuestionText: rows.filter(function (r) { return r.question_text; }).length,
                firstRowKeys: rows[0] ? Object.keys(rows[0]) : [],
                sample: rows.slice(0, 2).map(function (r) {
                    return {
                        id: r.id,
                        question_text: r.question_text,
                        question_text_len: r.question_text ? String(r.question_text).length : 0,
                    };
                }),
            });
            if (gridHelper) {
                gridHelper.setRowData(rows);
                gridHelper.refresh();
                AgGridHelper.enforceColumnMinWidths(gridApi);
            }
            return rows;
        } catch (err) {
            console.error(err);
            showFeedback(t.loadFailed || 'Failed to load', 'error');
            return [];
        }
    }

    async function loadSummaryPeriods() {
        var templateId = document.getElementById('vqs-template')?.value;
        var periodEl = document.getElementById('vqs-period');
        if (!periodEl) return;
        if (!templateId) {
            periodEl.innerHTML = '<option value="">' + esc('Select template first') + '</option>';
            periodEl.disabled = true;
            resetCountrySelect();
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

    async function loadCountrySummary() {
        var templateId = document.getElementById('vqs-template')?.value;
        var period = document.getElementById('vqs-period')?.value;
        if (!templateId || !period) {
            showFeedback(t.selectTemplatePeriod || 'Select template and period.', 'error');
            return;
        }
        var preferredCountryId = document.getElementById('vqs-country')?.value || null;
        try {
            var url = config.countriesUrl + '?template_id=' + encodeURIComponent(templateId) + '&period=' + encodeURIComponent(period);
            var resp = await fetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
            var data = await resp.json();
            if (!resp.ok) throw new Error(data.error || t.summaryFailed);
            var rows = data.countries || [];
            if (summaryApi) {
                summaryApi.setGridOption('rowData', rows);
            }
            updateQuestionStatusChart(rows);
            populateCountrySelect(rows, preferredCountryId);
            showFeedback('Loaded summary for ' + rows.length + ' countries.', 'info');
        } catch (err) {
            console.error(err);
            resetCountrySelect();
            showFeedback(t.summaryFailed || 'Summary failed', 'error');
        }
    }

    async function updateStatus(id, status) {
        var url = (config.statusUrlTemplate || '').replace('{id}', id);
        var resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, Accept: 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ status: status }),
        });
        var data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Update failed');
        showFeedback(t.updated || 'Status updated', 'success');
        await loadRows();
    }

    function findRowById(id) {
        var found = null;
        if (gridApi) {
            gridApi.forEachNode(function (node) {
                if (node.data && String(node.data.id) === String(id)) {
                    found = node.data;
                }
            });
        }
        return found;
    }

    function initEditModal() {
        var modal = document.getElementById('vq-edit-modal');
        if (!modal) return;
        editModalCtrl = window.ModalUtils
            ? window.ModalUtils.makeModal(modal, { closeSelector: '.close-modal' })
            : {
                openModal: function () { modal.classList.remove('hidden'); },
                closeModal: function () { modal.classList.add('hidden'); },
            };
    }

    function initFollowUpModal() {
        var modal = document.getElementById('vq-follow-up-modal');
        if (!modal) return;
        followUpModalCtrl = window.ModalUtils
            ? window.ModalUtils.makeModal(modal, { closeSelector: '.close-modal' })
            : {
                openModal: function () { modal.classList.remove('hidden'); },
                closeModal: function () { modal.classList.add('hidden'); },
            };
    }

    function openFollowUpModal(row) {
        if (!row || !followUpModalCtrl) return;
        var idEl = document.getElementById('vq-follow-up-parent-id');
        var metaEl = document.getElementById('vq-follow-up-meta');
        var parentQuestionEl = document.getElementById('vq-follow-up-parent-question');
        var parentAnswerEl = document.getElementById('vq-follow-up-parent-answer');
        if (idEl) idEl.value = row.id;
        if (metaEl) {
            metaEl.textContent = [
                row.entity_name,
                row.template_name,
                row.period_name,
                row.rule_code,
            ].filter(Boolean).join(' · ');
        }
        if (parentQuestionEl) parentQuestionEl.textContent = row.question_text || '—';
        if (parentAnswerEl) parentAnswerEl.textContent = row.answer_text || '—';
        var questionEl = document.getElementById('vq-follow-up-question');
        var definitionEl = document.getElementById('vq-follow-up-definition');
        if (questionEl) questionEl.value = '';
        if (definitionEl) definitionEl.value = '';
        followUpModalCtrl.openModal();
        if (questionEl) questionEl.focus();
    }

    async function saveFollowUpQuestion() {
        var parentId = document.getElementById('vq-follow-up-parent-id')?.value;
        if (!parentId) return;
        var questionText = (document.getElementById('vq-follow-up-question')?.value || '').trim();
        var definitionText = document.getElementById('vq-follow-up-definition')?.value || '';
        if (!questionText) {
            showFeedback(t.questionRequired || 'Question text is required', 'error');
            return;
        }

        var saveBtn = document.getElementById('vq-follow-up-save');
        if (saveBtn) saveBtn.disabled = true;
        try {
            var url = (config.followUpUrlTemplate || '').replace('{id}', parentId);
            var resp = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, Accept: 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({
                    question_text: questionText,
                    definition_text: definitionText,
                }),
            });
            var data = await resp.json();
            if (!resp.ok) throw new Error(data.error || t.followUpFailed || 'Follow-up failed');
            followUpModalCtrl.closeModal();
            showFeedback(t.followUpCreated || 'Follow-up question created.', 'success');
            await loadRows();
        } catch (err) {
            showFeedback(err.message, 'error');
        } finally {
            if (saveBtn) saveBtn.disabled = false;
        }
    }

    function openEditModal(row) {
        if (!row || !editModalCtrl) return;
        editingRow = row;
        var metaEl = document.getElementById('vq-edit-meta');
        var idEl = document.getElementById('vq-edit-id');
        if (idEl) idEl.value = row.id;
        if (metaEl) {
            metaEl.textContent = [
                row.entity_name,
                row.template_name,
                row.period_name,
                row.rule_code,
            ].filter(Boolean).join(' · ');
        }
        var questionEl = document.getElementById('vq-edit-question');
        var definitionEl = document.getElementById('vq-edit-definition');
        var statusEl = document.getElementById('vq-edit-status');
        var severityEl = document.getElementById('vq-edit-severity');
        var answerEl = document.getElementById('vq-edit-answer');
        var outcomeEl = document.getElementById('vq-edit-outcome');
        if (questionEl) questionEl.value = row.question_text || '';
        if (definitionEl) definitionEl.value = row.definition_text || '';
        if (statusEl) statusEl.value = row.status || 'open';
        if (severityEl) severityEl.value = row.severity || 'warning';
        if (answerEl) answerEl.value = row.answer_text || '';
        if (outcomeEl) outcomeEl.value = row.answer_outcome || '';
        editModalCtrl.openModal();
        if (questionEl) questionEl.focus();
    }

    async function saveEditedQuestion() {
        var id = document.getElementById('vq-edit-id')?.value;
        if (!id) return;
        var questionText = (document.getElementById('vq-edit-question')?.value || '').trim();
        var definitionText = document.getElementById('vq-edit-definition')?.value || '';
        var status = document.getElementById('vq-edit-status')?.value || '';
        var severity = document.getElementById('vq-edit-severity')?.value || '';
        var answerText = document.getElementById('vq-edit-answer')?.value || '';
        var answerOutcome = document.getElementById('vq-edit-outcome')?.value || '';

        if (!questionText) {
            showFeedback(t.questionRequired || 'Question text is required', 'error');
            return;
        }
        if (status === 'answered' && !answerText.trim()) {
            showFeedback(t.answerRequired || 'Answer is required when status is Answered', 'error');
            return;
        }

        var saveBtn = document.getElementById('vq-edit-save');
        if (saveBtn) saveBtn.disabled = true;

        try {
            var url = (config.updateUrlTemplate || '').replace('{id}', id);
            var resp = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, Accept: 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({
                    question_text: questionText,
                    definition_text: definitionText,
                    status: status,
                    severity: severity,
                    answer_text: answerText,
                    answer_outcome: answerOutcome || null,
                }),
            });
            var data = await resp.json();
            if (!resp.ok) throw new Error(data.error || t.saveFailed || 'Save failed');
            editModalCtrl.closeModal();
            editingRow = null;
            showFeedback(t.questionSaved || 'Question saved', 'success');
            await loadRows();
        } catch (err) {
            showFeedback(err.message, 'error');
        } finally {
            if (saveBtn) saveBtn.disabled = false;
        }
    }

    function initQuestionsGrid(rows) {
        var columnDefs = buildColumnDefs();
        var questionColDef = columnDefs.find(function (c) { return c.field === 'question_text'; });
        vqLog('initQuestionsGrid', {
            rowCount: (rows || []).length,
            questionColDef: questionColDef,
            listUrl: config.listUrl,
        });

        var result = AgGridHelper.create(
            'validationQuestionsGrid',
            'admin-validation-questions',
            columnDefs,
            rows,
            {
                sizeColumnsToFitOnInit: false,
                sizeColumnsToFitOnRefresh: false,
                sizeColumnsToFitOnColumnChange: false,
                gridOptions: {
                    pagination: true,
                    paginationPageSize: 50,
                    paginationPageSizeSelector: [25, 50, 100, 200],
                    defaultColDef: {
                        autoHeight: false,
                        wrapText: false,
                        suppressSizeToFit: true,
                    },
                    onFirstDataRendered: function (params) {
                        vqLog('onFirstDataRendered fired');
                        AgGridHelper.enforceColumnMinWidths(params.api);
                        inspectQuestionColumnDebug(params.api, 'onFirstDataRendered');
                    },
                },
                columnVisibilityOptions: { buttonPlaceholderId: 'vq-col-vis-placeholder', enableExport: true, enableReset: true },
                onReady: function (api) {
                    gridApi = api;
                    vqLog('onReady fired');
                    AgGridHelper.pinActionsColumn(api, null, result.helper && result.helper.columnVisibilityManager);
                    inspectQuestionColumnDebug(api, 'onReady');
                },
            }
        );
        gridHelper = result.helper;
        gridApi = result.api;
    }

    function initSummaryGrid() {
        var result = AgGridHelper.create(
            'validationCountrySummaryGrid',
            'admin-validation-country-summary',
            buildSummaryColumnDefs(),
            [],
            {
                sizeColumnsToFitOnInit: false,
                sizeColumnsToFitOnRefresh: false,
                sizeColumnsToFitOnColumnChange: false,
                gridOptions: {
                    pagination: true,
                    paginationPageSize: 50,
                    defaultColDef: {
                        suppressSizeToFit: true,
                    },
                    onRowClicked: function (e) {
                        if (e.data && e.data.country_id != null) {
                            selectSummaryCountry(e.data.country_id);
                        }
                    },
                },
                columnVisibilityOptions: { buttonPlaceholderId: 'vqs-col-vis-placeholder', enableExport: true },
            }
        );
        summaryApi = result.api;
    }

    document.querySelectorAll('#vq-tabs [role="tab"]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            activateTab(btn.getAttribute('data-tab'));
        });
    });

    document.getElementById('vqs-template')?.addEventListener('change', function () {
        resetCountrySelect();
        loadSummaryPeriods();
    });
    document.getElementById('vqs-period')?.addEventListener('change', resetCountrySelect);
    document.getElementById('vqs-load')?.addEventListener('click', loadCountrySummary);
    document.getElementById('vqs-country')?.addEventListener('change', function () {
        setSendEnabled(!!document.getElementById('vqs-country')?.value);
    });
    document.getElementById('vqs-send')?.addEventListener('click', function () {
        if (!getSelectedSummaryCountry() || !window.confirm(t.sendConfirm || 'Send to focal points?')) return;
        sendOpenQuestions().catch(function (e) { showFeedback(e.message, 'error'); });
    });
    document.getElementById('vq-refresh')?.addEventListener('click', loadRows);
    document.getElementById('vq-export')?.addEventListener('click', function () {
        window.location.href = config.exportUrl;
    });
    document.getElementById('vq-import')?.addEventListener('click', function () {
        document.getElementById('vq-import-file')?.click();
    });
    document.getElementById('vq-import-file')?.addEventListener('change', async function (e) {
        var file = e.target.files && e.target.files[0];
        if (!file) return;
        var formData = new FormData();
        formData.append('excel_file', file);
        formData.append('csrf_token', csrf);
        try {
            var resp = await fetch(config.importUrl, { method: 'POST', body: formData, credentials: 'same-origin', headers: { Accept: 'application/json' } });
            var data = await resp.json();
            if (!resp.ok) throw new Error(data.error || t.importFailed);
            showFeedback('Import complete — updated: ' + (data.updated || 0), data.has_errors ? 'error' : 'success');
            await loadRows();
        } catch (err) {
            showFeedback(t.importFailed || 'Import failed', 'error');
        } finally {
            e.target.value = '';
        }
    });

    document.getElementById('vq-edit-save')?.addEventListener('click', function () {
        saveEditedQuestion();
    });

    document.getElementById('vq-follow-up-save')?.addEventListener('click', function () {
        saveFollowUpQuestion();
    });

    document.addEventListener('click', function (e) {
        var edit = e.target.closest('.vq-edit');
        var followUp = e.target.closest('.vq-follow-up');
        var waive = e.target.closest('.vq-waive');
        var reopen = e.target.closest('.vq-reopen');
        if (edit) {
            var row = findRowById(edit.dataset.id);
            if (row) openEditModal(row);
        }
        if (followUp) {
            var followRow = findRowById(followUp.dataset.id);
            if (followRow) openFollowUpModal(followRow);
        }
        if (waive) {
            updateStatus(waive.dataset.id, 'waived').catch(function (err) { showFeedback(err.message, 'error'); });
        }
        if (reopen) {
            updateStatus(reopen.dataset.id, 'open').catch(function (err) { showFeedback(err.message, 'error'); });
        }
    });

    initEditModal();
    initFollowUpModal();
    initSummaryGrid();
    vqLog('script loaded', { listUrl: config.listUrl });
    loadRows().then(initQuestionsGrid);
})();
