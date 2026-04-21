# Backoffice/app/utils/schema_validation.py

import json
import logging
from typing import Dict, Any, List, Optional, Union
try:
    from jsonschema import validate, ValidationError, SchemaError
    from jsonschema.validators import validator_for
    JSONSCHEMA_AVAILABLE = True
except Exception as e:  # ModuleNotFoundError or other import issues
    logging.getLogger(__name__).debug("jsonschema not available: %s", e)
    validate = None
    ValidationError = Exception
    SchemaError = Exception
    validator_for = None
    JSONSCHEMA_AVAILABLE = False
import re

class SchemaValidationError(Exception):
    """Custom exception for schema validation errors."""
    def __init__(self, message: str, errors: List[str] = None):
        super().__init__(message)
        self.errors = errors or []

def validate_plugin_config(config: Dict[str, Any], schema: Dict[str, Any]) -> bool:
    """
    Validate plugin configuration against a JSON schema.

    Args:
        config: Configuration dictionary to validate
        schema: JSON schema to validate against

    Returns:
        True if valid, raises SchemaValidationError if invalid

    Raises:
        SchemaValidationError: If validation fails
    """
    if not JSONSCHEMA_AVAILABLE:
        # Best-effort fallback: basic shape check
        if not isinstance(config, dict) or not isinstance(schema, dict):
            raise SchemaValidationError("Invalid config or schema type without jsonschema installed")
        return True
    try:
        validate(instance=config, schema=schema)
        return True
    except ValidationError as e:
        errors = []
        # Create validator instance and get all errors
        validator = validator_for(schema)(schema)
        for error in validator.iter_errors(config):
            errors.append(f"{'.'.join(str(p) for p in error.path)}: {error.message}")
        raise SchemaValidationError(f"Plugin configuration validation failed: {getattr(e, 'message', str(e))}", errors)
    except SchemaError as e:
        raise SchemaValidationError(f"Invalid schema definition: {getattr(e, 'message', str(e))}")

def validate_plugin_data(data: Dict[str, Any], schema: Dict[str, Any]) -> bool:
    """
    Validate plugin field data against a JSON schema.

    Args:
        data: Field data dictionary to validate
        schema: JSON schema to validate against

    Returns:
        True if valid, raises SchemaValidationError if invalid

    Raises:
        SchemaValidationError: If validation fails
    """
    if not JSONSCHEMA_AVAILABLE:
        if not isinstance(data, dict) or not isinstance(schema, dict):
            raise SchemaValidationError("Invalid data or schema type without jsonschema installed")
        return True
    try:
        validate(instance=data, schema=schema)
        return True
    except ValidationError as e:
        errors = []
        # Create validator instance and get all errors
        validator = validator_for(schema)(schema)
        for error in validator.iter_errors(data):
            errors.append(f"{'.'.join(str(p) for p in error.path)}: {error.message}")
        raise SchemaValidationError(f"Plugin data validation failed: {getattr(e, 'message', str(e))}", errors)
    except SchemaError as e:
        raise SchemaValidationError(f"Invalid schema definition: {getattr(e, 'message', str(e))}")

def sanitize_plugin_data(data: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize plugin data by removing invalid fields and normalizing values.
    Also adds default values for required fields that are missing.

    Args:
        data: Raw plugin data
        schema: JSON schema defining valid structure

    Returns:
        Sanitized data dictionary
    """
    if not isinstance(data, dict):
        data = {}

    sanitized = {}

    # Get required fields from schema
    required_fields = schema.get('required', [])

    # Only include fields that are defined in the schema
    if 'properties' in schema:
        for field_name, field_schema in schema['properties'].items():
            # Check if field exists in data or is required
            if field_name in data:
                value = data[field_name]
            elif field_name in required_fields:
                # Field is required but missing - try to create a default
                value = _create_default_value(field_schema)
                if value is None:
                    # Can't create default, skip this field (will fail validation)
                    continue
            else:
                # Field not in data and not required, skip it
                continue

            # Apply type conversion if specified
            if 'type' in field_schema:
                try:
                    if field_schema['type'] == 'string':
                        value = str(value) if value is not None else ''
                    elif field_schema['type'] == 'number':
                        value = float(value) if value is not None else 0.0
                    elif field_schema['type'] == 'integer':
                        value = int(value) if value is not None else 0
                    elif field_schema['type'] == 'boolean':
                        value = bool(value) if value is not None else False
                    elif field_schema['type'] == 'array':
                        value = list(value) if value is not None else []
                    elif field_schema['type'] == 'object':
                        # Recursively sanitize nested objects
                        if isinstance(value, dict) and 'properties' in field_schema:
                            value = sanitize_plugin_data(value, field_schema)
                except (ValueError, TypeError):
                    # Use default value if conversion fails
                    if 'default' in field_schema:
                        value = field_schema['default']
                    else:
                        # Try to create a default
                        default_value = _create_default_value(field_schema)
                        if default_value is not None:
                            value = default_value
                        else:
                            continue

                # Apply constraints
                if 'type' in field_schema and field_schema['type'] == 'string':
                    if 'maxLength' in field_schema and len(str(value)) > field_schema['maxLength']:
                        value = str(value)[:field_schema['maxLength']]

                    # Sanitize HTML/scripts from strings
                    if isinstance(value, str):
                        value = sanitize_string(value)

                sanitized[field_name] = value

    return sanitized

def _create_default_value(field_schema: Dict[str, Any]) -> Any:
    """
    Create a default value for a field based on its schema.

    Args:
        field_schema: Field schema definition

    Returns:
        Default value or None if cannot be created
    """
    # Check if schema has a default
    if 'default' in field_schema:
        return field_schema['default']

    # Create default based on type
    field_type = field_schema.get('type')
    if field_type == 'string':
        return ''
    elif field_type == 'number':
        return 0.0
    elif field_type == 'integer':
        return 0
    elif field_type == 'boolean':
        return False
    elif field_type == 'array':
        return []
    elif field_type == 'object':
        # For objects, create a dict with defaults for required properties
        if 'properties' in field_schema:
            obj_default = {}
            required_props = field_schema.get('required', [])
            for prop_name, prop_schema in field_schema['properties'].items():
                if prop_name in required_props:
                    prop_default = _create_default_value(prop_schema)
                    if prop_default is not None:
                        obj_default[prop_name] = prop_default
            return obj_default if obj_default else {}

    return None

def sanitize_string(value: str) -> str:
    """
    Sanitize string values by removing potentially dangerous content.

    Args:
        value: String to sanitize

    Returns:
        Sanitized string
    """
    if not isinstance(value, str):
        return str(value) if value is not None else ''

    # Remove HTML tags and scripts
    value = re.sub(r'<script[^>]*>.*?</script>', '', value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r'<[^>]*>', '', value)

    # Remove potentially dangerous JavaScript
    value = re.sub(r'javascript:', '', value, flags=re.IGNORECASE)
    value = re.sub(r'on\w+\s*=', '', value, flags=re.IGNORECASE)

    # Remove null bytes and control characters
    value = value.replace('\x00', '')
    value = ''.join(char for char in value if ord(char) >= 32 or char in '\n\r\t')

    return value.strip()

def get_plugin_schema_version(data: Dict[str, Any]) -> Optional[str]:
    """
    Extract schema version from plugin data.

    Args:
        data: Plugin data dictionary

    Returns:
        Schema version string or None if not found
    """
    return data.get('_schema_version') or data.get('schema_version')

def set_plugin_schema_version(data: Dict[str, Any], version: str) -> Dict[str, Any]:
    """
    Set schema version in plugin data.

    Args:
        data: Plugin data dictionary
        version: Schema version string

    Returns:
        Updated data dictionary
    """
    data['_schema_version'] = version
    return data

SUPPORTED_PLUGIN_SCHEMA_VERSIONS = ["1.0.0", "1.1.0"]

_MIGRATION_HANDLERS = {}


def _register_migration(from_version: str, to_version: str):
    def decorator(func):
        _MIGRATION_HANDLERS[(from_version, to_version)] = func
        return func
    return decorator


@_register_migration("1.0.0", "1.1.0")
def _migrate_1_0_0_to_1_1_0(data: Dict[str, Any]) -> Dict[str, Any]:
    """Add structured defaults for map markers/center introduced in v1.1.0."""
    migrated = data.copy()

    markers = migrated.get('markers')
    if not isinstance(markers, list):
        migrated['markers'] = []

    map_center = migrated.get('map_center')
    if not isinstance(map_center, dict):
        migrated['map_center'] = {'lat': 0, 'lng': 0, 'zoom': 1}
    else:
        migrated['map_center'].setdefault('lat', 0)
        migrated['map_center'].setdefault('lng', 0)
        migrated['map_center'].setdefault('zoom', 1)

    metadata = migrated.get('metadata')
    if metadata is None or not isinstance(metadata, dict):
        migrated['metadata'] = {}

    return migrated


def _normalize_schema_version(version: Optional[str]) -> Optional[str]:
    if not version:
        return None
    version = str(version).strip()
    return version or None


def migrate_plugin_data(data: Dict[str, Any], from_version: str, to_version: str) -> Dict[str, Any]:
    """
    Migrate plugin data from one schema version to another.

    Args:
        data: Plugin data dictionary
        from_version: Current schema version
        to_version: Target schema version

    Returns:
        Migrated data dictionary
    """
    normalized_from = _normalize_schema_version(from_version) or SUPPORTED_PLUGIN_SCHEMA_VERSIONS[0]
    normalized_to = _normalize_schema_version(to_version) or SUPPORTED_PLUGIN_SCHEMA_VERSIONS[-1]

    if normalized_from not in SUPPORTED_PLUGIN_SCHEMA_VERSIONS:
        raise SchemaValidationError(f"Unsupported source schema version: {normalized_from}")
    if normalized_to not in SUPPORTED_PLUGIN_SCHEMA_VERSIONS:
        raise SchemaValidationError(f"Unsupported target schema version: {normalized_to}")

    from_index = SUPPORTED_PLUGIN_SCHEMA_VERSIONS.index(normalized_from)
    to_index = SUPPORTED_PLUGIN_SCHEMA_VERSIONS.index(normalized_to)

    if from_index > to_index:
        raise SchemaValidationError("Schema downgrades are not supported")

    migrated_data = data.copy()

    for step_index in range(from_index, to_index):
        step_from = SUPPORTED_PLUGIN_SCHEMA_VERSIONS[step_index]
        step_to = SUPPORTED_PLUGIN_SCHEMA_VERSIONS[step_index + 1]
        handler = _MIGRATION_HANDLERS.get((step_from, step_to))
        if not handler:
            raise SchemaValidationError(f"No migration path from {step_from} to {step_to}")
        migrated_data = handler(migrated_data)

    migrated_data = set_plugin_schema_version(migrated_data, normalized_to)
    return migrated_data
