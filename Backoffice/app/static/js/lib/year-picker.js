/**
 * Year Picker — compact stepper control with prev/next and direct year entry.
 *
 * Markup: wrap a year <input type="number"> in [data-year-picker].
 * Optional data-year-min / data-year-max on the wrapper or input.
 */
(function () {
    'use strict';

    function getBounds(input, root) {
        const source = input || root;
        const min = parseInt(source.getAttribute('data-year-min') || source.min || '2000', 10);
        const max = parseInt(source.getAttribute('data-year-max') || source.max || '2100', 10);
        return {
            min: Number.isFinite(min) ? min : 2000,
            max: Number.isFinite(max) ? max : 2100,
        };
    }

    function clampYear(value, min, max) {
        const n = parseInt(value, 10);
        if (!Number.isFinite(n)) return null;
        return Math.min(max, Math.max(min, n));
    }

    function updateButtonState(input, root) {
        const { min, max } = getBounds(input, root);
        const current = parseInt(input.value, 10);
        const decBtn = root.querySelector('[data-year-picker-decrement]');
        const incBtn = root.querySelector('[data-year-picker-increment]');
        if (decBtn) decBtn.disabled = !Number.isFinite(current) || current <= min;
        if (incBtn) incBtn.disabled = !Number.isFinite(current) || current >= max;
    }

    function setYear(input, root, year, dispatch) {
        const { min, max } = getBounds(input, root);
        const clamped = clampYear(year, min, max);
        if (clamped === null) return;
        const str = String(clamped);
        const changed = input.value !== str;
        input.value = str;
        updateButtonState(input, root);
        if (changed && dispatch !== false) {
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }

    function initPicker(root) {
        if (!root || root.dataset.yearPickerInit === '1') return;
        const input = root.querySelector('.year-picker-input, input[type="number"]');
        if (!input) return;

        root.dataset.yearPickerInit = '1';

        const decBtn = root.querySelector('[data-year-picker-decrement]');
        const incBtn = root.querySelector('[data-year-picker-increment]');

        function step(delta) {
            const current = parseInt(input.value, 10);
            const base = Number.isFinite(current) ? current : new Date().getFullYear();
            setYear(input, root, base + delta);
        }

        if (decBtn) decBtn.addEventListener('click', function () { step(-1); });
        if (incBtn) incBtn.addEventListener('click', function () { step(1); });

        input.addEventListener('input', function () {
            updateButtonState(input, root);
        });

        input.addEventListener('blur', function () {
            const raw = String(input.value || '').trim();
            if (!raw) {
                updateButtonState(input, root);
                return;
            }
            setYear(input, root, parseInt(raw, 10));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        });

        input.addEventListener('keydown', function (e) {
            if (e.key === 'ArrowUp') {
                e.preventDefault();
                step(1);
            } else if (e.key === 'ArrowDown') {
                e.preventDefault();
                step(-1);
            }
        });

        updateButtonState(input, root);
    }

    function initAll(scope) {
        (scope || document).querySelectorAll('[data-year-picker]').forEach(initPicker);
    }

    window.YearPicker = {
        init: initAll,
        initPicker: initPicker,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { initAll(); });
    } else {
        initAll();
    }
})();
