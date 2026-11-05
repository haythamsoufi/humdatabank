// Client-side lock for submitted pages/sections. Server still enforces the write skip.

const BUZZ_CLASS = 'page-locked-banner--buzz';
const BUZZ_MS = 500;
let buzzTimer = null;
let interactionBound = false;

function shouldBypassPageLock() {
    const form = document.getElementById('focalDataEntryForm');
    return form?.dataset?.bypassPageLock === 'true';
}

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
    if (el.closest && el.closest('.page-locked-banner')) return true;
    if (el.closest && el.closest('.sidebar-scope-actions')) return true;
    return false;
}

function findPageLockedBanner(pageId) {
    if (pageId == null || pageId === '') return null;
    return document.querySelector(`.page-locked-banner[data-page-id="${pageId}"]`);
}

function syncPageLockedBanner(pageId, locked) {
    const banner = findPageLockedBanner(pageId);
    if (!banner) return;
    banner.classList.toggle('hidden', !locked);
}

export function buzzPageLockedBanner(pageId) {
    const banner = findPageLockedBanner(pageId);
    if (!banner || banner.classList.contains('hidden')) return false;
    banner.classList.remove(BUZZ_CLASS);
    // Force reflow so re-adding the class retriggers the animation.
    void banner.offsetWidth;
    banner.classList.add(BUZZ_CLASS);
    if (buzzTimer) clearTimeout(buzzTimer);
    buzzTimer = setTimeout(() => {
        banner.classList.remove(BUZZ_CLASS);
        buzzTimer = null;
    }, BUZZ_MS);
    try {
        banner.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    } catch (_) { /* no-op */ }
    return true;
}

function onLockedInteraction(event) {
    if (shouldBypassPageLock()) return;
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (isReopenOrChromeControl(target)) return;

    const container = target.closest('[data-page-locked="true"], [data-section-locked="true"]');
    if (!container) return;

    // Disabled controls often deliver the event to a parent; treat form items and
    // collapsible content as an attempt to edit.
    const editingTarget = target.closest(
        'input, select, textarea, button, label, a, .form-item-block, .select2-container, [role="combobox"], [contenteditable="true"], [data-collapsible-content]'
    );
    if (!editingTarget) return;

    const pageId = container.dataset.pageId;
    if (pageId) {
        buzzPageLockedBanner(pageId);
    }
}

function bindLockedInteractionListeners() {
    if (interactionBound || shouldBypassPageLock()) return;
    interactionBound = true;
    // pointerdown covers mouse/touch; focusin covers keyboard tab into fields.
    // Avoid also binding click — it would re-trigger the buzz on the same gesture.
    document.addEventListener('pointerdown', onLockedInteraction, true);
    document.addEventListener('focusin', onLockedInteraction, true);
}

export function applySectionLock(container, locked) {
    if (!container) return;
    if (locked && shouldBypassPageLock()) {
        locked = false;
    }
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

    const pageId = container.dataset.pageId;
    if (pageId) {
        const anyLocked = locked || !!document.querySelector(
            `[id^="section-container-"][data-page-id="${pageId}"][data-page-locked="true"]`
        );
        syncPageLockedBanner(pageId, anyLocked);
    }

    try {
        document.dispatchEvent(new CustomEvent('ifrc:scoped-status:changed', {
            detail: { locked, containerId: container.id },
        }));
    } catch (_) { /* no-op */ }
}

export function initSectionLocks() {
    if (shouldBypassPageLock()) {
        document.querySelectorAll('[data-section-locked="true"], [data-page-locked="true"]').forEach((el) => {
            applySectionLock(el, false);
        });
        return;
    }
    document.querySelectorAll('[data-section-locked="true"], [data-page-locked="true"]').forEach((el) => {
        applySectionLock(el, true);
    });
    bindLockedInteractionListeners();
}
