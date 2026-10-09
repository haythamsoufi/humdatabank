/**
 * Communication Center - "Background jobs" tab and banner.
 *
 * Shows progress and failures of assignment notification jobs
 * (see app/services/notification/assignment_notification_jobs.py).
 * Polls while any job is active; otherwise refreshes only on demand / tab activation.
 */
(function () {
    const POLL_ACTIVE_MS = 3000;
    const POLL_IDLE_RECHECK_MS = 30000;

    const cfg = () => window.communicationPageConfig || {};
    const t = () => cfg().t || {};
    const urls = () => cfg().urls || {};

    let jobs = [];
    let pollTimer = null;
    let loading = false;
    const expanded = new Set(); // job ids with the entity table open
    const detailCache = new Map(); // job id -> detail payload

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text != null) node.textContent = text;
        return node;
    }

    function fill(template, values) {
        let out = String(template || '');
        Object.keys(values).forEach((key) => {
            out = out.split(`__${key}__`).join(String(values[key]));
        });
        return out;
    }

    function jobUrl(template, jobId) {
        return String(template || '').replace('__JOB__', encodeURIComponent(jobId));
    }

    function fetchJson(url, options) {
        const fn = (window.getApiFetch && window.getApiFetch()) || window.apiFetch || fetch;
        return fn(url, options || {});
    }

    function formatTime(iso) {
        if (!iso) return '';
        const d = new Date(iso);
        return Number.isNaN(d.getTime()) ? '' : d.toLocaleString();
    }

    function statusMeta(status) {
        const tr = t();
        switch (status) {
            case 'queued':
                return { label: tr.jobStatusQueued || 'Queued', badge: 'bg-gray-100 text-gray-800', bar: 'bg-blue-500' };
            case 'running':
                return { label: tr.jobStatusRunning || 'Running', badge: 'bg-blue-100 text-blue-800', bar: 'bg-blue-500' };
            case 'cancel_requested':
                return { label: tr.jobStatusCancelRequested || 'Cancelling', badge: 'bg-yellow-100 text-yellow-800', bar: 'bg-yellow-500' };
            case 'completed':
                return { label: tr.jobStatusCompleted || 'Completed', badge: 'bg-green-100 text-green-800', bar: 'bg-green-500' };
            case 'failed':
                return { label: tr.jobStatusFailed || 'Completed with failures', badge: 'bg-red-100 text-red-800', bar: 'bg-red-500' };
            case 'cancelled':
                return { label: tr.jobStatusCancelled || 'Cancelled', badge: 'bg-gray-100 text-gray-800', bar: 'bg-gray-400' };
            default:
                return { label: status || '', badge: 'bg-gray-100 text-gray-800', bar: 'bg-gray-400' };
        }
    }

    function itemStatusMeta(status) {
        const tr = t();
        switch (status) {
            case 'queued':
                return { label: tr.jobItemQueued || 'Waiting', cls: 'text-gray-600' };
            case 'processing':
            case 'downloading':
                return { label: tr.jobItemProcessing || 'Sending…', cls: 'text-blue-700' };
            case 'completed':
                return { label: tr.jobItemCompleted || 'Done', cls: 'text-green-700' };
            case 'failed':
                return { label: tr.jobItemFailed || 'Failed', cls: 'text-red-700 font-medium' };
            case 'cancelled':
                return { label: tr.jobItemCancelled || 'Not sent (cancelled)', cls: 'text-gray-600' };
            default:
                return { label: status || '', cls: 'text-gray-600' };
        }
    }

    function sourceLabel(source) {
        const tr = t();
        if (source === 'add_countries') return tr.jobSourceAddCountries || 'Countries added';
        if (source === 'add_entity') return tr.jobSourceAddEntity || 'Entity added';
        return tr.jobSourceCreate || 'New assignment';
    }

    function itemResultText(item) {
        const tr = t();
        if (item.status === 'failed') return item.error || '';
        if (item.status !== 'completed') return '';
        const parts = [];
        if (item.notifications > 0) {
            parts.push(fill(tr.jobResultNotifications || '__COUNT__ in-app notification(s)', { COUNT: item.notifications }));
        }
        if (item.email_status === 'sent') {
            parts.push(tr.jobResultEmailSent || 'email sent');
        }
        if (!parts.length) {
            return item.email_detail || tr.jobResultNoRecipients || 'no recipients to notify';
        }
        return parts.join(', ');
    }

    // ----- rendering -----

    function buildItemsTable(items) {
        const tr = t();
        const wrap = el('div', 'mt-3 overflow-x-auto border border-gray-200 rounded-lg');
        const table = el('table', 'min-w-full text-sm');
        const head = el('thead', 'bg-gray-50');
        const headRow = el('tr');
        [tr.jobColEntity || 'Entity', tr.jobColStatus || 'Status', tr.jobColResult || 'Result'].forEach((label) => {
            headRow.appendChild(el('th', 'px-3 py-2 text-left text-xs font-semibold text-gray-600 uppercase tracking-wide', label));
        });
        head.appendChild(headRow);
        table.appendChild(head);
        const body = el('tbody', 'divide-y divide-gray-100');
        items.forEach((item) => {
            const meta = itemStatusMeta(item.status);
            const row = el('tr');
            row.appendChild(el('td', 'px-3 py-2 text-gray-900', item.entity));
            row.appendChild(el('td', `px-3 py-2 whitespace-nowrap ${meta.cls}`, meta.label));
            row.appendChild(el('td', `px-3 py-2 ${item.status === 'failed' ? 'text-red-800' : 'text-gray-700'}`, itemResultText(item)));
            body.appendChild(row);
        });
        table.appendChild(body);
        wrap.appendChild(table);
        return wrap;
    }

    function buildFailures(job) {
        const tr = t();
        if (!job.failures || !job.failures.length) return null;
        const box = el('div', 'mt-3 p-3 bg-red-50 border border-red-200 rounded-lg');
        box.appendChild(el('div', 'text-sm font-medium text-red-900 mb-1', tr.jobFailuresHeading || 'Entities that could not be notified'));
        const list = el('ul', 'text-sm text-red-900 list-disc pl-5 space-y-0.5');
        job.failures.forEach((failure) => {
            const li = el('li');
            li.appendChild(el('span', 'font-medium', failure.entity));
            if (failure.error) li.appendChild(document.createTextNode(` — ${failure.error}`));
            list.appendChild(li);
        });
        box.appendChild(list);
        if (job.failures_truncated) {
            box.appendChild(el('p', 'text-xs text-red-800 mt-2 mb-0', tr.jobFailuresTruncated || ''));
        }
        return box;
    }

    function buildCard(job) {
        const tr = t();
        const meta = statusMeta(job.status);
        const c = job.counts || {};
        const card = el('div', 'border border-gray-200 rounded-lg p-4 bg-white');
        card.setAttribute('data-job-id', job.job_id);

        const top = el('div', 'flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2');
        const titleWrap = el('div', 'min-w-0');
        titleWrap.appendChild(el('div', 'text-sm font-semibold text-gray-900 break-words', job.assignment_label || tr.jobUnnamed || 'Assignment'));
        const subtitle = [sourceLabel(job.source)];
        if (job.created_by) subtitle.push(fill(tr.jobStartedBy || 'Started by __NAME__', { NAME: job.created_by }));
        if (job.created_at) subtitle.push(`${tr.jobCreated || 'Created'} ${formatTime(job.created_at)}`);
        if (job.finished_at) subtitle.push(`${tr.jobFinished || 'Finished'} ${formatTime(job.finished_at)}`);
        titleWrap.appendChild(el('div', 'text-xs text-gray-500 mt-0.5', subtitle.join(' · ')));
        top.appendChild(titleWrap);
        top.appendChild(el('span', `inline-flex self-start items-center rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap ${meta.badge}`, meta.label));
        card.appendChild(top);

        const track = el('div', 'mt-3 w-full h-2 bg-gray-100 rounded-full overflow-hidden');
        const bar = el('div', `h-2 rounded-full transition-all ${meta.bar}`);
        bar.style.width = `${Math.max(0, Math.min(100, Number(job.percent) || 0))}%`;
        track.appendChild(bar);
        track.setAttribute('role', 'progressbar');
        track.setAttribute('aria-valuemin', '0');
        track.setAttribute('aria-valuemax', '100');
        track.setAttribute('aria-valuenow', String(Math.round(Number(job.percent) || 0)));
        card.appendChild(track);

        const summary = [fill(tr.jobProgressLine || '__DONE__ of __TOTAL__ entities processed', { DONE: c.processed || 0, TOTAL: c.total || 0 })];
        if (c.notified) summary.push(fill(tr.jobNotified || '__COUNT__ notified', { COUNT: c.notified }));
        if (c.emails_sent) summary.push(fill(tr.jobEmailsSent || '__COUNT__ email(s) sent', { COUNT: c.emails_sent }));
        if (c.no_recipients) summary.push(fill(tr.jobNoRecipients || '__COUNT__ without recipients', { COUNT: c.no_recipients }));
        if (c.failed) summary.push(fill(tr.jobFailedCount || '__COUNT__ failed', { COUNT: c.failed }));
        card.appendChild(el('div', 'mt-2 text-sm text-gray-700', summary.join(' · ')));

        if (job.error) {
            const errorBox = el('div', 'mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-900');
            errorBox.textContent = job.error;
            card.appendChild(errorBox);
        }
        const failures = buildFailures(job);
        if (failures) card.appendChild(failures);

        const actions = el('div', 'mt-3 flex flex-wrap gap-2');
        const toggle = el('button', 'btn btn-secondary btn-sm whitespace-nowrap');
        toggle.type = 'button';
        toggle.textContent = expanded.has(job.job_id) ? (tr.jobHideDetails || 'Hide entities') : (tr.jobShowDetails || 'Show all entities');
        toggle.addEventListener('click', () => toggleDetails(job.job_id));
        actions.appendChild(toggle);
        if (job.status === 'queued' || job.status === 'running') {
            const cancel = el('button', 'btn btn-secondary btn-sm whitespace-nowrap');
            cancel.type = 'button';
            cancel.textContent = tr.jobCancel || 'Stop sending';
            cancel.addEventListener('click', () => cancelJob(job.job_id));
            actions.appendChild(cancel);
        }
        if (job.status === 'failed' && !job.dismissed) {
            const dismiss = el('button', 'btn btn-secondary btn-sm whitespace-nowrap');
            dismiss.type = 'button';
            dismiss.textContent = tr.jobDismiss || 'Dismiss';
            dismiss.addEventListener('click', () => dismissJob(job.job_id));
            actions.appendChild(dismiss);
        }
        card.appendChild(actions);

        if (expanded.has(job.job_id)) {
            const detail = detailCache.get(job.job_id);
            if (detail && detail.items) card.appendChild(buildItemsTable(detail.items));
        }
        return card;
    }

    function renderList() {
        const list = document.getElementById('background-jobs-list');
        const empty = document.getElementById('background-jobs-empty');
        if (!list) return;
        while (list.firstChild) list.removeChild(list.firstChild);
        jobs.forEach((job) => list.appendChild(buildCard(job)));
        if (empty) empty.classList.toggle('hidden', jobs.length > 0);
    }

    function updateBadgeAndBanner() {
        const active = jobs.filter((j) => j.is_active);
        const failed = jobs.filter((j) => j.status === 'failed' && !j.dismissed);

        const badge = document.getElementById('background-jobs-tab-badge');
        if (badge) {
            const n = failed.length || active.length;
            badge.textContent = n ? String(n) : '';
            badge.classList.toggle('hidden', !n);
            badge.classList.toggle('bg-red-100', failed.length > 0);
            badge.classList.toggle('text-red-800', failed.length > 0);
            badge.classList.toggle('bg-blue-100', !failed.length && active.length > 0);
            badge.classList.toggle('text-blue-800', !failed.length && active.length > 0);
        }

        const notice = document.getElementById('background-jobs-notice');
        const message = document.getElementById('background-jobs-notice-message');
        const icon = document.getElementById('background-jobs-notice-icon');
        if (!notice || !message || !icon) return;

        const tr = t();
        const setTone = (tone) => {
            ['bg-blue-50', 'border-blue-200', 'text-blue-900', 'bg-red-50', 'border-red-200', 'text-red-900'].forEach((cls) => notice.classList.remove(cls));
            if (tone === 'red') notice.classList.add('bg-red-50', 'border-red-200', 'text-red-900');
            else notice.classList.add('bg-blue-50', 'border-blue-200', 'text-blue-900');
        };

        // Failures take priority over progress: they need attention.
        if (failed.length) {
            setTone('red');
            icon.className = 'fas fa-exclamation-circle mr-2';
            message.textContent = fill(tr.jobsFailedNotice || 'Some assignment notifications could not be sent (__COUNT__ job(s) with failures).', { COUNT: failed.length });
            notice.classList.remove('hidden');
        } else if (active.length) {
            const done = active.reduce((sum, j) => sum + ((j.counts || {}).processed || 0), 0);
            const total = active.reduce((sum, j) => sum + ((j.counts || {}).total || 0), 0);
            setTone('blue');
            icon.className = 'fas fa-spinner fa-spin mr-2';
            message.textContent = fill(tr.jobsRunningNotice || 'Sending assignment notifications in the background: __DONE__ of __TOTAL__ entities done.', { DONE: done, TOTAL: total });
            notice.classList.remove('hidden');
        } else {
            notice.classList.add('hidden');
        }
    }

    function showError(show) {
        const box = document.getElementById('background-jobs-error');
        if (!box) return;
        box.textContent = show ? (t().jobsLoadError || 'Could not load background jobs. Please try again.') : '';
        box.classList.toggle('hidden', !show);
    }

    // ----- data -----

    async function refreshExpandedDetails() {
        const ids = Array.from(expanded).filter((id) => jobs.some((j) => j.job_id === id));
        await Promise.all(ids.map(async (id) => {
            try {
                const data = await fetchJson(jobUrl(urls().backgroundJobDetail, id));
                if (data && data.job) detailCache.set(id, data.job);
            } catch (_) { /* keep the previous detail */ }
        }));
    }

    function schedulePoll() {
        if (pollTimer) {
            clearTimeout(pollTimer);
            pollTimer = null;
        }
        const anyActive = jobs.some((j) => j.is_active);
        pollTimer = setTimeout(load, anyActive ? POLL_ACTIVE_MS : POLL_IDLE_RECHECK_MS);
    }

    async function load() {
        if (loading || !urls().backgroundJobs) return;
        loading = true;
        try {
            const data = await fetchJson(urls().backgroundJobs);
            jobs = (data && data.jobs) || [];
            showError(false);
            await refreshExpandedDetails();
            renderList();
            updateBadgeAndBanner();
        } catch (_) {
            showError(true);
        } finally {
            loading = false;
            schedulePoll();
        }
    }

    async function toggleDetails(jobId) {
        if (expanded.has(jobId)) {
            expanded.delete(jobId);
            renderList();
            return;
        }
        expanded.add(jobId);
        try {
            const data = await fetchJson(jobUrl(urls().backgroundJobDetail, jobId));
            if (data && data.job) detailCache.set(jobId, data.job);
        } catch (_) {
            showError(true);
        }
        renderList();
    }

    async function postAction(url) {
        try {
            await fetchJson(url, { method: 'POST', body: JSON.stringify({}), headers: { 'Content-Type': 'application/json' } });
        } catch (err) {
            const message = (err && err.message) || t().jobActionFailed || 'That action could not be completed.';
            if (typeof window.showFlashMessage === 'function') window.showFlashMessage(message, 'error');
        }
        await load();
    }

    function cancelJob(jobId) {
        if (!window.confirm(t().jobConfirmCancel || 'Stop this job? Entities not yet processed will not be notified.')) return;
        postAction(jobUrl(urls().backgroundJobCancel, jobId));
    }

    function dismissJob(jobId) {
        postAction(jobUrl(urls().backgroundJobDismiss, jobId));
    }

    function init() {
        const refresh = document.getElementById('background-jobs-refresh');
        if (refresh) refresh.addEventListener('click', () => load());
        const view = document.getElementById('background-jobs-notice-view');
        if (view) {
            view.addEventListener('click', () => {
                const tab = document.getElementById('tab-jobs');
                if (tab) tab.click();
            });
        }
        load();
    }

    window.CommunicationJobs = {
        refresh: load,
        onTabActivated() {
            load();
        },
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
