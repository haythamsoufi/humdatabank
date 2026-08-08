/**
 * Simple HTML table renderer for report table widgets.
 */
import { rowCellStyle } from './conditional-formatting.js';

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
            const value = row && row[col] != null ? String(row[col]) : '';
            td.textContent = value;
            const style = rowCellStyle(row && row[col], payload.chart_options);
            if (style) td.setAttribute('style', style);
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    container.appendChild(table);
}
