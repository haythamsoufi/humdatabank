import { debugLog, debugWarn, isDebugEnabled } from './debug.js';

const MODULE_NAME = 'pagination';

function parsePageNumber(raw, fallback = 1) {
    const n = parseInt(String(raw ?? ''), 10);
    return Number.isFinite(n) ? n : fallback;
}

// Initialize pagination when DOM is ready (handle both loading and already-loaded states)
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPagination);
} else {
    // DOM is already loaded, initialize immediately
    initPagination();
}

/**
 * Handle #field-<id> hash scrolling for both paginated and non-paginated forms.
 * Waits for the form UI to become visible, then scrolls to and highlights the field.
 */
function handleFieldHashScroll() {
    const hash = (window.location.hash || '').replace(/^#/, '');
    if (!/^field-\d+$/.test(hash)) return;
    debugLog(MODULE_NAME, 'handleFieldHashScroll: detected field hash:', hash);

    _afterFormReady(() => {
        debugLog(MODULE_NAME, 'handleFieldHashScroll: form ready, looking for element:', hash);
        const rawId = hash.replace('field-', '');
        const el = document.getElementById(hash)
            || document.querySelector(`[data-item-id="${rawId}"]`)
            || document.querySelector(`label[for="${hash}"]`);
        debugLog(MODULE_NAME, 'handleFieldHashScroll: getElementById:', !!document.getElementById(hash),
            'data-item-id:', !!document.querySelector(`[data-item-id="${rawId}"]`),
            'label[for]:', !!document.querySelector(`label[for="${hash}"]`),
            'chosen:', el?.tagName, el?.id);
        if (!el) {
            debugWarn(MODULE_NAME, 'handleFieldHashScroll: element not found for:', hash);
            return;
        }
        requestAnimationFrame(() => {
            _scrollElementIntoView(el);
            _highlightField(el);
        });
    });
}

function _afterFormReady(callback) {
    const ready = document.body.dataset.formInitialized === 'true';
    debugLog(MODULE_NAME, '_afterFormReady: formInitialized =', document.body.dataset.formInitialized, 'ready =', ready);
    if (ready) {
        requestAnimationFrame(callback);
        return;
    }
    const obs = new MutationObserver(() => {
        if (document.body.dataset.formInitialized === 'true') {
            obs.disconnect();
            debugLog(MODULE_NAME, '_afterFormReady:observer: formInitialized became true, firing callback');
            requestAnimationFrame(callback);
        }
    });
    obs.observe(document.body, { attributes: true, attributeFilter: ['data-form-initialized'] });
    setTimeout(() => { debugWarn(MODULE_NAME, '_afterFormReady: 30s timeout'); obs.disconnect(); }, 30000);
}

function _scrollElementIntoView(el) {
    if (!el) return;
    const mainElement = document.querySelector('main[style*="overflow-y"]') || document.querySelector('main');
    const isMainContainer = mainElement && mainElement.scrollHeight > mainElement.clientHeight;
    const scrollContainer = isMainContainer ? mainElement : window;
    const headerOffset = 100;
    const rect = el.getBoundingClientRect();
    debugLog(MODULE_NAME, '_scrollElementIntoView: el:', el.id || el.tagName, 'rect:', { top: Math.round(rect.top), bottom: Math.round(rect.bottom), height: Math.round(rect.height) }, 'isMainContainer:', isMainContainer);

    if (isMainContainer) {
        const containerRect = scrollContainer.getBoundingClientRect();
        const elTopRel = rect.top - containerRect.top;
        const targetTop = Math.max(0, scrollContainer.scrollTop + elTopRel - headerOffset);
        debugLog(MODULE_NAME, '_scrollElementIntoView: main scrollTo:', targetTop, 'from:', scrollContainer.scrollTop);
        scrollContainer.scrollTo({ top: targetTop, behavior: 'smooth' });
    } else {
        const targetTop = Math.max(0, window.pageYOffset + rect.top - headerOffset);
        debugLog(MODULE_NAME, '_scrollElementIntoView: window scrollTo:', targetTop, 'from:', window.pageYOffset);
        window.scrollTo({ top: targetTop, behavior: 'smooth' });
    }
}

function _highlightField(el) {
    if (!el) return;
    const target = el.closest('.form-item-block') || el.closest('.form-group') || el;
    debugLog(MODULE_NAME, '_highlightField: highlighting:', target.tagName, target.id || target.className?.substring(0, 60));
    target.style.transition = 'box-shadow 0.3s ease, outline 0.3s ease';
    target.style.outline = '2px solid #f59e0b';
    target.style.boxShadow = '0 0 0 4px rgba(245,158,11,0.25)';
    setTimeout(() => {
        target.style.outline = '';
        target.style.boxShadow = '';
        setTimeout(() => { target.style.transition = ''; }, 400);
    }, 2500);
}

function initPagination() {
    const sectionsContainer = document.getElementById('sections-container');
    if (!sectionsContainer) {
        debugLog(MODULE_NAME, 'No #sections-container found, skipping pagination.');
        return;
    }

    // Check if pagination is enabled for this template
    const isPaginated = sectionsContainer.dataset.isPaginated === 'true';
    if (!isPaginated) {
        debugLog(MODULE_NAME, 'Template is not paginated, showing all sections.');
        // Show all sections and exit
        Array.from(sectionsContainer.querySelectorAll('[data-page-number]')).forEach(el => {
            // Remove any previous pagination overrides (including !important)
            el.style.removeProperty('display');
        });
        // Still handle #field-* hash for non-paginated forms (scroll + highlight)
        handleFieldHashScroll();
        return;
    }

    // Collect all section containers that have a page number
    const sectionEls = Array.from(sectionsContainer.querySelectorAll('[data-page-number]'));
    if (sectionEls.length === 0) {
        debugLog(MODULE_NAME, 'No sections with data-page-number found.');
        return;
    }

    // Create a map of unique pages using page number as the key
    const pageMap = new Map();
    sectionEls.forEach(el => {
        const rawNum = el.dataset.pageNumber;
        const pageNum = parsePageNumber(rawNum, 1);
        const pageName = el.dataset.pageName || `Page ${pageNum}`;
        if (!pageMap.has(pageNum)) {
            pageMap.set(pageNum, { number: pageNum, name: pageName });
        }
    });

    // Convert map to sorted array
    const pages = Array.from(pageMap.values()).sort((a, b) => a.number - b.number);
    debugLog(MODULE_NAME, 'Unique pages detected:', pages);

    // If there's only one page, just ensure all sections are visible and exit
    if (pages.length <= 1) {
        debugLog(MODULE_NAME, 'Only one page detected, skipping pagination controls.');
        sectionEls.forEach(el => el.style.display = '');
        return;
    }

    // Build navigation controls dynamically
    const navControls = buildNavigationControls();
    sectionsContainer.appendChild(navControls);

    const prevBtn = navControls.querySelector('#prev-page-btn');
    const nextBtn = navControls.querySelector('#next-page-btn');
    const pageIndicator = navControls.querySelector('#page-indicator');

    // Get the current page from sessionStorage or default to 0
    const storageKey = getFormPageStorageKey();
    let currentPageIdx = getStoredPageIndex(storageKey, pages.length);
    let currentSection = getStoredSection();
    const initialHash = (window.location.hash || '').replace(/^#/, '');
    const initialHashIsField = /^field-\d+$/.test(initialHash);
    debugLog(MODULE_NAME, 'init: initialHash =', initialHash, 'isField =', initialHashIsField, 'currentSection =', currentSection, 'storedPageIdx =', currentPageIdx);

    // If URL has a section or field hash, show the page that contains that section
    if (currentSection) {
        const sectionEl = document.getElementById(currentSection);
        debugLog(MODULE_NAME, 'init: looking up section element:', currentSection, 'found:', !!sectionEl, 'pageNumber attr:', sectionEl?.dataset?.pageNumber);
        if (sectionEl && sectionEl.dataset.pageNumber !== undefined) {
            const pageNum = parsePageNumber(sectionEl.dataset.pageNumber, 1);
            const idx = pages.findIndex(p => p.number === pageNum);
            debugLog(MODULE_NAME, 'init: resolved pageNum:', pageNum, 'pageIdx:', idx);
            if (idx >= 0) currentPageIdx = idx;
        }
    }

    // Helpful diagnostics: map all elements that pagination can toggle
    debugLog(MODULE_NAME, 'Section elements detected (pagination hosts):', sectionEls.map(el => ({
        id: el.id || '(no id)',
        pageNumber: parsePageNumber(el.dataset.pageNumber, 1),
        pageName: el.dataset.pageName || '',
        sectionType: el.dataset.sectionType || '',
        hasRelevanceCondition: el.hasAttribute('data-relevance-condition'),
        isRelevanceHidden: el.classList.contains('relevance-hidden'),
        display: el.style.display || '(inline style empty)'
    })));

    // Log initial state and URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    const urlPageParam = urlParams.get('page');
    const urlHash = window.location.hash;

    debugLog(MODULE_NAME, 'Pagination initialization:', {
        totalPages: pages.length,
        currentPageIdx: currentPageIdx,
        currentPageNumber: pages[currentPageIdx]?.number || 'unknown',
        currentPageName: pages[currentPageIdx]?.name || 'unknown',
        currentSection: currentSection,
        urlPageParam: urlPageParam,
        urlHash: urlHash,
        storageKey: storageKey,
        isPaginated: isPaginated,
        sectionsCount: sectionEls.length
    });

    debugLog(MODULE_NAME, `Initializing with page index: ${currentPageIdx} (page ${pages[currentPageIdx]?.number || 'unknown'}) and section: ${currentSection}`);

    prevBtn.addEventListener('click', () => changePage(currentPageIdx - 1));
    nextBtn.addEventListener('click', () => changePage(currentPageIdx + 1));

    // Group sidebar navigation
    organiseSidebar();

    // Ensure section links switch pages if necessary
    hookSectionLinks();

    // Show initial page
    changePage(currentPageIdx, false);

    // Debug-only: watch for other modules overriding page visibility after pagination runs.
    // This is the most common cause of "sections showing on the wrong page".
    setupVisibilityMutationObserver();

    // Scroll to stored section or to field when opened via dashboard activity link (#field-*)
    debugLog(MODULE_NAME, 'init: about to schedule scroll. initialHashIsField =', initialHashIsField, 'currentSection =', currentSection);
    if (initialHashIsField) {
        debugLog(MODULE_NAME, 'init: scheduling afterFormReady → scrollToField for:', initialHash);
        _afterFormReady(() => {
            debugLog(MODULE_NAME, 'afterFormReady: FIRED for field scroll:', initialHash);
            scrollToField(initialHash);
        });
    } else if (currentSection) {
        debugLog(MODULE_NAME, 'init: scheduling afterFormReady → scrollToSection for:', currentSection);
        _afterFormReady(() => {
            debugLog(MODULE_NAME, 'afterFormReady: FIRED for section scroll:', currentSection);
            scrollToSection(currentSection);
        });
    } else {
        debugLog(MODULE_NAME, 'init: no field/section hash to scroll to');
    }

    /** Show the specified page by index */
    function changePage(targetIdx, scrollToTop = true) {
        if (targetIdx < 0 || targetIdx >= pages.length) {
            debugLog(MODULE_NAME, `Invalid page index: ${targetIdx} (valid range: 0-${pages.length - 1})`);
            return;
        }
        const targetPage = pages[targetIdx];

        debugLog(MODULE_NAME, `Changing page:`, {
            fromIndex: currentPageIdx,
            toIndex: targetIdx,
            fromPage: pages[currentPageIdx]?.number || 'unknown',
            toPage: targetPage.number,
            toPageName: targetPage.name,
            scrollToTop: scrollToTop,
            currentScrollY: window.pageYOffset
        });

        // Apply visibility for the target page
        const visibility = applyVisibilityForPage(targetPage.number, { reason: 'changePage' });
        debugLog(
            MODULE_NAME,
            `Page change complete: ${visibility.shownCount} sections visible for page ${targetPage.number}`,
            visibility
        );

        // Update buttons
        prevBtn.style.display = targetIdx === 0 ? 'none' : '';
        nextBtn.style.display = targetIdx === pages.length - 1 ? 'none' : '';
        const ofText = PAGINATION_LABELS.of || 'of';
        pageIndicator.textContent = `${targetPage.name} (${targetIdx + 1} ${ofText} ${pages.length})`;

        currentPageIdx = targetIdx;

        // Save the current page to sessionStorage
        saveCurrentPage(storageKey, targetIdx);

        // Update URL with current page parameter (preserve current section if any)
        updateURLWithPage(targetIdx, currentSection);

        if (scrollToTop) {
            // Find the scrollable container
            const scrollContainer = getScrollableContainer(sectionsContainer);
            const isMainContainer = scrollContainer !== window;

            // Scroll to top of sections container for better UX, accounting for navbar height
            // Try multiple selectors to find the navbar
            const navbar = document.querySelector('nav.sticky, nav[class*="sticky"], #navContainer')?.closest('nav') ||
                          document.querySelector('nav.bg-red-700, nav.nav-focal-point');
            const navbarHeight = navbar ? navbar.offsetHeight : 64; // Default to 4rem (64px) if navbar not found

            const containerRect = sectionsContainer.getBoundingClientRect();

            let targetScrollPosition;
            let currentScrollPosition;

            if (isMainContainer) {
                // For main container: calculate position relative to the container
                const containerTopRelative = containerRect.top - scrollContainer.getBoundingClientRect().top;
                const padding = 8;
                targetScrollPosition = scrollContainer.scrollTop + containerTopRelative - navbarHeight - padding;
                currentScrollPosition = scrollContainer.scrollTop;
            } else {
                // For window: calculate position relative to document
                const containerTop = containerRect.top + window.pageYOffset;
                const padding = 8;
                targetScrollPosition = containerTop - navbarHeight - padding;
                currentScrollPosition = window.pageYOffset;
            }

            // Ensure minimum scroll position to prevent layout issues
            const minScrollPosition = navbarHeight;
            const finalScrollPosition = Math.max(minScrollPosition, targetScrollPosition);

            debugLog(MODULE_NAME, 'Scrolling to top of sections container:', {
                scrollContainer: isMainContainer ? 'main' : 'window',
                navbarFound: !!navbar,
                navbarHeight: navbarHeight,
                containerTop: isMainContainer ? (containerRect.top - scrollContainer.getBoundingClientRect().top) : containerRect.top + window.pageYOffset,
                targetPosition: targetScrollPosition,
                finalScrollPosition: finalScrollPosition,
                minScrollPosition: minScrollPosition,
                currentScrollPosition: currentScrollPosition,
                navbarSelector: navbar ? navbar.className : 'not found',
                containerRect: {
                    top: containerRect.top,
                    bottom: containerRect.bottom,
                    height: containerRect.height
                }
            });

            // Scroll the appropriate container
            if (isMainContainer) {
                scrollContainer.scrollTo({
                    top: finalScrollPosition,
                    behavior: 'smooth'
                });
            } else {
                window.scrollTo({
                    top: finalScrollPosition,
                    behavior: 'smooth'
                });
            }
        }

        debugLog(MODULE_NAME, `Changed to page ${targetPage.number} (${targetPage.name})`);

        // Notify other modules (e.g. relevance) that the active page changed
        try {
            document.dispatchEvent(new CustomEvent('ifrc:pagination:pageChanged', {
                detail: {
                    pageIndex: currentPageIdx,
                    pageNumber: targetPage.number,
                    pageName: targetPage.name,
                    totalPages: pages.length
                }
            }));
        } catch (e) {
            // ignore
        }
    }

    // Expose a small API so other modules (e.g., form-validation) can switch pages
    // before scrolling to errors on submit.
    window.__ifrcPagination = window.__ifrcPagination || {};
    window.__ifrcPagination.showPageByNumber = (pageNumber) => {
        const targetPageNum = parsePageNumber(pageNumber, 1);
        const idx = pages.findIndex(p => p.number === targetPageNum);
        if (idx === -1) return false;
        changePage(idx, false);
        return true;
    };
    window.__ifrcPagination.getCurrentPageNumber = () => {
        return pages[currentPageIdx]?.number ?? null;
    };
    window.__ifrcPagination.getCurrentPageIndex = () => {
        return Number.isFinite(currentPageIdx) ? currentPageIdx : null;
    };
    window.__ifrcPagination.refresh = (opts = {}) => {
        const pageNumber = pages[currentPageIdx]?.number;
        if (!pageNumber) return false;
        debugLog(MODULE_NAME, 'Refresh requested; re-applying visibility for current page.', {
            pageIndex: currentPageIdx,
            pageNumber,
            opts
        });
        applyVisibilityForPage(pageNumber, { reason: 'refresh', opts });
        return true;
    };

    function applyVisibilityForPage(pageNumber, meta = {}) {
        const shownIds = [];
        const skippedDueToRelevance = [];
        const nonNumericPageNumbers = [];

        // Hide all pagination hosts first.
        // IMPORTANT: use !important to win against relevance CSS that may also use !important.
        sectionEls.forEach(el => { el.style.setProperty('display', 'none', 'important'); });

        // Show only sections for the target page, but never override relevance-hidden.
        sectionEls.forEach(el => {
            const raw = el.dataset.pageNumber;
            const elPageNum = parsePageNumber(raw, 1);
            if (!Number.isFinite(parseInt(String(raw ?? ''), 10))) {
                nonNumericPageNumbers.push({ id: el.id || '(no id)', raw });
            }

            if (elPageNum !== pageNumber) return;

            if (el.classList.contains('relevance-hidden')) {
                skippedDueToRelevance.push(el.id || '(no id)');
                el.style.setProperty('display', 'none', 'important');
                return;
            }

            // Remove display override (including !important) so normal CSS can apply.
            el.style.removeProperty('display');
            shownIds.push(el.id || '(no id)');
        });

        const result = {
            pageNumber,
            shownCount: shownIds.length,
            shownIds,
            skippedDueToRelevanceCount: skippedDueToRelevance.length,
            skippedDueToRelevance,
            nonNumericPageNumbersCount: nonNumericPageNumbers.length,
            nonNumericPageNumbers,
            meta
        };

        // High-signal check: if any *computed-visible* host has a different page number, another script is overriding us.
        // Exclude sections with data-relevance-condition: conditions.js owns their visibility (relevance-hidden /
        // relevance-visible + wrong-page); timing can make computed display briefly non-none.
        const visibleMismatches = sectionEls
            .filter(el => {
                if (el.hasAttribute('data-relevance-condition')) return false;
                try {
                    return window.getComputedStyle(el).display !== 'none';
                } catch (e) {
                    return el.style.display !== 'none';
                }
            })
            .map(el => ({ id: el.id || '(no id)', pageNumber: parsePageNumber(el.dataset.pageNumber, 1) }))
            .filter(x => x.pageNumber !== pageNumber);

        if (visibleMismatches.length) {
            debugWarn(MODULE_NAME, '⚠️ Visible page host mismatch detected (another module may be overriding display):', {
                pageNumber,
                visibleMismatches
            });
        }

        return result;
    }

    function setupVisibilityMutationObserver() {
        // Only enable the observer when pagination debugging is enabled
        if (!isDebugEnabled || typeof isDebugEnabled !== 'function' || !isDebugEnabled(MODULE_NAME)) return;
        if (typeof MutationObserver === 'undefined') return;

        const lastLoggedById = new Map();
        const minMsBetweenLogsPerElement = 1000;

        const observer = new MutationObserver((mutations) => {
            const activePage = (window.__ifrcPagination && typeof window.__ifrcPagination.getCurrentPageNumber === 'function')
                ? window.__ifrcPagination.getCurrentPageNumber()
                : null;
            if (!Number.isFinite(activePage)) return;

            for (const m of mutations) {
                const el = m.target;
                if (!el || el.nodeType !== 1) continue;
                if (!el.dataset || !('pageNumber' in el.dataset)) continue;

                const elId = el.id || '(no id)';
                const elPageNum = parsePageNumber(el.dataset.pageNumber, 1);

                // Only care about elements that *should* be hidden for the active page.
                if (elPageNum === activePage) continue;

                // Skip relevance-managed sections: conditions.js owns their visibility (relevance-hidden /
                // relevance-visible). Class/style mutations can cause brief timing quirks in computed display.
                if (el.hasAttribute('data-relevance-condition')) continue;

                let isVisible = false;
                let computedDisplay = '(unavailable)';
                try {
                    computedDisplay = window.getComputedStyle(el).display;
                    isVisible = computedDisplay !== 'none';
                } catch (e) {
                    isVisible = el.style.display !== 'none';
                }
                if (!isVisible) continue;

                const now = Date.now();
                const last = lastLoggedById.get(elId) || 0;
                if (now - last < minMsBetweenLogsPerElement) continue;
                lastLoggedById.set(elId, now);

                debugWarn(MODULE_NAME, '🚨 Element became visible on the wrong page (visibility override detected):', {
                    activePage,
                    element: {
                        id: elId,
                        pageNumber: elPageNum,
                        pageName: el.dataset.pageName || '',
                        sectionType: el.dataset.sectionType || '',
                        className: el.className || '',
                        inlineDisplay: el.style.display || '(inline style empty)',
                        computedDisplay
                    },
                    mutation: {
                        type: m.type,
                        attributeName: m.attributeName,
                        oldValue: m.oldValue
                    },
                    stack: (new Error('pagination visibility override')).stack
                });
            }
        });

        // Observe page host elements directly to keep noise low.
        sectionEls.forEach((el) => {
            try {
                observer.observe(el, {
                    attributes: true,
                    attributeFilter: ['style', 'class'],
                    attributeOldValue: true
                });
            } catch (e) {
                // ignore
            }
        });

        debugLog(MODULE_NAME, 'Visibility mutation observer enabled for pagination hosts:', {
            observedCount: sectionEls.length
        });
    }

    /** Build navigation controls element */
    function buildNavigationControls() {
        const PAGINATION_LABELS = window.PAGINATION_LABELS || { previous: "Previous Page", next: "Next Page", of: "of" };
        const wrapper = document.createElement('div');
        wrapper.id = 'page-navigation-controls';
        wrapper.className = 'flex items-center justify-between mt-8';

        const prevBtn = document.createElement('button');
        prevBtn.id = 'prev-page-btn';
        prevBtn.type = 'button';
        prevBtn.className = 'bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md text-sm font-medium';
        prevBtn.textContent = PAGINATION_LABELS.previous;

        const pageIndicator = document.createElement('span');
        pageIndicator.id = 'page-indicator';
        pageIndicator.className = 'text-gray-600 text-sm flex-1 text-center';

        const nextBtn = document.createElement('button');
        nextBtn.id = 'next-page-btn';
        nextBtn.type = 'button';
        nextBtn.className = 'bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md text-sm font-medium';
        nextBtn.textContent = PAGINATION_LABELS.next;

        wrapper.appendChild(prevBtn);
        wrapper.appendChild(pageIndicator);
        wrapper.appendChild(nextBtn);
        return wrapper;
    }

    /** Add page headers to sidebar navigation */
    function organiseSidebar() {
        const sidebar = document.getElementById('section-navigation-sidebar');
        if (!sidebar) return;
        const list = sidebar.querySelector('ul.space-y-2');
        if (!list) return;

        // Only add page headers if we have multiple pages
        if (pages.length <= 1) return;

        const processedPages = new Set();
        const listItems = Array.from(list.children);
        listItems.forEach(li => {
            const link = li.querySelector('.section-link');
            if (!link) return;
            const pNum = parseInt(link.dataset.pageNumber || '1');
            const pName = link.dataset.pageName || `Page ${pNum}`;
            if (!processedPages.has(pNum)) {
                const headerLi = document.createElement('li');
                headerLi.textContent = pName;
                headerLi.className = 'text-xs font-semibold text-gray-500 mt-4 mb-1 uppercase tracking-wide';
                list.insertBefore(headerLi, li);
                processedPages.add(pNum);
            }
        });
    }

    /** Hook clicks on section links so they switch pages automatically */
    function hookSectionLinks() {
        // Only hook section links if we have multiple pages
        if (pages.length <= 1) return;

        document.querySelectorAll('.section-link').forEach(link => {
            link.addEventListener('click', function (e) {
                // Prevent native anchor/hash scrolling. We'll manage scroll manually to avoid
                // window + main container scroll fighting (which can cause layout "jumps"/blank space).
                if (e) e.preventDefault();
                const targetPage = parseInt(this.dataset.pageNumber || '1');
                const targetSection = this.dataset.sectionId;
                const idx = pages.findIndex(p => p.number === targetPage);

                if (idx !== -1 && idx !== currentPageIdx) {
                    changePage(idx, false);
                }

                // Update current section and save it
                if (targetSection) {
                    currentSection = targetSection;
                    saveCurrentSection(storageKey, targetSection);
                    updateURLWithPage(currentPageIdx, targetSection);

                    // Scroll to the section
                    scrollToSection(targetSection);
                }
            });
        });
    }

    /** Generate a unique storage key for this form */
    function getFormPageStorageKey() {
        // Use the form action URL or current page URL as part of the key
        const form = document.getElementById('focalDataEntryForm');
        const formAction = form ? form.action : window.location.href;
        const urlHash = btoa(formAction).replace(/[^a-zA-Z0-9]/g, '');
        return `form_page_${urlHash}`;
    }

    /** Get the stored page index from sessionStorage */
    function getStoredPageIndex(storageKey, maxPages) {
        // First try to get from URL parameters (for form reloads with validation errors)
        const urlParams = new URLSearchParams(window.location.search);
        const pageParam = urlParams.get('page');
        if (pageParam) {
            const pageIndex = parseInt(pageParam, 10);
            if (!isNaN(pageIndex) && pageIndex >= 0 && pageIndex < maxPages) {
                debugLog(MODULE_NAME, `Restored page index from URL parameter: ${pageIndex}`);
                return pageIndex;
            }
        }

        // Then try sessionStorage
        try {
            const stored = sessionStorage.getItem(storageKey);
            if (stored !== null) {
                const pageIndex = parseInt(stored, 10);
                if (!isNaN(pageIndex) && pageIndex >= 0 && pageIndex < maxPages) {
                    debugLog(MODULE_NAME, `Restored page index from storage: ${pageIndex}`);
                    return pageIndex;
                }
            }
        } catch (error) {
            debugLog(MODULE_NAME, 'Error reading from sessionStorage:', error);
        }

        debugLog(MODULE_NAME, 'No valid stored page found, defaulting to page 0');
        return 0;
    }

    /** Get the stored section from URL or sessionStorage */
    function getStoredSection() {
        // First try to get from URL hash (for form reloads with validation errors, or dashboard activity links #field-*)
        const urlHash = window.location.hash;
        debugLog(MODULE_NAME, 'getStoredSection: urlHash =', urlHash);
        if (urlHash && urlHash.startsWith('#section-container-')) {
            const sectionId = urlHash.substring(1); // Remove the #
            debugLog(MODULE_NAME, 'getStoredSection: section hash detected:', sectionId);
            return sectionId;
        }
        // Dashboard recent-activity links use #field-<id>; resolve to section container so we show the right page
        if (urlHash && /^#field-\d+$/.test(urlHash)) {
            const fieldId = urlHash.substring(1); // e.g. "field-955"
            const fieldEl = document.getElementById(fieldId);
            debugLog(MODULE_NAME, 'getStoredSection: field hash detected:', fieldId, 'element found:', !!fieldEl);
            if (fieldEl) {
                const section = fieldEl.closest('[id^="section-container-"], #submitter-information-section');
                debugLog(MODULE_NAME, 'getStoredSection: closest section:', section?.id || '(not found)');
                if (section && section.id) {
                    return section.id;
                }
            } else {
                debugLog(MODULE_NAME, 'getStoredSection: trying data-item-id fallback for:', fieldId.replace('field-', ''));
                const byItemId = document.querySelector(`[data-item-id="${fieldId.replace('field-', '')}"]`);
                debugLog(MODULE_NAME, 'getStoredSection: data-item-id element:', !!byItemId);
                if (byItemId) {
                    const section = byItemId.closest('[id^="section-container-"], #submitter-information-section');
                    debugLog(MODULE_NAME, 'getStoredSection: closest section via data-item-id:', section?.id || '(not found)');
                    if (section && section.id) return section.id;
                }
            }
        } else {
            debugLog(MODULE_NAME, 'getStoredSection: hash does not match field pattern. regex test:', /^#field-\d+$/.test(urlHash));
        }

        // Then try sessionStorage
        try {
            const sectionKey = storageKey + '_section';
            const stored = sessionStorage.getItem(sectionKey);
            if (stored !== null) {
                debugLog(MODULE_NAME, `Restored section from storage: ${stored}`);
                return stored;
            }
        } catch (error) {
            debugLog(MODULE_NAME, 'Error reading section from sessionStorage:', error);
        }

        debugLog(MODULE_NAME, 'No valid stored section found');
        return null;
    }

    /** Save the current page index to sessionStorage */
    function saveCurrentPage(storageKey, pageIndex) {
        try {
            sessionStorage.setItem(storageKey, pageIndex.toString());
            debugLog(MODULE_NAME, `Saved page index to storage: ${pageIndex}`);
        } catch (error) {
            debugLog(MODULE_NAME, 'Error saving to sessionStorage:', error);
        }
    }

    /** Save the current section to sessionStorage */
    function saveCurrentSection(storageKey, sectionId) {
        try {
            const sectionKey = storageKey + '_section';
            sessionStorage.setItem(sectionKey, sectionId);
            debugLog(MODULE_NAME, `Saved section to storage: ${sectionId}`);
        } catch (error) {
            debugLog(MODULE_NAME, 'Error saving section to sessionStorage:', error);
        }
    }

    /** Update URL with current page parameter and section */
    function updateURLWithPage(pageIndex, sectionId = null) {
        try {
            const url = new URL(window.location);
            url.searchParams.set('page', pageIndex.toString());

            // Update hash with section if provided
            if (sectionId) {
                url.hash = sectionId;
            }

            // Use replaceState to avoid adding to browser history
            window.history.replaceState({}, '', url);
            debugLog(MODULE_NAME, `Updated URL with page parameter: ${pageIndex} and section: ${sectionId}`);
        } catch (error) {
            debugLog(MODULE_NAME, 'Error updating URL:', error);
        }
    }

    /** Find the scrollable container (main element or window) */
    function getScrollableContainer(element) {
        // Check if main element is scrollable
        const mainElement = document.querySelector('main[style*="overflow-y"]') ||
                          document.querySelector('main');

        if (mainElement) {
            const isScrollable = mainElement.scrollHeight > mainElement.clientHeight;
            debugLog(MODULE_NAME, 'Checking scrollable container:', {
                mainElementFound: !!mainElement,
                scrollHeight: mainElement.scrollHeight,
                clientHeight: mainElement.clientHeight,
                isScrollable: isScrollable,
                computedOverflow: window.getComputedStyle(mainElement).overflowY,
                maxHeight: window.getComputedStyle(mainElement).maxHeight
            });

            if (isScrollable) {
                return mainElement;
            }
        }

        // Fallback to window
        debugLog(MODULE_NAME, 'Using window as scrollable container');
        return window;
    }

    /** Scroll to a field element by id (e.g. "field-955") - delegates to top-level helpers */
    function scrollToField(fieldId) {
        debugLog(MODULE_NAME, 'scrollToField:paginated: called with:', fieldId);
        if (!fieldId) return;
        const rawId = fieldId.replace('field-', '');
        const el = document.getElementById(fieldId)
            || document.querySelector(`[data-item-id="${rawId}"]`)
            || document.querySelector(`label[for="${fieldId}"]`);
        debugLog(MODULE_NAME, 'scrollToField:paginated: element found:', !!el, el?.tagName, el?.id);
        if (!el) return;
        requestAnimationFrame(() => {
            _scrollElementIntoView(el);
            _highlightField(el);
        });
    }

    // afterFormReady: use top-level _afterFormReady

    /** Scroll to section if it exists and is visible */
    function scrollToSection(sectionId) {
        if (!sectionId) return;

        const section = document.getElementById(sectionId);
        if (section && section.style.display !== 'none') {
            // Use setTimeout to ensure the page change has completed
            setTimeout(() => {
                // Find the scrollable container
                const scrollContainer = getScrollableContainer(section);
                const isMainContainer = scrollContainer !== window;
                // Use CSS scroll-margin-top (Tailwind `scroll-mt-*`) as the single source of truth
                // for header offset. This avoids scrollIntoView() side effects (window scroll changes).
                const sectionRect = section.getBoundingClientRect();
                const computed = window.getComputedStyle(section);
                const scrollMarginTop = parseInt(computed.scrollMarginTop || '0', 10) || 80;
                const paddingBottom = 16;

                let targetTop;
                if (isMainContainer) {
                    const containerRect = scrollContainer.getBoundingClientRect();
                    const visibleTop = containerRect.top + scrollMarginTop;
                    const visibleBottom = containerRect.bottom - paddingBottom;
                    const sectionTopRel = sectionRect.top - containerRect.top;

                    if (sectionRect.top < visibleTop) {
                        // Scroll up just enough to bring the top into view (below header offset)
                        targetTop = Math.max(0, scrollContainer.scrollTop + sectionTopRel - scrollMarginTop);
                    } else if (sectionRect.bottom > visibleBottom) {
                        // Scroll down just enough to bring the bottom into view
                        const delta = sectionRect.bottom - visibleBottom;
                        targetTop = Math.max(0, scrollContainer.scrollTop + delta);
                    } else {
                        // Already in view; avoid any scroll to prevent "over-scrolling"
                        debugLog(MODULE_NAME, `Section already in view, no scroll: ${sectionId}`);
                        return;
                    }

                    scrollContainer.scrollTo({ top: targetTop, behavior: 'smooth' });
                } else {
                    const visibleTop = scrollMarginTop;
                    const visibleBottom = window.innerHeight - paddingBottom;

                    if (sectionRect.top < visibleTop) {
                        targetTop = Math.max(0, window.pageYOffset + sectionRect.top - scrollMarginTop);
                    } else if (sectionRect.bottom > visibleBottom) {
                        const delta = sectionRect.bottom - visibleBottom;
                        targetTop = Math.max(0, window.pageYOffset + delta);
                    } else {
                        debugLog(MODULE_NAME, `Section already in view, no scroll: ${sectionId}`);
                        return;
                    }

                    window.scrollTo({ top: targetTop, behavior: 'smooth' });
                }

                debugLog(MODULE_NAME, `Scrolled to section: ${sectionId}`, {
                    scrollContainer: isMainContainer ? 'main' : 'window',
                    scrollMarginTop,
                    targetTop,
                    paddingBottom
                });
            }, 100);
        } else {
            debugLog(MODULE_NAME, `Section not found or not visible: ${sectionId}`);
        }
    }

    // Add event listener for beforeunload to save current page and section
    window.addEventListener('beforeunload', function() {
        saveCurrentPage(storageKey, currentPageIdx);
        if (currentSection) {
            saveCurrentSection(storageKey, currentSection);
        }
    });

    // Add event listener for form submission to save current page and section
    const form = document.getElementById('focalDataEntryForm');
    if (form) {
        form.addEventListener('submit', function() {
            saveCurrentPage(storageKey, currentPageIdx);
            if (currentSection) {
                saveCurrentSection(storageKey, currentSection);
            }
        });
    }

    // Clear page state when form is successfully submitted
    // Listen for successful form submission (this will be triggered by AJAX save or form submission)
    document.addEventListener('formSubmitted', function() {
        try {
            sessionStorage.removeItem(storageKey);
            sessionStorage.removeItem(storageKey + '_section');
            debugLog(MODULE_NAME, 'Cleared page and section state after successful form submission');
        } catch (error) {
            debugLog(MODULE_NAME, 'Error clearing page state:', error);
        }
    });

    // Clear page state when user navigates away from the form page
    window.addEventListener('pagehide', function() {
        // Only clear if we're actually leaving the form page (not just switching tabs)
        if (document.visibilityState === 'hidden') {
            try {
                sessionStorage.removeItem(storageKey);
                sessionStorage.removeItem(storageKey + '_section');
                debugLog(MODULE_NAME, 'Cleared page and section state on page hide');
            } catch (error) {
                debugLog(MODULE_NAME, 'Error clearing page state on page hide:', error);
            }
        }
    });
}
