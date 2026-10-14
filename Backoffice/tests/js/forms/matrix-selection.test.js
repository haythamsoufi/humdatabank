/**
 * Multi-cell matrix selection draws an animated dotted outline and a
 * Copy / Paste menu. A single cell keeps the plain focus outline.
 */
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
    debugLog: vi.fn(),
    debugError: vi.fn(),
    debugWarn: vi.fn(),
}));

import { matrixSelectionMixin } from '../../../app/static/js/forms/modules/matrix/selection.js';

const TABLE_HTML = `
<div class="matrix-container" data-field-id="42" data-can-edit="true">
  <div class="matrix-table-scroll">
    <table>
      <tbody>
        <tr class="matrix-data-row">
          <td role="rowheader">A</td>
          <td><input data-cell-key="a-1" value="1"></td>
          <td><input data-cell-key="a-2" value="2"></td>
        </tr>
        <tr class="matrix-data-row">
          <td role="rowheader">B</td>
          <td><input data-cell-key="b-1" value="3"></td>
          <td><input data-cell-key="b-2" value="4"></td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
`;

function box(top, left, width, height) {
    return {
        top,
        left,
        width,
        height,
        bottom: top + height,
        right: left + width,
        x: left,
        y: top,
        toJSON() { return {}; },
    };
}

function layoutTable() {
    const scroll = document.querySelector('.matrix-table-scroll');
    scroll.getBoundingClientRect = () => box(0, 0, 900, 500);
    const coords = [
        [[40, 20, 100, 32], [40, 120, 80, 32], [40, 200, 80, 32]],
        [[72, 20, 100, 32], [72, 120, 80, 32], [72, 200, 80, 32]],
    ];
    document.querySelectorAll('tr.matrix-data-row').forEach((tr, r) => {
        Array.from(tr.cells).forEach((td, c) => {
            const [top, left, width, height] = coords[r][c];
            td.getBoundingClientRect = () => box(top, left, width, height);
        });
    });
}

function pointer(type, target) {
    target.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, button: 0 }));
}

function inputs() {
    return Array.from(document.querySelectorAll('input[data-cell-key]'));
}

function dragRange() {
    const cells = inputs();
    pointer('mousedown', cells[0]);
    pointer('mouseover', cells[3]);
    pointer('mouseup', document);
}

/** Let the clipboard read that follows a selection settle. */
async function flushClipboard() {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
}

function pasteButton() {
    return document.querySelector('.matrix-selection-menu [data-action="paste"]');
}

function pasteTip() {
    const btn = pasteButton();
    const wrap = btn && btn.closest('.matrix-selection-menu-item');
    return (wrap && (wrap.dataset.tooltip || wrap.title)) || '';
}

let host;

beforeAll(() => {
    host = Object.assign({
        matrices: new Map(),
        canEdit: true,
        updateMatrixData: vi.fn(),
        calculateMatrixTotals: vi.fn(),
        clearInputError: vi.fn(),
        _canEditMatrix() { return this.canEdit; },
    }, matrixSelectionMixin);
    host.setupMatrixSelection();
});

beforeEach(() => {
    host.canEdit = true;
    host.updateMatrixData.mockClear();
    document.body.innerHTML = TABLE_HTML;
    layoutTable();
    host._clearMatrixSelection();
});

describe('matrix range selection chrome', () => {
    it('shows an animated dotted outline and a Copy / Paste menu for a range', () => {
        const cells = inputs();
        pointer('mousedown', cells[0]);
        pointer('mouseover', cells[3]);

        const chrome = document.getElementById('matrix-selection-chrome');
        const menu = chrome.querySelector('.matrix-selection-menu');
        const ants = chrome.querySelector('.matrix-selection-ants');
        expect(chrome.hidden).toBe(false);
        expect(ants.querySelector('.matrix-selection-ants-dots')).toBeTruthy();
        expect(ants.style.width).toBe('160px');
        expect(ants.style.height).toBe('64px');
        expect(document.getElementById('matrix-selection-styles').textContent)
            .toContain('@keyframes matrix-selection-ants');
        expect(menu.hidden).toBe(false);
        expect(menu.style.pointerEvents).toBe('none');
        expect(Array.from(menu.querySelectorAll('button')).map((btn) => btn.textContent))
            .toEqual(['Copy', 'Paste']);

        pointer('mouseup', document);
        expect(menu.style.pointerEvents).toBe('auto');
        expect(menu.dataset.placement).toBe('below');
    });

    it('hides the outline and menu for a single cell', () => {
        const cells = inputs();
        pointer('mousedown', cells[0]);
        pointer('mouseup', document);
        expect(document.getElementById('matrix-selection-chrome').hidden).toBe(true);
        expect(cells[0].closest('td').classList.contains('matrix-cell-selected')).toBe(true);
    });

    it('copies the range from the menu without dropping the selection', async () => {
        const writeText = vi.fn().mockResolvedValue(undefined);
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: { writeText, readText: vi.fn().mockResolvedValue('') },
        });
        dragRange();
        await flushClipboard();
        const copyBtn = document.querySelector('.matrix-selection-menu [data-action="copy"]');
        pointer('mousedown', copyBtn);
        expect(host._matrixSelection).not.toBeNull();
        expect(writeText).toHaveBeenCalledWith('1\t2\n3\t4');
        await flushClipboard();
        // The copied block is the same size as the selection, so Paste turns on.
        expect(pasteButton().disabled).toBe(false);
        expect(pasteTip()).toBe('');
    });

    it('pastes a clipboard grid that matches the selection', async () => {
        const readText = vi.fn().mockResolvedValue('9\t8\n7\t6');
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: { writeText: vi.fn(), readText },
        });
        dragRange();
        await flushClipboard();
        expect(pasteButton().disabled).toBe(false);
        pointer('mousedown', pasteButton());
        await flushClipboard();
        expect(inputs().map((input) => input.value)).toEqual(['9', '8', '7', '6']);
    });

    it('disables Paste when the clipboard does not fit in the free cells', async () => {
        const readText = vi.fn().mockResolvedValue('1\t2\t3');
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: { writeText: vi.fn(), readText },
        });
        dragRange();
        await flushClipboard();
        expect(pasteButton().disabled).toBe(true);
        expect(pasteTip()).toContain('1×3');
        expect(pasteTip()).toContain('2×2');
        pointer('mousedown', pasteButton());
        await flushClipboard();
        expect(inputs().map((input) => input.value)).toEqual(['1', '2', '3', '4']);
    });

    it('pastes a wider clipboard into the free cells beside the selection', async () => {
        const readText = vi.fn().mockResolvedValue('9\t8\t7\t6');
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: { writeText: vi.fn(), readText },
        });
        document.body.innerHTML = `
            <div class="matrix-container" data-field-id="42" data-can-edit="true">
              <div class="matrix-table-scroll">
                <table>
                  <tbody>
                    <tr class="matrix-data-row">
                      <td role="rowheader">Sudan</td>
                      <td><input data-cell-key="a" value="0"></td>
                      <td><input data-cell-key="b" value="0"></td>
                      <td><input data-cell-key="c" value="0"></td>
                      <td><input data-cell-key="d" value="0"></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>`;
        const scroll = document.querySelector('.matrix-table-scroll');
        scroll.getBoundingClientRect = () => box(0, 0, 900, 200);
        document.querySelectorAll('td').forEach((td, index) => {
            const left = 20 + index * 80;
            td.getBoundingClientRect = () => box(40, left, 80, 32);
        });
        host._clearMatrixSelection();
        const cells = inputs();
        pointer('mousedown', cells[0]);
        pointer('mouseover', cells[1]);
        pointer('mouseup', document);
        await flushClipboard();
        expect(pasteButton().disabled).toBe(false);
        pointer('mousedown', pasteButton());
        await flushClipboard();
        expect(inputs().map((input) => input.value)).toEqual(['9', '8', '7', '6']);
    });

    it('pastes when the clipboard matches the cells available from the selection', async () => {
        const readText = vi.fn().mockResolvedValue('9\t8\n7\t6');
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: { writeText: vi.fn(), readText },
        });
        const cells = inputs();
        pointer('mousedown', cells[0]);
        pointer('mouseover', cells[1]);
        pointer('mouseup', document);
        await flushClipboard();
        expect(pasteButton().disabled).toBe(false);
        pointer('mousedown', pasteButton());
        await flushClipboard();
        expect(inputs().map((input) => input.value)).toEqual(['9', '8', '7', '6']);
    });

    it('disables Paste when the matrix cannot be edited', () => {
        host.canEdit = false;
        dragRange();
        const btn = pasteButton();
        expect(btn.disabled).toBe(true);
        expect(pasteTip()).toContain("can't be edited");
        expect(document.querySelector('.matrix-selection-menu [data-action="copy"]').disabled).toBe(false);
    });

    it('clears the range when the pointer goes down outside the menu', () => {
        dragRange();
        pointer('mousedown', document.body);
        expect(host._matrixSelection).toBeNull();
        expect(document.getElementById('matrix-selection-chrome').hidden).toBe(true);
    });
});
