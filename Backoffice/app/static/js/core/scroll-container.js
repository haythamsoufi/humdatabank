/**
 * Scroll helpers for admin layout where <main.admin-scroll-main> is the scroll container.
 * Avoids scrollIntoView(), which can scroll both window and main and leave blank space.
 */

export function getScrollableContainer() {
    const mainElement = document.querySelector('main[style*="overflow-y"]')
        || document.querySelector('main.admin-scroll-main')
        || document.querySelector('main');

    if (mainElement) {
        const style = window.getComputedStyle(mainElement);
        const overflowY = style.overflowY;
        const isScrollable = (overflowY === 'auto' || overflowY === 'scroll')
            && mainElement.scrollHeight > mainElement.clientHeight;
        if (isScrollable) {
            return mainElement;
        }
    }

    return window;
}

/**
 * Clamp admin layout scroll positions after dynamic content height changes.
 * Prevents blank space when <main> scrollTop outlives a shorter layout.
 */
export function stabilizeScrollContainer() {
    window.scrollTo(0, 0);
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;

    const scrollContainer = getScrollableContainer();
    if (scrollContainer === window) {
        return;
    }

    const maxScroll = Math.max(0, scrollContainer.scrollHeight - scrollContainer.clientHeight);
    if (scrollContainer.scrollTop > maxScroll) {
        scrollContainer.scrollTop = maxScroll;
    }
}

/**
 * Run after DOM/layout updates that change content height (e.g. wizard step 3 regroup).
 * Optionally preserves an anchor element's visual position inside the scroll container.
 */
export function stabilizeScrollAfterLayoutChange(anchorElement = null) {
    const scrollContainer = getScrollableContainer();
    const isMainContainer = scrollContainer !== window;
    let anchorOffset = null;

    if (anchorElement && isMainContainer) {
        const containerRect = scrollContainer.getBoundingClientRect();
        anchorOffset = anchorElement.getBoundingClientRect().top - containerRect.top;
    }

    const apply = () => {
        stabilizeScrollContainer();

        if (anchorElement && anchorOffset != null && isMainContainer) {
            const containerRect = scrollContainer.getBoundingClientRect();
            const nextOffset = anchorElement.getBoundingClientRect().top - containerRect.top;
            const drift = nextOffset - anchorOffset;
            if (Math.abs(drift) > 2) {
                scrollContainer.scrollTop = Math.max(0, scrollContainer.scrollTop + drift);
            }
            stabilizeScrollContainer();
        }
    };

    requestAnimationFrame(() => {
        requestAnimationFrame(apply);
    });
}

/**
 * Scroll an element into view only when needed, using the correct scroll container.
 * Returns true when a scroll was performed.
 */
export function scrollElementIntoViewIfNeeded(element, options = {}) {
    if (!element || element.getClientRects().length === 0) {
        return false;
    }

    const {
        behavior = 'smooth',
        scrollMarginTop = null,
        paddingBottom = 16,
    } = options;

    const scrollContainer = getScrollableContainer();
    const isMainContainer = scrollContainer !== window;
    const targetRect = element.getBoundingClientRect();
    const computed = window.getComputedStyle(element);
    const marginTop = scrollMarginTop != null
        ? scrollMarginTop
        : (parseInt(computed.scrollMarginTop || '0', 10) || 80);

    let targetTop;
    let didScroll = false;

    if (isMainContainer) {
        stabilizeScrollContainer();

        const containerRect = scrollContainer.getBoundingClientRect();
        const visibleTop = containerRect.top + marginTop;
        const visibleBottom = containerRect.bottom - paddingBottom;
        const elementTopRel = targetRect.top - containerRect.top;

        if (targetRect.top < visibleTop) {
            targetTop = Math.max(0, scrollContainer.scrollTop + elementTopRel - marginTop);
            didScroll = true;
        } else if (targetRect.bottom > visibleBottom) {
            const delta = targetRect.bottom - visibleBottom;
            targetTop = Math.max(0, scrollContainer.scrollTop + delta);
            didScroll = true;
        } else {
            return false;
        }

        scrollContainer.scrollTo({ top: targetTop, behavior });
    } else {
        const visibleTop = marginTop;
        const visibleBottom = window.innerHeight - paddingBottom;

        if (targetRect.top < visibleTop) {
            targetTop = Math.max(0, window.pageYOffset + targetRect.top - marginTop);
            didScroll = true;
        } else if (targetRect.bottom > visibleBottom) {
            const delta = targetRect.bottom - visibleBottom;
            targetTop = Math.max(0, window.pageYOffset + delta);
            didScroll = true;
        } else {
            return false;
        }

        window.scrollTo({ top: targetTop, behavior });
    }

    return didScroll;
}
