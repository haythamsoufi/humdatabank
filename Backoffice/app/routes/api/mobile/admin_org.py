# Backoffice/app/routes/api/mobile/admin_org.py
"""Admin organization routes: NS branches, sub-branches, structure."""

from flask import request, current_app

from app.utils.mobile_auth import mobile_auth_required
from app.utils.mobile_responses import mobile_ok, mobile_not_found, mobile_server_error
from app.routes.api.mobile import mobile_bp


@mobile_bp.route('/admin/org/branches/<int:country_id>', methods=['GET'])
@mobile_auth_required(permission='admin.organization.manage')
def list_branches(country_id):
    """List NS branches for a country (admin only — consistent with /admin/org/structure)."""
    from app.models import NSBranch

    branches = NSBranch.query.filter_by(country_id=country_id).order_by(NSBranch.name.asc()).all()
    return mobile_ok(data={
        'branches': [
            {'id': b.id, 'name': b.name, 'code': getattr(b, 'code', None)}
            for b in branches
        ],
    })


@mobile_bp.route('/admin/org/subbranches/<int:branch_id>', methods=['GET'])
@mobile_auth_required(permission='admin.organization.manage')
def list_subbranches(branch_id):
    """List NS sub-branches for a branch (admin only — consistent with /admin/org/structure)."""
    from app.models import NSSubBranch

    subbranches = NSSubBranch.query.filter_by(branch_id=branch_id).order_by(NSSubBranch.name.asc()).all()
    return mobile_ok(data={
        'subbranches': [
            {'id': s.id, 'name': s.name, 'code': getattr(s, 'code', None), 'branch_id': s.branch_id}
            for s in subbranches
        ],
    })


@mobile_bp.route('/admin/org/structure', methods=['GET'])
@mobile_auth_required(permission='admin.organization.manage')
def org_structure():
    """Organization entities as flat lists per type (countries, branches, subbranches)."""
    from app.models import Country, NSBranch, NSSubBranch

    try:
        countries_q = Country.query.order_by(Country.name.asc()).all()
        branches_q = NSBranch.query.order_by(NSBranch.name.asc()).all()
        subbranches_q = NSSubBranch.query.order_by(NSSubBranch.name.asc()).all()

        country_names = {c.id: c.name for c in countries_q}

        countries = [
            {'id': c.id, 'name': c.name, 'code': getattr(c, 'iso3', None)}
            for c in countries_q
        ]
        branches = [
            {
                'id': b.id, 'name': b.name, 'code': getattr(b, 'code', None),
                'country_id': b.country_id,
                'country_name': country_names.get(b.country_id, ''),
            }
            for b in branches_q
        ]
        subbranches = [
            {
                'id': s.id, 'name': s.name, 'code': getattr(s, 'code', None),
                'branch_id': s.branch_id,
            }
            for s in subbranches_q
        ]

        return mobile_ok(data={
            'countries': countries,
            'branches': branches,
            'subbranches': subbranches,
            'active_tab': 'countries',
        })
    except Exception as e:
        current_app.logger.error("org_structure: %s", e, exc_info=True)
        return mobile_server_error()
