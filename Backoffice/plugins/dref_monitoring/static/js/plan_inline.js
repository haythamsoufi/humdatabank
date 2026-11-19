(function () {
    'use strict';

    var root = document.querySelector('[data-dref-plan-edit]');
    if (!root) return;
    var form = root.querySelector('[data-dref-plan-form]');
    var start = root.querySelector('[data-dref-plan-start]');
    if (!form || !start) return;

    function rowFields(box) {
        var row = box.closest('[data-dref-add-row]');
        return row ? row.querySelectorAll('[data-add-field]') : [];
    }

    function setEditing(on) {
        if (!on) form.reset();
        root.classList.toggle('is-editing', on);
        form.querySelectorAll('.dref-plan-field').forEach(function (field) {
            field.disabled = field.hasAttribute('data-add-field') ? true : !on;
        });
        form.querySelectorAll('[data-dref-add]').forEach(function (box) {
            box.disabled = !on;
            if (!on) box.checked = false;
        });
    }

    start.addEventListener('click', function () {
        setEditing(true);
        var reason = form.querySelector('[name="justification"]');
        if (reason) reason.focus();
    });

    var cancel = form.querySelector('[data-dref-plan-cancel]');
    if (cancel) {
        cancel.addEventListener('click', function () {
            setEditing(false);
        });
    }

    form.querySelectorAll('[data-dref-add]').forEach(function (box) {
        box.addEventListener('change', function () {
            rowFields(box).forEach(function (field) {
                field.disabled = !box.checked;
            });
        });
    });
})();
