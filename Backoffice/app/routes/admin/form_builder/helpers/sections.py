"""Section utility helpers for the form_builder package."""

from flask_login import current_user
from app import db
from app.models import FormSection, FormItem, FormTemplateVersion
from app.utils.datetime_helpers import utcnow


def _get_descendant_section_ids(parent_section_id):
    """Return list of all descendant section IDs (children, grandchildren, ...) in leaf-first order for safe cascade delete."""
    descendants = []
    to_visit = [parent_section_id]
    while to_visit:
        pid = to_visit.pop()
        children = FormSection.query.filter_by(parent_section_id=pid).order_by(FormSection.id).all()
        for c in children:
            descendants.append(c.id)
            to_visit.append(c.id)
    # Reverse so we delete leaves first (children before their parents)
    return list(reversed(descendants))


def _delete_or_archive_one_section(sec, delete_data, keep_data_delete_section):
    """Delete or archive a single section and its item data. Used for cascade delete."""
    from app.models.forms import FormData, RepeatGroupData, RepeatGroupInstance, DynamicIndicatorData
    from app.models.form_items import FormItem

    items = FormItem.query.filter_by(section_id=sec.id).all()
    section_item_ids = [item.id for item in items]
    if delete_data:
        if section_item_ids:
            FormData.query.filter(FormData.form_item_id.in_(section_item_ids)).delete(synchronize_session=False)
            RepeatGroupData.query.filter(RepeatGroupData.form_item_id.in_(section_item_ids)).delete(synchronize_session=False)
        RepeatGroupInstance.query.filter_by(section_id=sec.id).delete(synchronize_session=False)
        DynamicIndicatorData.query.filter_by(section_id=sec.id).delete(synchronize_session=False)
        db.session.flush()
    if keep_data_delete_section:
        sec.archived = True
        db.session.add(sec)
        for item in items:
            item.archived = True
            db.session.add(item)
        db.session.flush()
    else:
        db.session.delete(sec)
        db.session.flush()


def _update_version_timestamp(version_id, user_id=None):
    """Update the updated_at timestamp and updated_by for a version when its contents change."""
    if version_id:
        version = FormTemplateVersion.query.get(version_id)
        if version:
            version.updated_at = utcnow()
            if user_id:
                version.updated_by = user_id
            elif current_user and current_user.is_authenticated:
                version.updated_by = current_user.id
