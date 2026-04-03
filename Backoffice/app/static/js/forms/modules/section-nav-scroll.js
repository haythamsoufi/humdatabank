import { debugLog } from './debug.js';

const MODULE_NAME = 'section-nav-scroll';

// Initialize section nav scroll when DOM is ready (handle both loading and already-loaded states)
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSectionNavScroll);
} else {
    // DOM is already loaded, initialize immediately
    initSectionNavScroll();
}

function initSectionNavScroll() {
  const sectionsContainer = document.getElementById('sections-container');
  if (!sectionsContainer) return;

  // If paginated, pagination.js owns all scroll/nav behaviour (including #field-* hashes).
  // Check the server-rendered attribute rather than #page-navigation-controls which is
  // created dynamically by pagination.js and may not exist yet at this point.
  debugLog(MODULE_NAME, 'isPaginated =', sectionsContainer.dataset.isPaginated);
  if (sectionsContainer.dataset.isPaginated === 'true') {
    debugLog(MODULE_NAME, 'paginated → bailing out, deferring to pagination.js');
    return;
  }

  const links = Array.from(document.querySelectorAll('a.section-link'));
  if (!links.length) return;

  const scrollToSection = (sectionId) => {
    if (!sectionId) return;
    const section = document.getElementById(sectionId);
    if (!section) return;

    const scrollContainer = getScrollableContainer();
    const isMainContainer = scrollContainer !== window;

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
        targetTop = Math.max(0, scrollContainer.scrollTop + sectionTopRel - scrollMarginTop);
      } else if (sectionRect.bottom > visibleBottom) {
        const delta = sectionRect.bottom - visibleBottom;
        targetTop = Math.max(0, scrollContainer.scrollTop + delta);
      } else {
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
  };

  const updateHashWithoutScroll = (sectionId) => {
    try {
      const url = new URL(window.location.href);
      url.hash = sectionId || '';
      window.history.replaceState({}, '', url);
    } catch (e) {
      // If URL API fails, don't block scroll.
    }
  };

  links.forEach((link) => {
    link.addEventListener('click', (e) => {
      // Always prevent native hash jump; we handle scroll manually.
      e.preventDefault();

      const sectionId =
        link.dataset.sectionId ||
        (link.getAttribute('href') || '').replace(/^#/, '') ||
        '';

      if (sectionId) updateHashWithoutScroll(sectionId);
      scrollToSection(sectionId);
    });
  });

  // If user loads the page with a hash (or refreshes), align scroll using the same logic.
  // Supports both #section-container-* and #field-* (dashboard activity links).
  const initialHash = (window.location.hash || '').replace(/^#/, '');
  if (initialHash) {
    const isFieldHash = /^field-\d+$/.test(initialHash);
    if (isFieldHash) {
      // Field hashes need the form UI to be visible before scrolling
      afterFormReady(() => scrollToSection(initialHash));
    } else {
      setTimeout(() => scrollToSection(initialHash), 50);
    }
  }
}

/** Run callback after the form UI is visible (formInitialized signal). */
function afterFormReady(callback) {
  if (document.body.dataset.formInitialized === 'true') {
    requestAnimationFrame(callback);
    return;
  }
  const obs = new MutationObserver(() => {
    if (document.body.dataset.formInitialized === 'true') {
      obs.disconnect();
      requestAnimationFrame(callback);
    }
  });
  obs.observe(document.body, { attributes: true, attributeFilter: ['data-form-initialized'] });
  setTimeout(() => obs.disconnect(), 30000);
}

function getScrollableContainer() {
  // Mirror pagination.js logic: prefer scrollable <main>, otherwise window.
  const mainElement = document.querySelector('main[style*="overflow-y"]') || document.querySelector('main');
  if (mainElement) {
    const isScrollable = mainElement.scrollHeight > mainElement.clientHeight;
    if (isScrollable) return mainElement;
  }
  return window;
}
