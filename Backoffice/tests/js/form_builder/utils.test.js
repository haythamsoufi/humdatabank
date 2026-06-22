/**
 * Tests for app/static/js/form_builder/modules/utils.js
 *
 * utils.js assigns to window.Utils (no ES module export) so we import it
 * for its side-effect, then access Utils through the global.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import '../../../app/static/js/form_builder/modules/utils.js';

const Utils = window.Utils;

// ---------------------------------------------------------------------------
// deepClone
// ---------------------------------------------------------------------------

describe('Utils.deepClone', () => {
    it('clones a flat object', () => {
        const obj = { a: 1, b: 'hello', c: true };
        const clone = Utils.deepClone(obj);
        expect(clone).toEqual(obj);
        expect(clone).not.toBe(obj);
    });

    it('clones an array', () => {
        const arr = [1, 2, 3];
        const clone = Utils.deepClone(arr);
        expect(clone).toEqual(arr);
        expect(clone).not.toBe(arr);
    });

    it('deep-clones nested structures without shared references', () => {
        const obj = { a: { b: { c: 42 } }, arr: [1, [2, 3]] };
        const clone = Utils.deepClone(obj);
        clone.a.b.c = 99;
        clone.arr[1][0] = 99;
        expect(obj.a.b.c).toBe(42);
        expect(obj.arr[1][0]).toBe(2);
    });
});

// ---------------------------------------------------------------------------
// generateUniqueId
// ---------------------------------------------------------------------------

describe('Utils.generateUniqueId', () => {
    it('returns a string', () => {
        expect(typeof Utils.generateUniqueId()).toBe('string');
    });

    it('starts with "id-"', () => {
        expect(Utils.generateUniqueId()).toMatch(/^id-/);
    });

    it('generates 100 distinct IDs', () => {
        const ids = new Set(Array.from({ length: 100 }, () => Utils.generateUniqueId()));
        expect(ids.size).toBe(100);
    });
});

// ---------------------------------------------------------------------------
// showElement / hideElement
// ---------------------------------------------------------------------------

describe('Utils.hideElement', () => {
    it('adds hidden class and sets display:none', () => {
        const el = document.createElement('div');
        Utils.hideElement(el);
        expect(el.classList.contains('hidden')).toBe(true);
        expect(el.style.display).toBe('none');
    });

    it('disables enabled text inputs', () => {
        const el = document.createElement('div');
        const input = document.createElement('input');
        input.type = 'text';
        el.appendChild(input);
        Utils.hideElement(el);
        expect(input.disabled).toBe(true);
        expect(input.dataset.utilsDisabledByHide).toBe('1');
    });

    it('does not disable hidden inputs', () => {
        const el = document.createElement('div');
        const hidden = document.createElement('input');
        hidden.type = 'hidden';
        el.appendChild(hidden);
        Utils.hideElement(el);
        expect(hidden.disabled).toBe(false);
    });

    it('does not mark already-disabled controls', () => {
        const el = document.createElement('div');
        const input = document.createElement('input');
        input.type = 'text';
        input.disabled = true;
        el.appendChild(input);
        Utils.hideElement(el);
        expect(input.dataset.utilsDisabledByHide).toBeUndefined();
    });

    it('handles null gracefully', () => {
        expect(() => Utils.hideElement(null)).not.toThrow();
    });
});

describe('Utils.showElement', () => {
    it('removes hidden class and clears display style', () => {
        const el = document.createElement('div');
        el.classList.add('hidden');
        el.style.display = 'none';
        Utils.showElement(el);
        expect(el.classList.contains('hidden')).toBe(false);
        expect(el.style.display).toBe('');
    });

    it('re-enables controls that were disabled by hideElement', () => {
        const el = document.createElement('div');
        const input = document.createElement('input');
        input.type = 'text';
        el.appendChild(input);
        Utils.hideElement(el);
        expect(input.disabled).toBe(true);
        Utils.showElement(el);
        expect(input.disabled).toBe(false);
    });

    it('does not re-enable controls that were already disabled before hide', () => {
        const el = document.createElement('div');
        const input = document.createElement('input');
        input.type = 'text';
        input.disabled = true;
        el.appendChild(input);
        Utils.hideElement(el);
        Utils.showElement(el);
        expect(input.disabled).toBe(true);
    });

    it('handles null gracefully', () => {
        expect(() => Utils.showElement(null)).not.toThrow();
    });
});

// ---------------------------------------------------------------------------
// sanitizeHtml
// ---------------------------------------------------------------------------

describe('Utils.sanitizeHtml', () => {
    it('escapes < and >', () => {
        const result = Utils.sanitizeHtml('<b>bold</b>');
        expect(result).toContain('&lt;b&gt;');
        expect(result).not.toContain('<b>');
    });

    it('escapes &', () => {
        expect(Utils.sanitizeHtml('cats & dogs')).toContain('&amp;');
    });

    it('returns plain text unchanged', () => {
        expect(Utils.sanitizeHtml('Hello world 123')).toBe('Hello world 123');
    });

    it('neutralises a script injection', () => {
        const result = Utils.sanitizeHtml('<script>alert("xss")</script>');
        expect(result).not.toContain('<script>');
    });
});

// ---------------------------------------------------------------------------
// setSanitizedHtml
// ---------------------------------------------------------------------------

describe('Utils.setSanitizedHtml', () => {
    it('renders safe HTML into container', () => {
        const container = document.createElement('div');
        Utils.setSanitizedHtml(container, '<p>Hello <strong>world</strong></p>');
        expect(container.querySelector('p')).not.toBeNull();
        expect(container.querySelector('strong')).not.toBeNull();
        expect(container.textContent).toBe('Hello world');
    });

    it('strips <script> tags', () => {
        const container = document.createElement('div');
        Utils.setSanitizedHtml(container, '<p>Safe</p><script>evil()</script>');
        expect(container.querySelector('script')).toBeNull();
        expect(container.querySelector('p')).not.toBeNull();
    });

    it('strips <iframe> tags', () => {
        const container = document.createElement('div');
        Utils.setSanitizedHtml(container, '<p>text</p><iframe src="evil.com"></iframe>');
        expect(container.querySelector('iframe')).toBeNull();
    });

    it('strips on* event handler attributes', () => {
        const container = document.createElement('div');
        Utils.setSanitizedHtml(container, '<div onclick="evil()" onmouseover="bad()">text</div>');
        const div = container.querySelector('div');
        expect(div).not.toBeNull();
        expect(div.getAttribute('onclick')).toBeNull();
        expect(div.getAttribute('onmouseover')).toBeNull();
    });

    it('strips javascript: href', () => {
        const container = document.createElement('div');
        Utils.setSanitizedHtml(container, '<a href="javascript:evil()">click</a>');
        const link = container.querySelector('a');
        expect(link).not.toBeNull();
        expect(link.getAttribute('href')).toBeNull();
    });

    it('strips data: src', () => {
        const container = document.createElement('div');
        Utils.setSanitizedHtml(container, '<img src="data:text/html,<script>evil()</script>">');
        const img = container.querySelector('img');
        expect(img?.getAttribute('src')).toBeNull();
    });

    it('handles null container without throwing', () => {
        expect(() => Utils.setSanitizedHtml(null, '<p>text</p>')).not.toThrow();
    });

    it('clears existing content when given empty html', () => {
        const container = document.createElement('div');
        container.textContent = 'existing content';
        Utils.setSanitizedHtml(container, '');
        expect(container.textContent).toBe('');
    });
});
