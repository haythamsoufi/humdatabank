(function () {
    'use strict';
    var A = window.AdminUnderlineTabs;
    var root = document.getElementById('dref-settings-tabs');
    if (!root || !A) {
        return;
    }

    function activate(tabId) {
        A.activateStripTab('#dref-settings-tabs', tabId, { panelSelector: '.settings-panel' });
        try {
            var url = new URL(window.location.href);
            if (tabId === 'overview') url.searchParams.delete('tab');
            else url.searchParams.set('tab', tabId);
            window.history.replaceState(null, '', url.pathname + url.search);
        } catch (e) { /* ignore */ }
    }

    root.querySelectorAll('.settings-tab').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var tabId = this.getAttribute('data-tab');
            if (tabId) activate(tabId);
        });
    });

    document.querySelectorAll('[data-dref-settings-tab]').forEach(function (el) {
        el.addEventListener('click', function () {
            var tabId = el.getAttribute('data-dref-settings-tab');
            if (tabId) activate(tabId);
        });
    });

    document.addEventListener('submit', function (event) {
        var form = event.target;
        if (!(form instanceof HTMLFormElement)) {
            return;
        }
        var panel = form.closest('.settings-panel');
        if (!panel || panel.id.indexOf('panel-') !== 0) {
            return;
        }
        if (form.querySelector('input[name="tab"]')) {
            return;
        }
        var input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'tab';
        input.value = panel.id.slice('panel-'.length);
        form.appendChild(input);
    }, true);
})();
