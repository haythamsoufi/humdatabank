# Multiselect Dropdown Component

A reusable searchable multiselect dropdown component for any data type.

## Features

- **Searchable**: Users can type to filter options by label or sublabel
- **Multiselect**: Multiple items can be selected simultaneously
- **Customizable**: Configurable placeholder text, search behavior, and styling
- **Accessible**: Proper keyboard navigation and screen reader support
- **Responsive**: Works well on different screen sizes
- **Select All/Deselect All**: Quick selection controls

## Usage

### 1. Include the Script

```html
<script src="{{ url_for('static', filename='js/components/multiselect-dropdown.js') }}"></script>
```

### 2. Create a Container

```html
<div>
    <label class="block text-sm font-medium text-gray-700 mb-1">Select Items</label>
    <div id="my-multiselect-container"></div>
</div>
```

### 3. Initialize the Component

```javascript
const multiselect = new MultiselectDropdown({
    containerId: 'my-multiselect-container',
    name: 'my-field',
    placeholder: 'Select items...',
    searchPlaceholder: 'Search items...',
    data: [
        { value: '1', label: 'Item 1', sublabel: 'Optional sublabel' },
        { value: '2', label: 'Item 2' },
        { value: '3', label: 'Item 3', sublabel: 'Another sublabel' }
    ],
    selectedValues: ['1', '3'], // Pre-selected values
    onSelectionChange: (selectedValues, selectedItems) => {
        console.log('Selection changed:', selectedValues, selectedItems);
    }
});
```

## Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `containerId` | string | **required** | ID of the container element |
| `name` | string | `'multiselect'` | Name attribute for form inputs |
| `placeholder` | string | `'Select items...'` | Placeholder text when no items selected |
| `searchPlaceholder` | string | `'Search items...'` | Placeholder text for search input |
| `data` | array | `[]` | Array of items with `value`, `label`, and optional `sublabel` |
| `selectedValues` | array | `[]` | Array of pre-selected values |
| `onSelectionChange` | function | `null` | Callback when selection changes |
| `showSelectAll` | boolean | `true` | Show Select All/Deselect All buttons |
| `maxHeight` | string | `'240px'` | Maximum height of dropdown |
| `searchable` | boolean | `true` | Enable search functionality |

## Data Format

Each item in the `data` array should have:

```javascript
{
    value: 'unique-value',     // Required: unique identifier
    label: 'Display Name',     // Required: main display text
    sublabel: 'Optional Info'  // Optional: secondary display text
}
```

## Public Methods

### `getSelectedValues()`
Returns an array of selected values.

```javascript
const selectedValues = multiselect.getSelectedValues();
// Returns: ['1', '3']
```

### `getSelectedItems()`
Returns an array of selected item objects.

```javascript
const selectedItems = multiselect.getSelectedItems();
// Returns: [{ value: '1', label: 'Item 1' }, { value: '3', label: 'Item 3' }]
```

### `setSelectedValues(values)`
Sets the selected values programmatically.

```javascript
multiselect.setSelectedValues(['2', '3']);
```

### `updateData(newData)`
Updates the dropdown data.

```javascript
multiselect.updateData([
    { value: 'a', label: 'New Item A' },
    { value: 'b', label: 'New Item B' }
]);
```

### `destroy()`
Cleans up the component and removes all event listeners.

```javascript
multiselect.destroy();
```

## Form Integration

The component automatically creates hidden input elements with the specified `name` attribute. When used in a form, the selected values will be submitted as multiple values with the same name.

```html
<!-- Generated hidden inputs -->
<input type="checkbox" name="my-field" value="1" checked>
<input type="checkbox" name="my-field" value="3" checked>
```

## Styling

The component uses Tailwind CSS classes by default. You can customize the appearance by overriding these CSS classes:

- `.multiselect-toggle` - The main button
- `.multiselect-dropdown` - The dropdown container
- `.multiselect-option` - Individual option items
- `.multiselect-checkbox` - Checkboxes
- `.multiselect-search` - Search input

## Example: User Selection

```javascript
// Example from audit trail template
const userMultiselect = new MultiselectDropdown({
    containerId: 'user-multiselect-container',
    name: 'user',
    placeholder: 'Select users...',
    searchPlaceholder: 'Search users...',
    data: [
        { value: 'john@example.com', label: 'John Doe', sublabel: 'john@example.com' },
        { value: 'jane@example.com', label: 'Jane Smith', sublabel: 'jane@example.com' }
    ],
    selectedValues: ['john@example.com']
});
```

## Browser Support

- Modern browsers (Chrome, Firefox, Safari, Edge)
- IE11+ (with polyfills for modern JavaScript features)

## Dependencies

- No external dependencies
- Uses modern JavaScript (ES6+)
- Designed for Tailwind CSS styling
