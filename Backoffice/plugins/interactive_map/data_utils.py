# Backoffice/plugins/interactive_map/data_utils.py

import json
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)
from typing import Dict, Any, List, Optional, Tuple
import re

# Optional imports for geometry validation
try:
    from shapely.geometry import Point, LineString, Polygon, MultiPolygon, shape
    from shapely.validation import explain_validity
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False
    # Create dummy classes for type hinting
    Point = LineString = Polygon = MultiPolygon = shape = None

def normalize_coordinates(lat: float, lng: float, precision: int = 6) -> Tuple[float, float]:
    """
    Normalize coordinates to specified precision and validate bounds.

    Args:
        lat: Latitude value
        lng: Longitude value
        precision: Decimal places for precision

    Returns:
        Tuple of (normalized_lat, normalized_lng)

    Raises:
        ValueError: If coordinates are out of bounds
    """
    # Validate bounds
    if not -90 <= lat <= 90:
        raise ValueError(f"Latitude {lat} is out of bounds (-90 to 90)")
    if not -180 <= lng <= 180:
        raise ValueError(f"Longitude {lng} is out of bounds (-180 to 180)")

    # Round to specified precision
    lat = round(lat, precision)
    lng = round(lng, precision)

    return lat, lng

def validate_geometry(coordinates: List, geometry_type: str) -> bool:
    """
    Validate geometry coordinates using Shapely if available, basic validation otherwise.

    Args:
        coordinates: Geometry coordinates
        geometry_type: Type of geometry (Point, LineString, Polygon, MultiPolygon)

    Returns:
        True if valid, False otherwise
    """
    if not SHAPELY_AVAILABLE:
        # Basic validation without shapely
        return _validate_geometry_basic(coordinates, geometry_type)

    try:
        if geometry_type == "Point":
            if len(coordinates) != 2:
                return False
            geom = Point(coordinates)
        elif geometry_type == "LineString":
            if len(coordinates) < 2:
                return False
            geom = LineString(coordinates)
        elif geometry_type == "Polygon":
            if len(coordinates) < 3:
                return False
            geom = Polygon(coordinates[0], coordinates[1:])
        elif geometry_type == "MultiPolygon":
            if not coordinates:
                return False
            geom = MultiPolygon([Polygon(poly[0], poly[1:]) for poly in coordinates])
        else:
            return False

        # Check if geometry is valid
        if not geom.is_valid:
            return False

        # Check for self-intersections in polygons
        if geometry_type in ["Polygon", "MultiPolygon"]:
            if not geom.is_simple:
                return False

        return True
    except Exception as e:
        logger.debug("validate_geometry (Shapely) failed: %s", e)
        return False

def _validate_geometry_basic(coordinates: List, geometry_type: str) -> bool:
    """
    Basic geometry validation without shapely.

    Args:
        coordinates: Geometry coordinates
        geometry_type: Type of geometry

    Returns:
        True if basic validation passes
    """
    try:
        if geometry_type == "Point":
            if len(coordinates) != 2:
                return False
            # Check if coordinates are valid numbers
            lat, lng = coordinates
            return isinstance(lat, (int, float)) and isinstance(lng, (int, float))

        elif geometry_type == "LineString":
            if len(coordinates) < 2:
                return False
            # Check all coordinate pairs
            for coord in coordinates:
                if len(coord) != 2 or not all(isinstance(x, (int, float)) for x in coord):
                    return False
            return True

        elif geometry_type == "Polygon":
            if not coordinates or len(coordinates[0]) < 3:
                return False
            # Check exterior ring
            for coord in coordinates[0]:
                if len(coord) != 2 or not all(isinstance(x, (int, float)) for x in coord):
                    return False
            return True

        elif geometry_type == "MultiPolygon":
            if not coordinates:
                return False
            # Basic check for each polygon
            for poly in coordinates:
                if not poly or len(poly[0]) < 3:
                    return False
            return True

        return False
    except Exception as e:
        logger.debug("_validate_geometry_basic failed: %s", e)
        return False

def normalize_marker_data(marker: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize and validate marker data.

    Args:
        marker: Raw marker data
        config: Plugin configuration

    Returns:
        Normalized marker data
    """
    normalized = {}

    # Required fields
    if 'lat' not in marker or 'lng' not in marker:
        raise ValueError("Marker must have lat and lng coordinates")

    # Normalize coordinates
    precision = config.get('coordinate_precision', 6)
    lat, lng = normalize_coordinates(marker['lat'], marker['lng'], precision)
    normalized['lat'] = lat
    normalized['lng'] = lng

    # Generate ID if not present
    normalized['id'] = marker.get('id') or str(uuid.uuid4())

    # Validate and normalize properties
    properties_schema = config.get('marker_properties_schema', {})
    if 'properties' in properties_schema:
        for prop_name, prop_schema in properties_schema['properties'].items():
            if prop_name in marker:
                value = marker[prop_name]

                # Type validation
                if prop_schema.get('type') == 'string':
                    if isinstance(value, str):
                        max_length = prop_schema.get('maxLength', 1000)
                        value = value[:max_length]
                    else:
                        value = str(value)[:max_length]

                # Enum validation
                if 'enum' in prop_schema:
                    if value not in prop_schema['enum']:
                        value = prop_schema['enum'][0]  # Use first valid value

                normalized[prop_name] = value

    # Timestamps
    now = datetime.utcnow().isoformat()
    normalized['created_at'] = marker.get('created_at') or now
    normalized['updated_at'] = now

    return normalized

def normalize_shape_data(shape_data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize and validate shape data.

    Args:
        shape_data: Raw shape data
        config: Plugin configuration

    Returns:
        Normalized shape data
    """
    normalized = {}

    # Required fields
    if 'type' not in shape_data or 'coordinates' not in shape_data:
        raise ValueError("Shape must have type and coordinates")

    geometry_type = shape_data['type']
    if geometry_type not in config.get('allowed_geometry_types', ['Point']):
        raise ValueError(f"Geometry type {geometry_type} not allowed")

    normalized['type'] = geometry_type

    # Validate coordinates
    coordinates = shape_data['coordinates']
    if not validate_geometry(coordinates, geometry_type):
        raise ValueError(f"Invalid coordinates for {geometry_type}")

    # Normalize coordinates precision
    precision = config.get('coordinate_precision', 6)
    normalized['coordinates'] = normalize_coordinate_array(coordinates, precision)

    # Generate ID if not present
    normalized['id'] = shape_data.get('id') or str(uuid.uuid4())

    # Properties
    if 'properties' in shape_data:
        normalized['properties'] = {}
        for key, value in shape_data['properties'].items():
            if isinstance(value, str):
                # Sanitize string values
                value = sanitize_string(value)
                if len(value) <= 500:  # Reasonable limit
                    normalized['properties'][key] = value
            elif isinstance(value, (int, float, bool)):
                normalized['properties'][key] = value

    # Timestamps
    now = datetime.utcnow().isoformat()
    normalized['created_at'] = shape_data.get('created_at') or now
    normalized['updated_at'] = now

    return normalized

def normalize_coordinate_array(coords: List, precision: int) -> List:
    """
    Recursively normalize coordinate arrays to specified precision.

    Args:
        coords: Coordinate array (can be nested)
        precision: Decimal places for precision

    Returns:
        Normalized coordinate array
    """
    if isinstance(coords[0], (int, float)):
        # Leaf coordinate pair
        return [round(coords[0], precision), round(coords[1], precision)]
    else:
        # Nested array
        return [normalize_coordinate_array(coord, precision) for coord in coords]

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

def normalize_map_data(data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize and validate complete map data.

    Args:
        data: Raw map data
        config: Plugin configuration

    Returns:
        Normalized map data
    """
    normalized = {}

    # Schema version
    normalized['_schema_version'] = '1.0.0'

    # Map center
    if 'map_center' in data:
        center = data['map_center']
        precision = config.get('coordinate_precision', 6)
        lat, lng = normalize_coordinates(center.get('lat', 0), center.get('lng', 0), precision)
        normalized['map_center'] = {
            'lat': lat,
            'lng': lng,
            'zoom': max(1, min(22, center.get('zoom', config.get('default_zoom', 10))))
        }
    else:
        # Use default center from config
        normalized['map_center'] = {
            'lat': config.get('map_center_lat', 0),
            'lng': config.get('map_center_lng', 0),
            'zoom': config.get('default_zoom', 10)
        }

    # Markers
    if config.get('allow_markers', True):
        markers = data.get('markers', [])
        max_markers = config.get('max_markers', 10)

        normalized['markers'] = []
        for marker in markers[:max_markers]:
            try:
                normalized_marker = normalize_marker_data(marker, config)
                normalized['markers'].append(normalized_marker)
            except ValueError as e:
                # Log error but continue processing other markers
                logger.warning("Invalid marker data: %s", e)
                continue

    # Shapes
    if config.get('allow_drawing', False):
        shapes = data.get('shapes', [])
        max_shapes = config.get('max_shapes', 50)

        normalized['shapes'] = []
        for shape_data in shapes[:max_shapes]:
            try:
                normalized_shape = normalize_shape_data(shape_data, config)
                normalized['shapes'].append(normalized_shape)
            except ValueError as e:
                # Log error but continue processing other shapes
                logger.warning("Invalid shape data: %s", e)
                continue

    # Metadata
    normalized['metadata'] = {
        'total_markers': len(normalized.get('markers', [])),
        'total_shapes': len(normalized.get('shapes', [])),
        'last_modified': datetime.utcnow().isoformat(),
        'user_id': data.get('metadata', {}).get('user_id'),
        'session_id': data.get('metadata', {}).get('session_id')
    }

    return normalized

def validate_map_bounds(coordinates: List, bounds: Dict[str, float]) -> bool:
    """
    Check if coordinates are within specified map bounds.

    Args:
        coordinates: Coordinates to check
        bounds: Map bounds {north, south, east, west}

    Returns:
        True if within bounds, False otherwise
    """
    if not bounds:
        return True

    def check_point(lat: float, lng: float) -> bool:
        return (bounds['south'] <= lat <= bounds['north'] and
                bounds['west'] <= lng <= bounds['east'])

    def check_coordinate_array(coords: List) -> bool:
        if isinstance(coords[0], (int, float)):
            return check_point(coords[0], coords[1])
        else:
            return all(check_coordinate_array(coord) for coord in coords)

    return check_coordinate_array(coordinates)

def calculate_map_metrics(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate useful metrics from map data.

    Args:
        data: Normalized map data

    Returns:
        Dictionary of calculated metrics
    """
    metrics = {}

    # Marker metrics
    markers = data.get('markers', [])
    metrics['total_markers'] = len(markers)
    metrics['marker_categories'] = {}
    for marker in markers:
        category = marker.get('category', 'unknown')
        metrics['marker_categories'][category] = metrics['marker_categories'].get(category, 0) + 1

    # Shape metrics
    shapes = data.get('shapes', [])
    metrics['total_shapes'] = len(shapes)
    metrics['shape_types'] = {}
    for shape_data in shapes:
        shape_type = shape_data.get('type', 'unknown')
        metrics['shape_types'][shape_type] = metrics['shape_types'].get(shape_type, 0) + 1

    # Coverage area (for polygons)
    total_area = 0
    if SHAPELY_AVAILABLE:
        for shape_data in shapes:
            if shape_data.get('type') == 'Polygon':
                try:
                    coords = shape_data['coordinates']
                    if coords and len(coords) > 0:
                        polygon = Polygon(coords[0], coords[1:])
                        # Approximate area in square degrees (very rough)
                        total_area += polygon.area
                except Exception as e:
                    logger.debug("Polygon area calc failed: %s", e)

    metrics['approximate_coverage_area'] = total_area

    return metrics


# ===== Activity/Display helpers for plugin integration =====

def summarize_map_payload_for_display(value: Dict[str, Any]) -> str:
    """
    Produce a concise human-readable summary of an interactive map payload for activity display.
    Example: "Markers: 3 (default: 2, health: 1); Shapes: 0"
    """
    try:
        markers = value.get('markers', []) if isinstance(value.get('markers'), list) else []
        shapes = value.get('shapes', []) if isinstance(value.get('shapes'), list) else []
        marker_count = len(markers)
        shape_count = len(shapes)

        # Summarize marker categories
        category_counts: Dict[str, int] = {}
        for m in markers:
            if isinstance(m, dict):
                cat = m.get('category', 'default')
                category_counts[cat] = category_counts.get(cat, 0) + 1

        if category_counts:
            # Show up to 3 categories
            items = list(category_counts.items())[:3]
            summary_parts = [f"{k}: {v}" for k, v in items]
            if len(category_counts) > 3:
                summary_parts.append(f"+{len(category_counts)-3} more")
            categories_summary = f" ({', '.join(summary_parts)})"
        else:
            categories_summary = ''

        return f"Markers: {marker_count}{categories_summary}; Shapes: {shape_count}"
    except Exception as e:
        logger.debug("summarize_map_payload_for_display failed: %s", e)
        return ""


def compute_marker_changes_for_activity(old_value_str: Any, new_value_str: Any, field_name: str, form_item_id: Any) -> List[Dict[str, Any]]:
    """
    Compute concise change entries for interactive map markers only.
    Returns a list of changes suitable for activity field_changes consumption.
    """
    changes: List[Dict[str, Any]] = []

    def _parse_json(val):
        try:
            if isinstance(val, dict):
                return val
            if isinstance(val, str) and val and val.strip().startswith('{'):
                return json.loads(val)
        except Exception as e:
            logger.debug("_parse_json failed: %s", e)
            return {}
        return {}

    def _fmt_coord(x: Any) -> str:
        try:
            return f"{float(x):.4f}"
        except Exception as e:
            logger.debug("_fmt_coord failed: %s", e)
            return str(x)

    def _marker_label(m: Dict[str, Any]) -> str:
        title = m.get('title') if isinstance(m.get('title'), str) and m.get('title') else None
        lat = _fmt_coord(m.get('lat'))
        lng = _fmt_coord(m.get('lng'))
        category = m.get('category') if isinstance(m.get('category'), str) and m.get('category') else None
        title_part = f" “{title}”" if title else ""
        category_part = f" ({category})" if category else ""
        return f"marker{title_part} at {lat}, {lng}{category_part}"

    old_data = _parse_json(old_value_str)
    new_data = _parse_json(new_value_str)

    old_markers = old_data.get('markers', []) if isinstance(old_data, dict) else []
    new_markers = new_data.get('markers', []) if isinstance(new_data, dict) else []

    # Index by id for stable matching
    old_by_id = {m.get('id'): m for m in old_markers if isinstance(m, dict) and m.get('id')}
    new_by_id = {m.get('id'): m for m in new_markers if isinstance(m, dict) and m.get('id')}

    # Removals
    for mid, m in old_by_id.items():
        if mid not in new_by_id:
            changes.append({
                'type': 'removed',
                'form_item_id': form_item_id,
                'field_name': field_name,
                'old_value': _marker_label(m),
                'new_value': None
            })

    # Additions
    for mid, m in new_by_id.items():
        if mid not in old_by_id:
            changes.append({
                'type': 'added',
                'form_item_id': form_item_id,
                'field_name': field_name,
                'old_value': None,
                'new_value': _marker_label(m)
            })

    # Updates (compare selected fields only)
    fields_to_compare = ['lat', 'lng', 'title', 'description', 'category']
    for mid, new_m in new_by_id.items():
        if mid in old_by_id:
            old_m = old_by_id[mid]
            changed = any(old_m.get(f) != new_m.get(f) for f in fields_to_compare)
            if changed:
                changes.append({
                    'type': 'updated',
                    'form_item_id': form_item_id,
                    'field_name': field_name,
                    'old_value': _marker_label(old_m),
                    'new_value': _marker_label(new_m)
                })

    return changes
