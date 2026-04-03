from app.utils.transactions import request_transaction_rollback
from contextlib import suppress
# Backoffice/app/routes/api/indicators.py
from app.utils.datetime_helpers import utcnow
from app.utils.sql_utils import safe_ilike_pattern
"""
Indicator Bank, Suggestions, and Sector API endpoints.
Part of the /api/v1 blueprint.
"""

from flask import request, current_app
import uuid
from sqlalchemy import desc
from datetime import datetime

# Import the API blueprint from parent
from app.routes.api import api_bp

# Import models
from app.models import IndicatorBank, IndicatorSuggestion, Sector, SubSector
from app.utils.auth import require_api_key
from app import db

# Import utility functions
from app.utils.api_helpers import json_response, api_error, get_json_safe
from app.utils.api_responses import require_json_data, require_json_keys
from app.utils.form_localization import get_localized_indicator_type, get_localized_indicator_unit

_SECTOR_LEVELS = ('primary', 'secondary', 'tertiary')


def _get_localized_type_unit(indicator, requested_locale):
    """Return (localized_type, localized_unit) for an indicator, optionally under requested_locale."""
    localized_type = None
    localized_unit = None
    if indicator.type:
        localized_type = get_localized_indicator_type(indicator.type)
    if indicator.unit:
        localized_unit = get_localized_indicator_unit(indicator.unit)
    if requested_locale:
        try:
            from flask_babel import force_locale
            with force_locale(requested_locale):
                if indicator.type:
                    localized_type = get_localized_indicator_type(indicator.type)
                if indicator.unit:
                    localized_unit = get_localized_indicator_unit(indicator.unit)
        except Exception as e:
            current_app.logger.debug("force_locale for indicator %s failed: %s", indicator.id, e)
    return localized_type, localized_unit


def _build_sector_subsector_names(indicator, sectors_dict, subsectors_dict):
    """Build sector and sub_sector name dicts (primary/secondary/tertiary) from pre-fetched id->name maps."""
    sector_names = {}
    subsector_names = {}
    for level in _SECTOR_LEVELS:
        sector_names[level] = (
            sectors_dict.get(indicator.sector[level]) if indicator.sector and level in indicator.sector else None
        )
        subsector_names[level] = (
            subsectors_dict.get(indicator.sub_sector[level]) if indicator.sub_sector and level in indicator.sub_sector else None
        )
    return {'sector': sector_names, 'sub_sector': subsector_names}


@api_bp.route('/indicator-bank', methods=['GET'])
@require_api_key
def get_indicator_bank():
    """
    API endpoint to retrieve all indicators from the indicator bank.
    Authentication: API key in Authorization header (Bearer token).
    Query Parameters:
        - search: Search query for indicator name or definition
        - type: Filter by indicator type
        - sector: Filter by sector
        - sub_sector: Filter by sub-sector
        - emergency: Filter by emergency type
        - archived: Filter by archived status (true=only archived, false=only non-archived, omit=all indicators)
        - locale: Optional locale code for localized type and unit (e.g., 'en', 'fr', 'es', 'ar', 'zh', 'ru', 'hi')
    Returns:
        JSON object containing:
        - indicators: List of all indicator bank objects
    """
    try:
        current_app.logger.debug("Entering indicator bank API endpoint")

        # Get locale for localization (default to 'en')
        requested_locale = request.args.get('locale', default='', type=str).strip().lower()
        if requested_locale:
            from flask_babel import force_locale
            # Set locale context if requested
            with suppress(Exception):  # Fallback to default locale
                with force_locale(requested_locale):
                    pass  # Locale will be set in context

        # Get filter parameters
        search_query = request.args.get('search', default='', type=str).strip()
        indicator_type = request.args.get('type', default='', type=str).strip()
        sector = request.args.get('sector', default='', type=str).strip()
        sub_sector = request.args.get('sub_sector', default='', type=str).strip()
        emergency = request.args.get('emergency', default='', type=str).strip()
        archived_param = request.args.get('archived', default=None)

        # Build base query
        query = IndicatorBank.query

        # Apply archived filter
        if archived_param is not None:
            if archived_param.lower() == 'true':
                query = query.filter(IndicatorBank.archived == True)
            elif archived_param.lower() == 'false':
                query = query.filter(IndicatorBank.archived == False)
            # If archived_param is neither 'true' nor 'false', no filter is applied (returns all)

        if search_query:
            safe_pattern = safe_ilike_pattern(search_query)
            query = query.filter(
                db.or_(
                    IndicatorBank.name.ilike(safe_pattern),
                    IndicatorBank.definition.ilike(safe_pattern)
                )
            )

        if indicator_type:
            query = query.filter(IndicatorBank.type.ilike(safe_ilike_pattern(indicator_type)))

        if sector:
            # Convert sector name to ID for filtering
            sector_obj = Sector.query.filter_by(name=sector, is_active=True).first()
            if sector_obj:
                # Use JSONB operators for proper filtering
                query = query.filter(
                    db.or_(
                        IndicatorBank.sector['primary'].astext == str(sector_obj.id),
                        IndicatorBank.sector['secondary'].astext == str(sector_obj.id),
                        IndicatorBank.sector['tertiary'].astext == str(sector_obj.id)
                    )
                )

        if sub_sector:
            # Convert sub-sector name to ID for filtering
            subsector_obj = SubSector.query.filter_by(name=sub_sector, is_active=True).first()
            if subsector_obj:
                # Use JSONB operators for proper filtering
                query = query.filter(
                    db.or_(
                        IndicatorBank.sub_sector['primary'].astext == str(subsector_obj.id),
                        IndicatorBank.sub_sector['secondary'].astext == str(subsector_obj.id),
                        IndicatorBank.sub_sector['tertiary'].astext == str(subsector_obj.id)
                    )
                )

        if emergency:
            query = query.filter(IndicatorBank.emergency.ilike(safe_ilike_pattern(emergency)))

        # Order by name and get all results
        indicators = query.order_by(IndicatorBank.name.asc()).all()

        # OPTIMIZATION: Pre-fetch all sectors and subsectors to avoid N+1 queries
        # Collect all unique sector and subsector IDs from all indicators
        sector_ids = set()
        subsector_ids = set()

        for indicator in indicators:
            if indicator.sector:
                for level in ['primary', 'secondary', 'tertiary']:
                    sector_id = indicator.sector.get(level)
                    if sector_id:
                        sector_ids.add(sector_id)

            if indicator.sub_sector:
                for level in ['primary', 'secondary', 'tertiary']:
                    subsector_id = indicator.sub_sector.get(level)
                    if subsector_id:
                        subsector_ids.add(subsector_id)

        # Fetch all sectors and subsectors in batch queries (2 queries total instead of N*6)
        sectors_dict = {}
        if sector_ids:
            sectors = Sector.query.filter(Sector.id.in_(sector_ids)).all()
            sectors_dict = {sector.id: sector.name for sector in sectors}

        subsectors_dict = {}
        if subsector_ids:
            subsectors = SubSector.query.filter(SubSector.id.in_(subsector_ids)).all()
            subsectors_dict = {subsector.id: subsector.name for subsector in subsectors}

        indicators_data = []
        for indicator in indicators:
            localized_type, localized_unit = _get_localized_type_unit(indicator, requested_locale)
            sector_sub = _build_sector_subsector_names(indicator, sectors_dict, subsectors_dict)
            indicators_data.append({
                'id': indicator.id,
                'name': indicator.name,
                'type': indicator.type,
                'localized_type': localized_type,
                'unit': indicator.unit,
                'localized_unit': localized_unit,
                'fdrs_kpi_code': getattr(indicator, 'fdrs_kpi_code', None),
                'definition': indicator.definition,
                'name_translations': indicator.name_translations if hasattr(indicator, 'name_translations') else None,
                'definition_translations': indicator.definition_translations if hasattr(indicator, 'definition_translations') else None,
                'sector': sector_sub['sector'],
                'sub_sector': sector_sub['sub_sector'],
                'emergency': indicator.emergency,
                'related_programs': indicator.related_programs_list,
                'archived': indicator.archived,
                'created_at': indicator.created_at.isoformat() if hasattr(indicator, 'created_at') and indicator.created_at else None,
                'updated_at': indicator.updated_at.isoformat() if hasattr(indicator, 'updated_at') and indicator.updated_at else None
            })

        current_app.logger.debug(f"Indicator bank API returning {len(indicators_data)} items")

        return json_response({
            'indicators': indicators_data
        })

    except Exception as e:
        current_app.logger.error(f"API Error fetching indicator bank: {e}", exc_info=True)
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            f"API Error [ID: {error_id}] fetching indicator bank: {e}",
            exc_info=True,
            extra={'endpoint': '/indicators', 'params': dict(request.args)}
        )
        return api_error("Could not fetch indicator bank data", 500, error_id, None)


@api_bp.route('/indicator-bank/<int:indicator_id>', methods=['GET'])
@require_api_key
def get_indicator_bank_details(indicator_id):
    """
    API endpoint to retrieve details for a specific indicator from the bank.
    Authentication: API key in Authorization header (Bearer token).
    """
    try:
        indicator = IndicatorBank.query.get(indicator_id)

        if not indicator:
            return api_error('Indicator not found', 404)

        # Get locale for localization
        requested_locale = request.args.get('locale', default='', type=str).strip().lower()

        # OPTIMIZATION: Pre-fetch sectors and subsectors for this indicator to avoid N+1 queries
        sector_ids = set()
        subsector_ids = set()

        if indicator.sector:
            for level in ['primary', 'secondary', 'tertiary']:
                sector_id = indicator.sector.get(level)
                if sector_id:
                    sector_ids.add(sector_id)

        if indicator.sub_sector:
            for level in ['primary', 'secondary', 'tertiary']:
                subsector_id = indicator.sub_sector.get(level)
                if subsector_id:
                    subsector_ids.add(subsector_id)

        # Fetch sectors and subsectors in batch
        sectors_dict = {}
        if sector_ids:
            sectors = Sector.query.filter(Sector.id.in_(sector_ids)).all()
            sectors_dict = {sector.id: sector.name for sector in sectors}

        subsectors_dict = {}
        if subsector_ids:
            subsectors = SubSector.query.filter(SubSector.id.in_(subsector_ids)).all()
            subsectors_dict = {subsector.id: subsector.name for subsector in subsectors}

        localized_type, localized_unit = _get_localized_type_unit(indicator, requested_locale)
        sector_sub = _build_sector_subsector_names(indicator, sectors_dict, subsectors_dict)
        indicator_data = {
            'id': indicator.id,
            'name': indicator.name,
            'type': indicator.type,
            'localized_type': localized_type,
            'unit': indicator.unit,
            'localized_unit': localized_unit,
            'fdrs_kpi_code': getattr(indicator, 'fdrs_kpi_code', None),
            'definition': indicator.definition,
            'name_translations': indicator.name_translations if hasattr(indicator, 'name_translations') else None,
            'definition_translations': indicator.definition_translations if hasattr(indicator, 'definition_translations') else None,
            'sector': sector_sub['sector'],
            'sub_sector': sector_sub['sub_sector'],
            'emergency': indicator.emergency,
            'related_programs': indicator.related_programs_list,
            'archived': indicator.archived,
            'created_at': indicator.created_at.isoformat() if hasattr(indicator, 'created_at') and indicator.created_at else None,
            'updated_at': indicator.updated_at.isoformat() if hasattr(indicator, 'updated_at') and indicator.updated_at else None
        }

        return json_response(indicator_data)

    except Exception as e:
        current_app.logger.error(f"API Error fetching indicator {indicator_id}: {e}", exc_info=True)
        return api_error("Could not fetch indicator details", 500)


@api_bp.route('/indicator-suggestions', methods=['POST'])
@require_api_key
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
            from app.utils.email_service import send_suggestion_confirmation_email, send_admin_notification_email
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
@require_api_key
def get_indicator_suggestions():
    """Get all indicator suggestions (admin only)."""
    try:
        # Get query parameters
        from app.utils.api_pagination import validate_pagination_params
        status = request.args.get('status')
        suggestion_type = request.args.get('suggestion_type')
        page, per_page = validate_pagination_params(request.args, default_per_page=20)

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
@require_api_key
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

    except Exception as e:
        current_app.logger.error(f"Error retrieving indicator suggestion {suggestion_id}: {str(e)}")
        return api_error('Failed to retrieve suggestion', 500)


@api_bp.route('/indicator-suggestions/<int:suggestion_id>/status', methods=['PUT'])
@require_api_key
def update_indicator_suggestion_status(suggestion_id):
    """Update the status of an indicator suggestion (admin only)."""
    try:
        data = get_json_safe()

        if not data or 'status' not in data:
            return api_error('Status is required', 400)

        suggestion = IndicatorSuggestion.query.get_or_404(suggestion_id)

        # Update status
        suggestion.status = data['status']
        suggestion.reviewed_at = utcnow()
        suggestion.admin_notes = data.get('admin_notes', suggestion.admin_notes)

        # If status is being updated, record who reviewed it
        # Note: This would need to be enhanced to get the current user from the API key
        # For now, we'll leave reviewed_by_user_id as None

        db.session.flush()

        return json_response({
            'message': 'Suggestion status updated successfully',
            'status': suggestion.status,
            'status_display': suggestion.status_display
        })

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error updating indicator suggestion status: {str(e)}")
        return api_error('Failed to update suggestion status', 500)


@api_bp.route('/sectors', methods=['GET'])
@require_api_key
def get_sectors():
    """Get all sectors with their hierarchical structure."""
    try:
        sectors = Sector.query.filter_by(is_active=True).order_by(Sector.display_order, Sector.name).all()

        sectors_data = []
        for sector in sectors:
            # Get subsectors for this sector
            subsectors = SubSector.query.filter_by(sector_id=sector.id, is_active=True).order_by(SubSector.display_order, SubSector.name).all()

            subsectors_data = []
            for subsector in subsectors:
                # Return translations dict only (fresh start; no legacy per-language columns).
                multilingual_subsector_names = (
                    subsector.name_translations if isinstance(getattr(subsector, "name_translations", None), dict) else {}
                )
                subsectors_data.append({
                    'id': subsector.id,
                    'name': subsector.name,
                    'description': subsector.description,
                    'display_order': subsector.display_order,
                    'logo_url': f"{request.host_url.rstrip('/')}/api/v1/uploads/subsectors/{subsector.logo_filename}" if subsector.logo_filename else None,
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
                'logo_url': f"{request.host_url.rstrip('/')}/api/v1/uploads/sectors/{sector.logo_filename}" if sector.logo_filename else None,
                'multilingual_names': multilingual_sector_names,
                'subsectors': subsectors_data
            })

        return json_response({
            'sectors': sectors_data
        })

    except Exception as e:
        current_app.logger.error(f"Error retrieving sectors: {str(e)}")
        return api_error('Failed to retrieve sectors', 500)


@api_bp.route('/subsectors', methods=['GET'])
@require_api_key
def get_subsectors():
    """Get all subsectors with their parent sector information."""
    try:
        subsectors = SubSector.query.filter_by(is_active=True).order_by(SubSector.display_order, SubSector.name).all()

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
                'logo_url': f"{request.host_url.rstrip('/')}/api/v1/uploads/subsectors/{subsector.logo_filename}" if subsector.logo_filename else None,
                'parent_sector': parent_sector,
                'multilingual_names': multilingual_subsector_names
            })

        return json_response({
            'subsectors': subsectors_data
        })

    except Exception as e:
        current_app.logger.error(f"Error retrieving subsectors: {str(e)}")
        return api_error('Failed to retrieve subsectors', 500)


@api_bp.route('/sectors-subsectors', methods=['GET'])
@require_api_key
def get_sectors_subsectors():
    """Get all sectors and subsectors with their logos and hierarchical structure for the frontend."""
    try:
        sectors = Sector.query.filter_by(is_active=True).order_by(Sector.display_order, Sector.name).all()

        sectors_data = []
        for sector in sectors:
            # Get subsectors for this sector
            subsectors = SubSector.query.filter_by(sector_id=sector.id, is_active=True).order_by(SubSector.display_order, SubSector.name).all()

            subsectors_data = []
            for subsector in subsectors:
                multilingual_subsector_names = (
                    subsector.name_translations if isinstance(getattr(subsector, "name_translations", None), dict) else {}
                )
                subsectors_data.append({
                    'id': subsector.id,
                    'name': subsector.name,
                    'description': subsector.description,
                    'display_order': subsector.display_order,
                    'logo_url': f"{request.host_url.rstrip('/')}/api/v1/uploads/subsectors/{subsector.logo_filename}" if subsector.logo_filename else None,
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
                'logo_url': f"{request.host_url.rstrip('/')}/api/v1/uploads/sectors/{sector.logo_filename}" if sector.logo_filename else None,
                'icon_class': sector.icon_class,  # Fallback icon class
                'multilingual_names': multilingual_sector_names,
                'subsectors': subsectors_data
            })

        return json_response({
            'sectors': sectors_data
        })

    except Exception as e:
        current_app.logger.error(f"Error retrieving sectors and subsectors: {str(e)}")
        return api_error('Failed to retrieve sectors and subsectors', 500)
