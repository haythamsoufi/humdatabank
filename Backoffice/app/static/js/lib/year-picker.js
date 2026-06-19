/**
 * Year Picker — compact stepper with prev/next, direct year entry,
 * and a year-grid calendar popup triggered by the calendar icon button.
 *
 * Markup: wrap a year <input type="number"> in [data-year-picker].
 * Optional data-year-min / data-year-max on the wrapper or input.
 * The calendar toggle must carry [data-year-picker-calendar].
 */
(function () {
    'use strict';

    var YEARS_PER_PAGE = 12; // 3 rows × 4 columns

    /** Currently open calendar root (only one at a time). */
    var _activeRoot = null;

    // ── Helpers ──────────────────────────────────────────────────────────────

    function getBounds(input, root) {
        var source = input || root;
        var min = parseInt(source.getAttribute('data-year-min') || source.min || '2000', 10);
        var max = parseInt(source.getAttribute('data-year-max') || source.max || '2100', 10);
        return {
            min: Number.isFinite(min) ? min : 2000,
            max: Number.isFinite(max) ? max : 2100,
        };
    }

    function clampYear(value, min, max) {
        var n = parseInt(value, 10);
        if (!Number.isFinite(n)) return null;
        return Math.min(max, Math.max(min, n));
    }

    function updateButtonState(input, root) {
        var bounds = getBounds(input, root);
        var current = parseInt(input.value, 10);
        var decBtn = root.querySelector('[data-year-picker-decrement]');
        var incBtn = root.querySelector('[data-year-picker-increment]');
        if (decBtn) decBtn.disabled = !Number.isFinite(current) || current <= bounds.min;
        if (incBtn) incBtn.disabled = !Number.isFinite(current) || current >= bounds.max;
    }

    function setYear(input, root, year, dispatch) {
        var bounds = getBounds(input, root);
        var clamped = clampYear(year, bounds.min, bounds.max);
        if (clamped === null) return;
        var str = String(clamped);
        var changed = input.value !== str;
        input.value = str;
        updateButtonState(input, root);
        if (changed && dispatch !== false) {
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }

    /** First year of the 12-year page containing `year`. */
    function pageStart(year) {
        return Math.floor(year / YEARS_PER_PAGE) * YEARS_PER_PAGE;
    }

    // ── Calendar DOM builder ──────────────────────────────────────────────────

    function buildCalendarEl(input, root, rangeStart) {
        var bounds = getBounds(input, root);
        var selected = parseInt(input.value, 10);
        var currentYear = new Date().getFullYear();
        var rangeEnd = rangeStart + YEARS_PER_PAGE - 1;

        var cal = document.createElement('div');
        cal.className = 'year-picker-calendar';
        cal.setAttribute('role', 'listbox');
        cal.setAttribute('aria-label', 'Select year');

        // ── Header: prev nav | range label | next nav ──
        var header = document.createElement('div');
        header.className = 'year-picker-calendar-header';

        var prevBtn = document.createElement('button');
        prevBtn.type = 'button';
        prevBtn.className = 'year-picker-calendar-nav';
        prevBtn.setAttribute('aria-label', 'Previous years');
        prevBtn.innerHTML = '<i class="fas fa-chevron-left" aria-hidden="true"></i>';
        prevBtn.disabled = rangeStart <= bounds.min;

        var rangeLabel = document.createElement('span');
        rangeLabel.className = 'year-picker-calendar-range';
        rangeLabel.textContent = rangeStart + '\u2013' + rangeEnd;

        var nextBtn = document.createElement('button');
        nextBtn.type = 'button';
        nextBtn.className = 'year-picker-calendar-nav';
        nextBtn.setAttribute('aria-label', 'Next years');
        nextBtn.innerHTML = '<i class="fas fa-chevron-right" aria-hidden="true"></i>';
        nextBtn.disabled = rangeEnd >= bounds.max;

        header.appendChild(prevBtn);
        header.appendChild(rangeLabel);
        header.appendChild(nextBtn);
        cal.appendChild(header);

        // ── Year grid ──
        var grid = document.createElement('div');
        grid.className = 'year-picker-calendar-grid';

        for (var y = rangeStart; y <= rangeEnd; y++) {
            (function (year) {
                var btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'year-picker-year-btn';
                btn.setAttribute('role', 'option');
                btn.textContent = String(year);

                var isDisabled = year < bounds.min || year > bounds.max;
                btn.disabled = isDisabled;

                if (year === selected) {
                    btn.classList.add('is-selected');
                    btn.setAttribute('aria-selected', 'true');
                }
                if (year === currentYear) {
                    btn.classList.add('is-current');
                }

                if (!isDisabled) {
                    btn.addEventListener('click', function () {
                        setYear(input, root, year);
                        closeCalendar(root);
                        var toggle = root.querySelector('[data-year-picker-calendar]');
                        if (toggle) toggle.focus();
                    });
                }

                grid.appendChild(btn);
            })(y);
        }

        cal.appendChild(grid);

        // ── Decade navigation ──
        prevBtn.addEventListener('click', function () {
            rerenderCalendar(input, root, rangeStart - YEARS_PER_PAGE);
        });
        nextBtn.addEventListener('click', function () {
            rerenderCalendar(input, root, rangeStart + YEARS_PER_PAGE);
        });

        return cal;
    }

    // ── Open / close / rerender ───────────────────────────────────────────────

    function openCalendar(root, input) {
        if (_activeRoot && _activeRoot !== root) {
            closeCalendar(_activeRoot);
        }
        closeCalendarDom(root);

        var selected = parseInt(input.value, 10);
        var base = Number.isFinite(selected) ? selected : new Date().getFullYear();
        var cal = buildCalendarEl(input, root, pageStart(base));

        root._ypCal = cal;
        root.appendChild(cal);
        _activeRoot = root;

        var toggle = root.querySelector('[data-year-picker-calendar]');
        if (toggle) toggle.setAttribute('aria-expanded', 'true');
    }

    function rerenderCalendar(input, root, newStart) {
        var bounds = getBounds(input, root);
        var clamped = Math.max(bounds.min, Math.min(bounds.max - YEARS_PER_PAGE + 1, newStart));
        closeCalendarDom(root);
        var cal = buildCalendarEl(input, root, clamped);
        root._ypCal = cal;
        root.appendChild(cal);
    }

    function closeCalendarDom(root) {
        if (root._ypCal) {
            root._ypCal.remove();
            root._ypCal = null;
        }
    }

    function closeCalendar(root) {
        closeCalendarDom(root);
        var toggle = root.querySelector('[data-year-picker-calendar]');
        if (toggle) toggle.setAttribute('aria-expanded', 'false');
        if (_activeRoot === root) _activeRoot = null;
    }

    // Close open calendar when clicking outside any picker
    document.addEventListener('pointerdown', function (e) {
        if (_activeRoot && !_activeRoot.contains(e.target)) {
            closeCalendar(_activeRoot);
        }
    }, true);

    // ── Per-picker initialisation ─────────────────────────────────────────────

    function initPicker(root) {
        if (!root || root.dataset.yearPickerInit === '1') return;
        var input = root.querySelector('.year-picker-input, input[type="number"]');
        if (!input) return;

        root.dataset.yearPickerInit = '1';

        var decBtn = root.querySelector('[data-year-picker-decrement]');
        var incBtn = root.querySelector('[data-year-picker-increment]');
        var calToggle = root.querySelector('[data-year-picker-calendar]');

        function step(delta) {
            var current = parseInt(input.value, 10);
            var base = Number.isFinite(current) ? current : new Date().getFullYear();
            setYear(input, root, base + delta);
        }

        if (decBtn) decBtn.addEventListener('click', function () { step(-1); });
        if (incBtn) incBtn.addEventListener('click', function () { step(1); });

        if (calToggle) {
            calToggle.addEventListener('click', function () {
                if (root._ypCal) {
                    closeCalendar(root);
                } else {
                    openCalendar(root, input);
                }
            });
        }

        // Strip any non-digit characters that slip through (e.g. mobile IME)
        input.addEventListener('input', function () {
            var cleaned = input.value.replace(/\D/g, '').slice(0, 4);
            if (cleaned !== input.value) input.value = cleaned;
            updateButtonState(input, root);
        });

        input.addEventListener('blur', function () {
            var raw = String(input.value || '').trim();
            if (!raw) {
                updateButtonState(input, root);
                return;
            }
            setYear(input, root, parseInt(raw, 10));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        });

        // Allow only digits; block everything else (letters, symbols, e, +, -)
        input.addEventListener('keydown', function (e) {
            if (e.key === 'ArrowUp') { e.preventDefault(); step(1); return; }
            if (e.key === 'ArrowDown') { e.preventDefault(); step(-1); return; }

            var isNav = ['Backspace', 'Delete', 'Tab', 'ArrowLeft', 'ArrowRight',
                          'Home', 'End', 'Enter'].indexOf(e.key) !== -1;
            var isCtrlShortcut = (e.ctrlKey || e.metaKey) &&
                ['a', 'c', 'v', 'x', 'z'].indexOf(e.key.toLowerCase()) !== -1;
            var isDigit = /^\d$/.test(e.key);

            if (!isNav && !isCtrlShortcut && !isDigit) {
                e.preventDefault();
            }
        });

        // Strip non-digits from pasted content and enforce 4-char limit
        input.addEventListener('paste', function (e) {
            e.preventDefault();
            var text = (e.clipboardData || window.clipboardData).getData('text');
            var digits = text.replace(/\D/g, '');
            var start = input.selectionStart;
            var end   = input.selectionEnd;
            var next  = (input.value.slice(0, start) + digits + input.value.slice(end)).slice(0, 4);
            input.value = next;
            updateButtonState(input, root);
            input.dispatchEvent(new Event('input', { bubbles: true }));
        });

        // Escape closes the calendar
        root.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && root._ypCal) {
                e.stopPropagation();
                closeCalendar(root);
                if (calToggle) calToggle.focus();
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
