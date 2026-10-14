/** Matrix range selection + Excel-style copy/paste.
 *
 * Adds spreadsheet-like behaviour to matrix tables in the entry form:
 *   • Click-drag to select a rectangular range of cells (horizontal,
 *     vertical, or diagonal — any rectangle).
 *   • Shift+Click to extend the range from the current anchor.
 *   • Shift+Arrow keys to grow/shrink the range from the keyboard.
 *   • Ctrl/Cmd+A to select every editable cell in the matrix.
 *   • Ctrl/Cmd+C / Ctrl/Cmd+X to copy the selected range to the clipboard
 *     as TSV (tab between columns, newline between rows) — paste-ready in
 *     Excel / Google Sheets.
 *   • Ctrl/Cmd+V to paste a TSV block from Excel (or anywhere) into the
 *     grid when that block is the same size as the selection, or the same
 *     size as the editable cells available from the selection. A single
 *     value still pastes into one focused cell.
 *   • A multi-cell range is outlined with an animated dotted line and a
 *     Copy / Paste menu anchored to that rectangle.
 *
 * Coordinate model
 * ────────────────
 * A cell is addressed by { r, c } where:
 *   • r = index of its <tr.matrix-data-row> within the container, and
 *   • c = the <td>.cellIndex of the cell (so the leading row-header column
 *         and any mid-table row-total column line up with what the user
 *         sees). Column-total rows (.matrix-column-totals-row) are not
 *         matrix-data-rows, so they are naturally excluded.
 *
 * Only cells containing an <input data-cell-key> participate; computed
 * cells rendered as spans copy out as empty strings and are skipped on
 * paste, which keeps the rectangle aligned with the visual grid.
 */
import { debugLog, debugWarn } from '../debug.js';
import {
    __setMatrixNumericCellDisplay,
    __syncWholeNumberViolationHighlight,
} from './formatting.js';
import { _t } from './shared.js';

const SELECTED_CLASS = 'matrix-cell-selected';
const ACTIVE_CLASS = 'matrix-cell-active';
const SELECTING_CLASS = 'matrix-selecting';
const STYLE_ID = 'matrix-selection-styles';
const CHROME_ID = 'matrix-selection-chrome';
const MENU_SELECTOR = '.matrix-selection-menu';

/** Inject the selection highlight CSS once (avoids a Tailwind rebuild). */
function __ensureSelectionStyles() {
    if (typeof document === 'undefined' || document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
.matrix-container td.${SELECTED_CLASS} { background-color: rgba(37, 99, 235, 0.14) !important; }
.matrix-container td.${SELECTED_CLASS} input { background-color: transparent; }
.matrix-container td.${ACTIVE_CLASS} { outline: 2px solid #2563eb; outline-offset: -2px; }
.matrix-container.${SELECTING_CLASS},
.matrix-container.${SELECTING_CLASS} * { user-select: none !important; }
#${CHROME_ID} { display: contents; }
#${CHROME_ID}[hidden] { display: none !important; }
.matrix-selection-ants {
  position: fixed;
  z-index: 110;
  pointer-events: none;
  overflow: visible;
}
.matrix-selection-ants svg { width: 100%; height: 100%; overflow: visible; display: block; }
.matrix-selection-ants rect {
  fill: none;
  x: 1.25px;
  y: 1.25px;
  width: calc(100% - 2.5px);
  height: calc(100% - 2.5px);
}
.matrix-selection-ants-halo { stroke: #fff; stroke-width: 3.5; }
.matrix-selection-ants-dots {
  stroke: #1d4ed8;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-dasharray: 0.8 5.4;
  animation: matrix-selection-ants 0.45s linear infinite;
}
@keyframes matrix-selection-ants { to { stroke-dashoffset: -6.2; } }
@media (prefers-reduced-motion: reduce) {
  .matrix-selection-ants-dots { animation: none; }
}
.matrix-selection-menu {
  position: fixed;
  z-index: 111;
  pointer-events: auto;
  display: flex;
  flex-direction: column;
  min-width: 8.75rem;
  padding: 4px;
  background: #fff;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.16);
}
.matrix-selection-menu[hidden] { display: none !important; }
.matrix-selection-menu::before {
  content: "";
  position: absolute;
  width: 8px;
  height: 8px;
  background: #fff;
  border-left: 1px solid #d1d5db;
  border-top: 1px solid #d1d5db;
}
.matrix-selection-menu[data-placement="below"]::before {
  top: -5px;
  right: 16px;
  transform: rotate(45deg);
}
.matrix-selection-menu[data-placement="above"]::before {
  bottom: -5px;
  right: 16px;
  transform: rotate(45deg);
  border-left: 0;
  border-top: 0;
  border-right: 1px solid #d1d5db;
  border-bottom: 1px solid #d1d5db;
}
.matrix-selection-menu button {
  appearance: none;
  border: 0;
  background: transparent;
  text-align: start;
  font: inherit;
  font-size: 0.8125rem;
  line-height: 1.2;
  color: #111827;
  padding: 7px 10px;
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
}
.matrix-selection-menu-item { position: relative; display: block; }
.matrix-selection-menu-item + .matrix-selection-menu-item { margin-top: 2px; }
.matrix-selection-menu-item button { width: 100%; }
.matrix-selection-menu-item[data-tooltip]:hover::after,
.matrix-selection-menu-item[data-tooltip]:focus-within::after {
  content: attr(data-tooltip);
  position: absolute;
  right: calc(100% + 8px);
  top: 0;
  z-index: 2;
  width: max-content;
  max-width: 16rem;
  padding: 6px 8px;
  border-radius: 6px;
  background: #111827;
  color: #fff;
  font-size: 0.75rem;
  font-weight: 400;
  line-height: 1.35;
  white-space: normal;
  text-align: start;
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.2);
  pointer-events: none;
}
.matrix-selection-menu button:hover,
.matrix-selection-menu button:focus-visible {
  background: #eff6ff;
  color: #1d4ed8;
  outline: none;
}
.matrix-selection-menu button:disabled {
  color: #9ca3af;
  cursor: not-allowed;
  background: transparent;
}
`;
    (document.head || document.documentElement).appendChild(style);
}

const CLIPBOARD_READ_TIMEOUT_MS = 800;

function __fillTemplate(message, vars) {
    return Object.keys(vars || {}).reduce(
        (text, key) => text.split(`{${key}}`).join(String(vars[key])),
        message,
    );
}

function __eventElement(target) {
    if (!target) return null;
    if (target.nodeType === 3) return target.parentElement;
    return target;
}

function __writeClipboardText(text) {
    try {
        if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
            const pending = navigator.clipboard.writeText(text);
            if (pending && typeof pending.then === 'function') {
                return pending.catch(() => __writeClipboardViaTextarea(text));
            }
        }
    } catch (err) {
        // Fall through to the textarea path.
    }
    return __writeClipboardViaTextarea(text);
}

function __writeClipboardViaTextarea(text) {
    return new Promise((resolve, reject) => {
        const area = document.createElement('textarea');
        area.value = text;
        area.setAttribute('readonly', '');
        area.style.position = 'fixed';
        area.style.top = '0';
        area.style.left = '-9999px';
        document.body.appendChild(area);
        area.select();
        let ok = false;
        try {
            ok = document.execCommand('copy');
        } catch (err) {
            ok = false;
        }
        area.remove();
        if (ok) resolve();
        else reject(new Error('copy failed'));
    });
}

export const matrixSelectionMixin = {
    /**
     * Wire up range-selection + clipboard listeners. Called once from
     * setupEventListeners(). All listeners are delegated at the document
     * level so dynamically added matrices (repeat sections) are covered.
     */
    setupMatrixSelection() {
        __ensureSelectionStyles();
        this._ensureMatrixSelectionChrome();

        if (this.__matrixSelectionBound) return;
        this.__matrixSelectionBound = true;

        // { container, anchor: {r,c}, focus: {r,c}, dragging: bool }
        this._matrixSelection = null;

        // ── Mouse: start / extend / finish a drag-selection ──────────────
        document.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;
            const input = this._matrixSelectableInput(e.target);
            if (!input) return;

            const coord = this._matrixCellCoord(input);
            if (!coord) return;

            if (e.shiftKey && this._matrixSelection && this._matrixSelection.container === coord.container) {
                // Extend the existing range to the clicked cell.
                e.preventDefault();
                this._matrixSelection.focus = { r: coord.r, c: coord.c };
                this._renderMatrixSelection();
            } else {
                // Begin a fresh selection anchored on this cell. Do NOT
                // preventDefault so the input still focuses for editing.
                this._matrixSelection = {
                    container: coord.container,
                    anchor: { r: coord.r, c: coord.c },
                    focus: { r: coord.r, c: coord.c },
                    dragging: true,
                };
                this._renderMatrixSelection();
            }
        });

        document.addEventListener('mouseover', (e) => {
            const sel = this._matrixSelection;
            if (!sel || !sel.dragging) return;
            const input = this._matrixSelectableInput(e.target);
            if (!input) return;
            const coord = this._matrixCellCoord(input);
            if (!coord || coord.container !== sel.container) return;
            if (sel.focus.r === coord.r && sel.focus.c === coord.c) return;

            sel.focus = { r: coord.r, c: coord.c };
            // We've moved past the anchor cell → it's a real drag, so stop
            // the browser from selecting input text underneath.
            sel.container.classList.add(SELECTING_CLASS);
            const native = window.getSelection && window.getSelection();
            if (native && native.removeAllRanges) native.removeAllRanges();
            this._renderMatrixSelection();
        });

        document.addEventListener('mouseup', () => {
            if (this._matrixSelection && this._matrixSelection.dragging) {
                this._matrixSelection.dragging = false;
                this._matrixSelection.container.classList.remove(SELECTING_CLASS);
                // The outline is visible while dragging; the menu becomes
                // clickable once the pointer is released.
                this._syncMatrixSelectionChrome();
            }
        });

        // Clicking anywhere outside a matrix cell clears the range.
        // The Copy / Paste menu sits outside the table, so it must not count.
        document.addEventListener('mousedown', (e) => {
            if (!this._matrixSelection) return;
            const hit = __eventElement(e.target);
            if (hit && typeof hit.closest === 'function' && hit.closest(MENU_SELECTOR)) return;
            if (!this._matrixSelectableInput(e.target)) {
                this._clearMatrixSelection();
            }
        }, true);

        const repositionChrome = () => {
            if (!this._matrixSelection) return;
            if (this._matrixSelectionRaf != null) return;
            this._matrixSelectionRaf = requestAnimationFrame(() => {
                this._matrixSelectionRaf = null;
                this._positionMatrixSelectionChrome();
            });
        };
        window.addEventListener('scroll', repositionChrome, { passive: true });
        document.addEventListener('scroll', repositionChrome, { passive: true, capture: true });
        window.addEventListener('resize', repositionChrome);
        // A copy made in another app becomes visible when the tab is focused.
        window.addEventListener('focus', () => {
            if (this._matrixSelectionIsRange()) this._scheduleMatrixClipboardRead();
        });

        // ── Keyboard: Shift+Arrow extend, plain Arrow reset, Esc, Ctrl+A ──
        document.addEventListener('keydown', (e) => {
            const input = this._matrixSelectableInput(e.target);

            if (e.key === 'Escape' && this._matrixSelection) {
                this._clearMatrixSelection();
                return;
            }

            if (!input) return;

            // Select all editable cells in this matrix.
            if ((e.ctrlKey || e.metaKey) && (e.key === 'a' || e.key === 'A')) {
                const container = input.closest('.matrix-container');
                if (container) {
                    e.preventDefault();
                    this._selectWholeMatrix(container);
                }
                return;
            }

            if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) return;

            // handleKeyboardNavigation (registered earlier) moves focus for
            // plain arrows and calls preventDefault. This listener runs after
            // it, so document.activeElement is already the new cell.
            const coord = this._matrixCellCoord(input);
            if (!coord) return;

            // Prefer the cell the navigation handler just focused so the
            // highlight always tracks the real caret; fall back to our own
            // DOM step (e.g. variable text cells the nav handler skips).
            const moved = this._matrixFocusedCoord(coord.container);
            const next = (moved && (moved.r !== coord.r || moved.c !== coord.c))
                ? moved
                : (this._matrixStep(coord.container, coord, e.key) || coord);

            if (e.shiftKey) {
                // Extend selection to the newly reached cell.
                const anchor = (this._matrixSelection && this._matrixSelection.container === coord.container)
                    ? this._matrixSelection.anchor
                    : { r: coord.r, c: coord.c };
                e.preventDefault();
                this._matrixSelection = {
                    container: coord.container,
                    anchor,
                    focus: { r: next.r, c: next.c },
                    dragging: false,
                };
                this._renderMatrixSelection();
                const target = this._matrixCellInputAt(coord.container, next.r, next.c);
                if (target) { target.focus(); target.select?.(); }
            } else {
                // Plain navigation collapses the selection to the active cell.
                this._matrixSelection = {
                    container: coord.container,
                    anchor: { r: next.r, c: next.c },
                    focus: { r: next.r, c: next.c },
                    dragging: false,
                };
                this._renderMatrixSelection();
            }
        });

        // ── Clipboard ────────────────────────────────────────────────────
        document.addEventListener('copy', (e) => this._handleMatrixCopy(e));
        document.addEventListener('cut', (e) => this._handleMatrixCopy(e, true));
        document.addEventListener('paste', (e) => this._handleMatrixPaste(e));
    },

    /** The nearest selectable matrix cell input for an event target, or null. */
    _matrixSelectableInput(target) {
        if (!target || typeof target.closest !== 'function') return null;
        const input = target.closest('input[data-cell-key]');
        if (!input) return null;
        if (!input.closest('.matrix-container')) return null;
        return input;
    },

    /** Coordinate of the currently focused cell if it's inside `container`. */
    _matrixFocusedCoord(container) {
        const active = this._matrixSelectableInput(document.activeElement);
        if (!active || active.closest('.matrix-container') !== container) return null;
        return this._matrixCellCoord(active);
    },

    /** Coordinate { r, c, container } for a cell input. */
    _matrixCellCoord(input) {
        const td = input.closest('td');
        const tr = input.closest('tr.matrix-data-row');
        const container = input.closest('.matrix-container');
        if (!td || !tr || !container) return null;
        const rows = Array.from(container.querySelectorAll('tr.matrix-data-row'));
        const r = rows.indexOf(tr);
        if (r < 0) return null;
        return { r, c: td.cellIndex, container };
    },

    /** The input at a given coordinate, or null if the cell has none. */
    _matrixCellInputAt(container, r, c) {
        const rows = container.querySelectorAll('tr.matrix-data-row');
        const tr = rows[r];
        if (!tr) return null;
        const td = tr.cells ? tr.cells[c] : null;
        if (!td) return null;
        return td.querySelector('input[data-cell-key]');
    },

    /**
     * Next coordinate in the arrow direction that actually holds a cell
     * input, skipping gaps (e.g. computed-total spans). Returns null if the
     * edge is reached.
     */
    _matrixStep(container, coord, key) {
        const rows = container.querySelectorAll('tr.matrix-data-row');
        let { r, c } = coord;
        const maxR = rows.length - 1;
        const maxC = () => {
            const tr = rows[r];
            return tr && tr.cells ? tr.cells.length - 1 : 0;
        };
        const dr = key === 'ArrowUp' ? -1 : key === 'ArrowDown' ? 1 : 0;
        const dc = key === 'ArrowLeft' ? -1 : key === 'ArrowRight' ? 1 : 0;

        // Step until we land on a cell with an input or run off the grid.
        let steps = 0;
        const guard = (rows.length + 32) * 32;
        while (steps++ < guard) {
            r += dr; c += dc;
            if (r < 0 || r > maxR || c < 0 || c > maxC()) return null;
            if (this._matrixCellInputAt(container, r, c)) return { r, c };
        }
        return null;
    },

    /** Replace the visible highlight to match the current selection rectangle. */
    _renderMatrixSelection() {
        // Clear existing highlight everywhere (cheap; matrices are small).
        document.querySelectorAll(`.${SELECTED_CLASS}, .${ACTIVE_CLASS}`).forEach((el) => {
            el.classList.remove(SELECTED_CLASS, ACTIVE_CLASS);
        });

        const sel = this._matrixSelection;
        if (!sel) return;

        const { container, anchor, focus } = sel;
        const minR = Math.min(anchor.r, focus.r);
        const maxR = Math.max(anchor.r, focus.r);
        const minC = Math.min(anchor.c, focus.c);
        const maxC = Math.max(anchor.c, focus.c);

        for (let r = minR; r <= maxR; r++) {
            for (let c = minC; c <= maxC; c++) {
                const input = this._matrixCellInputAt(container, r, c);
                if (!input) continue;
                const td = input.closest('td');
                if (td) td.classList.add(SELECTED_CLASS);
            }
        }

        const activeInput = this._matrixCellInputAt(container, focus.r, focus.c);
        const activeTd = activeInput ? activeInput.closest('td') : null;
        if (activeTd) activeTd.classList.add(ACTIVE_CLASS);
        this._syncMatrixSelectionChrome();
    },

    /** Drop the current selection + highlight. */
    _clearMatrixSelection() {
        this._matrixSelection = null;
        this._matrixPasteValidationKeySeen = '';
        // Drop clipboard reads that started for the selection we just cleared.
        this._matrixClipboardEpoch = (this._matrixClipboardEpoch || 0) + 1;
        document.querySelectorAll(`.${SELECTED_CLASS}, .${ACTIVE_CLASS}`).forEach((el) => {
            el.classList.remove(SELECTED_CLASS, ACTIVE_CLASS);
        });
        this._syncMatrixSelectionChrome();
    },

    /** True when the selection covers more than one cell. */
    _matrixSelectionIsRange(sel = this._matrixSelection) {
        if (!sel) return false;
        return !this._matrixSelectionBounds(sel).single;
    },

    /** Inclusive row/column bounds of a selection rectangle. */
    _matrixSelectionBounds(sel) {
        const minR = Math.min(sel.anchor.r, sel.focus.r);
        const maxR = Math.max(sel.anchor.r, sel.focus.r);
        const minC = Math.min(sel.anchor.c, sel.focus.c);
        const maxC = Math.max(sel.anchor.c, sel.focus.c);
        return { minR, maxR, minC, maxC, single: minR === maxR && minC === maxC };
    },

    /** The table cell at a coordinate, whether or not it holds an input. */
    _matrixCellTdAt(container, r, c) {
        const rows = container.querySelectorAll('tr.matrix-data-row');
        const tr = rows[r];
        if (!tr || !tr.cells) return null;
        return tr.cells[c] || null;
    },

    /** Build the outline + Copy/Paste menu once. */
    _ensureMatrixSelectionChrome() {
        if (typeof document === 'undefined') return null;
        let chrome = document.getElementById(CHROME_ID);
        if (chrome) {
            this._matrixSelectionChrome = chrome;
            return chrome;
        }
        chrome = document.createElement('div');
        chrome.id = CHROME_ID;
        chrome.hidden = true;
        chrome.innerHTML = `
            <div class="matrix-selection-ants" aria-hidden="true">
                <svg focusable="false" aria-hidden="true">
                    <rect class="matrix-selection-ants-halo" x="1.25" y="1.25" width="calc(100% - 2.5px)" height="calc(100% - 2.5px)"></rect>
                    <rect class="matrix-selection-ants-dots" x="1.25" y="1.25" width="calc(100% - 2.5px)" height="calc(100% - 2.5px)"></rect>
                </svg>
            </div>
            <div class="matrix-selection-menu" role="menu" hidden></div>
        `;
        const menu = chrome.querySelector(MENU_SELECTOR);
        menu.setAttribute('aria-label', `${_t('Copy')}, ${_t('Paste')}`);
        const copyBtn = document.createElement('button');
        copyBtn.type = 'button';
        copyBtn.dataset.action = 'copy';
        copyBtn.setAttribute('role', 'menuitem');
        copyBtn.textContent = _t('Copy');
        const pasteBtn = document.createElement('button');
        pasteBtn.type = 'button';
        pasteBtn.dataset.action = 'paste';
        pasteBtn.setAttribute('role', 'menuitem');
        pasteBtn.textContent = _t('Paste');
        // The tooltip sits on the wrapper so it still shows when the button is disabled.
        [copyBtn, pasteBtn].forEach((btn) => {
            const wrap = document.createElement('span');
            wrap.className = 'matrix-selection-menu-item';
            wrap.appendChild(btn);
            menu.appendChild(wrap);
        });

        // Keep the cell focused so keyboard copy/paste still sees the matrix.
        menu.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;
            const hit = __eventElement(e.target);
            const btn = hit && hit.closest ? hit.closest('button[data-action]') : null;
            e.preventDefault();
            if (!btn || btn.disabled) return;
            if (btn.dataset.action === 'copy') this._copyMatrixSelectionViaMenu();
            else if (btn.dataset.action === 'paste') this._pasteMatrixSelectionViaMenu();
        });

        (document.body || document.documentElement).appendChild(chrome);
        this._matrixSelectionChrome = chrome;
        return chrome;
    },

    /** Show the dotted outline and menu for a range; hide them otherwise. */
    _syncMatrixSelectionChrome() {
        const chrome = this._ensureMatrixSelectionChrome();
        if (!chrome) return;
        if (!this._matrixSelectionIsRange()) {
            chrome.hidden = true;
            return;
        }
        this._positionMatrixSelectionChrome();
    },

    /**
     * Place the outline on the visible part of the selection rectangle and
     * drop the menu just under its bottom-right corner (above it if that
     * would leave the viewport).
     */
    _positionMatrixSelectionChrome() {
        const chrome = this._matrixSelectionChrome || this._ensureMatrixSelectionChrome();
        const sel = this._matrixSelection;
        if (!chrome || !sel || !this._matrixSelectionIsRange(sel)) {
            if (chrome) chrome.hidden = true;
            return;
        }
        const rect = this._matrixSelectionVisibleRect(sel);
        const ants = chrome.querySelector('.matrix-selection-ants');
        const menu = chrome.querySelector(MENU_SELECTOR);
        if (!rect || !ants || !menu) {
            chrome.hidden = true;
            return;
        }

        chrome.hidden = false;
        ants.style.top = `${rect.top}px`;
        ants.style.left = `${rect.left}px`;
        ants.style.width = `${rect.width}px`;
        ants.style.height = `${rect.height}px`;

        menu.hidden = false;
        // Ignore the menu while the pointer is still drawing the range.
        const drawing = !!sel.dragging;
        menu.style.pointerEvents = drawing ? 'none' : 'auto';
        menu.toggleAttribute('inert', drawing);
        if (!sel.dragging) this._touchMatrixPasteValidation(sel);

        const gap = 6;
        const menuW = menu.offsetWidth || 140;
        const menuH = menu.offsetHeight || 76;
        let top = rect.top + rect.height + gap;
        let placement = 'below';
        if (top + menuH > window.innerHeight - 8) {
            top = Math.max(8, rect.top - menuH - gap);
            placement = 'above';
        }
        let left = rect.left + rect.width - menuW;
        if (left < 8) left = 8;
        if (left + menuW > window.innerWidth - 8) left = Math.max(8, window.innerWidth - menuW - 8);
        menu.style.top = `${Math.round(top)}px`;
        menu.style.left = `${Math.round(left)}px`;
        menu.dataset.placement = placement;
    },

    /** Viewport rectangle of the selection, clipped to the scroll container. */
    _matrixSelectionVisibleRect(sel) {
        const { container } = sel;
        const { minR, maxR, minC, maxC } = this._matrixSelectionBounds(sel);
        let top = Infinity;
        let left = Infinity;
        let bottom = -Infinity;
        let right = -Infinity;
        let found = false;
        for (let r = minR; r <= maxR; r++) {
            for (let c = minC; c <= maxC; c++) {
                const td = this._matrixCellTdAt(container, r, c);
                if (!td) continue;
                const box = td.getBoundingClientRect();
                if (!box || box.width < 1 || box.height < 1) continue;
                found = true;
                top = Math.min(top, box.top);
                left = Math.min(left, box.left);
                bottom = Math.max(bottom, box.bottom);
                right = Math.max(right, box.right);
            }
        }
        if (!found) return null;

        const scroll = container.querySelector('.matrix-table-scroll') || container;
        const clip = scroll.getBoundingClientRect();
        const clipTop = Math.max(0, clip.top);
        const clipLeft = Math.max(0, clip.left);
        const clipBottom = Math.min(window.innerHeight || bottom, clip.bottom);
        const clipRight = Math.min(window.innerWidth || right, clip.right);
        const t = Math.max(top, clipTop);
        const l = Math.max(left, clipLeft);
        const b = Math.min(bottom, clipBottom);
        const rgt = Math.min(right, clipRight);
        if (rgt - l < 2 || b - t < 2) return null;
        return { top: t, left: l, width: rgt - l, height: b - t };
    },

    /** Select every editable cell in a matrix container. */
    _selectWholeMatrix(container) {
        const rows = container.querySelectorAll('tr.matrix-data-row');
        if (!rows.length) return;
        let minC = Infinity;
        let maxC = -Infinity;
        rows.forEach((tr) => {
            tr.querySelectorAll('input[data-cell-key]').forEach((input) => {
                const c = input.closest('td')?.cellIndex;
                if (typeof c === 'number') {
                    if (c < minC) minC = c;
                    if (c > maxC) maxC = c;
                }
            });
        });
        if (!isFinite(minC)) return;
        this._matrixSelection = {
            container,
            anchor: { r: 0, c: minC },
            focus: { r: rows.length - 1, c: maxC },
            dragging: false,
        };
        this._renderMatrixSelection();
    },

    /** Read the display value of a cell input for copying. */
    _matrixCellCopyValue(input) {
        if (!input) return '';
        if (input.type === 'checkbox') return input.checked ? '1' : '0';
        return input.value != null ? String(input.value) : '';
    },

    /**
     * Copy (or cut) the selected range to the clipboard as TSV. No-op for a
     * single-cell selection so normal in-input copy still works.
     */
    _handleMatrixCopy(e, isCut = false) {
        const sel = this._matrixSelection;
        if (!sel || !this._matrixSelectionIsRange(sel)) return;

        // Only hijack copy when the focus is inside this matrix, so a
        // single-cell selection still copies in-input text.
        if (!this._matrixSelectableInput(document.activeElement)) return;

        const tsv = this._matrixSelectionTsv(sel);
        if (tsv == null) return;

        if (e.clipboardData) {
            e.preventDefault();
            e.clipboardData.setData('text/plain', tsv);
        } else if (navigator.clipboard && navigator.clipboard.writeText) {
            e.preventDefault();
            navigator.clipboard.writeText(tsv).catch(() => {});
        }

        if (isCut) this._clearMatrixSelectedValues();
        this._noteMatrixClipboard(tsv);
        const { minR, maxR, minC, maxC } = this._matrixSelectionBounds(sel);
        debugLog('matrix-handler', '[SELECTION] Copied range', { rows: maxR - minR + 1, cols: maxC - minC + 1 });
    },

    /** TSV (tab columns, newline rows) for the selected range, or null for one cell. */
    _matrixSelectionTsv(sel = this._matrixSelection) {
        if (!sel || !this._matrixSelectionIsRange(sel)) return null;
        const { container } = sel;
        const { minR, maxR, minC, maxC } = this._matrixSelectionBounds(sel);
        const lines = [];
        for (let r = minR; r <= maxR; r++) {
            const cols = [];
            for (let c = minC; c <= maxC; c++) {
                cols.push(this._matrixCellCopyValue(this._matrixCellInputAt(container, r, c)));
            }
            lines.push(cols.join('\t'));
        }
        return lines.join('\n');
    },

    /** Copy the selected range from the menu (keeps the range selected). */
    _copyMatrixSelectionViaMenu() {
        const tsv = this._matrixSelectionTsv();
        if (tsv == null) return;
        __writeClipboardText(tsv).then(() => {
            this._noteMatrixClipboard(tsv);
            debugLog('matrix-handler', '[SELECTION] Copied range from menu');
        }).catch((err) => {
            debugWarn('matrix-handler', '[SELECTION] Clipboard write failed', err);
        });
    },

    /** Paste the clipboard into the selected range from the menu. */
    _pasteMatrixSelectionViaMenu() {
        const sel = this._matrixSelection;
        if (!sel || !this._matrixSelectionIsRange(sel)) return;
        if (typeof this._canEditMatrix === 'function' && !this._canEditMatrix(sel.container)) return;

        const applyText = (text) => {
            const current = this._matrixSelection;
            if (!current || current.container !== sel.container) return;
            const grid = this._parseClipboardGrid(text || '');
            const plan = this._matrixPastePlan(current.container, current, grid);
            this._noteMatrixClipboard(text);
            if (!plan.ok) return;
            this._pasteMatrixGrid(current.container, plan.origin, grid);
        };

        const read = navigator.clipboard && navigator.clipboard.readText;
        if (typeof read === 'function') {
            Promise.resolve().then(() => read.call(navigator.clipboard)).then((text) => {
                applyText(text);
            }).catch((err) => {
                debugWarn('matrix-handler', '[SELECTION] Clipboard read failed', err);
                const cached = this._matrixClipboardCache;
                if (cached && cached.text) applyText(cached.text);
            });
            return;
        }
        if (this._matrixClipboardCache && this._matrixClipboardCache.text) {
            applyText(this._matrixClipboardCache.text);
        }
    },

    /** Clear the values of every cell in the current selection (for cut). */
    _clearMatrixSelectedValues() {
        const sel = this._matrixSelection;
        if (!sel) return;
        const { container } = sel;
        if (!this._canEditMatrix(container)) return;
        const fieldId = container.dataset.fieldId;

        const minR = Math.min(sel.anchor.r, sel.focus.r);
        const maxR = Math.max(sel.anchor.r, sel.focus.r);
        const minC = Math.min(sel.anchor.c, sel.focus.c);
        const maxC = Math.max(sel.anchor.c, sel.focus.c);

        for (let r = minR; r <= maxR; r++) {
            for (let c = minC; c <= maxC; c++) {
                this._writeMatrixCell(fieldId, this._matrixCellInputAt(container, r, c), '');
            }
        }
        this._finalizeMatrixBulkWrite(fieldId);
    },

    /**
     * Paste a TSV block from the clipboard into the grid. A 1×1 clipboard
     * pasted over a multi-cell selection fills the whole selection.
     */
    _handleMatrixPaste(e) {
        const input = this._matrixSelectableInput(document.activeElement)
            || this._matrixSelectableInput(e.target);
        if (!input) return;

        const container = input.closest('.matrix-container');
        if (!container || !this._canEditMatrix(container)) return;

        const clip = e.clipboardData || window.clipboardData;
        const text = clip ? clip.getData('text/plain') || clip.getData('Text') : '';
        if (text == null) return;
        const outcome = this._pasteMatrixText(container, input, text);
        if (outcome === 'applied' || outcome === 'rejected') {
            e.preventDefault();
            this._noteMatrixClipboard(text);
        }
    },

    /**
     * Paste clipboard text into the matrix.
     * 'applied' was written, 'rejected' was blocked because the shape does
     * not match, 'passthrough' lets the browser insert one value into the
     * focused cell, and 'ignore' means there was nothing to paste.
     */
    _pasteMatrixText(container, input, text) {
        const grid = this._parseClipboardGrid(text);
        if (!grid.length) return 'ignore';

        const sel = this._matrixSelection;
        const plan = this._matrixPastePlan(container, sel, grid, input);
        if (plan.ok) {
            this._pasteMatrixGrid(container, plan.origin, grid);
            return 'applied';
        }
        if (plan.reason === 'single') return 'passthrough';
        const hasRange = !!(sel && sel.container === container && this._matrixSelectionIsRange(sel));
        return hasRange || plan.reason === 'shape' ? 'rejected' : 'ignore';
    },

    /**
     * Decide whether a clipboard grid may be pasted.
     * A multi-cell selection accepts a grid that fits in the editable cells
     * starting at the selection's first cell (so a 1×4 copy can land on a
     * 1×2 selection when two further cells are free). An exact match with
     * the selection is also accepted. With no range selected, a single
     * value is left to the browser and a larger grid must fit around the
     * focused cell.
     */
    _matrixPastePlan(container, sel, grid, input) {
        const shape = this._matrixGridShape(grid);
        if (!shape) return { ok: false, reason: 'empty' };
        if (typeof this._canEditMatrix === 'function' && container && !this._canEditMatrix(container)) {
            return { ok: false, reason: 'readonly', shape };
        }

        const hasRange = !!(sel && sel.container === container && this._matrixSelectionIsRange(sel));
        if (hasRange) {
            const bounds = this._matrixSelectionBounds(sel);
            const selShape = {
                rows: bounds.maxR - bounds.minR + 1,
                cols: bounds.maxC - bounds.minC + 1,
            };
            const start = { r: bounds.minR, c: bounds.minC };
            // Room to paste, measured from the first selected cell rather than
            // whichever corner the pointer finished on.
            const available = this._matrixAvailableRange(container, start.r, start.c);
            if (this._matrixShapeFits(shape, available) || this._matrixShapeEquals(shape, selShape)) {
                return { ok: true, origin: start, shape, selShape, available };
            }
            return { ok: false, reason: 'shape', shape, selShape, available };
        }

        if (shape.rows === 1 && shape.cols === 1) return { ok: false, reason: 'single', shape };
        const coord = input ? this._matrixCellCoord(input) : null;
        const available = coord ? this._matrixAvailableRange(container, coord.r, coord.c) : null;
        if (available && shape.rows <= available.rows && shape.cols <= available.cols) {
            return { ok: true, origin: { r: coord.r, c: coord.c }, shape, available };
        }
        return { ok: false, reason: 'shape', shape, available };
    },

    /** Row × column size of a parsed clipboard grid, or null when it is empty. */
    _matrixGridShape(grid) {
        if (!Array.isArray(grid) || !grid.length) return null;
        const cols = grid.reduce((max, row) => Math.max(max, Array.isArray(row) ? row.length : 0), 0);
        if (!cols) return null;
        return { rows: grid.length, cols };
    },

    _matrixShapeEquals(a, b) {
        return !!a && !!b && a.rows === b.rows && a.cols === b.cols && a.rows > 0 && a.cols > 0;
    },

    /** True when `shape` can be written inside `available` without running off the grid. */
    _matrixShapeFits(shape, available) {
        return !!shape && !!available
            && shape.rows > 0 && shape.cols > 0
            && shape.rows <= available.rows
            && shape.cols <= available.cols;
    },

    /**
     * Contiguous editable cells starting at (r0, c0), moving right then down.
     * A disabled cell or a cell with no input ends the block.
     */
    _matrixAvailableRange(container, r0, c0) {
        const rows = container ? container.querySelectorAll('tr.matrix-data-row') : [];
        if (!rows.length || r0 < 0 || r0 >= rows.length || c0 < 0) return null;
        let colsAvail = Infinity;
        let rowsAvail = 0;
        for (let r = r0; r < rows.length; r++) {
            const tr = rows[r];
            const cellCount = tr && tr.cells ? tr.cells.length : 0;
            let cols = 0;
            for (let c = c0; c < cellCount; c++) {
                const input = tr.cells[c].querySelector('input[data-cell-key]');
                if (!input || input.disabled) break;
                cols++;
            }
            if (!cols) break;
            colsAvail = Math.min(colsAvail, cols);
            rowsAvail++;
        }
        if (!rowsAvail || !Number.isFinite(colsAvail)) return null;
        return { rows: rowsAvail, cols: colsAvail };
    },

    _matrixPasteValidationKey(sel) {
        if (!sel) return '';
        const { minR, maxR, minC, maxC } = this._matrixSelectionBounds(sel);
        const fieldId = sel.container && sel.container.dataset ? sel.container.dataset.fieldId : '';
        return `${fieldId}:${minR}:${maxR}:${minC}:${maxC}:${sel.focus.r}:${sel.focus.c}`;
    },

    /** Recompute Paste from the cached clipboard, and read the clipboard when the selection changes. */
    _touchMatrixPasteValidation(sel) {
        this._applyMatrixPasteButton();
        const key = this._matrixPasteValidationKey(sel);
        if (key === this._matrixPasteValidationKeySeen) return;
        this._matrixPasteValidationKeySeen = key;
        this._scheduleMatrixClipboardRead();
    },

    _scheduleMatrixClipboardRead() {
        const epoch = this._matrixClipboardEpoch || 0;
        if (this._matrixClipboardReadInFlight === epoch) return;
        const read = navigator.clipboard && navigator.clipboard.readText;
        if (typeof read !== 'function') {
            if (!this._matrixClipboardCache) this._matrixClipboardCache = { unreadable: true };
            this._applyMatrixPasteButton();
            return;
        }
        this._matrixClipboardReadInFlight = epoch;
        if (!this._matrixClipboardCache) {
            this._matrixClipboardPending = true;
            this._applyMatrixPasteButton();
        }
        // readText() can wait on a permission prompt and never settle. Stop
        // showing "Checking…" so Paste stays usable; a late result still applies.
        const timer = setTimeout(() => {
            if ((this._matrixClipboardEpoch || 0) !== epoch || !this._matrixClipboardPending) return;
            this._matrixClipboardPending = false;
            if (!this._matrixClipboardCache) this._matrixClipboardCache = { unreadable: true };
            this._applyMatrixPasteButton();
        }, CLIPBOARD_READ_TIMEOUT_MS);
        Promise.resolve().then(() => read.call(navigator.clipboard)).then((text) => {
            clearTimeout(timer);
            if ((this._matrixClipboardEpoch || 0) !== epoch) return;
            this._matrixClipboardPending = false;
            this._noteMatrixClipboard(text, { bump: false });
        }).catch((err) => {
            clearTimeout(timer);
            if ((this._matrixClipboardEpoch || 0) !== epoch) return;
            debugWarn('matrix-handler', '[SELECTION] Clipboard read failed', err);
            this._matrixClipboardPending = false;
            if (!this._matrixClipboardCache || this._matrixClipboardCache.unreadable) {
                this._matrixClipboardCache = { unreadable: true };
            }
            this._applyMatrixPasteButton();
        }).finally(() => {
            if (this._matrixClipboardReadInFlight === epoch) this._matrixClipboardReadInFlight = null;
        });
    },

    /** Remember clipboard text and refresh Copy / Paste. */
    _noteMatrixClipboard(text, { bump = true } = {}) {
        if (bump) this._matrixClipboardEpoch = (this._matrixClipboardEpoch || 0) + 1;
        const grid = this._parseClipboardGrid(text || '');
        const shape = this._matrixGridShape(grid);
        this._matrixClipboardCache = shape
            ? { text: String(text), rows: shape.rows, cols: shape.cols }
            : { text: String(text || ''), rows: 0, cols: 0 };
        this._matrixClipboardPending = false;
        this._applyMatrixPasteButton();
    },

    _matrixPasteMismatchTip(plan) {
        const shape = plan.shape || { rows: 0, cols: 0 };
        const selShape = plan.selShape;
        const available = plan.available;
        if (selShape && available) {
            return __fillTemplate(
                _t("Clipboard is {rows}×{cols}. Only {availRows}×{availCols} cells are free from here."),
                {
                    rows: shape.rows,
                    cols: shape.cols,
                    availRows: available.rows,
                    availCols: available.cols,
                },
            );
        }
        if (selShape) {
            return __fillTemplate(
                _t("Clipboard is {rows}×{cols}. It doesn't match the {selRows}×{selCols} selection."),
                { rows: shape.rows, cols: shape.cols, selRows: selShape.rows, selCols: selShape.cols },
            );
        }
        return _t('Copy a range that matches this selection.');
    },

    /** Enable Copy / Paste and set the tooltip that explains a disabled Paste. */
    _applyMatrixPasteButton() {
        const chrome = this._matrixSelectionChrome;
        if (!chrome) return;
        const pasteBtn = chrome.querySelector('[data-action="paste"]');
        const copyBtn = chrome.querySelector('[data-action="copy"]');
        if (!pasteBtn) return;
        const sel = this._matrixSelection;

        const setTip = (btn, message, disabled) => {
            const wrap = btn.closest('.matrix-selection-menu-item') || btn;
            if (message) {
                wrap.dataset.tooltip = message;
                wrap.title = message;
            } else {
                delete wrap.dataset.tooltip;
                wrap.removeAttribute('title');
            }
            btn.disabled = !!disabled;
        };

        if (copyBtn) {
            const canCopy = !!(sel && this._matrixSelectionTsv(sel) != null);
            setTip(copyBtn, canCopy ? '' : _t('Nothing to copy in this selection.'), !canCopy);
        }

        if (!sel || !this._matrixSelectionIsRange(sel)) {
            setTip(pasteBtn, '', true);
            return;
        }
        const canEdit = typeof this._canEditMatrix !== 'function' || this._canEditMatrix(sel.container);
        if (!canEdit) {
            setTip(pasteBtn, _t("This matrix can't be edited."), true);
            return;
        }
        if (this._matrixClipboardPending && !this._matrixClipboardCache) {
            // Stay clickable: the click reads the clipboard again and refuses a mismatch.
            setTip(pasteBtn, _t('Checking the clipboard…'), false);
            return;
        }
        const cache = this._matrixClipboardCache;
        if (!cache || cache.unreadable) {
            setTip(pasteBtn, _t('The clipboard could not be read. Copy a range here first.'), false);
            return;
        }
        if (!cache.rows || !cache.cols) {
            setTip(pasteBtn, _t('Copy a range that matches this selection.'), true);
            return;
        }
        const plan = this._matrixPastePlan(sel.container, sel, this._parseClipboardGrid(cache.text));
        if (plan.ok) {
            setTip(pasteBtn, '', false);
            return;
        }
        setTip(pasteBtn, this._matrixPasteMismatchTip(plan), true);
    },

    /** Parse clipboard text into a 2-D array of strings. */
    _parseClipboardGrid(text) {
        let t = String(text).replace(/\r\n/g, '\n').replace(/\r/g, '\n');
        // Drop a single trailing newline that spreadsheets usually append.
        if (t.endsWith('\n')) t = t.slice(0, -1);
        if (t === '') return [];
        return t.split('\n').map((line) => line.split('\t'));
    },

    /** Write a parsed grid into the matrix starting at a top-left coordinate. */
    _pasteMatrixGrid(container, start, grid) {
        const fieldId = container.dataset.fieldId;
        let wrote = 0;
        for (let i = 0; i < grid.length; i++) {
            for (let j = 0; j < grid[i].length; j++) {
                const input = this._matrixCellInputAt(container, start.r + i, start.c + j);
                if (this._writeMatrixCell(fieldId, input, grid[i][j])) wrote++;
            }
        }
        this._finalizeMatrixBulkWrite(fieldId);

        // Re-select the pasted block so the user sees what landed.
        const endR = start.r + grid.length - 1;
        const endC = start.c + Math.max(...grid.map((row) => row.length)) - 1;
        this._matrixSelection = {
            container,
            anchor: { r: start.r, c: start.c },
            focus: { r: endR, c: endC },
            dragging: false,
        };
        this._renderMatrixSelection();
        debugLog('matrix-handler', '[SELECTION] Pasted grid', { rows: grid.length, cellsWritten: wrote });
    },

    /**
     * Write a single raw value into a cell input and sync matrix.data.
     * Returns true when the cell accepted the value. Totals are recalculated
     * once afterwards via _finalizeMatrixBulkWrite().
     */
    _writeMatrixCell(fieldId, input, rawValue) {
        if (!input || input.disabled) return false;

        const value = rawValue == null ? '' : String(rawValue).trim();

        if (input.type === 'checkbox') {
            const truthy = /^(1|true|yes|y|x|✓|checked)$/i.test(value);
            input.checked = truthy;
        } else {
            input.value = value;
        }

        input.dataset.userEdited = '1';
        this.clearInputError?.(input);

        try {
            this.updateMatrixData(fieldId, input);
        } catch (err) {
            debugWarn('matrix-handler', '[SELECTION] updateMatrixData failed during paste', err);
        }

        if (input.type !== 'checkbox') {
            __setMatrixNumericCellDisplay(input);
            __syncWholeNumberViolationHighlight(input);
        }
        return true;
    },

    /** Recompute totals / highlighting once after a bulk write. */
    _finalizeMatrixBulkWrite(fieldId) {
        if (!fieldId || !this.matrices.has(fieldId)) return;
        try {
            this.calculateMatrixTotals(fieldId);
            this.applyPrefilledCellHighlighting?.(fieldId);
            this.applyWholeNumberViolationHighlighting?.(fieldId);
        } catch (err) {
            debugWarn('matrix-handler', '[SELECTION] finalize bulk write failed', err);
        }
    },
};
