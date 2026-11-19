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

    function userResult(state) {
        if (!state.id || !state.element) {
            return state.text;
        }
        var name = state.element.getAttribute('data-name') || state.text;
        var email = state.element.getAttribute('data-email') || '';
        var wrap = document.createElement('span');
        wrap.className = 'block leading-tight';
        var nameEl = document.createElement('span');
        nameEl.className = 'block text-sm font-medium';
        nameEl.textContent = name;
        wrap.appendChild(nameEl);
        if (email && email !== name) {
            var emailEl = document.createElement('span');
            emailEl.className = 'block text-xs opacity-70';
            emailEl.textContent = email;
            wrap.appendChild(emailEl);
        }
        return wrap;
    }

    function enhanceUserSelect(select) {
        var $ = window.jQuery;
        if (!$ || !$.fn || !$.fn.select2 || !select) {
            return null;
        }
        var $select = $(select);
        if ($select.data('select2')) {
            return $select;
        }
        $select.select2({
            width: '100%',
            placeholder: select.getAttribute('data-placeholder') || '',
            allowClear: false,
            dropdownParent: $(document.body),
            minimumResultsForSearch: 0,
            dropdownCssClass: 'dref-user-dropdown',
            containerCssClass: 'mt-1',
            language: {
                noResults: function () {
                    return select.getAttribute('data-empty') || '';
                }
            },
            templateResult: userResult,
            templateSelection: function (state) {
                if (!state.id || !state.element) {
                    return state.text;
                }
                return state.element.getAttribute('data-name') || state.text;
            }
        });
        $select.on('select2:open', function () {
            var field = document.querySelector('.select2-container--open .select2-search__field');
            if (!field) {
                return;
            }
            field.setAttribute('placeholder', select.getAttribute('data-search') || '');
            field.focus();
        });
        return $select;
    }

    document.querySelectorAll('[data-dref-reveal]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var panel = document.getElementById(btn.getAttribute('data-dref-reveal') || '');
            if (!panel) {
                return;
            }
            var open = !panel.classList.toggle('hidden');
            btn.setAttribute('aria-expanded', open ? 'true' : 'false');
            var icon = btn.querySelector('i');
            if (icon) {
                icon.classList.toggle('fa-plus', !open);
                icon.classList.toggle('fa-times', open);
            }
            var userSelect = panel.querySelector('[data-dref-user-select]');
            if (!open && userSelect && window.jQuery) {
                var existing = window.jQuery(userSelect);
                if (existing.data('select2')) {
                    existing.select2('close');
                }
                return;
            }
            if (!open) {
                return;
            }
            if (userSelect) {
                var $select = enhanceUserSelect(userSelect);
                if ($select) {
                    $select.select2('open');
                    return;
                }
            }
            var field = panel.querySelector('input:not([type="hidden"]), textarea, select');
            if (field) {
                field.focus();
            }
        });
    });

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
