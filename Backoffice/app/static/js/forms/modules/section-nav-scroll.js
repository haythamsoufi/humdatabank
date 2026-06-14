import { debugLog } from './debug.js';

const MODULE_NAME = 'section-nav-scroll';
const ACTIVE_CLASS = 'is-active';
const SCROLL_SPY_PAUSE_MS = 900;

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

  const links = Array.from(document.querySelectorAll('a.section-link'));
  if (!links.length) return;

  const isPaginated = sectionsContainer.dataset.isPaginated === 'true';
  const scrollSpy = createSectionNavScrollSpy(links);
  window.__ifrcSectionNavScrollSpy = scrollSpy;

  // Always highlight the active section while scrolling.
  scrollSpy.init();

  // Paginated templates: pagination.js owns click navigation and hash scrolling.
  if (isPaginated) {
    debugLog(MODULE_NAME, 'paginated → scroll spy only; click nav deferred to pagination.js');
    return;
  }

  debugLog(MODULE_NAME, 'non-paginated → scroll spy + click nav');

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

      if (sectionId) {
        updateHashWithoutScroll(sectionId);
        scrollSpy.setActive(sectionId);
        scrollSpy.pause(SCROLL_SPY_PAUSE_MS);
      }
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
      setTimeout(() => {
        scrollToSection(initialHash);
        scrollSpy.setActive(initialHash);
      }, 50);
    }
  }
}

function createSectionNavScrollSpy(links) {
  const linkById = new Map();
  links.forEach((link) => {
    const id =
      link.dataset.sectionId ||
      (link.getAttribute('href') || '').replace(/^#/, '') ||
      '';
    if (id) linkById.set(id, link);
  });

  let trackableSections = buildTrackableSections(linkById);
  let currentActiveId = null;
  let scrollSpyPausedUntil = 0;
  let scrollTicking = false;
  let scrollContainer = null;
  let boundOnScroll = null;
  let initialized = false;

  function buildTrackableSections(map) {
    const items = [];
    map.forEach((link, id) => {
      const el = document.getElementById(id);
      if (el) items.push({ id, el, link });
    });
    items.sort((a, b) => {
      if (a.el === b.el) return 0;
      const position = a.el.compareDocumentPosition(b.el);
      if (position & Node.DOCUMENT_POSITION_FOLLOWING) return -1;
      if (position & Node.DOCUMENT_POSITION_PRECEDING) return 1;
      return 0;
    });
    return items;
  }

  function isSectionVisible(sectionEl) {
    if (!sectionEl) return false;
    if (sectionEl.classList.contains('relevance-hidden')) return false;
    const cs = window.getComputedStyle(sectionEl);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    return sectionEl.getClientRects().length > 0;
  }

  function getScrollMarginTop() {
    const sample = trackableSections.find((item) => isSectionVisible(item.el));
    if (!sample) return 80;
    const computed = window.getComputedStyle(sample.el);
    const parsed = parseInt(computed.scrollMarginTop || '0', 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 80;
  }

  function getActivationLine(container) {
    const scrollMarginTop = getScrollMarginTop();
    if (container === window) return scrollMarginTop;
    return container.getBoundingClientRect().top + scrollMarginTop;
  }

  function isNearBottom(container) {
    const threshold = 48;
    if (container === window) {
      const scrollTop = window.pageYOffset || document.documentElement.scrollTop || 0;
      const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
      const scrollHeight = document.documentElement.scrollHeight || document.body.scrollHeight || 0;
      return scrollTop + viewportHeight >= scrollHeight - threshold;
    }
    return container.scrollTop + container.clientHeight >= container.scrollHeight - threshold;
  }

  function pickActiveSectionId(container) {
    const visible = trackableSections.filter((item) => isSectionVisible(item.el));
    if (!visible.length) return null;

    if (isNearBottom(container)) {
      return visible[visible.length - 1].id;
    }

    const activationLine = getActivationLine(container);
    let activeId = visible[0].id;
    for (const item of visible) {
      const rect = item.el.getBoundingClientRect();
      if (rect.top <= activationLine + 4) {
        activeId = item.id;
      } else {
        break;
      }
    }
    return activeId;
  }

  function ensureNavLinkVisible(link) {
    const navScroller = document.querySelector('#section-navigation-sidebar .overflow-y-auto');
    if (!navScroller || !link) return;
    const linkRect = link.getBoundingClientRect();
    const scrollerRect = navScroller.getBoundingClientRect();
    if (linkRect.top < scrollerRect.top || linkRect.bottom > scrollerRect.bottom) {
      link.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }

  function setActive(sectionId, { scrollNav = false } = {}) {
    if (!sectionId || sectionId === currentActiveId) return;
    currentActiveId = sectionId;

    links.forEach((link) => {
      const isActive = link.dataset.sectionId === sectionId;
      link.classList.toggle(ACTIVE_CLASS, isActive);
      if (isActive) {
        link.setAttribute('aria-current', 'location');
      } else {
        link.removeAttribute('aria-current');
      }
    });

    if (scrollNav) {
      ensureNavLinkVisible(linkById.get(sectionId));
    }

    debugLog(MODULE_NAME, 'Active section:', sectionId);
  }

  function updateActiveSection() {
    if (Date.now() < scrollSpyPausedUntil) return;
    const container = scrollContainer || getScrollableContainer();
    const nextId = pickActiveSectionId(container);
    if (!nextId) return;
    setActive(nextId, { scrollNav: true });
  }

  function onScroll() {
    if (scrollTicking) return;
    scrollTicking = true;
    requestAnimationFrame(() => {
      updateActiveSection();
      scrollTicking = false;
    });
  }

  function bindScrollListeners() {
    const container = getScrollableContainer();
    if (container === scrollContainer && boundOnScroll) return;

    if (scrollContainer && scrollContainer !== window && boundOnScroll) {
      scrollContainer.removeEventListener('scroll', boundOnScroll);
    } else if (scrollContainer === window && boundOnScroll) {
      window.removeEventListener('scroll', boundOnScroll);
    }

    scrollContainer = container;
    boundOnScroll = onScroll;

    if (container === window) {
      window.addEventListener('scroll', boundOnScroll, { passive: true });
    } else {
      container.addEventListener('scroll', boundOnScroll, { passive: true });
    }
  }

  function refresh() {
    trackableSections = buildTrackableSections(linkById);
    bindScrollListeners();
    updateActiveSection();
  }

  function init() {
    if (initialized) return;
    initialized = true;

    bindScrollListeners();
    window.addEventListener('resize', onScroll, { passive: true });

    document.addEventListener('ifrc:pagination:pageChanged', () => {
      scrollSpyPausedUntil = Date.now() + SCROLL_SPY_PAUSE_MS;
      requestAnimationFrame(refresh);
    });

    afterFormReady(() => {
      refresh();
    });

    // Form may already be ready if modules loaded late.
    if (document.body.dataset.formInitialized === 'true') {
      requestAnimationFrame(refresh);
    }
  }

  return {
    init,
    refresh,
    setActive,
    pause(ms) {
      scrollSpyPausedUntil = Date.now() + ms;
    },
  };
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
