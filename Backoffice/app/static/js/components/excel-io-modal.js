/**
 * Excel IO modal — open/close, tab switching, reset dropzones on close.
 */

import { resetExcelImportDropzones } from './excel-import-dropzone.js';

function resolveElement(el) {
    if (!el) return null;
    if (typeof el === 'string') return document.querySelector(el);
    return el;
}

function resolveElements(el) {
    if (!el) return [];
    if (typeof el === 'string') return Array.from(document.querySelectorAll(el));
    if (Array.isArray(el)) return el.map(resolveElement).filter(Boolean);
    return [el];
}

const initializedModals = new WeakMap();

function wireOpenTrigger(modal, openFn, trigger) {
    if (!trigger || trigger.dataset.excelIoOpenWired === modal.id) return;
    trigger.dataset.excelIoOpenWired = modal.id;
    trigger.addEventListener('click', (e) => {
        e.preventDefault();
        openFn();
    });
}

export function initExcelIoModal(modalId, options = {}) {
    const modal = resolveElement(modalId);
    if (!modal) return { open() {}, close() {} };

    const existing = initializedModals.get(modal);
    if (existing) {
        resolveElements(options.openTrigger).forEach((trigger) => {
            wireOpenTrigger(modal, existing.open, trigger);
        });
        if (typeof options.onClose === 'function') {
            existing.onCloseHandlers.add(options.onClose);
        }
        if (typeof options.onOpen === 'function') {
            existing.onOpenHandlers.add(options.onOpen);
        }
        return existing;
    }

    const openTriggers = resolveElements(options.openTrigger);
    const closeTriggers = [
        ...resolveElements(options.closeTriggers),
        modal.querySelector('.close-modal'),
        modal.querySelector('.btn-close-icon'),
    ].filter(Boolean);

    const resetDropzonesOnClose = options.resetDropzonesOnClose !== false;
    const defaultTab = options.defaultTab
        || modal.querySelector('[data-excel-io-default-tab]')?.dataset.excelIoDefaultTab
        || 'export';
    const onCloseHandlers = new Set();
    const onOpenHandlers = new Set();
    if (typeof options.onClose === 'function') onCloseHandlers.add(options.onClose);
    if (typeof options.onOpen === 'function') onOpenHandlers.add(options.onOpen);

    function setTab(tabName) {
        modal.querySelectorAll('[data-excel-io-tab]').forEach((btn) => {
            const active = btn.dataset.excelIoTab === tabName;
            btn.classList.toggle('excel-io-tabs__btn--active', active);
            btn.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        modal.querySelectorAll('[data-excel-io-panel]').forEach((panel) => {
            panel.hidden = panel.dataset.excelIoPanel !== tabName;
        });
    }

    function open() {
        modal.classList.remove('hidden');
        if (modal.dataset.excelIoLayout === 'tabs') {
            setTab(defaultTab);
        }
        onOpenHandlers.forEach((handler) => handler());
    }

    function close() {
        modal.classList.add('hidden');
        if (resetDropzonesOnClose) {
            resetExcelImportDropzones(modal);
        }
        modal.dispatchEvent(new CustomEvent('excel-io-modal-closed', { bubbles: true }));
        onCloseHandlers.forEach((handler) => handler());
    }

    const controller = { open, close, setTab, onCloseHandlers, onOpenHandlers };
    initializedModals.set(modal, controller);

    openTriggers.forEach((trigger) => wireOpenTrigger(modal, open, trigger));

    document.querySelectorAll('[data-excel-io-open]').forEach((btn) => {
        if (btn.dataset.excelIoOpen === modal.id) {
            wireOpenTrigger(modal, open, btn);
        }
    });

    closeTriggers.forEach((btn) => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            close();
        });
    });

    modal.addEventListener('click', (e) => {
        if (e.target === modal) close();
    });

    modal.querySelectorAll('[data-excel-io-tab]').forEach((btn) => {
        btn.addEventListener('click', () => setTab(btn.dataset.excelIoTab));
    });

    return controller;
}

export function initExcelIoModalsFromDom() {
    const seen = new Set();
    document.querySelectorAll('[data-excel-io-layout]').forEach((inner) => {
        const modal = inner.closest('[role="dialog"]');
        if (!modal || seen.has(modal.id)) return;
        seen.add(modal.id);
        initExcelIoModal(modal);
    });
}

function bootExcelIoModalsFromDom() {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initExcelIoModalsFromDom);
    } else {
        initExcelIoModalsFromDom();
    }
}

if (typeof document !== 'undefined') {
    bootExcelIoModalsFromDom();
}
