/**
 * Workflow progress tooltip: step descriptions on hover/focus, default to current step.
 * Also infinite-scrolls status/workflow change history when present.
 */
(function () {
    'use strict';

    const HISTORY_LOAD_THRESHOLD_PX = 40;
    const HISTORY_PAGE_LIMIT = 8;

    function historyUrl(aesId, offset) {
        const params = new URLSearchParams({
            offset: String(offset || 0),
            limit: String(HISTORY_PAGE_LIMIT),
        });
        return `/api/forms/assignment/${encodeURIComponent(aesId)}/status-history?${params}`;
    }

    async function fetchStatusHistoryPage(list) {
        if (!list || list.dataset.historyLoading === '1') return;
        if (list.dataset.statusHistoryHasMore !== '1') return;

        const aesId = list.dataset.statusHistoryAesId;
        const offset = Number(list.dataset.statusHistoryOffset || 0);
        if (!aesId) return;

        list.dataset.historyLoading = '1';
        const sentinel = list.querySelector('.assignment-status-history-load-more');
        const spinner = sentinel && sentinel.querySelector('.assignment-status-history-load-more-spinner');
        if (spinner) spinner.hidden = false;

        try {
            const response = await fetch(historyUrl(aesId, offset), {
                credentials: 'same-origin',
                headers: { Accept: 'application/json' },
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            const html = (data && data.html) || '';
            const hasMore = !!(data && data.has_more);
            const nextOffset = data && data.next_offset != null ? Number(data.next_offset) : offset;

            if (html) {
                const wrap = document.createElement('div');
                wrap.innerHTML = html;
                const fragment = document.createDocumentFragment();
                while (wrap.firstChild) fragment.appendChild(wrap.firstChild);
                if (sentinel) {
                    list.insertBefore(fragment, sentinel);
                } else {
                    list.appendChild(fragment);
                }
            }

            list.dataset.statusHistoryOffset = String(nextOffset);
            list.dataset.statusHistoryHasMore = hasMore ? '1' : '0';
            if (!hasMore && sentinel) sentinel.remove();
            if (hasMore) {
                requestAnimationFrame(() => maybeLoadMoreHistory(list));
            }
        } catch (err) {
            // Keep the sentinel so the user can scroll again to retry.
            // eslint-disable-next-line no-console
            console.warn('[status-history] failed to load more changes', err);
        } finally {
            list.dataset.historyLoading = '0';
            if (spinner) spinner.hidden = true;
        }
    }

    function maybeLoadMoreHistory(list) {
        if (!list || list.dataset.statusHistoryHasMore !== '1') return;
        if (list.scrollHeight <= list.clientHeight) {
            fetchStatusHistoryPage(list);
            return;
        }
        if (list.scrollTop + list.clientHeight >= list.scrollHeight - HISTORY_LOAD_THRESHOLD_PX) {
            fetchStatusHistoryPage(list);
        }
    }

    function bindStatusHistoryList(list) {
        if (!list || list.dataset.historyScrollBound === '1') return;
        list.dataset.historyScrollBound = '1';
        list.addEventListener('scroll', () => maybeLoadMoreHistory(list), { passive: true });
    }

    function initPipelineContainer(container) {
        const tooltip = container.querySelector('.assignment-status-pipeline-tooltip');
        if (!tooltip) return;

        const descLabel = tooltip.querySelector('.assignment-status-pipeline-description-label');
        const descText = tooltip.querySelector('.assignment-status-pipeline-description-text');
        const steps = Array.from(tooltip.querySelectorAll('.assignment-status-pipeline-step'));
        const pipeline = tooltip.querySelector('.assignment-status-pipeline');
        const historyList = tooltip.querySelector('.assignment-status-history-list[data-status-history-aes-id]');

        if (historyList) {
            bindStatusHistoryList(historyList);
            container.addEventListener('mouseenter', () => maybeLoadMoreHistory(historyList));
        }

        if (!descLabel || !descText || !steps.length) return;

        const parsedDefault = parseInt(tooltip.getAttribute('data-default-step-index') || '0', 10);
        const defaultIdx = Number.isFinite(parsedDefault) && parsedDefault >= 0 && parsedDefault < steps.length
            ? parsedDefault
            : 0;

        function setActiveStep(idx) {
            const step = steps[idx];
            if (!step) return;

            steps.forEach((candidate, candidateIdx) => {
                const isActive = candidateIdx === idx;
                candidate.classList.toggle('is-desc-active', isActive);
                candidate.setAttribute('aria-current', isActive ? 'step' : 'false');
            });

            descLabel.textContent = step.getAttribute('data-step-label') || '';
            descText.textContent = step.getAttribute('data-step-description') || '';
        }

        function resetToDefault() {
            setActiveStep(defaultIdx);
        }

        steps.forEach((step, idx) => {
            step.addEventListener('mouseenter', () => setActiveStep(idx));
            step.addEventListener('focus', () => setActiveStep(idx));
        });

        if (pipeline) {
            pipeline.addEventListener('mouseleave', resetToDefault);
        }

        tooltip.addEventListener('focusout', (event) => {
            if (tooltip.contains(event.relatedTarget)) return;
            resetToDefault();
        });

        resetToDefault();
    }

    function initAll() {
        document.querySelectorAll('.assignment-status-pipeline-container').forEach(initPipelineContainer);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
})();
