import { beforeEach, describe, expect, it } from 'vitest';
import { initFormBuilderActionOverflow, placeFormBuilderActionMenu } from '../../../app/static/js/form_builder/modules/action-overflow.js';

function mockMobile(matches) {
    window.matchMedia = (query) => ({
        matches,
        media: query,
        addEventListener() {},
        removeEventListener() {},
        addListener() {},
        removeListener() {},
    });
}

function renderCluster(label = 'Edit section') {
    document.body.innerHTML = `
        <div id="form-builder-ui">
            <div class="fb-actions">
                <button type="button" class="fb-actions-toggle" aria-expanded="false">Actions</button>
                <div class="fb-actions-panel">
                    <button type="button" class="fb-icon-btn edit-section-btn" title="${label}">Edit</button>
                </div>
            </div>
        </div>
    `;
    const toggle = document.querySelector('.fb-actions-toggle');
    const panel = document.querySelector('.fb-actions-panel');
    toggle.getBoundingClientRect = () => ({
        top: 100,
        bottom: 144,
        left: 300,
        right: 344,
        width: 44,
        height: 44,
    });
    Object.defineProperty(panel, 'offsetWidth', { configurable: true, value: 200 });
    Object.defineProperty(panel, 'offsetHeight', { configurable: true, value: 120 });
    return { toggle, panel };
}

describe('form builder action overflow', () => {
    beforeEach(() => {
        mockMobile(true);
        window.innerWidth = 390;
        window.innerHeight = 800;
        renderCluster();
        initFormBuilderActionOverflow();
    });

    it('marks the builder ready and opens a positioned menu from the toggle', () => {
        expect(document.getElementById('form-builder-ui').classList.contains('fb-actions-ready')).toBe(true);

        document.querySelector('.fb-actions-toggle').click();

        const root = document.querySelector('.fb-actions');
        const panel = document.querySelector('.fb-actions-panel');
        expect(root.classList.contains('is-open')).toBe(true);
        expect(document.querySelector('.fb-actions-toggle').getAttribute('aria-expanded')).toBe('true');
        expect(panel.style.top).toBe('148px');
        expect(panel.style.left).toBe('144px');
        expect(document.querySelector('.edit-section-btn').getAttribute('aria-label')).toBe('Edit section');
    });

    it('closes the open menu when another cluster opens', () => {
        document.body.innerHTML = `
            <div id="form-builder-ui">
                <div class="fb-actions" id="first">
                    <button type="button" class="fb-actions-toggle" aria-expanded="false">Actions</button>
                    <div class="fb-actions-panel"><button type="button" class="fb-icon-btn" title="Edit">Edit</button></div>
                </div>
                <div class="fb-actions" id="second">
                    <button type="button" class="fb-actions-toggle" aria-expanded="false">Actions</button>
                    <div class="fb-actions-panel"><button type="button" class="fb-icon-btn" title="Delete">Delete</button></div>
                </div>
            </div>
        `;
        initFormBuilderActionOverflow();
        document.querySelector('#first .fb-actions-toggle').click();
        document.querySelector('#second .fb-actions-toggle').click();
        expect(document.getElementById('first').classList.contains('is-open')).toBe(false);
        expect(document.getElementById('second').classList.contains('is-open')).toBe(true);
    });

    it('closes on Escape, outside click, and after choosing an action', () => {
        const toggle = document.querySelector('.fb-actions-toggle');
        toggle.click();
        document.querySelector('.edit-section-btn').click();
        expect(document.querySelector('.fb-actions').classList.contains('is-open')).toBe(false);

        toggle.click();
        document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        expect(document.querySelector('.fb-actions').classList.contains('is-open')).toBe(false);

        toggle.click();
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
        expect(document.querySelector('.fb-actions').classList.contains('is-open')).toBe(false);
    });

    it('still activates a menu action after the panel is moved', () => {
        document.body.innerHTML = `
            <div id="form-builder-ui">
                <div class="overflow-x-auto">
                    <div class="fb-actions">
                        <button type="button" class="fb-actions-toggle" aria-expanded="false">Actions</button>
                        <div class="fb-actions-panel">
                            <form class="duplicate-item-form">
                                <button type="submit" class="fb-icon-btn" title="Duplicate">Duplicate</button>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
        `;
        initFormBuilderActionOverflow();
        let submitted = false;
        document.querySelector('form').addEventListener('submit', (event) => {
            event.preventDefault();
            submitted = true;
        });
        document.querySelector('.fb-actions-toggle').click();
        expect(document.querySelector('.fb-actions-panel').parentElement.id).toBe('form-builder-ui');
        document.querySelector('button[type="submit"]').click();
        expect(submitted).toBe(true);
        expect(document.querySelector('.fb-actions').classList.contains('is-open')).toBe(false);
        expect(document.querySelector('.fb-actions-panel').parentElement.classList.contains('fb-actions')).toBe(true);
    });

    it('keeps the menu closed when the viewport is desktop width', () => {
        mockMobile(false);
        document.querySelector('.fb-actions-toggle').click();
        expect(document.querySelector('.fb-actions').classList.contains('is-open')).toBe(false);
    });

    it('opens upward when the menu would leave the viewport', () => {
        window.innerHeight = 200;
        const { panel, toggle } = renderCluster();
        initFormBuilderActionOverflow();
        placeFormBuilderActionMenu(panel, toggle);
        expect(panel.style.top).toBe('72px');
    });
});
