from app.utils.file_paths import save_sector_logo
from app.services import storage_service as storage
from flask import current_app
from datetime import datetime
from sqlalchemy import inspect
import os


# === Logo Helpers ===

_SAFE_LOGO_MIMETYPES = {
    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.gif': 'image/gif', '.webp': 'image/webp',
}


def _safe_logo_mimetype(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return _SAFE_LOGO_MIMETYPES.get(ext, 'application/octet-stream')


def _save_logo_file(file_storage, item_name):
    """Save a sector logo file."""
    try:
        if not file_storage or not file_storage.filename:
            return None
        return save_sector_logo(file_storage, item_name)
    except Exception as e:
        current_app.logger.exception("Error saving logo file: %s", e)
        return None


def _delete_logo_file(filename):
    """Delete a sector logo file."""
    try:
        storage.unpublish_system_logo_from_cdn("sectors", filename)
        storage.delete(storage.SYSTEM, f"sectors/{filename}")
    except Exception as e:
        current_app.logger.exception("Error deleting logo file: %s", e)


# === Indicator Change Tracking ===

def indicator_bank_history_snapshot(indicator):
    """Shared field snapshot for IndicatorBankHistory rows."""
    return {
        "name": indicator.name,
        "type": indicator.type,
        "unit": indicator.unit,
        "fdrs_kpi_code": getattr(indicator, "fdrs_kpi_code", None),
        "definition": indicator.definition,
        "name_translations": indicator.name_translations,
        "definition_translations": indicator.definition_translations,
        "aggregated_label": getattr(indicator, "aggregated_label", None),
        "aggregated_label_translations": getattr(indicator, "aggregated_label_translations", None),
        "area": getattr(indicator, "area", None),
        "area_label": getattr(indicator, "area_label", None),
        "data_source": getattr(indicator, "data_source", None),
        "disaggregation_guidance": getattr(indicator, "disaggregation_guidance", None),
        "monitoring_questions": getattr(indicator, "monitoring_questions", None),
        "tags": getattr(indicator, "tags", None),
        "archived": indicator.archived,
        "comments": indicator.comments,
        "emergency": indicator.emergency,
        "related_programs": indicator.related_programs,
        "sector": indicator.sector,
        "sub_sector": indicator.sub_sector,
    }


def track_indicator_changes(old_indicator, new_form_data, user):
    """
    Track specific changes between old indicator data and new form data.
    Returns a list of change descriptions.
    """
    from app.models import Sector, SubSector
    changes = []

    fields_to_track = [
        ('name', 'Name'),
        ('type', 'Type'),
        ('unit', 'Unit'),
        ('fdrs_kpi_code', 'FDRS KPI Code'),
        ('definition', 'Definition'),
        ('aggregated_label', 'Aggregated Label'),
        ('name_translations', 'Name Translations'),
        ('definition_translations', 'Definition Translations'),
        ('aggregated_label_translations', 'Aggregated Label Translations'),
        ('area', 'Area'),
        ('data_source', 'Data Source'),
        ('disaggregation_guidance', 'Disaggregation Guidance'),
        ('monitoring_questions', 'Monitoring Questions'),
        ('tags', 'Tags'),
        ('comments', 'Comments'),
        ('related_programs', 'Related Programs'),
        ('emergency', 'Emergency'),
        ('archived', 'Archived'),
        ('sector_primary', 'Sector Primary'),
        ('sector_secondary', 'Sector Secondary'),
        ('sector_tertiary', 'Sector Tertiary'),
        ('sub_sector_primary', 'Sub-Sector Primary'),
        ('sub_sector_secondary', 'Sub-Sector Secondary'),
        ('sub_sector_tertiary', 'Sub-Sector Tertiary')
    ]

    for field_name, display_name in fields_to_track:
        old_value = getattr(old_indicator, field_name, None)
        new_value = new_form_data.get(field_name)

        if field_name in ("name_translations", "definition_translations", "aggregated_label_translations", "monitoring_questions", "tags"):
            try:
                if isinstance(new_value, str) and new_value.strip():
                    import json as _json
                    parsed = _json.loads(new_value)
                    new_value = parsed if isinstance(parsed, dict) else None
                else:
                    new_value = None
            except Exception as e:
                current_app.logger.debug("name_translations/definition_translations parse failed: %s", e)
                new_value = None

        if field_name in ['emergency', 'archived']:
            old_value = bool(old_value)
            new_value = bool(new_value)

        if field_name.startswith('sector_'):
            level = field_name.replace('sector_', '')
            old_value = old_indicator.sector.get(level) if old_indicator.sector else None
        elif field_name.startswith('sub_sector_'):
            level = field_name.replace('sub_sector_', '')
            old_value = old_indicator.sub_sector.get(level) if old_indicator.sub_sector else None

        if new_value == '' or new_value == 'None':
            new_value = None
        if old_value == '' or old_value == 'None':
            old_value = None

        if old_value is None and new_value is None:
            continue

        if old_value != new_value:
            if field_name == 'type':
                old_type = str(old_value).lower() if old_value else None
                new_type = str(new_value).lower() if new_value else None
                if old_type == new_type:
                    continue

            if field_name.startswith('sector_') and new_value:
                try:
                    sector = Sector.query.get(new_value)
                    new_display_value = sector.name if sector else f"ID: {new_value}"
                except Exception as e:
                    current_app.logger.debug("sector lookup for new_value failed: %s", e)
                    new_display_value = f"ID: {new_value}"
            elif field_name.startswith('sub_sector_') and new_value:
                try:
                    subsector = SubSector.query.get(new_value)
                    new_display_value = subsector.name if subsector else f"ID: {new_value}"
                except Exception as e:
                    current_app.logger.debug("subsector lookup for new_value failed: %s", e)
                    new_display_value = f"ID: {new_value}"
            else:
                new_display_value = str(new_value) if new_value is not None else None

            if field_name.startswith('sector_') and old_value:
                try:
                    sector = Sector.query.get(old_value)
                    old_display_value = sector.name if sector else f"ID: {old_value}"
                except Exception as e:
                    current_app.logger.debug("sector lookup for old_value failed: %s", e)
                    old_display_value = f"ID: {old_value}"
            elif field_name.startswith('sub_sector_') and old_value:
                try:
                    subsector = SubSector.query.get(old_value)
                    old_display_value = subsector.name if subsector else f"ID: {old_value}"
                except Exception as e:
                    current_app.logger.debug("subsector lookup for old_value failed: %s", e)
                    old_display_value = f"ID: {old_value}"
            else:
                old_display_value = str(old_value) if old_value is not None else None

            if old_value is None and new_value is not None:
                changes.append(f"{display_name}: Added '{new_display_value}'")
            elif old_value is not None and new_value is None:
                changes.append(f"{display_name}: Removed '{old_display_value}'")
            elif old_value != new_value:
                old_display = old_display_value[:50] + "..." if len(str(old_display_value)) > 50 else str(old_display_value)
                new_display = new_display_value[:50] + "..." if len(str(new_display_value)) > 50 else str(new_display_value)
                changes.append(f"{display_name}: Changed from '{old_display}' to '{new_display}'")

    return changes


# === System List Helpers ===

from app.utils.sqlalchemy_grid import build_columns_config as _get_model_columns_config, model_to_dict as _model_to_dict
