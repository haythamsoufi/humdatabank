import { debugLog, debugWarn } from './debug.js';

const MODULE_NAME = 'ai-opinions';
const AI_VALIDATION_SOURCES_STORAGE_KEY = 'ifrc_ai_validation_sources_v1';

function escapeHtml(input) {
    const s = String(input ?? '');
    return s
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function normalizeText(value) {
    if (value === null || value === undefined) return '';
    const s = String(value).trim();
    if (!s) return '';
    const lo = s.toLowerCase();
    if (lo === 'none' || lo === 'null' || lo === 'undefined') return '';
    return s;
}

function verdictUi(validation) {
    const status = String(validation?.status || '').toLowerCase();
    const verdict = String(validation?.verdict || 'uncertain').toLowerCase();
    const conf = Number(validation?.confidence);
    const confText = Number.isFinite(conf) ? ` (${Math.round(conf * 100)}%)` : '';

    if (status === 'failed') {
        return {
            label: `Failed${confText}`,
            badgeClass: 'bg-red-100 text-red-800',
        };
    }
    if (verdict === 'good') {
        return {
            label: `Good${confText}`,
            badgeClass: 'bg-green-100 text-green-800',
        };
    }
    if (verdict === 'discrepancy') {
        return {
            label: `Discrepancy${confText}`,
            badgeClass: 'bg-orange-100 text-orange-800',
        };
    }
    return {
        label: `Uncertain${confText}`,
        badgeClass: 'bg-gray-100 text-gray-800',
    };
}

function renderOpinionHtml(validation) {
    const summary = normalizeText(validation?.opinion_summary || validation?.opinion_text);
    const details = normalizeText(validation?.opinion_details);
    const decision = normalizeText(validation?.decision);
    const basis = Array.isArray(validation?.opinion_basis) ? validation.opinion_basis.filter(Boolean) : [];
    const sources = Array.isArray(validation?.opinion_sources) ? validation.opinion_sources : [];
    const suggestion = (validation && typeof validation.suggestion === 'object') ? validation.suggestion : null;
    const suggestedValue = suggestion && suggestion.value !== undefined ? suggestion.value : null;
    const suggestedDisagg = suggestion && suggestion.disagg_data !== undefined ? suggestion.disagg_data : null;
    const suggestionReason = normalizeText(suggestion?.reason);
    const hasSuggestion = (suggestedValue !== null && suggestedValue !== undefined) || (suggestedDisagg !== null && suggestedDisagg !== undefined);
    if (!summary && !details && !decision && basis.length === 0 && sources.length === 0 && !hasSuggestion) return '';

    const ui = verdictUi(validation);
    const hasExpandable = !!(details || decision || basis.length || sources.length);
    const encodedSuggestion = hasSuggestion ? encodeURIComponent(JSON.stringify(suggestion || {})) : '';

    return `
        <div class="mt-2 p-3 rounded border border-purple-200 bg-purple-50 ai-item-opinion-block" data-ai-opinion="1">
            <div class="text-xs font-semibold text-purple-900 mb-1">AI opinion</div>
            <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${ui.badgeClass}">
                ${escapeHtml(ui.label)}
            </span>
            ${summary ? `<div class="text-xs text-gray-700 mt-1">${escapeHtml(summary)}</div>` : ''}
            ${hasExpandable ? `
                <details class="mt-1 text-xs">
                    <summary class="cursor-pointer text-purple-700 hover:text-purple-800 font-medium">
                        More details
                    </summary>
                    <div class="mt-2 pl-2 border-l-2 border-purple-200 space-y-1 text-gray-700">
                        ${details ? `<div><span class="font-semibold text-gray-800">Detailed analysis:</span> ${escapeHtml(details)}</div>` : ''}
                        ${decision ? `<div><span class="font-semibold text-gray-800">Decision:</span> <span class="font-mono text-purple-800">${escapeHtml(decision)}</span></div>` : ''}
                        ${basis.length ? `<div><span class="font-semibold text-gray-800">Based on:</span> ${basis.map((b) => `<span class="inline-block mr-1 mt-0.5 px-2 py-0.5 rounded-full bg-purple-100 border border-purple-200 text-purple-800">${escapeHtml(String(b))}</span>`).join('')}</div>` : ''}
                        ${sources.length ? `<div><span class="font-semibold text-gray-800">Sources:</span> ${escapeHtml(String(sources.length))}</div>` : ''}
                    </div>
                </details>
            ` : ''}
            ${hasSuggestion ? `
                <div class="mt-2 text-xs bg-blue-50 border border-blue-200 rounded p-2">
                    ${suggestedValue !== null && suggestedValue !== undefined ? `
                        <div class="font-semibold text-blue-800">Suggested value: <span class="font-mono">${escapeHtml(String(suggestedValue))}</span></div>
                    ` : ''}
                    ${suggestedDisagg !== null && suggestedDisagg !== undefined ? `
                        <div class="font-semibold text-blue-800 mt-1">Suggested disaggregation available</div>
                    ` : ''}
                    ${suggestionReason ? `<div class="text-blue-800/80 mt-1">${escapeHtml(suggestionReason)}</div>` : ''}
                    <div class="mt-2">
                        <button
                            type="button"
                            class="apply-ai-suggestion-btn px-2 py-1 bg-blue-600 text-white hover:bg-blue-700 rounded text-xs"
                            data-suggestion="${escapeHtml(encodedSuggestion)}">
                            Apply suggestion to field
                        </button>
                    </div>
                </div>
            ` : ''}
        </div>
    `;
}

function upsertOpinionBlock(fieldBlock, html) {
    if (!fieldBlock) return;
    const existing = fieldBlock.querySelector('.ai-item-opinion-block[data-ai-opinion="1"]');
    if (!html) {
        if (existing) existing.remove();
        return;
    }

    // Defense-in-depth: html is expected to come from renderOpinionHtml
    // (which escapes all dynamic values), but guard against misuse.
    const safe = (window.SafeDom && window.SafeDom.sanitizeHtml)
        ? window.SafeDom.sanitizeHtml(html)
        : html;

    if (existing) {
        existing.outerHTML = safe;
        return;
    }

    fieldBlock.insertAdjacentHTML('beforeend', safe);
}

const AI_OPINION_PROCESSING_CLASS = 'ai-opinion-processing';
const AI_OPINION_BADGE_CLASS = 'ai-opinion-processing-badge';
const AI_OPINION_SPARK_CLASS = 'ai-opinion-spark';
const AI_OPINION_SPARK_TRACK_CLASS = 'ai-opinion-spark-track';
const AI_OPINION_TRAIL_DOT_CLASS = 'ai-opinion-trail-dot';

function getFormItemBlock(itemId) {
    return document.querySelector(`.form-item-block[data-item-id="${String(itemId)}"]`);
}

function removeProcessingUi(block) {
    if (!block) return;
    block.querySelector(`.${AI_OPINION_SPARK_TRACK_CLASS}`)?.remove();
    const next = block.nextElementSibling;
    if (next?.classList?.contains(AI_OPINION_BADGE_CLASS)) next.remove();
}

function highlightFormItem(itemId) {
    document.querySelectorAll(`.form-item-block.${AI_OPINION_PROCESSING_CLASS}`).forEach((el) => {
        removeProcessingUi(el);
        el.classList.remove(AI_OPINION_PROCESSING_CLASS);
    });
    const block = getFormItemBlock(itemId);
    if (block) {
        block.classList.add(AI_OPINION_PROCESSING_CLASS);
        const track = document.createElement('div');
        track.className = AI_OPINION_SPARK_TRACK_CLASS;
        track.setAttribute('aria-hidden', 'true');
        for (let i = 0; i < 6; i++) {
            const dot = document.createElement('div');
            dot.className = AI_OPINION_TRAIL_DOT_CLASS;
            track.appendChild(dot);
        }
        const spark = document.createElement('div');
        spark.className = AI_OPINION_SPARK_CLASS;
        track.appendChild(spark);
        block.appendChild(track);
        const badge = document.createElement('div');
        badge.className = AI_OPINION_BADGE_CLASS;
        badge.setAttribute('role', 'status');
        badge.setAttribute('aria-live', 'polite');
        badge.innerHTML = '<i class="fas fa-robot"></i> AI is processing this item';
        block.insertAdjacentElement('afterend', badge);
        block.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

function unhighlightFormItem(itemId) {
    const block = getFormItemBlock(itemId);
    if (block) {
        removeProcessingUi(block);
        block.classList.remove(AI_OPINION_PROCESSING_CLASS);
    }
}

function unhighlightAllFormItems() {
    document.querySelectorAll(`.form-item-block.${AI_OPINION_PROCESSING_CLASS}`).forEach((el) => {
        removeProcessingUi(el);
        el.classList.remove(AI_OPINION_PROCESSING_CLASS);
    });
}

function applyOpinionForItem(itemId, validation) {
    const block = getFormItemBlock(itemId);
    if (!block) return;
    upsertOpinionBlock(block, renderOpinionHtml(validation));
}

function applyOpinions(opinionsByFormItemId) {
    if (!opinionsByFormItemId || typeof opinionsByFormItemId !== 'object') return;
    for (const [itemId, validation] of Object.entries(opinionsByFormItemId)) {
        applyOpinionForItem(itemId, validation);
    }
}

function getStoredSources() {
    const fallback = ['historical', 'system_documents'];
    try {
        const raw = localStorage.getItem(AI_VALIDATION_SOURCES_STORAGE_KEY);
        if (!raw) return fallback;
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed)) return fallback;
        const allowed = new Set(['historical', 'system_documents', 'upr_documents']);
        const normalized = parsed
            .map((v) => String(v || '').trim())
            .filter((v, idx, arr) => !!v && allowed.has(v) && arr.indexOf(v) === idx);
        return normalized.length ? normalized : fallback;
    } catch {
        return fallback;
    }
}

function collectHiddenIds(formId) {
    const root = document.getElementById(formId) || document;
    const hiddenSections = Array
        .from(root.querySelectorAll('.relevance-hidden[id^="section-container-"]'))
        .map((el) => (el.id || '').replace('section-container-', ''))
        .filter((id) => /^\d+$/.test(id))
        .map((id) => Number(id));

    const hiddenFields = Array
        .from(root.querySelectorAll('.relevance-hidden[data-item-id]'))
        .filter((el) => !(el.id && el.id.startsWith('section-container-')))
        .map((el) => String(el.getAttribute('data-item-id') || '').trim())
        .filter((id) => /^\d+$/.test(id))
        .map((id) => Number(id));

    return { hiddenSections, hiddenFields };
}

function dispatchInputEvents(el) {
    if (!el) return;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
}

function applyScalarToBlock(block, value) {
    if (!block || value === null || value === undefined) return false;
    const scalarValue = String(value);

    const selectEl = block.querySelector('select:not([disabled])');
    if (selectEl) {
        let matched = false;
        for (const opt of Array.from(selectEl.options || [])) {
            if (String(opt.value) === scalarValue || String(opt.textContent || '').trim() === scalarValue) {
                selectEl.value = String(opt.value);
                matched = true;
                break;
            }
        }
        if (matched) {
            dispatchInputEvents(selectEl);
            return true;
        }
    }

    const yesNo = String(value).trim().toLowerCase();
    const yesNoBoxes = Array.from(block.querySelectorAll('input[type="checkbox"][name$="_standard_value"]:not([disabled])'));
    if (yesNoBoxes.length >= 2 && (yesNo === 'yes' || yesNo === 'no')) {
        yesNoBoxes.forEach((cb) => {
            cb.checked = String(cb.value || '').trim().toLowerCase() === yesNo;
            dispatchInputEvents(cb);
        });
        return true;
    }

    const textInput = block.querySelector('input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([disabled])');
    if (textInput) {
        textInput.value = scalarValue;
        dispatchInputEvents(textInput);
        return true;
    }

    const textarea = block.querySelector('textarea:not([disabled])');
    if (textarea) {
        textarea.value = scalarValue;
        dispatchInputEvents(textarea);
        return true;
    }

    return false;
}

function applyDisaggToBlock(block, disaggData) {
    if (!block || !disaggData || typeof disaggData !== 'object') return false;

    // Matrix/plugin style payload: write hidden JSON field directly when present.
    if (disaggData && !disaggData.mode && !disaggData.values) {
        const itemId = String(block.getAttribute('data-item-id') || '').trim();
        const hidden = itemId ? block.querySelector(`input[type="hidden"][name="field_value[${itemId}]"]`) : null;
        if (hidden) {
            hidden.value = JSON.stringify(disaggData);
            dispatchInputEvents(hidden);
            return true;
        }
    }

    const sampleNamedInput = block.querySelector('input[name], textarea[name], select[name]');
    const sampleName = sampleNamedInput ? String(sampleNamedInput.getAttribute('name') || '') : '';
    const m = sampleName.match(/^(indicator|dynamic|question)_(\d+)_/);
    if (!m) return false;
    const base = `${m[1]}_${m[2]}`;
    const mode = String(disaggData.mode || '').trim();
    const values = (disaggData.values && typeof disaggData.values === 'object') ? disaggData.values : null;
    if (!mode || !values) return false;

    const modeRadio = block.querySelector(`input[type="radio"][name="${base}_reporting_mode"][value="${mode}"]:not([disabled])`);
    if (modeRadio) {
        modeRadio.checked = true;
        dispatchInputEvents(modeRadio);
    }

    let appliedAny = false;
    const trySetByName = (name, val) => {
        const el = block.querySelector(`[name="${name}"]:not([disabled])`);
        if (!el) return false;
        if (el.tagName === 'SELECT') {
            el.value = String(val ?? '');
        } else {
            el.value = String(val ?? '');
        }
        dispatchInputEvents(el);
        return true;
    };

    if (Object.prototype.hasOwnProperty.call(values, 'total')) {
        appliedAny = trySetByName(`${base}_total_value`, values.total) || appliedAny;
    }
    if (Object.prototype.hasOwnProperty.call(values, 'indirect')) {
        appliedAny = trySetByName(`${base}_indirect_reach`, values.indirect) || appliedAny;
    }

    for (const [key, rawVal] of Object.entries(values)) {
        if (key === 'total' || key === 'indirect') continue;
        appliedAny = trySetByName(`${base}_${mode}_${key}`, rawVal) || appliedAny;
        appliedAny = trySetByName(`${base}_${key}`, rawVal) || appliedAny;
    }

    return appliedAny;
}

function markSuggestionApplied(button) {
    if (!button) return;
    button.disabled = true;
    button.textContent = 'Applied';
    button.classList.remove('bg-blue-600', 'hover:bg-blue-700');
    button.classList.add('bg-green-600');
}

export function initAiOpinions() {
    const button = document.getElementById('fab-run-ai-opinions-btn')
        || document.getElementById('run-ai-opinions-btn');
    if (!button) return;

    const anchor = document.querySelector('[data-aes-id]');
    const aesId = anchor ? anchor.getAttribute('data-aes-id') : null;
    if (!aesId) return;

    const formId = 'focalDataEntryForm';
    const originalHtml = button.innerHTML;
    let inFlight = false;
    let currentEventSource = null;

    const stopRun = () => {
        if (!inFlight) return;
        if (currentEventSource) {
            try { currentEventSource.close(); } catch (_) { /* no-op */ }
            currentEventSource = null;
        }
        unhighlightAllFormItems();
        const banner = createProgressBanner();
        if (banner && banner.exists()) {
            banner.setCancelVisible(false);
            banner.hide();
        }
        inFlight = false;
        setButtonBusy(false);
    };

    const createProgressBanner = () => {
        if (!window.FloatingProgressBanner || typeof window.FloatingProgressBanner.fromIds !== 'function') return null;
        return window.FloatingProgressBanner.fromIds({
            bannerId: 'ai-opinions-progress-banner',
            titleId: 'ai-opinions-progress-title',
            detailId: 'ai-opinions-progress-detail',
            percentId: 'ai-opinions-progress-percent',
            barId: 'ai-opinions-progress-bar',
            spinnerId: 'ai-opinions-progress-spinner',
            cancelWrapId: 'ai-opinions-cancel-wrap',
            cancelBtnId: 'ai-opinions-stop-btn',
        });
    };
    const progressBanner = createProgressBanner();

    const stopBtn = document.getElementById('ai-opinions-stop-btn');
    if (stopBtn) stopBtn.addEventListener('click', stopRun);

    const setButtonBusy = (busy) => {
        button.disabled = !!busy;
        if (!busy) {
            button.innerHTML = originalHtml;
            return;
        }
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Running AI opinions...</span>';
    };

    const closeCurrentStream = () => {
        if (currentEventSource) {
            try { currentEventSource.close(); } catch (_) { /* no-op */ }
            currentEventSource = null;
        }
    };

    const runAndShow = async () => {
        if (inFlight) return;
        inFlight = true;
        setButtonBusy(true);
        try {
            const hidden = collectHiddenIds(formId);
            const params = new URLSearchParams();
            params.set('run_mode', 'missing');
            params.set('include_non_reported', '1');
            if (hidden.hiddenFields.length) params.set('hidden_fields', hidden.hiddenFields.join(','));
            if (hidden.hiddenSections.length) params.set('hidden_sections', hidden.hiddenSections.join(','));
            params.set('ai_sources', getStoredSources().join(','));

            closeCurrentStream();
            const es = new EventSource(`/forms/assignment_status/${encodeURIComponent(String(aesId))}/validation_summary/opinions/events?${params.toString()}`, { withCredentials: true });
            currentEventSource = es;

            let completed = 0;
            let total = 0;
            const updateProgress = (detailText) => {
                const pct = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
                if (progressBanner && progressBanner.exists()) {
                    progressBanner.update({
                        title: 'Running AI opinions...',
                        detail: detailText || `Processed ${completed}/${total || 0} items`,
                        progress: pct,
                        showPercent: true,
                        percentText: `${pct}%`,
                        showSpinner: true,
                    });
                }
            };

            if (progressBanner && progressBanner.exists()) {
                progressBanner.show();
                progressBanner.setCancelVisible(true);
                progressBanner.update({
                    title: 'Running AI opinions...',
                    detail: 'Preparing request...',
                    progress: 0,
                    showPercent: true,
                    percentText: '0%',
                    showSpinner: true,
                });
            }

            es.addEventListener('init', (ev) => {
                try {
                    const data = JSON.parse(ev.data || '{}');
                    total = Number(data.total_items || 0);
                    completed = Number(data.completed || 0);
                    applyOpinions(data.existingOpinionsByFormItemId || {});
                    updateProgress(`Found ${completed}/${total} existing opinions. Running missing...`);
                } catch (_) { /* no-op */ }
            });

            es.addEventListener('started', (ev) => {
                try {
                    const data = JSON.parse(ev.data || '{}');
                    const fi = data.form_item_id ? String(data.form_item_id) : '';
                    if (fi) highlightFormItem(fi);
                    updateProgress(fi ? `Running item ${fi}...` : 'Running...');
                } catch (_) { /* no-op */ }
            });

            es.addEventListener('item', (ev) => {
                try {
                    const data = JSON.parse(ev.data || '{}');
                    const itemId = data.form_item_id ? String(data.form_item_id) : '';
                    if (itemId) {
                        unhighlightFormItem(itemId);
                        applyOpinionForItem(itemId, data.validation || {});
                    }
                    completed = Number(data.completed || completed);
                    total = Number(data.total_items || total);
                    updateProgress(`Processed ${completed}/${total} items`);
                } catch (_) { /* no-op */ }
            });

            es.addEventListener('done', (ev) => {
                try {
                    unhighlightAllFormItems();
                    const data = JSON.parse(ev.data || '{}');
                    applyOpinions(data.opinionsByFormItemId || {});
                    completed = Number(data.completed || completed);
                    total = Number(data.total_items || total);
                    if (progressBanner && progressBanner.exists()) {
                        progressBanner.update({
                            title: 'AI opinions ready',
                            detail: `Processed ${completed}/${total || 0} items`,
                            progress: 100,
                            showPercent: true,
                            percentText: '100%',
                            showSpinner: false,
                        });
                        setTimeout(() => progressBanner.hide(), 1600);
                    }
                    closeCurrentStream();
                    button.innerHTML = '<i class="fas fa-sync-alt"></i><span>Refresh AI opinions</span>';
                    button.disabled = false;
                    inFlight = false;
                } catch (_) {
                    closeCurrentStream();
                    inFlight = false;
                    setButtonBusy(false);
                }
            });

            es.addEventListener('error', () => {
                unhighlightAllFormItems();
                closeCurrentStream();
                if (progressBanner && progressBanner.exists()) {
                    progressBanner.update({
                        title: 'AI opinions failed',
                        detail: 'Connection lost while running opinions.',
                        progress: 100,
                        showPercent: false,
                        showSpinner: false,
                    });
                    setTimeout(() => progressBanner.hide(), 2200);
                }
                if (window.showAlert) {
                    window.showAlert('Failed to run AI opinions. Please try again.', 'error');
                }
                inFlight = false;
                setButtonBusy(false);
            });
        } catch (error) {
            debugWarn(MODULE_NAME, 'Failed running AI opinions', error);
            if (window.showAlert) {
                window.showAlert('Failed to run AI opinions. Please try again.', 'error');
            }
            button.innerHTML = originalHtml;
            inFlight = false;
            setButtonBusy(false);
        }
    };

    button.addEventListener('click', runAndShow);

    document.addEventListener('click', (event) => {
        const target = event?.target;
        const applyBtn = target && target.closest ? target.closest('.apply-ai-suggestion-btn') : null;
        if (!applyBtn) return;
        event.preventDefault();

        const block = applyBtn.closest('.form-item-block[data-item-id]');
        if (!block) return;

        let suggestion = {};
        try {
            suggestion = JSON.parse(decodeURIComponent(String(applyBtn.getAttribute('data-suggestion') || '')));
        } catch (error) {
            debugWarn(MODULE_NAME, 'Invalid suggestion payload', error);
            return;
        }

        const didScalar = applyScalarToBlock(block, suggestion?.value);
        const didDisagg = applyDisaggToBlock(block, suggestion?.disagg_data);
        if (didScalar || didDisagg) {
            markSuggestionApplied(applyBtn);
            if (window.showAlert) window.showAlert('Suggestion applied in the form. Save if you want to keep it.', 'success');
        } else if (window.showAlert) {
            window.showAlert('Could not map this suggestion to an editable field automatically.', 'warning');
        }
    });

    debugLog(MODULE_NAME, 'AI opinion runner initialized');
}

