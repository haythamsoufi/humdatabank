import { debugLog, debugWarn } from './debug.js';

const MODULE_NAME = 'validation-summary-banner';

// Same wording as the real "stage" events validation_summary_overview_stream sends
// as each phase of the actual work begins (reading the assignment's entries →
// checking the deterministic UPR figures/funding/emergencies pack → only when an
// LLM call will really happen, writing the summary). Used as the phrase shown the
// instant the button is clicked (before the stream connects) and as a fallback
// cycle if real progress stalls for a bit — see startLoadingAnimation().
const DEFAULT_LOADING_PHRASES = [
    'Reading the assignment…',
    'Checking the figures, funding & emergencies…',
    'Putting the summary together…',
];

// If no real stage/result event arrives for this long, start gently cycling the
// remaining phrases so the animation never looks frozen. Real events always win —
// this is purely a fallback for a slow step (typically the LLM call) that already
// reported its real stage but is taking a while.
const STAGE_STALL_MS = 4000;
const STALL_CYCLE_MS = 1800;

function escapeHtml(input) {
    return String(input ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function collectHiddenIds(formId) {
    const root = document.getElementById(formId) || document;
    const hiddenSections = Array
        .from(root.querySelectorAll('.relevance-hidden[id^="section-container-"]'))
        .map((el) => (el.id || '').replace('section-container-', ''))
        .filter((id) => /^\d+$/.test(id));
    const hiddenFields = Array
        .from(root.querySelectorAll('.relevance-hidden[data-item-id]'))
        .filter((el) => !(el.id && el.id.startsWith('section-container-')))
        .map((el) => String(el.getAttribute('data-item-id') || '').trim())
        .filter((id) => /^\d+$/.test(id));
    return { hiddenSections, hiddenFields };
}

function labelFor(banner, key, fallback) {
    return banner.getAttribute(`data-i18n-${key}`) || fallback;
}

function loadingPhrasesFor(banner) {
    try {
        const raw = banner.getAttribute('data-i18n-loading-phrases');
        const parsed = raw ? JSON.parse(raw) : null;
        return Array.isArray(parsed) && parsed.length ? parsed : DEFAULT_LOADING_PHRASES;
    } catch {
        return DEFAULT_LOADING_PHRASES;
    }
}

function countChip(label, value, tone) {
    const tones = {
        good: 'bg-green-100 text-green-800',
        discrepancy: 'bg-orange-100 text-orange-800',
        uncertain: 'bg-gray-100 text-gray-800',
        failed: 'bg-red-100 text-red-800',
        missing: 'bg-slate-100 text-slate-700',
    };
    return `<span class="inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold ${tones[tone] || tones.missing}">
        ${escapeHtml(label)} <strong>${escapeHtml(String(value ?? 0))}</strong>
    </span>`;
}

function issueNumberClass(verdict) {
    if (verdict === 'discrepancy') return 'bg-orange-100 text-orange-800';
    if (verdict === 'failed') return 'bg-red-100 text-red-800';
    return 'bg-amber-100 text-amber-800';
}

function scrollToField(itemId) {
    if (!itemId) return;
    const block = document.querySelector(`.form-item-block[data-item-id="${itemId}"]`);
    if (!block) return;
    block.scrollIntoView({ behavior: 'smooth', block: 'center' });
    block.classList.add('validation-summary-flash');
    window.setTimeout(() => block.classList.remove('validation-summary-flash'), 1600);
}

export function initValidationSummaryBanner() {
    const button = document.getElementById('fab-validation-summary-btn');
    const banner = document.getElementById('validation-summary-banner');
    if (!button || !banner) return;

    const headlineEl = document.getElementById('validation-summary-headline');
    const countsEl = document.getElementById('validation-summary-counts');
    const figuresEl = document.getElementById('validation-summary-figures');
    const narrativeEl = document.getElementById('validation-summary-narrative');
    const goodWrap = document.getElementById('validation-summary-good-wrap');
    const goodEl = document.getElementById('validation-summary-good');
    const issuesHeading = document.getElementById('validation-summary-issues-heading');
    const issuesEl = document.getElementById('validation-summary-issues');
    const commentEl = document.getElementById('validation-summary-comment');
    const detailsLink = document.getElementById('validation-summary-details-link');
    const dismissBtn = document.getElementById('validation-summary-dismiss');
    const originalHtml = button.innerHTML;
    const loadingPhrases = loadingPhrasesFor(banner);
    let inFlight = false;
    let stallTimer = null;
    let lastStageAt = 0;
    let stallIndex = 0;

    const hideBanner = () => {
        banner.classList.add('hidden');
    };

    if (dismissBtn) {
        dismissBtn.addEventListener('click', hideBanner);
    }

    const setBusy = (busy) => {
        button.disabled = !!busy;
        if (!busy) {
            button.innerHTML = originalHtml;
            return;
        }
        button.innerHTML = '<span class="fab-hover-pill-icon"><i class="fas fa-spinner fa-spin"></i></span><span class="fab-hover-pill-label">…</span>';
    };

    const setLoadingPhrase = (phrase) => {
        if (!headlineEl) return;
        headlineEl.innerHTML = `<span class="validation-summary-shimmer">${escapeHtml(phrase)}</span>`
            + '<span class="validation-summary-dots" aria-hidden="true"><i></i><i></i><i></i></span>';
    };

    const stopLoadingAnimation = () => {
        if (stallTimer) {
            window.clearInterval(stallTimer);
            stallTimer = null;
        }
        if (headlineEl) headlineEl.classList.remove('validation-summary-loading-active');
    };

    // Shimmer/dots animation whose text is driven by REAL backend "stage" events
    // (see the EventSource wiring in the click handler below) rather than a blind
    // timer. The very first phrase shown (before the stream connects) matches the
    // real first stage's label, so it's honest from frame one. If real progress
    // stalls for a bit — typically because the LLM call reported as "summary" is
    // still running — we gently cycle the remaining phrases rather than freezing;
    // any real stage/result event always takes over immediately.
    const startLoadingAnimation = () => {
        if (!headlineEl) return;
        stopLoadingAnimation();
        headlineEl.classList.add('validation-summary-loading-active');
        stallIndex = 0;
        lastStageAt = Date.now();
        setLoadingPhrase(loadingPhrases[0]);
        stallTimer = window.setInterval(() => {
            if (Date.now() - lastStageAt < STAGE_STALL_MS) return;
            stallIndex += 1;
            setLoadingPhrase(loadingPhrases[stallIndex % loadingPhrases.length]);
            lastStageAt = Date.now();
        }, STALL_CYCLE_MS);
    };

    // Called from a real "stage" SSE event — always takes priority over the fallback cycle.
    const onRealStage = (label) => {
        if (!label) return;
        stallIndex = 0;
        lastStageAt = Date.now();
        setLoadingPhrase(label);
    };

    const showError = (message) => {
        stopLoadingAnimation();
        banner.classList.remove('hidden');
        if (headlineEl) headlineEl.textContent = message || labelFor(banner, 'error', 'Could not load the validation summary.');
        if (countsEl) countsEl.replaceChildren();
        if (figuresEl) {
            figuresEl.replaceChildren();
            figuresEl.classList.add('hidden');
        }
        if (narrativeEl) {
            narrativeEl.textContent = '';
            narrativeEl.classList.add('hidden');
        }
        if (goodWrap) {
            goodWrap.classList.add('hidden');
            goodWrap.removeAttribute('open');
        }
        if (goodEl) goodEl.replaceChildren();
        if (issuesHeading) issuesHeading.classList.add('hidden');
        if (issuesEl) issuesEl.replaceChildren();
        if (commentEl) {
            commentEl.textContent = '';
            commentEl.classList.add('hidden');
        }
        banner.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };

    const render = (payload, detailsUrl) => {
        stopLoadingAnimation();
        const counts = payload.counts || {};
        if (headlineEl) headlineEl.textContent = payload.headline || '';
        if (countsEl) {
            countsEl.innerHTML = [
                countChip(labelFor(banner, 'good', 'Good'), counts.good, 'good'),
                countChip(labelFor(banner, 'discrepancy', 'Discrepancy'), counts.discrepancy, 'discrepancy'),
                countChip(labelFor(banner, 'uncertain', 'Uncertain'), counts.uncertain, 'uncertain'),
                countChip(labelFor(banner, 'failed', 'Failed'), counts.failed, 'failed'),
                countChip(labelFor(banner, 'not-run', 'Not run'), counts.missing, 'missing'),
            ].join('');
        }
        const figures = Array.isArray(payload.overview_figures) ? payload.overview_figures : [];
        if (figuresEl) {
            if (figures.length) {
                figuresEl.classList.remove('hidden');
                figuresEl.innerHTML = figures.map((row) => {
                    const label = row && row.label ? row.label : '';
                    const value = row && row.value ? row.value : '';
                    return `<div class="rounded-md border border-gray-200 bg-gray-50 px-3 py-2">
                        <dt class="text-xs font-semibold uppercase tracking-wide text-gray-500">${escapeHtml(label)}</dt>
                        <dd class="text-sm font-medium text-gray-900 mt-0.5">${escapeHtml(value)}</dd>
                    </div>`;
                }).join('');
            } else {
                figuresEl.classList.add('hidden');
                figuresEl.replaceChildren();
            }
        }
        const narrative = String(payload.narrative || '').trim();
        if (narrativeEl) {
            if (narrative && narrative !== String(payload.headline || '').trim()) {
                narrativeEl.textContent = narrative;
                narrativeEl.classList.remove('hidden');
            } else {
                narrativeEl.textContent = '';
                narrativeEl.classList.add('hidden');
            }
        }
        if (issuesEl) {
            const issues = Array.isArray(payload.issues) ? payload.issues : [];
            if (issuesHeading) {
                if (issues.length) {
                    issuesHeading.textContent = labelFor(banner, 'whats-not', 'Needs attention');
                    issuesHeading.classList.remove('hidden');
                } else {
                    issuesHeading.classList.add('hidden');
                }
            }
            if (!issues.length) {
                issuesEl.innerHTML = `<li class="text-sm text-gray-500">${escapeHtml(labelFor(banner, 'no-issues', 'No issues to highlight.'))}</li>`;
            } else {
                // Numbered list; the label/summary text is clickable when it maps to a
                // field on the form (scrolls + flashes that field), plain text otherwise.
                issuesEl.innerHTML = issues.map((issue, idx) => {
                    const itemId = issue.form_item_id ? String(issue.form_item_id) : '';
                    const label = issue.label || '';
                    const summary = issue.opinion_summary || '';
                    const verdict = String(issue.verdict || 'uncertain');
                    const numberBadge = `<span class="validation-summary-issue-num ${issueNumberClass(verdict)}">${idx + 1}</span>`;
                    const body = `${label ? `<span class="text-sm font-medium text-gray-900">${escapeHtml(label)}</span>` : ''}
                        ${summary ? `<p class="text-xs text-gray-600 mt-0.5">${escapeHtml(summary)}</p>` : ''}`;
                    if (itemId) {
                        return `<li class="flex items-start gap-2.5">
                            ${numberBadge}
                            <button type="button"
                                    class="validation-summary-issue group flex-1 min-w-0 text-left rounded-md px-2 py-1 -mx-2 -my-1 hover:bg-purple-50"
                                    data-item-id="${escapeHtml(itemId)}">
                                <span class="group-hover:underline">${body}</span>
                            </button>
                        </li>`;
                    }
                    return `<li class="flex items-start gap-2.5">
                        ${numberBadge}
                        <div class="flex-1 min-w-0">${body}</div>
                    </li>`;
                }).join('');
            }
        }
        // "In good shape" is collapsed by default (native <details>, no [open] attribute)
        // since it needs less attention than the numbered issues above it.
        const goodItems = Array.isArray(payload.whats_good) ? payload.whats_good.filter(Boolean) : [];
        if (goodWrap && goodEl) {
            goodWrap.removeAttribute('open');
            if (goodItems.length) {
                const heading = goodWrap.querySelector('[data-good-heading]');
                if (heading) heading.textContent = `${labelFor(banner, 'whats-good', 'In good shape')} (${goodItems.length})`;
                goodEl.innerHTML = goodItems.map((item) => `<li>${escapeHtml(item)}</li>`).join('');
                goodWrap.classList.remove('hidden');
            } else {
                goodWrap.classList.add('hidden');
                goodEl.replaceChildren();
            }
        }
        if (commentEl) {
            const note = String(payload.comment_note || '').trim();
            if (note) {
                const prefix = labelFor(banner, 'comment', 'Reporting-country comment');
                commentEl.textContent = `${prefix}: ${note}`;
                commentEl.classList.remove('hidden');
            } else {
                commentEl.textContent = '';
                commentEl.classList.add('hidden');
            }
        }
        if (detailsLink) {
            detailsLink.href = detailsUrl || payload.details_url || '#';
        }
        banner.classList.remove('hidden');
        banner.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };

    if (issuesEl) {
        issuesEl.addEventListener('click', (event) => {
            const btn = event.target && event.target.closest ? event.target.closest('.validation-summary-issue') : null;
            if (!btn) return;
            event.preventDefault();
            scrollToField(btn.getAttribute('data-item-id'));
        });
    }

    function parseSseJson(raw) {
        try {
            return JSON.parse(raw);
        } catch {
            return {};
        }
    }

    button.addEventListener('click', (event) => {
        event.preventDefault();
        if (inFlight) return;
        const aesNode = document.querySelector('[data-aes-id]');
        const aesId = aesNode ? aesNode.getAttribute('data-aes-id') : null;
        if (!aesId) {
            showError(labelFor(banner, 'error', 'Could not load the validation summary.'));
            return;
        }

        inFlight = true;
        setBusy(true);
        startLoadingAnimation();
        banner.classList.remove('hidden');

        const hidden = collectHiddenIds('focalDataEntryForm');
        const params = new URLSearchParams();
        if (hidden.hiddenFields.length) params.set('hidden_fields', hidden.hiddenFields.join(','));
        if (hidden.hiddenSections.length) params.set('hidden_sections', hidden.hiddenSections.join(','));
        const qs = params.toString();
        const detailsParams = new URLSearchParams(params);
        detailsParams.set('run', '0');
        const detailsUrl = `/forms/assignment_status/${aesId}/validation_summary?${detailsParams.toString()}`;

        const finish = () => {
            inFlight = false;
            setBusy(false);
        };

        // Plain single-request path — used when the browser has no EventSource, or as
        // a resilience fallback if the SSE stream below errors before ever producing a
        // "result" (e.g. blocked by some proxy). Same summary either way, just without
        // live stage updates (the loading animation keeps itself honest via its own
        // stall-cycling instead of freezing).
        const fetchOnce = () => {
            fetch(`/forms/assignment_status/${aesId}/validation_summary/overview${qs ? `?${qs}` : ''}`, {
                credentials: 'same-origin',
                headers: { Accept: 'application/json' },
            })
                .then((res) => res.json().catch(() => ({})).then((data) => {
                    if (!res.ok || data.success === false) {
                        throw new Error(data.error || data.message || `HTTP ${res.status}`);
                    }
                    render(data, detailsUrl);
                }))
                .catch((err) => {
                    debugWarn(MODULE_NAME, 'overview fetch failed', err);
                    showError(labelFor(banner, 'error', 'Could not load the validation summary.'));
                })
                .finally(finish);
        };

        if (typeof window.EventSource !== 'function') {
            fetchOnce();
            return;
        }

        let settled = false;
        const streamUrl = `/forms/assignment_status/${aesId}/validation_summary/overview_stream${qs ? `?${qs}` : ''}`;
        const es = new window.EventSource(streamUrl, { withCredentials: true });
        const closeStream = () => {
            try { es.close(); } catch { /* already closed */ }
        };

        es.addEventListener('stage', (ev) => {
            const data = parseSseJson(ev.data);
            onRealStage(data && data.label);
        });
        es.addEventListener('result', (ev) => {
            settled = true;
            closeStream();
            render(parseSseJson(ev.data), detailsUrl);
            finish();
        });
        // Covers both a server-sent "event: error" frame (e.g. access denied) and the
        // browser's native connection-level error — the codebase's other SSE consumer
        // (validation-summary-progress.js) treats these the same way. Fall back to the
        // plain request instead of just giving up, so a blocked/dropped stream still
        // resolves correctly for the user.
        es.addEventListener('error', () => {
            if (settled) return;
            settled = true;
            closeStream();
            debugWarn(MODULE_NAME, 'overview stream failed, falling back to single request');
            fetchOnce();
        });
    });

    debugLog(MODULE_NAME, 'initialized');
}
