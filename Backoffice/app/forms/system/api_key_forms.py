"""
API Key Management Forms
"""

from typing import Any, Dict, Optional as Opt

from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, DateTimeField, BooleanField, SelectMultipleField
from wtforms.validators import DataRequired, Optional, NumberRange, Length
from wtforms.widgets import CheckboxInput, ListWidget
from app.services.security.api_key_permissions import (
    CAPABILITIES,
    PII_CAPABILITY_CODES,
    SCOPABLE_CAPABILITY_CODES,
    SENSITIVE_CAPABILITY_CODES,
    KeyPermissions,
    build_permissions_document,
    parse_key_permissions,
)
from app.utils.datetime_helpers import ensure_utc, utcnow


class APIKeyPermissionsForm(FlaskForm):
    """Permission fields shared by the create and edit screens (one source of truth)."""

    capabilities = SelectMultipleField(
        _l('Permissions'),
        choices=[(c.code, c.label) for c in CAPABILITIES],
        widget=ListWidget(prefix_label=False),
        option_widget=CheckboxInput(),
        validators=[Optional()],
    )
    restrict_data = BooleanField(_l('Limit data access to specific templates and/or countries'))
    scope_template_ids = SelectMultipleField(_l('Templates'), coerce=int, validators=[Optional()])
    scope_country_ids = SelectMultipleField(_l('Countries'), coerce=int, validators=[Optional()])
    allow_query_api_key = BooleanField(
        _l('Also accept this key in the URL query string (?api_key=...) - not recommended')
    )
    confirm_sensitive = BooleanField(
        _l('I understand this key can read sensitive or personal data and will only share it with a trusted client')
    )
    keep_legacy_full_access = BooleanField(
        _l('Keep legacy full access (every permission, including personal data)')
    )

    def __init__(self, *args, legacy_full_access: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.legacy_full_access_key = legacy_full_access
        self.scope_template_ids.choices = _template_choices()
        self.scope_country_ids.choices = _country_choices()

    def load_permissions(self, perms: KeyPermissions) -> None:
        """Pre-fill from an existing key (GET on the edit screen)."""
        self.capabilities.data = sorted(perms.capabilities)
        scope = perms.data_scope
        self.restrict_data.data = scope is not None
        self.scope_template_ids.data = list(scope["template_ids"]) if scope else []
        self.scope_country_ids.data = list(scope["country_ids"]) if scope else []
        self.allow_query_api_key.data = perms.allow_query_api_key
        self.keep_legacy_full_access.data = perms.legacy_full_access

    @property
    def keeps_legacy_full_access(self) -> bool:
        return bool(self.legacy_full_access_key and self.keep_legacy_full_access.data)

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators=extra_validators)
        if self.keeps_legacy_full_access:
            if not self.confirm_sensitive.data:
                self.confirm_sensitive.errors = list(self.confirm_sensitive.errors) + [
                    str(_l('Confirm that you accept keeping full access for this key, or untick "Keep legacy full access".'))
                ]
                ok = False
            return ok

        selected = set(self.capabilities.data or [])
        if not selected:
            self.capabilities.errors = list(self.capabilities.errors) + [
                str(_l('Select at least one permission. A key with no permissions cannot call any endpoint.'))
            ]
            ok = False
        if self.restrict_data.data:
            if not (self.scope_template_ids.data or self.scope_country_ids.data):
                self.restrict_data.errors = list(self.restrict_data.errors) + [
                    str(_l('Choose at least one template or country, or untick the data restriction.'))
                ]
                ok = False
            elif not (selected & SCOPABLE_CAPABILITY_CODES):
                self.restrict_data.errors = list(self.restrict_data.errors) + [
                    str(_l('The restriction only applies to Form data, Submissions and Form templates. Select one of them or untick the restriction.'))
                ]
                ok = False
        if selected & SENSITIVE_CAPABILITY_CODES and not self.confirm_sensitive.data:
            self.confirm_sensitive.errors = list(self.confirm_sensitive.errors) + [
                str(_l('Please confirm access to sensitive data.'))
            ]
            ok = False
        if self.allow_query_api_key.data and selected & PII_CAPABILITY_CODES:
            self.allow_query_api_key.errors = list(self.allow_query_api_key.errors) + [
                str(_l('Keys with personal-data permissions must be sent in a header, not in the URL.'))
            ]
            ok = False
        return ok

    def build_permissions(self, current: Opt[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Permission document to store. Keeping legacy full access leaves the stored row unchanged."""
        if self.keeps_legacy_full_access and current is not None:
            return current
        return build_permissions_document(
            self.capabilities.data or [],
            template_ids=self.scope_template_ids.data,
            country_ids=self.scope_country_ids.data,
            restrict_data=bool(self.restrict_data.data),
            allow_query_api_key=bool(self.allow_query_api_key.data),
        )


def _template_choices():
    from app.services import TemplateService

    try:
        return [(t.id, t.name) for t in TemplateService.get_all()]
    except Exception:
        return []


def _country_choices():
    from app.models import Country

    try:
        return [(c.id, c.name) for c in Country.query.order_by(Country.name).all()]
    except Exception:
        return []


class APIKeyForm(APIKeyPermissionsForm):
    """Form for creating/editing API keys"""

    client_name = StringField(
        'Client Name',
        validators=[DataRequired(), Length(max=255)],
        description='Human-readable name for this API key (e.g., "Mobile App", "External Integration")'
    )

    client_description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=1000)],
        description='Optional description of what this API key is used for'
    )

    rate_limit_per_minute = IntegerField(
        'Rate Limit (per minute)',
        validators=[Optional(), NumberRange(min=1, max=10000)],
        default=60,
        description='Maximum number of API requests allowed per minute for this key'
    )

    expires_at = DateTimeField(
        'Expiration Date',
        validators=[Optional()],
        format=['%Y-%m-%dT%H:%M', '%Y-%m-%d'],
        description='Optional expiration date for this API key (leave blank for no expiration)'
    )

    def validate_expires_at(self, field):
        """Ensure expiration date is in the future if provided"""
        if field.data and ensure_utc(field.data) <= utcnow():
            from wtforms.validators import ValidationError
            raise ValidationError('Expiration date must be in the future')


class APIKeyEditForm(APIKeyPermissionsForm):
    """Form for editing an existing API key's metadata and permissions (no key material change)."""

    original_expires_at = None

    client_name = StringField(
        'Client Name',
        validators=[DataRequired(), Length(max=255)],
        description='Human-readable name for this API key'
    )

    client_description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=1000)],
        description='Optional description of what this API key is used for'
    )

    rate_limit_per_minute = IntegerField(
        'Rate Limit (per minute)',
        validators=[Optional(), NumberRange(min=1, max=10000)],
        default=60,
        description='Maximum number of API requests allowed per minute for this key'
    )

    expires_at = DateTimeField(
        'Expiration Date',
        validators=[Optional()],
        format=['%Y-%m-%dT%H:%M', '%Y-%m-%d'],
        description='Optional expiration date (leave blank for no expiration)'
    )

    def validate_expires_at(self, field):
        unchanged = self.original_expires_at is not None and field.data == self.original_expires_at
        if field.data and ensure_utc(field.data) <= utcnow() and not unchanged:
            from wtforms.validators import ValidationError
            raise ValidationError('Expiration date must be in the future')


class APIKeyRevokeForm(FlaskForm):
    """Form for revoking API keys"""

    revocation_reason = TextAreaField(
        'Revocation Reason',
        validators=[Optional(), Length(max=500)],
        description='Optional reason for revoking this API key'
    )
