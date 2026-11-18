/**
 * In-place editing on the project page.
 * Edits stay on the page until the apply control is clicked.
 * A click outside the project panel, while something is unsaved, asks
 * whether to discard those edits or keep editing.
 */
(function () {
    'use strict';

    var root = document.querySelector('[data-inline-save]');
    if (!root) return;

    var saveUrl = root.getAttribute('data-inline-save');
    var applyLabel = root.getAttribute('data-apply-label') || 'Apply changes';
    var dialog = document.getElementById('projectInlineDialog');
    var errorEl = document.getElementById('projectInlineError');
    var fields = Array.prototype.slice.call(root.querySelectorAll('.project-inline-value'));
    var lastEdited = null;
    var swallowClick = false;
    if (!fields.length) return;

    fields.forEach(function (field) {
        field.setAttribute('data-original', field.getAttribute('data-value') || '');
        var text = field.querySelector('.project-inline-text');
        if (text) field.setAttribute('data-original-html', text.innerHTML);
        field.addEventListener('click', function (event) {
            if (event.target.closest('.project-inline-apply')) return;
            if (!field.classList.contains('is-editing')) openEditor(field);
        });
        field.addEventListener('keydown', function (event) {
            if (field.classList.contains('is-editing')) return;
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                openEditor(field);
            }
        });
    });

    if (dialog) {
        dialog.querySelector('[data-inline-discard]').addEventListener('click', discard);
        dialog.querySelector('[data-inline-continue]').addEventListener('click', continueEditing);
    }

    document.addEventListener('pointerdown', guardOutside, true);
    document.addEventListener('click', guardOutside, true);
    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') return;
        if (dialog && !dialog.hidden) {
            continueEditing();
            return;
        }
        var open = root.querySelector('.project-inline-value.is-editing');
        if (open) commitEditor(open);
    });

    function guardOutside(event) {
        if (event.type === 'click' && swallowClick) {
            swallowClick = false;
            event.preventDefault();
            event.stopPropagation();
            return;
        }
        if (dialog && !dialog.hidden) {
            if (!dialog.contains(event.target)) {
                event.preventDefault();
                event.stopPropagation();
            }
            return;
        }
        if (root.contains(event.target)) return;
        fields.forEach(function (field) {
            if (field.classList.contains('is-editing')) commitEditor(field);
        });
        if (!isDirty()) return;
        event.preventDefault();
        event.stopPropagation();
        if (event.type === 'pointerdown') swallowClick = true;
        if (dialog && dialog.hidden) {
            dialog.hidden = false;
            var keep = dialog.querySelector('[data-inline-continue]');
            if (keep) keep.focus();
        }
    }

    function openEditor(field) {
        lastEdited = field;
        fields.forEach(function (other) {
            if (other !== field && other.classList.contains('is-editing')) commitEditor(other);
        });
        var kind = field.getAttribute('data-kind') || 'text';
        var value = field.getAttribute('data-value') || '';
        var input = buildInput(kind, value, readOptions(field));
        input.className = 'project-inline-input';
        input.setAttribute('aria-label', field.getAttribute('data-label') || 'Edit');
        input.addEventListener('input', function () {
            field.setAttribute('data-value', input.value);
            refreshApply();
        });
        input.addEventListener('change', function () {
            field.setAttribute('data-value', input.value);
            refreshApply();
        });
        input.addEventListener('keydown', function (event) {
            if (event.key === 'Enter' && kind !== 'textarea') {
                event.preventDefault();
                commitEditor(field);
            }
            event.stopPropagation();
        });
        input.addEventListener('click', function (event) {
            event.stopPropagation();
        });
        field.classList.add('is-editing');
        field.classList.remove('is-dirty');
        field.replaceChildren(input);
        placeApply(field);
        input.focus();
        if (typeof input.select === 'function' && kind !== 'date') input.select();
    }

    function makeApplyButton() {
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'project-inline-apply';
        button.setAttribute('aria-label', applyLabel);
        var icon = document.createElement('i');
        icon.className = 'fas fa-check';
        icon.setAttribute('aria-hidden', 'true');
        button.appendChild(icon);
        button.addEventListener('pointerdown', function (event) {
            event.stopPropagation();
        });
        button.addEventListener('click', function (event) {
            event.preventDefault();
            event.stopPropagation();
            save();
        });
        return button;
    }

    function placeApply(field) {
        var dirty = currentValue(field) !== (field.getAttribute('data-original') || '');
        var existing = field.querySelector('.project-inline-apply');
        if (!dirty) {
            if (existing) existing.remove();
            return;
        }
        if (!existing) field.appendChild(makeApplyButton());
    }

    function readOptions(field) {
        var json = field.getAttribute('data-options-json');
        if (json) {
            try {
                return JSON.parse(json).map(function (option) {
                    return { value: String(option.value), label: String(option.label) };
                });
            } catch (err) {
                return [];
            }
        }
        return (field.getAttribute('data-options') || '').split(',').filter(Boolean).map(function (option) {
            return { value: option, label: option };
        });
    }

    function buildInput(kind, value, options) {
        var input;
        if (kind === 'select') {
            input = document.createElement('select');
            options.forEach(function (option) {
                var node = document.createElement('option');
                node.value = option.value;
                node.textContent = option.label;
                if (option.value === String(value)) node.selected = true;
                input.appendChild(node);
            });
            return input;
        }
        if (kind === 'textarea') {
            input = document.createElement('textarea');
            input.rows = 5;
            input.value = value;
            return input;
        }
        input = document.createElement('input');
        if (kind === 'date') input.type = 'date';
        else if (kind === 'number') {
            input.type = 'number';
            input.step = '0.01';
        } else if (kind === 'email') input.type = 'email';
        else input.type = 'text';
        input.value = value;
        return input;
    }

    function commitEditor(field) {
        var input = field.querySelector('input, select, textarea');
        if (input) field.setAttribute('data-value', input.value);
        paint(field);
        refreshApply();
    }

    function paint(field) {
        var value = field.getAttribute('data-value') || '';
        var original = field.getAttribute('data-original') || '';
        var text = document.createElement('span');
        text.className = 'project-inline-text';
        if (value === original) text.innerHTML = field.getAttribute('data-original-html') || '';
        else text.textContent = displayValue(field, value);
        var hint = document.createElement('i');
        hint.className = 'fas fa-pen project-inline-hint';
        hint.setAttribute('aria-hidden', 'true');
        field.classList.remove('is-editing');
        field.classList.toggle('is-dirty', value !== original);
        field.replaceChildren(text, hint);
        placeApply(field);
    }

    function displayValue(field, value) {
        if (!value) return '—';
        var match = readOptions(field).filter(function (option) { return option.value === String(value); })[0];
        if (match) return match.label;
        if ((field.getAttribute('data-kind') || '') === 'date' && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
            var parts = value.split('-');
            return parts[2] + '/' + parts[1] + '/' + parts[0];
        }
        return value;
    }

    function currentValue(field) {
        if (field.classList.contains('is-editing')) {
            var input = field.querySelector('input, select, textarea');
            if (input) return input.value || '';
        }
        return field.getAttribute('data-value') || '';
    }

    function isDirty() {
        return fields.some(function (field) {
            return currentValue(field) !== (field.getAttribute('data-original') || '');
        });
    }

    function applyButtons() {
        return root.querySelectorAll('.project-inline-apply');
    }

    function refreshApply() {
        fields.forEach(placeApply);
        if (errorEl && !isDirty()) errorEl.textContent = '';
    }

    function discard() {
        fields.forEach(function (field) {
            field.setAttribute('data-value', field.getAttribute('data-original') || '');
            field.classList.remove('is-editing');
            paint(field);
        });
        if (dialog) dialog.hidden = true;
        refreshApply();
    }

    function continueEditing() {
        if (dialog) dialog.hidden = true;
        if (lastEdited && !lastEdited.classList.contains('is-editing')) openEditor(lastEdited);
        else {
            var open = root.querySelector('.project-inline-value.is-editing input, .project-inline-value.is-editing select, .project-inline-value.is-editing textarea');
            if (open) open.focus();
        }
    }

    function csrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    }

    function save() {
        fields.forEach(function (field) {
            if (field.classList.contains('is-editing')) commitEditor(field);
        });
        var payload = {};
        fields.forEach(function (field) {
            if ((field.getAttribute('data-value') || '') !== (field.getAttribute('data-original') || '')) {
                payload[field.getAttribute('data-field')] = field.getAttribute('data-value') || '';
            }
        });
        if (!Object.keys(payload).length) {
            refreshApply();
            return;
        }
        applyButtons().forEach(function (button) { button.disabled = true; });
        if (errorEl) errorEl.textContent = '';
        fetch(saveUrl, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                Accept: 'application/json',
                'X-CSRFToken': csrfToken(),
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: JSON.stringify({ fields: payload }),
        })
            .then(function (response) {
                return response.json().catch(function () { return {}; }).then(function (body) {
                    return { ok: response.ok, body: body };
                });
            })
            .then(function (result) {
                if (result.ok && result.body && result.body.success) {
                    window.location.reload();
                    return;
                }
                applyButtons().forEach(function (button) { button.disabled = false; });
                if (errorEl) {
                    errorEl.textContent = (result.body && (result.body.error || result.body.message)) || 'Could not save the project.';
                }
            })
            .catch(function () {
                applyButtons().forEach(function (button) { button.disabled = false; });
                if (errorEl) errorEl.textContent = 'Could not save the project.';
            });
    }

    refreshApply();
})();
