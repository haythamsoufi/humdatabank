/**
 * Phone layout for form-builder action clusters.
 *
 * Desktop keeps the colored icon buttons. At the same 768px breakpoint used
 * by the rest of the builder, those buttons move into a vertical ⋮ menu so
 * section titles and item labels can use the row.
 */

const MOBILE_QUERY = '(max-width: 768px)';
const VIEWPORT_MARGIN = 8;

function isMobileLayout() {
    return window.matchMedia(MOBILE_QUERY).matches;
}

function ensureButtonNames(panel) {
    panel.querySelectorAll('.fb-icon-btn').forEach((btn) => {
        const title = btn.getAttribute('title');
        if (title && !btn.getAttribute('aria-label')) {
            btn.setAttribute('aria-label', title);
        }
    });
}

function clearPlacement(panel) {
    panel.style.top = '';
    panel.style.left = '';
    panel.style.right = '';
    panel.style.bottom = '';
}

export function placeFormBuilderActionMenu(panel, toggle) {
    const rect = toggle.getBoundingClientRect();
    const rtl = document.documentElement.getAttribute('dir') === 'rtl';
    const panelWidth = panel.offsetWidth || panel.getBoundingClientRect().width || 200;
    const panelHeight = panel.offsetHeight || panel.getBoundingClientRect().height || 0;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    let top = rect.bottom + 4;
    if (panelHeight && top + panelHeight > viewportHeight - VIEWPORT_MARGIN) {
        const above = rect.top - 4 - panelHeight;
        top = above >= VIEWPORT_MARGIN
            ? above
            : Math.max(VIEWPORT_MARGIN, viewportHeight - VIEWPORT_MARGIN - panelHeight);
    }

    let left = rtl ? rect.left : rect.right - panelWidth;
    if (left < VIEWPORT_MARGIN) left = VIEWPORT_MARGIN;
    if (left + panelWidth > viewportWidth - VIEWPORT_MARGIN) {
        left = Math.max(VIEWPORT_MARGIN, viewportWidth - VIEWPORT_MARGIN - panelWidth);
    }

    panel.style.right = 'auto';
    panel.style.bottom = 'auto';
    panel.style.top = `${Math.round(top)}px`;
    panel.style.left = `${Math.round(left)}px`;
}

function getPanel(root) {
    if (root._fbActionsPanel && root._fbActionsPanel.isConnected) return root._fbActionsPanel;
    const panel = root.querySelector(':scope > .fb-actions-panel');
    if (panel) root._fbActionsPanel = panel;
    return panel || null;
}

function closeMenu(root) {
    if (!root) return;
    root.classList.remove('is-open');
    const toggle = root.querySelector('.fb-actions-toggle');
    const panel = root._fbActionsPanel;
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
    if (!panel) return;
    panel.classList.remove('fb-actions-panel--floating');
    clearPlacement(panel);
    if (panel.parentElement !== root) root.appendChild(panel);
}

function closeAllMenus(except) {
    document.querySelectorAll('#form-builder-ui .fb-actions.is-open').forEach((root) => {
        if (root !== except) closeMenu(root);
    });
}

function openMenu(root) {
    if (!isMobileLayout()) return;
    const toggle = root.querySelector('.fb-actions-toggle');
    const panel = getPanel(root);
    const builder = document.getElementById('form-builder-ui');
    if (!toggle || !panel || !builder) return;
    closeAllMenus(root);
    ensureButtonNames(panel);
    panel._fbActionsRoot = root;
    // Leave the table's overflow container so the menu is not clipped.
    builder.appendChild(panel);
    panel.classList.add('fb-actions-panel--floating');
    root.classList.add('is-open');
    toggle.setAttribute('aria-expanded', 'true');
    placeFormBuilderActionMenu(panel, toggle);
}

function repositionOpenMenus() {
    if (!isMobileLayout()) {
        closeAllMenus();
        return;
    }
    document.querySelectorAll('#form-builder-ui .fb-actions.is-open').forEach((root) => {
        const toggle = root.querySelector('.fb-actions-toggle');
        const panel = root._fbActionsPanel;
        if (toggle && panel) placeFormBuilderActionMenu(panel, toggle);
    });
}

export function initFormBuilderActionOverflow() {
    const builder = document.getElementById('form-builder-ui');
    if (builder) builder.classList.add('fb-actions-ready');

    if (window.__fbActionsOverflowBound) return;
    window.__fbActionsOverflowBound = true;

    document.addEventListener('click', (event) => {
        const toggle = event.target.closest('.fb-actions-toggle');
        if (toggle && toggle.closest('#form-builder-ui')) {
            event.preventDefault();
            event.stopPropagation();
            const root = toggle.closest('.fb-actions');
            if (!root) return;
            if (root.classList.contains('is-open')) closeMenu(root);
            else openMenu(root);
            return;
        }

        const panel = event.target.closest('.fb-actions-panel');
        if (panel && (panel._fbActionsRoot || panel.closest('.fb-actions'))) {
            closeMenu(panel._fbActionsRoot || panel.closest('.fb-actions'));
            return;
        }

        if (!event.target.closest('#form-builder-ui .fb-actions')) {
            closeAllMenus();
        }
    });

    document.addEventListener('formBuilder:domUpdated', () => {
        document.querySelectorAll('#form-builder-ui > .fb-actions-panel--floating').forEach((panel) => {
            const root = panel._fbActionsRoot;
            if (root && root.isConnected) closeMenu(root);
            else panel.remove();
        });
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') closeAllMenus();
    });

    window.addEventListener('resize', repositionOpenMenus);
    window.addEventListener('scroll', repositionOpenMenus, true);
}
