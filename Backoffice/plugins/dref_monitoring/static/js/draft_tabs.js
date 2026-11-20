(function () {
    'use strict';
    var exportRoot = document.getElementById('dref-export');
    var exportButton = document.getElementById('dref-export-btn');
    var exportMenu = document.getElementById('dref-export-menu');
    if (exportRoot && exportButton && exportMenu) {
        function closeExport() {
            exportMenu.classList.add('hidden');
            exportButton.setAttribute('aria-expanded', 'false');
        }

        exportButton.addEventListener('click', function (event) {
            event.stopPropagation();
            var open = exportMenu.classList.contains('hidden');
            exportMenu.classList.toggle('hidden', !open);
            exportButton.setAttribute('aria-expanded', open ? 'true' : 'false');
        });

        document.addEventListener('click', function (event) {
            if (!exportRoot.contains(event.target)) closeExport();
        });

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') closeExport();
        });
    }

    var A = window.AdminUnderlineTabs;
    var root = document.getElementById('dref-draft-tabs');
    if (!root || !A) {
        return;
    }

    function activate(tabId) {
        A.activateStripTab('#dref-draft-tabs', tabId, { panelSelector: '#dref-draft-panels .settings-panel' });
        try {
            var url = new URL(window.location.href);
            if (tabId === 'narrative') url.searchParams.delete('tab');
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
})();
