/**
 * Sections Pane Responsive System
 *
 * Features:
 * - Large screens (≥1100px): Static pane with manual collapse/expand
 * - Small screens (<1100px): Mobile sidebar overlay with toggle button
 * - Force mobile mode: X button forces mobile behavior on large screens
 * - Admin sidebar integration: Adjusts button positions automatically
 * - State persistence: Remembers collapse state (but not force mobile mode)
 */

// Constants
const BREAKPOINT_LARGE = 1100;
const STORAGE_KEY = 'ifrc-sidebar-collapsed';
const RESIZE_DEBOUNCE_MS = 150;
const POSITION_SYNC_DELAY_MS = 50;
const FAB_SPACING = -5; // Negative spacing for seamless hover overlap

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
  ADMIN_TOGGLE: 'sidebarToggle'
};

/**
 * Main controller class for sidebar collapse functionality
 */
class SidebarCollapseController {
  constructor() {
    this.elements = {};
    this.isLargeScreen = () => window.innerWidth >= BREAKPOINT_LARGE;
    this.resizeTimeout = null;
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
   * Mobile sidebar operations
   */
  closeMobileSidebar() {
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

    // Hide expand button
    if (this.elements.expandbutton) {
      this.elements.expandbutton.style.display = 'none';
    }
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
        const rect = mobiletoggle.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
          fabmenu.style.left = `${Math.round(rect.left)}px`;
        } else {
          fabmenu.style.left = this.getAdminSidebarAdjustedPosition();
        }
        const toggleBottomPx = parseInt(
          window.getComputedStyle(mobiletoggle).bottom || '24',
          10
        );
        const toggleHeightPx = mobiletoggle.offsetHeight || 56;
        fabmenu.style.bottom = `${toggleBottomPx + toggleHeightPx + FAB_SPACING}px`;
        fabmenu.style.display = '';
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

    // Position FAB menu above the toggle button
    if (fabmenu && mobiletoggle) {
      const toggleBottomPx = parseInt(
        window.getComputedStyle(mobiletoggle).bottom || '24',
        10
      );
      const toggleHeightPx = mobiletoggle.offsetHeight || 56;
      fabmenu.style.left = leftPosition;
      fabmenu.style.bottom = (toggleBottomPx + toggleHeightPx + FAB_SPACING) + 'px';
      fabmenu.style.display = '';
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
  }

  /**
   * Handle expand button click
   */
  handleExpandButton() {
    this.setSidebarCollapsed(false);
    this.updateExpandButtonVisibility(false);
    this.updateCollapseToggle(false);
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
      } else {
        this.setSidebarCollapsed(false);
        this.updateExpandButtonVisibility(false);
      }
      this.adjustFloatingButtonPosition();
    }, RESIZE_DEBOUNCE_MS);
  }

  /**
   * Attach all event handlers
   */
  attachEventHandlers() {
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

    // Mobile close button (forces mobile mode)
    if (this.elements.mobileclose) {
      this.elements.mobileclose.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.forceMobileSidebarMode();
      });
    }

    // Overlay click
    if (this.elements.overlay) {
      this.elements.overlay.addEventListener('click', () => this.closeMobileSidebar());
    }

    // Window resize
    window.addEventListener('resize', () => this.handleResize());

    // Close sidebar when clicking section links (mobile only)
    const sectionLinks = this.elements.sidebar?.querySelectorAll('.section-link');
    sectionLinks?.forEach(link => {
      link.addEventListener('click', () => {
        if (!this.isLargeScreen()) {
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
export function initializeSidebarCollapse() {
  const controller = new SidebarCollapseController();
  controller.init();
}

// Auto-initialize
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeSidebarCollapse);
} else {
  initializeSidebarCollapse();
}
