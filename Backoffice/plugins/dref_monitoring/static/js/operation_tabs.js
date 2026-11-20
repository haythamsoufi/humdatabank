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

    var versionsModal = document.getElementById('dref-plan-versions-modal');
    var versionsOpen = document.getElementById('dref-plan-versions-open');
    var versionsDialog = versionsModal && window.ModalUtils
        ? window.ModalUtils.makeModal(versionsModal)
        : null;
    if (versionsOpen && versionsDialog) {
        versionsOpen.addEventListener('click', function () {
            versionsDialog.openModal();
        });
    }

    document.querySelectorAll('[data-dref-plan-confirm]').forEach(function (form) {
        form.addEventListener('submit', function (event) {
            var message = form.getAttribute('data-dref-plan-confirm') || '';
            if (message && !window.confirm(message)) {
                event.preventDefault();
            }
        });
    });

    var memberHelpModal = document.getElementById('dref-member-help-modal');
    var memberHelpOpen = document.getElementById('dref-member-help-open');
    var memberHelpDialog = memberHelpModal && window.ModalUtils
        ? window.ModalUtils.makeModal(memberHelpModal)
        : null;
    if (memberHelpOpen && memberHelpDialog) {
        memberHelpOpen.addEventListener('click', function () {
            memberHelpDialog.openModal();
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

    document.querySelectorAll('[data-dref-funds-toggle]').forEach(function (box) {
        var form = box.form;
        var date = form && form.querySelector('[data-dref-funds-date]');
        if (!date) {
            return;
        }
        function syncFundsDate() {
            date.disabled = !box.checked;
        }
        box.addEventListener('change', syncFundsDate);
        syncFundsDate();
    });

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

    function fieldMessage(field) {
        return field.getAttribute('data-dref-required') || '';
    }

    function isBlank(field) {
        return !String(field.value || '').trim();
    }

    function errorAnchor(field) {
        if (field.hasAttribute('data-dref-user-select') && window.jQuery) {
            var api = window.jQuery(field).data('select2');
            if (api && api.$container && api.$container[0]) {
                return api.$container[0];
            }
        }
        return field;
    }

    function clearFieldError(field) {
        field.classList.remove('dref-invalid');
        var anchor = errorAnchor(field);
        anchor.classList.remove('dref-invalid');
        var parent = anchor.parentElement;
        var error = parent && parent.querySelector('[data-dref-field-error]');
        if (error) {
            error.remove();
        }
    }

    function showFieldError(field) {
        var anchor = errorAnchor(field);
        var parent = anchor.parentElement;
        if (!parent) {
            return;
        }
        anchor.classList.add('dref-invalid');
        field.classList.add('dref-invalid');
        var error = parent.querySelector('[data-dref-field-error]');
        if (!error) {
            error = document.createElement('p');
            error.className = 'dref-field-error mt-1 text-xs text-red-600';
            error.setAttribute('data-dref-field-error', '');
            error.setAttribute('role', 'alert');
            anchor.insertAdjacentElement('afterend', error);
        }
        error.textContent = fieldMessage(field);
    }

    function syncRequired(field) {
        if (field.disabled || field.hasAttribute('data-dref-user-select')) {
            if (!field.hasAttribute('data-dref-user-select')) {
                field.setCustomValidity('');
            }
            return;
        }
        field.setCustomValidity(isBlank(field) ? fieldMessage(field) : '');
    }

    document.querySelectorAll('[data-dref-required]').forEach(function (field) {
        field.addEventListener('input', function () {
            syncRequired(field);
            if (!isBlank(field)) {
                clearFieldError(field);
            }
        });
        field.addEventListener('change', function () {
            if (!isBlank(field)) {
                clearFieldError(field);
            }
        });
        field.addEventListener('invalid', function () {
            syncRequired(field);
            showFieldError(field);
        });
    });

    document.addEventListener('click', function (event) {
        var button = event.target && event.target.closest
            ? event.target.closest('button, input[type="submit"]')
            : null;
        if (!button || button.type !== 'submit' || !button.form) {
            return;
        }
        button.form.querySelectorAll('[data-dref-required]').forEach(syncRequired);
    }, true);

    document.querySelectorAll('[data-dref-risk-status]').forEach(function (status) {
        var form = status.form;
        var field = form && form.querySelector('[data-dref-mitigation-field]');
        var note = form && form.querySelector('[data-dref-mitigation-note]');
        if (!field) {
            return;
        }
        function syncMitigation() {
            var locked = status.value === 'open';
            field.disabled = locked;
            field.classList.toggle('bg-gray-50', locked);
            field.classList.toggle('cursor-not-allowed', locked);
            if (note) {
                note.classList.toggle('hidden', !locked);
            }
            if (locked) {
                field.setCustomValidity('');
                clearFieldError(field);
            }
        }
        status.addEventListener('change', syncMitigation);
        syncMitigation();
    });

    document.addEventListener('submit', function (event) {
        var form = event.target;
        if (!(form instanceof HTMLFormElement)) {
            return;
        }
        var userSelect = form.querySelector('[data-dref-user-select]');
        if (userSelect && isBlank(userSelect)) {
            event.preventDefault();
            event.stopPropagation();
            showFieldError(userSelect);
            if (window.jQuery && window.jQuery(userSelect).data('select2')) {
                window.jQuery(userSelect).select2('open');
            } else {
                userSelect.focus();
            }
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

    var exportMenus = document.querySelectorAll('[data-dref-export]');
    function closeExportMenus(except) {
        exportMenus.forEach(function (menuRoot) {
            if (menuRoot === except) {
                return;
            }
            var menu = menuRoot.querySelector('[role="menu"]');
            var button = menuRoot.querySelector('button');
            if (menu) menu.classList.add('hidden');
            if (button) button.setAttribute('aria-expanded', 'false');
        });
    }
    exportMenus.forEach(function (menuRoot) {
        var button = menuRoot.querySelector('button');
        var menu = menuRoot.querySelector('[role="menu"]');
        if (!button || !menu) {
            return;
        }
        button.addEventListener('click', function (event) {
            event.stopPropagation();
            var open = menu.classList.contains('hidden');
            closeExportMenus(open ? menuRoot : null);
            menu.classList.toggle('hidden', !open);
            button.setAttribute('aria-expanded', open ? 'true' : 'false');
        });
    });
    document.addEventListener('click', function () {
        closeExportMenus(null);
    });
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') closeExportMenus(null);
    });
})();
