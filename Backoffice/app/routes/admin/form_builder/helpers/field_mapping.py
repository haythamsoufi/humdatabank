"""Manual stable_key linking for draft template structure rows."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

from app import db
from app.models import FormItem, FormSection, FormTemplate, FormTemplateVersion
from app.services.platform.user_analytics_service import log_admin_action
from app.utils.stable_key import generate_stable_key, is_valid_stable_key, normalize_stable_key


class FieldMappingConflictError(Exception):
    """Raised when linking would overwrite another draft row's published key."""

    def __init__(
        self,
        message: str,
        *,
        existing_draft_item: Optional[Dict[str, Any]] = None,
        existing_draft_section: Optional[Dict[str, Any]] = None,
        published_item: Optional[Dict[str, Any]] = None,
        published_section: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.existing_draft_item = existing_draft_item
        self.existing_draft_section = existing_draft_section
        self.published_item = published_item
        self.published_section = published_section


class FieldMappingValidationError(Exception):
    """Raised for invalid link/unlink requests."""


class FieldMappingIncompatibleError(FieldMappingValidationError):
    """Raised when two rows store their data in different shapes and can never be linked."""


class FieldMappingTypeMismatchError(Exception):
    """Raised when a link is possible but risky and needs explicit confirmation.

    Same kind of field, but a different data type or indicator: existing submissions
    would be carried onto a field that may not be able to display or validate them.
    """

    def __init__(self, message: str, *, warnings: List[str]):
        super().__init__(message)
        self.warnings = warnings


def _require_draft_version(version: FormTemplateVersion) -> None:
    if version.status == 'published':
        raise FieldMappingValidationError(
            'Field linking is only allowed on draft versions.'
        )


def _published_version(template: FormTemplate) -> FormTemplateVersion:
    if not template.published_version_id:
        raise FieldMappingValidationError(
            'No published version exists to link fields against.'
        )
    published = FormTemplateVersion.query.filter_by(
        id=template.published_version_id,
        template_id=template.id,
        status='published',
    ).first()
    if not published:
        raise FieldMappingValidationError('Published version not found.')
    return published


def _serialize_item(item: FormItem, sections_by_id: Dict[int, FormSection]) -> Dict[str, Any]:
    section = sections_by_id.get(item.section_id)
    return {
        'id': item.id,
        'label': item.label,
        'item_type': item.item_type,
        'section_name': section.name if section else '',
        'stable_key': item.stable_key,
        'indicator_bank_id': item.indicator_bank_id,
    }


def _serialize_section(section: FormSection) -> Dict[str, Any]:
    return {
        'id': section.id,
        'name': section.name,
        'section_type': section.section_type,
        'stable_key': section.stable_key,
    }


def _blocking_incompatibilities(
    draft_row: Union[FormItem, FormSection],
    published_row: Union[FormItem, FormSection],
) -> List[str]:
    """Differences that make carrying data across impossible (different storage shape)."""
    if isinstance(draft_row, FormItem) and isinstance(published_row, FormItem):
        draft_type = (draft_row.item_type or '').strip().lower()
        pub_type = (published_row.item_type or '').strip().lower()
        if draft_type != pub_type:
            return [
                f"Item type mismatch: draft is '{draft_type}', published is '{pub_type}'. "
                'Data of one kind of field cannot be carried onto another kind.'
            ]
    elif isinstance(draft_row, FormSection) and isinstance(published_row, FormSection):
        draft_type = (draft_row.section_type or '').strip().lower()
        pub_type = (published_row.section_type or '').strip().lower()
        if draft_type != pub_type:
            return [
                f"Section type mismatch: draft is '{draft_type}', published is '{pub_type}'. "
                'Standard, repeat and dynamic sections store their data differently.'
            ]
    return []


def _type_mismatch_warnings(
    draft_row: Union[FormItem, FormSection],
    published_row: Union[FormItem, FormSection],
) -> List[str]:
    """Differences that still allow linking but need an explicit confirmation."""
    warnings: List[str] = []
    if isinstance(draft_row, FormItem) and isinstance(published_row, FormItem):
        draft_dtype = (draft_row.type or '').strip().lower()
        pub_dtype = (published_row.type or '').strip().lower()
        if draft_dtype != pub_dtype:
            warnings.append(
                f"Data type differs: draft is '{draft_dtype or 'unset'}', "
                f"published is '{pub_dtype or 'unset'}'."
            )
        if draft_row.indicator_bank_id != published_row.indicator_bank_id:
            warnings.append(
                'indicator_bank_id differs between draft and published field.'
            )
    return warnings


def _check_link_compatibility(
    draft_row: Union[FormItem, FormSection],
    published_row: Union[FormItem, FormSection],
    confirm_type_mismatch: bool,
) -> List[str]:
    blocking = _blocking_incompatibilities(draft_row, published_row)
    if blocking:
        raise FieldMappingIncompatibleError(' '.join(blocking))
    warnings = _type_mismatch_warnings(draft_row, published_row)
    if warnings and not confirm_type_mismatch:
        raise FieldMappingTypeMismatchError(
            'These fields differ: ' + ' '.join(warnings) +
            ' Existing submissions would be carried onto the new field as they are.',
            warnings=warnings,
        )
    return warnings


def link_draft_item(
    *,
    template: FormTemplate,
    draft_version: FormTemplateVersion,
    draft_item: FormItem,
    published_stable_key: str,
    confirm_reassign: bool = False,
    confirm_type_mismatch: bool = False,
) -> Tuple[str, List[str], Optional[Dict[str, Any]]]:
    """Link a draft item to a published stable_key. Returns (stable_key, warnings, displaced_item)."""
    _require_draft_version(draft_version)
    if draft_item.template_id != template.id or draft_item.version_id != draft_version.id:
        raise FieldMappingValidationError('Item does not belong to this draft version.')

    key = normalize_stable_key(published_stable_key)
    if not key:
        raise FieldMappingValidationError('Invalid published_stable_key.')

    published_version = _published_version(template)
    published_item = FormItem.query.filter_by(
        template_id=template.id,
        version_id=published_version.id,
        stable_key=key,
    ).first()
    if not published_item:
        raise FieldMappingValidationError(
            'Published field not found for the given stable_key.'
        )
    warnings = _check_link_compatibility(draft_item, published_item, confirm_type_mismatch)

    existing = FormItem.query.filter_by(
        template_id=template.id,
        version_id=draft_version.id,
        stable_key=key,
    ).filter(FormItem.id != draft_item.id).first()
    displaced: Optional[Dict[str, Any]] = None
    if existing:
        sections = {
            section.id: section
            for section in FormSection.query.filter_by(
                template_id=template.id, version_id=draft_version.id
            ).all()
        }
        if not confirm_reassign:
            pub_sections = {
                section.id: section
                for section in FormSection.query.filter_by(
                    template_id=template.id, version_id=published_version.id
                ).all()
            }
            raise FieldMappingConflictError(
                f"Published field '{published_item.label}' is already linked to draft field "
                f"'{existing.label}'.",
                existing_draft_item=_serialize_item(existing, sections),
                published_item=_serialize_item(published_item, pub_sections),
            )
        new_key = generate_stable_key()
        existing.stable_key = new_key
        displaced = _serialize_item(existing, sections)

    draft_item.stable_key = key
    db.session.flush()

    log_admin_action(
        action_type='template_field_link',
        description=(
            f"Linked draft item '{draft_item.label}' to published stable_key for "
            f"'{published_item.label}' on template '{template.name}'"
        ),
        target_type='form_template',
        target_id=template.id,
        target_description=f"Template ID: {template.id}, Draft item ID: {draft_item.id}",
        risk_level='medium',
        new_values={
            'draft_version_id': draft_version.id,
            'draft_item_id': draft_item.id,
            'published_stable_key': key,
            'displaced_draft_item': displaced,
        },
    )
    return key, warnings, displaced


def unlink_draft_item(
    *,
    template: FormTemplate,
    draft_version: FormTemplateVersion,
    draft_item: FormItem,
) -> str:
    """Mark draft item as a new field with a fresh stable_key."""
    _require_draft_version(draft_version)
    if draft_item.template_id != template.id or draft_item.version_id != draft_version.id:
        raise FieldMappingValidationError('Item does not belong to this draft version.')

    new_key = generate_stable_key()
    draft_item.stable_key = new_key
    db.session.flush()

    log_admin_action(
        action_type='template_field_unlink',
        description=(
            f"Marked draft item '{draft_item.label}' as a new field on template '{template.name}'"
        ),
        target_type='form_template',
        target_id=template.id,
        target_description=f"Template ID: {template.id}, Draft item ID: {draft_item.id}",
        risk_level='low',
        new_values={
            'draft_version_id': draft_version.id,
            'draft_item_id': draft_item.id,
            'stable_key': new_key,
        },
    )
    return new_key


def link_draft_section(
    *,
    template: FormTemplate,
    draft_version: FormTemplateVersion,
    draft_section: FormSection,
    published_stable_key: str,
    confirm_reassign: bool = False,
    confirm_type_mismatch: bool = False,
) -> Tuple[str, List[str], Optional[Dict[str, Any]]]:
    _require_draft_version(draft_version)
    if draft_section.template_id != template.id or draft_section.version_id != draft_version.id:
        raise FieldMappingValidationError('Section does not belong to this draft version.')

    key = normalize_stable_key(published_stable_key)
    if not key:
        raise FieldMappingValidationError('Invalid published_stable_key.')

    published_version = _published_version(template)
    published_section = FormSection.query.filter_by(
        template_id=template.id,
        version_id=published_version.id,
        stable_key=key,
    ).first()
    if not published_section:
        raise FieldMappingValidationError(
            'Published section not found for the given stable_key.'
        )
    warnings = _check_link_compatibility(draft_section, published_section, confirm_type_mismatch)

    existing = FormSection.query.filter_by(
        template_id=template.id,
        version_id=draft_version.id,
        stable_key=key,
    ).filter(FormSection.id != draft_section.id).first()
    displaced: Optional[Dict[str, Any]] = None
    if existing:
        if not confirm_reassign:
            raise FieldMappingConflictError(
                f"Published section '{published_section.name}' is already linked to draft section "
                f"'{existing.name}'.",
                existing_draft_section=_serialize_section(existing),
                published_section=_serialize_section(published_section),
            )
        existing.stable_key = generate_stable_key()
        displaced = _serialize_section(existing)

    draft_section.stable_key = key
    db.session.flush()

    log_admin_action(
        action_type='template_section_link',
        description=(
            f"Linked draft section '{draft_section.name}' to published stable_key for "
            f"'{published_section.name}' on template '{template.name}'"
        ),
        target_type='form_template',
        target_id=template.id,
        target_description=f"Template ID: {template.id}, Draft section ID: {draft_section.id}",
        risk_level='medium',
        new_values={
            'draft_version_id': draft_version.id,
            'draft_section_id': draft_section.id,
            'published_stable_key': key,
            'displaced_draft_section': displaced,
        },
    )
    return key, warnings, displaced


def unlink_draft_section(
    *,
    template: FormTemplate,
    draft_version: FormTemplateVersion,
    draft_section: FormSection,
) -> str:
    _require_draft_version(draft_version)
    if draft_section.template_id != template.id or draft_section.version_id != draft_version.id:
        raise FieldMappingValidationError('Section does not belong to this draft version.')

    new_key = generate_stable_key()
    draft_section.stable_key = new_key
    db.session.flush()

    log_admin_action(
        action_type='template_section_unlink',
        description=(
            f"Marked draft section '{draft_section.name}' as new on template '{template.name}'"
        ),
        target_type='form_template',
        target_id=template.id,
        target_description=f"Template ID: {template.id}, Draft section ID: {draft_section.id}",
        risk_level='low',
        new_values={
            'draft_version_id': draft_version.id,
            'draft_section_id': draft_section.id,
            'stable_key': new_key,
        },
    )
    return new_key


def published_picker_items(template: FormTemplate) -> List[Dict[str, Any]]:
    """Published items for the link picker."""
    if not template.published_version_id:
        return []
    sections = {
        section.id: section
        for section in FormSection.query.filter_by(
            template_id=template.id, version_id=template.published_version_id
        ).all()
    }
    items = FormItem.query.filter_by(
        template_id=template.id, version_id=template.published_version_id
    ).order_by(FormItem.order, FormItem.id).all()
    return [
        {
            **_serialize_item(item, sections),
            'stable_key': item.stable_key,
        }
        for item in items
        if item.stable_key and is_valid_stable_key(item.stable_key)
    ]


def published_picker_sections(template: FormTemplate) -> List[Dict[str, Any]]:
    if not template.published_version_id:
        return []
    sections = FormSection.query.filter_by(
        template_id=template.id, version_id=template.published_version_id
    ).order_by(FormSection.order, FormSection.id).all()
    return [
        _serialize_section(section)
        for section in sections
        if section.stable_key and is_valid_stable_key(section.stable_key)
    ]
