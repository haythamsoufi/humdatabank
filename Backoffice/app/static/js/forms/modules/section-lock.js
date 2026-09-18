// Client-side lock for submitted sections. Server still enforces the write skip.

function isReopenOrChromeControl(el) {
    if (!el) return false;
    if (el.classList.contains('reopen-section-btn')) return true;
    if (el.classList.contains('reopen-page-btn')) return true;
    if (el.classList.contains('return-section-btn')) return true;
    if (el.classList.contains('return-page-btn')) return true;
    if (el.classList.contains('collapse-toggle')) return true;
    if (el.closest && el.closest('.reopen-section-form')) return true;
    if (el.closest && el.closest('.reopen-page-form')) return true;
    if (el.closest && el.closest('.return-section-form')) return true;
    if (el.closest && el.closest('.return-page-form')) return true;
    return false;
}

export function applySectionLock(container, locked) {
    if (!container) return;
    container.dataset.sectionLocked = locked ? 'true' : 'false';
    if (container.hasAttribute('data-page-id')) {
        container.dataset.pageLocked = locked ? 'true' : 'false';
    }
    container.classList.toggle('section-container--locked', locked);
    if (locked) {
        if (container.hasAttribute('data-section-workflow')) {
            container.setAttribute('data-section-workflow', 'submitted');
        }
        if (container.hasAttribute('data-page-workflow')) {
            container.setAttribute('data-page-workflow', 'submitted');
        }
    }

    container.querySelectorAll('input, select, textarea, button').forEach((el) => {
        if (isReopenOrChromeControl(el)) return;
        if (el.name === 'csrf_token') return;
        el.disabled = !!locked;
    });

    try {
        document.dispatchEvent(new CustomEvent('ifrc:scoped-status:changed', {
            detail: { locked, containerId: container.id },
        }));
    } catch (_) { /* no-op */ }
}

export function initSectionLocks() {
    document.querySelectorAll('[data-section-locked="true"], [data-page-locked="true"]').forEach((el) => {
        applySectionLock(el, true);
    });
}
