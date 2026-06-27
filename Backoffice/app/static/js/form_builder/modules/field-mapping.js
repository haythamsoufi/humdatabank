/**
 * Field mapping review page — link draft fields to published stable_key identity.
 */

function getCsrfToken() {
    const el = document.getElementById('field-mapping-csrf');
    return el ? el.value : '';
}

async function postJson(url, body) {
    const resp = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
            'X-CSRFToken': getCsrfToken(),
        },
        credentials: 'same-origin',
        body: JSON.stringify(body || {}),
    });
    const data = await resp.json().catch(() => ({}));
    return { resp, data };
}

function setButtonsLoading(rowEl, loading) {
    rowEl.querySelectorAll('button[data-action]').forEach((btn) => {
        btn.classList.toggle('is-loading', loading);
        btn.disabled = loading;
    });
}

async function linkRow(rowEl, publishedStableKey, confirmReassign = false) {
    const linkUrl = rowEl.dataset.linkUrl;
    if (!linkUrl || !publishedStableKey) return;
    setButtonsLoading(rowEl, true);
    try {
        const { resp, data } = await postJson(linkUrl, {
            published_stable_key: publishedStableKey,
            confirm_reassign: confirmReassign,
        });
        if (resp.status === 409 && data.conflict) {
            const existing = data.existing_draft_item || data.existing_draft_section;
            const published = data.published_item || data.published_section;
            const existingLabel = existing?.label || existing?.name || existing?.id;
            const publishedLabel = published?.label || published?.name || published?.id;
            const draftLabel = rowEl.dataset.draftLabel || 'this field';
            const message =
                `Published field "${publishedLabel}" is already linked to draft field "${existingLabel}".\n\n` +
                `Link it to "${draftLabel}" instead?\n` +
                `"${existingLabel}" will become a new field (submission data will not carry forward to it).`;
            setButtonsLoading(rowEl, false);
            if (window.showConfirmation) {
                window.showConfirmation(
                    message,
                    () => { linkRow(rowEl, publishedStableKey, true); },
                    null,
                    'Confirm reassign',
                    'Cancel',
                    'Reassign field link?'
                );
            } else if (window.confirm(message)) {
                await linkRow(rowEl, publishedStableKey, true);
            }
            return;
        }
        if (!resp.ok || !data.success) {
            window.alert(data.error || 'Link failed.');
            return;
        }
        if (data.warnings && data.warnings.length) {
            window.alert(data.warnings.join('\n'));
        }
        location.reload();
    } finally {
        setButtonsLoading(rowEl, false);
    }
}

async function unlinkRow(rowEl) {
    const unlinkUrl = rowEl.dataset.unlinkUrl;
    if (!unlinkUrl) return;
    setButtonsLoading(rowEl, true);
    try {
        const { resp, data } = await postJson(unlinkUrl, {});
        if (!resp.ok || !data.success) {
            window.alert(data.error || 'Could not mark as new field.');
            return;
        }
        location.reload();
    } finally {
        setButtonsLoading(rowEl, false);
    }
}

function rowMatchesFilter(rowEl, filter) {
    const confidence = rowEl.dataset.confidence || '';
    if (filter === 'all') return true;
    if (filter === 'needs_review') return confidence === 'suggested';
    return confidence === filter;
}

function updateEmptyFilterRows(panelEl) {
    if (!panelEl) return;
    const rows = panelEl.querySelectorAll('[data-field-mapping-row]');
    const emptyRow = panelEl.querySelector('[data-empty-filter-row]');
    if (!emptyRow) return;
    const visibleCount = Array.from(rows).filter((row) => !row.hidden).length;
    emptyRow.hidden = visibleCount > 0;
}

function applyStatusFilter(filter) {
    document.querySelectorAll('.field-mapping-filter-btn').forEach((btn) => {
        const active = btn.dataset.filter === filter;
        btn.classList.toggle('is-active', active);
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    document.querySelectorAll('[data-field-mapping-row]').forEach((rowEl) => {
        rowEl.hidden = !rowMatchesFilter(rowEl, filter);
    });
    document.querySelectorAll('[data-entity-panel]').forEach(updateEmptyFilterRows);
}

function switchEntityTab(entity) {
    const itemsTab = document.getElementById('field-mapping-tab-items');
    const sectionsTab = document.getElementById('field-mapping-tab-sections');
    const itemsPanel = document.getElementById('field-mapping-panel-items');
    const sectionsPanel = document.getElementById('field-mapping-panel-sections');

    const isItems = entity === 'items';
    if (itemsTab) {
        itemsTab.setAttribute('aria-selected', isItems ? 'true' : 'false');
        itemsTab.classList.toggle('border-blue-600', isItems);
        itemsTab.classList.toggle('text-blue-600', isItems);
        itemsTab.classList.toggle('border-transparent', !isItems);
        itemsTab.classList.toggle('text-gray-600', !isItems);
    }
    if (sectionsTab) {
        sectionsTab.setAttribute('aria-selected', !isItems ? 'true' : 'false');
        sectionsTab.classList.toggle('border-blue-600', !isItems);
        sectionsTab.classList.toggle('text-blue-600', !isItems);
        sectionsTab.classList.toggle('border-transparent', isItems);
        sectionsTab.classList.toggle('text-gray-600', isItems);
    }
    if (itemsPanel) itemsPanel.hidden = !isItems;
    if (sectionsPanel) sectionsPanel.hidden = isItems;
}

function wireFieldMappingPage() {
    document.querySelectorAll('[data-entity-tab]').forEach((tab) => {
        tab.addEventListener('click', () => {
            switchEntityTab(tab.dataset.entityTab || 'items');
        });
    });

    document.querySelectorAll('.field-mapping-filter-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
            applyStatusFilter(btn.dataset.filter || 'all');
        });
    });

    document.querySelectorAll('[data-field-mapping-row]').forEach((rowEl) => {
        const confirmBtn = rowEl.querySelector('[data-action="confirm-link"]');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', () => {
                const key = confirmBtn.dataset.publishedStableKey;
                if (key) linkRow(rowEl, key, false);
            });
        }

        const applyBtn = rowEl.querySelector('[data-action="apply-link"]');
        const selectEl = rowEl.querySelector('[data-published-key-select]');
        if (applyBtn && selectEl) {
            applyBtn.addEventListener('click', () => {
                const key = selectEl.value;
                if (!key) {
                    window.alert('Select a published field or section first.');
                    return;
                }
                linkRow(rowEl, key, false);
            });
        }

        const unlinkBtn = rowEl.querySelector('[data-action="unlink"]');
        if (unlinkBtn) {
            unlinkBtn.addEventListener('click', () => {
                const msg = 'Mark this as a new field? Submission data will not carry forward to it on deploy.';
                if (window.showConfirmation) {
                    window.showConfirmation(msg, () => unlinkRow(rowEl), null, 'Mark as new', 'Cancel');
                } else if (window.confirm(msg)) {
                    unlinkRow(rowEl);
                }
            });
        }
    });

    applyStatusFilter('all');
}

document.addEventListener('DOMContentLoaded', wireFieldMappingPage);
