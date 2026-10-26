/**
 * Shared helpers for pb-progress.js (consumer/Explore tab) and
 * pb-progress-admin.js (Backoffice management page).
 *
 * Both pages poll the same /status endpoint and render the same build
 * progress bar/stage list/cancel button, so this module holds the pieces
 * that were previously copy-pasted identically (or nearly identically) into
 * both files. Each caller keeps its own thin wrapper around these — closures
 * over page-specific state (active version, DOM elements, i18n strings) stay
 * in the page script; this module only takes explicit arguments so it has no
 * page-specific state of its own.
 *
 * Load this script before pb-progress.js / pb-progress-admin.js.
 */
(function() {
    'use strict';

    function buildApiUrl(apiBase, path, version) {
        return apiBase + '/' + encodeURIComponent(version) + path;
    }

    function currentStageLabel(stageList, status, i18n) {
        if (status && status.build_stage_label) return status.build_stage_label;
        if (!stageList || !stageList.length) {
            return (i18n && i18n.generatingReport) || 'Generating report...';
        }
        let active = null;
        stageList.forEach(function(stage) {
            if (stage.state === 'active') active = stage;
        });
        if (active && active.label) return active.label;
        return (i18n && i18n.generatingReport) || 'Generating report...';
    }

    function updateStagesToggle(toggleEl, expanded, visible, i18n) {
        if (!toggleEl) return;
        toggleEl.classList.toggle('hidden', !visible);
        toggleEl.textContent = expanded
            ? ((i18n && i18n.hideBuildSteps) || 'Hide steps')
            : ((i18n && i18n.showBuildSteps) || 'Show steps');
        toggleEl.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    }

    function renderBuildStages(stagesEl, toggleEl, stageList, status, stagesExpanded, i18n) {
        if (!stagesEl) return;
        const list = stageList || [];
        const running = status && status.status === 'running';
        if (!running || !list.length) {
            stagesEl.classList.add('hidden');
            stagesEl.innerHTML = '';
            updateStagesToggle(toggleEl, false, false, i18n);
            return;
        }
        updateStagesToggle(toggleEl, stagesExpanded, true, i18n);
        if (!stagesExpanded) {
            stagesEl.classList.add('hidden');
            stagesEl.innerHTML = '';
            return;
        }
        stagesEl.classList.remove('hidden');
        stagesEl.innerHTML = '';
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
            stagesEl.appendChild(item);
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

    function getCsrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    }

    async function fetchJson(url, options, requestFailedMessage) {
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
            throw new Error(payload.message || payload.error || requestFailedMessage || 'Request failed.');
        }
        return payload;
    }

    function anyVersionRunning(versionUi, versionOrder) {
        return (versionOrder || []).some(function(versionId) {
            const cached = versionUi[versionId] && versionUi[versionId].statusCache;
            return cached && cached.status === 'running';
        });
    }

    function updateCancelButton(btnEl, running, cancelling, i18n) {
        if (!btnEl) return;
        btnEl.classList.toggle('hidden', !running);
        btnEl.disabled = !!cancelling;
        btnEl.title = (i18n && i18n.cancelGeneration) || 'Cancel generation';
        if (cancelling) {
            btnEl.innerHTML = '<i class="fas fa-spinner fa-spin mr-1" aria-hidden="true"></i>'
                + ((i18n && i18n.cancellingGeneration) || 'Cancelling…');
        } else {
            btnEl.innerHTML = '<i class="fas fa-stop mr-1" aria-hidden="true"></i>'
                + ((i18n && i18n.cancelGeneration) || 'Cancel');
        }
    }

    window.PBProgressShared = {
        buildApiUrl: buildApiUrl,
        currentStageLabel: currentStageLabel,
        updateStagesToggle: updateStagesToggle,
        renderBuildStages: renderBuildStages,
        stageProgressPercent: stageProgressPercent,
        setMessage: setMessage,
        formatUploadedAt: formatUploadedAt,
        getCsrfToken: getCsrfToken,
        fetchJson: fetchJson,
        anyVersionRunning: anyVersionRunning,
        updateCancelButton: updateCancelButton,
    };
})();
