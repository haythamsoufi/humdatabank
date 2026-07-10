(function() {
    const cfg = window.PBProgressConfig || {};
    const API_BASE = cfg.apiBase || '/admin/data-exploration/pb-progress';
    const CAN_MANAGE = !!cfg.canManage;
    const VERSIONS = cfg.versions || {};
    const VERSION_ORDER = cfg.versionOrder || [];
    let activeVersion = cfg.defaultVersion || "";
    let pollTimer = null;
    let selectedFile = null;
    let importModal = null;
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
                statusCache: null,
            };
        });
    }
    initVersionUi();

    const els = {
        empty: document.getElementById('pb-progress-empty'),
        build: document.getElementById('pb-progress-build'),
        buildActive: document.getElementById('pb-progress-build-active'),
        buildMessage: document.getElementById('pb-progress-build-message'),
        viewer: document.getElementById('pb-progress-viewer'),
        viewerToolbar: document.getElementById('pb-progress-viewer-toolbar'),
        viewerToolbarAnchor: document.getElementById('pb-progress-viewer-toolbar-anchor'),
        viewerToolbarWrap: document.getElementById('pb-progress-viewer-toolbar-wrap'),
        viewerToolbarSpacer: document.getElementById('pb-progress-viewer-toolbar-spacer'),
        lastGenerated: document.getElementById('pb-progress-last-generated'),
        downloads: document.getElementById('pb-progress-downloads'),
        reportLanguageWrap: document.getElementById('pb-progress-report-language-wrap'),
        reportLanguageSelect: document.getElementById('pb-progress-report-language'),
        iframe: document.getElementById('pb-progress-iframe'),
        iframeLoading: document.getElementById('pb-progress-iframe-loading'),
        printBtn: document.getElementById('pb-progress-print-btn'),
        openTab: document.getElementById('pb-progress-open-tab'),
        tab: document.getElementById('tab-pb-progress'),
        versionTabs: document.getElementById('pb-progress-version-tabs'),
        openImportBtn: document.getElementById('pb-progress-open-import-btn'),
        importModal: document.getElementById('pb-progress-import-modal'),
        importVersionLabel: document.getElementById('pb-progress-import-version-label'),
        badge: document.getElementById('pb-progress-excel-badge'),
        badgeText: document.getElementById('pb-progress-excel-badge-text'),
        noExcelNotice: document.getElementById('pb-progress-no-excel-notice'),
        dropzone: document.getElementById('pb-progress-dropzone'),
        fileInput: document.getElementById('pb-progress-file-input'),
        chooseFileBtn: document.getElementById('pb-progress-choose-file-btn'),
        selectedFile: document.getElementById('pb-progress-selected-file'),
        replaceExisting: document.getElementById('pb-progress-replace-existing'),
        uploadBtn: document.getElementById('pb-progress-upload-btn'),
        uploadMessage: document.getElementById('pb-progress-upload-message'),
        generateBtn: document.getElementById('pb-progress-generate-btn'),
        languageSelect: document.getElementById('pb-progress-language'),
        progressText: document.getElementById('pb-progress-progress-text'),
        progressBar: document.getElementById('pb-progress-progress-bar'),
        stages: document.getElementById('pb-progress-stages'),
    };

    function currentUi() {
        return versionUi[activeVersion];
    }

    function versionMeta(versionId) {
        return VERSIONS[versionId] || { label: versionId };
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
        if (els.importVersionLabel) {
            els.importVersionLabel.textContent = (cfg.i18n && cfg.i18n.versionLabel ? cfg.i18n.versionLabel + ' ' : '') + (versionMeta(activeVersion).label || activeVersion);
        }
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

    function createDownloadLink(output) {
        const link = document.createElement('a');
        link.href = output.url;
        link.className = 'btn btn-secondary btn-sm';
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        const sizeSuffix = output.size_label ? ' (' + output.size_label + ')' : '';
        link.innerHTML = '<i class="fas fa-download mr-2"></i>' + (output.label || output.name) + sizeSuffix;
        return link;
    }

    function renderBuildStages(stageList) {
        if (!els.stages) return;
        if (!stageList || !stageList.length) {
            els.stages.classList.add('hidden');
            els.stages.innerHTML = '';
            return;
        }
        els.stages.classList.remove('hidden');
        els.stages.innerHTML = '';
        stageList.forEach(function(stage) {
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

    const DOWNLOAD_LANG_ORDER = ['English', 'French', 'Spanish', 'Arabic'];
    const ALL_FIGS_NAMES = ['pb-report-figures-all.zip', 'gb-report-figures-all.zip'];
    const ALL_DOCX_NAMES = ['pb-report-docx-all.zip', 'gb-report-docx-all.zip'];
    const ALL_PDF_NAMES = ['pb-report-pdf-all.zip', 'gb-report-pdf-all.zip'];

    function findAllLanguagesOutput(outputs, names) {
        var found = null;
        outputs.forEach(function(o) { if (names.indexOf(o.name) !== -1) found = o; });
        return found;
    }

    function buildTypeGroups(outputs) {
        const REPORT_HTML = ['pb-report.html', 'gb-report.html'];
        const skipNames = ALL_FIGS_NAMES.concat(ALL_DOCX_NAMES, ALL_PDF_NAMES);
        const groups = { docx: [], pdf: [], zip: [] };
        outputs.forEach(function(output) {
            if (REPORT_HTML.indexOf(output.name) !== -1) return;
            if (skipNames.indexOf(output.name) !== -1) return;
            const name = (output.name || '').toLowerCase();
            let lang = null;
            DOWNLOAD_LANG_ORDER.forEach(function(l) { if (name.includes(l.toLowerCase())) lang = l; });
            if (!lang) return;
            if (name.endsWith('.docx'))      groups.docx.push({ lang: lang, output: output });
            else if (name.endsWith('.pdf'))  groups.pdf.push({ lang: lang, output: output });
            else if (name.endsWith('.zip'))  groups.zip.push({ lang: lang, output: output });
        });
        ['docx', 'pdf', 'zip'].forEach(function(t) {
            groups[t].sort(function(a, b) {
                return DOWNLOAD_LANG_ORDER.indexOf(a.lang) - DOWNLOAD_LANG_ORDER.indexOf(b.lang);
            });
        });
        return groups;
    }

    function createTypeDropdown(label, icon, iconColor, items) {
        if (!items.length) return null;

        const wrap = document.createElement('div');
        wrap.className = 'relative';

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-secondary btn-sm inline-flex items-center gap-1.5';
        btn.innerHTML = '<i class="' + icon + ' ' + iconColor + ' mr-1 shrink-0"></i>' +
            label + ' <i class="fas fa-chevron-down text-xs opacity-60"></i>';

        const menu = document.createElement('div');
        menu.className = 'pb-dl-menu absolute z-30 left-0 mt-1 w-48 rounded-lg border border-gray-200 bg-white shadow-lg overflow-hidden hidden';

        items.forEach(function(item, idx) {
            const row = document.createElement('a');
            row.href = item.output.url;
            row.target = '_blank';
            row.rel = 'noopener noreferrer';
            row.className = 'flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors' +
                (idx > 0 ? ' border-t border-gray-100' : '');
            row.innerHTML = '<span class="flex-1">' + item.lang + '</span>' +
                (item.output.size_label ? '<span class="text-xs text-gray-400">' + item.output.size_label + '</span>' : '');
            menu.appendChild(row);
        });

        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const wasOpen = !menu.classList.contains('hidden');
            document.querySelectorAll('.pb-dl-menu').forEach(function(m) { m.classList.add('hidden'); });
            if (!wasOpen) menu.classList.remove('hidden');
        });

        wrap.appendChild(btn);
        wrap.appendChild(menu);
        return wrap;
    }

    function renderDownloads(container, outputs) {
        container.innerHTML = '';
        if (!outputs.length) return;
        let allDocxOutput = findAllLanguagesOutput(outputs, ALL_DOCX_NAMES);
        let allPdfOutput = findAllLanguagesOutput(outputs, ALL_PDF_NAMES);
        let allFigsOutput = findAllLanguagesOutput(outputs, ALL_FIGS_NAMES);
        const groups = buildTypeGroups(outputs);
        if (allDocxOutput) groups.docx.push({ lang: 'All languages', output: allDocxOutput });
        if (allPdfOutput) groups.pdf.push({ lang: 'All languages', output: allPdfOutput });
        if (allFigsOutput) groups.zip.push({ lang: 'All languages', output: allFigsOutput });
        var configs = [
            { key: 'docx', label: 'Word',    icon: 'fas fa-file-word', color: 'text-blue-700'  },
            { key: 'pdf',  label: 'PDF',     icon: 'fas fa-file-pdf',  color: 'text-red-600'   },
            { key: 'zip',  label: 'Figures', icon: 'fas fa-images',    color: 'text-green-600' },
        ];
        configs.forEach(function(cfg) {
            const el = createTypeDropdown(cfg.label, cfg.icon, cfg.color, groups[cfg.key]);
            if (el) container.appendChild(el);
        });
    }

    let syncingReportLanguage = false;
    let pendingIframeLanguage = null;

    function getIframeDocument() {
        if (!els.iframe) return null;
        try {
            return els.iframe.contentDocument
                || (els.iframe.contentWindow && els.iframe.contentWindow.document)
                || null;
        } catch (err) {
            return null;
        }
    }

    function prepareEmbeddedReportDoc(doc) {
        if (!doc || doc.getElementById('pb-embedded-language-hide')) return;
        var style = doc.createElement('style');
        style.id = 'pb-embedded-language-hide';
        style.textContent =
            'html.pb-report-embedded #quarto-margin-sidebar .pb-language-selector,' +
            'html.pb-report-embedded #quarto-sidebar .pb-language-selector,' +
            '#quarto-margin-sidebar .pb-language-selector,' +
            '#quarto-sidebar .pb-language-selector { display: none !important; }';
        (doc.head || doc.documentElement).appendChild(style);
        if (doc.documentElement) {
            doc.documentElement.classList.add('pb-report-embedded');
        }
    }

    function applyIframeReportLanguage(lang) {
        if (!lang) return false;
        var doc = getIframeDocument();
        if (!doc) return false;
        var select = doc.getElementById('pb-language-select');
        if (!select) return false;
        if (select.value !== lang) {
            select.value = lang;
            select.dispatchEvent(new Event('change', { bubbles: true }));
        }
        return true;
    }

    function flushPendingIframeLanguage() {
        if (!pendingIframeLanguage) return;
        if (applyIframeReportLanguage(pendingIframeLanguage)) {
            pendingIframeLanguage = null;
        }
    }

    function setIframeReportLanguage(lang) {
        if (!els.iframe || !lang) return;
        pendingIframeLanguage = lang;
        if (applyIframeReportLanguage(lang)) {
            pendingIframeLanguage = null;
            return;
        }
        try {
            var win = els.iframe.contentWindow;
            if (win) {
                win.postMessage({ type: 'pb-report-set-language', lang: lang }, window.location.origin);
            }
        } catch (err) {}
    }

    function syncReportLanguageFromIframe() {
        if (!els.iframe || !els.reportLanguageSelect) return;
        try {
            var doc = getIframeDocument();
            if (!doc) return;
            var select = doc.getElementById('pb-language-select');
            if (!select || !DOWNLOAD_LANG_ORDER.includes(select.value)) return;
            syncingReportLanguage = true;
            els.reportLanguageSelect.value = select.value;
            syncingReportLanguage = false;
        } catch (err) {}
    }

    function initializeEmbeddedReportLanguage() {
        var doc = getIframeDocument();
        if (!doc) return;
        prepareEmbeddedReportDoc(doc);
        if (pendingIframeLanguage) {
            flushPendingIframeLanguage();
        } else {
            syncReportLanguageFromIframe();
        }
        window.setTimeout(function() {
            if (pendingIframeLanguage) {
                flushPendingIframeLanguage();
            } else {
                syncReportLanguageFromIframe();
            }
        }, 100);
        window.setTimeout(flushPendingIframeLanguage, 500);
    }

    function renderConsumerView(status) {
        const outputs = status.outputs || [];
        const REPORT_HTML_NAMES = ['pb-report.html', 'gb-report.html'];
        const htmlOutput = outputs.find(function(item) { return REPORT_HTML_NAMES.indexOf(item.name) !== -1; });
        const running = status.status === 'running';
        const hasOutputs = outputs.length > 0;

        if (els.empty) els.empty.classList.toggle('hidden', hasOutputs || running);
        if (els.viewer) els.viewer.classList.toggle('hidden', !hasOutputs);
        if (!hasOutputs) setToolbarPinned(false);

        if (!hasOutputs) {
            if (els.iframe) els.iframe.removeAttribute('src');
            if (els.printBtn) els.printBtn.classList.add('hidden');
            if (els.openTab) els.openTab.classList.add('hidden');
            if (els.reportLanguageWrap) {
                els.reportLanguageWrap.classList.add('hidden');
                els.reportLanguageWrap.classList.remove('flex');
            }
            if (els.lastGenerated) els.lastGenerated.classList.add('hidden');
            return;
        }

        if (els.downloads) renderDownloads(els.downloads, outputs);
        if (els.reportLanguageWrap) {
            els.reportLanguageWrap.classList.remove('hidden');
            els.reportLanguageWrap.classList.add('flex');
        }

        if (htmlOutput && els.iframe) {
            if (els.iframe.src !== htmlOutput.url) {
                if (els.iframeLoading) els.iframeLoading.classList.remove('hidden');
                els.iframe.src = htmlOutput.url;
            }
            if (els.printBtn) els.printBtn.classList.remove('hidden');
            if (els.openTab) {
                els.openTab.href = htmlOutput.url;
                els.openTab.classList.remove('hidden');
            }
        }
        if (status.finished_at && els.lastGenerated) {
            els.lastGenerated.textContent = (cfg.i18n && cfg.i18n.lastUpdated ? cfg.i18n.lastUpdated + ' ' : '') + formatUploadedAt(status.finished_at);
            els.lastGenerated.classList.remove('hidden');
        }
    }

    function updateAdminUi(excel) {
        if (!CAN_MANAGE) return;
        const ui = currentUi();
        ui.hasExcel = !!excel;
        if (els.generateBtn) els.generateBtn.disabled = !ui.hasExcel;
        if (!excel) {
            if (els.badge) els.badge.classList.add('hidden');
            if (els.noExcelNotice) els.noExcelNotice.classList.remove('hidden');
            return;
        }
        const parts = [excel.filename || 'SG Report.xlsx'];
        if (excel.size_label) parts.push(excel.size_label);
        if (excel.uploaded_at) parts.push(formatUploadedAt(excel.uploaded_at));
        if (els.badgeText) els.badgeText.textContent = parts.join(' · ');
        if (els.badge) els.badge.classList.remove('hidden');
        if (els.noExcelNotice) els.noExcelNotice.classList.add('hidden');
    }

    function updateBuildProgress(status) {
        const ui = currentUi();
        const running = status.status === 'running';
        const failed = status.status === 'failed';
        const done = status.status === 'done';
        const stageList = status.build_stages || [];

        if (running) ui.trackingBuild = true;

        const showCompletion = ui.trackingBuild && (done || failed);
        const showPanel = running || showCompletion;

        if (els.build) els.build.classList.toggle('hidden', !showPanel);
        if (els.buildActive) els.buildActive.classList.toggle('hidden', !running);

        if (CAN_MANAGE && els.generateBtn) els.generateBtn.disabled = running || !ui.hasExcel;

        if (running && els.progressBar) {
            const pct = stageProgressPercent(stageList);
            ui.maxProgressPercent = Math.max(ui.maxProgressPercent, pct);
            els.progressBar.style.width = ui.maxProgressPercent + '%';
        } else if (!running) {
            ui.maxProgressPercent = 15;
        }

        if (els.progressText) {
            els.progressText.textContent = running && status.build_stage_label
                ? status.build_stage_label
                : (cfg.i18n && cfg.i18n.generatingReport) || 'Generating report...';
        }

        renderBuildStages(running ? stageList : []);

        if (showCompletion && failed) {
            setMessage(els.buildMessage, status.error || (cfg.i18n && cfg.i18n.reportGenerationFailed) || 'Report generation failed.', 'error');
            ui.trackingBuild = false;
        } else if (showCompletion && done) {
            setMessage(els.buildMessage, (cfg.i18n && cfg.i18n.reportGeneratedSuccessfully) || 'Report generated successfully.', 'success');
            ui.trackingBuild = false;
        } else if (running) {
            setMessage(els.buildMessage, '', null);
        } else if (!showPanel) {
            setMessage(els.buildMessage, '', null);
        }

        if (CAN_MANAGE && status.excel) {
            updateAdminUi(status.excel);
        }
    }

    function applyStatusToUi(status) {
        renderConsumerView(status);
        updateBuildProgress(status);
        if (CAN_MANAGE && status.excel) {
            updateAdminUi(status.excel);
        } else if (CAN_MANAGE && !status.excel) {
            updateAdminUi(null);
        }
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
        if (!CAN_MANAGE) return null;
        const payload = await fetchJson(apiUrl('/excel-info'));
        updateAdminUi(payload.excel || null);
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
        selectedFile = null;
        if (els.fileInput) els.fileInput.value = '';
        if (els.uploadBtn) els.uploadBtn.disabled = true;
        if (els.selectedFile) els.selectedFile.classList.add('hidden');
        setMessage(els.uploadMessage, '', null);
    }

    function setSelectedFile(file) {
        selectedFile = file || null;
        if (!els.uploadBtn) return;
        els.uploadBtn.disabled = !selectedFile;
        if (!selectedFile) {
            if (els.selectedFile) els.selectedFile.classList.add('hidden');
            return;
        }
        if (els.selectedFile) {
            els.selectedFile.textContent = selectedFile.name + ' (' + Math.round(selectedFile.size / 1024) + ' KB)';
            els.selectedFile.classList.remove('hidden');
        }
    }

    async function uploadExcel() {
        if (!selectedFile) return;
        const ui = currentUi();
        if (!ui.hasExcel && els.replaceExisting && !els.replaceExisting.checked) {
            setMessage(els.uploadMessage, (cfg.i18n && cfg.i18n.enableReplaceWorkbook) || '', 'error');
            return;
        }
        const formData = new FormData();
        formData.append('excel', selectedFile);
        setMessage(els.uploadMessage, (cfg.i18n && cfg.i18n.uploading) || 'Uploading...', null);
        try {
            const payload = await fetchJson(apiUrl('/upload'), {
                method: 'POST',
                body: formData,
            });
            updateAdminUi(payload.excel || null);
            setMessage(els.uploadMessage, (cfg.i18n && cfg.i18n.excelUploadedSuccessfully) || 'Excel uploaded successfully.', 'success');
            setSelectedFile(null);
            if (els.fileInput) els.fileInput.value = '';
        } catch (error) {
            setMessage(els.uploadMessage, error.message, 'error');
        }
    }

    async function startGeneration() {
        if (importModal) importModal.closeModal();
        const ui = currentUi();
        ui.trackingBuild = true;
        setMessage(els.buildMessage, '', null);
        ui.maxProgressPercent = 15;
        if (els.progressBar) els.progressBar.style.width = '15%';
        if (els.build) els.build.classList.remove('hidden');
        if (els.buildActive) els.buildActive.classList.remove('hidden');
        if (els.progressText) els.progressText.textContent = (cfg.i18n && cfg.i18n.generatingReport) || 'Generating report...';
        renderBuildStages([]);
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
        renderActiveVersionFromCache();
        refreshStatus().catch(function() {});
    }

    function bindVersionTabs() {
        if (!els.versionTabs) return;
        els.versionTabs.querySelectorAll('[data-pb-version]').forEach(function(btn) {
            btn.addEventListener('click', function() {
                switchVersion(btn.getAttribute('data-pb-version'));
            });
        });
    }

    function bindAdminEvents() {
        if (!CAN_MANAGE) return;
        if (window.ModalUtils && els.importModal) {
            importModal = window.ModalUtils.makeModal(els.importModal, {
                onOpen: function() {
                    resetUploadForm();
                    setActiveVersionTab();
                    loadExcelInfo().catch(function() {});
                    refreshStatus().catch(function() {});
                },
            });
        }
        if (els.openImportBtn && importModal) {
            els.openImportBtn.addEventListener('click', function() {
                importModal.openModal();
            });
        }
        if (els.chooseFileBtn && els.fileInput) {
            els.chooseFileBtn.addEventListener('click', function() { els.fileInput.click(); });
            els.fileInput.addEventListener('change', function() {
                setSelectedFile(els.fileInput.files && els.fileInput.files[0] ? els.fileInput.files[0] : null);
            });
        }
        if (els.dropzone) {
            ['dragenter', 'dragover'].forEach(function(eventName) {
                els.dropzone.addEventListener(eventName, function(event) {
                    event.preventDefault();
                    els.dropzone.classList.add('border-blue-400', 'bg-blue-50/40');
                });
            });
            ['dragleave', 'drop'].forEach(function(eventName) {
                els.dropzone.addEventListener(eventName, function(event) {
                    event.preventDefault();
                    els.dropzone.classList.remove('border-blue-400', 'bg-blue-50/40');
                });
            });
            els.dropzone.addEventListener('drop', function(event) {
                const file = event.dataTransfer && event.dataTransfer.files ? event.dataTransfer.files[0] : null;
                setSelectedFile(file || null);
            });
        }
        if (els.uploadBtn) els.uploadBtn.addEventListener('click', uploadExcel);
        if (els.generateBtn) els.generateBtn.addEventListener('click', startGeneration);
    }

    function bindEvents() {
        bindVersionTabs();
        bindAdminEvents();
        if (els.tab) {
            els.tab.addEventListener('click', function() {
                refreshAllStatuses().catch(function() {});
            });
        }
    }

    function scrollToIframeOffset(offset, extraPadding) {
        if (!els.iframe || !Number.isFinite(offset)) return;
        var padding = Number.isFinite(extraPadding) ? extraPadding : 16;
        if (els.viewerToolbar) padding += els.viewerToolbar.offsetHeight;
        var scrollParent = findScrollParent(els.iframe);
        var iframeRect = els.iframe.getBoundingClientRect();
        var parentRect = scrollParent.getBoundingClientRect();
        var top = scrollParent.scrollTop + (iframeRect.top - parentRect.top) + offset - padding;
        scrollParent.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
    }

    function elementDocumentTop(doc, el) {
        var rect = el.getBoundingClientRect();
        var rootRect = doc.documentElement.getBoundingClientRect();
        return rect.top - rootRect.top;
    }

    function bindIframeTocNavigation() {
        if (!els.iframe) return;
        var bind = function() {
            try {
                var doc = els.iframe.contentDocument
                    || (els.iframe.contentWindow && els.iframe.contentWindow.document);
                if (!doc || doc.documentElement.dataset.pbTocScrollBound === '1') return;
                doc.documentElement.dataset.pbTocScrollBound = '1';
                doc.addEventListener('click', function(event) {
                    var link = event.target.closest(
                        '#toc a[href^="#"], #quarto-sidebar a[href^="#"], #quarto-margin-sidebar a[href^="#"]'
                    );
                    if (!link) return;
                    var hash = link.hash || link.getAttribute('href') || '';
                    if (!hash || hash === '#') return;
                    event.preventDefault();
                    event.stopPropagation();
                    var id = hash.charAt(0) === '#' ? hash.slice(1) : hash;
                    var target = doc.getElementById(id);
                    if (!target) return;
                    scrollToIframeOffset(elementDocumentTop(doc, target), 16);
                }, true);
            } catch (err) {}
        };
        els.iframe.addEventListener('load', bind);
        bind();
    }

    // ── Iframe integration ────────────────────────────────────────────────
    if (els.iframe) {
        els.iframe.addEventListener('load', function() {
            if (els.iframeLoading) els.iframeLoading.classList.add('hidden');
            initializeEmbeddedReportLanguage();
        });
        bindIframeTocNavigation();
    }

    if (els.reportLanguageSelect) {
        els.reportLanguageSelect.addEventListener('change', function() {
            if (syncingReportLanguage) return;
            setIframeReportLanguage(els.reportLanguageSelect.value);
        });
    }

    window.addEventListener('message', function(event) {
        if (event.origin !== window.location.origin) return;
        if (!event.data || event.data.type !== 'pb-report-language') return;
        if (!els.reportLanguageSelect || !DOWNLOAD_LANG_ORDER.includes(event.data.lang)) return;
        syncingReportLanguage = true;
        els.reportLanguageSelect.value = event.data.lang;
        syncingReportLanguage = false;
    });

    if (els.printBtn) {
        els.printBtn.addEventListener('click', function() {
            try { els.iframe && els.iframe.contentWindow && els.iframe.contentWindow.print(); } catch(e) {}
        });
    }

    function findScrollParent(node) {
        let parent = node.parentElement;
        while (parent && parent !== document.body) {
            const overflowY = window.getComputedStyle(parent).overflowY;
            if (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay') {
                return parent;
            }
            parent = parent.parentElement;
        }
        return document.scrollingElement || document.documentElement;
    }

    let toolbarPinObserver = null;
    let toolbarPinned = false;
    let toolbarPinInitialized = false;

    function syncPinnedToolbarGeometry() {
        if (!toolbarPinned || !els.viewerToolbar || !els.viewerToolbarWrap) return;
        const scrollParent = findScrollParent(els.viewerToolbarWrap);
        const parentRect = scrollParent.getBoundingClientRect();
        const wrapRect = els.viewerToolbarWrap.getBoundingClientRect();
        els.viewerToolbar.style.position = 'fixed';
        els.viewerToolbar.style.top = Math.max(0, parentRect.top) + 'px';
        els.viewerToolbar.style.left = wrapRect.left + 'px';
        els.viewerToolbar.style.width = wrapRect.width + 'px';
        els.viewerToolbar.style.zIndex = '40';
    }

    function setToolbarPinned(next) {
        if (!els.viewerToolbar || !els.viewerToolbarSpacer) return;
        const wantPinned = !!next;
        if (wantPinned === toolbarPinned) {
            if (wantPinned) syncPinnedToolbarGeometry();
            return;
        }
        toolbarPinned = wantPinned;
        if (toolbarPinned) {
            const height = els.viewerToolbar.offsetHeight;
            els.viewerToolbarSpacer.style.height = height + 'px';
            els.viewerToolbarSpacer.classList.remove('hidden');
            els.viewerToolbar.classList.add('is-pinned', 'shadow-md');
            syncPinnedToolbarGeometry();
        } else {
            els.viewerToolbar.style.position = '';
            els.viewerToolbar.style.top = '';
            els.viewerToolbar.style.left = '';
            els.viewerToolbar.style.width = '';
            els.viewerToolbar.style.zIndex = '';
            els.viewerToolbar.classList.remove('is-pinned', 'shadow-md');
            els.viewerToolbarSpacer.classList.add('hidden');
            els.viewerToolbarSpacer.style.height = '';
        }
    }

    function initToolbarPin() {
        if (!els.viewerToolbar || !els.viewerToolbarAnchor || !els.viewerToolbarWrap) return;
        if (toolbarPinInitialized) return;
        toolbarPinInitialized = true;

        const scrollParent = findScrollParent(els.viewerToolbarWrap);
        const onScrollOrResize = function() {
            if (!els.viewer || els.viewer.classList.contains('hidden')) {
                setToolbarPinned(false);
                return;
            }
            if (toolbarPinned) syncPinnedToolbarGeometry();
        };

        scrollParent.addEventListener('scroll', onScrollOrResize, { passive: true });
        window.addEventListener('resize', onScrollOrResize);

        if (typeof IntersectionObserver === 'undefined') {
            scrollParent.addEventListener('scroll', function() {
                if (!els.viewer || els.viewer.classList.contains('hidden')) return;
                const parentTop = scrollParent.getBoundingClientRect().top;
                const anchorBottom = els.viewerToolbarAnchor.getBoundingClientRect().bottom;
                setToolbarPinned(anchorBottom <= parentTop + 1);
            }, { passive: true });
            return;
        }

        const root = (scrollParent === document.body || scrollParent === document.documentElement)
            ? null
            : scrollParent;
        toolbarPinObserver = new IntersectionObserver(function(entries) {
            if (!els.viewer || els.viewer.classList.contains('hidden')) {
                setToolbarPinned(false);
                return;
            }
            const entry = entries[0];
            if (!entry) return;
            setToolbarPinned(!entry.isIntersecting);
        }, { root: root, threshold: [0, 1] });
        toolbarPinObserver.observe(els.viewerToolbarAnchor);
    }

    // Auto-resize the iframe to its content so no inner scrollbar appears.
    window.addEventListener('message', function(e) {
        if (e.origin !== window.location.origin) return;
        if (!e.data || !els.iframe) return;

        if (e.data.type === 'pb-report-height') {
            var h = parseInt(e.data.height, 10);
            if (h > 0) els.iframe.style.height = h + 'px';
            return;
        }

        if (e.data.type === 'pb-report-scroll') {
            var offset = parseInt(e.data.offset, 10);
            if (!Number.isFinite(offset)) return;
            var padding = parseInt(e.data.padding, 10);
            scrollToIframeOffset(offset, Number.isFinite(padding) ? padding : 16);
        }
    });
    // ─────────────────────────────────────────────────────────────────────

    document.addEventListener('click', function() {
        document.querySelectorAll('.pb-dl-menu').forEach(function(m) { m.classList.add('hidden'); });
    });

    window.PBProgress = {
        init: function() {
            setActiveVersionTab();
            bindEvents();
            initToolbarPin();
            refreshAllStatuses().catch(function() {});
        },
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() { window.PBProgress.init(); });
    } else {
        window.PBProgress.init();
    }
})();
