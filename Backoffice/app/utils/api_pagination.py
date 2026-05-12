# ========== API Pagination Utilities ==========
"""
Pagination and query building functions for API routes.
Extracted from routes/api.py for better organization and reusability.
"""

from datetime import datetime
from flask import request, current_app
from sqlalchemy import desc, asc, literal
from app import db
from app.models import FormData, PublicSubmission
from app.utils.api_helpers import MAX_PER_PAGE, DEFAULT_PER_PAGE, DEFAULT_PAGE


def validate_pagination_params(request_args, default_per_page=None, max_per_page=None):
    """
    Validate and sanitize pagination parameters.

    SECURITY: Prevents DoS attacks via large pagination requests.
    Ensures page >= 1 and per_page is within reasonable limits.

    :param request_args: Flask request.args or similar dict-like object
    :param default_per_page: Override default per_page (default: DEFAULT_PER_PAGE)
    :param max_per_page: Override max per_page cap (default: MAX_PER_PAGE). Use 100 for admin UI.
    """
    _default = default_per_page if default_per_page is not None else DEFAULT_PER_PAGE
    _max = max_per_page if max_per_page is not None else MAX_PER_PAGE
    try:
        page = request_args.get('page', DEFAULT_PAGE, type=int)
        if page is None or page < 1:
            page = DEFAULT_PAGE
        page = max(1, int(page))
    except (ValueError, TypeError):
        page = DEFAULT_PAGE

    try:
        per_page = request_args.get('per_page', _default, type=int)
        if per_page is None or per_page < 1:
            per_page = _default
        per_page = min(max(1, int(per_page)), _max)
    except (ValueError, TypeError):
        per_page = _default

    return page, per_page


def parse_date_range(request_args):
    """
    Parse and validate date range parameters.

    SECURITY: Validates date formats to prevent injection and malformed requests.
    Returns None for invalid dates instead of raising exceptions.
    """
    date_from = None
    date_to = None

    date_from_str = request_args.get('date_from', type=str)
    date_to_str = request_args.get('date_to', type=str)

    # Validate string length to prevent DoS
    MAX_DATE_STRING_LENGTH = 50

    if date_from_str:
        # Sanitize input length
        if len(date_from_str) > MAX_DATE_STRING_LENGTH:
            current_app.logger.warning(f"date_from parameter too long: {len(date_from_str)} chars")
            date_from = None
        else:
            try:
                # Support ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS
                if 'T' in date_from_str:
                    date_from = datetime.fromisoformat(date_from_str.replace('Z', '+00:00'))
                else:
                    date_from = datetime.strptime(date_from_str, '%Y-%m-%d')
                    # Set to start of day
                    date_from = date_from.replace(hour=0, minute=0, second=0, microsecond=0)
            except (ValueError, TypeError) as e:
                current_app.logger.warning(f"Invalid date_from format: {date_from_str}, error: {e}")
                date_from = None

    if date_to_str:
        # Sanitize input length
        if len(date_to_str) > MAX_DATE_STRING_LENGTH:
            current_app.logger.warning(f"date_to parameter too long: {len(date_to_str)} chars")
            date_to = None
        else:
            try:
                # Support ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS
                if 'T' in date_to_str:
                    date_to = datetime.fromisoformat(date_to_str.replace('Z', '+00:00'))
                else:
                    date_to = datetime.strptime(date_to_str, '%Y-%m-%d')
                    # Set to end of day
                    date_to = date_to.replace(hour=23, minute=59, second=59, microsecond=999999)
            except (ValueError, TypeError) as e:
                current_app.logger.warning(f"Invalid date_to format: {date_to_str}, error: {e}")
                date_to = None

    # Validate date range makes sense
    if date_from and date_to and date_from > date_to:
        current_app.logger.warning(f"Invalid date range: date_from ({date_from}) > date_to ({date_to})")
        return None, None

    return date_from, date_to


def get_sort_params(request_args, default_sort='submitted_at', default_order='desc'):
    """
    Parse and validate sort parameters.

    Args:
        request_args: Request arguments
        default_sort: Default sort field
        default_order: Default sort order ('asc' or 'desc')

    Returns:
        tuple: (sort_field: str, sort_order: str, sort_column: SQLAlchemy column or None)
    """
    sort_field = request_args.get('sort', default_sort, type=str).strip().lower()
    sort_order = request_args.get('order', default_order, type=str).strip().lower()

    # Validate sort order
    if sort_order not in ['asc', 'desc']:
        sort_order = default_order

    # Map sort fields to SQLAlchemy columns
    # Note: These will be applied in the query building functions
    valid_sort_fields = {
        'submitted_at': 'submitted_at',
        'template_id': 'template_id',
        'country_id': 'country_id',
        'period_name': 'period_name',
        'created_at': 'created_at',
        'updated_at': 'updated_at',
    }

    if sort_field not in valid_sort_fields:
        sort_field = default_sort

    return sort_field, sort_order, valid_sort_fields.get(sort_field)


def validate_data_endpoint_params(request_args):
    """
    Validate and sanitize query parameters for data endpoints.

    SECURITY: Validates all input parameters to prevent injection and DoS attacks.
    """
    # Validate pagination with error handling
    try:
        page = request_args.get('page', 1, type=int)
        if page is None or page < 1:
            page = 1
        page = max(1, int(page))
    except (ValueError, TypeError):
        page = 1

    try:
        per_page = request_args.get('per_page', 20, type=int)
        if per_page is None or per_page < 1:
            per_page = 20
        per_page = min(max(1, int(per_page)), MAX_PER_PAGE)
    except (ValueError, TypeError):
        per_page = 20

    # Validate disagg parameter - only allow specific values
    disagg_param = request_args.get('disagg', default=None, type=str)
    include_disagg = False
    if disagg_param is not None:
        disagg_str = str(disagg_param).strip().lower()
        include_disagg = disagg_str in ['1', 'true', 'yes', 'y']

    # Validate include_full_info parameter (default False for performance with large datasets)
    full_info_param = request_args.get('include_full_info', default=None, type=str)
    include_full_info = False
    if full_info_param is not None:
        full_info_str = str(full_info_param).strip().lower()
        include_full_info = full_info_str in ['1', 'true', 'yes', 'y']

    return {
        'page': page,
        'per_page': per_page,
        'include_disagg': include_disagg,
        'include_full_info': include_full_info
    }


def build_pagination_queries(assigned_form_data_query, public_form_data_query, submission_type=None):
    """Build lightweight pagination queries for UNION.

    Args:
        assigned_form_data_query: Query for assigned form data
        public_form_data_query: Query for public form data
        submission_type: Filter by submission type ('assigned', 'public', or None for both)

    Returns:
        tuple: (assigned_ids_q, public_ids_q) - Queries for pagination, may be None
    """
    assigned_ids_q = None
    public_ids_q = None

    # If submission_type is None, include both types (default behavior)
    if submission_type is None or submission_type != 'public':
        assigned_ids_q = assigned_form_data_query.with_entities(
            FormData.id.label('id'),
            FormData.submitted_at.label('submitted_at'),
            literal('assigned').label('submission_type')
        )

    if submission_type is None or submission_type != 'assigned':
        public_ids_q = public_form_data_query.with_entities(
            FormData.id.label('id'),
            PublicSubmission.submitted_at.label('submitted_at'),
            literal('public').label('submission_type')
        )

    return assigned_ids_q, public_ids_q


def get_paginated_data_ids(assigned_ids_q, public_ids_q, page, per_page, paginate=True, sort_field='submitted_at', sort_order='desc'):
    """Get paginated data IDs from UNION queries.

    Args:
        assigned_ids_q: Query for assigned submission IDs
        public_ids_q: Query for public submission IDs
        page: Page number (only used if paginate=True)
        per_page: Items per page (only used if paginate=True)
        paginate: If False, returns all rows without pagination
        sort_field: Field to sort by (default: 'submitted_at')
        sort_order: Sort order 'asc' or 'desc' (default: 'desc')

    Returns:
        tuple: (page_rows, total_items)
    """
    # Compute total count cheaply per-branch
    total_items = 0
    if assigned_ids_q is not None:
        total_items += assigned_ids_q.order_by(None).count()
    if public_ids_q is not None:
        total_items += public_ids_q.order_by(None).count()

    # Determine sort column and order
    # For UNION queries, we can only sort by fields that exist in both queries
    # Default to submitted_at which is always available
    if sort_field == 'submitted_at':
        sort_column = 'submitted_at'
    else:
        # For other fields, we'd need to join, so default to submitted_at
        sort_column = 'submitted_at'
        current_app.logger.debug(f"Sort field '{sort_field}' not available in UNION, defaulting to submitted_at")

    order_func = desc if sort_order == 'desc' else asc

    if not paginate:
        # Return all rows without pagination
        if assigned_ids_q is not None and public_ids_q is not None:
            combined = assigned_ids_q.union_all(public_ids_q).subquery()
            page_rows = (
                db.session.query(
                    combined.c.id, combined.c.submitted_at, combined.c.submission_type
                )
                .order_by(order_func(getattr(combined.c, sort_column)))
                .all()
            )
        else:
            only_q = assigned_ids_q or public_ids_q
            if only_q is None:
                page_rows = []
            else:
                subq = only_q.subquery()
                page_rows = (
                    db.session.query(subq.c.id, subq.c.submitted_at, subq.c.submission_type)
                    .order_by(order_func(getattr(subq.c, sort_column)))
                    .all()
                )
        return page_rows, total_items

    # Build combined ordered page of ids
    offset = (page - 1) * per_page

    if assigned_ids_q is not None and public_ids_q is not None:
        combined = assigned_ids_q.union_all(public_ids_q).subquery()
        page_rows = (
            db.session.query(
                combined.c.id, combined.c.submitted_at, combined.c.submission_type
            )
            .order_by(order_func(getattr(combined.c, sort_column)))
            .offset(offset)
            .limit(per_page)
            .all()
        )
    else:
        only_q = assigned_ids_q or public_ids_q
        if only_q is None:
            page_rows = []
        else:
            subq = only_q.subquery()
            page_rows = (
                db.session.query(subq.c.id, subq.c.submitted_at, subq.c.submission_type)
                .order_by(order_func(getattr(subq.c, sort_column)))
                .offset(offset)
                .limit(per_page)
                .all()
            )

    return page_rows, total_items


def fetch_paginated_rows(assigned_form_data_query, public_form_data_query, page_rows):
    """Fetch full ORM objects for paginated IDs.

    Note: This function assumes eager loading is already applied to the queries
    (e.g., via query_form_data with preload=True). Adding additional eager loading
    here would cause loader strategy conflicts.
    """
    assigned_ids = [r.id for r in page_rows if r.submission_type == 'assigned']
    public_ids = [r.id for r in page_rows if r.submission_type == 'public']

    assigned_rows = []
    public_rows = []
    if assigned_ids:
        # Query already has eager loading from query_form_data, just filter by IDs
        assigned_rows = (
            assigned_form_data_query
            .filter(FormData.id.in_(assigned_ids))
            .all()
        )
    if public_ids:
        # Query already has eager loading from query_form_data, just filter by IDs
        public_rows = (
            public_form_data_query
            .filter(FormData.id.in_(public_ids))
            .all()
        )

    assigned_map = {row.id: row for row in assigned_rows}
    public_map = {row.id: row for row in public_rows}

    return assigned_map, public_map


def build_paginated_response(paginated_data, total_items, page, per_page):
    """Build standardized paginated response format.

    Args:
        paginated_data: List of serialized data items
        total_items: Total number of items across all pages
        page: Current page number
        per_page: Items per page

    Returns:
        dict: Paginated response with data, total_items, total_pages, current_page, per_page
    """
    return {
        'data': paginated_data,
        'total_items': total_items,
        'total_pages': (total_items + per_page - 1) // per_page if per_page else 1,
        'current_page': page,
        'per_page': per_page
    }
