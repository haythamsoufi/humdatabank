/**
 * Chatbot WidgetUi module
 * @module chatbot/widget-ui
 */

export const WidgetUiMixin = {
    _syncFloatingMobileBodyLock(isOpen) {
        try {
            if (this._isImmersive() || !document.body) return;
            if (this._isMobileFloatingLayout() && isOpen) {
                // Save current scroll position before locking (needed for iOS restore)
                this._savedBodyScrollY = window.scrollY || window.pageYOffset || 0;
                document.body.style.top = `-${this._savedBodyScrollY}px`;
                document.body.classList.add('chat-floating-mobile-open');
            } else {
                const savedY = this._savedBodyScrollY || 0;
                document.body.classList.remove('chat-floating-mobile-open');
                document.body.style.top = '';
                // Restore scroll so the page appears unchanged after chat closes
                window.scrollTo(0, savedY);
                this._savedBodyScrollY = 0;
            }
        } catch (_) { /* ignore */ }
    },

    _initFloatingDrag() {
        const widget = this.elements && this.elements.widget;
        if (!widget || this._isImmersive()) return;
        const header = widget.querySelector('.chat-header');
        if (!header) return;

        const STORAGE_KEY = 'chatbot_float_pos';
        let dragging = false;
        let startX = 0, startY = 0, startLeft = 0, startTop = 0;

        const clamp = (val, min, max) => Math.min(Math.max(val, min), max);

        const applyPos = (left, top) => {
            const maxLeft = window.innerWidth - widget.offsetWidth;
            const maxTop = window.innerHeight - widget.offsetHeight;
            widget.style.left = clamp(left, 0, Math.max(0, maxLeft)) + 'px';
            widget.style.top  = clamp(top,  0, Math.max(0, maxTop))  + 'px';
        };

        const onMouseMove = (e) => {
            if (!dragging) return;
            applyPos(startLeft + e.clientX - startX, startTop + e.clientY - startY);
        };

        const onMouseUp = () => {
            if (!dragging) return;
            dragging = false;
            widget.classList.remove('chat-dragging');
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
            try {
                localStorage.setItem(STORAGE_KEY, JSON.stringify({
                    left: parseInt(widget.style.left, 10),
                    top:  parseInt(widget.style.top,  10),
                }));
            } catch (_) {}
        };

        header.addEventListener('mousedown', (e) => {
            if (this._isImmersive() || this._isMobileFloatingLayout()) return;
            if (e.button !== 0) return;
            if (e.target.closest('button, a, input, textarea, select, [role="button"]')) return;

            const rect = widget.getBoundingClientRect();
            widget.classList.add('chat-dragged');
            applyPos(rect.left, rect.top);

            dragging = true;
            startX    = e.clientX;
            startY    = e.clientY;
            startLeft = parseInt(widget.style.left, 10);
            startTop  = parseInt(widget.style.top,  10);

            widget.classList.add('chat-dragging');
            e.preventDefault();

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });

        // Clamp back inside viewport on window resize
        window.addEventListener('resize', () => {
            if (!widget.classList.contains('chat-dragged')) return;
            applyPos(parseInt(widget.style.left, 10), parseInt(widget.style.top, 10));
        });

        this._restoreFloatPos = () => {
            if (this._isImmersive() || this._isMobileFloatingLayout()) return;
            try {
                const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
                if (saved && typeof saved.left === 'number' && typeof saved.top === 'number') {
                    widget.classList.add('chat-dragged');
                    applyPos(saved.left, saved.top);
                }
            } catch (_) {}
        };
    },

    _initFabDrag() {
        const fab = this.elements && this.elements.fab;
        if (!fab || this._isImmersive()) return;

        const dlog = (fmt = '', ...args) => window.CHATBOT_DEBUG && console.log('[FAB drag] ' + fmt, ...args);

        const DRAG_THRESHOLD = 5;   // px movement before drag mode activates
        const EDGE_MARGIN    = 16;  // px gap between FAB and screen edge when snapped
        const VIEWPORT_PAD   = 8;   // min clearance from viewport edges during free drag
        const NAV_BAR_HEIGHT = 64;  // approx top-nav height (h-14 = 56 px + 8 px buffer)

        // Actual FAB dimensions measured at drag-start — handles pill vs compact shapes.
        let fabW = 56, fabH = 48;

        let isDragging  = false;
        let hasDragged  = false;
        let startX = 0, startY = 0;
        let grabOffsetX = 0, grabOffsetY = 0;
        let baseLeft = 0, baseTop = 0;
        let hideZone = null;
        let hideZoneHot = false;
        let lastPointerX = 0;
        let lastPointerY = 0;

        const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);

        // Safe clamp that returns lo when any value is non-finite (catches NaN / Infinity).
        const safeClamp = (v, lo, hi) => {
            if (!isFinite(v)) return lo;
            if (!isFinite(hi) || hi < lo) return lo;
            return clamp(v, lo, hi);
        };

        // Set position via inline !important styles so we always win over any stylesheet rule,
        // including `html[dir="rtl"] #aiChatbotFAB { left: ... !important }` in rtl.css.
        // Inline !important has higher priority than any author-stylesheet !important.
        const setPos = (left, top) => {
            fab.style.setProperty('left',   left + 'px', 'important');
            fab.style.setProperty('top',    top  + 'px', 'important');
            fab.style.setProperty('bottom', 'auto',      'important');
            fab.style.setProperty('right',  'auto',      'important');
        };

        // Reset to the default CSS position (bottom/right) on every page load.
        const resetDefaultPos = () => {
            fab.style.removeProperty('left');
            fab.style.removeProperty('top');
            fab.style.removeProperty('bottom');
            fab.style.removeProperty('right');
            fab.style.removeProperty('transform');
            fab.classList.remove('fab-dragged', 'fab-snapping', 'fab-dragging');
            baseLeft = 0;
            baseTop  = 0;
        };

        const ensureHideZone = () => {
            if (hideZone && hideZone.isConnected) return hideZone;
            hideZone = document.createElement('div');
            hideZone.id = 'aiChatbotFabHideZone';
            hideZone.className = 'fab-hide-zone';
            hideZone.setAttribute('role', 'status');
            hideZone.setAttribute('aria-hidden', 'true');
            hideZone.innerHTML =
                '<div class="fab-hide-zone-inner">' +
                '<i class="fas fa-eye-slash" aria-hidden="true"></i>' +
                '<span class="fab-hide-zone-label">Drop to hide</span>' +
                '</div>';
            document.body.appendChild(hideZone);
            return hideZone;
        };

        const showHideZone = () => {
            const zone = ensureHideZone();
            zone.setAttribute('aria-hidden', 'false');
            // Next frame so the enter transition runs.
            requestAnimationFrame(() => zone.classList.add('fab-hide-zone--visible'));
        };

        const hideHideZone = () => {
            if (!hideZone) return;
            hideZone.classList.remove('fab-hide-zone--visible', 'fab-hide-zone--hot');
            hideZone.setAttribute('aria-hidden', 'true');
        };

        const pointInHideZone = (clientX, clientY) => {
            if (!hideZone || !hideZone.classList.contains('fab-hide-zone--visible')) return false;
            const r = hideZone.getBoundingClientRect();
            const pad = 12;
            return clientX >= r.left - pad && clientX <= r.right + pad
                && clientY >= r.top - pad && clientY <= r.bottom + pad;
        };

        const fabOverlapsHideZone = () => {
            if (!hideZone || !hideZone.classList.contains('fab-hide-zone--visible')) return false;
            const a = fab.getBoundingClientRect();
            const b = hideZone.getBoundingClientRect();
            return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
        };

        const setHideZoneHot = (hot) => {
            hideZoneHot = !!hot;
            if (!hideZone) return;
            hideZone.classList.toggle('fab-hide-zone--hot', hideZoneHot);
            fab.classList.toggle('fab-dragging-over-hide', hideZoneHot);
        };

        const dismissFabForSession = () => {
            this._fabSessionHidden = true;
            try {
                if (typeof this.isOpen === 'function' && this.isOpen() && typeof this.toggleChat === 'function') {
                    this.toggleChat(false);
                }
            } catch (_) { /* ignore */ }
            hideHideZone();
            endDragVisuals();
            // Hide before resetting position so it never flashes back to the corner.
            fab.classList.add('fab-session-hidden');
            fab.hidden = true;
            fab.style.setProperty('display', 'none', 'important');
            try { fab.setAttribute('aria-hidden', 'true'); } catch (_) { /* ignore */ }
            resetDefaultPos();
            dlog('FAB dismissed for this page load');
        };

        // Apply left/top anchoring. Called only once the drag threshold is exceeded — never on a plain click.
        const beginDrag = () => {
            fab.classList.add('fab-dragged', 'fab-dragging');
            fab.style.setProperty('transform', 'scale(1.02)', 'important');
            showHideZone();
        };

        const endDragVisuals = () => {
            fab.style.removeProperty('transform');
            fab.classList.remove('fab-dragging', 'fab-dragging-over-hide');
        };

        // Snap finished position to nearest vertical edge with a smooth transition.
        const snapToEdge = (rawLeft, rawTop) => {
            const mid         = (window.innerWidth - fabW) / 2;
            const minTop      = NAV_BAR_HEIGHT + VIEWPORT_PAD;
            const snappedLeft = rawLeft <= mid
                ? EDGE_MARGIN
                : window.innerWidth - fabW - EDGE_MARGIN;
            const snappedTop  = clamp(rawTop, minTop, window.innerHeight - fabH - VIEWPORT_PAD);

            dlog('snapToEdge: rawLeft=%d → snappedLeft=%d top=%d', rawLeft, snappedLeft, snappedTop);

            fab.classList.add('fab-snapping');
            setPos(snappedLeft, snappedTop);
            baseLeft = snappedLeft;
            baseTop  = snappedTop;

            fab.addEventListener('transitionend', () => {
                fab.classList.remove('fab-snapping');
            }, { once: true });
        };

        // ── Pointer Events ──────────────────────────────────────────────────────
        fab.addEventListener('pointerdown', (e) => {
            if (e.pointerType === 'mouse' && e.button !== 0) return;
            if (this._fabSessionHidden) return;

            const rect = fab.getBoundingClientRect();
            fabW        = rect.width  || fabW;
            fabH        = rect.height || fabH;
            grabOffsetX = e.clientX - rect.left;
            grabOffsetY = e.clientY - rect.top;
            baseLeft    = rect.left;
            baseTop     = rect.top;
            isDragging  = true;
            hasDragged  = false;
            startX      = e.clientX;
            startY      = e.clientY;
            fab.setPointerCapture(e.pointerId);
            fab.classList.remove('fab-snapping');
            dlog('pointerdown at (%d,%d) fab rect=(%d,%d)', e.clientX, e.clientY, rect.left, rect.top);
        });

        fab.addEventListener('pointermove', (e) => {
            if (!isDragging) return;
            const dx = e.clientX - startX;
            const dy = e.clientY - startY;

            if (!hasDragged && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;

            if (!hasDragged) {
                hasDragged = true;
                beginDrag();
                dlog('drag started: base=(%d,%d)', baseLeft, baseTop);
            }

            const minTop  = NAV_BAR_HEIGHT + VIEWPORT_PAD;
            const newLeft = clamp(e.clientX - grabOffsetX, VIEWPORT_PAD, window.innerWidth  - fabW - VIEWPORT_PAD);
            const newTop  = clamp(e.clientY - grabOffsetY, minTop,        window.innerHeight - fabH - VIEWPORT_PAD);
            setPos(newLeft, newTop);
            baseLeft = newLeft;
            baseTop  = newTop;
            lastPointerX = e.clientX;
            lastPointerY = e.clientY;

            const overHide = pointInHideZone(e.clientX, e.clientY) || fabOverlapsHideZone();
            setHideZoneHot(overHide);
        });

        const endDrag = (e) => {
            if (!isDragging) return;
            isDragging = false;
            dlog('endDrag: hasDragged=%s event=%s', hasDragged, e.type);

            if (hasDragged) {
                const releaseX = Number.isFinite(e.clientX) ? e.clientX : lastPointerX;
                const releaseY = Number.isFinite(e.clientY) ? e.clientY : lastPointerY;
                // Prefer the live "hot" state from the last move — more reliable than
                // re-hit-testing after pointerup (coords can be stale with pointer capture).
                const overHide = hideZoneHot
                    || pointInHideZone(releaseX, releaseY)
                    || fabOverlapsHideZone();
                dlog('drag end: final=(%d,%d) overHide=%s hot=%s', baseLeft, baseTop, overHide, hideZoneHot);

                // Suppress the next click so the chat widget does not open after a drag.
                fab.addEventListener('click', (ce) => {
                    dlog('click suppressed after drag');
                    ce.stopImmediatePropagation();
                }, { once: true, capture: true });

                if (overHide) {
                    dismissFabForSession();
                    setHideZoneHot(false);
                    return;
                }

                setHideZoneHot(false);
                hideHideZone();
                endDragVisuals();
                snapToEdge(baseLeft, baseTop);
            } else {
                // Plain click — no DOM changes, let the existing click handler fire normally.
                dlog('plain click (no drag) — letting click event through');
                endDragVisuals();
                hideHideZone();
                setHideZoneHot(false);
            }
        };

        fab.addEventListener('pointerup',     endDrag);
        fab.addEventListener('pointercancel', endDrag);

        // Re-snap to the correct edge whenever the viewport resizes during this session.
        window.addEventListener('resize', () => {
            if (!fab.classList.contains('fab-dragged') || isDragging) return;
            if (this._fabSessionHidden) return;
            const minTop = NAV_BAR_HEIGHT + VIEWPORT_PAD;
            const cl = safeClamp(baseLeft, VIEWPORT_PAD, window.innerWidth  - fabW - VIEWPORT_PAD);
            const ct = safeClamp(baseTop,  minTop,        window.innerHeight - fabH - VIEWPORT_PAD);
            snapToEdge(cl, ct);
        });

        // Always start from the default CSS position; drag position is session-only.
        this._fabSessionHidden = false;
        resetDefaultPos();
        try { localStorage.removeItem('chatbot_fab_pos'); } catch (_) {}
    },
    /**
     * Nudge the FAB upward when it covers primary page actions (Save/Cancel/Submit at page bottom).
     * Re-checks on scroll, resize, and DOM changes; returns to default when clear.
     *
     * Blocking controls (worth jumping): design-system CTAs (.btn-primary, .btn-success, …),
     * submit inputs, entry-form #fab-menu actions, or explicit data-fab-overlap-block.
     * Generic buttons, ghost toggles, and [role="button"] disclosure headers are ignored.
     *
     * Stabilization rules (prevents up/down bouncing):
     * - Never remeasure while an avoidance transition is in flight (rest-rect math is wrong mid-tween).
     * - Resolve the full control rect (not a nested child) so tall buttons clear in one step.
     * - Only move when a *single* capped target is fully clear (no second hop needed);
     *   otherwise stay put rather than climbing the page.
     * - Hysteresis before returning to rest so tiny layout jitter does not re-trigger.
     */

    _initFabOverlapAvoidance() {
        const fab = this.elements && this.elements.fab;
        if (!fab || this._isImmersive()) return;

        const GAP = 12;
        const SAMPLE_INSET = 6;
        const MIN_SHIFT = 8;
        const HYSTERESIS = 20;
        /** Hard ceiling: keep the FAB in the lower part of the screen (~2.5× its height). */
        const MAX_SHIFT_PX = 120;
        const FAB_AVOID_EASE = 'cubic-bezier(0.4, 0, 0.2, 1)';
        const FAB_AVOID_MS = 280;

        let rafId = 0;
        let debounceId = 0;
        let transitionLock = false;
        let transitionUnlockTimer = 0;
        let disposed = false;
        this._fabAvoidanceShift = 0;

        const olog = (...args) => {
            if (window.FAB_OVERLAP_DEBUG || window.CHATBOT_DEBUG) {
                console.log('[FAB overlap]', ...args);
            }
        };

        const maxShiftCap = (restRect) => {
            const bySize = Math.round((restRect.height || 48) * 2.5);
            // Also keep the FAB top within the bottom third of the viewport.
            const minTop = Math.floor(window.innerHeight * (2 / 3));
            const byViewport = Math.max(0, Math.round(restRect.top - minTop));
            return Math.max(0, Math.min(MAX_SHIFT_PX, bySize, byViewport));
        };

        const isExcluded = (el) => {
            if (!el || fab === el || fab.contains(el)) return true;
            return !!el.closest(
                '#aiChatbotFAB, #aiChatWidget, #mobileMenuFAB, #chatbot-ai-hover-menu, '
                + '.flash-messages, .flash-messages-wrapper'
            );
        };

        const resolveControl = (el) => {
            if (!el) return null;
            if (el.matches('button, a, input[type="submit"], input[type="button"], [role="button"]')) return el;
            return el.closest('button, a, input[type="submit"], input[type="button"], [role="button"]');
        };

        /** Matches components.css semantic CTA variants — not .btn-ghost / bare buttons. */
        const FAB_CTA_SELECTOR = [
            '.btn-primary',
            '.btn-success',
            '.btn-danger',
            '.btn-secondary',
            '.btn-warning',
            '.btn-purple',
            '.btn-dark',
        ].join(', ');
        const FAB_CTA_LINK_SELECTOR = FAB_CTA_SELECTOR.split(', ').map((s) => 'a' + s).join(', ');

        const isFabBlockingControl = (el) => {
            const control = resolveControl(el);
            if (!control || isExcluded(control) || !control.isConnected) return false;

            if (control.closest('[data-fab-overlap-ignore]') || control.hasAttribute('data-fab-overlap-ignore')) {
                return false;
            }
            if (control.classList.contains('fab-overlap-ignore')) return false;

            // Form-builder chrome (row icons, page/section collapse) — not bottom-bar CTAs
            if (control.classList.contains('fb-icon-btn') || control.closest('.fb-icon-btn')) return false;
            if (control.matches('#toggle-all-pages-btn, #toggle-all-sections-btn, .page-toggle-btn')) return false;
            if (control.closest('#form-builder-ui') && control.matches('button, a') && !control.classList.contains('btn')) {
                return false;
            }

            const style = window.getComputedStyle(control);
            if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false;
            const rect = control.getBoundingClientRect();
            if (rect.width < 4 || rect.height < 4) return false;
            if (control.matches(':disabled, [disabled], [aria-disabled="true"]')) return false;

            if (control.hasAttribute('data-fab-overlap-block') || control.closest('[data-fab-overlap-block]')) {
                return true;
            }
            if (control.matches('input[type="submit"]')) return true;
            // Entry-form mobile Save/Submit/Pin stack (round FAB menu; no .btn-* classes)
            if (control.closest('#fab-menu')) return true;
            if (control.matches(FAB_CTA_SELECTOR)) return true;
            if (control.matches(FAB_CTA_LINK_SELECTOR)) return true;

            return false;
        };

        const rectsOverlap = (a, b) =>
            a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;

        const shiftRect = (rect, shift) => DOMRect.fromRect({
            x: rect.x,
            y: rect.y - shift,
            width: rect.width,
            height: rect.height,
        });

        /**
         * Default FAB slot (home position). Safe because measure() never runs mid-transition
         * — visualRect + known shift equals rest without neutralizing transform (no flicker).
         */
        const getRestFabRect = () => {
            const visualRect = fab.getBoundingClientRect();
            const shift = this._fabAvoidanceShift || 0;
            if (!shift) return visualRect;
            return DOMRect.fromRect({
                x: visualRect.x,
                y: visualRect.y + shift,
                width: visualRect.width,
                height: visualRect.height,
            });
        };

        const collectOverlappingControls = (fabRect) => {
            const sampleXs = [
                fabRect.left + SAMPLE_INSET,
                fabRect.left + fabRect.width * 0.5,
                fabRect.right - SAMPLE_INSET,
            ];
            const sampleYs = [
                fabRect.top + SAMPLE_INSET,
                fabRect.top + fabRect.height * 0.5,
                fabRect.bottom - SAMPLE_INSET,
            ];

            const seen = new Set();
            const overlaps = [];
            const prevPE = fab.style.pointerEvents;
            fab.style.pointerEvents = 'none';
            try {
                for (const y of sampleYs) {
                    for (const x of sampleXs) {
                        if (x < 0 || y < 0 || x > window.innerWidth || y > window.innerHeight) continue;
                        for (const el of document.elementsFromPoint(x, y)) {
                            if (!isFabBlockingControl(el)) continue;
                            const control = resolveControl(el);
                            if (!control || seen.has(control)) break;
                            const controlRect = control.getBoundingClientRect();
                            if (!rectsOverlap(fabRect, controlRect)) continue;
                            seen.add(control);
                            overlaps.push({ control, rect: controlRect });
                            break;
                        }
                    }
                }
            } finally {
                fab.style.pointerEvents = prevPE || '';
            }
            return overlaps;
        };

        /**
         * One-shot avoidance: compute a single target above resting overlaps.
         * Returns that shift only when the destination is fully clear and within the
         * height cap; otherwise null (= do not move — stay where we are).
         */
        const computeSafeShift = (restRect) => {
            const restOverlaps = collectOverlappingControls(restRect);
            if (!restOverlaps.length) return 0;

            let needed = 0;
            for (const { rect } of restOverlaps) {
                needed = Math.max(needed, restRect.bottom - rect.top + GAP);
            }
            needed = Math.round(needed);

            const cap = maxShiftCap(restRect);
            if (needed < MIN_SHIFT) return 0;
            if (needed > cap) {
                olog('reject: over cap', { needed, cap });
                return null;
            }

            const destination = shiftRect(restRect, needed);
            if (destination.top < GAP) {
                olog('reject: above viewport floor', { top: destination.top, needed });
                return null;
            }

            const destOverlaps = collectOverlappingControls(destination);
            if (destOverlaps.length) {
                olog('reject: target still covered', {
                    needed,
                    controls: destOverlaps.map(({ control }) => control.id || control.className || control.tagName),
                });
                return null;
            }

            return needed;
        };

        const endTransitionLock = () => {
            if (disposed) return;
            transitionLock = false;
            fab.style.removeProperty('transition');
            olog('transition unlock');
            // One settle pass after the tween so we do not leave a wrong shift frozen.
            scheduleCheckDebounced();
        };

        const armTransitionLock = () => {
            transitionLock = true;
            clearTimeout(transitionUnlockTimer);
            const onEnd = (e) => {
                if (e.target !== fab || e.propertyName !== 'transform') return;
                clearTimeout(transitionUnlockTimer);
                endTransitionLock();
            };
            fab.addEventListener('transitionend', onEnd, { once: true });
            // Fallback if transitionend is skipped (display:none, reduced motion, etc.).
            transitionUnlockTimer = setTimeout(endTransitionLock, FAB_AVOID_MS + 80);
        };

        const applyShift = (shift) => {
            const next = Math.max(0, Math.round(shift));
            if (next === this._fabAvoidanceShift) return;

            olog('apply shift', { prev: this._fabAvoidanceShift, next });
            this._fabAvoidanceShift = next;
            armTransitionLock();

            if (next > 0) {
                fab.style.setProperty('transition', `transform ${FAB_AVOID_MS}ms ${FAB_AVOID_EASE}`, 'important');
                fab.style.setProperty('--fab-avoidance-shift', next + 'px');
                fab.classList.add('fab-avoiding-controls');
                fab.style.setProperty('transform', `translateY(-${next}px)`, 'important');
            } else {
                fab.style.setProperty('transition', `transform ${FAB_AVOID_MS}ms ${FAB_AVOID_EASE}`, 'important');
                fab.classList.remove('fab-avoiding-controls');
                fab.style.removeProperty('--fab-avoidance-shift');
                fab.style.removeProperty('transform');
            }
        };

        const getSkipReason = () => {
            if (!fab.isConnected) return 'fab-not-connected';
            if (fab.hidden) return 'fab-hidden';
            if (fab.classList.contains('chat-open')) return 'chat-open';
            if (fab.classList.contains('fab-dragged')) return 'fab-dragged';
            if (fab.classList.contains('fab-dragging')) return 'fab-dragging';
            if (document.body && document.body.classList.contains('fb-ai-panel-open')) return 'fb-ai-panel-open';
            const style = window.getComputedStyle(fab);
            if (style.display === 'none') return 'display-none';
            if (style.visibility === 'hidden') return 'visibility-hidden';
            return null;
        };

        const measure = () => {
            rafId = 0;
            if (transitionLock) {
                olog('skip: transition-lock');
                return;
            }

            const skipReason = getSkipReason();
            if (skipReason) {
                applyShift(0);
                return;
            }

            const restRect = getRestFabRect();
            if (!restRect.width || !restRect.height) return;

            const current = this._fabAvoidanceShift || 0;
            const cap = maxShiftCap(restRect);
            const needed = computeSafeShift(restRect);

            // null => no safe single move — stay put (do not climb / bounce).
            let next = current;
            if (needed === null) {
                next = current > cap ? 0 : current;
            } else if (needed === 0) {
                next = 0;
            } else if (current === 0) {
                next = needed;
            } else if (needed > current) {
                // Only accept a higher nudge when that exact target is already proven clear.
                next = needed;
            } else if ((current - needed) >= HYSTERESIS) {
                next = needed;
            }

            if (next > cap) next = needed === 0 || needed === null ? 0 : Math.min(next, cap);

            olog('measure', { current, needed, next, cap, restTop: Math.round(restRect.top) });
            applyShift(next);
        };

        const scheduleCheck = () => {
            if (rafId || transitionLock) return;
            rafId = requestAnimationFrame(measure);
        };

        const scheduleCheckDebounced = () => {
            clearTimeout(debounceId);
            debounceId = setTimeout(scheduleCheck, 120);
        };

        document.addEventListener('scroll', scheduleCheck, { capture: true, passive: true });
        window.addEventListener('resize', scheduleCheckDebounced, { passive: true });

        const domObs = new MutationObserver((mutations) => {
            // Avoidance itself mutates FAB class/style — ignore those or we re-enter forever.
            const onlyFab = mutations.every((m) => m.target === fab || (fab.contains && fab.contains(m.target)));
            if (onlyFab) return;
            scheduleCheckDebounced();
        });
        if (document.body) {
            domObs.observe(document.body, {
                childList: true,
                subtree: true,
                attributes: true,
                attributeFilter: ['class', 'style', 'hidden', 'disabled', 'aria-hidden'],
            });
        }

        this._fabOverlapAvoidanceCleanup = () => {
            disposed = true;
            document.removeEventListener('scroll', scheduleCheck, { capture: true });
            window.removeEventListener('resize', scheduleCheckDebounced);
            domObs.disconnect();
            clearTimeout(debounceId);
            clearTimeout(transitionUnlockTimer);
            if (rafId) cancelAnimationFrame(rafId);
            transitionLock = false;
            this._fabAvoidanceShift = 0;
            fab.classList.remove('fab-avoiding-controls');
            fab.style.removeProperty('--fab-avoidance-shift');
            fab.style.removeProperty('transform');
            fab.style.removeProperty('transition');
        };

        window.__fabOverlapRemeasure = scheduleCheck;
        scheduleCheckDebounced();
    },

    toggleChat(forceOpen) {
        if (!this.elements || !this.elements.widget) return;
        const isOpen = typeof forceOpen === 'boolean' ? forceOpen : !this.isOpen();

        this.elements.widget.classList.toggle('chat-open', isOpen);
        if (this.elements.fab) {
            this.elements.fab.classList.toggle('chat-open', isOpen);
            this.elements.fab.setAttribute('aria-expanded', isOpen.toString());
        }

        if (isOpen) {
            if (typeof this._restoreFloatPos === 'function') this._restoreFloatPos();
            // Only show greeting if chat is opened AND there's no conversation history
            if (this.conversationHistory.length === 0) {
                this.showWelcomeMessage();
            }
            if (this.elements.input) {
                this.elements.input.focus();
            }
            // No-op by design (see spotlight-tours.js#_preloadCommonWorkflowToursOnce) —
            // kept as a call site in case tour preloading is reinstated later.
            if (typeof this._preloadCommonWorkflowToursOnce === 'function') {
                this._preloadCommonWorkflowToursOnce();
            }
            // Fetch the floating header title once per page load, on first actual open,
            // instead of on every page load. Centralized here (rather than only on the FAB
            // click listener) so it also fires when chat is opened programmatically, e.g.
            // form-builder-ai.js calling toggleChat(true) without going through the FAB.
            if (!this._floatingTitleLoaded && !this._isImmersive() && this._getFloatingConversationId()) {
                this._floatingTitleLoaded = true;
                void this._refreshFloatingHeaderTitleFromServer();
            }
        }

        this._syncFloatingMobileBodyLock(isOpen);
    },

    isOpen() {
        if (!this.elements || !this.elements.widget) return false;
        return this.elements.widget.classList.contains('chat-open');
    },

    scrollToBottom() {
        // Immersive page: scroll the messages scroll container and respect auto-scroll flag
        if (this._isImmersive()) {
            if (typeof window.humdbChatImmersiveAutoScroll !== 'undefined' && window.humdbChatImmersiveAutoScroll === false) return;
            const scrollEl = this.elements.messages && this.elements.messages.parentElement;
            if (scrollEl && scrollEl.classList && scrollEl.classList.contains('chat-immersive-messages-scroll')) {
                scrollEl.scrollTop = scrollEl.scrollHeight;
                return;
            }
        }
        this.elements.messages.scrollTop = this.elements.messages.scrollHeight;
    },

    _resizeChatInput() {
        const ta = this.elements.input;
        if (!ta || ta.nodeName !== 'TEXTAREA') return;
        const maxHeight = 200;
        const minHeight = this._isImmersive() ? 36 : 34;
        ta.style.height = '0';
        const h = Math.min(Math.max(ta.scrollHeight, minHeight), maxHeight);
        ta.style.height = h + 'px';

        const pill = ta.closest('.chat-input-pill');
        if (pill) {
            pill.classList.toggle('chat-input-pill--multiline', h > minHeight + 4);
        }
    },

    showTypingIndicator() {
        if (document.getElementById('typingIndicator')) return; // Already showing

        const typingDiv = document.createElement('div');
        typingDiv.className = 'chat-progress-panel';
        typingDiv.id = 'typingIndicator';
        typingDiv.setAttribute('aria-live', 'polite');

        const stepsList = document.createElement('ul');
        stepsList.className = 'chat-progress-steps';
        stepsList.setAttribute('aria-live', 'polite');
        stepsList.setAttribute('aria-label', this._uiString('stepsInProgress') || 'Steps in progress');

        const initialLi = document.createElement('li');
        initialLi.className = 'chat-progress-step chat-progress-step-active';
        const initialIcon = document.createElement('i');
        initialIcon.className = 'fas fa-spinner fa-spin chat-progress-step-icon';
        initialIcon.setAttribute('aria-hidden', 'true');
        const initialLabel = document.createElement('span');
        initialLabel.className = 'chat-progress-step-label';
        initialLabel.textContent = this._uiString('preparingQuery') || 'Preparing query…';
        initialLi.append(initialIcon, initialLabel);
        stepsList.appendChild(initialLi);

        typingDiv.appendChild(stepsList);
        this.elements.messages.appendChild(typingDiv);
        this.scrollToBottom();
    },

    addStepToProgress(stepMessage, detail) {
        if (!stepMessage || typeof stepMessage !== 'string') return;
        const trimmed = String(stepMessage).trim();
        if (!trimmed) return;
        const typingIndicator = document.getElementById('typingIndicator');
        if (!typingIndicator) return;
        const stepsList = typingIndicator.querySelector('.chat-progress-steps');
        if (!stepsList) return;
        const lastItem = stepsList.querySelector('.chat-progress-step:last-child');
        const lastLabel = lastItem ? (lastItem.querySelector('.chat-progress-step-label') || lastItem).textContent : '';
        if (lastItem && (lastLabel || '').trim() === trimmed) {
            if (detail && String(detail).trim()) {
                this._updateStepDetail(lastItem, String(detail).trim());
            }
            return;
        }
        // If the backend streams progress ticks (e.g. "Processing documents: 10/64"),
        // update the current step label in-place instead of appending many near-identical steps.
        const progressRe = /^(.+?):\s*(\d+)\s*\/\s*(\d+)\s*$/;
        const newProgress = trimmed.match(progressRe);
        const lastProgress = ((lastLabel || '').trim()).match(progressRe);
        if (lastItem && newProgress && lastProgress) {
            const newPrefix = String(newProgress[1] || '').trim();
            const lastPrefix = String(lastProgress[1] || '').trim();
            // Only coalesce if the "prefix" matches; counts may change.
            if (newPrefix && lastPrefix && newPrefix === lastPrefix) {
                const labelEl = lastItem.querySelector('.chat-progress-step-label') || lastItem;
                labelEl.textContent = trimmed;
                if (detail && String(detail).trim()) {
                    this._updateStepDetail(lastItem, String(detail).trim());
                }
                this.scrollToBottom();
                return;
            }
        }
        // Mark previous step as done (check) and collapse its detail when next step is shown
        if (lastItem) {
            const prevDetailEl = lastItem.querySelector('.chat-progress-step-detail');
            // If the previous step had no meaningful detail (empty or placeholder), show "Done." or refined query for "Preparing query…"
            if (prevDetailEl) {
                const prevDetailText = String(prevDetailEl.textContent || '').trim();
                const hasNoMeaningfulDetail = !prevDetailText;
                if (hasNoMeaningfulDetail) {
                    const prevLabel = (lastItem.querySelector('.chat-progress-step-label') || lastItem).textContent || '';
                    const preparingLabel = (this._uiString && this._uiString('preparingQuery')) || 'Preparing query…';
                    if (prevLabel.trim() === String(preparingLabel || '').trim() && this._lastPreparingQueryDetail) {
                        prevDetailEl.textContent = String(this._lastPreparingQueryDetail).trim();
                        this._lastPreparingQueryDetail = null;
                    } else {
                        prevDetailEl.textContent = 'Done.';
                    }
                }
            }
            const prevIcon = lastItem.querySelector('.chat-progress-step-icon');
            if (prevIcon) {
                prevIcon.className = 'fas fa-check chat-progress-step-icon chat-progress-step-done';
                prevIcon.setAttribute('aria-hidden', 'true');
            }
            if (lastItem.querySelector('.chat-progress-step-detail')) {
                lastItem.classList.add('chat-progress-step-detail-collapsed');
                const prevToggle = lastItem.querySelector('.chat-progress-step-detail-toggle');
                const prevRow = lastItem.querySelector('.chat-progress-step-row');
                if (prevToggle) prevToggle.className = 'fas fa-chevron-right chat-progress-step-detail-toggle';
                if (prevRow) prevRow.setAttribute('aria-expanded', 'false');
            }
        }
        const li = document.createElement('li');
        li.className = 'chat-progress-step chat-progress-step-active';
        const stepIcon = document.createElement('i');
        stepIcon.className = 'fas fa-spinner fa-spin chat-progress-step-icon';
        stepIcon.setAttribute('aria-hidden', 'true');
        const stepLabel = document.createElement('span');
        stepLabel.className = 'chat-progress-step-label';
        stepLabel.textContent = trimmed;
        if (detail && String(detail).trim()) {
            const row = document.createElement('div');
            row.className = 'chat-progress-step-row';
            row.append(stepIcon, stepLabel);
            const toggleIcon = document.createElement('i');
            toggleIcon.className = 'fas fa-chevron-down chat-progress-step-detail-toggle';
            toggleIcon.setAttribute('aria-hidden', 'true');
            row.appendChild(toggleIcon);
            const detailEl = document.createElement('div');
            detailEl.className = 'chat-progress-step-detail';
            detailEl.textContent = String(detail).trim();
            li.append(row, detailEl);
            row.setAttribute('role', 'button');
            row.setAttribute('tabIndex', '0');
            row.setAttribute('aria-expanded', 'true');
            row.addEventListener('click', () => {
                li.classList.toggle('chat-progress-step-detail-collapsed');
                const collapsed = li.classList.contains('chat-progress-step-detail-collapsed');
                row.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
                toggleIcon.className = collapsed ? 'fas fa-chevron-right chat-progress-step-detail-toggle' : 'fas fa-chevron-down chat-progress-step-detail-toggle';
            });
            row.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    row.click();
                }
            });
        } else {
            li.append(stepIcon, stepLabel);
        }
        stepsList.appendChild(li);
        this.scrollToBottom();
    },

    _isSuppressedStepDetail(text) {
        // Filter internal planner diagnostics that have no value for end users.
        return /^No single-tool shortcut for this request/i.test(String(text || '').trim());
    },

    appendStepDetail(detailLine) {
        if (!detailLine || typeof detailLine !== 'string') return;
        const trimmed = String(detailLine).trim();
        if (!trimmed) return;
        if (this._isSuppressedStepDetail(trimmed)) return;
        const typingIndicator = document.getElementById('typingIndicator');
        if (!typingIndicator) return;
        const stepsList = typingIndicator.querySelector('.chat-progress-steps');
        if (!stepsList) return;
        const lastItem = stepsList.querySelector('.chat-progress-step:last-child');
        if (!lastItem) return;
        const detailEl = lastItem.querySelector('.chat-progress-step-detail');
        if (detailEl) {
            // Avoid duplicate consecutive detail lines (common when backend re-emits last progress)
            const existing = String(detailEl.textContent || '');
            const lastLine = existing.split('\n').slice(-1)[0]?.trim() || '';
            if (lastLine === trimmed) return;

            // Coalesce "progress tick" lines like "Processing documents: 10/64" by replacing the last tick
            // instead of appending many near-identical lines.
            const progressRe = /^(.+?):\s*(\d+)\s*\/\s*(\d+)\s*$/;
            const newProgress = trimmed.match(progressRe);
            const lastProgress = lastLine.match(progressRe);
            if (newProgress && lastProgress) {
                const newPrefix = String(newProgress[1] || '').trim();
                const lastPrefix = String(lastProgress[1] || '').trim();
                if (newPrefix && lastPrefix && newPrefix === lastPrefix) {
                    const lines = existing.split('\n');
                    lines[lines.length - 1] = trimmed;
                    detailEl.textContent = lines.join('\n');
                    this._log('Coalesced step_detail progress tick:', { from: lastLine, to: trimmed });
                    this.scrollToBottom();
                    return;
                }
            }

            detailEl.textContent = detailEl.textContent ? detailEl.textContent + '\n' + trimmed : trimmed;
            this._log('Appended step_detail line:', trimmed);
        } else {
            this._updateStepDetail(lastItem, trimmed);
            this._log('Created step_detail block with first line:', trimmed);
        }
        this.scrollToBottom();
    },

    _updateStepDetail(stepLi, detailText) {
        const detailEl = stepLi.querySelector('.chat-progress-step-detail');
        if (detailEl) {
            detailEl.textContent = detailText;
            return;
        }
        const icon = stepLi.querySelector('.chat-progress-step-icon');
        const label = stepLi.querySelector('.chat-progress-step-label');
        if (!icon || !label) return;
        const row = document.createElement('div');
        row.className = 'chat-progress-step-row';
        row.append(icon, label);
        const toggleIcon = document.createElement('i');
        toggleIcon.className = 'fas fa-chevron-down chat-progress-step-detail-toggle';
        toggleIcon.setAttribute('aria-hidden', 'true');
        row.appendChild(toggleIcon);
        const detailElNew = document.createElement('div');
        detailElNew.className = 'chat-progress-step-detail';
        detailElNew.textContent = detailText;
        stepLi.append(row, detailElNew);
        row.setAttribute('role', 'button');
        row.setAttribute('tabIndex', '0');
        row.setAttribute('aria-expanded', 'true');
        row.addEventListener('click', () => {
            stepLi.classList.toggle('chat-progress-step-detail-collapsed');
            const collapsed = stepLi.classList.contains('chat-progress-step-detail-collapsed');
            row.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
            toggleIcon.className = collapsed ? 'fas fa-chevron-right chat-progress-step-detail-toggle' : 'fas fa-chevron-down chat-progress-step-detail-toggle';
        });
        row.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                row.click();
            }
        });
    },

    updateTypingIndicator(message, detail) {
        const typingIndicator = document.getElementById('typingIndicator');
        if (!typingIndicator) return;
        if (typingIndicator.classList.contains('chat-progress-panel')) {
            const preparingLabel = (this._uiString && this._uiString('preparingQuery')) || 'Preparing query…';
            if (String(message || '').trim() === String(preparingLabel || '').trim() && detail && String(detail).trim()) {
                this._lastPreparingQueryDetail = String(detail).trim();
            }
            this.addStepToProgress(message, detail);
            return;
        }
        const textSpan = typingIndicator.querySelector('.typing-indicator-text, .text-sm.text-gray-500');
        if (textSpan) {
            textSpan.textContent = message || this._uiString('assistantIsTyping') || 'Assistant is typing';
        }
    },

    hideTypingIndicator() {
        this._lastPreparingQueryDetail = null;
        const typingIndicator = document.getElementById('typingIndicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
    },

    _setSendButtonStop(isStop) {
        const btn = this.elements.sendBtn;
        if (!btn) return;
        const icon = btn.querySelector('i');
        const stopLabel = btn.getAttribute('data-stop-label') || this._uiString('stop') || 'Stop';
        const sendLabel = btn.getAttribute('data-send-label') || this._uiString('send') || 'Send';
        if (isStop) {
            btn.setAttribute('aria-label', stopLabel);
            btn.setAttribute('title', stopLabel);
            btn.classList.add('chat-send-is-stop');
            if (icon) {
                icon.classList.remove('fa-arrow-up');
                icon.classList.add('fa-stop');
            }
        } else {
            btn.setAttribute('aria-label', sendLabel);
            btn.setAttribute('title', sendLabel);
            btn.classList.remove('chat-send-is-stop');
            if (icon) {
                icon.classList.remove('fa-stop');
                icon.classList.add('fa-arrow-up');
            }
        }
    },

    stopCurrentRequest() {
        this._log('stopCurrentRequest called, isTyping=', this.isTyping, ', _currentAbort=', typeof this._currentAbort);
        if (typeof this._currentAbort === 'function') {
            try {
                this._currentAbort();
            } catch (e) {
                this._warn('stopCurrentRequest error:', e);
            }
            this._currentAbort = null;
        } else {
            this._warn('stopCurrentRequest: no abort callback (nothing to stop)');
        }
    },

    _updateImmersiveQuickPromptsVisibility() {
        if (!this._isImmersive()) return;
        const hasUserMessage = this.conversationHistory.some(entry => entry.isUser);
        const showEmpty = !hasUserMessage;
        if (this.elements.quickPrompts) {
            this.elements.quickPrompts.style.display = showEmpty ? 'block' : 'none';
        }
        if (this.elements.welcomeCenter) {
            this.elements.welcomeCenter.style.display = showEmpty ? 'flex' : 'none';
            this.elements.welcomeCenter.setAttribute('aria-hidden', showEmpty ? 'false' : 'true');
        }
    }

};
