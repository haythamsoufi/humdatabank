/**
 * Simple HTML table renderer for report table widgets.
 */
export function renderTable(container, payload) {
    container.innerHTML = '';
    if (payload.error) {
        container.textContent = payload.error;
        return;
    }
    const columns = payload.columns || [];
    const rows = payload.rows || [];
    if (!columns.length && rows.length && typeof rows[0] === 'object') {
        columns.push(...Object.keys(rows[0]));
    }
    const table = document.createElement('table');
    table.className = 'report-data-table';
    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');
    columns.forEach(function (col) {
        const th = document.createElement('th');
        th.textContent = col;
        headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);
    const tbody = document.createElement('tbody');
    rows.forEach(function (row) {
        const tr = document.createElement('tr');
        columns.forEach(function (col) {
            const td = document.createElement('td');
            td.textContent = row && row[col] != null ? String(row[col]) : '';
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    container.appendChild(table);
}
