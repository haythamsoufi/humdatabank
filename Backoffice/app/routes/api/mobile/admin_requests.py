# Backoffice/app/routes/api/mobile/admin_requests.py
"""Admin access-request routes: list, approve, reject, bulk approve."""

from flask import request, current_app
from flask_login import current_user

from app import db
from app.services.platform.user_analytics_service import log_admin_action
from app.utils.mobile_auth import mobile_auth_required
from app.utils.mobile_responses import (
    mobile_ok, mobile_bad_request, mobile_not_found, mobile_server_error,
)
from app.routes.api.mobile import mobile_bp


def _notify_added_to_countries(user_id, country_ids):
    try:
        if len(country_ids) == 1:
            from app.services.notification.core import notify_user_added_to_country

            notify_user_added_to_country(user_id, country_ids[0])
        else:
            from app.services.notification.core import notify_user_added_to_countries

            notify_user_added_to_countries(user_id, country_ids)
    except Exception as e:
        current_app.logger.error("notify_user_added_to_country(ies) failed: %s", e, exc_info=True)


@mobile_bp.route('/admin/access-requests', methods=['GET'])
@mobile_auth_required(permissions=('admin.access_requests.view', 'admin.users.edit'))
def list_access_requests():
    """List country access requests (admin). Returns both pending and processed."""
    from app.models import CountryAccessRequest, Country
    from app.models import User as UserModel
    from sqlalchemy.orm import joinedload
    from app.services.organization.country_access_request_service import (
        pending_country_access_requests_query,
        processed_country_access_requests_query,
        reconcile_fulfilled_pending_country_access_requests,
    )

    reconcile_fulfilled_pending_country_access_requests()
    pending_requests = pending_country_access_requests_query().options(
        joinedload(CountryAccessRequest.user),
        joinedload(CountryAccessRequest.country),
    ).order_by(CountryAccessRequest.created_at.desc()).all()

    processed_requests = processed_country_access_requests_query().options(
        joinedload(CountryAccessRequest.user),
        joinedload(CountryAccessRequest.country),
    ).order_by(CountryAccessRequest.created_at.desc()).limit(100).all()

    def _serialize(req):
        user = req.user
        country = req.country
        return {
            'id': req.id,
            'user_id': req.user_id,
            'user_email': user.email if user else None,
            'user_name': user.name if user else None,
            'country_id': req.country_id,
            'country_name': country.name if country else None,
            'status': req.status,
            'created_at': req.created_at.isoformat() if req.created_at else None,
        }

    return mobile_ok(data={
        'pending': [_serialize(r) for r in pending_requests],
        'processed': [_serialize(r) for r in processed_requests],
    })


@mobile_bp.route('/admin/access-requests/<int:request_id>/approve', methods=['POST'])
@mobile_auth_required(permission='admin.access_requests.approve')
def approve_access_request(request_id):
    """Approve a country access request (admin)."""
    from app.models import CountryAccessRequest, Country
    from app.models import User as UserModel

    req = CountryAccessRequest.query.get(request_id)
    if not req:
        return mobile_not_found('Access request not found')
    if req.status != 'pending':
        return mobile_bad_request('This request has already been processed.')

    try:
        user = UserModel.query.get(req.user_id)
        country = Country.query.get(req.country_id)
        if not user or not country:
            return mobile_not_found('User or country not found')
        user.add_entity_permission(entity_type='country', entity_id=country.id)
        req.status = 'approved'
        req.processed_by_user_id = current_user.id
        req.processed_at = db.func.now()
        db.session.flush()
        log_admin_action(
            action_type='access_request_approve',
            description=f'Approved country access request for {user.email} to {country.name}',
            target_type='country_access_request',
            target_id=request_id,
            target_description=f'User: {user.email}, Country: {country.name}',
            new_values={
                'user_id': user.id,
                'user_email': user.email,
                'country_id': country.id,
                'country_name': country.name,
                'status': 'approved',
            },
            risk_level='low',
        )
        db.session.flush()
        _notify_added_to_countries(user.id, [country.id])
        return mobile_ok(message='Access request approved')
    except Exception as e:
        current_app.logger.error("approve_access_request: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()


@mobile_bp.route('/admin/access-requests/<int:request_id>/reject', methods=['POST'])
@mobile_auth_required(permission='admin.access_requests.reject')
def reject_access_request(request_id):
    """Reject a country access request (admin)."""
    from app.models import CountryAccessRequest

    req = CountryAccessRequest.query.get(request_id)
    if not req:
        return mobile_not_found('Access request not found')
    if req.status != 'pending':
        return mobile_bad_request('This request has already been processed.')

    try:
        from app.models import Country
        from app.models import User as UserModel

        user = UserModel.query.get(req.user_id)
        country = Country.query.get(req.country_id)
        req.status = 'rejected'
        req.processed_by_user_id = current_user.id
        req.processed_at = db.func.now()
        db.session.flush()
        user_email = user.email if user else 'unknown'
        country_name = country.name if country else 'unknown'
        log_admin_action(
            action_type='access_request_reject',
            description=f'Rejected country access request for {user_email} to {country_name}',
            target_type='country_access_request',
            target_id=request_id,
            target_description=f'User: {user_email}, Country: {country_name}',
            new_values={
                'user_id': req.user_id,
                'user_email': user.email if user else None,
                'country_id': req.country_id,
                'country_name': country.name if country else None,
                'status': 'rejected',
            },
            risk_level='low',
        )
        db.session.flush()
        return mobile_ok(message='Access request rejected')
    except Exception as e:
        current_app.logger.error("reject_access_request: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()


@mobile_bp.route('/admin/access-requests/approve-all', methods=['POST'])
@mobile_auth_required(permission='admin.access_requests.approve')
def approve_all_access_requests():
    """Bulk-approve all pending access requests."""
    from app.models import CountryAccessRequest, Country
    from app.models import User as UserModel
    from app.services.organization.country_access_request_service import (
        pending_country_access_requests_query,
        reconcile_fulfilled_pending_country_access_requests,
    )

    reconcile_fulfilled_pending_country_access_requests()
    pending = pending_country_access_requests_query().all()
    if not pending:
        return mobile_ok(message='No pending requests to approve', data={'approved_count': 0})

    user_ids = {req.user_id for req in pending}
    country_ids = {req.country_id for req in pending}
    users_by_id = {
        u.id: u for u in UserModel.query.filter(UserModel.id.in_(user_ids)).all()
    } if user_ids else {}
    countries_by_id = {
        c.id: c for c in Country.query.filter(Country.id.in_(country_ids)).all()
    } if country_ids else {}

    approved_count = 0
    approved_country_ids_by_user = {}
    try:
        for req in pending:
            user = users_by_id.get(req.user_id)
            country = countries_by_id.get(req.country_id)
            if user and country:
                user.add_entity_permission(entity_type='country', entity_id=country.id)
                req.status = 'approved'
                req.processed_by_user_id = current_user.id
                req.processed_at = db.func.now()
                db.session.flush()
                log_admin_action(
                    action_type='access_request_approve',
                    description=f'Bulk-approved country access request for {user.email} to {country.name}',
                    target_type='country_access_request',
                    target_id=req.id,
                    target_description=f'User: {user.email}, Country: {country.name}',
                    new_values={
                        'user_id': user.id,
                        'user_email': user.email,
                        'country_id': country.id,
                        'country_name': country.name,
                        'status': 'approved',
                    },
                    risk_level='low',
                )
                approved_country_ids_by_user.setdefault(user.id, []).append(country.id)
                approved_count += 1
        db.session.flush()
        for user_id, country_ids in approved_country_ids_by_user.items():
            _notify_added_to_countries(user_id, country_ids)
        return mobile_ok(message=f'{approved_count} request(s) approved', data={'approved_count': approved_count})
    except Exception as e:
        current_app.logger.error("approve_all_access_requests: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()
