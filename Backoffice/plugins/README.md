# Plugin System Documentation

## Overview

The NGO Databank supports a plugin system that allows developers to extend the application with custom field types, functionality, and integrations.

> **Security notice:** Plugins execute in the host process with full application privileges (database, file system, network, secrets). There is no OS-level sandbox. Only install plugins from trusted sources.

## Plugin Directory Structure

All plugins must be placed in the `Backoffice/plugins/` directory and follow this structure:

```
Backoffice/plugins/
├── plugin_name/
│   ├── plugin.py              # Main plugin class and field type definitions
│   ├── routes.py              # Plugin-specific routes and API endpoints
│   ├── static/                # Static assets (JS, CSS, images)
│   │   ├── js/               # JavaScript files
│   │   ├── css/              # CSS files
│   │   └── images/           # Image files
│   └── templates/             # HTML templates
│       ├── builder.html       # Form builder configuration template
│       └── field.html         # Entry form field rendering template
```

## Required Files

### 1. `plugin.py`
- Must contain a class that inherits from `BasePlugin`
- Must define custom field types that inherit from `BaseFieldType`
- Must implement all required methods and properties

### 2. `routes.py`
- Must define a `create_blueprint()` function that returns a Flask Blueprint
- Can contain plugin-specific API endpoints and routes

### 3. Static Assets
- **JavaScript files**: Must be in `static/js/` directory
- **CSS files**: Must be in `static/css/` directory
- **Images**: Must be in `static/images/` directory

### 4. Templates
- **`builder.html`**: Configuration interface for form builders
- **`field.html`**: Field rendering for entry forms

## Plugin Configuration

### Form Builder Configuration
```python
def get_form_builder_config(self) -> Dict[str, Any]:
    return {
        'title': 'Field Configuration Title',
        'icon': 'fas fa-icon-name',
        'custom_template': 'plugin_name/builder.html',  # Optional: custom template
        'fields': [
            # Configuration field definitions
        ],
        'validation_rules': True,
        'condition_types': True
    }
```

### Entry Form Configuration
```python
def get_entry_form_config(self) -> Dict[str, Any]:
    return {
        'template': 'plugins/plugin_name/field.html',
        'js_module': 'JavaScriptModuleName',
        'css_files': ['plugin_name/static/css/style.css'],
        'data_attributes': ['data-attr1', 'data-attr2']
    }
```

## File Paths

### Static File URLs
- **JavaScript**: `/plugins/static/plugin_name/js/filename.js`
- **CSS**: `/plugins/static/plugin_name/css/filename.css`
- **Images**: `/plugins/static/plugin_name/images/filename.png`

### Template Paths
- **Builder template**: `plugin_name/builder.html`
- **Field template**: `plugins/plugin_name/field.html`

## Example Plugin

See `interactive_map/` for a complete example plugin implementation.

## Best Practices

1. **Self-contained**: All plugin files should be within the plugin directory
2. **Naming**: Use descriptive, unique names for plugins
3. **Dependencies**: Minimize external dependencies
4. **Error handling**: Implement proper error handling and validation
5. **Documentation**: Include clear documentation for configuration options

## Security Considerations

1. **File validation**: Validate all uploaded files and user inputs
2. **Access control**: Implement proper permission checks
3. **Sanitization**: Sanitize all user-generated content
4. **Rate limiting**: Implement rate limiting for API endpoints

## Testing

1. Test plugin installation and uninstallation
2. Test field type configuration in form builder
3. Test field rendering in entry forms
4. Test data validation and submission
5. Test error handling and edge cases
