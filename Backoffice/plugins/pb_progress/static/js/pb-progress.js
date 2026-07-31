(function() {
    const cfg = window.PBProgressConfig || {};
    const API_BASE = cfg.apiBase || '/admin/data-exploration/pb-progress';
    const VERSIONS = cfg.versions || {};
    const VERSION_ORDER = cfg.versionOrder || [];
    const URL_PARAM_PB_VERSION = 'pb_version';
    let activeVersion = cfg.defaultVersion || '';
    let pollTimer = null;
    const versionUi = {};

    function apiUrl(path, versionId) {
        const version = versionId || activeVersion;
        return API_BASE + '/' + encodeURIComponent(version) + path;
    }

    function initVersionUi() {
        VERSION_ORDER.forEach(function(versionId) {
            versionUi[versionId] = {
                maxProgressPercent: 15,
                trackingBuild: false,
                cancellingBuild: false,
                statusCache: null,
                statusLoaded: false,
            };
        });
    }
    initVersionUi();

    const els = {
        empty: document.getElementById('pb-progress-empty'),
        loading: document.getElementById('pb-progress-loading'),
        build: document.getElementById('pb-progress-build'),
        buildActive: document.getElementById('pb-progress-build-active'),
        buildMessage: document.getElementById('pb-progress-build-message'),
        viewer: document.getElementById('pb-progress-viewer'),
        viewerToolbar: document.getElementById('pb-progress-viewer-toolbar'),
        viewerToolbarTitle: document.getElementById('pb-progress-viewer-toolbar-title'),
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
        progressText: document.getElementById('pb-progress-progress-text'),
        progressBar: document.getElementById('pb-progress-progress-bar'),
        stages: document.getElementById('pb-progress-stages'),
        stagesToggle: document.getElementById('pb-progress-stages-toggle'),
        cancelBtn: document.getElementById('pb-progress-cancel-btn'),
    };

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

    function getVersionFromUrl() {
        try {
            return new URLSearchParams(window.location.search).get(URL_PARAM_PB_VERSION) || '';
        } catch (e) {
            return '';
        }
    }

    function resolveInitialVersion() {
        const fromUrl = getVersionFromUrl();
        if (fromUrl && VERSIONS[fromUrl]) {
            activeVersion = fromUrl;
        }
    }

    function syncVersionToUrl(versionId) {
        if (typeof window.applyExploreParamsToUrl === 'function') {
            window.applyExploreParamsToUrl({
                tab: 'pb-progress',
                pb_version: versionId || '',
            });
            return;
        }
        const usp = new URLSearchParams(window.location.search);
        usp.set('tab', 'pb-progress');
        if (versionId) usp.set(URL_PARAM_PB_VERSION, versionId);
        else usp.delete(URL_PARAM_PB_VERSION);
        const query = usp.toString();
        window.history.replaceState({}, '', query ? (window.location.pathname + '?' + query) : window.location.pathname);
    }

    function currentUi() {
        return versionUi[activeVersion];
    }

    function updateViewerToolbarTitle() {
        if (!els.viewerToolbarTitle) return;
        const version = VERSIONS[activeVersion];
        els.viewerToolbarTitle.textContent = version && version.label ? version.label : '';
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
        updateViewerToolbarTitle();
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
        configs.forEach(function(item) {
            const el = createTypeDropdown(item.label, item.icon, item.color, groups[item.key]);
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
            '#quarto-sidebar .pb-language-selector,' +
            '.quarto-alternate-formats,' +
            '#title-block-header .subtitle { display: none !important; }';
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

    function showLoadingState() {
        if (els.loading) els.loading.classList.remove('hidden');
        if (els.empty) els.empty.classList.add('hidden');
        if (els.viewer) els.viewer.classList.add('hidden');
        if (els.build) els.build.classList.add('hidden');
        setToolbarPinned(false);
    }

    function renderConsumerView(status) {
        const ui = currentUi();
        if (!ui.statusLoaded) {
            showLoadingState();
            return;
        }
        if (els.loading) els.loading.classList.add('hidden');

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

    function updateCancelButton(running, cancelling) {
        if (!els.cancelBtn || !cfg.canManage) return;
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
            setMessage(els.buildMessage, status.error || (cfg.i18n && cfg.i18n.reportGenerationFailed) || 'Report generation failed.', 'error');
            ui.trackingBuild = false;
        } else if (showCompletion && cancelled) {
            setMessage(
                els.buildMessage,
                (cfg.i18n && cfg.i18n.reportGenerationCancelled) || 'Report generation was cancelled.',
                'warning'
            );
            ui.trackingBuild = false;
        } else if (showCompletion && done) {
            setMessage(els.buildMessage, (cfg.i18n && cfg.i18n.reportGeneratedSuccessfully) || 'Report generated successfully.', 'success');
            ui.trackingBuild = false;
        } else if (running) {
            setMessage(els.buildMessage, '', null);
        } else if (!showPanel) {
            setMessage(els.buildMessage, '', null);
        }
    }

    function applyStatusToUi(status) {
        renderConsumerView(status);
        updateBuildProgress(status);
    }

    function renderActiveVersionFromCache() {
        const ui = currentUi();
        if (!ui.statusLoaded) {
            showLoadingState();
            return;
        }
        if (ui.statusCache) {
            applyStatusToUi(ui.statusCache);
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

    async function refreshAllStatuses() {
        let hadError = false;
        for (let i = 0; i < VERSION_ORDER.length; i += 1) {
            const versionId = VERSION_ORDER[i];
            try {
                const payload = await fetchJson(apiUrl('/status', versionId));
                versionUi[versionId].statusCache = payload.status || {};
                versionUi[versionId].statusLoaded = true;
            } catch (error) {
                hadError = true;
                versionUi[versionId].statusLoaded = true;
                if (!versionUi[versionId].statusCache) {
                    versionUi[versionId].statusCache = { status: 'idle', outputs: [] };
                }
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
            versionUi[activeVersion].statusLoaded = true;
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
            versionUi[activeVersion].statusLoaded = true;
            if (!versionUi[activeVersion].statusCache) {
                versionUi[activeVersion].statusCache = { status: 'idle', outputs: [] };
            }
            renderActiveVersionFromCache();
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
            updateCancelButton(true, false);
            if (currentUi().trackingBuild && els.build) {
                setMessage(els.buildMessage, error.message, 'error');
            }
        } finally {
            ui.cancellingBuild = false;
        }
    }

    function switchVersion(versionId) {
        if (!VERSIONS[versionId] || versionId === activeVersion) return;
        activeVersion = versionId;
        setActiveVersionTab();
        renderActiveVersionFromCache();
        syncVersionToUrl(versionId);
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

    function bindEvents() {
        bindVersionTabs();
        if (els.stagesToggle) {
            els.stagesToggle.addEventListener('click', function() {
                stagesExpanded = !stagesExpanded;
                const cached = currentUi().statusCache;
                if (cached && cached.status === 'running') {
                    renderBuildStages(cached.build_stages || [], cached);
                }
            });
        }
        if (els.cancelBtn) {
            els.cancelBtn.addEventListener('click', function() {
                cancelGeneration().catch(function() {});
            });
        }
        if (els.tab) {
            els.tab.addEventListener('click', function() {
                refreshAllStatuses().catch(function() {});
            });
        }
    }

    if (els.iframe) {
        els.iframe.addEventListener('load', function() {
            if (els.iframeLoading) els.iframeLoading.classList.add('hidden');
            initializeEmbeddedReportLanguage();
        });
    }

    if (els.reportLanguageSelect) {
        els.reportLanguageSelect.addEventListener('change', function() {
            if (syncingReportLanguage) return;
            setIframeReportLanguage(els.reportLanguageSelect.value);
        });
    }

    window.addEventListener('message', function(event) {
        if (event.origin !== window.location.origin) return;
        if (!event.data) return;

        if (event.data.type === 'pb-report-language') {
            if (!els.reportLanguageSelect || !DOWNLOAD_LANG_ORDER.includes(event.data.lang)) return;
            syncingReportLanguage = true;
            els.reportLanguageSelect.value = event.data.lang;
            syncingReportLanguage = false;
            return;
        }

        if (event.data.type === 'pb-report-height' && els.iframe) {
            var h = parseInt(event.data.height, 10);
            if (h > 0) els.iframe.style.height = h + 'px';
            return;
        }

        if (event.data.type === 'pb-report-scroll-to' && els.iframe) {
            var offsetTop = parseInt(event.data.top, 10);
            if (!Number.isFinite(offsetTop)) return;
            var scrollParent = findScrollParent(els.viewerToolbarWrap || els.iframe);
            var iframeTop = 0;
            var node = els.iframe;
            while (node && node !== scrollParent) {
                iframeTop += node.offsetTop;
                node = node.offsetParent;
            }
            var gap = (toolbarPinned && els.viewerToolbar) ? els.viewerToolbar.offsetHeight + 12 : 16;
            scrollParent.scrollTo({
                top: Math.max(0, iframeTop + offsetTop - gap),
                behavior: 'smooth',
            });
            return;
        }
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

    document.addEventListener('click', function() {
        document.querySelectorAll('.pb-dl-menu').forEach(function(m) { m.classList.add('hidden'); });
    });

    window.PBProgress = {
        init: function() {
            resolveInitialVersion();
            setActiveVersionTab();
            bindEvents();
            initToolbarPin();
            showLoadingState();
            refreshAllStatuses().catch(function() {
                const ui = currentUi();
                ui.statusLoaded = true;
                if (!ui.statusCache) {
                    ui.statusCache = { status: 'idle', outputs: [] };
                }
                renderActiveVersionFromCache();
            });
            if (els.tab && els.tab.getAttribute('aria-selected') === 'true') {
                syncVersionToUrl(activeVersion);
            }
        },
        getActiveVersion: function() {
            return activeVersion;
        },
        setActiveVersion: function(versionId) {
            if (!VERSIONS[versionId]) return;
            if (versionId === activeVersion) return;
            activeVersion = versionId;
            setActiveVersionTab();
            renderActiveVersionFromCache();
            syncVersionToUrl(versionId);
            if (!currentUi().statusLoaded) {
                showLoadingState();
            }
            refreshStatus().catch(function() {});
        },
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() { window.PBProgress.init(); });
    } else {
        window.PBProgress.init();
    }
})();
