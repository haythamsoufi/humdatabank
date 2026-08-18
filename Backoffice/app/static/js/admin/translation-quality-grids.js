/**
 * AG Grid for approved glossary terms and candidate inbox.
 */
(function () {
    'use strict';

    var cfg = window.translationQualityGridConfig || {};
    var t = window.TRANSLATION_QUALITY_GRID_TRANSLATIONS || cfg.translations || {};
    var languageNames = cfg.languageNames || {};
    var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
    var termsLoaded = false;
    var inboxLoaded = false;

    function esc(value) {
        if (window.esc) return window.esc(value);
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function langLabel(code) {
        return languageNames[code] || String(code || '').toUpperCase();
    }

    function jsonFetch(url, options) {
        options = options || {};
        var headers = Object.assign({
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': csrf
        }, options.headers || {});
        if (options.body && !headers['Content-Type']) {
            headers['Content-Type'] = 'application/json';
        }
        return fetch(url, Object.assign({ credentials: 'same-origin' }, options, { headers: headers }))
            .then(function (res) {
                return res.json().then(function (data) {
                    if (!res.ok || (data && data.success === false)) {
                        throw new Error((data && data.message) || t.saveFailed || 'Request failed');
                    }
                    return data || {};
                });
            });
    }

    function countRows(api, pred) {
        var n = 0;
        if (!api || typeof api.forEachNode !== 'function') return 0;
        api.forEachNode(function (node) {
            if (node.data && (!pred || pred(node.data))) n += 1;
        });
        return n;
    }

    function setCount(el, value) {
        if (el) el.textContent = String(Math.max(0, value));
    }

    function resizeApi(api) {
        if (!api) return;
        if (typeof api.sizeColumnsToFit === 'function') api.sizeColumnsToFit();
        if (typeof api.resetRowHeights === 'function') api.resetRowHeights();
    }

    function updateTermCounts(activeCount) {
        setCount(document.getElementById('glossary-terms-kpi'), activeCount);
        setCount(document.getElementById('glossary-tab-badge'), activeCount);
    }

    function updateInboxCounts(pendingCount) {
        setCount(document.getElementById('glossary-pending-kpi'), pendingCount);
        setCount(document.getElementById('inbox-tab-badge'), pendingCount);
        var pendingEl = document.querySelector('#glossary-inbox-summary [data-role="pending-count"]');
        if (pendingEl) {
            pendingEl.textContent = pendingCount === 1
                ? (t.pendingOne || '1 pending')
                : (t.pendingMany || '{count} pending').replace('{count}', String(pendingCount));
        }
    }

    var termsApi = null;
    var termsHelper = null;
    var inboxApi = null;
    var inboxHelper = null;

    function setGridRows(api, helper, items) {
        if (helper && typeof helper.setRowData === 'function') {
            helper.setRowData(items);
            return;
        }
        if (api && typeof api.setGridOption === 'function') {
            api.setGridOption('rowData', items);
        }
    }
    var saving = {};
    var bulkBusy = false;

    function selectedRows(api) {
        if (!api || typeof api.getSelectedRows !== 'function') return [];
        return api.getSelectedRows() || [];
    }

    function selectedLabel(count) {
        if (count === 1) return t.selectedOne || '1 selected';
        return (t.selectedMany || '{count} selected').replace('{count}', String(count));
    }

    function syncBulkBar(barId, api) {
        var bar = document.getElementById(barId);
        if (!bar) return;
        var rows = selectedRows(api);
        var count = rows.length;
        var countEl = bar.querySelector('[data-role="selected-count"]');
        if (countEl) countEl.textContent = selectedLabel(count);
        if (count > 0) {
            bar.classList.remove('hidden');
            bar.classList.add('flex');
        } else {
            bar.classList.add('hidden');
            bar.classList.remove('flex');
        }
    }

    function setBulkBusy(barId, busy) {
        bulkBusy = busy;
        var bar = document.getElementById(barId);
        if (!bar) return;
        bar.querySelectorAll('button[data-bulk]').forEach(function (btn) {
            btn.disabled = busy;
        });
    }

    function loadTerms() {
        var url = cfg.termsUrl + (cfg.termsUrl.indexOf('?') === -1 ? '?' : '&') + 'include_inactive=1';
        return jsonFetch(url).then(function (data) {
            var items = (data && data.items) || [];
            termsLoaded = true;
            setGridRows(termsApi, termsHelper, items);
            updateTermCounts(items.filter(function (row) { return row.is_active; }).length);
            return items;
        }).catch(function (err) {
            if (window.showAlert) window.showAlert(err.message || t.saveFailed, 'error');
        });
    }

    function loadInbox() {
        return jsonFetch(cfg.candidatesUrl).then(function (data) {
            var items = (data && data.items) || [];
            inboxLoaded = true;
            setGridRows(inboxApi, inboxHelper, items);
            updateInboxCounts((data && data.total) || items.length);
            return items;
        }).catch(function (err) {
            if (window.showAlert) window.showAlert(err.message || t.decideFailed, 'error');
        });
    }

    function saveTerm(row, payload) {
        if (!row || !row.id) return Promise.resolve();
        var key = 'term-' + row.id;
        if (saving[key]) return saving[key];
        saving[key] = jsonFetch(cfg.termUpdateUrl.replace('999999', String(row.id)), {
            method: 'POST',
            body: JSON.stringify(payload)
        }).then(function (data) {
            if (!data || !data.success || !data.term) {
                throw new Error((data && data.message) || t.saveFailed);
            }
            Object.assign(row, data.term);
            if (termsApi) {
                termsApi.applyTransaction({ update: [row] });
            }
            updateTermCounts(countRows(termsApi, function (item) { return item.is_active; }));
            return data.term;
        }).finally(function () {
            delete saving[key];
        });
        return saving[key];
    }

    function decideCandidate(row, accept) {
        if (!row || !row.id) return Promise.resolve();
        if (accept && (!String(row.source_term || '').trim() || !String(row.target_term || '').trim())) {
            if (window.showAlert) window.showAlert(t.emptyTerm || 'Enter both the source term and the translation.', 'error');
            return Promise.resolve();
        }
        return jsonFetch(cfg.candidateDecideUrl.replace('999999', String(row.id)), {
            method: 'POST',
            body: JSON.stringify({
                accept: accept,
                source_term: row.source_term,
                target_term: row.target_term,
                tier: row.proposed_tier
            })
        }).then(function (data) {
            if (!data || !data.success) {
                throw new Error((data && data.message) || t.decideFailed);
            }
            if (inboxApi) inboxApi.applyTransaction({ remove: [row] });
            updateInboxCounts(countRows(inboxApi));
            if (accept && termsApi) loadTerms();
        });
    }

    function termsColumns() {
        return [
            {
                field: 'source_term',
                headerName: t.source || 'Source',
                flex: 1.4,
                minWidth: 180,
                filter: 'agTextColumnFilter',
                editable: true,
                tooltipField: 'source_term'
            },
            {
                field: 'target_term',
                headerName: t.translation || 'Translation',
                flex: 1.4,
                minWidth: 180,
                filter: 'agTextColumnFilter',
                editable: true,
                tooltipField: 'target_term'
            },
            {
                field: 'target_lang',
                headerName: t.language || 'Language',
                width: 140,
                minWidth: 110,
                filter: 'customSetFilter',
                valueFormatter: function (params) {
                    return langLabel(params.value);
                }
            },
            {
                field: 'tier',
                headerName: t.tier || 'Tier',
                width: 130,
                minWidth: 110,
                filter: 'customSetFilter',
                editable: true,
                cellEditor: 'agSelectCellEditor',
                cellEditorParams: { values: ['must', 'preferred'] },
                valueFormatter: function (params) {
                    return params.value === 'must' ? (t.must || 'Must') : (t.preferred || 'Preferred');
                }
            },
            {
                field: 'origin',
                headerName: t.origin || 'Origin',
                width: 140,
                minWidth: 100,
                filter: 'customSetFilter'
            },
            {
                field: 'is_active',
                headerName: t.status || 'Status',
                width: 110,
                minWidth: 90,
                filter: 'customSetFilter',
                valueFormatter: function (params) {
                    return params.value ? (t.active || 'Active') : (t.inactive || 'Inactive');
                }
            },
            {
                colId: 'actions',
                headerName: t.actions || 'Actions',
                width: 130,
                minWidth: 120,
                maxWidth: 160,
                pinned: 'right',
                sortable: false,
                filter: false,
                cellRenderer: function (params) {
                    var row = params.data || {};
                    var label = row.is_active ? (t.deactivate || 'Deactivate') : (t.activate || 'Activate');
                    var klass = row.is_active ? 'btn-danger' : 'btn-success';
                    return '<button type="button" class="btn btn-sm ' + klass + ' glossary-term-active" data-action="toggle-active">' +
                        esc(label) + '</button>';
                }
            }
        ];
    }

    function inboxColumns() {
        return [
            {
                field: 'source_term',
                headerName: t.source || 'Source',
                flex: 1.3,
                minWidth: 160,
                filter: 'agTextColumnFilter',
                editable: true,
                tooltipField: 'source_term'
            },
            {
                field: 'target_term',
                headerName: t.translation || 'Translation',
                flex: 1.3,
                minWidth: 160,
                filter: 'agTextColumnFilter',
                editable: true,
                tooltipField: 'target_term'
            },
            {
                field: 'target_lang',
                headerName: t.language || 'Language',
                width: 130,
                minWidth: 110,
                filter: 'customSetFilter',
                valueFormatter: function (params) {
                    return langLabel(params.value);
                }
            },
            {
                field: 'proposed_tier',
                headerName: t.tier || 'Tier',
                width: 120,
                minWidth: 100,
                filter: 'customSetFilter',
                editable: true,
                cellEditor: 'agSelectCellEditor',
                cellEditorParams: { values: ['must', 'preferred'] },
                valueFormatter: function (params) {
                    return params.value === 'must' ? (t.must || 'Must') : (t.preferred || 'Preferred');
                }
            },
            {
                field: 'conflict',
                headerName: t.conflict || 'Conflict',
                width: 160,
                minWidth: 130,
                filter: 'customSetFilter',
                cellRenderer: function (params) {
                    var row = params.data || {};
                    if (!row.conflict) return '';
                    var official = row.official_term ? esc(row.official_term) : '';
                    return '<span class="text-amber-800">' + esc(t.conflict || 'Conflict') +
                        (official ? ': ' + official : '') + '</span>' +
                        (official ? ' <button type="button" class="underline text-xs glossary-use-official" data-action="use-official">' +
                            esc(t.useApproved || 'Use approved') + '</button>' : '');
                }
            },
            {
                field: 'extractor',
                headerName: t.extractor || 'Extractor',
                width: 130,
                minWidth: 100,
                filter: 'customSetFilter'
            },
            {
                field: 'confidence',
                headerName: t.confidence || 'Confidence',
                width: 120,
                minWidth: 100,
                filter: 'agNumberColumnFilter',
                valueFormatter: function (params) {
                    return Math.round((params.value || 0) * 100) + '%';
                }
            },
            {
                colId: 'actions',
                headerName: t.actions || 'Actions',
                width: 180,
                minWidth: 170,
                maxWidth: 200,
                pinned: 'right',
                sortable: false,
                filter: false,
                cellRenderer: function () {
                    return '<button type="button" class="btn btn-success btn-sm" data-action="accept">' + esc(t.accept || 'Accept') +
                        '</button> <button type="button" class="btn btn-danger btn-sm" data-action="reject">' +
                        esc(t.reject || 'Reject') + '</button>';
                }
            }
        ];
    }

    function initTermsGrid() {
        if (!window.AgGridHelper || !document.getElementById('glossaryTermsGrid')) return;
        AgGridHelper.createTabAware('glossaryTermsGrid', 'translation-quality-glossary', termsColumns(), [], {
            emptyMessage: t.noTerms || 'No approved glossary terms yet.',
            onReady: function (api, helper) {
                termsApi = api;
                termsHelper = helper || termsHelper;
                if (!termsLoaded) loadTerms();
            },
            gridOptions: {
                pagination: true,
                paginationPageSize: 50,
                stopEditingWhenCellsLoseFocus: true,
                getRowId: function (params) { return String(params.data.id); },
                onSelectionChanged: function () {
                    syncBulkBar('glossary-terms-bulk', termsApi);
                },
                onCellValueChanged: function (ev) {
                    if (!ev.data || ev.colDef.field === 'is_active') return;
                    saveTerm(ev.data, {
                        source_term: ev.data.source_term,
                        target_term: ev.data.target_term,
                        tier: ev.data.tier
                    }).catch(function (err) {
                        if (window.showAlert) window.showAlert(err.message || t.saveFailed, 'error');
                        loadTerms();
                    });
                },
                onCellClicked: function (ev) {
                    var btn = ev.event && ev.event.target && ev.event.target.closest('[data-action="toggle-active"]');
                    if (!btn || !ev.data) return;
                    saveTerm(ev.data, { is_active: !ev.data.is_active }).catch(function (err) {
                        if (window.showAlert) window.showAlert(err.message || t.saveFailed, 'error');
                    });
                }
            }
        }, {
            eventName: 'quality-tab-activated',
            tabId: 'glossary',
            deferUntilVisible: true,
            onTabActivated: function (api, helper) {
                termsApi = api;
                termsHelper = helper || termsHelper;
                if (!termsLoaded) loadTerms();
                resizeApi(api);
            }
        });
    }

    function initInboxGrid() {
        if (!window.AgGridHelper || !document.getElementById('glossaryInboxGrid')) return;
        AgGridHelper.createTabAware('glossaryInboxGrid', 'translation-quality-inbox', inboxColumns(), [], {
            emptyMessage: t.noCandidates || 'No pending candidates.',
            onReady: function (api, helper) {
                inboxApi = api;
                inboxHelper = helper || inboxHelper;
                if (!inboxLoaded) loadInbox();
            },
            gridOptions: {
                pagination: true,
                paginationPageSize: 50,
                stopEditingWhenCellsLoseFocus: true,
                getRowId: function (params) { return String(params.data.id); },
                onSelectionChanged: function () {
                    syncBulkBar('glossary-inbox-bulk', inboxApi);
                },
                onCellClicked: function (ev) {
                    var target = ev.event && ev.event.target;
                    var btn = target && target.closest('[data-action]');
                    if (!btn || !ev.data) return;
                    var action = btn.getAttribute('data-action');
                    if (action === 'use-official' && ev.data.official_term) {
                        ev.data.target_term = ev.data.official_term;
                        inboxApi.applyTransaction({ update: [ev.data] });
                        return;
                    }
                    if (action === 'accept' || action === 'reject') {
                        decideCandidate(ev.data, action === 'accept').catch(function (err) {
                            if (window.showAlert) window.showAlert(err.message || t.decideFailed, 'error');
                        });
                    }
                }
            }
        }, {
            eventName: 'quality-tab-activated',
            tabId: 'inbox',
            deferUntilVisible: true,
            onTabActivated: function (api, helper) {
                inboxApi = api;
                inboxHelper = helper || inboxHelper;
                if (!inboxLoaded) loadInbox();
                resizeApi(api);
            }
        });
    }

    function bindAddForm() {
        var form = document.getElementById('glossary-add-form');
        var modal = document.getElementById('glossaryAddTermModal');
        var openBtn = document.getElementById('glossary-add-open');
        var modalCtrl = window.ModalUtils
            ? window.ModalUtils.makeModal(modal, {
                closeSelector: '.close-modal, .close-modal-btn',
                onOpen: function () {
                    var source = document.getElementById('glossary-add-source');
                    if (source) setTimeout(function () { source.focus(); }, 0);
                },
                onClose: function () {
                    var errorEl = document.getElementById('glossary-add-error');
                    if (errorEl) {
                        errorEl.classList.add('hidden');
                        errorEl.textContent = '';
                    }
                }
            })
            : {
                openModal: function () { if (modal) modal.classList.remove('hidden'); },
                closeModal: function () { if (modal) modal.classList.add('hidden'); }
            };
        if (openBtn) {
            openBtn.addEventListener('click', function () {
                modalCtrl.openModal();
            });
        }
        if (!form) return;
        form.addEventListener('submit', function (ev) {
            ev.preventDefault();
            var source = (document.getElementById('glossary-add-source') || {}).value || '';
            var target = (document.getElementById('glossary-add-target') || {}).value || '';
            var lang = (document.getElementById('glossary-add-lang') || {}).value || '';
            var tier = (document.getElementById('glossary-add-tier') || {}).value || 'must';
            var errorEl = document.getElementById('glossary-add-error');
            if (errorEl) {
                errorEl.classList.add('hidden');
                errorEl.textContent = '';
            }
            if (!source.trim() || !target.trim()) {
                if (errorEl) {
                    errorEl.textContent = t.emptyTerm || 'Enter both the English source and the translation.';
                    errorEl.classList.remove('hidden');
                }
                return;
            }
            var submit = form.querySelector('button[type="submit"]');
            if (submit) submit.disabled = true;
            jsonFetch(cfg.termCreateUrl, {
                method: 'POST',
                body: JSON.stringify({
                    source_term: source,
                    target_term: target,
                    target_lang: lang,
                    tier: tier
                })
            }).then(function (data) {
                if (!data || !data.success || !data.term) {
                    throw new Error((data && data.message) || t.saveFailed);
                }
                if (termsApi) {
                    termsApi.applyTransaction({ add: [data.term] });
                    updateTermCounts(countRows(termsApi, function (item) { return item.is_active; }));
                } else {
                    loadTerms();
                }
                form.reset();
                modalCtrl.closeModal();
            }).catch(function (err) {
                if (errorEl) {
                    errorEl.textContent = err.message || t.saveFailed;
                    errorEl.classList.remove('hidden');
                }
            }).finally(function () {
                if (submit) submit.disabled = false;
            });
        });
    }

    function bindBulkActions() {
        var termsBar = document.getElementById('glossary-terms-bulk');
        if (termsBar) {
            termsBar.addEventListener('click', function (ev) {
                var btn = ev.target && ev.target.closest('[data-bulk]');
                if (!btn || bulkBusy) return;
                var rows = selectedRows(termsApi);
                var ids = rows.map(function (row) { return row && row.id; }).filter(Boolean);
                if (!ids.length) return;
                var action = btn.getAttribute('data-bulk');
                var payload = { ids: ids };
                if (action === 'activate') payload.is_active = true;
                else if (action === 'deactivate') payload.is_active = false;
                else if (action === 'tier-must') payload.tier = 'must';
                else if (action === 'tier-preferred') payload.tier = 'preferred';
                else return;
                setBulkBusy('glossary-terms-bulk', true);
                jsonFetch(cfg.termBulkUrl, {
                    method: 'POST',
                    body: JSON.stringify(payload)
                }).then(function (data) {
                    var items = (data && data.items) || [];
                    if (termsApi && items.length) {
                        termsApi.applyTransaction({ update: items });
                        if (typeof termsApi.deselectAll === 'function') termsApi.deselectAll();
                    }
                    updateTermCounts(countRows(termsApi, function (item) { return item.is_active; }));
                    syncBulkBar('glossary-terms-bulk', termsApi);
                }).catch(function (err) {
                    if (window.showAlert) window.showAlert(err.message || t.bulkFailed, 'error');
                }).finally(function () {
                    setBulkBusy('glossary-terms-bulk', false);
                });
            });
        }

        var inboxBar = document.getElementById('glossary-inbox-bulk');
        if (inboxBar) {
            inboxBar.addEventListener('click', function (ev) {
                var btn = ev.target && ev.target.closest('[data-bulk]');
                if (!btn || bulkBusy) return;
                var rows = selectedRows(inboxApi);
                if (!rows.length) return;
                var accept = btn.getAttribute('data-bulk') === 'accept';
                if (btn.getAttribute('data-bulk') !== 'accept' && btn.getAttribute('data-bulk') !== 'reject') return;
                var items = rows.map(function (row) {
                    return {
                        id: row.id,
                        source_term: row.source_term,
                        target_term: row.target_term,
                        tier: row.proposed_tier
                    };
                });
                setBulkBusy('glossary-inbox-bulk', true);
                jsonFetch(cfg.candidateBulkUrl, {
                    method: 'POST',
                    body: JSON.stringify({ accept: accept, items: items })
                }).then(function () {
                    if (inboxApi) {
                        inboxApi.applyTransaction({ remove: rows });
                        if (typeof inboxApi.deselectAll === 'function') inboxApi.deselectAll();
                    }
                    updateInboxCounts(countRows(inboxApi));
                    syncBulkBar('glossary-inbox-bulk', inboxApi);
                    if (accept && termsApi) loadTerms();
                }).catch(function (err) {
                    if (window.showAlert) window.showAlert(err.message || t.bulkFailed, 'error');
                }).finally(function () {
                    setBulkBusy('glossary-inbox-bulk', false);
                });
            });
        }
    }

    initTermsGrid();
    initInboxGrid();
    bindAddForm();
    bindBulkActions();
})();
