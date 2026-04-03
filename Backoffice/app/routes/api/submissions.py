# Backoffice/app/routes/api/submissions.py
"""
Submission API endpoints.
Part of the /api/v1 blueprint.
"""

from flask import request, current_app
from flask_login import login_required
from sqlalchemy import desc, select, union_all, literal, func
from sqlalchemy.orm import joinedload
import uuid

# Import the API blueprint from parent
from app.routes.api import api_bp

# Import models
from app.models import FormData, PublicSubmission, AssignedForm
from app.models.assignments import AssignmentEntityStatus
from app.utils.auth import require_api_key
from app import db

# Import utility functions
from app.utils.api_helpers import json_response, api_error
from app.utils.api_serialization import format_country_info
from app.utils.api_authentication import authenticate_api_request, get_user_allowed_template_ids
from app.utils.api_pagination import validate_pagination_params
from app.utils.api_formatting import format_form_data_response
from app.utils.api_serialization import format_indicator_details
from app.services import get_assignments_for_country


@api_bp.route('/submissions', methods=['GET'])
def get_submissions():
    """
    API endpoint to retrieve a list of submissions.
    Authentication (one of):
      - Authorization: Bearer YOUR_API_KEY (full access, paginated response)
      - HTTP Basic auth or session (user-scoped access, no pagination)
    Query Parameters:
        - template_id: Filter by template ID
        - country_id: Filter by country ID
        - submission_type: Filter by submission type ('assigned' or 'public')
        - page: Page number (default: 1, only used with API key auth)
        - per_page: Items per page (default: 20, max 100000, only used with API key auth)
    """
    try:
        # Authenticate request
        auth_result = authenticate_api_request()
        # Check if it's an error response (has status_code attribute)
        if hasattr(auth_result, 'status_code'):
            return auth_result  # Return error response
        elevated_access, auth_user, api_key_record = auth_result

        # Determine if we should paginate
        should_paginate = elevated_access

        # Validate pagination parameters
        if should_paginate:
            page, per_page = validate_pagination_params(request.args)
        else:
            page = 1
            per_page = None

        # Get query parameters for filtering
        template_id = request.args.get('template_id', type=int)
        country_id = request.args.get('country_id', type=int)
        submission_type = request.args.get('submission_type')

        # Apply RBAC filtering for user auth
        allowed_template_ids = None
        if not elevated_access and auth_user is not None:
            allowed_template_ids = get_user_allowed_template_ids(auth_user.id)
            if not allowed_template_ids:
                # User has no access to any templates
                return json_response({
                    'submissions': [],
                    'total_items': 0,
                    'total_pages': 0 if should_paginate else None,
                    'current_page': page if should_paginate else None,
                    'per_page': per_page if should_paginate else None
                })

        submission_type = (submission_type or '').strip().lower() or None
        if submission_type not in (None, 'assigned', 'public'):
            submission_type = None

        selects = []

        # Latest submitted_at for assigned submissions (one scalar per AES id)
        assigned_latest_submitted_at_sq = (
            select(func.max(FormData.submitted_at))
            .where(FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
            .scalar_subquery()
        )

        if submission_type in (None, 'assigned'):
            assigned_sel = (
                select(
                    AssignmentEntityStatus.id.label('id'),
                    literal('assigned').label('submission_type'),
                    func.coalesce(assigned_latest_submitted_at_sq, AssignedForm.assigned_at).label('sort_ts'),
                )
                .select_from(AssignmentEntityStatus)
                .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
                .where(AssignmentEntityStatus.entity_type == 'country')
            )
            if template_id:
                assigned_sel = assigned_sel.where(AssignedForm.template_id == template_id)
            elif allowed_template_ids is not None:
                assigned_sel = assigned_sel.where(AssignedForm.template_id.in_(allowed_template_ids))
            if country_id:
                assigned_sel = assigned_sel.where(AssignmentEntityStatus.entity_id == country_id)
            selects.append(assigned_sel)

        if submission_type in (None, 'public'):
            public_sel = (
                select(
                    PublicSubmission.id.label('id'),
                    literal('public').label('submission_type'),
                    PublicSubmission.submitted_at.label('sort_ts'),
                )
                .select_from(PublicSubmission)
                .join(AssignedForm, PublicSubmission.assigned_form_id == AssignedForm.id)
            )
            if template_id:
                public_sel = public_sel.where(AssignedForm.template_id == template_id)
            elif allowed_template_ids is not None:
                public_sel = public_sel.where(AssignedForm.template_id.in_(allowed_template_ids))
            if country_id:
                public_sel = public_sel.where(PublicSubmission.country_id == country_id)
            selects.append(public_sel)

        if not selects:
            return json_response({
                'submissions': [],
                'total_items': 0,
                'total_pages': 0 if should_paginate else None,
                'current_page': page if should_paginate else None,
                'per_page': per_page if should_paginate else None
            })

        combined = selects[0]
        for s in selects[1:]:
            combined = union_all(combined, s)

        combined_sq = combined.subquery()

        # Total count
        total_items = int(db.session.execute(select(func.count()).select_from(combined_sq)).scalar() or 0)

        # Ordering: newest first; tie-break by id for stability. Keep nulls last.
        base_ordered = (
            select(combined_sq.c.id, combined_sq.c.submission_type, combined_sq.c.sort_ts)
            .order_by(combined_sq.c.sort_ts.desc().nullslast(), combined_sq.c.id.desc())
        )

        if should_paginate:
            offset = (page - 1) * per_page
            base_ordered = base_ordered.offset(offset).limit(per_page)

        page_rows = db.session.execute(base_ordered).mappings().all()

        assigned_ids = [int(r['id']) for r in page_rows if r.get('submission_type') == 'assigned' and r.get('id') is not None]
        public_ids = [int(r['id']) for r in page_rows if r.get('submission_type') == 'public' and r.get('id') is not None]

        # Bulk-load ORM objects with eager loading to avoid N+1
        assigned_map = {}
        if assigned_ids:
            assigned_statuses = (
                AssignmentEntityStatus.query
                .options(
                    joinedload(AssignmentEntityStatus.assigned_form).joinedload(AssignedForm.template),
                    joinedload(AssignmentEntityStatus.country),
                )
                .filter(AssignmentEntityStatus.id.in_(assigned_ids))
                .all()
            )
            assigned_map = {int(a.id): a for a in assigned_statuses if a and a.id is not None}

        public_map = {}
        if public_ids:
            public_subs = (
                PublicSubmission.query
                .options(
                    joinedload(PublicSubmission.assigned_form).joinedload(AssignedForm.template),
                    joinedload(PublicSubmission.country),
                )
                .filter(PublicSubmission.id.in_(public_ids))
                .all()
            )
            public_map = {int(p.id): p for p in public_subs if p and p.id is not None}

        # Bulk compute latest submitted_at for assigned submissions
        latest_submitted_map = {}
        if assigned_ids:
            rows = (
                db.session.query(FormData.assignment_entity_status_id, func.max(FormData.submitted_at))
                .filter(FormData.assignment_entity_status_id.in_(assigned_ids))
                .group_by(FormData.assignment_entity_status_id)
                .all()
            )
            latest_submitted_map = {int(aes_id): dt for (aes_id, dt) in rows if aes_id is not None}

        serialized_submissions = []
        for r in page_rows:
            stype = r.get('submission_type')
            sid = r.get('id')
            if sid is None:
                continue
            sid_int = int(sid)
            if stype == 'assigned':
                status_entry = assigned_map.get(sid_int)
                if not status_entry:
                    continue
                assigned_form = status_entry.assigned_form
                country = status_entry.country
                submitted_dt = latest_submitted_map.get(sid_int)
                serialized_submissions.append({
                    'id': status_entry.id,
                    'type': 'assigned',
                    'assigned_form_id': assigned_form.id if assigned_form else None,
                    'template_id': assigned_form.template_id if assigned_form else None,
                    'template_name': assigned_form.template.name if assigned_form and assigned_form.template else None,
                    'period_name': assigned_form.period_name if assigned_form else None,
                    'country_info': format_country_info(country),
                    'status': status_entry.status,
                    'due_date': status_entry.due_date.isoformat() if status_entry.due_date is not None else None,
                    'submitted_at': submitted_dt.isoformat() if submitted_dt else None,
                    'created_at': assigned_form.assigned_at.isoformat() if assigned_form and assigned_form.assigned_at is not None else None,
                    'updated_at': None,
                })
            elif stype == 'public':
                submission = public_map.get(sid_int)
                if not submission:
                    continue
                serialized_submissions.append({
                    'id': submission.id,
                    'type': 'public',
                    'assignment_id': submission.assigned_form_id,
                    'assignment_name': submission.assigned_form.period_name if submission.assigned_form else None,
                    'template_id': submission.assigned_form.template_id if submission.assigned_form else None,
                    'template_name': submission.assigned_form.template.name if submission.assigned_form and submission.assigned_form.template else None,
                    'country_info': format_country_info(submission.country),
                    'organization_name': None,
                    'contact_name': submission.submitter_name,
                    'contact_email': submission.submitter_email,
                    'submitted_at': submission.submitted_at.isoformat() if submission.submitted_at is not None else None,
                    'created_at': submission.submitted_at.isoformat() if submission.submitted_at is not None else None,
                    'updated_at': None,
                })

        # Build response based on authentication type
        if should_paginate:
            total_pages = (total_items + per_page - 1) // per_page if per_page > 0 else 1
            return json_response({
                'submissions': serialized_submissions,
                'total_items': total_items,
                'total_pages': total_pages,
                'current_page': page,
                'per_page': per_page
            })

        return json_response({
            'submissions': serialized_submissions,
            'total_items': total_items,
            'total_pages': None,
            'current_page': None,
            'per_page': None
        })
    except Exception as e:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            f"API Error [ID: {error_id}] fetching submissions: {e}",
            exc_info=True,
            extra={'endpoint': '/submissions', 'params': dict(request.args)}
        )
        return api_error("Could not fetch submissions", 500, error_id, None)


@api_bp.route('/submissions/<int:submission_id>', methods=['GET'])
@require_api_key
def get_submission_details(submission_id):
    """
    API endpoint to retrieve details and data for a specific submission.
    """
    assigned_submission_status = AssignmentEntityStatus.query.get(submission_id)
    submission = None
    submission_type = None

    if assigned_submission_status:
        submission = assigned_submission_status
        submission_type = 'assigned'
    else:
        public_submission = PublicSubmission.query.get(submission_id)
        if public_submission:
            submission = public_submission
            submission_type = 'public'

    if not submission:
        return api_error('Submission not found', 404)

    # Serialize submission details and data
    serialized_submission = {
        'id': submission.id,
        'type': submission_type,
        'data': []
    }

    if submission_type == 'assigned':
        assigned_form = submission.assigned_form
        country = submission.country
        serialized_submission.update({
            'assigned_form_id': assigned_form.id if assigned_form else None,
            'template_id': assigned_form.template_id if assigned_form else None,
            'template_name': assigned_form.template.name if assigned_form and assigned_form.template else None,
            'period_name': assigned_form.period_name if assigned_form else None,
            'country_info': format_country_info(country),
            'status': submission.status,
            'due_date': submission.due_date.isoformat() if submission.due_date is not None else None,
            'submitted_at': submission.data_entries.order_by(desc(FormData.submitted_at)).first().submitted_at.isoformat() if submission.data_entries.first() else None,
            'created_at': assigned_form.assigned_at.isoformat() if assigned_form and assigned_form.assigned_at is not None else None,
            'updated_at': None,
        })
        for form_data_item in submission.data_entries:
            # Format the form data using the new structure
            form_data_info = format_form_data_response(form_data_item)

            serialized_submission['data'].append({
                'id': form_data_item.id,
                'section_id': form_data_item.form_item.section_id if form_data_item.form_item else None,
                'indicator_id': form_data_item.form_item_id if form_data_item.form_item and form_data_item.form_item.is_indicator else None,
                'indicator': format_indicator_details(form_data_item.form_item if form_data_item.form_item and form_data_item.form_item.is_indicator else None),
                'indicator_name': form_data_item.form_item.label if form_data_item.form_item and form_data_item.form_item.is_indicator else None,
                'question_id': form_data_item.form_item_id if form_data_item.form_item and form_data_item.form_item.is_question else None,
                'question_text': form_data_item.form_item.label if form_data_item.form_item and form_data_item.form_item.is_question else None,
                'answer_value': form_data_info['answer_value'],
                'disaggregation_data': form_data_info['disaggregation_data'],
                'data_status': form_data_info['data_status'],
                'data_not_available': form_data_info['data_not_available'],
                'not_applicable': form_data_info['not_applicable'],
                'unit': form_data_item.form_item.unit if form_data_item.form_item and form_data_item.form_item.is_indicator else None,
                'start_date': None,
                'end_date': None,
                'date_collected': form_data_item.submitted_at.isoformat() if form_data_item.submitted_at is not None else None,
                'created_at': form_data_item.submitted_at.isoformat() if form_data_item.submitted_at is not None else None,
                'updated_at': None,
            })
        serialized_submission['documents'] = []
        for submitted_doc in submission.submitted_documents:
            serialized_submission['documents'].append({
                'id': submitted_doc.id,
                'form_item_id': submitted_doc.form_item_id,
                'document_field_name': submitted_doc.form_item.label if submitted_doc.form_item else None,
                'filename': submitted_doc.filename,
                'filepath': submitted_doc.storage_path,
                'uploaded_at': submitted_doc.uploaded_at.isoformat() if submitted_doc.uploaded_at is not None else None,
            })

    elif submission_type == 'public':
        serialized_submission.update({
            'assignment_id': submission.assigned_form_id,
            'assignment_name': submission.assigned_form.period_name if submission.assigned_form and submission.assigned_form.period_name else (submission.assigned_form.template.name if submission.assigned_form and submission.assigned_form.template else None),
            'template_id': submission.assigned_form.template_id if submission.assigned_form else None,
            'template_name': submission.assigned_form.template.name if submission.assigned_form and submission.assigned_form.template else None,
            'country_info': format_country_info(submission.country),
            'organization_name': None,
            'contact_name': submission.submitter_name,
            'contact_email': submission.submitter_email,
            'submitted_at': submission.submitted_at.isoformat() if submission.submitted_at is not None else None,
            'created_at': submission.submitted_at.isoformat() if submission.submitted_at is not None else None,
            'updated_at': None,
        })
        for form_data_item in submission.data_entries:
            # Format the form data using the new structure
            form_data_info = format_form_data_response(form_data_item)

            serialized_submission['data'].append({
                'id': form_data_item.id,
                'section_id': form_data_item.form_item.section_id if form_data_item.form_item else None,
                'indicator_id': form_data_item.form_item_id if form_data_item.form_item and form_data_item.form_item.is_indicator else None,
                'indicator': format_indicator_details(form_data_item.form_item if form_data_item.form_item and form_data_item.form_item.is_indicator else None),
                'indicator_name': form_data_item.form_item.label if form_data_item.form_item and form_data_item.form_item.is_indicator else None,
                'question_id': form_data_item.form_item_id if form_data_item.form_item and form_data_item.form_item.is_question else None,
                'question_text': form_data_item.form_item.label if form_data_item.form_item and form_data_item.form_item.is_question else None,
                'answer_value': form_data_info['answer_value'],
                'disaggregation_data': form_data_info['disaggregation_data'],
                'data_status': form_data_info['data_status'],
                'data_not_available': form_data_info['data_not_available'],
                'not_applicable': form_data_info['not_applicable'],
                'unit': form_data_item.form_item.unit if form_data_item.form_item and form_data_item.form_item.is_indicator else None,
                'start_date': None,
                'end_date': None,
                'date_collected': submission.submitted_at.isoformat() if submission and submission.submitted_at is not None else None,
                'period_name': submission.assigned_form.period_name if submission.assigned_form else None,
                'submitted_at': submission.submitted_at.isoformat() if submission and submission.submitted_at is not None else None,
                'created_at': submission.submitted_at.isoformat() if submission and submission.submitted_at is not None else None,
                'updated_at': None,
                'assignment_name': submission.assigned_form.period_name if submission.assigned_form else None
            })
        serialized_submission['documents'] = []
        for submitted_doc in submission.submitted_documents:
            serialized_submission['documents'].append({
                'id': submitted_doc.id,
                'form_item_id': submitted_doc.form_item_id,
                'document_field_name': submitted_doc.form_item.label if submitted_doc.form_item else None,
                'filename': submitted_doc.filename,
                'filepath': submitted_doc.storage_path,
                'uploaded_at': submitted_doc.uploaded_at.isoformat() if submitted_doc.uploaded_at is not None else None,
            })

    return json_response(serialized_submission)
