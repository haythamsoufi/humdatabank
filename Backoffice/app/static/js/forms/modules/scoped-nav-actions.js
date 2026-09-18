// Toggle per-section / per-page nav actions when a scope is locked or reopened.

const LOCKED_STATUSES = new Set(['submitted', 'sent_for_review', 'approved', 'cancelled']);

function readScopeStatus(group) {
    const scope = group.dataset.scope;
    const id = group.dataset.scopeId;
    if (!id) return group.dataset.status || 'not_started';
    if (scope === 'page') {
        const container = document.querySelector(`[id^="section-container-"][data-page-id="${id}"][data-page-workflow]`);
        return container?.getAttribute('data-page-workflow') || group.dataset.status || 'not_started';
    }
    const container = document.getElementById(`section-container-${id}`);
    return container?.getAttribute('data-section-workflow') || group.dataset.status || 'not_started';
}

export function refreshScopedNavActions() {
    document.querySelectorAll('.sidebar-scope-actions').forEach((group) => {
        const status = readScopeStatus(group);
        const locked = LOCKED_STATUSES.has(status);
        group.dataset.status = status;
        const edit = group.querySelector('.sidebar-scope-actions__edit');
        const lockedWrap = group.querySelector('.sidebar-scope-actions__locked');
        if (edit) {
            edit.classList.toggle('hidden', locked);
            edit.setAttribute('aria-hidden', locked ? 'true' : 'false');
        }
        if (lockedWrap) {
            lockedWrap.classList.toggle('hidden', !locked);
            lockedWrap.setAttribute('aria-hidden', locked ? 'false' : 'true');
        }
    });
}

export function initScopedNavActions() {
    if (!document.querySelector('.sidebar-scope-actions')) return;
    document.addEventListener('ifrc:scoped-status:changed', refreshScopedNavActions);
    refreshScopedNavActions();
}
