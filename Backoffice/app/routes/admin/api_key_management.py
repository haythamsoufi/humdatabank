from app.utils.transactions import request_transaction_rollback
from app.utils.datetime_helpers import utcnow
from app.utils.sql_utils import safe_ilike_pattern
"""
API Key Management Module - Admin UI for managing API keys
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user
from app import db
from datetime import datetime, timedelta
from sqlalchemy import func, desc, case
from app.models.api_key_management import APIKey, APIKeyUsage
from app.forms.system.api_key_forms import APIKeyForm, APIKeyRevokeForm
from app.routes.admin.shared import admin_permission_required
from app.services.user_analytics_service import log_admin_action
from app.utils.api_responses import json_ok, json_ok_result, json_server_error

bp = Blueprint("api_key_management", __name__, url_prefix="/admin/api-management")


@bp.route("/api-keys", methods=["GET"])
@admin_permission_required('admin.api.manage')
def list_api_keys():
    """List all API keys"""
    try:
        # Get filter parameters
        status_filter = request.args.get('status', 'all')  # all, active, revoked, expired
        search_query = request.args.get('search', '').strip()

        # Base query
        query = APIKey.query

        # Apply status filter
        if status_filter == 'active':
            query = query.filter(APIKey.is_active == True, APIKey.is_revoked == False)
            # Also filter out expired keys
            query = query.filter(
                (APIKey.expires_at.is_(None)) | (APIKey.expires_at > utcnow())
            )
        elif status_filter == 'revoked':
            query = query.filter(APIKey.is_revoked == True)
        elif status_filter == 'expired':
            query = query.filter(
                APIKey.expires_at.isnot(None),
                APIKey.expires_at <= utcnow()
            )

        # Apply search filter
        if search_query:
            safe_pattern = safe_ilike_pattern(search_query)
            query = query.filter(
                db.or_(
                    APIKey.client_name.ilike(safe_pattern),
                    APIKey.client_description.ilike(safe_pattern),
                    APIKey.key_prefix.ilike(safe_pattern)
                )
            )

        # Order by creation date (newest first)
        api_keys = query.order_by(desc(APIKey.created_at)).all()

        # Get statistics (use same now for consistency)
        now = utcnow()
        total_keys = APIKey.query.count()
        active_keys = APIKey.query.filter(
            APIKey.is_active == True,
            APIKey.is_revoked == False,
            db.or_(
                APIKey.expires_at.is_(None),
                APIKey.expires_at > now
            )
        ).count()
        revoked_keys = APIKey.query.filter(APIKey.is_revoked == True).count()
        expired_keys = APIKey.query.filter(
            APIKey.expires_at.isnot(None),
            APIKey.expires_at <= now
        ).count()

        return render_template(
            "admin/api_keys/list.html",
            api_keys=api_keys,
            status_filter=status_filter,
            search_query=search_query,
            total_keys=total_keys,
            active_keys=active_keys,
            revoked_keys=revoked_keys,
            expired_keys=expired_keys,
            now=now,  # Pass current time to template for date comparisons
            title="API Key Management"
        )
    except Exception as e:
        current_app.logger.error(f"Error listing API keys: {e}", exc_info=True)
        flash("Error loading API keys. Please try again.", "danger")
        return redirect(url_for('admin.admin_dashboard'))


@bp.route("/api-keys/create", methods=["GET", "POST"])
@admin_permission_required('admin.api.manage')
def create_api_key():
    """Create a new API key"""
    form = APIKeyForm()

    if form.validate_on_submit():
        try:
            # Generate new API key
            full_key, key_hash, key_prefix = APIKey.generate_key()
            key_id = full_key[:32]  # Use first 32 chars as key_id

            # Create API key record
            api_key = APIKey(
                key_id=key_id,
                key_hash=key_hash,
                key_prefix=key_prefix,
                client_name=form.client_name.data,
                client_description=form.client_description.data or None,
                rate_limit_per_minute=form.rate_limit_per_minute.data or 60,
                expires_at=form.expires_at.data if form.expires_at.data else None,
                created_by_user_id=current_user.id,
                is_active=True,
                is_revoked=False
            )

            db.session.add(api_key)
            db.session.flush()

            # Log admin action
            log_admin_action(
                action_type='api_key_create',
                description=f'Created API key for client: {form.client_name.data}',
                target_type='api_key',
                target_id=api_key.id,
                target_description=f'Client: {form.client_name.data}, Prefix: {key_prefix}...',
                new_values={
                    'client_name': form.client_name.data,
                    'key_prefix': key_prefix,
                    'rate_limit_per_minute': form.rate_limit_per_minute.data or 60,
                    'expires_at': (
                        form.expires_at.data.isoformat() if form.expires_at.data else None
                    ),
                },
            )

            # Flash success with the key (only shown once!)
            flash(f"API key created successfully! Please copy it now - it won't be shown again.", "success")

            return render_template(
                "admin/api_keys/create_success.html",
                api_key=api_key,
                full_key=full_key,  # Only shown once on creation
                title="API Key Created"
            )
        except Exception as e:
            current_app.logger.error(f"Error creating API key: {e}", exc_info=True)
            request_transaction_rollback()
            flash("Error creating API key. Please try again.", "danger")

    return render_template(
        "admin/api_keys/create.html",
        form=form,
        title="Create API Key"
    )


@bp.route("/api-keys/<int:key_id>", methods=["GET"])
@admin_permission_required('admin.api.manage')
def view_api_key(key_id):
    """View API key details"""
    try:
        api_key = APIKey.query.get_or_404(key_id)

        # Get usage statistics
        usage_stats = db.session.query(
            func.count(APIKeyUsage.id).label('total_requests'),
            func.min(APIKeyUsage.timestamp).label('first_used'),
            func.max(APIKeyUsage.timestamp).label('last_used'),
            func.avg(APIKeyUsage.response_time_ms).label('avg_response_time')
        ).filter(APIKeyUsage.api_key_id == key_id).first()

        # Get recent usage (last 100 requests)
        recent_usage = APIKeyUsage.query.filter(
            APIKeyUsage.api_key_id == key_id
        ).order_by(desc(APIKeyUsage.timestamp)).limit(100).all()

        # Get usage by endpoint
        usage_by_endpoint = db.session.query(
            APIKeyUsage.endpoint,
            func.count(APIKeyUsage.id).label('count'),
            func.avg(APIKeyUsage.response_time_ms).label('avg_time'),
            func.sum(case((APIKeyUsage.status_code >= 400, 1), else_=0)).label('errors')
        ).filter(
            APIKeyUsage.api_key_id == key_id
        ).group_by(APIKeyUsage.endpoint).order_by(desc('count')).limit(20).all()

        return render_template(
            "admin/api_keys/details.html",
            api_key=api_key,
            usage_stats=usage_stats,
            recent_usage=recent_usage,
            usage_by_endpoint=usage_by_endpoint,
            now=utcnow(),  # Pass current time for date comparisons
            title=f"API Key: {api_key.client_name}"
        )
    except Exception as e:
        current_app.logger.error(f"Error viewing API key: {e}", exc_info=True)
        flash("Error loading API key details. Please try again.", "danger")
        return redirect(url_for('api_key_management.list_api_keys'))


@bp.route("/api-keys/<int:key_id>/revoke", methods=["GET", "POST"])
@admin_permission_required('admin.api.manage')
def revoke_api_key(key_id):
    """Revoke an API key"""
    api_key = APIKey.query.get_or_404(key_id)
    form = APIKeyRevokeForm()

    if form.validate_on_submit():
        try:
            # Revoke the key
            api_key.revoke(
                reason=form.revocation_reason.data or None
            )

            db.session.flush()

            # Log admin action
            log_admin_action(
                action_type='api_key_revoke',
                description=f'Revoked API key for client: {api_key.client_name}',
                target_type='api_key',
                target_id=key_id,
                target_description=f'Client: {api_key.client_name}, Prefix: {api_key.key_prefix}...',
                old_values={'is_revoked': False, 'is_active': True},
                new_values={'is_revoked': True, 'is_active': False}
            )

            flash(f"API key '{api_key.client_name}' has been revoked.", "success")
            return redirect(url_for('api_key_management.list_api_keys'))
        except Exception as e:
            current_app.logger.error(f"Error revoking API key: {e}", exc_info=True)
            request_transaction_rollback()
            flash("Error revoking API key. Please try again.", "danger")

    return render_template(
        "admin/api_keys/revoke.html",
        api_key=api_key,
        form=form,
        title=f"Revoke API Key: {api_key.client_name}"
    )


@bp.route("/api-keys/<int:key_id>/usage", methods=["GET"])
@admin_permission_required('admin.api.manage')
def api_key_usage(key_id):
    """Get API key usage statistics (JSON endpoint)"""
    try:
        api_key = APIKey.query.get_or_404(key_id)

        # Get date range from query params
        days = int(request.args.get('days', 30))
        start_date = utcnow() - timedelta(days=days)

        # Get usage data
        usage_data = db.session.query(
            func.date(APIKeyUsage.timestamp).label('date'),
            func.count(APIKeyUsage.id).label('requests'),
            func.avg(APIKeyUsage.response_time_ms).label('avg_response_time'),
            func.sum(case((APIKeyUsage.status_code >= 400, 1), else_=0)).label('errors')
        ).filter(
            APIKeyUsage.api_key_id == key_id,
            APIKeyUsage.timestamp >= start_date
        ).group_by(func.date(APIKeyUsage.timestamp)).order_by('date').all()

        # Format for JSON response
        result = {
            'key_id': key_id,
            'client_name': api_key.client_name,
            'period_days': days,
            'usage': [
                {
                    'date': row.date.isoformat(),
                    'requests': row.requests,
                    'avg_response_time': float(row.avg_response_time) if row.avg_response_time else 0,
                    'errors': row.errors or 0
                }
                for row in usage_data
            ]
        }

        return json_ok_result(result)
    except Exception as e:
        current_app.logger.error(f"Error getting API key usage: {e}", exc_info=True)
        return json_server_error('Error loading usage statistics')
