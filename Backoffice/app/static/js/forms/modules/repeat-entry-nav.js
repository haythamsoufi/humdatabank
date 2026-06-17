import { debugLog } from './debug.js';

const MODULE = 'repeat-entry-nav';

function getScrollableContainer() {
    const mainElement = document.querySelector('main[style*="overflow-y"]') || document.querySelector('main');
    if (mainElement && mainElement.scrollHeight > mainElement.clientHeight) {
        return mainElement;
    }
    return window;
}

function scrollToElement(elementId) {
    const target = document.getElementById(elementId);
    if (!target) return;

    const scrollContainer = getScrollableContainer();
    const isMainContainer = scrollContainer !== window;
    const targetRect = target.getBoundingClientRect();
    const computed = window.getComputedStyle(target);
    const scrollMarginTop = parseInt(computed.scrollMarginTop || '0', 10) || 80;

    if (isMainContainer) {
        const containerRect = scrollContainer.getBoundingClientRect();
        const targetTop = Math.max(
            0,
            scrollContainer.scrollTop + (targetRect.top - containerRect.top) - scrollMarginTop
        );
        scrollContainer.scrollTo({ top: targetTop, behavior: 'smooth' });
    } else {
        const targetTop = Math.max(0, window.pageYOffset + targetRect.top - scrollMarginTop);
        window.scrollTo({ top: targetTop, behavior: 'smooth' });
    }
}

function getRepeatEntryLabelText(repeatEntry) {
    const titleSelect = repeatEntry.querySelector('select[data-use-as-repeat-entry-title="true"]');
    if (titleSelect && titleSelect.value) {
        const selected = titleSelect.options[titleSelect.selectedIndex];
        return selected ? selected.textContent.trim() : titleSelect.value;
    }

    const labelEl = repeatEntry.querySelector('.repeat-entry__label');
    if (labelEl) {
        const text = labelEl.textContent.trim();
        if (text) return text;
    }

    const instanceNumber = repeatEntry.getAttribute('data-repeat-instance') || '1';
    return (window.REPEAT_SECTION_LABELS?.entry || 'Entry') + ' #' + instanceNumber;
}

function buildRepeatEntryNavLink(repeatEntry, sectionId) {
    const instanceNumber = repeatEntry.getAttribute('data-repeat-instance') || '1';
    const entryId = repeatEntry.id || `repeat-entry-${sectionId}-${instanceNumber}`;
    const pageNumber = repeatEntry.closest('[data-page-number]')?.dataset.pageNumber || '';
    const pageName = repeatEntry.closest('[data-page-number]')?.dataset.pageName || '';

    const link = document.createElement('a');
    link.href = `#${entryId}`;
    link.className = 'repeat-entry-nav-link section-link group flex items-center gap-2 px-2 py-1 rounded-md text-xs font-medium text-blue-700 hover:bg-blue-50 hover:text-blue-800 transition duration-150 ease-in-out';
    link.dataset.sectionId = entryId;
    link.dataset.repeatSectionId = String(sectionId);
    link.dataset.repeatInstance = String(instanceNumber);
    if (pageNumber) link.dataset.pageNumber = pageNumber;
    if (pageName) link.dataset.pageName = pageName;

    const icon = document.createElement('i');
    icon.className = 'fas fa-circle-dot flex-shrink-0 w-2 h-2 text-blue-400';
    icon.setAttribute('aria-hidden', 'true');

    const label = document.createElement('span');
    label.className = 'truncate min-w-0 flex-1 repeat-entry-nav-label';
    label.textContent = getRepeatEntryLabelText(repeatEntry);

    link.append(icon, label);
    return link;
}

export function syncRepeatEntryNavigation(sectionId) {
    const navList = document.querySelector(
        `.repeat-entry-nav-list[data-repeat-section-id="${sectionId}"]`
    );
    const sectionContainer = document.getElementById(`section-container-${sectionId}`);
    if (!navList || !sectionContainer) return;
    if (sectionContainer.dataset.showEntriesInNavigation !== 'true') {
        navList.replaceChildren();
        return;
    }

    const repeatContainer = document.getElementById(`repeat-entries-${sectionId}`);
    if (!repeatContainer) return;

    navList.replaceChildren();
    repeatContainer.querySelectorAll('.repeat-entry').forEach((repeatEntry) => {
        const li = document.createElement('li');
        li.appendChild(buildRepeatEntryNavLink(repeatEntry, sectionId));
        navList.appendChild(li);
    });

    debugLog(MODULE, `Synced ${navList.children.length} nav links for repeat section ${sectionId}`);
}

export function syncAllRepeatEntryNavigation() {
    document.querySelectorAll('[data-show-entries-in-navigation="true"]').forEach((sectionEl) => {
        const sectionId = sectionEl.getAttribute('data-collapsible-id')
            || sectionEl.id.replace('section-container-', '');
        if (sectionId) {
            syncRepeatEntryNavigation(sectionId);
        }
    });
}

export function initRepeatEntryNavigation() {
    syncAllRepeatEntryNavigation();

    document.addEventListener('click', (e) => {
        const link = e.target.closest('a.repeat-entry-nav-link');
        if (!link) return;
        e.preventDefault();

        const entryId = link.dataset.sectionId
            || (link.getAttribute('href') || '').replace(/^#/, '');
        if (!entryId) return;

        try {
            const url = new URL(window.location.href);
            url.hash = entryId;
            window.history.replaceState({}, '', url);
        } catch (_err) { /* no-op */ }

        scrollToElement(entryId);

        document.querySelectorAll('a.repeat-entry-nav-link.is-active').forEach((el) => {
            el.classList.remove('is-active');
            el.removeAttribute('aria-current');
        });
        link.classList.add('is-active');
        link.setAttribute('aria-current', 'location');
    });

    window.syncRepeatEntryNavigation = syncRepeatEntryNavigation;
    window.syncAllRepeatEntryNavigation = syncAllRepeatEntryNavigation;
}
