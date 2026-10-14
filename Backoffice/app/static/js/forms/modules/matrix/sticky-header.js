/**
 * Keep a matrix's column headers on screen while the page is scrolled past them.
 *
 * The table lives in a horizontal scroller, so position:sticky cannot follow the
 * window. A fixed copy of the header is shown instead, lined up with the columns.
 */

const pins = new Set();
let listening = false;
let scheduled = false;

/** True once the real header has left the top of the screen and the table is still there. */
export function shouldPinMatrixHeader(headerRect, tableRect, pinTop) {
    const height = headerRect.bottom - headerRect.top;
    if (!(height > 0)) return false;
    if (headerRect.bottom > pinTop) return false;
    if (tableRect.bottom <= pinTop + height) return false;
    return true;
}

function pinTop() {
    const nav = document.getElementById('appTopNav');
    if (!nav) return 0;
    const bottom = nav.getBoundingClientRect().bottom;
    return bottom > 0 ? bottom : 0;
}

function lockCellWidths(sourceRow, cloneRow) {
    const source = sourceRow ? sourceRow.children : [];
    const clone = cloneRow ? cloneRow.children : [];
    for (let i = 0; i < clone.length; i += 1) {
        const width = source[i] ? source[i].getBoundingClientRect().width : 0;
        clone[i].style.boxSizing = 'border-box';
        clone[i].style.width = `${width}px`;
        clone[i].style.minWidth = `${width}px`;
        clone[i].style.maxWidth = `${width}px`;
    }
}

function updatePin(pin) {
    const { scrollEl, table, thead, bar, shift } = pin;
    if (!scrollEl.isConnected || !thead.isConnected) {
        bar.classList.remove('is-active');
        return;
    }
    const top = pinTop();
    const headerRect = thead.getBoundingClientRect();
    const tableRect = table.getBoundingClientRect();
    const visible = shouldPinMatrixHeader(headerRect, tableRect, top);
    if (!visible) {
        bar.classList.remove('is-active');
        return;
    }

    const scrollRect = scrollEl.getBoundingClientRect();
    bar.style.top = `${top}px`;
    bar.style.left = `${scrollRect.left}px`;
    bar.style.width = `${scrollRect.width}px`;
    bar.classList.add('is-active');

    const tableWidth = table.getBoundingClientRect().width;
    shift.style.width = `${tableWidth}px`;
    shift.style.transform = `translateX(${-scrollEl.scrollLeft}px)`;

    const sourceRows = thead.rows;
    const cloneRows = pin.clone.rows;
    for (let i = 0; i < cloneRows.length; i += 1) {
        lockCellWidths(sourceRows[i], cloneRows[i]);
    }
}

function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
        scheduled = false;
        pins.forEach(updatePin);
    });
}

function ensureListening() {
    if (listening) return;
    listening = true;
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);
    document.addEventListener('scroll', schedule, { passive: true, capture: true });
}

export function pinMatrixColumnHeaders(container) {
    const scrollEl = container.querySelector('.matrix-table-scroll');
    const table = scrollEl ? scrollEl.querySelector('table') : null;
    const thead = table ? table.querySelector('thead') : null;
    if (!scrollEl || !thead || thead.rows.length === 0) return;

    const bar = document.createElement('div');
    bar.className = 'matrix-pinned-header';
    bar.setAttribute('aria-hidden', 'true');

    const shift = document.createElement('div');
    const cloneTable = document.createElement('table');
    cloneTable.className = table.className;
    const clone = thead.cloneNode(true);
    clone.querySelectorAll('[id]').forEach((el) => el.removeAttribute('id'));
    clone.querySelectorAll('[name]').forEach((el) => el.removeAttribute('name'));
    cloneTable.appendChild(clone);
    shift.appendChild(cloneTable);
    bar.appendChild(shift);
    document.body.appendChild(bar);

    const pin = { scrollEl, table, thead, bar, shift, clone };
    pins.add(pin);
    ensureListening();

    if (typeof ResizeObserver === 'function') {
        const observer = new ResizeObserver(schedule);
        observer.observe(table);
        observer.observe(scrollEl);
    }
    schedule();
}
