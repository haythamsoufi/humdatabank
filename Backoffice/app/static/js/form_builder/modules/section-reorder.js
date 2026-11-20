/**
 * Drag collapsed form-builder sections to reorder them within their page.
 * The handle is only shown while a section is collapsed.
 */

import { CsrfHandler } from './csrf-handler.js';

const _t = (k) => (typeof window.t === 'function' ? window.t(k) : k);

let draggedSection = null;
let dropTarget = null;
let saving = false;

function showError(message) {
    if (window.Utils && typeof window.Utils.showError === 'function') {
        window.Utils.showError(message);
        return;
    }
    if (typeof window.showFlashMessage === 'function') {
        window.showFlashMessage(message, 'danger');
    }
}

function sectionContainer(section) {
    return section ? section.closest('.page-sections-container') : null;
}

function siblingSections(container) {
    if (!container) return [];
    return Array.from(container.querySelectorAll(':scope > .section-item'));
}

function clearDropMarkers(container) {
    if (!container) return;
    container.querySelectorAll(':scope > .section-item').forEach((el) => {
        el.classList.remove('drop-above', 'drop-below');
    });
}

function applyOrder(section, order) {
    const value = String(order);
    section.dataset.sectionOrder = value;
    const label = section.querySelector('.section-display-order');
    if (label) label.textContent = `${value}.`;
    section.querySelectorAll('.section-header-actions [data-section-order]').forEach((el) => {
        el.dataset.sectionOrder = value;
    });
}

function readOrders(sections) {
    return sections.map((section) => {
        const raw = section.dataset.sectionOrder
            || section.querySelector('.section-display-order')?.textContent
            || '';
        const order = parseInt(String(raw), 10);
        return Number.isFinite(order) ? order : null;
    });
}

/** Keep the same order numbers, written back in visual sequence. */
export function ordersForSequence(currentOrders) {
    const known = currentOrders.filter((order) => order !== null);
    const sorted = known.slice().sort((a, b) => a - b);
    const unique = new Set(sorted).size === sorted.length;
    const sequence = unique
        ? sorted
        : Array.from({ length: sorted.length }, (_, index) => (sorted[0] ?? 1) + index);
    let next = 0;
    return currentOrders.map((order) => {
        if (order === null) return null;
        const assigned = sequence[next];
        next += 1;
        return assigned;
    });
}

function paintOrders(sections) {
    const assigned = ordersForSequence(readOrders(sections));
    sections.forEach((section, index) => {
        if (assigned[index] !== null) applyOrder(section, assigned[index]);
    });
}

function versionId() {
    const fromConfig = document.getElementById('excel-import-version-config')?.dataset.versionId;
    if (fromConfig) return fromConfig;
    return new URLSearchParams(window.location.search).get('version_id') || '';
}

function snapshotOrder(container) {
    return siblingSections(container).map((section) => section.dataset.sectionId);
}

function restoreOrder(container, ids) {
    const byId = new Map(siblingSections(container).map((section) => [section.dataset.sectionId, section]));
    ids.forEach((id) => {
        const section = byId.get(id);
        if (section) container.appendChild(section);
    });
    paintOrders(siblingSections(container));
}

async function persistOrder(container, previousIds) {
    const sections = siblingSections(container);
    const ids = sections.map((section) => Number(section.dataset.sectionId)).filter((id) => Number.isFinite(id));
    const templateId = window.templateId;
    if (!templateId || !ids.length) return;

    paintOrders(sections);
    saving = true;
    try {
        const response = await CsrfHandler.safeFetch(
            `/admin/templates/${templateId}/sections/reorder`,
            {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    Accept: 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: JSON.stringify({
                    version_id: versionId(),
                    section_ids: ids,
                }),
            },
        );
        let data = null;
        try {
            data = await response.json();
        } catch (_e) {
            data = null;
        }
        if (!response.ok || !data || data.success === false) {
            throw new Error((data && (data.message || data.error)) || _t('Could not save the new section order.'));
        }
        const orders = data.orders || {};
        sections.forEach((section) => {
            const order = orders[section.dataset.sectionId] ?? orders[Number(section.dataset.sectionId)];
            if (order !== undefined && order !== null) applyOrder(section, order);
        });
    } catch (error) {
        restoreOrder(container, previousIds);
        showError(error && error.message ? error.message : _t('Could not save the new section order.'));
    } finally {
        saving = false;
    }
}

function moveSection(section, target, before) {
    const container = sectionContainer(section);
    if (!container || sectionContainer(target) !== container || section === target) return;
    const previousIds = snapshotOrder(container);
    if (before) container.insertBefore(section, target);
    else container.insertBefore(section, target.nextElementSibling);
    const nextIds = snapshotOrder(container);
    if (previousIds.join() === nextIds.join()) return;
    persistOrder(container, previousIds);
}

function onPointerDown(event) {
    const handle = event.target.closest('.section-drag-handle');
    if (!handle || !handle.closest('#form-builder-ui')) return;
    const section = handle.closest('.section-item');
    if (!section || !section.classList.contains('section-collapsed') || saving) return;
    section.draggable = true;
}

function clearDraggable() {
    if (draggedSection) return;
    document.querySelectorAll('#form-builder-ui .section-item[draggable="true"]').forEach((section) => {
        section.draggable = false;
    });
}

function onDragStart(event) {
    const section = event.target.closest?.('.section-item');
    if (!section || !section.classList.contains('section-collapsed') || saving) {
        event.preventDefault();
        return;
    }
    draggedSection = section;
    section.classList.add('dragging');
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', section.dataset.sectionId || '');
}

function onDragOver(event) {
    if (!draggedSection) return;
    const container = sectionContainer(draggedSection);
    if (!container || !container.contains(event.target)) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';

    const scroller = document.querySelector('.admin-scroll-main');
    if (scroller) {
        const bounds = scroller.getBoundingClientRect();
        if (event.clientY < bounds.top + 56) scroller.scrollTop -= 18;
        else if (event.clientY > bounds.bottom - 56) scroller.scrollTop += 18;
    }

    const section = event.target.closest('.section-item');
    if (!section || section === draggedSection || section.parentElement !== container) return;
    const rect = section.getBoundingClientRect();
    const before = event.clientY < rect.top + rect.height / 2;
    clearDropMarkers(container);
    section.classList.add(before ? 'drop-above' : 'drop-below');
    dropTarget = { section, before };
}

function onDrop(event) {
    if (!draggedSection) return;
    const container = sectionContainer(draggedSection);
    if (!container || !container.contains(event.target)) return;
    event.preventDefault();
    const target = dropTarget;
    clearDropMarkers(container);
    dropTarget = null;
    if (target) moveSection(draggedSection, target.section, target.before);
}

function onDragEnd() {
    const section = draggedSection;
    const container = sectionContainer(section);
    clearDropMarkers(container);
    if (section) {
        section.classList.remove('dragging');
        section.draggable = false;
    }
    draggedSection = null;
    dropTarget = null;
}

function onKeyDown(event) {
    const handle = event.target.closest?.('.section-drag-handle');
    if (!handle || saving) return;
    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
    const section = handle.closest('.section-item');
    if (!section || !section.classList.contains('section-collapsed')) return;
    const sibling = event.key === 'ArrowUp'
        ? section.previousElementSibling
        : section.nextElementSibling;
    if (!sibling || !sibling.classList.contains('section-item')) return;
    event.preventDefault();
    moveSection(section, sibling, event.key === 'ArrowUp');
    section.querySelector('.section-drag-handle')?.focus();
}

export function initCollapsedSectionReorder() {
    if (window.__fbSectionReorderBound) return;
    window.__fbSectionReorderBound = true;
    CsrfHandler.init();
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('pointerup', clearDraggable);
    document.addEventListener('pointercancel', clearDraggable);
    document.addEventListener('dragstart', onDragStart);
    document.addEventListener('dragover', onDragOver);
    document.addEventListener('drop', onDrop);
    document.addEventListener('dragend', onDragEnd);
    document.addEventListener('keydown', onKeyDown);
}
