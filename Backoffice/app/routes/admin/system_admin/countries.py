from app.utils.transactions import request_transaction_rollback
from flask import render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user
from app import db
from app.models import Country
from app.forms.system import CountryForm
from app.routes.admin.shared import permission_required
from app.utils.request_utils import is_json_request
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_ok, json_server_error, json_form_errors

from app.routes.admin.system_admin import bp


# === Country Management Routes ===
@bp.route("/countries", methods=["GET"])
@permission_required('admin.countries.view')
def manage_countries():
    # Redirect to organization page with countries tab active
    return redirect(url_for('organization.index', tab='countries'))

@bp.route("/countries/new", methods=["GET", "POST"])
@permission_required('admin.countries.edit')
def new_country():
    form = CountryForm()

    if form.validate_on_submit():
        try:
            translatable_langs = current_app.config.get("TRANSLATABLE_LANGUAGES", []) or []

            new_country = Country(
                name=form.name.data,
                short_name=(form.short_name.data or '').strip() or None,
                iso3=(form.iso3.data or '').upper(),
                status=form.status.data,
                preferred_language=Country.normalize_language_code(form.preferred_language.data),
                currency_code=form.currency_code.data
            )

            for code in translatable_langs:
                field = getattr(form, f"name_{code}", None)
                if field is not None:
                    new_country.set_name_translation(code, (field.data or "").strip())

            db.session.add(new_country)
            db.session.flush()

            flash(f"Country '{new_country.name}' created successfully.", "success")
            return redirect(url_for("system_admin.manage_countries"))

        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")
            current_app.logger.error(f"Error creating country: {e}", exc_info=True)

    return render_template("admin/countries/manage_country.html",
                         form=form,
                         title="Create New Country",
                         country=None)

@bp.route("/countries/<int:country_id>/data", methods=["GET"])
@permission_required('admin.countries.view')
def get_country_data_json(country_id):
    """API endpoint to get full country data for edit modal (used by AJAX)."""
    country = Country.query.get_or_404(country_id)
    return json_ok(
        id=country.id,
        name=country.name,
        short_name=country.short_name or '',
        iso3=country.iso3,
        status=country.status,
        preferred_language=country.preferred_language_code,
        currency_code=country.currency_code,
        name_translations=country.name_translations or {},
    )

@bp.route("/countries/<int:country_id>", methods=["GET"])
@permission_required('admin.countries.view')
def get_country_data(country_id):
    """API endpoint to get country data as JSON"""
    country = Country.query.get_or_404(country_id)
    return json_ok(id=country.id, name=country.name, region=country.region, iso3=country.iso3, status=country.status)

@bp.route("/countries/edit/<int:country_id>", methods=["GET", "POST"])
@permission_required('admin.countries.edit')
def edit_country(country_id):
    country = Country.query.get_or_404(country_id)
    form = CountryForm(request.form, obj=country)
    form.original_country_id = country.id

    if form.validate_on_submit():
        try:
            country.name = form.name.data
            country.short_name = (form.short_name.data or '').strip() or None
            country.iso3 = (form.iso3.data or '').upper()
            country.status = form.status.data
            country.preferred_language = Country.normalize_language_code(form.preferred_language.data)
            country.currency_code = form.currency_code.data

            translatable_langs = current_app.config.get("TRANSLATABLE_LANGUAGES", []) or []
            for code in translatable_langs:
                field = getattr(form, f"name_{code}", None)
                if field is not None:
                    country.set_name_translation(code, (field.data or "").strip())

            db.session.flush()
            if is_json_request():
                return json_ok(
                    message=f"Country '{country.name}' updated successfully.",
                    country={
                        'id': country.id,
                        'name': country.name,
                        'short_name': country.short_name or '',
                        'iso3': country.iso3,
                        'status': country.status,
                        'preferred_language': country.preferred_language_code,
                        'currency_code': country.currency_code,
                        'name_translations': country.name_translations or {},
                    },
                )
            flash(f"Country '{country.name}' updated successfully.", "success")
            return redirect(url_for("system_admin.manage_countries"))

        except Exception as e:
            request_transaction_rollback()
            current_app.logger.error(f"Error updating country {country_id}: {e}", exc_info=True)
            if is_json_request():
                return json_server_error(GENERIC_ERROR_MESSAGE)
            flash("An error occurred. Please try again.", "danger")

    if request.method == 'POST' and is_json_request():
        return json_form_errors(form, "Validation failed.")

    return render_template("admin/countries/manage_country.html",
                         form=form,
                         country=country,
                         title=f"Edit Country: {country.name}")

@bp.route("/countries/delete/<int:country_id>", methods=["POST"])
@permission_required('admin.countries.edit')
def delete_country(country_id):
    country = Country.query.get_or_404(country_id)

    try:
        if country.users.first() or country.assignment_statuses.first():
            flash(f"Cannot delete country '{country.name}' as it is associated with users or assignments.", "danger")
            return redirect(url_for("system_admin.manage_countries"))

        db.session.delete(country)
        db.session.flush()
        flash(f"Country '{country.name}' deleted successfully.", "success")

    except Exception as e:
        request_transaction_rollback()
        flash("Error deleting country.", "danger")
        current_app.logger.error(f"Error deleting country {country_id}: {e}", exc_info=True)

    return redirect(url_for("system_admin.manage_countries"))
