# Backoffice/app/routes/api/mobile/admin_requests.py
"""Admin access-request routes: list, approve, reject, bulk approve."""

from flask import request, current_app
from flask_login import current_user

from app import db
from app.utils.mobile_auth import mobile_auth_required
from app.utils.mobile_responses import (
    mobile_ok, mobile_bad_request, mobile_not_found, mobile_server_error,
)
from app.routes.api.mobile import mobile_bp


@mobile_bp.route('/admin/access-requests', methods=['GET'])
@mobile_auth_required(permission='admin.access_requests.view')
def list_access_requests():
    """List country access requests (admin). Returns both pending and processed."""
    from app.models import CountryAccessRequest, Country
    from app.models import User as UserModel

    def _serialize(req):
        user = UserModel.query.get(req.user_id)
        country = Country.query.get(req.country_id)
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

    pending_q = CountryAccessRequest.query.filter_by(status='pending').order_by(
        CountryAccessRequest.created_at.desc()
    )
    processed_q = CountryAccessRequest.query.filter(
        CountryAccessRequest.status.in_(['approved', 'rejected'])
    ).order_by(CountryAccessRequest.created_at.desc()).limit(100)

    pending = [_serialize(r) for r in pending_q.all()]
    processed = [_serialize(r) for r in processed_q.all()]

    return mobile_ok(data={
        'pending': pending,
        'processed': processed,
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
        req.status = 'rejected'
        req.processed_by_user_id = current_user.id
        req.processed_at = db.func.now()
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

    pending = CountryAccessRequest.query.filter_by(status='pending').all()
    if not pending:
        return mobile_ok(message='No pending requests to approve', data={'approved_count': 0})

    approved_count = 0
    try:
        for req in pending:
            user = UserModel.query.get(req.user_id)
            country = Country.query.get(req.country_id)
            if user and country:
                user.add_entity_permission(entity_type='country', entity_id=country.id)
                req.status = 'approved'
                req.processed_by_user_id = current_user.id
                req.processed_at = db.func.now()
                approved_count += 1
        db.session.flush()
        return mobile_ok(message=f'{approved_count} request(s) approved', data={'approved_count': approved_count})
    except Exception as e:
        current_app.logger.error("approve_all_access_requests: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()
