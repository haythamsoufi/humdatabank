/**
 * Dev tools pane (dashboard + entry form).
 * Style preview and, on the entry form, section-nav preview are tools.
 * Requires .ui-style-root and optional #dev-tools (DEBUG + loopback).
 * The pane starts collapsed. Drag the header to move it; position,
 * open/closed state, and the active tool are saved in this browser.
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'uiStylePreview';
    var LEGACY_STORAGE_KEY = 'dashboardStylePreview';
    var PANE_KEY = 'devToolsPane';
    var LEGACY_PANE_KEY = 'uiStylePreviewPane';
    var ALLOWED = ['ifrc', 'go', 'erp', 'legacy'];
    /* Production/staging always use legacy until a shipped style is chosen. */
    var DEFAULT_STYLE = 'legacy';
    var NAV_STORAGE_KEY = 'sectionNavPreview';
    var NAV_ALLOWED = ['side', 'stepper'];
    var DEFAULT_NAV = 'side';
    var DRAG_THRESHOLD = 4;
    var VIEWPORT_PAD = 8;

    function normalizeStyle(value) {
        return ALLOWED.indexOf(value) !== -1 ? value : DEFAULT_STYLE;
    }

    function readStoredStyle() {
        try {
            var stored = window.localStorage.getItem(STORAGE_KEY);
            if (stored == null) {
                stored = window.localStorage.getItem(LEGACY_STORAGE_KEY);
            }
            return normalizeStyle(stored);
        } catch (err) {
            return DEFAULT_STYLE;
        }
    }

    function writeStoredStyle(style) {
        try {
            window.localStorage.setItem(STORAGE_KEY, style);
        } catch (err) {
            /* ignore quota / private mode */
        }
    }

    function applyStyle(root, style, previewEnabled) {
        var next = previewEnabled ? normalizeStyle(style) : DEFAULT_STYLE;
        root.setAttribute('data-ui-style', next);
        return next;
    }

    function syncButtons(switcher, activeStyle) {
        if (!switcher) {
            return;
        }
        switcher.querySelectorAll('[data-ui-style-option]').forEach(function (btn) {
            var option = btn.getAttribute('data-ui-style-option');
            var isActive = option === activeStyle;
            btn.classList.toggle('is-active', isActive);
            btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });
    }

    function init() {
        var root = document.querySelector('.ui-style-root');
        if (!root) {
            return;
        }

        var previewEnabled = root.getAttribute('data-style-preview') === '1';
        var active = applyStyle(
            root,
            previewEnabled ? readStoredStyle() : DEFAULT_STYLE,
            previewEnabled
        );

        if (!previewEnabled) {
            return;
        }

        var switcher = document.getElementById('dev-tools');
        syncButtons(switcher, active);

        initSectionNavPreview(root, switcher);

        if (!switcher) {
            return;
        }

        switcher.addEventListener('click', function (event) {
            var btn = event.target.closest('[data-ui-style-option]');
            if (!btn || !switcher.contains(btn)) {
                return;
            }
            var next = normalizeStyle(btn.getAttribute('data-ui-style-option'));
            writeStoredStyle(next);
            active = applyStyle(root, next, true);
            syncButtons(switcher, active);
        });

        initPane(switcher);
    }

    function normalizeNav(value) {
        return NAV_ALLOWED.indexOf(value) !== -1 ? value : DEFAULT_NAV;
    }

    function readStoredNav() {
        try {
            return normalizeNav(window.localStorage.getItem(NAV_STORAGE_KEY));
        } catch (err) {
            return DEFAULT_NAV;
        }
    }

    function writeStoredNav(nav) {
        try {
            window.localStorage.setItem(NAV_STORAGE_KEY, nav);
        } catch (err) {
            /* ignore quota / private mode */
        }
    }

    function applySectionNav(root, nav) {
        var next = normalizeNav(nav);
        root.setAttribute('data-section-nav', next);
        placeSectionNavActions(next);
        return next;
    }

    var PAGE_FOOTER_ID = 'section-nav-page-footer';

    function sectionNavPageFooter(create) {
        var footer = document.getElementById(PAGE_FOOTER_ID);
        if (footer || !create) {
            return footer;
        }
        var host = document.getElementById('focalDataEntryForm')
            || document.getElementById('main-form-area')
            || document.getElementById('entry-form-layout');
        if (!host) {
            return null;
        }
        footer = document.createElement('div');
        footer.id = PAGE_FOOTER_ID;
        footer.className = 'section-nav-page-footer';
        host.appendChild(footer);
        return footer;
    }

    function rememberSectionNavHome(el) {
        if (el && !el._sectionNavHome) {
            el._sectionNavHome = el.parentElement;
        }
    }

    /* Stepper keeps the steps at the top. Save, submit, and the other
       pane actions move to the end of the form. */
    function placeSectionNavActions(nav) {
        var buttons = document.getElementById('sidebar-action-buttons');
        var scopes = Array.prototype.slice.call(document.querySelectorAll('.sidebar-scope-actions'));
        if (nav !== 'stepper') {
            scopes.forEach(function (el) {
                if (el._sectionNavHome) {
                    el._sectionNavHome.appendChild(el);
                }
            });
            if (buttons && buttons._sectionNavHome) {
                buttons._sectionNavHome.appendChild(buttons);
            }
            var existing = document.getElementById(PAGE_FOOTER_ID);
            if (existing) {
                existing.remove();
            }
            return;
        }
        var footer = sectionNavPageFooter(true);
        if (!footer) {
            return;
        }
        scopes.forEach(function (el) {
            rememberSectionNavHome(el);
            footer.appendChild(el);
        });
        if (buttons) {
            rememberSectionNavHome(buttons);
            footer.appendChild(buttons);
        }
    }

    function syncNavButtons(switcher, activeNav) {
        if (!switcher) {
            return;
        }
        switcher.querySelectorAll('[data-section-nav-option]').forEach(function (btn) {
            var option = btn.getAttribute('data-section-nav-option');
            var isActive = option === activeNav;
            btn.classList.toggle('is-active', isActive);
            btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });
    }

    function initSectionNavPreview(root, switcher) {
        if (!root || root.getAttribute('data-section-nav-preview') !== '1') {
            return;
        }
        var active = applySectionNav(root, readStoredNav());
        syncNavButtons(switcher, active);
        if (!switcher) {
            return;
        }
        switcher.addEventListener('click', function (event) {
            var btn = event.target.closest('[data-section-nav-option]');
            if (!btn || !switcher.contains(btn)) {
                return;
            }
            var next = normalizeNav(btn.getAttribute('data-section-nav-option'));
            writeStoredNav(next);
            active = applySectionNav(root, next);
            syncNavButtons(switcher, active);
            window.dispatchEvent(new Event('resize'));
        });
    }

    function readPane() {
        var empty = { open: false, x: null, y: null, tool: 'style' };
        try {
            var raw = window.localStorage.getItem(PANE_KEY);
            if (raw == null) {
                raw = window.localStorage.getItem(LEGACY_PANE_KEY);
            }
            var data = JSON.parse(raw || 'null');
            if (!data || typeof data !== 'object') {
                return empty;
            }
            var x = Number(data.x);
            var y = Number(data.y);
            return {
                open: data.open === true,
                x: isFinite(x) ? x : null,
                y: isFinite(y) ? y : null,
                tool: typeof data.tool === 'string' && data.tool ? data.tool : 'style'
            };
        } catch (err) {
            return empty;
        }
    }

    function writePane(state) {
        try {
            var payload = {
                open: state.open === true,
                tool: state.tool || 'style'
            };
            if (typeof state.x === 'number' && typeof state.y === 'number') {
                payload.x = Math.round(state.x);
                payload.y = Math.round(state.y);
            }
            window.localStorage.setItem(PANE_KEY, JSON.stringify(payload));
        } catch (err) {
            /* ignore quota / private mode */
        }
    }

    function initPane(switcher) {
        var dragHandle = switcher.querySelector('[data-dev-tools-drag]');
        var toggle = switcher.querySelector('[data-dev-tools-toggle]');
        var body = switcher.querySelector('[data-dev-tools-body]');
        if (!dragHandle || !toggle || !body) {
            return;
        }

        var state = readPane();
        var positioned = switcher.classList.contains('is-positioned');
        var dragging = false;
        var moved = false;
        var suppressClick = false;
        var startX = 0;
        var startY = 0;
        var originLeft = 0;
        var originTop = 0;

        function place(left, top) {
            switcher.classList.add('is-positioned');
            switcher.style.left = Math.round(left) + 'px';
            switcher.style.top = Math.round(top) + 'px';
            switcher.style.right = 'auto';
            switcher.style.bottom = 'auto';
            switcher.style.insetInlineEnd = 'auto';
            positioned = true;
            state.x = Math.round(left);
            state.y = Math.round(top);
        }

        function clampIntoView(persist) {
            var rect = switcher.getBoundingClientRect();
            var maxLeft = Math.max(VIEWPORT_PAD, window.innerWidth - rect.width - VIEWPORT_PAD);
            var maxTop = Math.max(VIEWPORT_PAD, window.innerHeight - rect.height - VIEWPORT_PAD);
            var nextLeft = Math.min(Math.max(rect.left, VIEWPORT_PAD), maxLeft);
            var nextTop = Math.min(Math.max(rect.top, VIEWPORT_PAD), maxTop);
            if (Math.abs(nextLeft - rect.left) < 0.5 && Math.abs(nextTop - rect.top) < 0.5) {
                return;
            }
            place(nextLeft, nextTop);
            if (persist) {
                writePane(state);
            }
        }

        function setOpen(open) {
            state.open = open === true;
            switcher.classList.toggle('is-collapsed', !state.open);
            if (state.open) {
                body.removeAttribute('hidden');
            } else {
                body.setAttribute('hidden', '');
            }
            toggle.setAttribute('aria-expanded', state.open ? 'true' : 'false');
            writePane(state);
            window.requestAnimationFrame(function () {
                if (positioned || state.open) {
                    clampIntoView(positioned);
                }
            });
        }

        function selectTool(toolId, persist) {
            var safeId = /^[a-z0-9-]+$/.test(toolId) ? toolId : '';
            var known = safeId && switcher.querySelector('[data-dev-tool-panel="' + safeId + '"]');
            var next = known ? safeId : 'style';
            state.tool = next;
            switcher.querySelectorAll('[data-dev-tool]').forEach(function (tab) {
                var on = tab.getAttribute('data-dev-tool') === next;
                if (window.AdminUnderlineTabs) window.AdminUnderlineTabs.setStripButtonActive(tab, on);
                tab.setAttribute('aria-selected', on ? 'true' : 'false');
            });
            switcher.querySelectorAll('[data-dev-tool-panel]').forEach(function (panel) {
                if (panel.getAttribute('data-dev-tool-panel') === next) {
                    panel.removeAttribute('hidden');
                } else {
                    panel.setAttribute('hidden', '');
                }
            });
            if (persist) {
                writePane(state);
            }
        }

        if (positioned && state.x != null && state.y != null) {
            place(state.x, state.y);
            clampIntoView(true);
        }
        selectTool(state.tool, false);
        setOpen(state.open);

        switcher.addEventListener('click', function (event) {
            var tab = event.target.closest('[data-dev-tool]');
            if (!tab || !switcher.contains(tab)) {
                return;
            }
            selectTool(tab.getAttribute('data-dev-tool'), true);
        });

        /* Pointer capture retargets the click to the bar, so listen here
           rather than on the button. Keyboard activation still bubbles up. */
        dragHandle.addEventListener('click', function (event) {
            if (suppressClick) {
                suppressClick = false;
                event.preventDefault();
                event.stopPropagation();
                return;
            }
            setOpen(!state.open);
        });

        dragHandle.addEventListener('pointerdown', function (event) {
            if (event.pointerType === 'mouse' && event.button !== 0) {
                return;
            }
            if (event.target.closest('[data-ui-style-option]')) {
                return;
            }
            var rect = switcher.getBoundingClientRect();
            dragging = true;
            moved = false;
            startX = event.clientX;
            startY = event.clientY;
            originLeft = rect.left;
            originTop = rect.top;
            dragHandle.setPointerCapture(event.pointerId);
        });

        dragHandle.addEventListener('pointermove', function (event) {
            if (!dragging) {
                return;
            }
            var dx = event.clientX - startX;
            var dy = event.clientY - startY;
            if (!moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) {
                return;
            }
            if (!moved) {
                moved = true;
                switcher.classList.add('is-dragging');
            }
            var width = switcher.offsetWidth;
            var height = switcher.offsetHeight;
            var maxLeft = Math.max(VIEWPORT_PAD, window.innerWidth - width - VIEWPORT_PAD);
            var maxTop = Math.max(VIEWPORT_PAD, window.innerHeight - height - VIEWPORT_PAD);
            var left = Math.min(Math.max(originLeft + dx, VIEWPORT_PAD), maxLeft);
            var top = Math.min(Math.max(originTop + dy, VIEWPORT_PAD), maxTop);
            place(left, top);
        });

        function endDrag(event) {
            if (!dragging) {
                return;
            }
            dragging = false;
            switcher.classList.remove('is-dragging');
            if (moved) {
                suppressClick = true;
                writePane(state);
            }
            try {
                dragHandle.releasePointerCapture(event.pointerId);
            } catch (err) {
                /* capture may already be released */
            }
        }

        dragHandle.addEventListener('pointerup', endDrag);
        dragHandle.addEventListener('pointercancel', endDrag);

        window.addEventListener('resize', function () {
            if (!positioned) {
                return;
            }
            clampIntoView(true);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
