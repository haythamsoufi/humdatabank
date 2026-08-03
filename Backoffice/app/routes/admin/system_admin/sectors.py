from app.utils.transactions import request_transaction_rollback
from flask import render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user
from app import db
from sqlalchemy import or_
from app.models import IndicatorBank, Sector, SubSector
from app.forms.system import SectorForm, SubSectorForm
from app.routes.admin.shared import permission_required, rbac_guard_audit_exempt
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_responses import (
    json_ok,
    json_server_error,
)
from app.utils.request_utils import is_json_request
from sqlalchemy.orm.attributes import flag_modified
from app.utils.sector_logo_urls import sector_logo_url
from app.services.platform import storage_service as storage
from app.routes.admin.system_admin import bp
from app.routes.admin.system_admin.helpers import (
    _save_logo_file, _delete_logo_file, _safe_logo_mimetype,
    apply_name_translations_from_form,
    flash_form_errors,
    handle_hierarchy_db_error,
    update_entity_name_translations_json,
)

from app.forms.organization import (
    NSBranchForm,
    NSSubBranchForm,
    NSLocalUnitForm,
)


# === Sector and SubSector Management Routes ===
@bp.route("/sectors_subsectors", methods=["GET"])
@permission_required('admin.organization.manage')
def manage_sectors_subsectors():
    return redirect(url_for("system_admin.manage_indicator_bank", tab="sectors"))

@bp.route("/sectors/new", methods=["POST"])
@permission_required('admin.organization.manage')
def new_sector():
    form = SectorForm()

    if form.validate():
        try:
            new_sector = Sector(
                name=form.name.data,
            )

            apply_name_translations_from_form(new_sector, form)

            if form.logo_file.data:
                logo_filename = _save_logo_file(
                    form.logo_file.data,
                    form.name.data,
                )
                if logo_filename:
                    new_sector.logo_filename = logo_filename

            db.session.add(new_sector)
            db.session.flush()

            flash(f"Sector '{new_sector.name}' created successfully.", "success")

        except Exception as e:
            handle_hierarchy_db_error(e, log_message=f"Error creating sector: {e}")
    else:
        flash_form_errors(form)

    return redirect(url_for("system_admin.manage_sectors_subsectors"))

@bp.route("/sectors/edit/<int:sector_id>", methods=["POST"])
@permission_required('admin.organization.manage')
def edit_sector(sector_id):
    sector = Sector.query.get_or_404(sector_id)

    if is_json_request():
        try:
            data = get_json_safe()
            return update_entity_name_translations_json(
                sector, data, success_message="Sector translations updated"
            )
        except Exception as e:
            request_transaction_rollback()
            current_app.logger.error(
                f"Error updating sector {sector_id} via JSON: {e}", exc_info=True
            )
            return json_server_error(GENERIC_ERROR_MESSAGE)

    form = SectorForm(original_sector_id=sector_id)

    if form.validate():
        try:
            sector.name = form.name.data

            apply_name_translations_from_form(sector, form)

            if form.logo_file.data:
                if sector.logo_filename:
                    _delete_logo_file(sector.logo_filename)

                logo_filename = _save_logo_file(
                    form.logo_file.data,
                    sector.name,
                )
                if logo_filename:
                    sector.logo_filename = logo_filename

            db.session.flush()
            flash(f"Sector '{sector.name}' updated successfully.", "success")

        except Exception as e:
            handle_hierarchy_db_error(e, log_message=f"Error updating sector {sector_id}: {e}")
    else:
        flash_form_errors(form)

    return redirect(url_for("system_admin.manage_sectors_subsectors"))

@bp.route("/sectors/<int:sector_id>", methods=["GET"])
@permission_required('admin.organization.manage')
def get_sector(sector_id):
    """API endpoint to get sector data for editing"""
    sector = Sector.query.get_or_404(sector_id)

    indicator_count = sum(
        1 for (j,) in db.session.query(IndicatorBank.sector)
        .filter(IndicatorBank.sector.isnot(None)).all()
        if j and isinstance(j, dict)
        and sector_id in (j.get("primary"), j.get("secondary"), j.get("tertiary"))
    )

    return json_ok(
        id=sector.id,
        name=sector.name,
        description=sector.description or '',
        display_order=sector.display_order or 0,
        icon_class=sector.icon_class or '',
        logo_filename=sector.logo_filename or '',
        logo_url=sector_logo_url(sector) or '',
        is_active=sector.is_active,
        name_translations=sector.name_translations or {},
        indicator_count=indicator_count,
        subsector_count=len(sector.sub_sectors),
    )

@bp.route("/sectors/delete/<int:sector_id>", methods=["POST"])
@permission_required('admin.organization.manage')
def delete_sector(sector_id):
    sector = Sector.query.get_or_404(sector_id)

    try:
        if sector.sub_sectors:
            flash(f"Cannot delete sector '{sector.name}' as it has associated sub-sectors.", "danger")
            return redirect(url_for("system_admin.manage_sectors_subsectors"))

        # Clear all indicator references to this sector (primary / secondary / tertiary)
        affected = IndicatorBank.query.filter(
            or_(
                IndicatorBank.sector["primary"].astext == str(sector_id),
                IndicatorBank.sector["secondary"].astext == str(sector_id),
                IndicatorBank.sector["tertiary"].astext == str(sector_id),
            )
        ).all()
        for indicator in affected:
            if indicator.sector and isinstance(indicator.sector, dict):
                updated = dict(indicator.sector)
                for level in ("primary", "secondary", "tertiary"):
                    if updated.get(level) == sector_id:
                        updated[level] = None
                indicator.sector = updated
                flag_modified(indicator, "sector")

        if sector.logo_filename:
            _delete_logo_file(sector.logo_filename)

        db.session.delete(sector)
        db.session.flush()
        flash(f"Sector '{sector.name}' deleted successfully.", "success")

    except Exception as e:
        handle_hierarchy_db_error(e, log_message=f"Error deleting sector {sector_id}: {e}")

    return redirect(url_for("system_admin.manage_sectors_subsectors"))

@bp.route("/subsectors/new", methods=["POST"])
@permission_required('admin.organization.manage')
def new_subsector():
    form = SubSectorForm()

    if form.validate():
        try:
            new_subsector = SubSector(
                name=form.name.data,
                sector_id=form.sector_id.data
            )

            apply_name_translations_from_form(new_subsector, form)

            db.session.add(new_subsector)
            db.session.flush()

            flash(f"Sub-sector '{new_subsector.name}' created successfully.", "success")

        except Exception as e:
            handle_hierarchy_db_error(e, log_message=f"Error creating subsector: {e}")
    else:
        flash_form_errors(form)

    return redirect(url_for("system_admin.manage_sectors_subsectors"))

@bp.route("/subsectors/edit/<int:subsector_id>", methods=["POST"])
@permission_required('admin.organization.manage')
def edit_subsector(subsector_id):
    subsector = SubSector.query.get_or_404(subsector_id)

    if is_json_request():
        try:
            data = get_json_safe()
            return update_entity_name_translations_json(
                subsector, data, success_message="Sub-sector translations updated"
            )
        except Exception as e:
            request_transaction_rollback()
            current_app.logger.error(
                f"Error updating subsector {subsector_id} via JSON: {e}", exc_info=True
            )
            return json_server_error(GENERIC_ERROR_MESSAGE)

    form = SubSectorForm(original_subsector_id=subsector_id)

    if form.validate():
        try:
            subsector.name = form.name.data
            apply_name_translations_from_form(subsector, form)
            subsector.sector_id = form.sector_id.data

            db.session.flush()
            flash(f"Sub-sector '{subsector.name}' updated successfully.", "success")

        except Exception as e:
            handle_hierarchy_db_error(e, log_message=f"Error updating subsector {subsector_id}: {e}")
    else:
        flash_form_errors(form)

    return redirect(url_for("system_admin.manage_sectors_subsectors"))

@bp.route("/subsectors/<int:subsector_id>", methods=["GET"])
@permission_required('admin.organization.manage')
def get_subsector(subsector_id):
    """API endpoint to get subsector data for editing"""
    subsector = SubSector.query.get_or_404(subsector_id)

    indicator_count = sum(
        1 for (j,) in db.session.query(IndicatorBank.sub_sector)
        .filter(IndicatorBank.sub_sector.isnot(None)).all()
        if j and isinstance(j, dict)
        and subsector_id in (j.get("primary"), j.get("secondary"), j.get("tertiary"))
    )

    return json_ok(
        id=subsector.id,
        name=subsector.name,
        description=subsector.description or '',
        sector_id=subsector.sector_id,
        display_order=subsector.display_order or 0,
        icon_class=subsector.icon_class or '',
        is_active=subsector.is_active,
        name_translations=subsector.name_translations or {},
        indicator_count=indicator_count,
    )

@bp.route("/subsectors/delete/<int:subsector_id>", methods=["POST"])
@permission_required('admin.organization.manage')
def delete_subsector(subsector_id):
    subsector = SubSector.query.get_or_404(subsector_id)

    try:
        # Clear all indicator sub-sector references before deleting
        affected = IndicatorBank.query.filter(
            or_(
                IndicatorBank.sub_sector["primary"].astext == str(subsector_id),
                IndicatorBank.sub_sector["secondary"].astext == str(subsector_id),
                IndicatorBank.sub_sector["tertiary"].astext == str(subsector_id),
            )
        ).all()
        for indicator in affected:
            if indicator.sub_sector and isinstance(indicator.sub_sector, dict):
                updated = dict(indicator.sub_sector)
                for level in ("primary", "secondary", "tertiary"):
                    if updated.get(level) == subsector_id:
                        updated[level] = None
                indicator.sub_sector = updated
                flag_modified(indicator, "sub_sector")

        db.session.delete(subsector)
        db.session.flush()
        flash(f"Sub-sector '{subsector.name}' deleted successfully.", "success")

    except Exception as e:
        handle_hierarchy_db_error(e, log_message=f"Error deleting subsector {subsector_id}: {e}")

    return redirect(url_for("system_admin.manage_sectors_subsectors"))


# === Static file serving for sector logos ===

@bp.route("/sectors/<int:sector_id>/logo", methods=["GET"])
@rbac_guard_audit_exempt("Intentionally public to allow logo rendering without admin session.")
def sector_logo(sector_id):
    sector = Sector.query.get_or_404(sector_id)
    if not sector.logo_filename:
        return ("", 404)
    rel_path = f"sectors/{sector.logo_filename}"
    if not storage.exists(storage.SYSTEM, rel_path):
        return ("", 404)
    return storage.stream_response(
        storage.SYSTEM, rel_path,
        filename=sector.logo_filename, as_attachment=False,
        mimetype=_safe_logo_mimetype(sector.logo_filename),
    )


# === NS Hierarchy Management Routes ===

@bp.route("/ns_hierarchy/branch/new", methods=["GET", "POST"])
@permission_required('admin.organization.manage')
def new_ns_branch():
    """Create a new NS branch using unified edit template"""
    from app.models import NSBranch, Country

    form = NSBranchForm()
    from app.services.organization.authorization_service import AuthorizationService
    is_focal_point_only = AuthorizationService.has_role(current_user, "assignment_editor_submitter") and not AuthorizationService.is_admin(current_user)
    if is_focal_point_only:
        countries = list(current_user.countries)
    else:
        countries = Country.query.order_by(Country.name).all()
    form.country_id.choices = [(c.id, c.name) for c in countries]

    if form.validate_on_submit():
        try:
            new_branch = NSBranch(
                name=form.name.data,
                code=form.code.data or None,
                description=form.description.data or None,
                country_id=form.country_id.data,
                address=form.address.data or None,
                city=form.city.data or None,
                postal_code=form.postal_code.data or None,
                coordinates=form.coordinates.data or None,
                phone=form.phone.data or None,
                email=form.email.data or None,
                website=form.website.data or None,
                is_active=form.is_active.data,
                established_date=form.established_date.data,
                display_order=form.display_order.data or 0
            )
            db.session.add(new_branch)
            db.session.flush()
            flash(f"Branch '{new_branch.name}' created successfully.", "success")
            return redirect(url_for("main.manage_ns_hierarchy"))
        except Exception as e:
            handle_hierarchy_db_error(
                e,
                log_message=f"Error creating NS branch: {e}",
                flash_message="Error creating branch.",
            )

    return render_template(
        "admin/organization/edit_entity.html",
        form=form,
        is_edit=False,
        entity=None,
        entity_label='NS Branch',
        icon='fas fa-code-branch',
        cancel_url=url_for('main.manage_ns_hierarchy')
    )

@bp.route("/ns_hierarchy/branch/edit/<int:branch_id>", methods=["GET", "POST"])
@permission_required('admin.organization.manage')
def edit_ns_branch(branch_id):
    """Edit an existing NS branch using unified edit template"""
    from app.models import NSBranch, Country

    branch = NSBranch.query.get_or_404(branch_id)

    from app.services.organization.authorization_service import AuthorizationService
    is_focal_point_only = AuthorizationService.has_role(current_user, "assignment_editor_submitter") and not AuthorizationService.is_admin(current_user)
    if is_focal_point_only:
        user_country_ids = [country.id for country in current_user.countries]
        if branch.country_id not in user_country_ids:
            flash("Access denied. You can only manage branches in your assigned countries.", "danger")
            return redirect(url_for("main.manage_ns_hierarchy"))

    form = NSBranchForm(obj=branch)
    if is_focal_point_only:
        countries = list(current_user.countries)
    else:
        countries = Country.query.order_by(Country.name).all()
    form.country_id.choices = [(c.id, c.name) for c in countries]

    if form.validate_on_submit():
        try:
            branch.name = form.name.data
            branch.code = form.code.data or None
            branch.description = form.description.data or None
            branch.country_id = form.country_id.data
            branch.address = form.address.data or None
            branch.city = form.city.data or None
            branch.postal_code = form.postal_code.data or None
            branch.coordinates = form.coordinates.data or None
            branch.phone = form.phone.data or None
            branch.email = form.email.data or None
            branch.website = form.website.data or None
            branch.is_active = form.is_active.data
            branch.established_date = form.established_date.data
            branch.display_order = form.display_order.data or 0
            db.session.flush()
            flash(f"Branch '{branch.name}' updated successfully.", "success")
            return redirect(url_for("main.manage_ns_hierarchy"))
        except Exception as e:
            handle_hierarchy_db_error(e, log_message=f"Error updating NS branch {branch_id}: {e}")

    return render_template(
        "admin/organization/edit_entity.html",
        form=form,
        is_edit=True,
        entity=branch,
        entity_label='NS Branch',
        icon='fas fa-code-branch',
        cancel_url=url_for('main.manage_ns_hierarchy')
    )

@bp.route("/ns_hierarchy/branch/delete/<int:branch_id>", methods=["POST"])
@permission_required('admin.organization.manage')
def delete_ns_branch(branch_id):
    """Delete an NS branch"""
    from app.models import NSBranch

    branch = NSBranch.query.get_or_404(branch_id)

    from app.services.organization.authorization_service import AuthorizationService
    is_focal_point_only = AuthorizationService.has_role(current_user, "assignment_editor_submitter") and not AuthorizationService.is_admin(current_user)
    if is_focal_point_only:
        user_country_ids = [country.id for country in current_user.countries]
        if branch.country_id not in user_country_ids:
            flash("Access denied. You can only manage branches in your assigned countries.", "danger")
            return redirect(url_for("main.manage_ns_hierarchy"))

    try:
        if branch.subbranches.first() or branch.local_units.first():
            flash(f"Cannot delete branch '{branch.name}' as it has associated sub-branches or local units.", "danger")
            return redirect(url_for("main.manage_ns_hierarchy"))

        db.session.delete(branch)
        db.session.flush()

        flash(f"Branch '{branch.name}' deleted successfully.", "success")

    except Exception as e:
        handle_hierarchy_db_error(
            e,
            log_message=f"Error deleting NS branch {branch_id}: {e}",
            flash_message="Error deleting branch.",
        )

    return redirect(url_for("main.manage_ns_hierarchy"))

@bp.route("/ns_hierarchy/subbranch/new", methods=["GET", "POST"])
@permission_required('admin.organization.manage')
def new_ns_subbranch():
    """Create a new NS sub-branch using unified edit template"""
    from app.models import NSSubBranch, NSBranch

    form = NSSubBranchForm()
    branches = NSBranch.query.filter_by(is_active=True).order_by(NSBranch.name).all()
    form.branch_id.choices = [(b.id, b.name) for b in branches]

    if form.validate_on_submit():
        try:
            new_subbranch = NSSubBranch(
                name=form.name.data,
                code=form.code.data or None,
                description=form.description.data or None,
                branch_id=form.branch_id.data,
                address=form.address.data or None,
                city=form.city.data or None,
                postal_code=form.postal_code.data or None,
                coordinates=form.coordinates.data or None,
                phone=form.phone.data or None,
                email=form.email.data or None,
                is_active=form.is_active.data,
                established_date=form.established_date.data,
                display_order=form.display_order.data or 0
            )
            db.session.add(new_subbranch)
            db.session.flush()
            flash(f"Sub-branch '{new_subbranch.name}' created successfully.", "success")
            return redirect(url_for("main.manage_ns_hierarchy"))
        except Exception as e:
            handle_hierarchy_db_error(e, log_message=f"Error creating NS sub-branch: {e}")

    return render_template(
        "admin/organization/edit_entity.html",
        form=form,
        is_edit=False,
        entity=None,
        entity_label='NS Sub-branch',
        icon='fas fa-network-wired',
        cancel_url=url_for('main.manage_ns_hierarchy')
    )

@bp.route("/ns_hierarchy/subbranch/edit/<int:subbranch_id>", methods=["GET", "POST"])
@permission_required('admin.organization.manage')
def edit_ns_subbranch(subbranch_id):
    """Edit an existing NS sub-branch using unified edit template"""
    from app.models import NSSubBranch, NSBranch

    subbranch = NSSubBranch.query.get_or_404(subbranch_id)
    form = NSSubBranchForm(obj=subbranch)
    branches = NSBranch.query.filter_by(is_active=True).order_by(NSBranch.name).all()
    form.branch_id.choices = [(b.id, b.name) for b in branches]

    if form.validate_on_submit():
        try:
            subbranch.name = form.name.data
            subbranch.code = form.code.data or None
            subbranch.description = form.description.data or None
            subbranch.branch_id = form.branch_id.data
            subbranch.address = form.address.data or None
            subbranch.city = form.city.data or None
            subbranch.postal_code = form.postal_code.data or None
            subbranch.coordinates = form.coordinates.data or None
            subbranch.phone = form.phone.data or None
            subbranch.email = form.email.data or None
            subbranch.is_active = form.is_active.data
            subbranch.established_date = form.established_date.data
            subbranch.display_order = form.display_order.data or 0
            db.session.flush()
            flash(f"Sub-branch '{subbranch.name}' updated successfully.", "success")
            return redirect(url_for("main.manage_ns_hierarchy"))
        except Exception as e:
            handle_hierarchy_db_error(
                e,
                log_message=f"Error updating NS sub-branch {subbranch_id}: {e}",
                flash_message="Error updating sub-branch.",
            )

    return render_template(
        "admin/organization/edit_entity.html",
        form=form,
        is_edit=True,
        entity=subbranch,
        entity_label='NS Sub-branch',
        icon='fas fa-network-wired',
        cancel_url=url_for('main.manage_ns_hierarchy')
    )

@bp.route("/ns_hierarchy/subbranch/delete/<int:subbranch_id>", methods=["POST"])
@permission_required('admin.organization.manage')
def delete_ns_subbranch(subbranch_id):
    """Delete an NS sub-branch"""
    from app.models import NSSubBranch

    subbranch = NSSubBranch.query.get_or_404(subbranch_id)

    try:
        if subbranch.local_units.first():
            flash(f"Cannot delete sub-branch '{subbranch.name}' as it has associated local units.", "danger")
            return redirect(url_for("main.manage_ns_hierarchy"))

        db.session.delete(subbranch)
        db.session.flush()

        flash(f"Sub-branch '{subbranch.name}' deleted successfully.", "success")

    except Exception as e:
        handle_hierarchy_db_error(e, log_message=f"Error deleting NS sub-branch {subbranch_id}: {e}")

    return redirect(url_for("main.manage_ns_hierarchy"))

@bp.route("/ns_hierarchy/localunit/new", methods=["GET", "POST"])
@permission_required('admin.organization.manage')
def new_ns_localunit():
    """Create a new NS local unit using unified edit template"""
    from app.models import NSLocalUnit, NSBranch, NSSubBranch

    form = NSLocalUnitForm()
    branches = NSBranch.query.filter_by(is_active=True).order_by(NSBranch.name).all()
    form.branch_id.choices = [(b.id, b.name) for b in branches]
    subbranches = NSSubBranch.query.filter_by(is_active=True).order_by(NSSubBranch.name).all()
    form.subbranch_id.choices = [('', 'None (Direct to Branch)')] + [(sb.id, sb.name) for sb in subbranches]

    if form.validate_on_submit():
        try:
            new_localunit = NSLocalUnit(
                name=form.name.data,
                code=form.code.data or None,
                description=form.description.data or None,
                branch_id=form.branch_id.data,
                subbranch_id=form.subbranch_id.data or None,
                address=form.address.data or None,
                city=form.city.data or None,
                postal_code=form.postal_code.data or None,
                coordinates=form.coordinates.data or None,
                phone=form.phone.data or None,
                email=form.email.data or None,
                is_active=form.is_active.data,
                established_date=form.established_date.data,
                display_order=form.display_order.data or 0
            )
            db.session.add(new_localunit)
            db.session.flush()
            flash(f"Local unit '{new_localunit.name}' created successfully.", "success")
            return redirect(url_for("main.manage_ns_hierarchy"))
        except Exception as e:
            handle_hierarchy_db_error(
                e,
                log_message=f"Error creating NS local unit: {e}",
                flash_message="Error creating local unit.",
            )

    return render_template(
        "admin/organization/edit_entity.html",
        form=form,
        is_edit=False,
        entity=None,
        entity_label='NS Local Unit',
        icon='fas fa-map-marker-alt',
        cancel_url=url_for('main.manage_ns_hierarchy')
    )

@bp.route("/ns_hierarchy/localunit/edit/<int:localunit_id>", methods=["GET", "POST"])
@permission_required('admin.organization.manage')
def edit_ns_localunit(localunit_id):
    """Edit an existing NS local unit using unified edit template"""
    from app.models import NSLocalUnit, NSBranch, NSSubBranch

    localunit = NSLocalUnit.query.get_or_404(localunit_id)
    form = NSLocalUnitForm(obj=localunit)
    branches = NSBranch.query.filter_by(is_active=True).order_by(NSBranch.name).all()
    form.branch_id.choices = [(b.id, b.name) for b in branches]
    subbranches = NSSubBranch.query.filter_by(is_active=True).order_by(NSSubBranch.name).all()
    form.subbranch_id.choices = [('', 'None (Direct to Branch)')] + [(sb.id, sb.name) for sb in subbranches]

    if form.validate_on_submit():
        try:
            localunit.name = form.name.data
            localunit.code = form.code.data or None
            localunit.description = form.description.data or None
            localunit.branch_id = form.branch_id.data
            localunit.subbranch_id = form.subbranch_id.data or None
            localunit.address = form.address.data or None
            localunit.city = form.city.data or None
            localunit.postal_code = form.postal_code.data or None
            localunit.coordinates = form.coordinates.data or None
            localunit.phone = form.phone.data or None
            localunit.email = form.email.data or None
            localunit.is_active = form.is_active.data
            localunit.established_date = form.established_date.data
            localunit.display_order = form.display_order.data or 0
            db.session.flush()
            flash(f"Local unit '{localunit.name}' updated successfully.", "success")
            return redirect(url_for("main.manage_ns_hierarchy"))
        except Exception as e:
            handle_hierarchy_db_error(e, log_message=f"Error updating NS local unit {localunit_id}: {e}")

    return render_template(
        "admin/organization/edit_entity.html",
        form=form,
        is_edit=True,
        entity=localunit,
        entity_label='NS Local Unit',
        icon='fas fa-map-marker-alt',
        cancel_url=url_for('main.manage_ns_hierarchy')
    )

@bp.route("/ns_hierarchy/localunit/delete/<int:localunit_id>", methods=["POST"])
@permission_required('admin.organization.manage')
def delete_ns_localunit(localunit_id):
    """Delete an NS local unit"""
    from app.models import NSLocalUnit

    localunit = NSLocalUnit.query.get_or_404(localunit_id)

    try:
        db.session.delete(localunit)
        db.session.flush()

        flash(f"Local unit '{localunit.name}' deleted successfully.", "success")

    except Exception as e:
        handle_hierarchy_db_error(
            e,
            log_message=f"Error deleting NS local unit {localunit_id}: {e}",
            flash_message="Error deleting local unit.",
        )

    return redirect(url_for("main.manage_ns_hierarchy"))
