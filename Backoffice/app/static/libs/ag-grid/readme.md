# AG Grid Community - Complete Documentation

Complete integration guide for AG Grid Community with custom Set Filter and Column Visibility Manager for Flask/Jinja2 templates.

## 📦 Files Overview

### Core AG Grid Files
- `ag-grid-community.min.js` - Main AG Grid library (all Community features)
- `ag-grid.css` - Core AG Grid styles
- `ag-theme-alpine.css` - Alpine theme (recommended)
- `ag-theme-balham.css` - Balham theme
- `ag-theme-quartz.css` - Quartz theme
- `ag-theme-material.css` - Material theme

### Custom Components
- `ag-set-filter-community.js` - Excel-like Set Filter component
- `ag-set-filter-community.css` - Set Filter styles
- `ag-column-visibility-manager.js` - Column show/hide manager with persistence
- `ag-column-visibility-manager.css` - Column Visibility Manager styles
- `ag-grid-helper.js` - Centralized helper utility (recommended)
- `ag-grid-common-styles.css` - Common button and grid styles

## 🚀 Quick Start

### Step 1: Include CSS Files

Add to your template's `{% block head %}`:

```html
{% block head %}
    {{ super() }}
    <!-- AG Grid Core CSS -->
    <link rel="stylesheet" href="{{ url_for('static', filename='libs/ag-grid/ag-grid.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='libs/ag-grid/ag-theme-alpine.css') }}">
    
    <!-- Custom Components CSS -->
    <link rel="stylesheet" href="{{ url_for('static', filename='libs/ag-grid/ag-set-filter-community.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='libs/ag-grid/ag-column-visibility-manager.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='libs/ag-grid/ag-grid-common-styles.css') }}">
{% endblock %}
```

### Step 2: Include JavaScript Files

Add before closing `</body>` or in `{% block extra_js %}`:

```html
{% block extra_js %}
    <!-- AG Grid Core -->
    <script src="{{ url_for('static', filename='libs/ag-grid/ag-grid-community.min.js') }}"></script>
    
    <!-- Custom Components -->
    <script src="{{ url_for('static', filename='libs/ag-grid/ag-set-filter-community.js') }}"></script>
    <script src="{{ url_for('static', filename='libs/ag-grid/ag-column-visibility-manager.js') }}"></script>
    <script src="{{ url_for('static', filename='libs/ag-grid/ag-grid-helper.js') }}"></script>
{% endblock %}
```

### Step 3: Create Grid Container

Add to your template content:

```html
{% block content %}
    <div class="flex justify-end items-center mb-4">
        <div id="column-visibility-button-placeholder"></div>
    </div>
    <div id="myGrid" class="ag-theme-alpine" style="height: 600px; width: 100%;"></div>
{% endblock %}
```

### Step 4: Initialize Grid (Using Helper - Recommended)

```javascript
// Define column definitions
const columnDefs = [
    { field: 'id', headerName: 'ID', width: 80, lockVisible: true },
    { field: 'name', headerName: 'Name', width: 200 },
    { 
        field: 'status', 
        headerName: 'Status',
        filter: 'customSetFilter'  // Excel-like filter
    }
];

// Initialize grid with helper
const gridHelper = new AgGridHelper({
    containerId: 'myGrid',
    templateId: 'my-template-id',  // Must be unique per page!
    columnDefs: columnDefs,
    rowData: {{ data|tojson|safe }},
    columnVisibilityOptions: {
        persistOnChange: true,
        showPanelButton: true,
        enableExport: true,
        enableReset: true
    }
});

const gridApi = gridHelper.initialize();

// Expose for debugging
window.gridApi = gridApi;
window.gridHelper = gridHelper;
```

## ✨ Key Features

### 1. Set Filter (Excel-like)

**Use Case**: Columns with limited unique values (status, category, department)

**Features**:
- Shows all unique values in dropdown
- Search to filter values
- Select multiple values with checkboxes
- Select all/none functionality
- Value count display

**Usage**:
```javascript
{
    field: 'status',
    headerName: 'Status',
    filter: 'customSetFilter'  // Excel-like filter
}
```

### 2. Column Visibility Manager

**Use Case**: Allow users to customize which columns to show/hide

**Features**:
- Toggle column visibility
- Save preferences per template/page
- Search columns
- Export/import configurations
- Reset to default
- Lock critical columns

**Usage**:
```javascript
const columnVisibilityManager = new ColumnVisibilityManager(
    gridApi,
    'unique-template-id',  // Must be unique per template
    {
        persistOnChange: true,
        showPanelButton: true,
        enableExport: true,
        enableReset: true
    }
);
```

### 3. AG Grid Helper Utility

**Purpose**: Centralizes and simplifies AG Grid initialization, reducing code by 90%+

**Benefits**:
- Single line grid initialization
- Automatic API detection (createGrid vs Grid constructor)
- Built-in Column Visibility Manager integration
- Consistent defaults with easy customization
- Utility methods for common operations

**Usage**:
```javascript
const gridHelper = new AgGridHelper({
    containerId: 'myGrid',
    templateId: 'my-template-id',
    columnDefs: columnDefs,
    rowData: data
});

const gridApi = gridHelper.initialize();
```

## 📋 Complete Example Template

```html
{% extends "core/layout.html" %}

{% block title %}{{ _('My Data Grid') }}{% endblock %}

{% block head %}
    {{ super() }}
    <!-- AG Grid CSS -->
    <link rel="stylesheet" href="{{ url_for('static', filename='libs/ag-grid/ag-grid.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='libs/ag-grid/ag-theme-alpine.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='libs/ag-grid/ag-set-filter-community.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='libs/ag-grid/ag-column-visibility-manager.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='libs/ag-grid/ag-grid-common-styles.css') }}">
{% endblock %}

{% block content %}
    <div class="container mx-auto px-4 py-6">
        <h1 class="text-2xl font-bold mb-4">{{ _('My Data Grid') }}</h1>
        
        <div class="flex justify-end items-center mb-4">
            <div id="column-visibility-button-placeholder"></div>
        </div>
        
        <!-- Grid Container -->
        <div id="myGrid" class="ag-theme-alpine" style="height: 600px; width: 100%;"></div>
    </div>
{% endblock %}

{% block extra_js %}
    <!-- AG Grid -->
    <script src="{{ url_for('static', filename='libs/ag-grid/ag-grid-community.min.js') }}"></script>
    <script src="{{ url_for('static', filename='libs/ag-grid/ag-set-filter-community.js') }}"></script>
    <script src="{{ url_for('static', filename='libs/ag-grid/ag-column-visibility-manager.js') }}"></script>
    <script src="{{ url_for('static', filename='libs/ag-grid/ag-grid-helper.js') }}"></script>
    
    <script>
        // Column definitions
        const columnDefs = [
            { 
                field: 'id', 
                headerName: 'ID', 
                width: 80,
                minWidth: 80,
                maxWidth: 120,
                lockVisible: true  // Prevent hiding this column
            },
            { 
                field: 'name', 
                headerName: 'Name', 
                width: 200,
                minWidth: 150,
                maxWidth: 300,
                filter: 'agTextColumnFilter'
            },
            { 
                field: 'department', 
                headerName: 'Department',
                width: 150,
                minWidth: 120,
                maxWidth: 200,
                filter: 'customSetFilter'  // Excel-like filter
            },
            { 
                field: 'status', 
                headerName: 'Status',
                width: 120,
                minWidth: 100,
                maxWidth: 150,
                filter: 'customSetFilter'
            }
        ];
        
        // Initialize grid with helper
        const templateId = '{{ request.endpoint|default("default") }}';  // Use Flask route name
        const gridHelper = new AgGridHelper({
            containerId: 'myGrid',
            templateId: templateId,
            columnDefs: columnDefs,
            rowData: {{ data|tojson|safe }},
            options: {
                pagination: true,
                paginationPageSize: 50
            },
            columnVisibilityOptions: {
                persistOnChange: true,
                showPanelButton: true,
                enableExport: true,
                enableReset: true
            }
        });
        
        const gridApi = gridHelper.initialize();
        
        // Optional: Expose to window for debugging
        window.gridApi = gridApi;
        window.gridHelper = gridHelper;
    </script>
{% endblock %}
```

## 🔧 Configuration Options

### AG Grid Helper Options

```javascript
const gridHelper = new AgGridHelper({
    containerId: 'myGrid',           // Required: DOM ID of grid container
    templateId: 'my-template-id',    // Required: Unique identifier per page
    columnDefs: columnDefs,          // Required: Column definitions array
    rowData: data,                    // Optional: Initial row data (default: [])
    options: {                        // Optional: Grid options to override defaults
        paginationPageSize: 100,
        defaultColDef: {
            wrapText: false
        }
    },
    columnVisibilityOptions: {       // Optional: Column Visibility Manager options
        persistOnChange: true,
        showPanelButton: true,
        enableExport: true,
        enableReset: true
    }
});
```

### Default Grid Options

The helper provides sensible defaults:

```javascript
{
    components: {
        customSetFilter: CustomSetFilter  // Auto-registered if available
    },
    defaultColDef: {
        sortable: true,
        resizable: true,
        filter: true,
        wrapText: true,
        autoHeight: true
    },
    pagination: true,
    paginationPageSize: 50,
    paginationPageSizeSelector: [25, 50, 100, 200],
    animateRows: true,
    rowSelection: {
        mode: 'multiRow',
        enableClickSelection: false
    },
    cellSelection: false
}
```

### Column Definition Options

```javascript
{
    field: 'id',
    headerName: 'ID',
    width: 80,              // Initial width (pixels)
    minWidth: 80,           // Minimum width (pixels)
    maxWidth: 120,          // Maximum width (pixels)
    lockVisible: true,      // Prevent hiding
    filter: 'customSetFilter',  // Use custom set filter
    sortable: true,
    resizable: true,
    pinned: 'left'         // Pin column to left
}
```

**Width Options**:
- `width` - Initial/default width in pixels
- `minWidth` - Minimum width column can be resized to
- `maxWidth` - Maximum width column can be resized to
- `flex` - Alternative to width: takes proportional space (e.g., `flex: 1`)

### Column Visibility Manager Options

```javascript
const columnVisibilityManager = new ColumnVisibilityManager(
    gridApi,
    'template-id',  // Unique identifier for this template
    {
        storageKey: 'ag-grid-column-visibility',  // localStorage key prefix
        persistOnChange: true,  // Auto-save on column visibility change
        showPanelButton: true,  // Show "Columns" button
        panelPosition: 'top-right',  // Panel position
        enableExport: true,  // Enable export button
        enableReset: true  // Enable reset button
    }
);
```

## 🎯 Helper Methods

### setRowData(rowData)
Update grid data after initialization:

```javascript
gridHelper.setRowData(newData);
```

### getSelectedRows()
Get array of selected row data:

```javascript
const selected = gridHelper.getSelectedRows();
```

### getSelectedRowIds(idField)
Get array of selected row IDs:

```javascript
const ids = gridHelper.getSelectedRowIds('id');  // Default field is 'id'
```

### refresh()
Refresh grid (recalculate row heights, etc.):

```javascript
gridHelper.refresh();
```

### exportSelectedToCSV(filename)
Export selected rows to CSV:

```javascript
gridHelper.exportSelectedToCSV('export.csv');
```

## 🔍 Filter Types

### Available Filters

1. **customSetFilter** - Excel-like dropdown with unique values (Custom)
2. **agTextColumnFilter** - Text filtering (Built-in)
3. **agNumberColumnFilter** - Number filtering (Built-in)
4. **agDateColumnFilter** - Date filtering (Built-in)

### When to Use Each

- **customSetFilter**: For columns with limited unique values (status, category, department)
- **agTextColumnFilter**: For text columns with many unique values (names, descriptions)
- **agNumberColumnFilter**: For numeric columns (prices, quantities)
- **agDateColumnFilter**: For date columns

## 💾 Persistence Details

### Column Visibility Storage
- **Storage Key**: `ag-grid-column-visibility-{templateId}`
- **Storage Location**: Browser localStorage
- **Data Format**: JSON with column visibility, width, sort state
- **Scope**: Per template/page (unique templateId)

### Example Storage Data
```json
{
    "id": { "visible": true, "width": 80 },
    "name": { "visible": true, "width": 200 },
    "department": { "visible": false, "width": 150 }
}
```

## 🎨 Theming

### Available Themes
- **Alpine** (Recommended) - Modern, clean design
- **Balham** - Professional business look
- **Quartz** - Modern with rounded corners
- **Material** - Material Design style

### Change Theme
Simply change the CSS class and include the corresponding theme CSS:

```html
<!-- Change class -->
<div id="myGrid" class="ag-theme-balham"></div>

<!-- Include theme CSS -->
<link rel="stylesheet" href="{{ url_for('static', filename='libs/ag-grid/ag-theme-balham.css') }}">
```

## 📊 Column Width Guide

### Basic Usage

```javascript
// Simple width
{ field: 'id', width: 80 }

// Width with constraints
{ 
    field: 'name', 
    width: 200,      // Initial width: 200px
    minWidth: 150,   // Cannot resize smaller than 150px
    maxWidth: 300    // Cannot resize larger than 300px
}

// Flexible width (auto-sizing)
{ 
    field: 'description', 
    flex: 1,         // Takes available space proportionally
    minWidth: 200    // But never smaller than 200px
}
```

### Best Practices

1. **Always Set minWidth for Flexible Columns**
   ```javascript
   // ✅ Good
   { field: 'description', flex: 1, minWidth: 200 }
   
   // ❌ Bad - column can become too narrow
   { field: 'description', flex: 1 }
   ```

2. **Use Fixed Width for Small Columns**
   ```javascript
   // ✅ Good - ID columns should be fixed
   { field: 'id', width: 80, minWidth: 80, maxWidth: 80 }
   ```

3. **Use Flex for Content Columns**
   ```javascript
   // ✅ Good - description takes available space
   { field: 'description', flex: 1, minWidth: 200, maxWidth: 600 }
   ```

## 🔑 Column Identification

**Important**: AG Grid identifies columns by their **field names** (or `colId`), **NOT** by numerical indexes.

```javascript
// ✅ Correct: Using field names
gridApi.setColumnVisible('name', false);
columnVisibilityManager.toggleColumn('status');

// ❌ Incorrect: Using indexes
gridApi.setColumnVisible(0, false);  // Wrong!
```

**Why?**
- Field names stay the same when columns are reordered
- Indexes change when columns move
- Persistence uses field names, so it works after page reload

## 🐛 Troubleshooting

### Grid Not Appearing
1. Check browser console for errors
2. Verify all CSS and JS files are loaded
3. Ensure container has height: `style="height: 600px;"`
4. Check that `ag-grid-community.min.js` loads before custom components

### Column Visibility Not Persisting
1. Check browser localStorage (DevTools > Application > Local Storage)
2. Verify templateId is unique and consistent
3. Check browser console for errors
4. Ensure `persistOnChange: true` is set

### Set Filter Not Working
1. Verify `CustomSetFilter` is registered in `components`
2. Check that column has `filter: 'customSetFilter'`
3. Ensure data is loaded before filter initialization
4. Check browser console for errors

### Helper Methods Not Available
1. Ensure helper is initialized: `const gridHelper = new AgGridHelper(...)`
2. Store helper instance: `window.gridHelper = gridHelper`
3. Check helper was initialized successfully: `if (gridHelper.gridApi) { ... }`

### Styling Issues
1. Ensure theme CSS is included
2. Check CSS load order (core CSS before theme CSS)
3. Verify no conflicting CSS rules
4. Check browser DevTools for CSS conflicts

## ✅ Integration Checklist

- [ ] All CSS files included in `{% block head %}`
- [ ] All JS files included before `</body>` or in `{% block extra_js %}`
- [ ] Grid container has height set
- [ ] Theme CSS class matches included theme
- [ ] CustomSetFilter registered in components (or use helper)
- [ ] Column Visibility Manager initialized with unique templateId (or use helper)
- [ ] Data passed correctly from Flask (using `|tojson|safe`)
- [ ] Browser console checked for errors
- [ ] Tested on target browsers

## 🎓 Best Practices

### 1. Use Descriptive Template IDs
```javascript
// Good: Use route name or page identifier
templateId: 'indicator-bank'
templateId: 'data-exploration'
templateId: 'user-management'

// Bad: Generic or duplicate IDs
templateId: 'grid'
templateId: 'table'
```

### 2. Store Helper Instance
```javascript
// Store for later use
window.gridHelper = gridHelper;
window.gridApi = gridApi;
```

### 3. Use Helper Methods
```javascript
// Good: Use helper methods
gridHelper.setRowData(newData);
gridHelper.refresh();

// Avoid: Direct API calls when helper methods exist
gridApi.setGridOption('rowData', newData);
```

### 4. Customize Only What You Need
```javascript
// Good: Override specific defaults
options: {
    paginationPageSize: 100
}

// Avoid: Recreating entire defaultColDef
options: {
    defaultColDef: {
        sortable: true,
        resizable: true,
        // ... all defaults again
    }
}
```

### 5. Always Define `field` in Column Definitions
```javascript
// ✅ Good
{ field: 'name', headerName: 'Name' }

// ❌ Avoid - no identifier
{ headerName: 'Name' }  // AG Grid will auto-generate colId
```

## 📚 Additional Resources

- [AG Grid Community Documentation](https://www.ag-grid.com/javascript-data-grid/)
- [AG Grid Column API](https://www.ag-grid.com/javascript-data-grid/column-api/)
- [AG Grid Filtering](https://www.ag-grid.com/javascript-data-grid/filtering/)

## 🎉 Summary

This AG Grid setup provides:
- ✅ Excel-like Set Filter
- ✅ Column Visibility Manager with persistence
- ✅ Full AG Grid Community features
- ✅ Professional styling
- ✅ Template-specific configurations
- ✅ Centralized helper utility (90% code reduction)
- ✅ Consistent behavior across all templates

Happy coding! 🚀
