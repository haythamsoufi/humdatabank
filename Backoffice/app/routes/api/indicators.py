from app.utils.database.transactions import request_transaction_rollback
from contextlib import suppress
# Backoffice/app/routes/api/indicators.py
from app.utils.common.datetime_helpers import utcnow
from app.utils.branding.sector_logo_urls import sector_logo_url
"""
Indicator Bank, Suggestions, and Sector API endpoints.
Part of the /api/v1 blueprint.
"""

from flask import request, current_app
from werkzeug.exceptions import NotFound
import uuid
from sqlalchemy import desc
from app.models.enums import IndicatorSuggestionStatusValue
import re
from collections import defaultdict
from datetime import datetime, timedelta

# Import the API blueprint from parent
from app.routes.api import api_bp

# Import models
from app.models import (
    IndicatorBank,
    IndicatorBankType,
    IndicatorBankUnit,
    IndicatorSuggestion,
    Sector,
    SubSector,
)
from app.utils.auth.auth import require_api_key
from app.services.security.api_authentication import get_api_principal, redact_request_params
from app.services.security.api_key_permissions import (
    INDICATORS_MANAGE,
    INDICATORS_SUGGEST,
    REFERENCE_READ,
)
from app.utils.security.rate_limiting import api_rate_limit
from app import db

# Import utility functions
from app.utils.api.api_helpers import json_response, api_error, get_json_safe
from app.utils.api.api_responses import require_json_data, require_json_keys
from app.utils.forms.form_localization import get_localized_indicator_type, get_localized_indicator_unit
from app.services.indicators.bank_service import (
    IndicatorBankFilters,
    build_sector_subsector_names as _build_sector_subsector_names,
    get_indicator_list,
    get_localized_type_unit as _get_localized_type_unit,
    get_supported_language_codes as _get_supported_language_codes,
    load_measurement_lookup_maps as _load_measurement_lookup_maps,
    serialize_indicator as _serialize_indicator_bank_record,
    serialize_indicator_list,
)

@api_bp.route('/indicator-bank', methods=['GET'])
@api_rate_limit()
def get_indicator_bank():
    """
    API endpoint to retrieve indicators from the indicator bank.
    Public read — no API key required. The catalogue is paged: clients that need
    every match must follow ``total`` with ``page`` until the pages are exhausted.
    Query Parameters:
        - search: Search query for indicator name or definition
        - type: Filter by indicator type
        - sector: Filter by sector
        - sub_sector: Filter by sub-sector
        - emergency: Filter by emergency type
        - archived: Filter by archived status (true=only archived, false=only non-archived, omit=all indicators)
        - page: Page number (default 1)
        - per_page: Page size (default 100, max 500)
        - limit: Optional cap on this page's size (max 500). Does not replace paging.
    Returns:
        JSON object containing:
        - indicators: Indicator objects for this page
        - total: Matching indicators across all pages
        - page, per_page: The page that was returned
    """
    try:
        current_app.logger.debug("Entering indicator bank API endpoint")
        filters = IndicatorBankFilters(
            search=request.args.get('search', default='', type=str).strip(),
            indicator_type=request.args.get('type', default='', type=str).strip(),
            sector=request.args.get('sector', default='', type=str).strip(),
            sub_sector=request.args.get('sub_sector', default='', type=str).strip(),
            emergency=request.args.get('emergency', default='', type=str).strip(),
            archived=request.args.get('archived', default=None),
        )
        from app.utils.api.api_pagination import validate_pagination_params

        page, per_page = validate_pagination_params(
            request.args, default_per_page=100, max_per_page=500
        )
        limit = request.args.get('limit', default=None, type=int)
        if limit is not None and limit > 0:
            per_page = min(limit, 500)
        indicators_data, total, page, per_page = get_indicator_list(
            filters, page=page, per_page=per_page
        )
        current_app.logger.debug("Indicator bank API returning %s items", len(indicators_data))
        response = json_response({
            'indicators': indicators_data,
            'total': total,
            'page': page,
            'per_page': per_page,
        })
        # Public, rarely-changing data. Allow downstream caches (AGW, CDN, BI tools) to
        # reuse the response for 5 minutes before re-querying the backend.
        response.headers['Cache-Control'] = 'public, max-age=300, stale-while-revalidate=60'
        return response

    except Exception as e:
        current_app.logger.error(f"API Error fetching indicator bank: {e}", exc_info=True)
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            f"API Error [ID: {error_id}] fetching indicator bank: {e}",
            exc_info=True,
            extra={'endpoint': '/indicators', 'params': redact_request_params()}
        )
        return api_error("Could not fetch indicator bank data", 500, error_id, None)


@api_bp.route('/indicator-bank/<int:indicator_id>', methods=['GET'])
@api_rate_limit()
def get_indicator_bank_details(indicator_id):
    """
    API endpoint to retrieve details for a specific indicator from the bank.
    Public read — no API key required.
    """
    try:
        indicator = IndicatorBank.query.get(indicator_id)

        if not indicator:
            return api_error('Indicator not found', 404)

        indicator_data = serialize_indicator_list([indicator])[0]
        return json_response(indicator_data)

    except Exception as e:
        current_app.logger.error(f"API Error fetching indicator {indicator_id}: {e}", exc_info=True)
        return api_error("Could not fetch indicator details", 500)


_EMAIL_RE = re.compile(r"^[^@\s<>\"',;:()\[\]\\]+@[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)+$")

# (field, max length). Columns are String(255)/String(50); free-text columns are capped so a
# public key cannot store or mail unbounded content.
_SUGGESTION_TEXT_LIMITS = (
    ('submitter_name', 255),
    ('submitter_email', 254),
    ('suggestion_type', 50),
    ('indicator_name', 255),
    ('definition', 5000),
    ('type', 50),
    ('unit', 50),
    ('related_programs', 2000),
    ('reason', 5000),
    ('additional_notes', 5000),
)
_SUGGESTION_LEVEL_MAX = 255
_DEFAULT_SUGGESTIONS_PER_EMAIL_HOUR = 5
_DEFAULT_SUGGESTIONS_PER_HOUR = 200


def _validate_suggestion_payload(data):
    """Return an error message when the payload is malformed or oversized, else ``None``."""
    for field, limit in _SUGGESTION_TEXT_LIMITS:
        value = data.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            return f'Field must be text: {field}'
        if len(value) > limit:
            return f'Field is too long (max {limit} characters): {field}'

    email = data['submitter_email'].strip()
    if not _EMAIL_RE.fullmatch(email):
        return 'submitter_email is not a valid email address'

    if 'emergency' in data and data['emergency'] is not None and not isinstance(data['emergency'], bool):
        return 'Field must be true or false: emergency'

    for field in ('sector', 'sub_sector'):
        value = data.get(field)
        if not value:
            continue
        if isinstance(value, dict):
            for level in ('primary', 'secondary', 'tertiary'):
                level_value = value.get(level)
                if level_value is None:
                    continue
                if not isinstance(level_value, str) or len(level_value) > _SUGGESTION_LEVEL_MAX:
                    return f'Invalid {field}.{level}'
        elif not isinstance(value, str) or len(value) > _SUGGESTION_LEVEL_MAX:
            return f'Invalid {field}'
    return None


def _suggestion_throttle_error(email):
    """Return a message when too many suggestions arrived recently (also bounds outbound mail)."""
    since = utcnow() - timedelta(hours=1)
    per_email = int(current_app.config.get('API_SUGGESTIONS_PER_EMAIL_HOUR') or _DEFAULT_SUGGESTIONS_PER_EMAIL_HOUR)
    total = int(current_app.config.get('API_SUGGESTIONS_PER_HOUR') or _DEFAULT_SUGGESTIONS_PER_HOUR)

    recent_for_email = IndicatorSuggestion.query.filter(
        db.func.lower(IndicatorSuggestion.submitter_email) == email.lower(),
        IndicatorSuggestion.submitted_at >= since,
    ).count()
    if recent_for_email >= per_email:
        return 'Too many suggestions from this email address. Please try again later.'

    recent_total = IndicatorSuggestion.query.filter(IndicatorSuggestion.submitted_at >= since).count()
    if recent_total >= total:
        return 'Too many suggestions received. Please try again later.'
    return None


@api_bp.route('/indicator-suggestions', methods=['POST'])
@require_api_key(capability=INDICATORS_SUGGEST)
@api_rate_limit()
def submit_indicator_suggestion():
    """Submit a new indicator suggestion."""
    try:
        data = get_json_safe()
        required_fields = ['submitter_name', 'submitter_email', 'suggestion_type', 'indicator_name', 'reason']
        err = require_json_keys(data, required_fields)
        if err:
            return err
        for field in required_fields:
            if not data.get(field):
                return api_error(f'Missing required field: {field}', 400)

        # This endpoint is reachable with a key that may be embedded in a public site, and it
        # sends mail to the submitted address: validate shape and size, then throttle.
        validation_error = _validate_suggestion_payload(data)
        if validation_error:
            return api_error(validation_error, 400)
        data['submitter_email'] = data['submitter_email'].strip()
        throttled = _suggestion_throttle_error(data['submitter_email'])
        if throttled:
            return api_error(throttled, 429, extra={"retry_after": 3600})

        # Validate sector and subsector data
        if data.get('sector'):
            sector_data = data['sector']
            if isinstance(sector_data, dict):
                # Only primary sector is mandatory
                if not sector_data.get('primary', '').strip():
                    return api_error('Primary sector must be filled', 400)

        if data.get('sub_sector'):
            subsector_data = data['sub_sector']
            if isinstance(subsector_data, dict):
                # Only primary subsector is mandatory
                if not subsector_data.get('primary', '').strip():
                    return api_error('Primary subsector must be filled', 400)

        # Process sector and subsector data to match the JSON structure
        sector_data = None
        if data.get('sector'):
            if isinstance(data['sector'], dict):
                # Store sector text values directly
                sector_data = {}
                for level in ['primary', 'secondary', 'tertiary']:
                    if data['sector'].get(level):
                        sector_data[level] = data['sector'][level].strip()
                    else:
                        sector_data[level] = None
            else:
                # If it's a simple string or other format, convert to JSON structure
                sector_data = {
                    'primary': data['sector'],
                    'secondary': None,
                    'tertiary': None
                }

        subsector_data = None
        if data.get('sub_sector'):
            if isinstance(data['sub_sector'], dict):
                # Store subsector text values directly
                subsector_data = {}
                for level in ['primary', 'secondary', 'tertiary']:
                    if data['sub_sector'].get(level):
                        subsector_data[level] = data['sub_sector'][level].strip()
                    else:
                        subsector_data[level] = None
            else:
                # If it's a simple string or other format, convert to JSON structure
                subsector_data = {
                    'primary': data['sub_sector'],
                    'secondary': None,
                    'tertiary': None
                }

        # Create new suggestion
        suggestion = IndicatorSuggestion(
            submitter_name=data['submitter_name'],
            submitter_email=data['submitter_email'],
            suggestion_type=data['suggestion_type'],
            indicator_id=data.get('indicator_id'),  # Optional for new indicators
            indicator_name=data['indicator_name'],
            definition=data.get('definition'),
            type=data.get('type'),
            unit=data.get('unit'),
            sector=sector_data,
            sub_sector=subsector_data,
            emergency=data.get('emergency', False),
            related_programs=data.get('related_programs'),
            reason=data['reason'],
            additional_notes=data.get('additional_notes')
        )

        db.session.add(suggestion)
        db.session.flush()

        # Send confirmation email to submitter
        try:
            from app.services.email.service import send_suggestion_confirmation_email, send_admin_notification_email
            send_suggestion_confirmation_email(suggestion)
            send_admin_notification_email(suggestion)
        except Exception as email_error:
            current_app.logger.error(f"Failed to send emails for suggestion {suggestion.id}: {str(email_error)}")
            # Don't fail the request if email sending fails

        return json_response({
            'message': 'Suggestion submitted successfully',
            'suggestion_id': suggestion.id
        }, 201)

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error submitting indicator suggestion: {str(e)}")
        return api_error('Failed to submit suggestion', 500)


@api_bp.route('/indicator-suggestions', methods=['GET'])
@require_api_key(capability=INDICATORS_MANAGE)
@api_rate_limit()
def get_indicator_suggestions():
    """Get all indicator suggestions (admin only)."""
    try:
        # Get query parameters
        from app.utils.api.api_pagination import validate_pagination_params
        status = request.args.get('status')
        suggestion_type = request.args.get('suggestion_type')
        page, per_page = validate_pagination_params(request.args, default_per_page=20, max_per_page=500)

        # Build query
        query = IndicatorSuggestion.query

        if status:
            query = query.filter(IndicatorSuggestion.status == status)

        if suggestion_type:
            query = query.filter(IndicatorSuggestion.suggestion_type == suggestion_type)

        # Order by submitted_at (newest first)
        query = query.order_by(desc(IndicatorSuggestion.submitted_at))

        # Paginate
        pagination = query.paginate(
            page=page, per_page=per_page, error_out=False
        )

        suggestions = []
        for suggestion in pagination.items:
            suggestions.append({
                'id': suggestion.id,
                'submitter_name': suggestion.submitter_name,
                'submitter_email': suggestion.submitter_email,
                'suggestion_type': suggestion.suggestion_type,
                'suggestion_type_display': suggestion.suggestion_type_display,
                'status': suggestion.status,
                'status_display': suggestion.status_display,
                'submitted_at': suggestion.submitted_at.isoformat() if suggestion.submitted_at else None,
                'reviewed_at': suggestion.reviewed_at.isoformat() if suggestion.reviewed_at else None,
                'indicator_id': suggestion.indicator_id,
                'indicator_name': suggestion.indicator_name,
                'definition': suggestion.definition,
                'type': suggestion.type,
                'unit': suggestion.unit,
                'sector': suggestion.sector,
                'sub_sector': suggestion.sub_sector,
                'emergency': suggestion.emergency,
                'related_programs': suggestion.related_programs,
                'reason': suggestion.reason,
                'additional_notes': suggestion.additional_notes,
                'admin_notes': suggestion.admin_notes,
                'reviewed_by': suggestion.reviewed_by.name if suggestion.reviewed_by else None,
                'is_new_indicator': suggestion.is_new_indicator
            })

        return json_response({
            'suggestions': suggestions,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        })

    except Exception as e:
        current_app.logger.error(f"Error retrieving indicator suggestions: {str(e)}")
        return api_error('Failed to retrieve suggestions', 500)


@api_bp.route('/indicator-suggestions/<int:suggestion_id>', methods=['GET'])
@require_api_key(capability=INDICATORS_MANAGE)
@api_rate_limit()
def get_indicator_suggestion(suggestion_id):
    """Get a specific indicator suggestion by ID."""
    try:
        suggestion = IndicatorSuggestion.query.get_or_404(suggestion_id)

        return json_response({
            'id': suggestion.id,
            'submitter_name': suggestion.submitter_name,
            'submitter_email': suggestion.submitter_email,
            'suggestion_type': suggestion.suggestion_type,
            'suggestion_type_display': suggestion.suggestion_type_display,
            'status': suggestion.status,
            'status_display': suggestion.status_display,
            'submitted_at': suggestion.submitted_at.isoformat() if suggestion.submitted_at else None,
            'reviewed_at': suggestion.reviewed_at.isoformat() if suggestion.reviewed_at else None,
            'indicator_id': suggestion.indicator_id,
            'indicator_name': suggestion.indicator_name,
            'definition': suggestion.definition,
            'type': suggestion.type,
            'unit': suggestion.unit,
            'sector': suggestion.sector,
            'sub_sector': suggestion.sub_sector,
            'emergency': suggestion.emergency,
            'related_programs': suggestion.related_programs,
            'reason': suggestion.reason,
            'additional_notes': suggestion.additional_notes,
            'admin_notes': suggestion.admin_notes,
            'reviewed_by': suggestion.reviewed_by.name if suggestion.reviewed_by else None,
            'is_new_indicator': suggestion.is_new_indicator
        })

    except NotFound:
        raise
    except Exception as e:
        current_app.logger.error(f"Error retrieving indicator suggestion {suggestion_id}: {str(e)}")
        return api_error('Failed to retrieve suggestion', 500)


@api_bp.route('/indicator-suggestions/<int:suggestion_id>/status', methods=['PUT'])
@require_api_key(capability=INDICATORS_MANAGE)
@api_rate_limit()
def update_indicator_suggestion_status(suggestion_id):
    """Update the status of an indicator suggestion.

    Authorization is the key's ``indicators:manage`` permission (enforced before this view
    runs); a key has no user, so there is no per-user admin check.
    """
    try:
        data = get_json_safe()

        if not data or 'status' not in data:
            return api_error('Status is required', 400)

        raw_status = data['status']
        if not isinstance(raw_status, str) or (
            raw_status.strip().lower() not in IndicatorSuggestionStatusValue.values()
            and raw_status.strip().lower() != 'pending review'
        ):
            return api_error(
                'Invalid status',
                400,
                extra={'allowed': list(IndicatorSuggestionStatusValue.values())},
            )
        admin_notes = data.get('admin_notes')
        if admin_notes is not None and (not isinstance(admin_notes, str) or len(admin_notes) > 5000):
            return api_error('admin_notes must be text of at most 5000 characters', 400)

        suggestion = IndicatorSuggestion.query.get_or_404(suggestion_id)
        old_status = suggestion.status

        # Update status
        suggestion.status = IndicatorSuggestionStatusValue.normalize(raw_status)
        suggestion.reviewed_at = utcnow()
        if admin_notes is not None:
            suggestion.admin_notes = admin_notes
        # reviewed_by_user_id stays unset: a key is not a user. The key is recorded in the log.

        db.session.flush()
        principal = get_api_principal()
        current_app.logger.info(
            "Indicator suggestion %s status %s -> %s via API key id=%s (%s)",
            suggestion_id, old_status, suggestion.status,
            getattr(principal, 'api_key_id', None), getattr(principal, 'client_name', None),
        )

        return json_response({
            'message': 'Suggestion status updated successfully',
            'status': suggestion.status,
            'status_display': suggestion.status_display
        })

    except NotFound:
        raise
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error updating indicator suggestion status: {str(e)}")
        return api_error('Failed to update suggestion status', 500)


@api_bp.route('/sectors', methods=['GET'])
@require_api_key(capability=REFERENCE_READ)
@api_rate_limit()
def get_sectors():
    """Get all sectors with their hierarchical structure."""
    try:
        sectors = Sector.query.filter_by(is_active=True).order_by(Sector.display_order, Sector.name).all()

        # Batch-load all active subsectors in a single query, indexed by sector_id
        sector_ids = [s.id for s in sectors]
        all_subsectors = (
            SubSector.query
            .filter(SubSector.sector_id.in_(sector_ids), SubSector.is_active == True)
            .order_by(SubSector.display_order, SubSector.name)
            .all()
        ) if sector_ids else []
        subsectors_by_sector: dict = defaultdict(list)
        for ss in all_subsectors:
            subsectors_by_sector[ss.sector_id].append(ss)

        sectors_data = []
        for sector in sectors:
            subsectors_data = []
            for subsector in subsectors_by_sector.get(sector.id, []):
                multilingual_subsector_names = (
                    subsector.name_translations if isinstance(getattr(subsector, "name_translations", None), dict) else {}
                )
                subsectors_data.append({
                    'id': subsector.id,
                    'name': subsector.name,
                    'description': subsector.description,
                    'display_order': subsector.display_order,
                    'multilingual_names': multilingual_subsector_names
                })

            multilingual_sector_names = (
                sector.name_translations if isinstance(getattr(sector, "name_translations", None), dict) else {}
            )

            sectors_data.append({
                'id': sector.id,
                'name': sector.name,
                'description': sector.description,
                'display_order': sector.display_order,
                'logo_url': sector_logo_url(sector, external=True, via_api=True),
                'multilingual_names': multilingual_sector_names,
                'subsectors': subsectors_data
            })

        response = json_response({'sectors': sectors_data})
        response.headers['Cache-Control'] = 'public, max-age=300'
        return response

    except Exception as e:
        current_app.logger.error(f"Error retrieving sectors: {str(e)}")
        return api_error('Failed to retrieve sectors', 500)


@api_bp.route('/subsectors', methods=['GET'])
@require_api_key(capability=REFERENCE_READ)
@api_rate_limit()
def get_subsectors():
    """Get all subsectors with their parent sector information."""
    try:
        # Eager-load parent sector to avoid N+1
        from sqlalchemy.orm import joinedload
        subsectors = (
            SubSector.query
            .options(joinedload(SubSector.sector))
            .filter_by(is_active=True)
            .order_by(SubSector.display_order, SubSector.name)
            .all()
        )

        subsectors_data = []
        for subsector in subsectors:
            parent_sector = None
            if subsector.sector:
                multilingual_parent_names = (
                    subsector.sector.name_translations if isinstance(getattr(subsector.sector, "name_translations", None), dict) else {}
                )
                parent_sector = {
                    'id': subsector.sector.id,
                    'name': subsector.sector.name,
                    'multilingual_names': multilingual_parent_names
                }

            multilingual_subsector_names = (
                subsector.name_translations if isinstance(getattr(subsector, "name_translations", None), dict) else {}
            )
            subsectors_data.append({
                'id': subsector.id,
                'name': subsector.name,
                'description': subsector.description,
                'display_order': subsector.display_order,
                'parent_sector': parent_sector,
                'multilingual_names': multilingual_subsector_names
            })

        response = json_response({'subsectors': subsectors_data})
        response.headers['Cache-Control'] = 'public, max-age=300'
        return response

    except Exception as e:
        current_app.logger.error(f"Error retrieving subsectors: {str(e)}")
        return api_error('Failed to retrieve subsectors', 500)


@api_bp.route('/sectors-subsectors', methods=['GET'])
@require_api_key(capability=REFERENCE_READ)
@api_rate_limit()
def get_sectors_subsectors():
    """Get all sectors and subsectors with their logos and hierarchical structure for the frontend."""
    try:
        sectors = Sector.query.filter_by(is_active=True).order_by(Sector.display_order, Sector.name).all()

        # Batch-load all active subsectors in one query
        sector_ids = [s.id for s in sectors]
        all_subsectors = (
            SubSector.query
            .filter(SubSector.sector_id.in_(sector_ids), SubSector.is_active == True)
            .order_by(SubSector.display_order, SubSector.name)
            .all()
        ) if sector_ids else []
        subsectors_by_sector: dict = defaultdict(list)
        for ss in all_subsectors:
            subsectors_by_sector[ss.sector_id].append(ss)

        sectors_data = []
        for sector in sectors:
            subsectors_data = []
            for subsector in subsectors_by_sector.get(sector.id, []):
                multilingual_subsector_names = (
                    subsector.name_translations if isinstance(getattr(subsector, "name_translations", None), dict) else {}
                )
                subsectors_data.append({
                    'id': subsector.id,
                    'name': subsector.name,
                    'description': subsector.description,
                    'display_order': subsector.display_order,
                    'multilingual_names': multilingual_subsector_names
                })

            multilingual_sector_names = (
                sector.name_translations if isinstance(getattr(sector, "name_translations", None), dict) else {}
            )

            sectors_data.append({
                'id': sector.id,
                'name': sector.name,
                'description': sector.description,
                'display_order': sector.display_order,
                'logo_url': sector_logo_url(sector, external=True, via_api=True),
                'icon_class': sector.icon_class,
                'multilingual_names': multilingual_sector_names,
                'subsectors': subsectors_data
            })

        response = json_response({'sectors': sectors_data})
        response.headers['Cache-Control'] = 'public, max-age=300'
        return response

    except Exception as e:
        current_app.logger.error(f"Error retrieving sectors and subsectors: {str(e)}")
        return api_error('Failed to retrieve sectors and subsectors', 500)
