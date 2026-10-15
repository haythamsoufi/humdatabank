/**
 * Section-nav clicks must land on the start of a section.
 * The previous "scroll the nearest edge into view" path aligned a tall
 * section's bottom with the viewport, which left the heading in the middle.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { scrollElementToStart } from '../../../app/static/js/core/scroll-container.js';

function rect(top, bottom) {
    return () => ({
        top,
        bottom,
        left: 0,
        right: 100,
        width: 100,
        height: bottom - top,
        x: 0,
        y: top,
        toJSON() { return this; },
    });
}

describe('scrollElementToStart', () => {
    let scrollCalls;

    beforeEach(() => {
        scrollCalls = [];
        document.body.innerHTML = '';
    });

    afterEach(() => {
        document.body.innerHTML = '';
    });

    it('aligns a tall section below the fold to its top, not its bottom', () => {
        const main = document.createElement('main');
        main.className = 'admin-scroll-main';
        main.style.overflowY = 'auto';
        Object.defineProperty(main, 'scrollHeight', { value: 5000, configurable: true });
        Object.defineProperty(main, 'clientHeight', { value: 800, configurable: true });
        main.scrollTop = 0;
        main.scrollTo = (opts) => { scrollCalls.push(opts); };

        const section = document.createElement('div');
        section.id = 'section-container-9';
        section.style.scrollMarginTop = '80px';
        section.getBoundingClientRect = rect(1400, 3200);
        section.getClientRects = () => [{ top: 1400, bottom: 3200 }];
        main.getBoundingClientRect = rect(56, 856);
        main.appendChild(section);
        document.body.appendChild(main);

        const didScroll = scrollElementToStart(section, { behavior: 'auto' });

        expect(didScroll).toBe(true);
        // top of section relative to main (1400 - 56) minus the 8px inset
        expect(scrollCalls).toEqual([{ top: 1336, behavior: 'auto' }]);
    });

    it('does not scroll when the section start is already at the top', () => {
        const main = document.createElement('main');
        main.className = 'admin-scroll-main';
        main.style.overflowY = 'auto';
        Object.defineProperty(main, 'scrollHeight', { value: 5000, configurable: true });
        Object.defineProperty(main, 'clientHeight', { value: 800, configurable: true });
        main.scrollTop = 200;
        main.scrollTo = (opts) => { scrollCalls.push(opts); };

        const section = document.createElement('div');
        section.style.scrollMarginTop = '80px';
        // container top 56 + 8px inset = 64
        section.getBoundingClientRect = rect(64, 900);
        section.getClientRects = () => [{ top: 64, bottom: 900 }];
        main.getBoundingClientRect = rect(56, 856);
        main.appendChild(section);
        document.body.appendChild(main);

        const didScroll = scrollElementToStart(section, { behavior: 'smooth' });

        expect(didScroll).toBe(false);
        expect(scrollCalls).toEqual([]);
    });
});
