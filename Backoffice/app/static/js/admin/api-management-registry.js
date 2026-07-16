// ── Endpoint Registry — AG Grid + surface/search filters ────────────────
(function () {
    'use strict';
    var cfg = window.apiMgmtRegistryConfig || {};

    var EP_L = {
        unknown: cfg.t.unknown_88183b94,
        public: cfg.t.public_3d067bed,
        apiKey: cfg.t.api_key_d876ff8d,
        keySession: cfg.t.key_session_ba743dea,
        session: cfg.t.session_71c7ae29,
        aiSession: cfg.t.ai_session_37b73772,
        userJwt: cfg.t.user_jwt_a813f254,
        rbac: cfg.t.rbac_fad878b0,
        rateLimited: cfg.t.rate_limited_8ff3d0a7,
        featured: cfg.t.featured_endpoint_7b9a1e22,
        undocumented: cfg.t.undocumented_af60b8f5,
        stale: cfg.t.stale_36f34fd8,
    };

    /** Longer native `title` tooltips for auth icons (keep in sync with legend `title` attributes). */
    var AUTH_TOOLTIPS = {
        '?': cfg.t.auth_mode_could_not_be_inferred_from_rou_253a2059,
        public: cfg.t.no_authentication_anyone_who_can_reach_t_900cfbe9,
        api_key: cfg.t.bearer_token_using_a_database_managed_ap_e33b4b55,
        api_key_or_session: cfg.t.valid_api_key_bearer_or_an_authenticated_b2773975,
        session: cfg.t.flask_login_session_only_login_required__ed5712e9,
        ai_session: cfg.t.ai_identity_from_resolve_ai_identity_1_b_b4baf968,
        user: cfg.t.mobile_user_jwt_or_compatible_session_vi_952d94ed,
        rbac: cfg.t.mobile_admin_mobile_auth_required_plus_o_d68c5a24,
    };

    var surfaceBtns = document.querySelectorAll('.ep-surface-btn');
    var emptyMsg = document.getElementById('epEmpty');
    var matchFooter = document.getElementById('epRegistryFooter');
    var matchCountEl = document.getElementById('epMatchCount');
    var matchChipTotalEl = document.getElementById('epMatchChipTotal');
    var matchHintEl = document.getElementById('epMatchHint');
    var matchHintTextEl = document.getElementById('epMatchHintText');
    var clearColFiltersBtn = document.getElementById('epClearColFilters');
    var loadingEl = document.getElementById('epRegistryGrid-loading');
    var containerEl = document.getElementById('epRegistryGrid-container');

    window.__apiMgmtUrlExtra = window.__apiMgmtUrlExtra || { surface: 'all', ep_f: '', vol_p: 'daily', vol_e: 'all' };
    var activeSurface = window.__apiMgmtUrlExtra.surface || 'all';
    var epFilterUrlTimer = null;
    /** False until post-init timeout applies URL column filters (avoids clobbering `ep_f` on load). */
    var epRegistryFilterUrlSyncReady = false;
    var epRegistryGridApi = null;
    var epRegistryGridSizeFitTimer = null;
    var epRegistryAllRows = [];

    var AUTH_LABELS = {
        public: 'Public (no auth)',
        api_key: 'API Key (Bearer, DB-managed)',
        api_key_or_session: 'API Key or Session',
        session: 'Session (@login_required)',
        ai_session: 'AI Session (resolve_ai_identity)',
        user: 'User JWT (@mobile_auth_required)',
        rbac: 'RBAC (@mobile_auth_required + permission)',
    };
    var SURFACE_LABELS = {
        v1: 'External /api/v1',
        mobile: 'Mobile /api/mobile/v1',
        ai: 'AI /api/ai/v2',
    };

    function styleActiveBtn(activeBtn) {
        var colourMap = {
            all: ['bg-gray-800', 'text-white', 'border-gray-800'],
            v1: ['bg-blue-100', 'text-blue-700', 'border-blue-300'],
            mobile: ['bg-teal-100', 'text-teal-700', 'border-teal-300'],
            ai: ['bg-purple-100', 'text-purple-700', 'border-purple-300'],
            flagged: ['bg-red-100', 'text-red-700', 'border-red-200'],
            has_stats: ['bg-green-100', 'text-green-700', 'border-green-200'],
            overlap: ['bg-indigo-100', 'text-indigo-700', 'border-indigo-200'],
            undocumented: ['bg-yellow-100', 'text-yellow-800', 'border-yellow-300'],
            stale: ['bg-gray-200', 'text-gray-800', 'border-gray-400'],
            gaps: ['bg-yellow-100', 'text-yellow-700', 'border-yellow-300'],
        };
        var allColours = Object.values(colourMap).flat();
        surfaceBtns.forEach(function (b) {
            b.classList.remove('ep-active', ...allColours);
            if (b.disabled) return;
            b.classList.add('bg-white', 'text-gray-600', 'border-gray-300');
        });
        if (activeBtn.disabled) {
            activeBtn = document.querySelector('.ep-surface-btn[data-surface="all"]') || activeBtn;
            activeSurface = 'all';
        }
        activeBtn.classList.remove('bg-white', 'text-gray-600', 'border-gray-300');
        activeBtn.classList.add('ep-active', ...(colourMap[activeBtn.dataset.surface] || colourMap.all));
    }

    /** Whether a data row matches a registry surface chip (not tied to `activeSurface`). */
    function rowMatchesSurface(d, surface) {
        if (!d || d.__epGroupHeader) return false;
        if (surface === 'all') return true;
        if (surface === 'flagged') return d.has_flags;
        if (surface === 'overlap') return d.has_overlap;
        if (surface === 'has_stats') return d.has_stats;
        if (surface === 'undocumented') return !!d.undocumented;
        if (surface === 'stale') return !!d.stale;
        if (surface === 'gaps') return d.gaps;
        return d.surface === surface;
    }

    function countRowsForSurface(surface, rows) {
        if (!rows || !rows.length) return 0;
        var n = 0;
        for (var i = 0; i < rows.length; i++) {
            if (rowMatchesSurface(rows[i], surface)) n += 1;
        }
        return n;
    }

    function updateEpSurfaceBtnStates() {
        var rows = window.__epRegistryAllRows || epRegistryAllRows || [];
        var allBtnRef = document.querySelector('.ep-surface-btn[data-surface="all"]');
        surfaceBtns.forEach(function (b) {
            var surf = b.dataset.surface || 'all';
            if (surf === 'all') {
                b.disabled = false;
                return;
            }
            b.disabled = countRowsForSurface(surf, rows) === 0;
        });
        if (activeSurface !== 'all') {
            var cur = document.querySelector('.ep-surface-btn[data-surface="' + activeSurface + '"]');
            if (cur && cur.disabled && allBtnRef) {
                activeSurface = 'all';
                window.__apiMgmtUrlExtra.surface = 'all';
                if (typeof window.apiMgmtSyncUrl === 'function') window.apiMgmtSyncUrl();
                styleActiveBtn(allBtnRef);
                refreshExternalFilter();
                return;
            }
        }
    }

    function rowPassesSurfaceFilter(d) {
        if (!d) return true;
        if (d.__epGroupHeader) return false;
        return rowMatchesSurface(d, activeSurface);
    }

    /** AG Grid v31+ passes `{ node }` to `doesExternalFilterPass`; older builds pass the node directly. */
    function epRegistryRowNodeFromFilterParams(params) {
        if (params && params.node) return params.node;
        return params;
    }

    function externalFilterPass(node) {
        var d = node.data;
        if (!d) return true;
        if (d.__epGroupHeader) {
            var key = d.__epGroupKey;
            var src = window.__epRegistryAllRows || epRegistryAllRows;
            for (var i = 0; i < src.length; i++) {
                var r = src[i];
                if (r.__epGroupHeader) continue;
                if (r.registryGroup !== key) continue;
                if (rowPassesSurfaceFilter(r)) return true;
            }
            return false;
        }
        return rowPassesSurfaceFilter(d);
    }

    /** Synthetic full-width header rows; real endpoint rows stay in epRegistryAllRows / __epRegistryAllRows only. */
    function buildRegistryGroupedRows(rows) {
        if (!rows || !rows.length) return [];
        // Groups that contain a featured (endorsed) endpoint float to the top of the list;
        // within a group, featured rows sort first so paths like /api/v1/data stay pinned.
        var featuredGroups = {};
        for (var fi = 0; fi < rows.length; fi++) {
            if (rows[fi].featured) {
                featuredGroups[String(rows[fi].registryGroup || '')] = true;
            }
        }
        var sorted = rows.slice().sort(function (a, b) {
            var ga = String(a.registryGroup || '');
            var gb = String(b.registryGroup || '');
            var groupPinA = featuredGroups[ga] ? 0 : 1;
            var groupPinB = featuredGroups[gb] ? 0 : 1;
            if (groupPinA !== groupPinB) return groupPinA - groupPinB;
            if (ga !== gb) return ga < gb ? -1 : ga > gb ? 1 : 0;
            var featA = a.featured ? 0 : 1;
            var featB = b.featured ? 0 : 1;
            if (featA !== featB) return featA - featB;
            var pa = String(a.path || '');
            var pb = String(b.path || '');
            return pa < pb ? -1 : pa > pb ? 1 : 0;
        });
        var out = [];
        var lastGroup = null;
        for (var i = 0; i < sorted.length; i++) {
            var r = sorted[i];
            var g = r.registryGroup != null ? String(r.registryGroup) : '';
            if (g !== lastGroup) {
                lastGroup = g;
                out.push({
                    __epGroupHeader: true,
                    __epGroupKey: g,
                    registryGroup: g,
                    surface: '',
                    path: '',
                    pathLower: '',
                    pathSearch: '',
                    description: '',
                    methods: [],
                    methodsStr: '',
                    auth: '',
                    permission: '',
                    consumers: '',
                    total_requests: 0,
                    success_rate: 0,
                    featured: false,
                    has_flags: false,
                    has_overlap: false,
                    has_stats: false,
                    undocumented: false,
                    stale: false,
                    gaps: false,
                    rate_limited: false,
                    overlapPaths: [],
                    flags: [],
                });
            }
            out.push(r);
        }
        return out;
    }

    function EpRegistryGroupFullWidthRenderer() {}
    EpRegistryGroupFullWidthRenderer.prototype.init = function (params) {
        var d = params.data;
        var label = (d && d.__epGroupKey != null) ? String(d.__epGroupKey) : '';
        var src = window.__epRegistryAllRows || epRegistryAllRows;
        var n = 0;
        for (var j = 0; j < src.length; j++) {
            var row = src[j];
            if (row.__epGroupHeader) continue;
            if (String(row.registryGroup || '') !== label) continue;
            n += 1;
        }
        var wrap = document.createElement('div');
        wrap.className = 'ep-registry-group-header-fw flex items-center w-full px-3 py-1.5 bg-gray-100 border-b border-gray-200 text-sm font-semibold text-gray-800';
        var title = document.createElement('span');
        title.textContent = label;
        wrap.appendChild(title);
        if (n > 0) {
            var c = document.createElement('span');
            c.className = 'text-xs text-gray-500 font-normal ml-2';
            c.textContent = '(' + n + ')';
            wrap.appendChild(c);
        }
        this.eGui = wrap;
    };
    EpRegistryGroupFullWidthRenderer.prototype.getGui = function () {
        return this.eGui;
    };
    EpRegistryGroupFullWidthRenderer.prototype.refresh = function () {
        return false;
    };

    function isExternalFilterPresent() {
        return activeSurface !== 'all';
    }

    function refreshExternalFilter() {
        if (!epRegistryGridApi) {
            updateFooterAndEmpty();
            return;
        }
        /* External filter changes must notify the grid (v34: onFilterChanged; older: refreshClientSideRowModel). */
        if (typeof epRegistryGridApi.onFilterChanged === 'function') {
            epRegistryGridApi.onFilterChanged();
        } else if (typeof epRegistryGridApi.refreshClientSideRowModel === 'function') {
            epRegistryGridApi.refreshClientSideRowModel('filter');
        }
        updateFooterAndEmpty();
    }

    function countVisibleDataRows() {
        if (!epRegistryGridApi) return 0;
        var n = 0;
        epRegistryGridApi.forEachNodeAfterFilter(function (node) {
            if (node.data && !node.data.__epGroupHeader) n += 1;
        });
        return n;
    }

    /** Rows matching the surface chip only (ignores AG Grid column / floating filters). */
    function countRowsMatchingActiveChip() {
        if (activeSurface === 'all') return 0;
        var src = window.__epRegistryAllRows || epRegistryAllRows || [];
        return countRowsForSurface(activeSurface, src);
    }

    function clearEpRegistryColumnFilters() {
        if (!epRegistryGridApi || typeof epRegistryGridApi.setFilterModel !== 'function') return;
        try {
            epRegistryGridApi.setFilterModel(null);
        } catch (e) {}
        if (typeof epRegistryGridApi.onFilterChanged === 'function') {
            epRegistryGridApi.onFilterChanged();
        } else if (typeof epRegistryGridApi.refreshClientSideRowModel === 'function') {
            epRegistryGridApi.refreshClientSideRowModel('filter');
        }
        window.__apiMgmtUrlExtra.ep_f = '';
        if (typeof window.apiMgmtSyncUrl === 'function') window.apiMgmtSyncUrl();
        updateFooterAndEmpty();
    }

    function scheduleEpColumnFilterUrlSync() {
        if (!epRegistryFilterUrlSyncReady) return;
        if (epFilterUrlTimer) clearTimeout(epFilterUrlTimer);
        epFilterUrlTimer = setTimeout(function () {
            epFilterUrlTimer = null;
            if (!epRegistryGridApi || typeof epRegistryGridApi.getFilterModel !== 'function') return;
            var m = epRegistryGridApi.getFilterModel();
            var json = m && Object.keys(m).length ? JSON.stringify(m) : '';
            window.__apiMgmtUrlExtra.ep_f = json;
            if (typeof window.apiMgmtSyncUrl === 'function') window.apiMgmtSyncUrl();
        }, 300);
    }

    function updateFooterAndEmpty() {
        var n = countVisibleDataRows();
        var chipN = countRowsMatchingActiveChip();
        if (emptyMsg) emptyMsg.classList.toggle('hidden', n > 0);
        if (matchFooter && matchCountEl) {
            if (n > 0) {
                matchFooter.classList.remove('hidden');
                matchCountEl.textContent = String(n);
                if (matchChipTotalEl) {
                    var showSplit = activeSurface !== 'all' && chipN > 0 && n < chipN;
                    matchChipTotalEl.classList.toggle('hidden', !showSplit);
                    matchChipTotalEl.textContent = showSplit ? ' / ' + String(chipN) : '';
                }
                if (matchHintEl && matchHintTextEl) {
                    var showHint = activeSurface !== 'all' && chipN > 0 && n < chipN;
                    matchHintEl.classList.toggle('hidden', !showHint);
                    matchHintTextEl.textContent = showHint
                        ? cfg.t.column_filters_are_hiding_some_rows_that_20419783
                        : '';
                }
            } else {
                matchFooter.classList.add('hidden');
                matchCountEl.textContent = '';
                if (matchChipTotalEl) {
                    matchChipTotalEl.classList.add('hidden');
                    matchChipTotalEl.textContent = '';
                }
                if (matchHintEl && matchHintTextEl) {
                    matchHintEl.classList.add('hidden');
                    matchHintTextEl.textContent = '';
                }
            }
        }
    }

    /** Verbose clip logs: reload after `localStorage.setItem('epRegistryClipDebug','1')` or `window.__EP_REGISTRY_CLIP_DEBUG = true`. */
    function epRegistryClipDebugEnabled() {
        try {
            if (typeof window.__EP_REGISTRY_CLIP_DEBUG !== 'undefined' && window.__EP_REGISTRY_CLIP_DEBUG) return true;
            return localStorage.getItem('epRegistryClipDebug') === '1';
        } catch (e) {
            return !!window.__EP_REGISTRY_CLIP_DEBUG;
        }
    }

    var epRegistryClipOverflowWarnCount = 0;
    var epRegistryClipRunCount = 0;

    /** Force path / description cells to clip (flex min-width:auto + inline styles otherwise spill into next columns). */
    function applyEpRegistryCellClipping(reason) {
        reason = reason || 'unknown';
        var root = document.getElementById('epRegistryGrid');
        if (!root) {
            console.warn('[ep-registry-clip] no #epRegistryGrid', { reason: reason });
            return;
        }
        var debug = epRegistryClipDebugEnabled();
        var cells = root.querySelectorAll('.ag-cell[col-id="path"], .ag-cell[col-id="description"], .ag-cell.ep-registry-path-cell, .ag-cell.ep-registry-desc-cell');
        var n = cells.length;
        epRegistryClipRunCount += 1;
        if (debug) {
            (window.__clientLog || window.__clientInfo || function(){})('[ep-registry-clip] run', { reason: reason, run: epRegistryClipRunCount, matchingCells: n });
        }
        var samplePathDone = false;
        var sampleDescDone = false;
        cells.forEach(function (cell) {
            var colId = cell.getAttribute('col-id') || cell.getAttribute('aria-colindex') || '(no-col-id)';
            cell.style.setProperty('overflow', 'hidden', 'important');
            cell.style.setProperty('min-width', '0', 'important');
            var wrap = cell.querySelector('.ag-cell-wrapper');
            if (wrap) {
                wrap.style.setProperty('min-width', '0', 'important');
                wrap.style.setProperty('max-width', '100%', 'important');
                wrap.style.setProperty('width', '100%', 'important');
                wrap.style.setProperty('overflow', 'hidden', 'important');
                wrap.style.setProperty('flex', '1 1 0%', 'important');
            }
            var val = cell.querySelector('.ag-cell-value');
            if (val) {
                val.style.setProperty('min-width', '0', 'important');
                val.style.setProperty('max-width', '100%', 'important');
                val.style.setProperty('width', '100%', 'important');
                val.style.setProperty('overflow', 'hidden', 'important');
            }
            var inner = val && val.firstElementChild;
            if (inner) {
                inner.style.setProperty('min-width', '0', 'important');
                inner.style.setProperty('max-width', '100%', 'important');
                inner.style.setProperty('width', '100%', 'important');
                inner.style.setProperty('overflow', 'hidden', 'important');
            }

            var cs = window.getComputedStyle(cell);
            var pathSample = colId === 'path' && !samplePathDone;
            var descSample = colId === 'description' && !sampleDescDone;
            if (debug && (pathSample || descSample)) {
                if (pathSample) samplePathDone = true;
                if (descSample) sampleDescDone = true;
                (window.__clientLog || window.__clientInfo || function(){})('[ep-registry-clip] sample cell layout', {
                    reason: reason,
                    colId: colId,
                    classes: cell.className,
                    cell: { clientWidth: cell.clientWidth, scrollWidth: cell.scrollWidth, offsetWidth: cell.offsetWidth },
                    computed: { overflow: cs.overflow, overflowX: cs.overflowX, minWidth: cs.minWidth, maxWidth: cs.maxWidth, display: cs.display, position: cs.position },
                    inlineOverflow: cell.style.getPropertyValue('overflow'),
                    dom: { hasWrapper: !!wrap, hasValue: !!val, valueChildCount: val ? val.childNodes.length : 0, innerTag: inner ? inner.tagName : null, innerClass: inner ? inner.className : '' },
                    innerBox: inner ? { clientWidth: inner.clientWidth, scrollWidth: inner.scrollWidth } : null,
                    wrapBox: wrap ? { clientWidth: wrap.clientWidth, scrollWidth: wrap.scrollWidth } : null,
                    valBox: val ? { clientWidth: val.clientWidth, scrollWidth: val.scrollWidth } : null
                });
            }

            if (cell.scrollWidth > cell.clientWidth + 1) {
                if (epRegistryClipOverflowWarnCount < 12) {
                    epRegistryClipOverflowWarnCount += 1;
                    console.warn('[ep-registry-clip] cell still wider than client (horizontal overflow)', {
                        n: epRegistryClipOverflowWarnCount,
                        reason: reason,
                        colId: colId,
                        clientWidth: cell.clientWidth,
                        scrollWidth: cell.scrollWidth,
                        innerScroll: inner ? inner.scrollWidth : null,
                        innerClient: inner ? inner.clientWidth : null
                    });
                }
            }
        });
        if (n === 0 && debug) {
            (window.__clientLog || window.__clientInfo || function(){})('[ep-registry-clip] no path/description cells in DOM (hidden tab or not yet rendered?)', { reason: reason });
        }
        if (n > 0 && !window.__epRegistryClipHintShown) {
            window.__epRegistryClipHintShown = true;
            (window.__clientLog || window.__clientInfo || function(){})('[ep-registry-clip] Horizontal overflow (if any) logs as warnings below. Verbose layout samples: localStorage.setItem("epRegistryClipDebug","1") then reload, or set window.__EP_REGISTRY_CLIP_DEBUG = true.');
        }
    }

    var epRegistryClipScrollTimer = null;
    function scheduleEpRegistryCellClipping(reason) {
        if (epRegistryClipScrollTimer) clearTimeout(epRegistryClipScrollTimer);
        epRegistryClipScrollTimer = setTimeout(function () {
            epRegistryClipScrollTimer = null;
            applyEpRegistryCellClipping(reason || 'debounced');
        }, 80);
    }

    /**
     * AI identity help: single position:fixed layer on document.body so AG Grid viewports/cards
     * cannot clip it. Triggers carry .ep-ai-identity-tip-source (sr-only) with plain text.
     */
    function epAiIdentityTooltipInit() {
        if (window.__epAiIdentityTooltipInitDone) return;
        var layer = document.getElementById('epAiIdentityTooltipLayer');
        var registryPanel = document.getElementById('panel-registry');
        if (!layer || !registryPanel) return;
        var inner = layer.querySelector('.ep-rich-tip-inner');
        if (!inner) return;
        window.__epAiIdentityTooltipInitDone = true;

        if (layer.parentElement !== document.body) {
            document.body.appendChild(layer);
        }

        var hideT = null;
        var activeTrigger = null;
        var HIDE_MS = 220;

        function hide() {
            clearTimeout(hideT);
            hideT = null;
            activeTrigger = null;
            layer.classList.remove('ep-ai-identity-tip-visible');
            layer.setAttribute('aria-hidden', 'true');
            layer.style.left = '';
            layer.style.top = '';
        }

        function positionNear(rect) {
            var vw = window.innerWidth;
            var vh = window.innerHeight;
            var w = layer.offsetWidth;
            var h = layer.offsetHeight;
            if (!w || !h) {
                w = 280;
                h = 100;
            }
            var left = rect.left + rect.width / 2 - w / 2;
            left = Math.max(12, Math.min(left, vw - w - 12));
            var gap = 8;
            var top = rect.top - h - gap;
            if (top < 12) {
                top = rect.bottom + gap;
            }
            if (top + h > vh - 12) {
                top = Math.max(12, vh - h - 12);
            }
            layer.style.left = left + 'px';
            layer.style.top = top + 'px';
        }

        function showFor(trig) {
            if (!trig) return;
            var src = trig.querySelector('.ep-ai-identity-tip-source');
            var txt = src ? src.textContent : '';
            if (!txt) return;
            inner.textContent = txt;
            activeTrigger = trig;
            layer.classList.add('ep-ai-identity-tip-visible');
            layer.setAttribute('aria-hidden', 'false');
            requestAnimationFrame(function () {
                requestAnimationFrame(function () {
                    positionNear(trig.getBoundingClientRect());
                });
            });
        }

        function schedHide() {
            clearTimeout(hideT);
            hideT = setTimeout(hide, HIDE_MS);
        }

        function onDocMove(e) {
            var tr = e.target.closest && e.target.closest('.ep-ai-identity-tip-trigger');
            if (tr && registryPanel.contains(tr)) {
                clearTimeout(hideT);
                hideT = null;
                if (activeTrigger !== tr || !layer.classList.contains('ep-ai-identity-tip-visible')) {
                    showFor(tr);
                }
                return;
            }
            if (!layer.classList.contains('ep-ai-identity-tip-visible')) return;
            if (layer.contains(e.target)) {
                clearTimeout(hideT);
                hideT = null;
                return;
            }
            schedHide();
        }

        document.addEventListener('mousemove', onDocMove, true);

        layer.addEventListener('mouseenter', function () {
            clearTimeout(hideT);
            hideT = null;
        });
        layer.addEventListener('mouseleave', function () {
            schedHide();
        });

        function onScrollOrResize() {
            if (!layer.classList.contains('ep-ai-identity-tip-visible') || !activeTrigger) return;
            if (!document.body.contains(activeTrigger)) {
                hide();
                return;
            }
            positionNear(activeTrigger.getBoundingClientRect());
        }
        document.addEventListener('scroll', onScrollOrResize, true);
        window.addEventListener('resize', onScrollOrResize);

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && layer.classList.contains('ep-ai-identity-tip-visible')) {
                hide();
            }
        });
    }

    function methodBadgeHtml(m) {
        var esc = AgGridRenderers.escapeHtml(m);
        var cls = 'px-1.5 py-0.5 text-xs font-bold rounded ';
        if (m === 'GET') cls += 'bg-blue-100 text-blue-700';
        else if (m === 'POST') cls += 'bg-green-100 text-green-700';
        else if (m === 'PUT' || m === 'PATCH') cls += 'bg-yellow-100 text-yellow-700';
        else if (m === 'DELETE') cls += 'bg-red-100 text-red-700';
        else cls += 'bg-gray-100 text-gray-700';
        return '<span class="' + cls + '">' + esc + '</span>';
    }

    function methodsCellRenderer(params) {
        var d = params.data;
        if (!d || d.__epGroupHeader) return '';
        var methods = d.methods;
        if (!methods || !methods.length) return '';
        return '<div class="flex flex-wrap gap-1">' + methods.map(methodBadgeHtml).join('') + '</div>';
    }

    function authIconOnly(iconClass, iconTextClass, shortLabel, tooltipText) {
        var tip = tooltipText != null && String(tooltipText) !== '' ? String(tooltipText) : String(shortLabel || '');
        return '<span class="inline-flex items-center justify-center cursor-help" title="' +
            AgGridRenderers.escapeHtmlAttr(tip) + '"><i class="fas ' + iconClass + ' ' + iconTextClass + '" aria-hidden="true"></i><span class="sr-only">' +
            AgGridRenderers.escapeHtml(shortLabel || '') + '</span></span>';
    }

    /** AI Session icon: fixed-layer tooltip (see epAiIdentityTooltipInit); hidden source holds text. */
    function authAiIdentityIconHtml(shortLabel, bodyText) {
        var raw = bodyText != null ? String(bodyText) : '';
        var body = AgGridRenderers.escapeHtml(raw);
        var lab = AgGridRenderers.escapeHtml(shortLabel != null ? String(shortLabel) : '');
        return '<span class="ep-ai-identity-tip-trigger inline-flex items-center justify-center cursor-help" aria-label="' +
            AgGridRenderers.escapeHtmlAttr(raw) + '">' +
            '<span class="inline-flex items-center justify-center"><i class="fas fa-robot text-purple-600" aria-hidden="true"></i>' +
            '<span class="sr-only">' + lab + '</span></span>' +
            '<span class="ep-ai-identity-tip-source sr-only" aria-hidden="true">' + body + '</span></span>';
    }

    function authCellRenderer(params) {
        var d = params.data;
        if (!d || d.__epGroupHeader) return '';
        var a = d.auth;
        var html = '';
        var rbacTip = AUTH_TOOLTIPS.rbac;
        if (a === 'rbac' && d.permission) {
            rbacTip = rbacTip + ' ' + cfg.t.permission_0caf7e41 + ' ' + String(d.permission);
        }
        var rateTip = cfg.t.this_route_applies_request_throttling_fo_40ca3ff9;
        if (a === '?') {
            html = authIconOnly('fa-question', 'text-yellow-600', EP_L.unknown, AUTH_TOOLTIPS['?']);
        } else if (a === 'public') {
            html = authIconOnly('fa-globe', 'text-gray-500', EP_L.public, AUTH_TOOLTIPS.public);
        } else if (a === 'api_key') {
            html = authIconOnly('fa-key', 'text-amber-600', EP_L.apiKey, AUTH_TOOLTIPS.api_key);
        } else if (a === 'api_key_or_session') {
            html = authIconOnly('fa-user-lock', 'text-indigo-600', EP_L.keySession, AUTH_TOOLTIPS.api_key_or_session);
        } else if (a === 'session') {
            html = authIconOnly('fa-user', 'text-blue-600', EP_L.session, AUTH_TOOLTIPS.session);
        } else if (a === 'ai_session') {
            html = authAiIdentityIconHtml(EP_L.aiSession, AUTH_TOOLTIPS.ai_session);
        } else if (a === 'user') {
            html = authIconOnly('fa-mobile-alt', 'text-teal-600', EP_L.userJwt, AUTH_TOOLTIPS.user);
        } else if (a === 'rbac') {
            html = authIconOnly('fa-shield-alt', 'text-orange-600', EP_L.rbac, rbacTip);
        } else {
            var raw = (a != null && String(a) !== '') ? String(a) : EP_L.unknown;
            html = authIconOnly('fa-tag', 'text-gray-500', raw, raw);
        }
        html = '<div class="flex items-center gap-2 flex-nowrap">' + html;
        if (d.rate_limited) {
            html += authIconOnly('fa-tachometer-alt', 'text-yellow-500', EP_L.rateLimited, rateTip);
        }
        html += '</div>';
        return html;
    }

    function epRegistryV1PathHref(path) {
        // Never embed API keys in URLs — they leak via browser history, referrer headers,
        // and server logs.  Return a clean link; callers can copy the path and use their
        // key via an Authorization header or a dedicated test-request tool instead.
        try {
            var u = new URL(path, window.location.origin);
            u.searchParams.delete('api_key');
            return u.href;
        } catch (e) {
            return '#';
        }
    }

    function pathCellRenderer(params) {
        var d = params.data;
        if (!d || d.__epGroupHeader) return '';
        var path = d.path || '';
        var pathEl;
        var pathTextStyle = 'display:block;min-width:0;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;box-sizing:border-box';
        if (d.surface === 'v1') {
            var pathHref = epRegistryV1PathHref(path);
            pathEl = '<a href="' + AgGridRenderers.escapeHtmlAttr(pathHref) + '" target="_blank" rel="noopener noreferrer" style="' + pathTextStyle + '" class="font-mono text-xs text-blue-600 hover:underline api-endpoint-link" data-endpoint-path="' +
                AgGridRenderers.escapeHtmlAttr(path) + '">' + AgGridRenderers.escapeHtml(path) + '</a>';
        } else if (d.auth === 'public') {
            /* Public endpoints on non-v1 surfaces (e.g. /api/mobile/v1/auth/token) need no
               credentials, so they can be opened directly in a browser or Postman. */
            try {
                var publicHref = new URL(path, window.location.origin).href;
                pathEl = '<a href="' + AgGridRenderers.escapeHtmlAttr(publicHref) + '" target="_blank" rel="noopener noreferrer" style="' + pathTextStyle + '" class="font-mono text-xs text-blue-600 hover:underline api-endpoint-link" data-endpoint-path="' +
                    AgGridRenderers.escapeHtmlAttr(path) + '">' + AgGridRenderers.escapeHtml(path) + '</a>';
            } catch (e) {
                pathEl = '<code class="font-mono text-xs text-gray-700" style="' + pathTextStyle + '">' + AgGridRenderers.escapeHtml(path) + '</code>';
            }
        } else {
            pathEl = '<code class="font-mono text-xs text-gray-700" style="' + pathTextStyle + '">' + AgGridRenderers.escapeHtml(path) + '</code>';
        }
        var star = d.featured ? '<i class="fas fa-star text-yellow-400 flex-shrink-0 text-xs" title="' + AgGridRenderers.escapeHtmlAttr(EP_L.featured) + '"></i>' : '';
        var pathRow = '<div class="min-w-0 flex-1 flex items-center gap-1 overflow-hidden" style="min-width:0;flex:1 1 0%;overflow:hidden">' + pathEl + star + '</div>';
        var badges = '';
        if (d.undocumented) {
            badges += '<span class="inline-flex items-center gap-0.5 px-1.5 py-0.5 text-xs font-bold rounded bg-yellow-200 text-yellow-800 flex-shrink-0">' + AgGridRenderers.escapeHtml(EP_L.undocumented) + '</span>';
        }
        if (d.stale) {
            badges += '<span class="inline-flex items-center gap-0.5 px-1.5 py-0.5 text-xs font-bold rounded bg-gray-300 text-gray-700 flex-shrink-0">' + AgGridRenderers.escapeHtml(EP_L.stale) + '</span>';
        }
        var badgeRow = badges ? '<div class="flex flex-shrink-0 flex-wrap items-center gap-1">' + badges + '</div>' : '';
        var mainRow = '<div class="flex items-start gap-1 min-w-0 w-full" style="min-width:0;width:100%;max-width:100%;overflow:hidden">' + pathRow + badgeRow + '</div>';
        var sub = '';
        if (d.overlapPaths && d.overlapPaths.length) {
            var overlapPlain = '≈ ' + d.overlapPaths.join(', ');
            sub = '<div class="text-xs text-indigo-400 mt-0.5 min-w-0 truncate font-mono" title="' + AgGridRenderers.escapeHtmlAttr(overlapPlain) + '">' + AgGridRenderers.escapeHtml(overlapPlain) + '</div>';
        }
        return '<div class="ep-path-root w-full min-w-0 max-w-full overflow-hidden flex flex-col gap-0.5" style="box-sizing:border-box;width:100%;max-width:100%;min-width:0;overflow:hidden">' + mainRow + sub + '</div>';
    }

    function descriptionCellRenderer(params) {
        var d = params.data;
        if (!d || d.__epGroupHeader) return '';
        var t = d.description != null ? String(d.description) : '';
        if (!t) return '<span class="text-gray-300 text-xs">—</span>';
        return '<div class="ep-desc-inner w-full min-w-0 max-w-full overflow-hidden text-sm text-gray-700 leading-snug" style="box-sizing:border-box;width:100%;max-width:100%;min-width:0;overflow:hidden">' +
            '<span class="block min-w-0 truncate" style="display:block;min-width:0;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + AgGridRenderers.escapeHtml(t) + '</span></div>';
    }

    function successCellRenderer(params) {
        var d = params.data;
        if (!d || d.__epGroupHeader || !d.total_requests) return '<span class="text-gray-300 text-xs">—</span>';
        var pct = Math.min(100, Math.max(0, Math.round(d.success_rate || 0)));
        return '<div class="flex items-center gap-1.5"><div class="flex-1 bg-gray-200 rounded-full h-1.5 min-w-[3rem]">' +
            '<div class="bg-green-500 h-1.5 rounded-full" style="width:' + pct + '%"></div></div>' +
            '<span class="text-xs text-gray-600 whitespace-nowrap">' + pct + '%</span></div>';
    }

    function flagsCellRenderer(params) {
        var d = params.data;
        if (!d || d.__epGroupHeader || !d.flags || !d.flags.length) return '<span class="text-gray-300 text-xs">—</span>';
        var map = { bug: ['bg-red-500 text-white', 'fa-bug'], contract: ['bg-red-500 text-white', 'fa-bug'], mismatch: ['bg-red-400 text-white', 'fa-exclamation-triangle'], policy: ['bg-yellow-400 text-white', 'fa-balance-scale'], unused: ['bg-gray-400 text-white', 'fa-unlink'] };
        var parts = d.flags.map(function (f) {
            var t = (f.type || 'minor');
            var m = map[t] || ['bg-blue-400 text-white', 'fa-info-circle'];
            var note = AgGridRenderers.escapeHtmlAttr(f.note || '');
            return '<span class="ep-flag-badge inline-flex items-center gap-0.5 px-1.5 py-0.5 text-xs font-bold rounded cursor-pointer ' + m[0] + '" data-flag-type="' + AgGridRenderers.escapeHtmlAttr(t) + '" title="' + note + '"><i class="fas ' + m[1] + '"></i> ' + AgGridRenderers.escapeHtml(t) + '</span>';
        });
        return '<div class="flex flex-col gap-1 items-center">' + parts.join('') + '</div>';
    }

    function surfaceCellRenderer(params) {
        if (params.data && params.data.__epGroupHeader) return '';
        var s = params.value;
        if (s === 'v1') return '<span class="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded bg-blue-100 text-blue-700 font-semibold">v1</span>';
        if (s === 'mobile') return '<span class="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded bg-teal-100 text-teal-700 font-semibold">mob</span>';
        if (s === 'ai') return '<span class="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded bg-purple-100 text-purple-700 font-semibold">ai</span>';
        return AgGridRenderers.escapeHtml(s || '');
    }

    function buildUniqueOverlapPairs(eps) {
        var byPath = {};
        eps.forEach(function (e) { byPath[e.path] = e; });
        var seen = {};
        var out = [];
        eps.forEach(function (e) {
            if (!e.overlap) return;
            var targets = e.overlapWith ? e.overlapWith.split(',') : [];
            targets.forEach(function (raw) {
                var o = (raw || '').trim();
                if (!o) return;
                var k = [e.path, o].sort().join('\0');
                if (seen[k]) return;
                seen[k] = true;
                var ea = byPath[e.path];
                var eb = byPath[o];
                var first = ea;
                var second = eb;
                if (ea && eb && ea.surface === 'mobile' && eb.surface === 'v1') {
                    first = eb;
                    second = ea;
                }
                out.push({ first: first, second: second, secondPath: o });
            });
        });
        return out;
    }

    function buildReport() {
        var rows = (window.__epRegistryAllRows || epRegistryAllRows).filter(function (r) { return !r.__epGroupHeader; });
        var now = new Date().toLocaleDateString('en-GB', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
        var eps = rows.map(function (d) {
            return {
                surface: d.surface,
                path: d.path,
                methods: d.methodsStr,
                auth: d.auth,
                permission: d.permission || '',
                description: d.description || '',
                consumers: d.consumers || '',
                rateLimited: d.rate_limited,
                flagged: d.has_flags,
                overlap: d.has_overlap,
                overlapWith: (d.overlapPaths || []).join(', '),
                group: d.registryGroup,
                requests: d.total_requests,
                flags: d.flags || [],
            };
        });
        var flagged = eps.filter(function (e) { return e.flagged; });
        var overlapPairs = buildUniqueOverlapPairs(eps);
        var bySurface = { v1: eps.filter(function (e) { return e.surface === 'v1'; }), mobile: eps.filter(function (e) { return e.surface === 'mobile'; }), ai: eps.filter(function (e) { return e.surface === 'ai'; }) };
        function authOf(e) { return AUTH_LABELS[e.auth] || e.auth; }
        function surfOf(e) { return SURFACE_LABELS[e.surface] || e.surface; }
        function esc(s) {
            return String(s || '—')
                .replace(/\\/g, '\\\\')
                .replace(/\|/g, '\\|')
                .replace(/`/g, '\\`')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
        }
        var md = '# API Endpoint Registry — Audit Report\nGenerated: ' + now + '\n\n---\n\n## Summary\n\n| | Count |\n|---|---:|\n';
        md += '| **Total endpoints** | **' + eps.length + '** |\n';
        md += '| External `/api/v1` | ' + bySurface.v1.length + ' |\n| Mobile `/api/mobile/v1` | ' + bySurface.mobile.length + ' |\n| AI `/api/ai/v2` | ' + bySurface.ai.length + ' |\n';
        md += '| ⚠️ Flagged issues | **' + flagged.length + '** |\n| 🔁 Cross-surface overlaps | ' + overlapPairs.length + ' |\n';
        md += '| 📊 Endpoints with usage stats | ' + eps.filter(function (e) { return e.requests > 0; }).length + ' |\n';
        md += '| 👻 Undocumented | ' + rows.filter(function (r) { return r.undocumented; }).length + ' |\n';
        md += '| 🕸️ Stale | ' + rows.filter(function (r) { return r.stale; }).length + ' |\n\n---\n\n';
        if (flagged.length > 0) {
            md += '## ⚠️ Flagged Issues (' + flagged.length + ')\n\n';
            var n = 0;
            flagged.forEach(function (ep) {
                ep.flags.forEach(function (flag) {
                    n += 1;
                    md += '### ' + n + '. [' + String(flag.type || 'issue').toUpperCase() + '] `' + esc(ep.path) + '`\n\n- **Surface:** ' + surfOf(ep) + '\n- **Auth:** ' + authOf(ep);
                    if (ep.permission) md += ' — permission: `' + esc(ep.permission) + '`';
                    md += '\n- **Issue:** ' + (flag.note || '') + '\n\n';
                });
            });
            md += '---\n\n';
        }
        if (overlapPairs.length > 0) {
            md += '## 🔁 Cross-surface Overlaps (' + overlapPairs.length + ' unique pairs)\n\n| Path (A) | Auth (A) | Path (B) | Auth (B) |\n|----------|----------|----------|----------|\n';
            overlapPairs.forEach(function (pair) {
                var fa = pair.first;
                var fb = pair.second;
                var pb = (fb && fb.path) ? fb.path : pair.secondPath;
                var authB = fb ? authOf(fb) : '—';
                md += '| `' + esc(fa.path) + '` | ' + esc(authOf(fa)) + ' | `' + esc(pb) + '` | ' + esc(authB) + ' |\n';
            });
            md += '\n---\n\n';
        }
        var authCount = {};
        eps.forEach(function (e) { authCount[e.auth] = (authCount[e.auth] || 0) + 1; });
        md += '## 🔐 Auth Distribution\n\n| Auth type | Count | % |\n|-----------|------:|--:|\n';
        Object.keys(authCount).sort().forEach(function (a) {
            md += '| ' + (AUTH_LABELS[a] || a) + ' | ' + authCount[a] + ' | ' + ((authCount[a] / eps.length) * 100).toFixed(1) + '% |\n';
        });
        md += '\n---\n\n## 📋 Full Endpoint List (' + eps.length + ')\n\n| # | Surface | Path | Methods | Auth | Permission | Rate-ltd | Requests | Consumers |\n|---|---------|------|---------|------|-----------|----------|----------|----------|\n';
        eps.forEach(function (ep, i) {
            var rl = ep.rateLimited ? '✓' : '—';
            var req = ep.requests > 0 ? String(ep.requests) : '—';
            md += '| ' + (i + 1) + ' | ' + ep.surface + ' | `' + esc(ep.path) + '` | ' + esc(ep.methods) + ' | ' + esc(authOf(ep)) + ' | ' + esc(ep.permission || '—') + ' | ' + rl + ' | ' + req + ' | ' + esc(ep.consumers) + ' |\n';
        });
        md += '\n---\n*Exported from API Management → Endpoint Registry*\n';
        return md;
    }

    function downloadMd(content) {
        var blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'api-endpoint-report.md';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    function initEpRegistryGrid() {
        if (window.__epRegistryGridInited) return;
        var jsonEl = document.getElementById('ep-registry-grid-data');
        if (!jsonEl || typeof AgGridHelper === 'undefined' || typeof AgGridRenderers === 'undefined') return;

        var rowData;
        try {
            rowData = JSON.parse(jsonEl.textContent);
        } catch (e) {
            console.error('ep-registry-grid-data parse error', e);
            rowData = [];
        }
        epRegistryAllRows = rowData;
        window.__epRegistryAllRows = rowData;
        updateEpSurfaceBtnStates();
        var gridRowData = buildRegistryGroupedRows(rowData);

        if (!rowData.length) {
            if (loadingEl) loadingEl.style.display = 'none';
            if (containerEl) containerEl.style.display = 'none';
            if (emptyMsg) emptyMsg.classList.remove('hidden');
            window.__epRegistryGridInited = true;
            return;
        }

        /*
         * Column width budget (~860px visible area):
         *   surface(75) + methodsStr(110) + auth(80) + total_requests(85) + success_rate(110) + flags(100) = 560px fixed
         *   path(flex:2) + description(flex:1) share the remaining ~300px
         *   consumers hidden by default (toggle via column-visibility manager)
         * minWidth:0 on flex cols lets sizeColumnsToFit compress them freely within the panel.
         */
        var columnDefs = [
            { field: 'surface', headerName: cfg.t.surface_aa0d528b, width: 75, cellRenderer: surfaceCellRenderer, filter: 'customSetFilter' },
            { field: 'path', headerName: cfg.t.path_ac70412e, flex: 2, minWidth: 0, cellClass: 'ep-registry-path-cell', cellStyle: { display: 'flex', alignItems: 'center', minWidth: 0, overflow: 'hidden', maxWidth: '100%' }, cellRenderer: pathCellRenderer, filter: 'agTextColumnFilter', tooltipValueGetter: function (p) { return p.data && !p.data.__epGroupHeader && p.data.path ? p.data.path : ''; } },
            { field: 'methodsStr', headerName: cfg.t.methods_20c51b5f, width: 110, cellRenderer: methodsCellRenderer, filter: 'agTextColumnFilter', valueGetter: function (p) { return p.data && !p.data.__epGroupHeader ? p.data.methodsStr : ''; } },
            {
                field: 'auth',
                headerName: cfg.t.auth_632c9594,
                headerTooltip: cfg.t.how_callers_are_authenticated_hover_an_i_ef02143d,
                width: 80,
                maxWidth: 100,
                cellRenderer: authCellRenderer,
                filter: 'customSetFilter',
            },
            { field: 'description', headerName: cfg.t.description_b5a7adde, flex: 1, minWidth: 0, cellClass: 'ep-registry-desc-cell', cellStyle: { display: 'flex', alignItems: 'center', minWidth: 0, overflow: 'hidden', maxWidth: '100%' }, cellRenderer: descriptionCellRenderer, filter: 'agTextColumnFilter', tooltipValueGetter: function (p) { return p.data && !p.data.__epGroupHeader && p.data.description != null ? String(p.data.description) : ''; } },
            { field: 'consumers', headerName: cfg.t.consumers_1ebe06b1, width: 140, hide: true, filter: 'agTextColumnFilter', cellClass: 'font-mono text-xs text-gray-600' },
            {
                field: 'total_requests',
                headerName: cfg.t.requests_b134a801,
                width: 85,
                /* Avoid built-in numericColumn: it applies ag-right-aligned-header in LTR, which moves the filter menu icon to the left of the title. */
                filter: 'agNumberColumnFilter',
                cellClass: 'text-right tabular-nums ag-right-aligned-cell',
                valueFormatter: function (p) {
                    if (p.data && p.data.__epGroupHeader) return '';
                    var v = p.value;
                    if (v == null || v === '') return '';
                    var n = Number(v);
                    if (!isFinite(n)) return '';
                    return n.toLocaleString(undefined, { maximumFractionDigits: 0, useGrouping: true });
                },
            },
            { field: 'success_rate', headerName: cfg.t.success_505a83f2, width: 110, cellRenderer: successCellRenderer, filter: 'agNumberColumnFilter' },
            {
                field: 'flags',
                headerName: cfg.t.flags_4ea7801f,
                width: 100,
                cellDataType: false,
                cellRenderer: flagsCellRenderer,
                filter: false,
                sortable: false,
                valueFormatter: function (p) {
                    if (p.data && p.data.__epGroupHeader) return '';
                    var v = p.value;
                    if (!Array.isArray(v) || !v.length) return '';
                    return v.map(function (f) { return f && f.type ? String(f.type) : ''; }).filter(Boolean).join(', ');
                },
            },
        ];

        var gridHelper = new AgGridHelper({
            containerId: 'epRegistryGrid',
            templateId: 'api-mgmt-endpoint-registry',
            columnDefs: columnDefs,
            rowData: gridRowData,
            contextMenuLabels: {
                copyUrl: cfg.t.copy_url_8f2e1a0b,
            },
            columnVisibilityOptions: {
                buttonPlaceholderId: 'ep-registry-col-vis-placeholder',
                persistOnChange: true,
                enableExport: false,
                enableReset: true,
            },
            heightOptions: { minHeight: 280, maxHeight: 800, maxRowsToShow: 0, viewportOffset: 200 },
            /* AgGridHelper merges `options` into grid options; `gridOptions` is ignored. */
            options: {
                pagination: false,
                /* Native browser tooltips for headerTooltip (Auth column) and tooltipValueGetter cells. */
                enableBrowserTooltips: true,
                embedFullWidthRows: true,
                components: {
                    epRegistryGroupFw: EpRegistryGroupFullWidthRenderer,
                },
                isFullWidthRow: function (p) {
                    var rn = p && (p.rowNode || p.node);
                    return !!(rn && rn.data && rn.data.__epGroupHeader);
                },
                fullWidthCellRenderer: 'epRegistryGroupFw',
                getRowId: function (p) {
                    var d = p.data;
                    if (!d) return 'ep:empty';
                    if (d.__epGroupHeader) return 'epg:' + String(d.__epGroupKey || '');
                    return 'ep:' + String(d.surface || '') + ':' + String(d.path || '') + ':' + String(d.methodsStr || '');
                },
                getRowHeight: function (p) {
                    if (p.data && p.data.__epGroupHeader) return 36;
                    return undefined;
                },
                rowSelection: { mode: 'multiRow', checkboxes: false, headerCheckbox: false, enableClickSelection: false },
                selectionColumnDef: { hide: true },
                isExternalFilterPresent: function () { return isExternalFilterPresent(); },
                doesExternalFilterPass: function (params) {
                    return externalFilterPass(epRegistryRowNodeFromFilterParams(params));
                },
                getRowClass: function (p) {
                    var d = p.data;
                    if (!d) return '';
                    if (d.__epGroupHeader) return 'ep-registry-group-header-row';
                    if (d.undocumented) return 'ep-ag-row-undocumented';
                    if (d.stale) return 'ep-ag-row-stale';
                    if (d.has_flags) return 'ep-ag-row-flagged';
                    return '';
                },
                defaultColDef: {
                    sortable: false,
                    resizable: true,
                    filter: true,
                    wrapText: false,
                    autoHeight: false,
                },
                onFirstDataRendered: function () {
                    applyEpRegistryCellClipping('onFirstDataRendered');
                    requestAnimationFrame(function () {
                        requestAnimationFrame(function () {
                            applyEpRegistryCellClipping('onFirstDataRendered+2rAF');
                        });
                    });
                    if (typeof window.updateEndpointLinks === 'function') window.updateEndpointLinks();
                    updateFooterAndEmpty();
                },
                onGridSizeChanged: function () {
                    if (epRegistryGridSizeFitTimer) clearTimeout(epRegistryGridSizeFitTimer);
                    epRegistryGridSizeFitTimer = setTimeout(function () {
                        epRegistryGridSizeFitTimer = null;
                        try {
                            if (epRegistryGridApi && typeof epRegistryGridApi.sizeColumnsToFit === 'function') {
                                epRegistryGridApi.sizeColumnsToFit();
                            }
                        } catch (e) {}
                    }, 80);
                },
                onColumnResized: function () {
                    scheduleEpRegistryCellClipping('onColumnResized');
                },
                onBodyScroll: function (ev) {
                    if (ev && ev.direction === 'horizontal') return;
                    scheduleEpRegistryCellClipping('onBodyScroll');
                },
                onFilterChanged: function () {
                    updateFooterAndEmpty();
                    scheduleEpRegistryCellClipping('onFilterChanged');
                    scheduleEpColumnFilterUrlSync();
                },
            },
        });

        epRegistryGridApi = gridHelper.initialize();
        window.epRegistryGridApi = epRegistryGridApi;
        if (!epRegistryGridApi) {
            console.warn('[ep-registry] AgGridHelper.initialize() returned null (check #epRegistryGrid in DOM)');
        }

        if (loadingEl) loadingEl.style.display = 'none';
        if (containerEl) containerEl.style.display = 'block';
        window.__epRegistryGridInited = true;
        if (typeof window.updateEndpointLinks === 'function') window.updateEndpointLinks();
        updateFooterAndEmpty();

        /* sizeColumnsToFit called here (post-init, epRegistryGridApi is guaranteed set) so columns
           fill the panel. onFirstDataRendered's ev.api is undefined in this AG Grid build so we cannot
           rely on that timing. AgGridHelper also fires its own sizeColumnsToFit via applyGridHeight. */
        setTimeout(function () {
            try {
                if (epRegistryGridApi && typeof epRegistryGridApi.sizeColumnsToFit === 'function') {
                    epRegistryGridApi.sizeColumnsToFit();
                }
            } catch (e) {}
            var raw = window.__apiMgmtUrlExtra && window.__apiMgmtUrlExtra.ep_f;
            if (raw && epRegistryGridApi && typeof epRegistryGridApi.setFilterModel === 'function') {
                try {
                    var m = JSON.parse(decodeURIComponent(raw));
                    if (m && typeof m === 'object') {
                        epRegistryGridApi.setFilterModel(m);
                        if (typeof epRegistryGridApi.onFilterChanged === 'function') {
                            epRegistryGridApi.onFilterChanged();
                        } else if (typeof epRegistryGridApi.refreshClientSideRowModel === 'function') {
                            epRegistryGridApi.refreshClientSideRowModel('filter');
                        }
                    }
                } catch (err) {}
            }
            epRegistryFilterUrlSyncReady = true;
        }, 250);
    }

    function tryInitGrid() {
        var panel = document.getElementById('panel-registry');
        if (!panel || panel.classList.contains('hidden')) return;
        initEpRegistryGrid();
    }

    if (clearColFiltersBtn) {
        clearColFiltersBtn.addEventListener('click', function () {
            clearEpRegistryColumnFilters();
        });
    }

    surfaceBtns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            if (btn.disabled) return;
            var surf = btn.dataset.surface || 'all';
            if (surf !== 'all' && activeSurface === surf) {
                activeSurface = 'all';
                var allB = document.querySelector('.ep-surface-btn[data-surface="all"]');
                if (allB) styleActiveBtn(allB);
            } else {
                activeSurface = surf;
                styleActiveBtn(btn);
            }
            refreshExternalFilter();
            window.__apiMgmtUrlExtra.surface = activeSurface;
            if (typeof window.apiMgmtSyncUrl === 'function') window.apiMgmtSyncUrl();
        });
    });

    document.addEventListener('click', function (e) {
        var badge = e.target.closest && e.target.closest('.ep-flag-badge');
        if (badge && badge.closest('#epRegistryGrid')) {
            e.stopPropagation();
            var flaggedBtn = document.querySelector('.ep-surface-btn[data-surface="flagged"]');
            if (flaggedBtn && !flaggedBtn.disabled) flaggedBtn.click();
        }
    });

    document.addEventListener('api-mgmt-tab-activated', function (e) {
        if (e.detail && e.detail.tab === 'registry') {
            requestAnimationFrame(function () {
                tryInitGrid();
                if (epRegistryGridApi) {
                    try {
                        if (typeof epRegistryGridApi.doLayout === 'function') epRegistryGridApi.doLayout();
                        if (typeof epRegistryGridApi.sizeColumnsToFit === 'function') epRegistryGridApi.sizeColumnsToFit();
                    } catch (err) {}
                }
            });
        }
    });

    var exportBtn = document.getElementById('epExportBtn');
    if (exportBtn) {
        exportBtn.addEventListener('click', function () {
            var md = buildReport();
            var orig = exportBtn.innerHTML;
            function resetBtn(success) {
                exportBtn.innerHTML = success ? '<i class="fas fa-check mr-1.5"></i>Copied!' : '<i class="fas fa-download mr-1.5"></i>Downloaded';
                exportBtn.classList.toggle('btn-success', success);
                setTimeout(function () {
                    exportBtn.innerHTML = orig;
                    exportBtn.classList.remove('btn-success');
                }, 2500);
            }
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(md).then(function () { resetBtn(true); }).catch(function () { downloadMd(md); resetBtn(false); });
            } else {
                downloadMd(md);
                resetBtn(false);
            }
        });
    }

    var allBtn = document.querySelector('.ep-surface-btn[data-surface="all"]');
    var surfBtnRestore = document.querySelector('.ep-surface-btn[data-surface="' + activeSurface + '"]');
    if (surfBtnRestore && !surfBtnRestore.disabled) {
        styleActiveBtn(surfBtnRestore);
    } else if (allBtn) {
        activeSurface = 'all';
        window.__apiMgmtUrlExtra.surface = 'all';
        styleActiveBtn(allBtn);
    }

    epAiIdentityTooltipInit();

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', tryInitGrid);
    } else {
        tryInitGrid();
    }
})();
