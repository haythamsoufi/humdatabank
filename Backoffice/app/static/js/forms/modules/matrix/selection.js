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
 *     grid, starting at the top-left of the current selection. A single
 *     copied value pasted over a multi-cell selection fills the whole
 *     selection (Excel behaviour).
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

const SELECTED_CLASS = 'matrix-cell-selected';
const ACTIVE_CLASS = 'matrix-cell-active';
const SELECTING_CLASS = 'matrix-selecting';
const STYLE_ID = 'matrix-selection-styles';

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
`;
    (document.head || document.documentElement).appendChild(style);
}

export const matrixSelectionMixin = {
    /**
     * Wire up range-selection + clipboard listeners. Called once from
     * setupEventListeners(). All listeners are delegated at the document
     * level so dynamically added matrices (repeat sections) are covered.
     */
    setupMatrixSelection() {
        __ensureSelectionStyles();

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
            }
        });

        // Clicking anywhere outside a matrix cell clears the range.
        document.addEventListener('mousedown', (e) => {
            if (!this._matrixSelection) return;
            if (!this._matrixSelectableInput(e.target)) {
                this._clearMatrixSelection();
            }
        }, true);

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
    },

    /** Drop the current selection + highlight. */
    _clearMatrixSelection() {
        this._matrixSelection = null;
        document.querySelectorAll(`.${SELECTED_CLASS}, .${ACTIVE_CLASS}`).forEach((el) => {
            el.classList.remove(SELECTED_CLASS, ACTIVE_CLASS);
        });
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
        if (!sel) return;

        const { container, anchor, focus } = sel;
        const minR = Math.min(anchor.r, focus.r);
        const maxR = Math.max(anchor.r, focus.r);
        const minC = Math.min(anchor.c, focus.c);
        const maxC = Math.max(anchor.c, focus.c);

        const singleCell = minR === maxR && minC === maxC;
        if (singleCell) return; // let the browser copy in-input text

        // Only hijack copy when the focus is inside this matrix.
        if (!this._matrixSelectableInput(document.activeElement)) return;

        const lines = [];
        for (let r = minR; r <= maxR; r++) {
            const cols = [];
            for (let c = minC; c <= maxC; c++) {
                cols.push(this._matrixCellCopyValue(this._matrixCellInputAt(container, r, c)));
            }
            lines.push(cols.join('\t'));
        }
        const tsv = lines.join('\n');

        if (e.clipboardData) {
            e.preventDefault();
            e.clipboardData.setData('text/plain', tsv);
        } else if (navigator.clipboard && navigator.clipboard.writeText) {
            e.preventDefault();
            navigator.clipboard.writeText(tsv).catch(() => {});
        }

        if (isCut) this._clearMatrixSelectedValues();
        debugLog('matrix-handler', '[SELECTION] Copied range', { rows: maxR - minR + 1, cols: maxC - minC + 1 });
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

        const grid = this._parseClipboardGrid(text);
        if (!grid.length) return;

        const sel = this._matrixSelection;
        const start = (sel && sel.container === container)
            ? { r: Math.min(sel.anchor.r, sel.focus.r), c: Math.min(sel.anchor.c, sel.focus.c) }
            : this._matrixCellCoord(input);
        if (!start) return;

        const selHasRange = !!sel && sel.container === container
            && (sel.anchor.r !== sel.focus.r || sel.anchor.c !== sel.focus.c);
        const singleValue = grid.length === 1 && grid[0].length === 1;

        // A single value pasted over a selected range fills that range.
        if (singleValue && selHasRange) {
            e.preventDefault();
            this._fillMatrixRange(container, sel, grid[0][0]);
            return;
        }

        // Let a single value paste normally into a single focused cell.
        if (singleValue && !selHasRange) return;

        e.preventDefault();
        this._pasteMatrixGrid(container, start, grid);
    },

    /** Parse clipboard text into a 2-D array of strings. */
    _parseClipboardGrid(text) {
        let t = String(text).replace(/\r\n/g, '\n').replace(/\r/g, '\n');
        // Drop a single trailing newline that spreadsheets usually append.
        if (t.endsWith('\n')) t = t.slice(0, -1);
        if (t === '') return [];
        return t.split('\n').map((line) => line.split('\t'));
    },

    /** Fill every cell of a selection rectangle with one value. */
    _fillMatrixRange(container, sel, value) {
        const fieldId = container.dataset.fieldId;
        const minR = Math.min(sel.anchor.r, sel.focus.r);
        const maxR = Math.max(sel.anchor.r, sel.focus.r);
        const minC = Math.min(sel.anchor.c, sel.focus.c);
        const maxC = Math.max(sel.anchor.c, sel.focus.c);
        for (let r = minR; r <= maxR; r++) {
            for (let c = minC; c <= maxC; c++) {
                this._writeMatrixCell(fieldId, this._matrixCellInputAt(container, r, c), value);
            }
        }
        this._finalizeMatrixBulkWrite(fieldId);
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
