// Entry-form completion rate, section nav status icons, and missing-item highlights.

const STATUS_ICON_CLASSES = {
    Completed: 'fas fa-check-circle text-green-500',
    in_progress: 'fas fa-pen text-blue-500',
    'Not Started': 'far fa-circle text-gray-400',
    'N/A': 'fas fa-minus-circle text-gray-500',
};

const COMPLETION_COLOR_CLASSES = ['text-red-600', 'text-amber-600', 'text-green-700', 'text-gray-400', 'font-semibold'];
const HIGHLIGHT_CLASS = 'completion-gap-highlight';
const SECTION_HIGHLIGHT_CLASS = 'completion-gap-section';
const BTN_ACTIVE_CLASS = 'completion-gap-active';

const LABEL_SHOW = 'Show me what I missed';
const LABEL_CLEAR = 'Clear highlights';

const _t = (k) => (typeof window.t === 'function' ? window.t(k) : k);

let gapsActive = false;
let gapsLoading = false;
let lastGapsPayload = null;
let refreshCompletionTimer = null;
let suppressRefreshUntil = 0;
let refreshAbort = null;

function cancelPendingCompletionRefresh() {
    if (refreshCompletionTimer) {
        clearTimeout(refreshCompletionTimer);
        refreshCompletionTimer = null;
    }
}

function markSaveAppliedProgress() {
    cancelPendingCompletionRefresh();
    suppressRefreshUntil = Date.now() + 1000;
    try {
        document.body.dataset.completionRateFromSave = '1';
    } catch (_) { /* no-op */ }
}

function collectHiddenCompletionQueryString(extraParams = {}) {
    if (typeof window.collectHiddenFieldsForSubmission === 'function') {
        window.collectHiddenFieldsForSubmission();
    }

    const params = new URLSearchParams();
    const hiddenFieldsInput = document.getElementById('hidden_fields_to_clear');
    const hiddenFields = (hiddenFieldsInput?.value || '').trim();
    if (hiddenFields) {
        params.set('hidden_fields', hiddenFields);
    }

    const hiddenSections = Array
        .from(document.querySelectorAll('.relevance-hidden[id^="section-container-"]'))
        .map((el) => (el.id || '').replace('section-container-', ''))
        .filter((id) => /^\d+$/.test(id))
        .join(',');
    if (hiddenSections) {
        params.set('hidden_sections', hiddenSections);
    }

    Object.entries(extraParams).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
            params.set(key, String(value));
        }
    });

    const qs = params.toString();
    return qs ? `?${qs}` : '';
}

export function coerceCompletionRate(value) {
    if (typeof value === 'number' && Number.isFinite(value)) {
        return value;
    }
    if (typeof value === 'string' && value.trim() !== '') {
        const parsed = Number(value);
        if (Number.isFinite(parsed)) {
            return parsed;
        }
    }
    return null;
}

function completionColorClass(rate) {
    if (rate >= 80) return 'text-green-700 font-semibold';
    if (rate >= 25) return 'text-amber-600 font-semibold';
    return 'text-red-600 font-semibold';
}

function getCompletionDisplay() {
    return document.getElementById('completion-rate-display');
}

function getGapButton() {
    return document.getElementById('completion-gap-btn');
}

function getGapButtonLabel() {
    const btn = getGapButton();
    return btn ? btn.querySelector('.completion-gap-btn-label') : null;
}

function setGapButtonLabel(text) {
    const label = getGapButtonLabel();
    if (label) {
        label.textContent = _t(text);
    }
}

function updateGapButtonState(completionRate) {
    const btn = getGapButton();
    if (!btn) {
        return;
    }

    if (gapsActive) {
        btn.disabled = false;
        setGapButtonLabel(LABEL_CLEAR);
        btn.setAttribute('aria-label', _t('Clear missing-item highlights'));
        return;
    }

    const complete = Number.isFinite(completionRate) && completionRate >= 100;
    btn.disabled = complete || gapsLoading;
    setGapButtonLabel(LABEL_SHOW);
    btn.setAttribute(
        'aria-label',
        complete ? _t('All countable items are complete') : _t('Show me what I missed')
    );
}

/**
 * Update the header completion-rate display.
 * @param {number} completionRate
 * @returns {boolean} whether the display was updated
 */
export function applyCompletionRate(completionRate) {
    const completionDisplay = getCompletionDisplay();
    const rate = coerceCompletionRate(completionRate);
    if (!completionDisplay || rate === null) {
        return false;
    }
    completionDisplay.textContent = `${rate.toFixed(1)}%`;
    completionDisplay.classList.remove(...COMPLETION_COLOR_CLASSES);
    completionDisplay.classList.add('font-medium', ...completionColorClass(rate).split(/\s+/));

    const btn = getGapButton();
    if (btn) {
        btn.dataset.completionRate = String(rate);
    }
    updateGapButtonState(rate);
    return true;
}

/**
 * Update section/sub-section status icons in the side nav.
 * @param {Record<string, string>} sectionStatuses keyed by section id (string)
 */
export function updateSectionStatusIcons(sectionStatuses) {
    if (!sectionStatuses || typeof sectionStatuses !== 'object') {
        return;
    }

    document.querySelectorAll('a.section-link[data-section-id^="section-container-"]').forEach((link) => {
        const sectionId = (link.dataset.sectionId || '').replace(/^section-container-/, '');
        const status = sectionStatuses[sectionId];
        if (!status) {
            return;
        }

        const icon = link.querySelector('.section-status-icon');
        if (!icon) {
            return;
        }

        const sizeClass = icon.classList.contains('w-3') ? 'w-3 h-3' : 'w-4 h-4';
        const statusClasses = STATUS_ICON_CLASSES[status] || STATUS_ICON_CLASSES['Not Started'];
        icon.className = `section-status-icon ${statusClasses} flex-shrink-0 ${sizeClass}`;
    });
}

function clearCompletionGapHighlights() {
    document.querySelectorAll(`.form-item-block.${HIGHLIGHT_CLASS}`).forEach((el) => {
        el.classList.remove(HIGHLIGHT_CLASS);
    });
    document.querySelectorAll(`.repeat-entry__title-select-wrap.${HIGHLIGHT_CLASS}, .repeat-entry__header.${HIGHLIGHT_CLASS}, .repeat-entry.${HIGHLIGHT_CLASS}`).forEach((el) => {
        el.classList.remove(HIGHLIGHT_CLASS);
    });
    document.querySelectorAll(`a.section-link.${SECTION_HIGHLIGHT_CLASS}`).forEach((el) => {
        el.classList.remove(SECTION_HIGHLIGHT_CLASS);
    });

    const btn = getGapButton();
    if (btn) {
        btn.classList.remove(BTN_ACTIVE_CLASS);
        btn.setAttribute('aria-pressed', 'false');
    }
    gapsActive = false;

    const rate = parseFloat(btn?.dataset.completionRate || '');
    updateGapButtonState(rate);
}

function showFlash(message, type = 'info') {
    if (typeof window.showFlashMessage === 'function') {
        window.showFlashMessage(message, type);
    }
}

function scrollContainerForElement(el) {
    const mainElement = document.querySelector('main[style*="overflow-y"]') || document.querySelector('main');
    const isMainContainer = mainElement && mainElement.scrollHeight > mainElement.clientHeight;
    return isMainContainer ? mainElement : window;
}

function scrollElementIntoView(el) {
    if (!el) return;
    const scrollContainer = scrollContainerForElement(el);
    const headerOffset = 100;
    const rect = el.getBoundingClientRect();

    if (scrollContainer === window) {
        const targetTop = Math.max(0, window.pageYOffset + rect.top - headerOffset);
        window.scrollTo({ top: targetTop, behavior: 'smooth' });
        return;
    }

    const containerRect = scrollContainer.getBoundingClientRect();
    const elTopRel = rect.top - containerRect.top;
    const targetTop = Math.max(0, scrollContainer.scrollTop + elTopRel - headerOffset);
    scrollContainer.scrollTo({ top: targetTop, behavior: 'smooth' });
}

function ensurePageVisibleForElement(el) {
    const section = el.closest('[id^="section-container-"]');
    if (!section) return;

    const pageNumber = section.getAttribute('data-page-number');
    if (pageNumber && window.__ifrcPagination && typeof window.__ifrcPagination.showPageByNumber === 'function') {
        window.__ifrcPagination.showPageByNumber(parseInt(pageNumber, 10));
    }
}

function findHighlightTarget(formItemId) {
    const id = String(formItemId);

    const titleSelect = document.querySelector(
        `select[data-use-as-repeat-entry-title="true"][data-field-item-id="${id}"]`
    );
    if (titleSelect && !titleSelect.closest('.relevance-hidden')) {
        const wrap = titleSelect.closest('.repeat-entry__title-select-wrap')
            || titleSelect.closest('.repeat-entry__header')
            || titleSelect.closest('.repeat-entry');
        if (wrap) {
            return wrap;
        }
    }

    const blocks = Array.from(document.querySelectorAll(`.form-item-block[data-item-id="${id}"]`));
    for (const block of blocks) {
        if (block.classList.contains('relevance-hidden')) {
            continue;
        }
        if (block.classList.contains('repeat-entry-title-field--hidden')) {
            const entry = block.closest('.repeat-entry');
            const wrap = entry?.querySelector('.repeat-entry__title-select-wrap');
            if (wrap) {
                return wrap;
            }
            if (entry) {
                return entry;
            }
            continue;
        }
        if (block.dataset.itemType === 'blank' || block.dataset.itemType === 'image') {
            continue;
        }
        return block;
    }
    return null;
}

function applyCompletionGapHighlights(payload) {
    clearCompletionGapHighlights();

    const missingItems = Array.isArray(payload?.missing_items) ? payload.missing_items : [];
    const sectionIds = new Set((payload?.section_ids || []).map(String));

    let highlightedCount = 0;

    missingItems.forEach((item) => {
        const block = findHighlightTarget(item.form_item_id);
        if (block) {
            block.classList.add(HIGHLIGHT_CLASS);
            highlightedCount += 1;
        }
    });

    sectionIds.forEach((sectionId) => {
        document.querySelectorAll(`a.section-link[data-section-id="section-container-${sectionId}"]`).forEach((link) => {
            link.classList.add(SECTION_HIGHLIGHT_CLASS);
        });
        document.querySelectorAll(`a.repeat-entry-nav-link[data-repeat-section-id="${sectionId}"]`).forEach((link) => {
            link.classList.add(SECTION_HIGHLIGHT_CLASS);
        });
    });

    const btn = getGapButton();
    if (btn) {
        btn.classList.add(BTN_ACTIVE_CLASS);
        btn.setAttribute('aria-pressed', 'true');
    }
    gapsActive = true;
    updateGapButtonState(payload?.completion_rate);

    const firstTarget = missingItems
        .map((item) => findHighlightTarget(item.form_item_id))
        .find(Boolean);

    if (firstTarget) {
        ensurePageVisibleForElement(firstTarget);
        requestAnimationFrame(() => scrollElementIntoView(firstTarget));
    }

    const missingCount = payload?.missing_count ?? missingItems.length;
    if (missingCount === 0) {
        showFlash(_t('All countable items are complete.'), 'success');
        clearCompletionGapHighlights();
        return;
    }

    let message = _t('Highlighted %(count)s missing item(s).').replace('%(count)s', String(highlightedCount));
    showFlash(message, 'info');
}

async function fetchCompletionGaps(aesId) {
    const fetchFn = (window.getCsrfAwareFetch && window.getCsrfAwareFetch()) || fetch;
    const useDebug = window.location.search.includes('debug_completion=1')
        || window.localStorage.getItem('ifrc_debug_completion') === '1';
    const query = collectHiddenCompletionQueryString(useDebug ? { debug: '1' } : {});
    const url = `/api/forms/assignment/${aesId}/completion-gaps${query}`;
    const response = await fetchFn(url, {
        headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
        credentials: 'same-origin',
    });
    if (window.responseAsResult) {
        const result = await window.responseAsResult(response);
        if (!result.ok) {
            throw new Error(result.data?.error || `HTTP ${result.status}`);
        }
        return result.data;
    }
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }
    const ct = response.headers.get('Content-Type') || '';
    if (!ct.includes('application/json')) {
        throw new Error(`HTTP ${response.status}: non-JSON response`);
    }
    return response.json();
}

function logCompletionGapDiagnostics(payload) {
    const matrixItems = (payload?.missing_items || []).filter((i) => i.item_type === 'matrix');
    if (!matrixItems.length) {
        return;
    }
    const rule = payload?.matrix_rule === 'one_cell_enough'
        ? 'Matrix counts as complete when any one cell has data (not all cells).'
        : null;
    // eslint-disable-next-line no-console
    console.group('[completion-gaps] matrix items marked missing');
    if (rule) console.info(rule);
    matrixItems.forEach((item) => {
        console.info(
            `form_item_id=${item.form_item_id} "${item.label}" hint=${item.fill_hint || 'unknown'}`,
            item.fill_debug || '(enable debug: add ?debug_completion=1 to URL or localStorage.ifrc_debug_completion=1)',
        );
    });
    // eslint-disable-next-line no-console
    console.groupEnd();
}

async function toggleCompletionGapHighlights() {
    const btn = getGapButton();
    if (!btn || gapsLoading || btn.disabled) {
        return;
    }

    if (gapsActive) {
        clearCompletionGapHighlights();
        showFlash(_t('Highlights cleared.'), 'info');
        return;
    }

    const aesId = btn.dataset.aesId;
    if (!aesId) {
        return;
    }

    const cachedRate = parseFloat(btn.dataset.completionRate || '');
    if (Number.isFinite(cachedRate) && cachedRate >= 100) {
        showFlash(_t('All countable items are complete.'), 'success');
        return;
    }

    gapsLoading = true;
    btn.setAttribute('aria-busy', 'true');
    btn.disabled = true;

    try {
        const payload = await fetchCompletionGaps(aesId);
        lastGapsPayload = payload;
        logCompletionGapDiagnostics(payload);
        // Do NOT call applyCompletionRate here — the gaps rate is computed with
        // relevance-hidden fields excluded, which diverges from the dashboard rate.
        // The header is the sole responsibility of refreshVisibleCompletionRate.
        applyCompletionGapHighlights(payload);
    } catch (_) {
        showFlash(_t('Could not load missing items. Please try again.'), 'error');
        updateGapButtonState(cachedRate);
    } finally {
        gapsLoading = false;
        btn.setAttribute('aria-busy', 'false');
        if (!gapsActive) {
            updateGapButtonState(parseFloat(btn.dataset.completionRate || ''));
        }
    }
}

/**
 * Fetch and display the completion rate from the server (matches the dashboard).
 *
 * This is the ONLY function that should update the header completion-rate display.
 * It calls /completion-rate without hidden-field params so the result is identical
 * to what AssignmentCompletionService.compute_for_assignment returns for the
 * dashboard — all template items, no relevance-visibility filtering.
 *
 * Called on page load (main.js) and on ifrc:relevance-settled (debounced).
 * After a save, the header is updated from the save payload instead — a
 * relevance refetch in that window would race and can show a stale cached rate.
 * The completion-gaps callback must NOT call applyCompletionRate because the
 * gaps endpoint computes the rate with hidden fields excluded, which would
 * diverge from the dashboard value.
 *
 * @param {string|number} aesId
 */
export async function refreshVisibleCompletionRate(aesId) {
    const fetchFn = (window.getCsrfAwareFetch && window.getCsrfAwareFetch()) || fetch;
    const response = await fetchFn(`/api/forms/assignment/${aesId}/completion-rate`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
        credentials: 'same-origin',
        cache: 'no-store',
    });
    let data;
    if (window.responseAsResult) {
        const result = await window.responseAsResult(response);
        if (!result.ok) {
            throw new Error(result.data?.error || `HTTP ${result.status}`);
        }
        data = result.data;
    } else {
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const ct = response.headers.get('Content-Type') || '';
        if (!ct.includes('application/json')) {
            throw new Error(`HTTP ${response.status}: non-JSON response`);
        }
        data = await response.json();
    }
    const rate = coerceCompletionRate(data?.completion_rate);
    if (rate !== null) {
        applyCompletionRate(rate);
    }
    return data;
}

/**
 * Recompute completion when relevance conditions show or hide fields.
 * @param {string|number} aesId
 */
export function initCompletionRateRefresh(aesId) {
    if (!aesId || document.body.dataset.completionRateRefreshInit === '1') {
        return;
    }
    document.body.dataset.completionRateRefreshInit = '1';

    const debouncedRefresh = () => {
        if (Date.now() < suppressRefreshUntil) {
            return;
        }
        cancelPendingCompletionRefresh();
        refreshCompletionTimer = setTimeout(() => {
            if (Date.now() < suppressRefreshUntil) {
                return;
            }
            refreshVisibleCompletionRate(aesId).catch(() => { /* ignore */ });
        }, 300);
    };

    refreshAbort?.abort();
    refreshAbort = new AbortController();
    document.addEventListener('ifrc:relevance-settled', debouncedRefresh, {
        signal: refreshAbort.signal,
    });
}

/** Remove the relevance-settled listener and pending refresh (tests / teardown). */
export function teardownCompletionRateRefresh() {
    refreshAbort?.abort();
    refreshAbort = null;
    cancelPendingCompletionRefresh();
    suppressRefreshUntil = 0;
    try {
        delete document.body.dataset.completionRateRefreshInit;
        delete document.body.dataset.completionRateFromSave;
    } catch (_) { /* no-op */ }
}

/**
 * Wire the "Show me what I missed" button.
 */
export function initCompletionGapHighlight() {
    const btn = getGapButton();
    if (!btn || !btn.dataset.aesId || btn.dataset.gapHighlightInit === '1') {
        return;
    }
    btn.dataset.gapHighlightInit = '1';
    btn.setAttribute('aria-pressed', 'false');

    btn.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        toggleCompletionGapHighlights();
    });
}

/**
 * Apply completion rate and/or section statuses from bootstrap or save response payloads.
 * @param {{ completion_rate?: number, section_statuses?: Record<string, string> }} data
 */
export function applyEntryFormProgress(data) {
    if (!data || typeof data !== 'object') {
        return;
    }
    const rate = coerceCompletionRate(data.completion_rate ?? data.data?.completion_rate);
    if (rate !== null) {
        applyCompletionRate(rate);
        markSaveAppliedProgress();
    }
    if (data.section_statuses) {
        updateSectionStatusIcons(data.section_statuses);
    }
    if (gapsActive) {
        clearCompletionGapHighlights();
        lastGapsPayload = null;
    }
}
