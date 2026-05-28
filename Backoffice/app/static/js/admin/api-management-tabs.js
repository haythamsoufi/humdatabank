(function () {
    'use strict';
    window.__apiMgmtUrlExtra = window.__apiMgmtUrlExtra || { surface: 'all', ep_f: '', vol_p: 'daily', vol_e: 'all' };
    try {
        var u0 = new URLSearchParams(window.location.search);
        if (u0.has('surface')) window.__apiMgmtUrlExtra.surface = u0.get('surface') || 'all';
        if (u0.has('ep_f')) window.__apiMgmtUrlExtra.ep_f = u0.get('ep_f') || '';
        if (u0.has('vol_p')) window.__apiMgmtUrlExtra.vol_p = u0.get('vol_p') || 'daily';
        if (u0.has('vol_e')) window.__apiMgmtUrlExtra.vol_e = u0.get('vol_e') || 'all';
    } catch (e) {}

    var KEYS = { tab: 'tab', surface: 'surface', ep_f: 'ep_f', vol_p: 'vol_p', vol_e: 'vol_e' };

    function getActiveTabId() {
        var el = document.querySelector('#api-mgmt-tabs .settings-tab[aria-selected="true"]');
        return (el && el.getAttribute('data-tab')) || 'registry';
    }

    function syncApiMgmtUrl() {
        var usp = new URLSearchParams();
        var tab = getActiveTabId();
        if (tab !== 'registry') usp.set(KEYS.tab, tab);
        var ex = window.__apiMgmtUrlExtra || {};
        if (ex.surface && ex.surface !== 'all') usp.set(KEYS.surface, ex.surface);
        if (ex.ep_f) usp.set(KEYS.ep_f, ex.ep_f);
        if (ex.vol_p && ex.vol_p !== 'daily') usp.set(KEYS.vol_p, ex.vol_p);
        if (ex.vol_e && ex.vol_e !== 'all') usp.set(KEYS.vol_e, ex.vol_e);
        var qs = usp.toString();
        var url = qs ? (window.location.pathname + '?' + qs) : window.location.pathname;
        window.history.replaceState({}, '', url);
    }
    window.apiMgmtSyncUrl = syncApiMgmtUrl;

    function runApiMgmtTabs() {
        const A = window.AdminUnderlineTabs;
        const tabs = document.querySelectorAll('#api-mgmt-tabs .settings-tab');
        if (!tabs.length || !A) return;
        function activate(tabId) {
            A.activateStripTab('#api-mgmt-tabs', tabId, { panelSelector: '.settings-panel' });
            document.dispatchEvent(new CustomEvent('api-mgmt-tab-activated', { detail: { tab: tabId } }));
        }
        tabs.forEach(function (btn) {
            btn.addEventListener('click', function () {
                const id = btn.getAttribute('data-tab');
                if (!id) return;
                activate(id);
                syncApiMgmtUrl();
            });
        });
        var tabTarget = '';
        try {
            var u = new URLSearchParams(window.location.search);
            tabTarget = (u.get(KEYS.tab) || '').trim();
        } catch (e) {}
        if (!tabTarget) {
            const hash = (location.hash || '').replace('#', '');
            if (hash && document.getElementById('panel-' + hash)) tabTarget = hash;
        }
        if (!tabTarget || !document.getElementById('panel-' + tabTarget)) {
            tabTarget = 'registry';
        }
        activate(tabTarget);
        if (window.location.hash) {
            window.history.replaceState({}, '', window.location.pathname + window.location.search);
        }
        syncApiMgmtUrl();
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', runApiMgmtTabs);
    } else {
        runApiMgmtTabs();
    }
})();
