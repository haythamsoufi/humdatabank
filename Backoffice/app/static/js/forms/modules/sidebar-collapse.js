/**
 * Sections Pane Responsive System
 *
 * Features:
 * - Large screens (≥1100px): Static pane with manual collapse/expand
 * - Small screens (<1100px): Mobile sidebar overlay with toggle button
 * - Force mobile mode: X button forces mobile behavior on large screens
 * - Admin sidebar integration: Adjusts button positions automatically
 * - State persistence: Remembers collapse state (but not force mobile mode)
 * - Hover-visible splitter: drag (or arrow keys) to resize the sections pane
 */

// Constants
const BREAKPOINT_LARGE = 1100;
const STORAGE_KEY = 'ifrc-sidebar-collapsed';
export const SIDEBAR_WIDTH_STORAGE_KEY = 'ifrc-sidebar-width';
const SIDEBAR_MIN_WIDTH_PX = 200;
const SIDEBAR_MAX_WIDTH_PX = 560;
const SIDEBAR_MAX_LAYOUT_RATIO = 0.5;
const SIDEBAR_KEYBOARD_STEP_PX = 16;
const RESIZE_DEBOUNCE_MS = 150;
const POSITION_SYNC_DELAY_MS = 50;
const FAB_SPACING = -5; // Negative spacing for seamless hover overlap

/**
 * Clamp a requested sections-pane width against the layout and hard limits.
 * @param {number} widthPx
 * @param {number} layoutWidthPx
 * @returns {number}
 */
export function clampEntryFormSidebarWidth(widthPx, layoutWidthPx) {
  const requested = Number(widthPx);
  const layoutWidth = Number(layoutWidthPx);
  if (!Number.isFinite(requested)) {
    return SIDEBAR_MIN_WIDTH_PX;
  }
  const maxByLayout = Number.isFinite(layoutWidth)
    ? Math.floor(layoutWidth * SIDEBAR_MAX_LAYOUT_RATIO)
    : SIDEBAR_MAX_WIDTH_PX;
  const max = Math.max(SIDEBAR_MIN_WIDTH_PX, Math.min(SIDEBAR_MAX_WIDTH_PX, maxByLayout));
  return Math.round(Math.min(max, Math.max(SIDEBAR_MIN_WIDTH_PX, requested)));
}

function isRtlDocument() {
  return (document.documentElement.getAttribute('dir') || '').toLowerCase() === 'rtl';
}

// DOM Element IDs
const ELEMENT_IDS = {
  SIDEBAR: 'section-navigation-sidebar',
  COLLAPSE_TOGGLE: 'sidebar-collapse-toggle',
  EXPAND_BUTTON: 'sidebar-expand-button',
  MOBILE_TOGGLE: 'mobile-nav-toggle-button',
  MOBILE_CLOSE: 'mobile-nav-close-button',
  OVERLAY: 'mobile-nav-overlay',
  FAB_MENU: 'fab-menu',
  FAB_PIN: 'fab-pin-btn',
  ADMIN_SIDEBAR: 'adminSidebar',
  ADMIN_TOGGLE: 'sidebarToggle',
  RESIZER: 'entry-form-sidebar-resizer',
  LAYOUT: 'entry-form-layout'
};

/**
 * Main controller class for sidebar collapse functionality
 */
class SidebarCollapseController {
  constructor() {
    this.elements = {};
    this.isLargeScreen = () => window.innerWidth >= BREAKPOINT_LARGE;
    this.resizeTimeout = null;
    this._resizePointerId = null;
    this._resizeMoveHandler = null;
    this._resizeUpHandler = null;
  }

  /**
   * Initialize the controller
   */
  init() {
    this.cacheElements();
    if (!this.elements.sidebar) {
      console.warn('Sections sidebar not found');
      return;
    }

    this.initializeState();
    this.applySavedSidebarWidth();
    this.attachEventHandlers();
    this.initializeFabTooltips();
    this.initSectionNavHoverExpand();
    this.adjustFloatingButtonPosition();

    // Position FAB menu after a short delay to ensure layout is complete
    setTimeout(() => this.adjustFloatingButtonPosition(), POSITION_SYNC_DELAY_MS);
  }

  /**
   * Cache all DOM elements
   */
  cacheElements() {
    Object.entries(ELEMENT_IDS).forEach(([key, id]) => {
      this.elements[key.toLowerCase().replace(/_/g, '')] = document.getElementById(id);
    });
  }

  /**
   * Initialize sidebar state based on screen size and saved preferences
   */
  initializeState() {
    if (this.isLargeScreen()) {
      const savedState = localStorage.getItem(STORAGE_KEY);
      const isCollapsed = savedState === 'true';
      this.setSidebarCollapsed(isCollapsed);
      this.updateExpandButtonVisibility(isCollapsed);
    } else {
      this.setSidebarCollapsed(false);
      this.updateExpandButtonVisibility(false);
    }
  }

  /**
   * Set sidebar collapsed state
   */
  setSidebarCollapsed(collapsed) {
    if (this.elements.sidebar) {
      this.elements.sidebar.setAttribute('data-collapsed', collapsed.toString());
    }
    if (collapsed && this.isLargeScreen()) {
      localStorage.setItem(STORAGE_KEY, 'true');
    } else if (!collapsed && this.isLargeScreen()) {
      localStorage.setItem(STORAGE_KEY, 'false');
    }
  }

  /**
   * Update expand button visibility based on state
   */
  updateExpandButtonVisibility(shouldShow) {
    const { expandbutton } = this.elements;
    if (!expandbutton) return;

    if (shouldShow && this.isLargeScreen()) {
      expandbutton.classList.remove('hidden');
      expandbutton.style.display = 'flex';
    } else {
      expandbutton.classList.add('hidden');
      expandbutton.style.display = 'none';
    }
  }

  /**
   * Update collapse toggle icon and tooltip
   */
  updateCollapseToggle(isCollapsed) {
    const { collapsetoggle } = this.elements;
    if (!collapsetoggle) return;

    collapsetoggle.setAttribute(
      'title',
      isCollapsed ? 'Expand sections panel' : 'Collapse sections panel'
    );

    const icon = collapsetoggle.querySelector('i');
    if (icon) {
      icon.className = isCollapsed
        ? 'fas fa-chevron-right text-lg'
        : 'fas fa-chevron-left text-lg';
    }
  }

  /**
   * True when the sections pane behaves as a slide-over (mobile or forced mobile).
   */
  usesMobileOverlay() {
    const { sidebar } = this.elements;
    if (!sidebar) return false;
    return !this.isLargeScreen() || sidebar.classList.contains('force-mobile-mode');
  }

  /**
   * Show/hide the Save/Submit FAB stack for forced mobile overlay on large screens.
   */
  setFabMenuForceVisible(visible) {
    const { fabmenu } = this.elements;
    if (!fabmenu) return;
    if (visible) {
      fabmenu.classList.add('force-visible');
      fabmenu.classList.remove('xl:hidden');
    } else {
      fabmenu.classList.remove('force-visible');
      fabmenu.classList.add('xl:hidden');
      fabmenu.style.left = '';
      fabmenu.style.bottom = '';
      fabmenu.style.display = '';
    }
  }

  /**
   * Mobile sidebar operations
   */
  closeMobileSidebar() {
    document.dispatchEvent(new CustomEvent('discussion:collapse'));
    const { sidebar, overlay, mobiletoggle } = this.elements;
    if (sidebar) {
      sidebar.classList.add('-translate-x-full');
      sidebar.classList.remove('translate-x-0');
    }
    if (overlay) {
      overlay.classList.add('hidden');
    }
    if (mobiletoggle) {
      mobiletoggle.classList.remove('sidebar-open');
    }
    document.body.classList.remove('overflow-hidden');
    document.body.classList.remove('entry-sections-nav-open');
    this.adjustFloatingButtonPosition();
  }

  openMobileSidebar() {
    const { sidebar, overlay, mobiletoggle } = this.elements;
    if (sidebar) {
      sidebar.classList.remove('-translate-x-full');
      sidebar.classList.add('translate-x-0');
    }
    if (overlay) {
      overlay.classList.remove('hidden');
    }
    if (mobiletoggle) {
      mobiletoggle.classList.add('sidebar-open');
    }
    document.body.classList.add('overflow-hidden');
    document.body.classList.add('entry-sections-nav-open');
  }

  /**
   * Force mobile mode (when X button is clicked on large screens)
   */
  forceMobileSidebarMode() {
    this.closeMobileSidebar();
    if (this.elements.sidebar) {
      this.elements.sidebar.classList.add('force-mobile-mode');
    }

    // Show mobile toggle button
    if (this.elements.mobiletoggle) {
      const classesToRemove = ['xl:hidden', 'lg:hidden', 'md:hidden', 'sm:hidden', 'hidden'];
      classesToRemove.forEach(cls => this.elements.mobiletoggle.classList.remove(cls));
      this.elements.mobiletoggle.style.display = 'flex';
      this.elements.mobiletoggle.style.visibility = 'visible';
      this.elements.mobiletoggle.classList.add('force-visible');
      this.elements.mobiletoggle.classList.remove('sidebar-open');
    }

    this.setFabMenuForceVisible(true);
    this.clearSidebarWidthStyles();

    // Hide expand button
    if (this.elements.expandbutton) {
      this.elements.expandbutton.style.display = 'none';
    }

    this.adjustFloatingButtonPosition();
  }

  /**
   * Restore pane mode (normal large screen behavior)
   */
  restorePaneMode() {
    if (this.elements.sidebar) {
      this.elements.sidebar.classList.remove('force-mobile-mode');
    }
    this.closeMobileSidebar();
    this.setSidebarCollapsed(false);

    // Restore button visibility
    if (this.elements.mobiletoggle) {
      this.elements.mobiletoggle.style.display = '';
      this.elements.mobiletoggle.style.visibility = '';
      this.elements.mobiletoggle.classList.add('xl:hidden');
      this.elements.mobiletoggle.classList.remove('force-visible');
    }
    if (this.elements.expandbutton) {
      this.elements.expandbutton.style.display = '';
    }
    this.setFabMenuForceVisible(false);
    this.applySavedSidebarWidth();
  }

  /**
   * Center the Save/Submit FAB stack on the sections toggle button.
   */
  alignFabMenuToToggle(fabmenu, mobiletoggle) {
    if (!fabmenu || !mobiletoggle) return;

    const toggleRect = mobiletoggle.getBoundingClientRect();
    if (toggleRect.width <= 0 || toggleRect.height <= 0) return;

    const menuWidth = fabmenu.offsetWidth || toggleRect.width;
    const centeredLeft = toggleRect.left + (toggleRect.width - menuWidth) / 2;

    fabmenu.style.left = `${Math.round(centeredLeft)}px`;

    const toggleBottomPx = parseFloat(window.getComputedStyle(mobiletoggle).bottom) || 24;
    const toggleHeightPx = mobiletoggle.offsetHeight || toggleRect.height;
    fabmenu.style.bottom = `${toggleBottomPx + toggleHeightPx + FAB_SPACING}px`;
    fabmenu.style.display = '';
  }

  /**
   * Adjust floating button positions based on screen size and admin sidebar state
   */
  adjustFloatingButtonPosition() {
    const leftPosition = this.getAdminSidebarAdjustedPosition();

    // On large screens, adjust based on admin sidebar state
    if (this.isLargeScreen()) {
      this.setButtonPositions(leftPosition);
    } else {
      // Small screens: pin Save/Submit FAB column above the sections toggle (toggle uses CSS)
      const { fabmenu, mobiletoggle } = this.elements;
      if (fabmenu && mobiletoggle) {
        this.alignFabMenuToToggle(fabmenu, mobiletoggle);
      } else {
        this.clearInlinePositions();
      }
    }
  }

  /**
   * Clear inline position styles on small screens
   */
  clearInlinePositions() {
    const { mobiletoggle, expandbutton, fabmenu } = this.elements;

    if (mobiletoggle) mobiletoggle.style.left = '';
    if (expandbutton) expandbutton.style.left = '';
    if (fabmenu) {
      fabmenu.style.left = '';
      fabmenu.style.bottom = '';
      fabmenu.style.display = '';
    }
  }

  /**
   * Get left position adjusted for admin sidebar state
   */
  getAdminSidebarAdjustedPosition() {
    const { adminsidebar } = this.elements;
    if (!adminsidebar) return '24px'; // Default position

    const isCollapsed = adminsidebar.classList.contains('collapsed');
    const isInitiallyCollapsed = document.documentElement.classList.contains('sidebar-initially-collapsed');
    const actuallyCollapsed = isCollapsed || isInitiallyCollapsed;

    return actuallyCollapsed ? '104px' : '294px';
  }

  /**
   * Set button positions on large screens
   */
  setButtonPositions(leftPosition) {
    const { mobiletoggle, expandbutton, fabmenu } = this.elements;

    if (mobiletoggle) {
      mobiletoggle.style.left = leftPosition;
    }
    if (expandbutton) {
      expandbutton.style.left = leftPosition;
    }

    // Position FAB menu above the toggle button, centered horizontally
    if (fabmenu && mobiletoggle) {
      this.alignFabMenuToToggle(fabmenu, mobiletoggle);
    }
  }

  /**
   * Handle collapse toggle click
   */
  handleCollapseToggle() {
    const isCollapsed = this.elements.sidebar?.getAttribute('data-collapsed') === 'true';
    const newState = !isCollapsed;

    this.setSidebarCollapsed(newState);
    this.updateExpandButtonVisibility(newState);
    this.updateCollapseToggle(newState);
    if (!newState) {
      this.applySavedSidebarWidth();
    }
  }

  /**
   * Handle expand button click
   */
  handleExpandButton() {
    this.setSidebarCollapsed(false);
    this.updateExpandButtonVisibility(false);
    this.updateCollapseToggle(false);
    this.applySavedSidebarWidth();
  }

  /**
   * Handle mobile toggle click
   */
  handleMobileToggle() {
    const isOpen = this.elements.sidebar?.classList.contains('translate-x-0');
    if (isOpen) {
      this.closeMobileSidebar();
    } else {
      this.openMobileSidebar();
    }
  }

  /**
   * Handle window resize
   */
  handleResize() {
    clearTimeout(this.resizeTimeout);
    this.resizeTimeout = setTimeout(() => {
      if (this.isLargeScreen()) {
        const savedState = localStorage.getItem(STORAGE_KEY);
        if (savedState !== null) {
          const isCollapsed = savedState === 'true';
          this.setSidebarCollapsed(isCollapsed);
          this.updateExpandButtonVisibility(isCollapsed);
        }
        this.closeMobileSidebar();
        this.applySavedSidebarWidth();
      } else {
        this.setSidebarCollapsed(false);
        this.updateExpandButtonVisibility(false);
        this.clearSidebarWidthStyles();
      }
      this.adjustFloatingButtonPosition();
    }, RESIZE_DEBOUNCE_MS);
  }

  /**
   * True when the hover splitter can change the sections pane width.
   */
  canResizeSidebar() {
    const { sidebar } = this.elements;
    if (!sidebar || !this.isLargeScreen()) return false;
    if (sidebar.classList.contains('force-mobile-mode')) return false;
    return sidebar.getAttribute('data-collapsed') !== 'true';
  }

  getSidebarWidthPx() {
    return this.elements.sidebar?.getBoundingClientRect().width || SIDEBAR_MIN_WIDTH_PX;
  }

  getLayoutWidthPx() {
    return this.elements.layout?.getBoundingClientRect().width || window.innerWidth || 0;
  }

  syncResizerAria(widthPx) {
    const { resizer, sidebar } = this.elements;
    if (!resizer) return;
    const layoutWidth = this.getLayoutWidthPx();
    const maxByLayout = Math.floor(layoutWidth * SIDEBAR_MAX_LAYOUT_RATIO);
    const max = Math.max(SIDEBAR_MIN_WIDTH_PX, Math.min(SIDEBAR_MAX_WIDTH_PX, maxByLayout));
    const value = Math.round(widthPx ?? sidebar?.getBoundingClientRect().width ?? 0);
    resizer.setAttribute('aria-valuemin', String(SIDEBAR_MIN_WIDTH_PX));
    resizer.setAttribute('aria-valuemax', String(max));
    if (value) {
      resizer.setAttribute('aria-valuenow', String(value));
    }
  }

  setSidebarWidthPx(widthPx, { persist } = {}) {
    const { sidebar } = this.elements;
    if (!sidebar) return 0;
    const clamped = clampEntryFormSidebarWidth(widthPx, this.getLayoutWidthPx());
    sidebar.style.width = `${clamped}px`;
    sidebar.style.minWidth = `${clamped}px`;
    sidebar.style.maxWidth = `${clamped}px`;
    sidebar.style.flexShrink = '0';
    this.syncResizerAria(clamped);
    if (persist) {
      try {
        localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(clamped));
      } catch (e) {
        /* ignore quota / private-mode failures */
      }
    }
    return clamped;
  }

  clearSidebarWidthStyles() {
    const { sidebar } = this.elements;
    if (!sidebar) return;
    sidebar.style.width = '';
    sidebar.style.minWidth = '';
    sidebar.style.maxWidth = '';
    sidebar.style.flexShrink = '';
  }

  applySavedSidebarWidth() {
    if (!this.canResizeSidebar()) return;
    let raw = null;
    try {
      raw = localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY);
    } catch (e) {
      return;
    }
    const parsed = parseInt(raw, 10);
    if (!Number.isFinite(parsed)) {
      this.syncResizerAria();
      return;
    }
    this.setSidebarWidthPx(parsed, { persist: false });
  }

  resetSidebarWidth() {
    this.clearSidebarWidthStyles();
    try {
      localStorage.removeItem(SIDEBAR_WIDTH_STORAGE_KEY);
    } catch (e) {
      /* ignore */
    }
    this.syncResizerAria();
  }

  stopSidebarResize() {
    if (this._resizeMoveHandler) {
      window.removeEventListener('pointermove', this._resizeMoveHandler);
    }
    if (this._resizeUpHandler) {
      window.removeEventListener('pointerup', this._resizeUpHandler);
      window.removeEventListener('pointercancel', this._resizeUpHandler);
    }
    this._resizeMoveHandler = null;
    this._resizeUpHandler = null;
    document.body.classList.remove('entry-form-sidebar-resizing');
    const { resizer } = this.elements;
    if (resizer && this._resizePointerId != null) {
      try {
        resizer.releasePointerCapture(this._resizePointerId);
      } catch (e) {
        /* already released */
      }
    }
    this._resizePointerId = null;
  }

  startSidebarResize(event) {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    if (!this.canResizeSidebar()) return;
    event.preventDefault();

    const { sidebar, resizer } = this.elements;
    if (!sidebar || !resizer) return;

    this.stopSidebarResize();
    this._resizePointerId = event.pointerId;
    try {
      resizer.setPointerCapture(event.pointerId);
    } catch (e) {
      /* setPointerCapture is optional */
    }

    const startX = event.clientX;
    const startWidth = sidebar.getBoundingClientRect().width;
    const rtl = isRtlDocument();
    document.body.classList.add('entry-form-sidebar-resizing');

    this._resizeMoveHandler = (moveEvent) => {
      if (moveEvent.pointerId !== this._resizePointerId) return;
      const delta = moveEvent.clientX - startX;
      this.setSidebarWidthPx(startWidth + (rtl ? -delta : delta), { persist: false });
    };
    this._resizeUpHandler = (upEvent) => {
      if (upEvent.pointerId !== this._resizePointerId) return;
      this.stopSidebarResize();
      this.setSidebarWidthPx(this.getSidebarWidthPx(), { persist: true });
    };

    window.addEventListener('pointermove', this._resizeMoveHandler);
    window.addEventListener('pointerup', this._resizeUpHandler);
    window.addEventListener('pointercancel', this._resizeUpHandler);
  }

  handleResizerKeydown(event) {
    if (!this.canResizeSidebar()) return;
    const rtl = isRtlDocument();
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
      event.preventDefault();
      const dir = event.key === 'ArrowRight' ? 1 : -1;
      const delta = rtl ? -dir : dir;
      this.setSidebarWidthPx(this.getSidebarWidthPx() + delta * SIDEBAR_KEYBOARD_STEP_PX, {
        persist: true
      });
    } else if (event.key === 'Home') {
      event.preventDefault();
      this.resetSidebarWidth();
    }
  }

  attachResizeHandlers() {
    const { resizer } = this.elements;
    if (!resizer) return;

    resizer.addEventListener('pointerdown', (event) => this.startSidebarResize(event));
    resizer.addEventListener('keydown', (event) => this.handleResizerKeydown(event));
    resizer.addEventListener('dblclick', (event) => {
      event.preventDefault();
      this.resetSidebarWidth();
    });
    this.syncResizerAria();
  }

  /**
   * Attach all event handlers
   */
  attachEventHandlers() {
    this.attachResizeHandlers();

    // Collapse toggle (large screens)
    if (this.elements.collapsetoggle) {
      this.elements.collapsetoggle.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.handleCollapseToggle();
      });
    }

    // Expand button (large screens)
    if (this.elements.expandbutton) {
      this.elements.expandbutton.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.handleExpandButton();
      });
    }

    // Mobile toggle button
    if (this.elements.mobiletoggle) {
      this.elements.mobiletoggle.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.handleMobileToggle();
      });

      // Sync FAB menu position on hover
      if (this.elements.fabmenu) {
        const syncFabPosition = () => {
          setTimeout(() => this.adjustFloatingButtonPosition(), 0);
        };
        this.elements.mobiletoggle.addEventListener('mouseenter', syncFabPosition);
        this.elements.fabmenu.addEventListener('mouseenter', syncFabPosition);
      }

      // Double-click to restore pane mode on large screens
      this.elements.mobiletoggle.addEventListener('dblclick', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (this.isLargeScreen()) {
          this.restorePaneMode();
        }
      });
    }

    // Mobile close button (forces mobile mode on large screens only)
    if (this.elements.mobileclose) {
      this.elements.mobileclose.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (this.isLargeScreen()) {
          this.forceMobileSidebarMode();
        } else {
          this.closeMobileSidebar();
          document.body.classList.remove('overflow-hidden');
        }
      });
    }

    // Overlay click
    if (this.elements.overlay) {
      this.elements.overlay.addEventListener('click', () => this.closeMobileSidebar());
    }

    // Window resize
    window.addEventListener('resize', () => this.handleResize());

    // Close sidebar when clicking section links in overlay mode
    const sectionLinks = this.elements.sidebar?.querySelectorAll('.section-link');
    sectionLinks?.forEach(link => {
      link.addEventListener('click', () => {
        if (
          this.usesMobileOverlay() &&
          this.elements.sidebar?.classList.contains('translate-x-0')
        ) {
          setTimeout(() => this.closeMobileSidebar(), 100);
        }
      });
    });

    // FAB Pin button - restores pane mode on large screens
    if (this.elements.fabpin) {
      this.elements.fabpin.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (this.isLargeScreen()) {
          this.restorePaneMode();
        }
      });
    }

    // Admin sidebar toggle integration
    if (this.elements.admintoggle) {
      this.elements.admintoggle.addEventListener('click', () => {
        setTimeout(() => this.adjustFloatingButtonPosition(), POSITION_SYNC_DELAY_MS);
      });
    }

    // Watch for mainContent class changes (when sidebar collapses/expands)
    const mainContent = document.getElementById('mainContent');
    if (mainContent) {
      const observer = new MutationObserver(() => {
        this.adjustFloatingButtonPosition();
      });
      observer.observe(mainContent, {
        attributes: true,
        attributeFilter: ['class']
      });
    }
  }

  /**
   * Section nav: show full label on one line when hovering truncated names (position:fixed overlay)
   */
  initSectionNavHoverExpand() {
    const sidebar = this.elements.sidebar;
    if (!sidebar) return;

    const overlay = document.createElement('div');
    overlay.setAttribute('id', 'section-nav-hover-expand');
    overlay.setAttribute('aria-hidden', 'true');
    overlay.style.cssText = 'position:fixed;z-index:9999;white-space:nowrap;pointer-events:none;display:none;background:#fff;padding:0 0.5rem 0 0;box-shadow:2px 0 4px rgba(0,0,0,0.08);';
    document.body.appendChild(overlay);

    const showOverlay = (link) => {
      const span = link.querySelector('span.truncate');
      if (!span) return;
      const text = span.textContent || '';
      if (!text) return;
      const rect = span.getBoundingClientRect();
      const cs = window.getComputedStyle(span);
      overlay.textContent = text;
      overlay.style.fontSize = cs.fontSize;
      overlay.style.fontWeight = cs.fontWeight;
      overlay.style.color = cs.color;
      overlay.style.fontFamily = cs.fontFamily;
      overlay.style.lineHeight = cs.lineHeight;
      overlay.style.top = rect.top + 'px';
      overlay.style.left = rect.left + 'px';
      overlay.style.display = 'block';
    };

    const hideOverlay = () => {
      overlay.style.display = 'none';
    };

    const links = sidebar.querySelectorAll('a.section-link');
    links.forEach((link) => {
      link.addEventListener('mouseenter', () => showOverlay(link));
      link.addEventListener('mouseleave', hideOverlay);
    });
  }

  /**
   * Initialize FAB tooltips
   */
  initializeFabTooltips() {
    const fabButtons = document.querySelectorAll('.fab-tooltip');

    fabButtons.forEach(button => {
      const tooltip = button.querySelector('.tooltip-text');
      if (!tooltip) return;

      button.addEventListener('mouseenter', () => {
        tooltip.style.visibility = 'visible';
        tooltip.style.opacity = '1';
        tooltip.style.transform = 'translateY(-50%) translateX(10px)';
      });

      button.addEventListener('mouseleave', () => {
        tooltip.style.visibility = 'hidden';
        tooltip.style.opacity = '0';
        tooltip.style.transform = 'translateY(-50%) translateX(15px)';
      });

      // Prevent tooltip from interfering with button clicks
      tooltip.addEventListener('click', (e) => {
        e.stopPropagation();
      });
    });
  }
}

/**
 * Initialize the sidebar collapse system
 */
let sidebarCollapseController = null;

export function initializeSidebarCollapse() {
  sidebarCollapseController = new SidebarCollapseController();
  sidebarCollapseController.init();
  return sidebarCollapseController;
}

/** Close the sections overlay and restore the floating toggle (shared helper). */
export function closeEntryFormMobileNav() {
  sidebarCollapseController?.closeMobileSidebar();
}

// Auto-initialize
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeSidebarCollapse);
} else {
  initializeSidebarCollapse();
}
