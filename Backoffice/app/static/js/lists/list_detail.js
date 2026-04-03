// List detail page JavaScript for inline editing
// Assumes lookupListId is defined globally
// Uses apiFetch/fetchJson and confirm-dialogs from core layout (load api-fetch.js)

const fetchJson = (url, options) => (window.fetchJson || window.apiFetch)(url, options);

// Drag and drop functionality
let draggedRow = null;
let draggedRowInitialY = 0;
let draggedRowInitialIndex = 0;
let dropTarget = null;

function initDragAndDrop() {
    const tableBody = document.getElementById('table-body');
    if (!tableBody) {
        console.log('Table body not found, skipping drag and drop initialization');
        return;
    }
    const rows = tableBody.getElementsByTagName('tr');

    Array.from(rows).forEach(row => {
        // Only make rows draggable from the handle
        const handle = row.querySelector('.drag-handle');
        if (!handle) return;

        handle.addEventListener('mousedown', () => {
            row.draggable = true;
        });

        handle.addEventListener('mouseup', () => {
            row.draggable = false;
        });

        row.addEventListener('dragstart', (e) => {
            draggedRow = row;
            draggedRowInitialY = e.clientY;
            draggedRowInitialIndex = Array.from(rows).indexOf(row);
            row.classList.add('bg-blue-50');

            // Create a custom drag image
            const dragImage = row.cloneNode(true);
            dragImage.style.opacity = '0.5';
            document.body.appendChild(dragImage);
            e.dataTransfer.setDragImage(dragImage, 0, 0);
            setTimeout(() => document.body.removeChild(dragImage), 0);
        });

        row.addEventListener('dragend', () => {
            draggedRow.classList.remove('bg-blue-50');
            draggedRow = null;
            dropTarget = null;
        });

        row.addEventListener('dragover', (e) => {
            e.preventDefault();
            if (row === draggedRow) return;

            const rect = row.getBoundingClientRect();
            const midpoint = rect.top + rect.height / 2;

            // Determine if we're dropping before or after based on mouse position
            const position = e.clientY < midpoint ? 'before' : 'after';

            // Remove existing drop indicators
            row.classList.remove('drop-above', 'drop-below');

            // Add new drop indicator
            row.classList.add(position === 'before' ? 'drop-above' : 'drop-below');

            dropTarget = { row, position };
        });

        row.addEventListener('dragleave', () => {
            row.classList.remove('drop-above', 'drop-below');
            if (dropTarget?.row === row) {
                dropTarget = null;
            }
        });

        row.addEventListener('drop', (e) => {
            e.preventDefault();
            row.classList.remove('drop-above', 'drop-below');

            if (!draggedRow || draggedRow === row) return;

            const position = dropTarget?.position || 'after';
            moveRow(draggedRow.dataset.rowId, row.dataset.rowId, position);
        });
    });
}

// Edit cell functionality
function editCell(cell) {
    console.log('editCell called with:', cell);

    // Prevent editing if cell is already being edited
    if (cell.querySelector('input')) {
        console.log('Cell already being edited, returning');
        return;
    }

    const currentValue = cell.textContent.trim();
    const column = cell.dataset.column;
    console.log('Starting edit:', { currentValue, column });

    // Create input element
    const input = document.createElement('input');
    input.type = 'text';
    input.value = currentValue;
    input.className = 'w-full px-2 py-1 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500';

    // Replace cell content with input
    cell.replaceChildren();
    cell.appendChild(input);
    input.focus();
    input.select();

    // Save on Enter or blur
    function saveCell() {
        const newValue = input.value.trim();
        const rowId = cell.closest('tr').dataset.rowId;

        console.log('saveCell called:', { newValue, rowId, column });

        // Update cell display
        cell.textContent = newValue;

        // Send update to server
        updateRowData(rowId, column, newValue);
    }

    input.addEventListener('blur', saveCell);
    input.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            saveCell();
        }
    });

    input.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            // Cancel edit
            cell.textContent = currentValue;
        }
    });
}

// Update row data on server
function updateRowData(rowId, column, value) {
    const data = {};
    data[column] = value;

    console.log('Sending update request:', { rowId, column, value, data });

    window.csrfFetch(`/admin/templates/lists/${lookupListId}/rows/${rowId}`, {
        method: 'PATCH',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    })
    .then(response => {
        console.log('Update response status:', response.status);
        if (!response.ok) {
            throw (window.httpErrorSync && window.httpErrorSync(response)) || new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        console.log('Update response data:', data);
        if (!data.success) {
            console.error('Failed to update row:', data.message);
            // Could show user notification here
        } else {
            console.log('Row updated successfully!');
        }
    })
    .catch(error => {
        console.error('Error updating row:', error);
    });
}

// Add new row
function addRow() {
    // Get the last row's order value
    const rows = document.querySelectorAll('tr[data-row-id]');
    const lastRow = rows[rows.length - 1];
    const order = lastRow ? parseInt(lastRow.dataset.order || '0') + 1 : 1;

    fetchJson(`/admin/api/templates/lists/${lookupListId}/rows`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order: order })
    }).then(data => {
        if (data && data.success) {
            location.reload();
        } else {
            console.error('Failed to add row:', data?.message);
        }
    }).catch(error => {
        console.error('Error adding row:', error);
    });
}

// Add event listeners for row management buttons
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOMContentLoaded - initializing list detail functionality');
    console.log('LookupListId:', lookupListId);

    // Check if table exists before initializing features
    const tableBody = document.getElementById('table-body');
    if (!tableBody) {
        console.log('Table body not found - no columns configured, skipping table features');
        return;
    }

    // Initialize drag and drop
    initDragAndDrop();

    // Delete row buttons
    document.querySelectorAll('button[data-delete-row]').forEach(button => {
        button.addEventListener('click', function() {
            const rowId = this.getAttribute('data-delete-row');
            deleteRow(rowId);
        });
    });

    // Add row buttons
    document.querySelectorAll('.add-row-btn').forEach(button => {
        button.addEventListener('click', function() {
            const row = this.closest('tr');
            addRowAfter(row);
        });
    });

    // Initialize cell editing click listeners
    function initCellEditing() {
        const editableCells = document.querySelectorAll('.editable');
        console.log('Found editable cells:', editableCells.length);

        editableCells.forEach(cell => {
            // Remove existing listeners to prevent duplicates
            cell.removeEventListener('click', cellEditingHandler);
            cell.addEventListener('click', cellEditingHandler);
            console.log('Added click listener to cell:', cell);
        });
    }

    // Cell editing click handler
    function cellEditingHandler(e) {
        console.log('Cell clicked:', e.target);

        // Don't trigger edit if clicking on drag handle or action buttons
        if (e.target.closest('.drag-handle') || e.target.closest('button')) {
            console.log('Click ignored - drag handle or button');
            return;
        }
        console.log('Starting cell edit');
        editCell(this);
    }

    // Initialize cell editing
    console.log('Initializing cell editing...');
    initCellEditing();

    // Re-evaluate cell editing after any Ajax operations
    document.addEventListener('row-updated', function() {
        initCellEditing(); // Reinitialize cell editing for new rows
    });
});

// Move row in the table
function moveRow(rowId, targetRowId, position) {
    fetchJson(`/admin/templates/lists/${lookupListId}/rows/${rowId}/move`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_row_id: targetRowId, position: position })
    }).then(data => {
        if (data && data.success) {
            // Move was successful, update the UI
            const row = document.querySelector(`tr[data-row-id="${rowId}"]`);
            const targetRow = document.querySelector(`tr[data-row-id="${targetRowId}"]`);
            if (row && targetRow) {
                if (position === 'before') {
                    targetRow.parentNode.insertBefore(row, targetRow);
                } else {
                    targetRow.parentNode.insertBefore(row, targetRow.nextSibling);
                }
            }
        } else {
            console.error('Failed to move row:', data?.message);
        }
    }).catch(error => {
        console.error('Error moving row:', error);
    });
}

// Add row after a specific row
function addRowAfter(afterRow) {
    // Get the order value of the row we want to insert after
    const afterOrder = parseInt(afterRow.dataset.order || '0');

    fetchJson(`/admin/api/templates/lists/${lookupListId}/rows`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ insert_after_order: afterOrder })
    }).then(data => {
        if (data && data.success) {
            location.reload();
        } else {
            console.error('Failed to add row:', data?.message);
        }
    }).catch(error => {
        console.error('Error adding row:', error);
    });
}

// Delete a row
function deleteRow(rowId) {
    const doDelete = () => {
        fetchJson(`/admin/templates/lists/${lookupListId}/rows/${rowId}`, {
            method: 'DELETE'
        }).then(data => {
            if (data && data.success) {
                const row = document.querySelector(`tr[data-row-id="${rowId}"]`);
                if (row) row.remove();
                document.dispatchEvent(new Event('row-updated'));
            } else {
                console.error('Failed to delete row:', data?.message);
            }
        }).catch(error => console.error('Error deleting row:', error));
    };
    if (window.showDangerConfirmation) {
        window.showDangerConfirmation('Are you sure you want to delete this row?', doDelete, null, 'Delete', 'Cancel', 'Confirm Delete');
    } else if (window.showConfirmation) {
        window.showConfirmation('Are you sure you want to delete this row?', doDelete, null, 'Delete', 'Cancel', 'Confirm Delete');
    }
}

// Add the first row to an empty list
function addFirstRow() {
    console.log('Adding first row to list:', lookupListId);

    fetchJson(`/admin/api/templates/lists/${lookupListId}/rows`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order: 1 })
    }).then(data => {
        if (data && data.success) {
            location.reload();
        } else {
            const msg = data?.message || 'Unknown error';
            if (window.showAlert) window.showAlert('Failed to add first row: ' + msg, 'error');
        }
    }).catch(error => {
        console.error('Error adding first row:', error);
        if (window.showAlert) window.showAlert('Error adding first row: ' + (error.message || error), 'error');
    });
}

// Add a row at the end of the list
function addRowAtEnd() {
    console.log('Adding row at end of list:', lookupListId);

    // Get the highest order number
    const rows = document.querySelectorAll('tr[data-row-id]');
    let maxOrder = 0;
    rows.forEach(row => {
        const order = parseInt(row.dataset.order || '0');
        if (order > maxOrder) {
            maxOrder = order;
        }
    });

    const newOrder = maxOrder + 1;

    fetchJson(`/admin/api/templates/lists/${lookupListId}/rows`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order: newOrder })
    }).then(data => {
        if (data && data.success) {
            location.reload();
        } else {
            const msg = data?.message || 'Unknown error';
            if (window.showAlert) window.showAlert('Failed to add row: ' + msg, 'error');
        }
    }).catch(error => {
        console.error('Error adding row:', error);
        if (window.showAlert) window.showAlert('Error adding row: ' + (error.message || error), 'error');
    });
}
