import { describe, it, expect, beforeEach } from 'vitest';
import {
    assignFilesToInput,
    formatSelectedFilenames,
    initExcelImportDropzone,
} from '../../../app/static/js/components/excel-import-dropzone.js';

function makeFile(name, type = 'application/pdf') {
    return new File(['x'], name, { type });
}

class FakeDataTransfer {
    constructor() {
        this.items = {
            _files: [],
            add(file) { this._files.push(file); },
        };
    }
    get files() {
        const files = this.items._files.slice();
        files.item = (i) => files[i] || null;
        return files;
    }
}

if (typeof globalThis.DataTransfer === 'undefined') {
    globalThis.DataTransfer = FakeDataTransfer;
}

function stubAssignableFiles(input) {
    let assigned = [];
    Object.defineProperty(input, 'files', {
        configurable: true,
        get() { return assigned; },
        set(value) { assigned = value; },
    });
    return () => Array.from(assigned || []).map((file) => file.name);
}

describe('excel-import-dropzone multiple files', () => {
    beforeEach(() => {
        document.body.innerHTML = `
            <div id="dz" class="excel-io-dropzone" data-multiple="true">
                <input type="file" id="f" class="excel-io-file-input" multiple accept=".pdf,.md">
                <div class="excel-io-dropzone__content excel-io-dropzone__content--empty"></div>
                <div class="excel-io-dropzone__content excel-io-dropzone__content--selected" hidden>
                    <p class="excel-io-dropzone__filename"></p>
                </div>
            </div>
        `;
    });

    it('formats one or many selected filenames', () => {
        expect(formatSelectedFilenames([])).toBe('');
        expect(formatSelectedFilenames([makeFile('a.pdf')])).toBe('a.pdf');
        expect(formatSelectedFilenames([makeFile('a.pdf'), makeFile('b.md')])).toBe('a.pdf, b.md');
    });

    it('keeps every file when the input allows multiple', () => {
        const input = document.getElementById('f');
        const names = stubAssignableFiles(input);
        assignFilesToInput(input, [makeFile('a.pdf'), makeFile('b.md')]);
        expect(names()).toEqual(['a.pdf', 'b.md']);
    });

    it('keeps only the first file when multiple is off', () => {
        const input = document.getElementById('f');
        input.multiple = false;
        const names = stubAssignableFiles(input);
        assignFilesToInput(input, [makeFile('a.pdf'), makeFile('b.md')]);
        expect(names()).toEqual(['a.pdf']);
    });

    it('assigns every accepted dropped file on a multiple dropzone', () => {
        const input = document.getElementById('f');
        const names = stubAssignableFiles(input);
        initExcelImportDropzone('#dz', {
            multiple: true,
            acceptExtensions: ['.pdf', '.md'],
            requireValidation: false,
        });
        const dt = new DataTransfer();
        dt.items.add(makeFile('guide.pdf'));
        dt.items.add(makeFile('notes.md'));
        dt.items.add(makeFile('skip.exe', 'application/octet-stream'));
        const event = new Event('drop', { bubbles: true, cancelable: true });
        Object.defineProperty(event, 'dataTransfer', { value: dt });
        input.closest('.excel-io-dropzone').dispatchEvent(event);
        expect(names()).toEqual(['guide.pdf', 'notes.md']);
        expect(document.querySelector('.excel-io-dropzone__filename').textContent).toBe('guide.pdf, notes.md');
    });
});
