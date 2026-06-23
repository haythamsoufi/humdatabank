/**
 * Sticky + compact executive page headers (opt-in via .executive-page-header--pin-actions).
 * Admin layout scrolls inside <main>; compact state uses a sentinel + IntersectionObserver when available.
 * Fallback: scroll + geometry hysteresis + cooldown.
 */
(function () {
    'use strict';

    var ENTER_PX = 3;
    var LEAVE_PX = 28;
    var SCROLL_TOP_SLACK = 40;
    var TOGGLE_COOLDOWN_MS = 220;
    var IO_ROOT_MARGIN_TOP_PX = 14;
    var IO_POST_TOGGLE_MS = 180;

    function nowMs() {
        return typeof performance !== 'undefined' && performance.now
            ? performance.now()
            : Date.now();
    }

    function getScrollTop(sp) {
        if (sp === document.documentElement || sp === document.body) {
            return window.pageYOffset
                || (document.documentElement && document.documentElement.scrollTop)
                || 0;
        }
        return sp.scrollTop || 0;
    }

    function findScrollParent(el) {
        var p = el.parentElement;
        while (p && p !== document.body) {
            var st = window.getComputedStyle(p);
            var oy = st.overflowY;
            if (oy === 'auto' || oy === 'scroll' || oy === 'overlay') {
                return p;
            }
            p = p.parentElement;
        }
        return document.scrollingElement || document.documentElement;
    }

    function bindWithSentinelIO(header, scrollParent, sentinel) {
        var compact = false;
        var ignoreIoUntil = 0;
        var resyncTimer = null;
        var io = null;

        function resyncFromObserver() {
            if (!io || typeof io.takeRecords !== 'function') {
                return;
            }
            try {
                io.takeRecords();
            } catch (e) { /* ignore */ }
        }

        function setCompact(want) {
            var next = !!want;
            if (next === compact) {
                return;
            }
            compact = next;
            header.classList.toggle('is-header-pinned-compact', compact);
            ignoreIoUntil = nowMs() + IO_POST_TOGGLE_MS;
            if (resyncTimer) {
                clearTimeout(resyncTimer);
            }
            resyncTimer = setTimeout(function () {
                resyncTimer = null;
                resyncFromObserver();
            }, IO_POST_TOGGLE_MS + 30);
        }

        var ioRoot = null;
        if (scrollParent && scrollParent !== document.body && scrollParent !== document.documentElement) {
            ioRoot = scrollParent;
        }

        var marginTop = IO_ROOT_MARGIN_TOP_PX + 'px 0px 0px 0px';
        io = new IntersectionObserver(function (entries) {
            var e = entries[0];
            if (!e) {
                return;
            }
            if (nowMs() < ignoreIoUntil) {
                return;
            }
            setCompact(!e.isIntersecting);
        }, { root: ioRoot, rootMargin: marginTop, threshold: 0 });

        io.observe(sentinel);

        window.requestAnimationFrame(function () {
            resyncFromObserver();
        });

        window.addEventListener('resize', function () {
            resyncFromObserver();
        }, { passive: true });
    }

    function bindWithScrollGeometry(header, scrollParent) {
        var ticking = false;
        var compact = false;
        var cooldownUntil = 0;
        var cooldownTimer = null;

        function update() {
            ticking = false;
            var now = nowMs();
            var scrollTop = getScrollTop(scrollParent);
            var nearScrollTop = scrollTop <= SCROLL_TOP_SLACK;
            if (now < cooldownUntil && !(compact && nearScrollTop)) {
                return;
            }

            var hr = header.getBoundingClientRect();
            var refTop;
            if (scrollParent === document.documentElement || scrollParent === document.body) {
                refTop = 0;
            } else {
                refTop = scrollParent.getBoundingClientRect().top;
            }
            var y = Math.round(hr.top);
            var ref = Math.round(refTop);

            var prevCompact = compact;
            if (!compact) {
                if (!nearScrollTop && y <= ref + ENTER_PX) {
                    compact = true;
                }
            } else {
                if (nearScrollTop || y > ref + LEAVE_PX) {
                    compact = false;
                }
            }

            if (prevCompact !== compact) {
                cooldownUntil = now + TOGGLE_COOLDOWN_MS;
                if (cooldownTimer) {
                    clearTimeout(cooldownTimer);
                }
                cooldownTimer = setTimeout(function () {
                    cooldownTimer = null;
                    update();
                }, TOGGLE_COOLDOWN_MS + 20);
            }

            header.classList.toggle('is-header-pinned-compact', compact);
        }

        function onScrollOrResize() {
            if (!ticking) {
                ticking = true;
                window.requestAnimationFrame(update);
            }
        }

        if (scrollParent === document.documentElement || scrollParent === document.body) {
            window.addEventListener('scroll', onScrollOrResize, { passive: true });
        } else {
            scrollParent.addEventListener('scroll', onScrollOrResize, { passive: true });
        }
        window.addEventListener('resize', onScrollOrResize, { passive: true });

        update();
    }

    function bindHeader(header) {
        if (header.dataset.pinHeaderBound === '1') {
            return;
        }
        header.dataset.pinHeaderBound = '1';

        var scrollParent = findScrollParent(header);
        var prev = header.previousElementSibling;
        var hasSentinel = prev && prev.classList && prev.classList.contains('page-header-pin-sentinel');
        var ioOk = typeof IntersectionObserver !== 'undefined';

        if (hasSentinel && ioOk && scrollParent && scrollParent.contains(prev)) {
            bindWithSentinelIO(header, scrollParent, prev);
        } else {
            bindWithScrollGeometry(header, scrollParent);
        }
    }

    function init() {
        document.querySelectorAll('.executive-page-header--pin-actions').forEach(bindHeader);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
