# Backoffice/plugins/interactive_map/schemas.py

# JSON Schema for Interactive Map Plugin Configuration
INTERACTIVE_MAP_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "map_type": {
            "type": "string",
            "enum": ["mapbox", "openstreetmap", "google_maps", "custom_tiles"],
            "default": "mapbox",
            "description": "Type of map provider to use"
        },
        "default_zoom": {
            "type": "integer",
            "minimum": 1,
            "maximum": 22,
            "default": 10,
            "description": "Default zoom level for the map"
        },
        "allow_markers": {
            "type": "boolean",
            "default": True,
            "description": "Whether users can add markers to the map"
        },
        "max_markers": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 10,
            "description": "Maximum number of markers allowed"
        },
        "map_center_lat": {
            "type": "number",
            "minimum": -90,
            "maximum": 90,
            "default": 0,
            "description": "Default center latitude"
        },
        "map_center_lng": {
            "type": "number",
            "minimum": -180,
            "maximum": 180,
            "default": 0,
            "description": "Default center longitude"
        },
        "allow_drawing": {
            "type": "boolean",
            "default": False,
            "description": "Whether users can draw shapes on the map"
        },
        "allowed_geometry_types": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["Point", "LineString", "Polygon", "MultiPolygon"]
            },
            "default": ["Point"],
            "minItems": 1,
            "description": "Types of geometry allowed for drawing"
        },
        "coordinate_precision": {
            "type": "integer",
            "minimum": 4,
            "maximum": 8,
            "default": 6,
            "description": "Decimal places for coordinate precision"
        },
        "show_search_box": {
            "type": "boolean",
            "default": True,
            "description": "Whether to show the location search box"
        },
        "show_coordinates": {
            "type": "boolean",
            "default": True,
            "description": "Whether to display coordinate information"
        },
        "allow_multiple_markers": {
            "type": "boolean",
            "default": True,
            "description": "Whether to allow multiple markers"
        },
        "min_markers": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "default": 0,
            "description": "Minimum number of markers required"
        },
        "map_height": {
            "type": "string",
            "default": "400px",
            "description": "Height of the map container"
        },
        "map_provider": {
            "type": "string",
            "enum": ["openstreetmap", "google_maps", "mapbox", "leaflet"],
            "default": "mapbox",
            "description": "Map provider to use (legacy field name)"
        },
        "map_bounds": {
            "type": "object",
            "properties": {
                "north": {"type": "number", "minimum": -90, "maximum": 90},
                "south": {"type": "number", "minimum": -90, "maximum": 90},
                "east": {"type": "number", "minimum": -180, "maximum": 180},
                "west": {"type": "number", "minimum": -180, "maximum": 180}
            },
            "additionalProperties": False,
            "description": "Geographic bounds to restrict map area"
        },
        "marker_properties_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "maxLength": 100},
                "description": {"type": "string", "maxLength": 500},
                "category": {"type": "string", "maxLength": 50}
            },
            "additionalProperties": False,
            "description": "Schema for marker properties"
        },
        "style_rules": {
            "type": "object",
            "properties": {
                "marker_color": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                "marker_size": {"type": "integer", "minimum": 8, "maximum": 32},
                "line_color": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                "line_width": {"type": "integer", "minimum": 1, "maximum": 10},
                "fill_color": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                "fill_opacity": {"type": "number", "minimum": 0, "maximum": 1}
            },
            "additionalProperties": False,
            "description": "Visual styling rules for map elements"
        },
        "localization": {
            "type": "object",
            "properties": {
                "add_marker": {"type": "string", "maxLength": 50},
                "remove_marker": {"type": "string", "maxLength": 50},
                "draw_shape": {"type": "string", "maxLength": 50},
                "clear_all": {"type": "string", "maxLength": 50},
                "coordinates": {"type": "string", "maxLength": 50}
            },
            "additionalProperties": False,
            "description": "Localized labels for UI elements"
        }
    },
    "required": ["map_type", "default_zoom"],
    "additionalProperties": False
}

# JSON Schema for Interactive Map Field Data
INTERACTIVE_MAP_DATA_SCHEMA = {
    "type": "object",
    "properties": {
        "_schema_version": {
            "type": "string",
            "pattern": "^\\d+\\.\\d+\\.\\d+$",
            "description": "Schema version for data migration"
        },
        "map_center": {
            "type": "object",
            "properties": {
                "lat": {"type": "number", "minimum": -90, "maximum": 90},
                "lng": {"type": "number", "minimum": -180, "maximum": 180},
                "zoom": {"type": "integer", "minimum": 1, "maximum": 22}
            },
            "required": ["lat", "lng", "zoom"],
            "additionalProperties": False
        },
        "markers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "maxLength": 50},
                    "lat": {"type": "number", "minimum": -90, "maximum": 90},
                    "lng": {"type": "number", "minimum": -180, "maximum": 180},
                    "title": {"type": "string", "maxLength": 100},
                    "description": {"type": "string", "maxLength": 500},
                    "category": {"type": "string", "maxLength": 50}
                },
                "required": ["id", "lat", "lng"],
                "additionalProperties": False
            },
            "maxItems": 100
        },
        "shapes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "maxLength": 50},
                    "type": {"type": "string", "enum": ["Point", "LineString", "Polygon", "MultiPolygon"]},
                    "coordinates": {
                        "oneOf": [
                            {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                            {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
                            {"type": "array", "items": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}}},
                            {"type": "array", "items": {"type": "array", "items": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}}}}
                        ]
                    },
                    "properties": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "maxLength": 100},
                            "description": {"type": "string", "maxLength": 500},
                            "color": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                            "opacity": {"type": "number", "minimum": 0, "maximum": 1}
                        },
                        "additionalProperties": False
                    },
                },
                "required": ["id", "type", "coordinates"],
                "additionalProperties": False
            },
            "maxItems": 50
        },
        "metadata": {
            "type": "object",
            "properties": {
                "total_markers": {"type": "integer", "minimum": 0},
                "total_shapes": {"type": "integer", "minimum": 0},
                "last_modified": {"type": "string", "format": "date-time"},
                "user_id": {"type": "string", "maxLength": 50},
                "session_id": {"type": "string", "maxLength": 100}
            },
            "additionalProperties": False
        }
    },
    "required": [],
    "additionalProperties": False
}

# Default configuration values
DEFAULT_INTERACTIVE_MAP_CONFIG = {
    "map_type": "openstreetmap",
    "default_zoom": 10,
    "allow_markers": True,
    "max_markers": 10,
    "map_center_lat": 0,
    "map_center_lng": 0,
    "allow_drawing": False,
    "allowed_geometry_types": ["Point"],
    "coordinate_precision": 6,
    "show_search_box": True,
    "show_coordinates": True,
    "allow_multiple_markers": True,
    "min_markers": 0,
    "map_height": "400px",
    # Legacy field names for backward compatibility
    "map_provider": "openstreetmap",
    "default_lat": 0,
    "default_lng": 0,
    "marker_properties_schema": {
        "title": {"type": "string", "maxLength": 100},
        "description": {"type": "string", "maxLength": 500},
        "category": {"type": "string", "maxLength": 50}
    },
    "style_rules": {
        "marker_color": "#ff4444",
        "marker_size": 16,
        "line_color": "#4444ff",
        "line_width": 2,
        "fill_color": "#4444ff",
        "fill_opacity": 0.3
    },
    "localization": {
        "add_marker": "Add Marker",
        "remove_marker": "Remove Marker",
        "draw_shape": "Draw Shape",
        "clear_all": "Clear All",
        "coordinates": "Coordinates"
    }
}

# Default data values
DEFAULT_INTERACTIVE_MAP_DATA = {
    "_schema_version": "1.0.0",
    "map_center": {
        "lat": 0,
        "lng": 0,
        "zoom": 10
    },
    "markers": [],
    "shapes": [],
    "metadata": {
        "total_markers": 0,
        "total_shapes": 0,
        "last_modified": None,
        "user_id": None,
        "session_id": None
    }
}
