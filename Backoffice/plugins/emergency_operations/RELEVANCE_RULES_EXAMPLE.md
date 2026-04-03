# Emergency Operations Plugin - Relevance Rules Usage

The Emergency Operations plugin exposes:

- **Relevance measure**: **Operations Count** (`data-operations-count`) – number of operations after applying filters; use in relevance conditions.
- **Label variables**: **EO1**, **EO2**, **EO3** – for use in section/item labels. When editing a label, type `[` to get suggestions; EO1 (First Emergency Operation), EO2, EO3 appear with metadata and manual variables. At runtime they are replaced by the operation code for the first, second, or third operation in the filtered list.

## How It Works

1. **Data Attribute**: The plugin field automatically updates its `data-operations-count` attribute with the current number of operations after filtering
2. **Real-time Updates**: The count updates automatically when:
   - Operations are loaded from the API
   - Operation type filters are applied
   - No operations are found (count = 0)
   - An error occurs (count = 0)

## Using in Relevance Rules

You can create relevance rules that show/hide other form items based on the number of operations found.

### Example Relevance Rule JSON

```json
{
  "conditions": [
    {
      "item_id": "emergency_operations_field_id",
      "condition_type": "greater_than",
      "value": "3"
    }
  ],
  "operator": "AND"
}
```

### Supported Condition Types

- `greater_than`: Show item when operations count is greater than specified value
- `less_than`: Show item when operations count is less than specified value
- `equals`: Show item when operations count equals specified value
- `not_equals`: Show item when operations count does not equal specified value

### Example Use Cases

1. **Show additional questions only if there are 4+ operations**:
   ```json
   {
     "conditions": [
       {
         "item_id": "emergency_operations_field_id",
         "condition_type": "greater_than",
         "value": "3"
       }
     ],
     "operator": "AND"
   }
   ```

2. **Show emergency contact section only if there are operations**:
   ```json
   {
     "conditions": [
       {
         "item_id": "emergency_operations_field_id",
         "condition_type": "greater_than",
         "value": "0"
       }
     ],
     "operator": "AND"
   }
   ```

3. **Show specific message if no operations found**:
   ```json
   {
     "conditions": [
       {
         "item_id": "emergency_operations_field_id",
         "condition_type": "equals",
         "value": "0"
       }
     ],
     "operator": "AND"
   }
   ```

## Technical Details

- **Data Attribute**: `data-operations-count`
- **Value Type**: String representation of number (e.g., "4", "0")
- **Update Event**: `operationsCountUpdated` (bubbles up the DOM)
- **Field ID**: Use the actual field ID of the emergency operations plugin field

## EO1, EO2, EO3 as label variables

In the form builder, when editing a **section name** or an **item label**, type `[` to open variable suggestions. You will see:

- **Metadata variables** (e.g. Entity Name, Template Name)
- **Manual template variables** (if any)
- **EO1**, **EO2**, **EO3** (from this plugin)

Insert e.g. `[EO1]` in a label; at data entry time it is replaced by the code of the first operation in the filtered list (or empty if none). Same for `[EO2]`, `[EO3]`.

## Notes

- The count reflects the total number of operations after applying all filters (operation types, active/closed status)
- EO1/EO2/EO3 use the same filtered list (after operation types and active/closed filters)
- The count and EO1/EO2/EO3 are updated in real-time as the plugin loads and processes data
- If the plugin fails to load data or no operations are found, count is "0" and EO1/EO2/EO3 are empty
