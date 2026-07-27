// Tooltip positioning for entry form question/indicator tooltips.
//
// Tooltips stay as DOM children so CSS descendant-selector styling is preserved.
// position:fixed is applied inline so the box escapes overflow:hidden ancestors.
//
// The ::after arrow is controlled via CSS custom properties so it always points
// at the icon regardless of how far the tooltip box has been clamped, and flips
// direction when the box appears above the icon instead of below.
//
// A 150 ms hover-bridge delay lets the mouse travel from the trigger icon to
// the tooltip without it vanishing, keeping interactive links reachable.
//
// When the page (or any scrollable ancestor) is scrolled, positionTooltip is
// called again via requestAnimationFrame so the tooltip follows the icon
// smoothly — getBoundingClientRect() always returns live viewport coordinates.

const ENTRY_FORM_TOOLTIP_SELECTORS = [
  '.indicator-definition-tooltip',
  '.question-unit-tooltip',
];

const MARGIN     = 8;  // px gap between trigger icon and tooltip box
const ARROW_HALF = 5;  // matches border-width: 5px in the ::after rule
const ARROW_MIN  = 10; // minimum distance from tooltip edge to arrow centre

// Module-level reference so the scroll handler can always reach the active tooltip.
let _activeContainer  = null;
let _activeHideTimer  = null;
let _scrollRafPending = false;

/** Returns the viewport x coordinate the tooltip must not cross on the left.
 *  Reads the admin sidebar's live right edge so it works for both expanded
 *  (240 px) and collapsed (72 px) states. Falls back to MARGIN for non-admin
 *  views that have no sidebar. */
function getLeftBound() {
  const sidebar = document.getElementById('adminSidebar');
  if (sidebar) {
    const r = sidebar.getBoundingClientRect().right;
    if (r > 0) return r + MARGIN;
  }
  return MARGIN;
}

function positionTooltip(tooltipContainer) {
  const tooltip = tooltipContainer.querySelector('.tooltip-text');
  if (!tooltip) return;

  const iconRect = tooltipContainer.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  // Render at (0,0) hidden to get true width before committing to a position.
  // Clear `right` so the CSS `right:0` fallback doesn't fight the inline `left`.
  tooltip.style.position   = 'fixed';
  tooltip.style.right      = 'auto';
  tooltip.style.left       = '0';
  tooltip.style.top        = '0';
  tooltip.style.transform  = 'none';
  tooltip.style.visibility = 'hidden';
  tooltip.style.display    = 'block';

  const tw = tooltip.offsetWidth;
  const th = tooltip.offsetHeight;

  // ── Vertical: below (preferred) or above ────────────────────────────────
  const spaceBelow = vh - iconRect.bottom - MARGIN;
  const spaceAbove = iconRect.top - MARGIN;
  const isAbove    = spaceBelow < th && spaceAbove > spaceBelow;

  let top, transform;
  if (isAbove) {
    top       = iconRect.top - MARGIN;
    transform = 'translateY(-100%)';
  } else {
    top       = iconRect.bottom + MARGIN;
    transform = 'none';
  }

  // ── Horizontal: right-align tooltip with icon's right edge ──────────────
  // Matches the original CSS `right:0` strategy so the ::after arrow (at
  // right:12px inside the box) naturally lands near the icon. Clamped so
  // the box never overlaps the admin sidebar or the right viewport edge.
  const leftBound = getLeftBound();
  let left = iconRect.right - tw;
  left = Math.max(leftBound, Math.min(left, vw - tw - MARGIN));

  tooltip.style.left      = `${left}px`;
  tooltip.style.top       = `${top}px`;
  tooltip.style.transform = transform;

  // ── Arrow: track the icon centre, flip direction for above/below ─────────
  const iconCenterX = iconRect.left + iconRect.width / 2;
  const rawArrow    = Math.round(iconCenterX - left - ARROW_HALF);
  const arrowLeft   = Math.max(ARROW_MIN, Math.min(rawArrow, tw - ARROW_MIN - ARROW_HALF * 2));

  tooltip.style.setProperty('--tooltip-arrow-left',  `${arrowLeft}px`);
  tooltip.style.setProperty('--tooltip-arrow-right', 'auto');

  if (isAbove) {
    tooltip.style.setProperty('--tooltip-arrow-bottom', 'auto');
    tooltip.style.setProperty('--tooltip-arrow-top',    '100%');
    tooltip.style.setProperty('--tooltip-arrow-color',  '#1f2937 transparent transparent transparent');
  } else {
    tooltip.style.setProperty('--tooltip-arrow-bottom', '100%');
    tooltip.style.setProperty('--tooltip-arrow-top',    'auto');
    tooltip.style.setProperty('--tooltip-arrow-color',  'transparent transparent #1f2937 transparent');
  }

  tooltip.style.visibility = 'visible';
  tooltip.style.opacity    = '1';
}

function hideTooltip(tooltipContainer) {
  if (!tooltipContainer) return;
  const tooltip = tooltipContainer.querySelector('.tooltip-text');
  if (!tooltip) return;
  tooltip.style.visibility = 'hidden';
  tooltip.style.opacity    = '0';
  // Do NOT touch position/left/top/right or CSS variables here.
  // The CSS rule has `transition: opacity .3s` so the fade takes 300 ms.
  // Resetting position fixed→absolute mid-transition reflows the element to
  // wrong absolute coordinates and causes a visible flash in the corner.
  // positionTooltip() resets all inline coordinates on the next mouseenter.
  if (_activeContainer === tooltipContainer) _activeContainer = null;
}

function bindTooltipEvents(container) {
  if (container.dataset.tooltipBound === 'true') return;
  container.dataset.tooltipBound = 'true';

  const show = () => {
    clearTimeout(_activeHideTimer);
    // Close any tooltip that was open on a different icon.
    if (_activeContainer && _activeContainer !== container) {
      hideTooltip(_activeContainer);
    }
    _activeContainer = container;
    positionTooltip(container);
  };

  const scheduleHide = () => {
    clearTimeout(_activeHideTimer);
    _activeHideTimer = setTimeout(() => hideTooltip(container), 150);
  };

  container.addEventListener('mouseenter', show);
  container.addEventListener('mouseleave', scheduleHide);

  // Bind on the tooltip itself so hovering over content cancels the pending hide.
  const tooltip = container.querySelector('.tooltip-text');
  if (tooltip) {
    tooltip.addEventListener('mouseenter', () => clearTimeout(_activeHideTimer));
    tooltip.addEventListener('mouseleave', scheduleHide);
  }
}

/** When any scrollable ancestor scrolls, reposition the active tooltip so it
 *  follows the icon. Throttled with requestAnimationFrame to avoid jank.
 *  getBoundingClientRect() always returns live viewport coordinates, so calling
 *  positionTooltip() on scroll makes the tooltip track the icon exactly. */
function onScroll() {
  if (!_activeContainer || _scrollRafPending) return;
  _scrollRafPending = true;
  requestAnimationFrame(() => {
    _scrollRafPending = false;
    if (_activeContainer) positionTooltip(_activeContainer);
  });
}

export function initTooltips() {
  // Expose globally for explicit callers (e.g. form-builder template-variables.js).
  window.positionTooltip = positionTooltip;

  // Wire up JS-driven positioning for all entry-form tooltip containers.
  ENTRY_FORM_TOOLTIP_SELECTORS.forEach(selector => {
    document.querySelectorAll(selector).forEach(bindTooltipEvents);
  });

  // Single capture-phase scroll listener catches scroll from any ancestor
  // (scroll does not bubble, so capture is required). Guarded so multiple
  // initTooltips() calls don't stack listeners.
  if (!window._entryTooltipScrollBound) {
    window._entryTooltipScrollBound = true;
    window.addEventListener('scroll', onScroll, { passive: true, capture: true });
  }
}
