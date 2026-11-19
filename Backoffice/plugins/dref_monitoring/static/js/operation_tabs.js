(function () {
    'use strict';

    var sourceModal = document.getElementById('dref-plan-source-modal');
    var sourceOpen = document.getElementById('dref-plan-source-open');
    var sourceDialog = sourceModal && window.ModalUtils
        ? window.ModalUtils.makeModal(sourceModal)
        : null;
    if (sourceOpen && sourceDialog) {
        sourceOpen.addEventListener('click', function () {
            sourceDialog.openModal();
        });
    }

    var excelOpen = document.querySelector('[data-excel-io-open="dref-plan-excel-modal"]');
    var excelDialog = null;
    if (excelOpen && excelOpen.dataset.excelModalModule && excelOpen.dataset.excelDropzoneModule) {
        Promise.all([
            import(excelOpen.dataset.excelModalModule),
            import(excelOpen.dataset.excelDropzoneModule)
        ]).then(function (modules) {
            excelDialog = modules[0].initExcelIoModal('#dref-plan-excel-modal');
            modules[1].initExcelImportDropzone('#dref-plan-excel-dropzone', {
                acceptExtensions: ['.xlsx'],
                resetOnModalClose: '#dref-plan-excel-modal'
            });
        }).catch(function (error) {
            console.error('Failed to open the Excel import modal', error);
        });
    }

    var A = window.AdminUnderlineTabs;
    var tabs = document.querySelectorAll('#dref-operation-tabs .settings-tab');
    if (!tabs.length || !A) {
        return;
    }

    function activate(tabId) {
        A.activateStripTab('#dref-operation-tabs', tabId, { panelSelector: '.settings-panel' });
    }

    tabs.forEach(function (btn) {
        btn.addEventListener('click', function () {
            var tabId = this.getAttribute('data-tab');
            if (!tabId) {
                return;
            }
            activate(tabId);
            if (sourceDialog) {
                sourceDialog.closeModal();
            }
            if (excelDialog) {
                excelDialog.close();
            }
            var url = new URL(window.location.href);
            url.searchParams.set('tab', tabId);
            window.history.replaceState(null, '', url.pathname + url.search);
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
