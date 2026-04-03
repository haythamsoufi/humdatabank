from flask import Blueprint, render_template, request
from sqlalchemy import func, case
from datetime import datetime, timedelta
from app.models.api_usage import APIUsage
from app.models import IndicatorBank, Sector, SubSector, FormTemplate, Country, User, Resource
from app import db
from app.routes.admin.shared import admin_permission_required
from flask import current_app
from app.utils.datetime_helpers import utcnow
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_ok, json_server_error
from app.utils.sql_utils import safe_ilike_pattern

bp = Blueprint('api_management', __name__, url_prefix='/admin')

@bp.route('/api-management')
@admin_permission_required('admin.api.manage')
def api_management():
    # Define the available API endpoints
    api_endpoints = [
        {
            'path': '/api/v1/submissions',
            'method': 'GET',
            'description': 'Get a list of all submissions with optional filtering'
        },
        {
            'path': '/api/v1/submissions/{submission_id}',
            'method': 'GET',
            'description': 'Get detailed information about a specific submission'
        },
        {
            'path': '/api/v1/templates',
            'method': 'GET',
            'description': 'Get a list of all form templates with optional filtering'
        },
        {
            'path': '/api/v1/templates/{template_id}',
            'method': 'GET',
            'description': 'Get detailed structure of a specific template (pages, sections, items)'
        },
        {
            'path': '/api/v1/templates/{template_id}/data',
            'method': 'GET',
            'description': 'Get all form data for a specific template'
        },
        {
            'path': '/api/v1/form-items',
            'method': 'GET',
            'description': 'Get form items with optional filtering'
        },
        {
            'path': '/api/v1/form-items/{item_id}',
            'method': 'GET',
            'description': 'Get details for a specific form item'
        },
        {
            'path': '/api/v1/lookup-lists',
            'method': 'GET',
            'description': 'Get lookup lists used for dynamic options'
        },
        {
            'path': '/api/v1/lookup-lists/{list_id}',
            'method': 'GET',
            'description': 'Get details and rows for a specific lookup list'
        },
        {
            'path': '/api/v1/countries/{country_id}/data',
            'method': 'GET',
            'description': 'Get all form data for a specific country'
        },
        {
            'path': '/api/v1/countrymap',
            'method': 'GET',
            'description': 'Get a list of all available countries'
        },
        {
            'path': '/api/v1/nationalsocietymap',
            'method': 'GET',
            'description': 'Get a list of all available national societies'
        },
        {
            'path': '/api/v1/publications',
            'method': 'GET',
            'description': 'Get a paginated list of publications with optional search'
        },
        {
            'path': '/api/v1/indicator-bank',
            'method': 'GET',
            'description': 'Get a list of all indicators with optional filters'
        },
        {
            'path': '/api/v1/indicator-bank/{indicator_id}',
            'method': 'GET',
            'description': 'Get details for a specific indicator by ID'
        },
        {
            'path': '/api/v1/data',
            'method': 'GET',
            'description': 'Get all form data with optional filtering'
        },
        {
            'path': '/api/v1/data/tables',
            'method': 'GET',
            'description': 'Get denormalized data rows plus related form item and country tables',
            'featured': True
        },
        {
            'path': '/api/v1/users',
            'method': 'GET',
            'description': 'Get a list of all users with optional filtering'
        },
        {
            'path': '/api/v1/users/{user_id}',
            'method': 'GET',
            'description': 'Get details of a specific user by ID'
        },
        {
            'path': '/api/v1/assigned-forms',
            'method': 'GET',
            'description': 'Get assigned form IDs and their associated country IDs'
        },
        {
            'path': '/api/v1/submitted-documents',
            'method': 'GET',
            'description': 'Get submitted documents with optional filtering by country, type, and status'
        }
    ]

    # Calculate statistics for each endpoint
    for endpoint in api_endpoints:
        # Build a filter pattern that ignores any path parameters in curly braces
        filter_prefix = endpoint['path'].split('{')[0]
        endpoint_stats = APIUsage.query.filter(APIUsage.api_endpoint.like(f"{filter_prefix}%")).with_entities(
            func.count().label('total_requests'),
            func.avg(APIUsage.response_time).label('avg_response_time'),
            func.sum(case((APIUsage.status_code < 400, 1), else_=0)).label('successful_requests')
        ).first()

        endpoint['total_requests'] = endpoint_stats.total_requests if endpoint_stats else 0
        endpoint['avg_response_time'] = float(endpoint_stats.avg_response_time) if endpoint_stats and endpoint_stats.avg_response_time else 0
        endpoint['success_rate'] = (endpoint_stats.successful_requests / endpoint_stats.total_requests * 100) if endpoint_stats and endpoint_stats.total_requests > 0 else 100

    # Sort endpoints by total_requests in descending order
    api_endpoints.sort(key=lambda x: x['total_requests'], reverse=True)

    # Fetch real data for parameter dropdowns
    templates = FormTemplate.query.all()
    # Sort by name (from published version) in Python since it's a property
    templates.sort(key=lambda t: t.name if t.name else "")
    countries = Country.query.order_by(Country.name.asc()).all()
    users = User.query.order_by(User.name.asc()).all()
    publications = Resource.query.order_by(Resource.default_title.asc()).all()

    # Fetch dropdown options for Indicator Bank filters
    sector_options = [s.name for s in Sector.query.order_by(Sector.name.asc()).all()]
    sub_sector_options = [ss.name for ss in SubSector.query.order_by(SubSector.name.asc()).all()]
    type_options = [t[0] for t in db.session.query(IndicatorBank.type).distinct().order_by(IndicatorBank.type.asc()).all()]

    # Get overall statistics
    total_requests = APIUsage.query.count()
    avg_response_time = db.session.query(func.avg(APIUsage.response_time)).scalar() or 0
    success_rate = (
        APIUsage.query.filter(APIUsage.status_code < 400).count() / total_requests * 100
        if total_requests > 0 else 100
    )
    unique_ips = APIUsage.query.with_entities(APIUsage.ip_address).distinct().count()

    # Get recent activity
    recent_activity = APIUsage.query.order_by(APIUsage.timestamp.desc()).limit(50).all()

    # Generate chart data for the last 24 hours
    base_query = APIUsage.query.filter(APIUsage.api_endpoint.like('/api/%'))
    last_24h = utcnow() - timedelta(days=1)
    stats = base_query.filter(APIUsage.timestamp >= last_24h).all()

    # Group by hour using Python
    hour_counts = {}
    for record in stats:
        hour = record.timestamp.strftime('%H:00')
        hour_counts[hour] = hour_counts.get(hour, 0) + 1

    # Fill in missing hours with zeros
    all_hours = {}
    current = utcnow()
    for i in range(24):
        hour = (current - timedelta(hours=i)).strftime('%H:00')
        all_hours[hour] = hour_counts.get(hour, 0)

    chart_data = [{'label': h, 'count': c} for h, c in reversed(all_hours.items())]

    return render_template('admin/api_management.html',
                         endpoints=api_endpoints,
                         total_requests=total_requests,
                         avg_response_time=avg_response_time,
                         success_rate=success_rate,
                         unique_ips=unique_ips,
                         recent_activity=recent_activity,
                         chart_data=chart_data,
                         sector_options=sector_options,
                         sub_sector_options=sub_sector_options,
                         type_options=type_options,
                         templates=templates,
                         countries=countries,
                         users=users,
                         publications=publications)

@bp.route('/api-management/stats')
@admin_permission_required('admin.api.manage')
def api_stats():
    try:
        period = request.args.get('period', 'daily')
        endpoint = request.args.get('endpoint', 'all')
        current_app.logger.debug(f"Fetching stats for period: {period}, endpoint: {endpoint}")

        # Debug: Check total records in APIUsage table
        total_records = APIUsage.query.count()
        current_app.logger.debug(f"Total APIUsage records: {total_records}")

        # Debug: Show recent records
        recent_records = APIUsage.query.order_by(APIUsage.timestamp.desc()).limit(5).all()
        for record in recent_records:
            current_app.logger.debug(f"Recent record: {record.api_endpoint} at {record.timestamp}")

        # Get all API requests that start with /api/
        base_query = APIUsage.query.filter(APIUsage.api_endpoint.like('/api/%'))

        # Filter by specific endpoint if requested
        if endpoint != 'all':
            base_query = base_query.filter(APIUsage.api_endpoint.ilike(safe_ilike_pattern(endpoint)))
            current_app.logger.debug(f"Filtering by endpoint: {endpoint}")

        api_records = base_query.all()
        current_app.logger.debug(f"API records found: {len(api_records)}")

        if period == 'daily':
            # Get hourly stats for the last 24 hours
            last_24h = utcnow() - timedelta(days=1)
            current_app.logger.debug(f"Looking for records since: {last_24h}")

            stats = base_query.filter(APIUsage.timestamp >= last_24h).all()
            current_app.logger.debug(f"Records in last 24h: {len(stats)}")

            # Group by hour using Python
            hour_counts = {}
            for record in stats:
                hour = record.timestamp.strftime('%H:00')
                hour_counts[hour] = hour_counts.get(hour, 0) + 1
                current_app.logger.debug(f"Record at {record.timestamp} -> hour {hour}")

            current_app.logger.debug(f"Hour counts: {hour_counts}")

            # Fill in missing hours with zeros
            all_hours = {}
            current = utcnow()
            for i in range(24):
                hour = (current - timedelta(hours=i)).strftime('%H:00')
                all_hours[hour] = hour_counts.get(hour, 0)

            formatted_stats = [{'label': h, 'count': c} for h, c in reversed(all_hours.items())]

        elif period == 'weekly':
            # Get daily stats for the last 7 days
            last_7d = utcnow() - timedelta(days=7)
            stats = base_query.filter(APIUsage.timestamp >= last_7d).all()

            # Group by day
            day_counts = {}
            for record in stats:
                day = record.timestamp.strftime('%Y-%m-%d')
                day_counts[day] = day_counts.get(day, 0) + 1

            # Fill in missing days with zeros
            all_days = {}
            current = utcnow()
            for i in range(7):
                day = (current - timedelta(days=i)).strftime('%Y-%m-%d')
                all_days[day] = day_counts.get(day, 0)

            formatted_stats = [{'label': d, 'count': c} for d, c in reversed(all_days.items())]

        elif period == 'monthly':
            # Get daily stats for the last 30 days
            last_30d = utcnow() - timedelta(days=30)
            stats = base_query.filter(APIUsage.timestamp >= last_30d).all()

            # Group by day
            day_counts = {}
            for record in stats:
                day = record.timestamp.strftime('%Y-%m-%d')
                day_counts[day] = day_counts.get(day, 0) + 1

            # Fill in missing days with zeros
            all_days = {}
            current = utcnow()
            for i in range(30):
                day = (current - timedelta(days=i)).strftime('%Y-%m-%d')
                all_days[day] = day_counts.get(day, 0)

            formatted_stats = [{'label': d, 'count': c} for d, c in reversed(all_days.items())]

        else:  # yearly
            # Get monthly stats for the last year
            last_year = utcnow() - timedelta(days=365)
            stats = base_query.filter(APIUsage.timestamp >= last_year).all()

            # Group by month
            month_counts = {}
            for record in stats:
                month = record.timestamp.strftime('%Y-%m')
                month_counts[month] = month_counts.get(month, 0) + 1

            # Fill in missing months with zeros
            all_months = {}
            current = utcnow()
            for i in range(12):
                month = (current - timedelta(days=i*30)).strftime('%Y-%m')
                all_months[month] = month_counts.get(month, 0)

            formatted_stats = [{'label': m, 'count': c} for m, c in reversed(all_months.items())]

        current_app.logger.debug(f"Found {len(stats)} records")
        current_app.logger.debug(f"Formatted stats: {formatted_stats}")

        return json_ok(stats=formatted_stats)

    except Exception as e:
        current_app.logger.error(f"Error in api_stats: {str(e)}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)
