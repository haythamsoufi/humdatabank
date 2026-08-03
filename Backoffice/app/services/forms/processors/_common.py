"""Shared utilities for form data processors."""
from app.services.monitoring.debug import debug_manager

logger = debug_manager.get_logger(__name__)


def get_english_field_name(form_item):
    """Get the English field name for fallback storage in activity logging."""
    return form_item.label
