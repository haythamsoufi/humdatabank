(function() {
    const cfg = window.PBProgressConfig || {};
    const API_BASE = cfg.apiBase || '/admin/data-exploration/pb-progress';
    const EXPLORE_REPORT_URL = cfg.exploreReportUrl || '/admin/data-exploration?tab=pb-progress';
    const VERSIONS = cfg.versions || {};
    const VERSION_ORDER = cfg.versionOrder || [];
    let activeVersion = cfg.defaultVersion || "";
    let pollTimer = null;
    let uploadInProgress = false;
    let activeSubtab = cfg.initialSubtab || 'build';
    const versionUi = {};

    function apiUrl(path, versionId) {
        const version = versionId || activeVersion;
        return API_BASE + '/' + encodeURIComponent(version) + path;
    }

    function initVersionUi() {
        VERSION_ORDER.forEach(function(versionId) {
            versionUi[versionId] = {
                hasExcel: false,
                maxProgressPercent: 15,
                trackingBuild: false,
                cancellingBuild: false,
                statusCache: null,
            };
        });
    }
    initVersionUi();

    const els = {
        build: document.getElementById('pb-progress-build'),
        buildActive: document.getElementById('pb-progress-build-active'),
        buildMessage: document.getElementById('pb-progress-build-message'),
        versionTabs: document.getElementById('pb-progress-version-tabs'),
        subtabs: document.getElementById('pb-progress-subtabs'),
        panelBuild: document.getElementById('pb-progress-panel-build'),
        panelMapping: document.getElementById('pb-progress-panel-mapping'),
        panelTranslations: document.getElementById('pb-progress-panel-translations'),
        panelSectionOrder: document.getElementById('pb-progress-panel-section-order'),
        excelWorkflow: document.getElementById('pb-progress-excel-workflow'),
        systemWorkflow: document.getElementById('pb-progress-system-workflow'),
        systemDatasetBadge: document.getElementById('pb-progress-system-dataset-badge'),
        compareSummary: document.getElementById('pb-progress-compare-summary'),
        mappingFilter: document.getElementById('pb-progress-mapping-filter'),
        mappingCount: document.getElementById('pb-progress-mapping-count'),
        badge: document.getElementById('pb-progress-excel-badge'),
        badgeText: document.getElementById('pb-progress-excel-badge-text'),
        noExcelNotice: document.getElementById('pb-progress-no-excel-notice'),
        fileInput: document.getElementById('pb-progress-file-input'),
        downloadWorkbookLink: document.getElementById('pb-progress-download-workbook-link'),
        uploadBtn: document.getElementById('pb-progress-upload-btn'),
        generateBtn: document.getElementById('pb-progress-generate-btn'),
        generateHint: document.getElementById('pb-progress-generate-hint'),
        languageSelect: document.getElementById('pb-progress-language'),
        headerViewLink: document.getElementById('pb-progress-header-view-link'),
        progressText: document.getElementById('pb-progress-progress-text'),
        progressBar: document.getElementById('pb-progress-progress-bar'),
        stages: document.getElementById('pb-progress-stages'),
        stagesToggle: document.getElementById('pb-progress-stages-toggle'),
        cancelBtn: document.getElementById('pb-progress-cancel-btn'),
        sourceExcelBtn: document.getElementById('pb-progress-source-excel'),
        sourceSystemBtn: document.getElementById('pb-progress-source-system'),
        mappingBody: document.getElementById('pb-progress-mapping-body'),
        translationsBody: document.getElementById('pb-progress-translations-body'),
        sectionOrderBody: document.getElementById('pb-progress-section-order-body'),
        syncMappingBtn: document.getElementById('pb-progress-sync-mapping-btn'),
        importConfigBtn: document.getElementById('pb-progress-import-config-btn'),
        saveMappingBtn: document.getElementById('pb-progress-save-mapping-btn'),
        saveTranslationsBtn: document.getElementById('pb-progress-save-translations-btn'),
        saveSectionOrderBtn: document.getElementById('pb-progress-save-section-order-btn'),
        generateSystemBtn: document.getElementById('pb-progress-generate-system-btn'),
        compareSystemBtn: document.getElementById('pb-progress-compare-system-btn'),
        downloadSystemLink: document.getElementById('pb-progress-download-system-link'),
        yearsMultiselectHost: document.getElementById('pb-progress-years-multiselect'),
    };

    const SUBTAB_PANELS = {
        build: els.panelBuild,
        mapping: els.panelMapping,
        translations: els.panelTranslations,
        'section-order': els.panelSectionOrder,
    };
    const SYSTEM_ONLY_SUBTABS = ['mapping', 'translations', 'section-order'];

    let mappingRows = [];
    let mappingFilterText = '';
    let translationRows = [];
    let sectionOrderRows = [];
    let activeDataSource = cfg.initialDataSource || 'excel';
    let yearsMultiselect = null;
    let yearsSaveTimer = null;
    let yearsSelectionSaved = [];
    let stagesExpanded = false;
    let wasBuildRunning = false;

    function currentStageLabel(stageList, status) {
        if (status && status.build_stage_label) return status.build_stage_label;
        if (!stageList || !stageList.length) {
            return (cfg.i18n && cfg.i18n.generatingReport) || 'Generating report...';
        }
        let active = null;
        stageList.forEach(function(stage) {
            if (stage.state === 'active') active = stage;
        });
        if (active && active.label) return active.label;
        return (cfg.i18n && cfg.i18n.generatingReport) || 'Generating report...';
    }

    function updateStagesToggle(expanded, visible) {
        if (!els.stagesToggle) return;
        els.stagesToggle.classList.toggle('hidden', !visible);
        els.stagesToggle.textContent = expanded
            ? ((cfg.i18n && cfg.i18n.hideBuildSteps) || 'Hide steps')
            : ((cfg.i18n && cfg.i18n.showBuildSteps) || 'Show steps');
        els.stagesToggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    }

    function renderBuildStages(stageList, status) {
        if (!els.stages) return;
        const list = stageList || [];
        const running = status && status.status === 'running';
        if (!running || !list.length) {
            els.stages.classList.add('hidden');
            els.stages.innerHTML = '';
            updateStagesToggle(false, false);
            return;
        }
        updateStagesToggle(stagesExpanded, true);
        if (!stagesExpanded) {
            els.stages.classList.add('hidden');
            els.stages.innerHTML = '';
            return;
        }
        els.stages.classList.remove('hidden');
        els.stages.innerHTML = '';
        list.forEach(function(stage) {
            const item = document.createElement('li');
            item.className = 'flex items-center gap-2';
            let iconClass = 'far fa-circle text-gray-400';
            let textClass = 'text-gray-500';
            if (stage.state === 'done') {
                iconClass = 'fas fa-check-circle text-green-600';
                textClass = 'text-gray-700';
            } else if (stage.state === 'active') {
                iconClass = 'fas fa-spinner fa-spin text-blue-600';
                textClass = 'text-blue-800 font-medium';
            }
            item.innerHTML = '<i class="' + iconClass + '" aria-hidden="true"></i><span class="' + textClass + '">' + stage.label + '</span>';
            els.stages.appendChild(item);
        });
    }

    function currentUi() {
        return versionUi[activeVersion];
    }

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function exploreUrlForVersion(versionId) {
        try {
            const url = new URL(EXPLORE_REPORT_URL, window.location.origin);
            url.searchParams.set('tab', 'pb-progress');
            if (versionId) url.searchParams.set('pb_version', versionId);
            return url.pathname + url.search;
        } catch (e) {
            const join = EXPLORE_REPORT_URL.indexOf('?') >= 0 ? '&' : '?';
            return EXPLORE_REPORT_URL + join + 'pb_version=' + encodeURIComponent(versionId || '');
        }
    }

    function updateExploreLinks() {
        const href = exploreUrlForVersion(activeVersion);
        if (els.headerViewLink) els.headerViewLink.href = href;
    }

    function updateGenerateHint(status) {
        if (!els.generateHint) return;
        const cached = status || currentUi().statusCache || {};
        if (canGenerateReport(cached) || cached.status === 'running') {
            els.generateHint.textContent = '';
            return;
        }
        els.generateHint.textContent = isSystemMode()
            ? ((cfg.i18n && cfg.i18n.generateHintSystem) || '')
            : ((cfg.i18n && cfg.i18n.generateHintExcel) || '');
    }

    function isSystemOnlySubtab(subtabId) {
        return SYSTEM_ONLY_SUBTABS.indexOf(subtabId) !== -1;
    }

    function hasReferenceWorkbook(status) {
        return !!(status && status.excel);
    }

    function updateModeScopedElements() {
        const showSystem = isSystemMode();
        const showExcel = isExcelMode();
        document.querySelectorAll('[data-pb-system-only]').forEach(function(el) {
            el.classList.toggle('hidden', !showSystem);
        });
        document.querySelectorAll('[data-pb-excel-only]').forEach(function(el) {
            el.classList.toggle('hidden', !showExcel);
        });
        if (!showSystem && isSystemOnlySubtab(activeSubtab)) {
            setActiveSubtab('build');
        }
    }

    function clearSystemWorkflowState() {
        if (els.compareSummary) {
            els.compareSummary.innerHTML = '';
            els.compareSummary.classList.add('hidden');
        }
    }

    function setActiveSubtab(subtabId) {
        if (!SUBTAB_PANELS[subtabId]) return;
        if (!isSystemMode() && isSystemOnlySubtab(subtabId)) {
            subtabId = 'build';
        }
        activeSubtab = subtabId;
        if (els.subtabs) {
            els.subtabs.querySelectorAll('[data-pb-subtab]').forEach(function(btn) {
                const selected = btn.getAttribute('data-pb-subtab') === subtabId;
                btn.setAttribute('aria-selected', selected ? 'true' : 'false');
                if (window.AdminUnderlineTabs && typeof window.AdminUnderlineTabs.setStripButtonActive === 'function') {
                    window.AdminUnderlineTabs.setStripButtonActive(btn, selected);
                }
            });
        }
        Object.keys(SUBTAB_PANELS).forEach(function(key) {
            const panel = SUBTAB_PANELS[key];
            if (panel) panel.classList.toggle('is-active', key === subtabId);
        });
        if (subtabId === 'mapping') {
            loadMappingPanel().catch(handleAdminError);
        } else if (subtabId === 'translations') {
            loadTranslationsPanel().catch(handleAdminError);
        } else if (subtabId === 'section-order') {
            loadSectionOrderPanel().catch(handleAdminError);
        }
        if (subtabId === 'build') {
            refreshStatus().catch(function() {});
            if (isExcelMode()) {
                loadExcelInfo().catch(function() {});
            } else {
                loadYearsPanel().catch(function() {});
            }
        }
    }

    function setActiveVersionTab() {
        if (!els.versionTabs) return;
        els.versionTabs.querySelectorAll('[data-pb-version]').forEach(function(btn) {
            const selected = btn.getAttribute('data-pb-version') === activeVersion;
            btn.setAttribute('aria-selected', selected ? 'true' : 'false');
            btn.classList.toggle('border-blue-600', selected);
            btn.classList.toggle('text-blue-700', selected);
            btn.classList.toggle('border-transparent', !selected);
            btn.classList.toggle('text-gray-600', !selected);
        });
    }

    function setMessage(el, text, tone) {
        if (!el) return;
        el.textContent = text || '';
        el.classList.remove('hidden', 'text-red-600', 'text-green-700', 'text-gray-600');
        if (!text) {
            el.classList.add('hidden');
            return;
        }
        if (tone === 'error') el.classList.add('text-red-600');
        else if (tone === 'success') el.classList.add('text-green-700');
        else el.classList.add('text-gray-600');
    }

    function formatUploadedAt(value) {
        if (!value) return '';
        try {
            return new Date(value).toLocaleString();
        } catch (e) {
            return value;
        }
    }

    function stageProgressPercent(stageList) {
        if (!stageList || !stageList.length) return 15;
        let completed = 0;
        let hasActive = false;
        stageList.forEach(function(stage) {
            if (stage.state === 'done') completed += 1;
            if (stage.state === 'active') hasActive = true;
        });
        const total = stageList.length;
        const value = hasActive ? completed + 0.5 : completed;
        return Math.min(95, Math.max(15, Math.round((value / total) * 100)));
    }

    function isExcelMode() {
        return activeDataSource === 'excel';
    }

    function isSystemMode() {
        return activeDataSource === 'system';
    }

    function syncActiveDataSource(status) {
        if (status && (status.data_source === 'excel' || status.data_source === 'system')) {
            activeDataSource = status.data_source;
        }
    }

    function renderHeaderStatus(status) {
        if (els.systemDatasetBadge) {
            const ready = isSystemMode() && status && status.system_dataset_available;
            els.systemDatasetBadge.classList.toggle('hidden', !ready);
        }
    }

    function updateReferenceWorkbookActions(status) {
        const hasWorkbook = hasReferenceWorkbook(status);
        if (els.compareSystemBtn) {
            els.compareSystemBtn.classList.toggle('hidden', !isSystemMode() || !hasWorkbook);
        }
        if (els.importConfigBtn) {
            els.importConfigBtn.classList.toggle('hidden', !hasWorkbook);
        }
    }

    function renderExcelFileState(excel) {
        if (!isExcelMode()) return;
        const hasWorkbook = !!excel;
        if (!excel) {
            if (els.badge) els.badge.classList.add('hidden');
            if (els.noExcelNotice) els.noExcelNotice.classList.remove('hidden');
            if (els.downloadWorkbookLink) els.downloadWorkbookLink.classList.add('hidden');
            return;
        }
        const parts = [excel.filename || 'SG Report.xlsx'];
        if (excel.size_label) parts.push(excel.size_label);
        if (excel.uploaded_at) parts.push(formatUploadedAt(excel.uploaded_at));
        if (els.badgeText) els.badgeText.textContent = parts.join(' · ');
        if (els.badge) els.badge.classList.remove('hidden');
        if (els.noExcelNotice) els.noExcelNotice.classList.add('hidden');
        if (els.downloadWorkbookLink) {
            if (excel.download_url) {
                els.downloadWorkbookLink.href = excel.download_url;
                els.downloadWorkbookLink.classList.remove('hidden');
            } else {
                els.downloadWorkbookLink.classList.add('hidden');
            }
        }
    }

    function applyDataSourceMode(status, syncFromStatus) {
        if (syncFromStatus !== false) {
            syncActiveDataSource(status);
        }
        const isExcel = isExcelMode();
        const isSystem = isSystemMode();

        if (els.sourceExcelBtn) {
            els.sourceExcelBtn.classList.toggle('bg-blue-600', isExcel);
            els.sourceExcelBtn.classList.toggle('text-white', isExcel);
            els.sourceExcelBtn.classList.toggle('bg-white', !isExcel);
            els.sourceExcelBtn.classList.toggle('text-gray-700', !isExcel);
        }
        if (els.sourceSystemBtn) {
            els.sourceSystemBtn.classList.toggle('bg-blue-600', isSystem);
            els.sourceSystemBtn.classList.toggle('text-white', isSystem);
            els.sourceSystemBtn.classList.toggle('bg-white', !isSystem);
            els.sourceSystemBtn.classList.toggle('text-gray-700', !isSystem);
        }

        if (els.excelWorkflow) els.excelWorkflow.classList.toggle('hidden', !isExcel);
        if (els.systemWorkflow) els.systemWorkflow.classList.toggle('hidden', !isSystem);

        updateModeScopedElements();
        renderHeaderStatus(status || {});
        updateReferenceWorkbookActions(status || {});

        if (!isSystem) {
            clearSystemWorkflowState();
        }
        if (isSystem && activeSubtab === 'build') {
            loadYearsPanel().catch(function() {});
        }
        if (!isExcel && els.fileInput) {
            els.fileInput.value = '';
            setUploadBusy(false);
        }
    }

    function canGenerateReport(status) {
        if (isSystemMode()) {
            return !!(status && status.mapping_ready);
        }
        return !!(status && status.excel);
    }

    function mappingRowMatchesFilter(row, filterText) {
        if (!filterText) return true;
        const haystack = [
            row.id,
            row.section,
            row.source,
            row.label_override,
        ].join(' ').toLowerCase();
        return haystack.indexOf(filterText) !== -1;
    }

    function updateMappingCount(visibleCount) {
        if (!els.mappingCount) return;
        const total = mappingRows.length;
        const label = (cfg.i18n && cfg.i18n.indicatorsLabel) || 'indicators';
        const count = visibleCount != null ? visibleCount : total;
        els.mappingCount.textContent = count + ' ' + label + (visibleCount != null && visibleCount !== total ? ' (' + total + ' total)' : '');
    }

    function renderMappingTable(rows) {
        mappingRows = Array.isArray(rows) ? rows.slice() : [];
        if (!els.mappingBody) return;
        const filterText = (mappingFilterText || '').trim().toLowerCase();
        els.mappingBody.innerHTML = '';
        let visible = 0;
        mappingRows.forEach(function(row, index) {
            if (!mappingRowMatchesFilter(row, filterText)) return;
            visible += 1;
            const tr = document.createElement('tr');
            if (row.tag_missing) tr.classList.add('bg-amber-50/60');

            const statusParts = [];
            if (row.tag_missing) statusParts.push('<span class="inline-flex items-center rounded-full bg-amber-100 text-amber-800 px-2 py-0.5 text-xs">' + escapeHtml((cfg.i18n && cfg.i18n.tagMissing) || 'Tag removed') + '</span>');
            if (row.source_warning) statusParts.push('<span class="inline-flex items-center rounded-full bg-red-100 text-red-800 px-2 py-0.5 text-xs" title="' + escapeHtml(row.source_warning) + '">' + escapeHtml((cfg.i18n && cfg.i18n.sourceWarning) || 'Source unavailable') + '</span>');

            tr.innerHTML =
                '<td class="px-3 py-2 text-gray-800 font-medium">' + escapeHtml(row.id || '') + '</td>' +
                '<td class="px-3 py-2 text-gray-700">' + escapeHtml(row.section || '') + '</td>' +
                '<td class="px-3 py-2"><select class="pb-mapping-source w-full border border-gray-300 rounded pl-2 pr-7 py-1 text-sm" data-index="' + index + '">' +
                    ['FDRS', 'UPR', 'Manual'].map(function(source) {
                        const selected = (row.source || 'Manual') === source ? ' selected' : '';
                        return '<option value="' + source + '"' + selected + '>' + source + '</option>';
                    }).join('') +
                '</select></td>' +
                '<td class="px-3 py-2"><input type="text" class="pb-mapping-override w-full border border-gray-300 rounded px-2 py-1 text-sm" data-index="' + index + '" value="' + escapeHtml(row.label_override || '') + '" placeholder="' + escapeHtml((cfg.i18n && cfg.i18n.labelOverridePlaceholder) || 'Optional') + '"></td>' +
                '<td class="px-3 py-2"><div class="flex flex-wrap gap-1">' + (statusParts.join('') || '<span class="text-gray-400">—</span>') + '</div></td>';
            els.mappingBody.appendChild(tr);
        });

        if (!visible) {
            const empty = document.createElement('tr');
            empty.innerHTML = '<td colspan="5" class="px-4 py-8 text-center text-sm text-gray-500">' + escapeHtml((cfg.i18n && cfg.i18n.noMappingRows) || 'No mapping rows yet.') + '</td>';
            els.mappingBody.appendChild(empty);
        }

        updateMappingCount(visible);

        els.mappingBody.querySelectorAll('.pb-mapping-source').forEach(function(select) {
            select.addEventListener('change', function() {
                const idx = parseInt(select.getAttribute('data-index'), 10);
                if (mappingRows[idx]) mappingRows[idx].source = select.value;
            });
        });
        els.mappingBody.querySelectorAll('.pb-mapping-override').forEach(function(input) {
            input.addEventListener('input', function() {
                const idx = parseInt(input.getAttribute('data-index'), 10);
                if (mappingRows[idx]) mappingRows[idx].label_override = input.value;
            });
        });
    }

    function renderTranslationsTable(rows) {
        translationRows = Array.isArray(rows) ? rows.slice() : [];
        if (!els.translationsBody) return;
        els.translationsBody.innerHTML = '';
        translationRows.forEach(function(row, index) {
            const tr = document.createElement('tr');
            ['id', 'EN', 'FR', 'SP', 'AR'].forEach(function(field) {
                const td = document.createElement('td');
                td.className = 'px-3 py-2';
                const input = document.createElement('input');
                input.type = 'text';
                input.className = 'pb-translation-field w-full border border-gray-300 rounded px-2 py-1';
                input.setAttribute('data-index', String(index));
                input.setAttribute('data-field', field);
                input.value = row[field] || '';
                input.addEventListener('input', function() {
                    if (translationRows[index]) translationRows[index][field] = input.value;
                });
                td.appendChild(input);
                tr.appendChild(td);
            });
            els.translationsBody.appendChild(tr);
        });
    }

    function renderSectionOrderTable(rows) {
        sectionOrderRows = Array.isArray(rows) ? rows.slice() : [];
        if (!els.sectionOrderBody) return;
        els.sectionOrderBody.innerHTML = '';
        sectionOrderRows.forEach(function(row, index) {
            const tr = document.createElement('tr');
            ['part', 'section', 'order'].forEach(function(field) {
                const td = document.createElement('td');
                td.className = 'px-3 py-2';
                const input = document.createElement('input');
                input.type = field === 'order' ? 'number' : 'text';
                input.className = 'pb-section-order-field w-full border border-gray-300 rounded px-2 py-1';
                input.setAttribute('data-index', String(index));
                input.setAttribute('data-field', field);
                input.value = row[field] != null ? row[field] : '';
                input.addEventListener('input', function() {
                    if (!sectionOrderRows[index]) return;
                    sectionOrderRows[index][field] = field === 'order' ? parseInt(input.value, 10) || 0 : input.value;
                });
                td.appendChild(input);
                tr.appendChild(td);
            });
            els.sectionOrderBody.appendChild(tr);
        });
    }

    async function loadYearsPanel() {
        if (!isSystemMode() || !els.yearsMultiselectHost) return;
        const payload = await fetchJson(apiUrl('/years'));
        const available = payload.available_years || [];
        const selected = (payload.selected_years && payload.selected_years.length)
            ? payload.selected_years
            : (payload.effective_years || available);
        yearsSelectionSaved = selected.slice();
        renderYearsMultiselect(available, selected);
    }

    function renderYearsMultiselect(availableYears, selectedYears) {
        if (!els.yearsMultiselectHost || typeof window.MultiselectDropdown !== 'function') return;
        const data = (availableYears || []).map(function(year) {
            return { value: String(year), label: String(year) };
        });
        const selected = (selectedYears || []).map(String);
        if (yearsMultiselect) {
            yearsMultiselect.updateData(data);
            yearsMultiselect.setSelectedValues(selected);
            return;
        }
        yearsMultiselect = new window.MultiselectDropdown({
            containerId: 'pb-progress-years-multiselect',
            name: 'pb-progress-years',
            placeholder: (cfg.i18n && cfg.i18n.yearsPlaceholder) || 'Select years…',
            searchPlaceholder: (cfg.i18n && cfg.i18n.yearsSearchPlaceholder) || 'Search years…',
            data: data,
            selectedValues: selected,
            onSelectionChange: function(values) {
                if (!values.length) {
                    showFlash((cfg.i18n && cfg.i18n.yearsSelectAtLeastOne) || 'Select at least one year.', 'danger');
                    yearsMultiselect.setSelectedValues(yearsSelectionSaved.slice());
                    return;
                }
                scheduleSaveYears(values);
            },
        });
    }

    function scheduleSaveYears(values) {
        if (yearsSaveTimer) window.clearTimeout(yearsSaveTimer);
        yearsSaveTimer = window.setTimeout(function() {
            saveSelectedYears(values).catch(handleAdminError);
        }, 400);
    }

    async function saveSelectedYears(values) {
        const cleaned = (values || []).map(String).sort();
        if (!cleaned.length) return;
        if (cleaned.join(',') === yearsSelectionSaved.slice().sort().join(',')) return;
        const payload = await fetchJson(apiUrl('/years'), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ years: cleaned }),
        });
        yearsSelectionSaved = (payload.selected_years || cleaned).slice();
        showFlash((cfg.i18n && cfg.i18n.yearsUpdated) || 'Report years updated.', 'success');
    }

    async function loadMappingPanel() {
        const payload = await fetchJson(apiUrl('/mapping'));
        renderMappingTable(payload.mapping || []);
    }

    async function loadTranslationsPanel() {
        const payload = await fetchJson(apiUrl('/translations'));
        renderTranslationsTable(payload.translations || []);
    }

    async function loadSectionOrderPanel() {
        const payload = await fetchJson(apiUrl('/section-order'));
        renderSectionOrderTable(payload.section_order || []);
    }

    function showFlash(message, category) {
        if (typeof window.showFlashMessage === 'function') {
            window.showFlashMessage(message, category || 'info');
        }
    }

    async function setDataSource(source) {
        const payload = await fetchJson(apiUrl('/data-source'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ data_source: source }),
        });
        activeDataSource = payload.data_source || source;
        applyDataSourceMode(currentUi().statusCache || {}, false);
        showFlash((cfg.i18n && cfg.i18n.dataSourceUpdated) || 'Data source updated.', 'success');
        await refreshStatus();
    }

    async function syncMappingFromIndicatorBank() {
        const payload = await fetchJson(apiUrl('/mapping/sync-from-indicator-bank'), { method: 'POST' });
        renderMappingTable(payload.mapping || []);
        showFlash((cfg.i18n && cfg.i18n.syncCompleted) || 'Indicator Bank sync completed.', 'success');
    }

    async function applyImportedConfigPayload(payload) {
        if (payload.mapping) renderMappingTable(payload.mapping);
        if (payload.translations) renderTranslationsTable(payload.translations);
        if (payload.section_order) renderSectionOrderTable(payload.section_order);
    }

    function configImportSuccessMessage(payload) {
        const base = (cfg.i18n && cfg.i18n.excelUploadedSuccessfully) || 'Excel uploaded successfully.';
        const validation = payload.validation || {};
        const warnings = validation.warnings || [];
        if (!warnings.length) return base;
        const prefix = (cfg.i18n && cfg.i18n.excelUploadedWithWarnings) || 'Excel uploaded with warnings:';
        return prefix + ' ' + warnings.join(' ');
    }

    function uploadResultFlashLevel(payload) {
        const warnings = (payload.validation && payload.validation.warnings) || [];
        return warnings.length ? 'warning' : 'success';
    }

    async function importConfigFromExcel() {
        const payload = await fetchJson(apiUrl('/config/import-from-excel'), { method: 'POST' });
        await applyImportedConfigPayload(payload);
        showFlash((cfg.i18n && cfg.i18n.configImported) || 'Configuration imported from Excel.', 'success');
    }

    async function saveMapping() {
        await fetchJson(apiUrl('/mapping'), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mapping: mappingRows }),
        });
        showFlash((cfg.i18n && cfg.i18n.mappingSaved) || 'Mapping saved.', 'success');
    }

    async function saveTranslations() {
        await fetchJson(apiUrl('/translations'), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ translations: translationRows }),
        });
        showFlash((cfg.i18n && cfg.i18n.translationsSaved) || 'Translations saved.', 'success');
    }

    async function saveSectionOrder() {
        await fetchJson(apiUrl('/section-order'), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ section_order: sectionOrderRows }),
        });
        showFlash((cfg.i18n && cfg.i18n.sectionOrderSaved) || 'Section order saved.', 'success');
    }

    async function generateSystemDataset() {
        await fetchJson(apiUrl('/generate-system-dataset'), { method: 'POST' });
        showFlash((cfg.i18n && cfg.i18n.systemDatasetGenerated) || 'System dataset generated.', 'success');
        if (els.downloadSystemLink) {
            els.downloadSystemLink.href = apiUrl('/system-dataset/download');
            els.downloadSystemLink.classList.remove('hidden');
        }
        await refreshStatus();
    }

    async function compareSystemDataset() {
        const payload = await fetchJson(apiUrl('/compare-system-dataset'));
        const comparison = payload.comparison || payload;
        if (els.compareSummary) {
            const mismatches = comparison.mismatch_count || 0;
            const excelRows = comparison.excel_rows || 0;
            const intro = (cfg.i18n && cfg.i18n.compareIntro) || 'Comparison';
            const mismatchesLabel = (cfg.i18n && cfg.i18n.compareMismatchesLabel) || 'mismatches of';
            const excelLabel = (cfg.i18n && cfg.i18n.compareExcelRowsLabel) || 'Excel rows';
            const systemLabel = (cfg.i18n && cfg.i18n.compareSystemRowsLabel) || 'System rows';
            els.compareSummary.innerHTML =
                '<p class="font-medium text-gray-900">' + escapeHtml(intro + ': ' + mismatches + ' ' + mismatchesLabel + ' ' + excelRows + ' ' + excelLabel) + '</p>' +
                '<p class="text-gray-600">' + escapeHtml(systemLabel + ': ' + (comparison.system_rows || 0)) + '</p>';
            if (comparison.mismatches && comparison.mismatches.length) {
                const list = document.createElement('ul');
                list.className = 'mt-2 space-y-1 text-xs text-gray-700 max-h-40 overflow-auto';
                comparison.mismatches.slice(0, 20).forEach(function(item) {
                    const li = document.createElement('li');
                    const key = item.key ? item.key.join(' / ') : '';
                    li.textContent = (item.issue || 'mismatch') + (key ? ': ' + key : '') + (item.column ? ' [' + item.column + ']' : '');
                    list.appendChild(li);
                });
                els.compareSummary.appendChild(list);
            }
            els.compareSummary.classList.remove('hidden');
        }
        showFlash((cfg.i18n && cfg.i18n.compareComplete) || 'Comparison complete.', 'success');
    }

    function updateAdminUi(excel, status) {
        const ui = currentUi();
        const cachedStatus = status || currentUi().statusCache || {};
        applyDataSourceMode(cachedStatus);
        ui.hasExcel = canGenerateReport(cachedStatus);
        if (els.generateBtn) els.generateBtn.disabled = !ui.hasExcel;
        if (els.downloadSystemLink) {
            if (isSystemMode() && cachedStatus.system_dataset_available) {
                els.downloadSystemLink.href = apiUrl('/system-dataset/download');
                els.downloadSystemLink.classList.remove('hidden');
            } else {
                els.downloadSystemLink.classList.add('hidden');
            }
        }
        updateReferenceWorkbookActions(cachedStatus);
        updateGenerateHint(cachedStatus);
        if (isExcelMode()) {
            renderExcelFileState(excel || cachedStatus.excel || null);
        }
    }

    function updateCancelButton(running, cancelling) {
        if (!els.cancelBtn) return;
        els.cancelBtn.classList.toggle('hidden', !running);
        els.cancelBtn.disabled = !!cancelling;
        els.cancelBtn.title = (cfg.i18n && cfg.i18n.cancelGeneration) || 'Cancel generation';
        if (cancelling) {
            els.cancelBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1" aria-hidden="true"></i>'
                + ((cfg.i18n && cfg.i18n.cancellingGeneration) || 'Cancelling…');
        } else {
            els.cancelBtn.innerHTML = '<i class="fas fa-stop mr-1" aria-hidden="true"></i>'
                + ((cfg.i18n && cfg.i18n.cancelGeneration) || 'Cancel');
        }
    }

    function updateBuildProgress(status) {
        const ui = currentUi();
        const running = status.status === 'running';
        const failed = status.status === 'failed';
        const done = status.status === 'done';
        const cancelled = status.status === 'cancelled';
        const stageList = status.build_stages || [];

        if (running && !wasBuildRunning) {
            stagesExpanded = false;
        }
        wasBuildRunning = running;

        if (running) ui.trackingBuild = true;

        const showCompletion = ui.trackingBuild && (done || failed || cancelled);
        const showPanel = running || showCompletion;

        if (els.build) els.build.classList.toggle('hidden', !showPanel);
        if (els.buildActive) els.buildActive.classList.toggle('hidden', !running);
        updateCancelButton(running, ui.cancellingBuild);

        if (els.generateBtn) {
            const cached = currentUi().statusCache || status;
            els.generateBtn.disabled = running || !canGenerateReport(cached);
        }

        if (running && els.progressBar) {
            const pct = stageProgressPercent(stageList);
            ui.maxProgressPercent = Math.max(ui.maxProgressPercent, pct);
            els.progressBar.style.width = ui.maxProgressPercent + '%';
        } else if (!running) {
            ui.maxProgressPercent = 15;
        }

        if (els.progressText) {
            els.progressText.textContent = running
                ? currentStageLabel(stageList, status)
                : ((cfg.i18n && cfg.i18n.generatingReport) || 'Generating report...');
        }

        renderBuildStages(running ? stageList : [], status);

        if (showCompletion && failed) {
            let failText = status.error || (cfg.i18n && cfg.i18n.reportGenerationFailed) || 'Report generation failed.';
            if (status.build_log_excerpt) {
                failText = failText + '\n\n' + status.build_log_excerpt;
            }
            setMessage(els.buildMessage, failText, 'error');
            ui.trackingBuild = false;
        } else if (showCompletion && cancelled) {
            setMessage(
                els.buildMessage,
                (cfg.i18n && cfg.i18n.reportGenerationCancelled) || 'Report generation was cancelled.',
                'warning'
            );
            ui.trackingBuild = false;
        } else if (showCompletion && done) {
            const successText = (cfg.i18n && cfg.i18n.reportGeneratedSuccessfully) || 'Report generated successfully.';
            showFlash(successText, 'success');
            setMessage(els.buildMessage, successText, 'success');
            ui.trackingBuild = false;
        } else if (running) {
            setMessage(els.buildMessage, '', null);
        } else if (!showPanel) {
            setMessage(els.buildMessage, '', null);
        }

        updateAdminUi(status.excel || null, status);
    }

    function applyStatusToUi(status) {
        updateBuildProgress(status);
    }

    function renderActiveVersionFromCache() {
        const cached = currentUi().statusCache;
        if (cached) {
            applyStatusToUi(cached);
        } else {
            applyStatusToUi({ status: 'idle', outputs: [] });
        }
    }

    function getCsrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    }

    async function fetchJson(url, options) {
        const opts = Object.assign({ credentials: 'same-origin' }, options || {});
        const method = (opts.method || 'GET').toUpperCase();
        if (method !== 'GET' && method !== 'HEAD') {
            const headers = Object.assign({}, opts.headers || {});
            const token = getCsrfToken();
            if (token) {
                headers['X-CSRFToken'] = token;
            }
            opts.headers = headers;
        }
        const response = await fetch(url, opts);
        const payload = await response.json().catch(function() { return {}; });
        if (!response.ok) {
            throw new Error(payload.message || payload.error || (cfg.i18n && cfg.i18n.requestFailed) || 'Request failed.');
        }
        return payload;
    }

    function anyVersionRunning() {
        return VERSION_ORDER.some(function(versionId) {
            const cached = versionUi[versionId].statusCache;
            return cached && cached.status === 'running';
        });
    }

    async function loadExcelInfo() {
        const payload = await fetchJson(apiUrl('/excel-info'));
        const cachedStatus = Object.assign({}, currentUi().statusCache || {}, {
            excel: payload.excel || null,
        });
        versionUi[activeVersion].statusCache = cachedStatus;
        updateAdminUi(payload.excel || null, cachedStatus);
        return payload.excel || null;
    }

    async function refreshAllStatuses() {
        let hadError = false;
        for (let i = 0; i < VERSION_ORDER.length; i += 1) {
            const versionId = VERSION_ORDER[i];
            try {
                const payload = await fetchJson(apiUrl('/status', versionId));
                versionUi[versionId].statusCache = payload.status || {};
            } catch (error) {
                hadError = true;
            }
        }
        renderActiveVersionFromCache();
        if (hadError && currentUi().trackingBuild && els.build) {
            els.build.classList.remove('hidden');
            if (els.buildActive) els.buildActive.classList.add('hidden');
            setMessage(
                els.buildMessage,
                (cfg.i18n && cfg.i18n.lostConnection) || '',
                'error'
            );
        }
        if (anyVersionRunning()) {
            if (!pollTimer) {
                pollTimer = window.setInterval(function() {
                    refreshAllStatuses().catch(function() {});
                }, 3000);
            }
        } else if (pollTimer) {
            window.clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    async function refreshStatus() {
        try {
            const payload = await fetchJson(apiUrl('/status'));
            const status = payload.status || {};
            versionUi[activeVersion].statusCache = status;
            applyStatusToUi(status);
            if (status.status === 'running' || anyVersionRunning()) {
                if (!pollTimer) {
                    pollTimer = window.setInterval(function() {
                        refreshAllStatuses().catch(function() {});
                    }, 3000);
                }
            } else {
                await refreshAllStatuses();
            }
            return status;
        } catch (error) {
            if (pollTimer) {
                window.clearInterval(pollTimer);
                pollTimer = null;
            }
            if (currentUi().trackingBuild && els.build) {
                els.build.classList.remove('hidden');
                if (els.buildActive) els.buildActive.classList.add('hidden');
                setMessage(
                    els.buildMessage,
                    (cfg.i18n && cfg.i18n.lostConnection) || '',
                    'error'
                );
            }
            throw error;
        }
    }

    function resetUploadForm() {
        if (els.fileInput) els.fileInput.value = '';
    }

    function setUploadBusy(busy) {
        uploadInProgress = !!busy;
        if (els.uploadBtn) els.uploadBtn.disabled = uploadInProgress;
    }

    async function uploadExcelFile(file) {
        if (!file || uploadInProgress || !isExcelMode()) return;
        const formData = new FormData();
        formData.append('excel', file);
        setUploadBusy(true);
        try {
            const payload = await fetchJson(apiUrl('/upload'), {
                method: 'POST',
                body: formData,
            });
            const cachedStatus = Object.assign({}, currentUi().statusCache || {}, {
                excel: payload.excel || null,
            });
            versionUi[activeVersion].statusCache = cachedStatus;
            updateAdminUi(payload.excel || null, cachedStatus);
            await applyImportedConfigPayload(payload);
            showFlash(configImportSuccessMessage(payload), uploadResultFlashLevel(payload));
            if (els.fileInput) els.fileInput.value = '';
        } catch (error) {
            showFlash(error.message, 'danger');
        } finally {
            setUploadBusy(false);
        }
    }

    async function cancelGeneration() {
        const ui = currentUi();
        if (ui.cancellingBuild) return;
        ui.cancellingBuild = true;
        updateCancelButton(true, true);
        try {
            const payload = await fetchJson(apiUrl('/cancel'), { method: 'POST' });
            const status = payload.status || { status: 'cancelled' };
            versionUi[activeVersion].statusCache = status;
            applyStatusToUi(status);
            if (pollTimer) {
                window.clearInterval(pollTimer);
                pollTimer = null;
            }
        } catch (error) {
            showFlash(error.message, 'danger');
            updateCancelButton(true, false);
        } finally {
            ui.cancellingBuild = false;
        }
    }

    async function startGeneration() {
        const ui = currentUi();
        ui.trackingBuild = true;
        stagesExpanded = false;
        setMessage(els.buildMessage, '', null);
        ui.maxProgressPercent = 15;
        if (els.progressBar) els.progressBar.style.width = '15%';
        if (els.build) els.build.classList.remove('hidden');
        if (els.buildActive) els.buildActive.classList.remove('hidden');
        if (els.progressText) els.progressText.textContent = (cfg.i18n && cfg.i18n.preparingReport) || 'Preparing dataset and report...';
        renderBuildStages([], null);
        try {
            const payload = await fetchJson(apiUrl('/generate'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    language: els.languageSelect ? els.languageSelect.value : 'all',
                }),
            });
            const status = payload.status || { status: 'running' };
            versionUi[activeVersion].statusCache = status;
            applyStatusToUi(status);
            if (!pollTimer) {
                pollTimer = window.setInterval(function() {
                    refreshAllStatuses().catch(function() {});
                }, 3000);
            }
        } catch (error) {
            if (els.build) els.build.classList.remove('hidden');
            if (els.buildActive) els.buildActive.classList.add('hidden');
            setMessage(els.buildMessage, error.message, 'error');
            ui.trackingBuild = false;
        }
    }

    function switchVersion(versionId) {
        if (!VERSIONS[versionId] || versionId === activeVersion) return;
        activeVersion = versionId;
        setActiveVersionTab();
        updateExploreLinks();
        renderActiveVersionFromCache();
        refreshStatus().catch(function() {});
        if (activeSubtab === 'build' && isExcelMode()) {
            loadExcelInfo().catch(function() {});
        } else if (activeSubtab === 'build' && isSystemMode()) {
            loadYearsPanel().catch(function() {});
        } else if (isSystemMode() && activeSubtab === 'mapping') {
            loadMappingPanel().catch(handleAdminError);
        } else if (isSystemMode() && activeSubtab === 'translations') {
            loadTranslationsPanel().catch(handleAdminError);
        } else if (isSystemMode() && activeSubtab === 'section-order') {
            loadSectionOrderPanel().catch(handleAdminError);
        }
    }

    function bindVersionTabs() {
        if (!els.versionTabs) return;
        els.versionTabs.querySelectorAll('[data-pb-version]').forEach(function(btn) {
            btn.addEventListener('click', function() {
                switchVersion(btn.getAttribute('data-pb-version'));
            });
        });
    }

    function bindSubtabs() {
        if (!els.subtabs) return;
        els.subtabs.querySelectorAll('[data-pb-subtab]').forEach(function(btn) {
            btn.addEventListener('click', function() {
                setActiveSubtab(btn.getAttribute('data-pb-subtab'));
            });
        });
    }

    function bindAdminEvents() {
        bindSubtabs();
        if (els.mappingFilter) {
            els.mappingFilter.addEventListener('input', function() {
                mappingFilterText = els.mappingFilter.value || '';
                renderMappingTable(mappingRows);
            });
        }
        if (els.uploadBtn && els.fileInput) {
            els.uploadBtn.addEventListener('click', function() {
                if (!uploadInProgress) els.fileInput.click();
            });
            els.fileInput.addEventListener('change', function() {
                const file = els.fileInput.files && els.fileInput.files[0] ? els.fileInput.files[0] : null;
                if (file) uploadExcelFile(file);
            });
        }
        if (els.generateBtn) els.generateBtn.addEventListener('click', startGeneration);
        if (els.cancelBtn) els.cancelBtn.addEventListener('click', function() { cancelGeneration().catch(handleAdminError); });
        if (els.sourceExcelBtn) els.sourceExcelBtn.addEventListener('click', function() {
            setDataSource('excel').catch(function(error) {
                showFlash((error && error.message) || (cfg.i18n && cfg.i18n.requestFailed) || 'Request failed.', 'danger');
            });
        });
        if (els.sourceSystemBtn) els.sourceSystemBtn.addEventListener('click', function() {
            setDataSource('system').catch(function(error) {
                showFlash((error && error.message) || (cfg.i18n && cfg.i18n.requestFailed) || 'Request failed.', 'danger');
            });
        });
        if (els.syncMappingBtn) els.syncMappingBtn.addEventListener('click', function() { syncMappingFromIndicatorBank().catch(handleAdminError); });
        if (els.importConfigBtn) els.importConfigBtn.addEventListener('click', function() { importConfigFromExcel().catch(handleAdminError); });
        if (els.saveMappingBtn) els.saveMappingBtn.addEventListener('click', function() { saveMapping().catch(handleAdminError); });
        if (els.saveTranslationsBtn) els.saveTranslationsBtn.addEventListener('click', function() { saveTranslations().catch(handleAdminError); });
        if (els.saveSectionOrderBtn) els.saveSectionOrderBtn.addEventListener('click', function() { saveSectionOrder().catch(handleAdminError); });
        if (els.generateSystemBtn) els.generateSystemBtn.addEventListener('click', function() { generateSystemDataset().catch(handleAdminError); });
        if (els.compareSystemBtn) els.compareSystemBtn.addEventListener('click', function() { compareSystemDataset().catch(handleAdminError); });
        if (els.stagesToggle) {
            els.stagesToggle.addEventListener('click', function() {
                stagesExpanded = !stagesExpanded;
                const cached = currentUi().statusCache;
                if (cached && cached.status === 'running') {
                    renderBuildStages(cached.build_stages || [], cached);
                }
            });
        }
    }

    function handleAdminError(error) {
        const message = (error && error.message) || (cfg.i18n && cfg.i18n.requestFailed) || 'Request failed.';
        showFlash(message, 'danger');
    }

    function bindEvents() {
        bindVersionTabs();
        bindAdminEvents();
    }

    window.PBProgressAdmin = {
        init: function() {
            setActiveVersionTab();
            updateExploreLinks();
            bindEvents();
            applyDataSourceMode({ data_source: activeDataSource }, false);
            setActiveSubtab(cfg.initialSubtab || 'build');
            refreshAllStatuses().catch(function() {});
        },
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() { window.PBProgressAdmin.init(); });
    } else {
        window.PBProgressAdmin.init();
    }
})();
