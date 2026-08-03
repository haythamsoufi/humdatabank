/**
 * P&B-style year grid table below line charts.
 */
export function renderYearDataGrid(container, dashboard) {
    if (!dashboard || !Array.isArray(dashboard.years) || dashboard.years.length === 0) {
        return;
    }
    const years = dashboard.years;
    const showReporting = dashboard.show_reporting !== false;
    const showImplementing = dashboard.show_implementing !== false;
    const labels = dashboard.table_labels || {};
    const colPct = (100 / years.length).toFixed(6);

    const wrap = document.createElement('div');
    wrap.className = 'report-dashboard-footer';

    const layout = document.createElement('table');
    layout.className = 'report-dashboard-layout';
    layout.setAttribute('role', 'presentation');

    const labelCell = document.createElement('td');
    labelCell.className = 'report-dashboard-labels';
    const labelTable = document.createElement('table');
    labelTable.className = 'report-dashboard-label-grid';
    labelTable.setAttribute('role', 'presentation');

    function addLabelRow(text, className) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        if (className) td.className = className;
        td.textContent = text;
        tr.appendChild(td);
        labelTable.appendChild(tr);
    }

    addLabelRow(labels.year || 'Year', 'year-label');
    if (showReporting) addLabelRow(labels.reporting || 'Reporting NS');
    if (showImplementing) addLabelRow(labels.implementing || 'Implementing NS');
    labelCell.appendChild(labelTable);

    const dataCell = document.createElement('td');
    dataCell.className = 'report-dashboard-table-data';

    const grid = document.createElement('table');
    grid.className = 'report-year-data-grid';
    grid.setAttribute('role', 'presentation');
    const colgroup = document.createElement('colgroup');
    years.forEach(function () {
        const col = document.createElement('col');
        col.style.width = colPct + '%';
        colgroup.appendChild(col);
    });
    grid.appendChild(colgroup);

    function addDataRow(values, rowClass) {
        const tr = document.createElement('tr');
        if (rowClass) tr.className = rowClass;
        values.forEach(function (value) {
            const td = document.createElement('td');
            td.textContent = value != null && value !== '' ? String(value) : '—';
            tr.appendChild(td);
        });
        grid.appendChild(tr);
    }

    addDataRow(years, 'year-row');
    if (showReporting) addDataRow(dashboard.reporting || []);
    if (showImplementing) addDataRow(dashboard.implementing || []);
    dataCell.appendChild(grid);

    const row = document.createElement('tr');
    row.appendChild(labelCell);
    row.appendChild(dataCell);
    layout.appendChild(row);
    wrap.appendChild(layout);
    container.appendChild(wrap);
}
