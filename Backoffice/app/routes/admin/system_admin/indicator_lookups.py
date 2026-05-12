"""
Admin UI for central indicator measurement types and units.
"""
from typing import Optional

from flask import current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _
from sqlalchemy import func
from sqlalchemy.orm.attributes import flag_modified

from app import db
from app.utils.api_helpers import get_json_safe
from app.utils.api_responses import json_bad_request, json_ok, require_json_data
from app.utils.request_utils import is_json_request
from app.forms.system.indicator_lookup_forms import IndicatorBankTypeForm, IndicatorBankUnitForm
from app.models import FormItem, IndicatorBank, IndicatorBankType, IndicatorBankUnit
from app.routes.admin.shared import permission_required
from app.routes.admin.system_admin import bp
from app.utils.transactions import request_transaction_rollback
from config import Config


def _type_usage_count(tid: int) -> int:
    b = (
        db.session.query(func.count(IndicatorBank.id))
        .filter(IndicatorBank.indicator_type_id == tid)
        .scalar()
    )
    f = (
        db.session.query(func.count(FormItem.id))
        .filter(
            FormItem.item_type == "indicator",
            FormItem.indicator_type_id == tid,
        )
        .scalar()
    )
    return int(b or 0) + int(f or 0)


def _unit_usage_count(uid: int) -> int:
    b = (
        db.session.query(func.count(IndicatorBank.id))
        .filter(IndicatorBank.indicator_unit_id == uid)
        .scalar()
    )
    f = (
        db.session.query(func.count(FormItem.id))
        .filter(
            FormItem.item_type == "indicator",
            FormItem.indicator_unit_id == uid,
        )
        .scalar()
    )
    return int(b or 0) + int(f or 0)


def _wants_json_post() -> bool:
    return request.method == "POST" and is_json_request()


def _ensure_national_society_unit_row() -> bool:
    """Insert ``ns`` / National Society if missing (matches migration ``add_ns_indicator_bank_unit``).

    The indicator bank list can show “National Society” from localized *codes* on rows that have
    ``unit='ns'`` even when this catalog row was never inserted (e.g. migration not run). The
    lookups page only lists ``indicator_bank_unit`` rows, so we repair the catalog idempotently.
    """
    if IndicatorBankUnit.query.filter(func.lower(IndicatorBankUnit.code) == "ns").first():
        return False
    try:
        row = IndicatorBankUnit(
            code="ns",
            name="National Society",
            sort_order=35,
            is_active=True,
            allows_disaggregation=False,
        )
        db.session.add(row)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        current_app.logger.warning("ensure_national_society_unit_row: %s", e, exc_info=True)
        return False


@bp.route("/indicator-bank/measurement-lookups", methods=["GET"])
@permission_required("admin.indicator_bank.edit")
def manage_measurement_lookups():
    if _ensure_national_society_unit_row():
        flash(
            _("Added missing unit: National Society (code %(code)s).", code="ns"),
            "info",
        )
    types = (
        IndicatorBankType.query.order_by(IndicatorBankType.sort_order, IndicatorBankType.name).all()
    )
    units = (
        IndicatorBankUnit.query.order_by(IndicatorBankUnit.sort_order, IndicatorBankUnit.name).all()
    )
    ucount = {t.id: _type_usage_count(t.id) for t in types}
    vcount = {u.id: _unit_usage_count(u.id) for u in units}
    return render_template(
        "admin/indicator_bank/measurement_lookups.html",
        title="Indicator types & units",
        types=types,
        units=units,
        type_usage=ucount,
        unit_usage=vcount,
    )


@bp.route(
    "/indicator-bank/measurement-lookups/types/<int:tid>/translations",
    methods=["POST"],
)
@permission_required("admin.indicator_bank.edit")
def api_patch_measurement_type_translations(tid: int):
    """JSON: merge `name` translations (ISO keys) into ``IndicatorBankType.name_translations``."""
    if not is_json_request():
        return json_bad_request("JSON body required")
    data = get_json_safe() or {}
    err = require_json_data(data)
    if err:
        return err
    row = IndicatorBankType.query.get_or_404(tid)
    incoming = data.get("translations")
    if not isinstance(incoming, dict):
        return json_bad_request("Expected object with key `translations` (map of language code to string).")
    allowed = {
        str(c).strip().lower().split("_", 1)[0].split("-", 1)[0]
        for c in (current_app.config.get("TRANSLATABLE_LANGUAGES") or getattr(Config, "TRANSLATABLE_LANGUAGES", []) or [])
    }
    for lang, val in incoming.items():
        if not isinstance(lang, str) or not lang:
            continue
        lc = lang.strip().lower().split("_", 1)[0].split("-", 1)[0]
        if lc not in allowed or lc == "en":
            continue
        row.set_name_translation(lc, (val or "") if isinstance(val, str) else str(val or ""))
    flag_modified(row, "name_translations")
    db.session.add(row)
    db.session.commit()
    return json_ok(message="ok")


@bp.route(
    "/indicator-bank/measurement-lookups/units/<int:uid>/translations",
    methods=["POST"],
)
@permission_required("admin.indicator_bank.edit")
def api_patch_measurement_unit_translations(uid: int):
    """JSON: merge `name` translations (ISO keys) into ``IndicatorBankUnit.name_translations``."""
    if not is_json_request():
        return json_bad_request("JSON body required")
    data = get_json_safe() or {}
    err = require_json_data(data)
    if err:
        return err
    row = IndicatorBankUnit.query.get_or_404(uid)
    incoming = data.get("translations")
    if not isinstance(incoming, dict):
        return json_bad_request("Expected object with key `translations` (map of language code to string).")
    allowed = {
        str(c).strip().lower().split("_", 1)[0].split("-", 1)[0]
        for c in (current_app.config.get("TRANSLATABLE_LANGUAGES") or getattr(Config, "TRANSLATABLE_LANGUAGES", []) or [])
    }
    for lang, val in incoming.items():
        if not isinstance(lang, str) or not lang:
            continue
        lc = lang.strip().lower().split("_", 1)[0].split("-", 1)[0]
        if lc not in allowed or lc == "en":
            continue
        row.set_name_translation(lc, (val or "") if isinstance(val, str) else str(val or ""))
    flag_modified(row, "name_translations")
    db.session.add(row)
    db.session.commit()
    return json_ok(message="ok")


def _type_partial(
    form,
    *,
    is_edit: bool,
    row,
    form_action_url: str,
    usage_count: int = 0,
) -> str:
    return render_template(
        "admin/indicator_bank/measurement_lookup_type_form_partial.html",
        form=form,
        is_edit=is_edit,
        row=row,
        usage_count=usage_count,
        modal=True,
        form_action_url=form_action_url,
    )


def _unit_partial(
    form,
    *,
    is_edit: bool,
    row,
    form_action_url: str,
    delete_url: Optional[str] = None,
    usage_count: int = 0,
) -> str:
    return render_template(
        "admin/indicator_bank/measurement_lookup_unit_form_partial.html",
        form=form,
        is_edit=is_edit,
        row=row,
        usage_count=usage_count,
        modal=True,
        form_action_url=form_action_url,
        delete_url=delete_url,
    )


@bp.route("/indicator-bank/measurement-lookups/types/new", methods=["GET", "POST"])
@permission_required("admin.indicator_bank.edit")
def new_measurement_type():
    form = IndicatorBankTypeForm()
    new_url = url_for("system_admin.new_measurement_type")
    if request.method == "GET":
        if request.args.get("partial") == "1":
            return _type_partial(
                form,
                is_edit=False,
                row=None,
                form_action_url=new_url,
                usage_count=0,
            )
        return redirect(url_for("system_admin.manage_measurement_lookups", new_type=1))
    if not form.validate_on_submit():
        if _wants_json_post():
            return (
                jsonify(
                    {
                        "success": False,
                        "errors": form.errors,
                        "form_html": _type_partial(
                            form,
                            is_edit=False,
                            row=None,
                            form_action_url=new_url,
                            usage_count=0,
                        ),
                    }
                ),
                400,
            )
        return render_template(
            "admin/indicator_bank/measurement_lookup_type_form.html",
            form=form,
            title="New measurement type",
            is_edit=False,
            form_action_url=new_url,
        )
    try:
        row = IndicatorBankType(
            code=(form.code.data or "").strip().lower(),
            name=(form.name.data or "").strip(),
            sort_order=form.sort_order.data or 0,
            is_active=form.is_active.data,
        )
        langs = current_app.config.get("TRANSLATABLE_LANGUAGES") or getattr(
            Config, "TRANSLATABLE_LANGUAGES", []
        ) or []
        for lang in langs:
            field = getattr(form, f"name_{lang}", None)
            if field is not None:
                row.set_name_translation(lang, field.data or "")
        db.session.add(row)
        db.session.commit()
        if _wants_json_post():
            return json_ok(message=_("Measurement type created."))
        flash("Measurement type created.", "success")
        return redirect(url_for("system_admin.manage_measurement_lookups"))
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error("new_measurement_type: %s", e, exc_info=True)
        if _wants_json_post():
            return json_bad_request(_("Could not create type."))
        flash("Could not create type.", "danger")
    return render_template(
        "admin/indicator_bank/measurement_lookup_type_form.html",
        form=form,
        title="New measurement type",
        is_edit=False,
        form_action_url=new_url,
    )


@bp.route("/indicator-bank/measurement-lookups/types/<int:tid>/edit", methods=["GET", "POST"])
@permission_required("admin.indicator_bank.edit")
def edit_measurement_type(tid: int):
    row = IndicatorBankType.query.get_or_404(tid)
    form = IndicatorBankTypeForm(editing_id=tid)
    p_url = url_for("system_admin.edit_measurement_type", tid=tid)
    ucount = _type_usage_count(tid)
    if request.method == "GET":
        if request.args.get("partial") != "1":
            return redirect(url_for("system_admin.manage_measurement_lookups", edit_type=tid))
        form.code.data = row.code
        form.name.data = row.name
        form.sort_order.data = row.sort_order
        form.is_active.data = row.is_active
        translations = row.name_translations if isinstance(row.name_translations, dict) else {}
        for lang in current_app.config.get("TRANSLATABLE_LANGUAGES") or []:
            f = getattr(form, f"name_{lang}", None)
            if f is not None:
                f.data = translations.get(lang, "")
        return _type_partial(
            form,
            is_edit=True,
            row=row,
            form_action_url=p_url,
            usage_count=ucount,
        )

    if not form.validate_on_submit():
        if _wants_json_post():
            return (
                jsonify(
                    {
                        "success": False,
                        "errors": form.errors,
                        "form_html": _type_partial(
                            form,
                            is_edit=True,
                            row=row,
                            form_action_url=p_url,
                            usage_count=ucount,
                        ),
                    }
                ),
                400,
            )
        return render_template(
            "admin/indicator_bank/measurement_lookup_type_form.html",
            form=form,
            title=f"Edit type: {row.code}",
            is_edit=True,
            row=row,
            usage_count=ucount,
            form_action_url=p_url,
        )

    n = ucount
    new_code = (form.code.data or "").strip().lower()
    if new_code != row.code and n > 0:
        if _wants_json_post():
            return json_bad_request(
                _("Code cannot be changed while indicators reference this type.")
            )
        flash("Code cannot be changed while indicators reference this type.", "danger")
    else:
        try:
            if n == 0 or new_code == row.code:
                row.code = new_code
            row.name = (form.name.data or "").strip()
            row.sort_order = form.sort_order.data or 0
            row.is_active = form.is_active.data
            langs = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
            for lang in langs:
                field = getattr(form, f"name_{lang}", None)
                if field is not None:
                    row.set_name_translation(lang, field.data or "")
            flag_modified(row, "name_translations")
            db.session.add(row)
            for ind in IndicatorBank.query.filter_by(indicator_type_id=row.id).all():
                ind.type = (row.code or "")[:50]
            for it in (
                FormItem.query.filter(
                    FormItem.item_type == "indicator",
                    FormItem.indicator_type_id == row.id,
                )
                .all()
            ):
                it.type = (row.code or "")[:50]
            db.session.commit()
            if _wants_json_post():
                return json_ok(message=_("Measurement type saved."))
            flash("Measurement type saved.", "success")
            return redirect(url_for("system_admin.manage_measurement_lookups"))
        except Exception as e:
            request_transaction_rollback()
            current_app.logger.error("edit_measurement_type: %s", e, exc_info=True)
            if _wants_json_post():
                return json_bad_request(_("Could not save type."))
            flash("Could not save type.", "danger")
    return render_template(
        "admin/indicator_bank/measurement_lookup_type_form.html",
        form=form,
        title=f"Edit type: {row.code}",
        is_edit=True,
        row=row,
        usage_count=ucount,
        form_action_url=p_url,
    )


@bp.route("/indicator-bank/measurement-lookups/units/new", methods=["GET", "POST"])
@permission_required("admin.indicator_bank.edit")
def new_measurement_unit():
    form = IndicatorBankUnitForm()
    new_url = url_for("system_admin.new_measurement_unit")
    if request.method == "GET":
        if request.args.get("partial") == "1":
            return _unit_partial(
                form,
                is_edit=False,
                row=None,
                form_action_url=new_url,
                delete_url=None,
                usage_count=0,
            )
        return redirect(url_for("system_admin.manage_measurement_lookups", new_unit=1))
    if not form.validate_on_submit():
        if _wants_json_post():
            return (
                jsonify(
                    {
                        "success": False,
                        "errors": form.errors,
                        "form_html": _unit_partial(
                            form,
                            is_edit=False,
                            row=None,
                            form_action_url=new_url,
                            delete_url=None,
                            usage_count=0,
                        ),
                    }
                ),
                400,
            )
        return render_template(
            "admin/indicator_bank/measurement_lookup_unit_form.html",
            form=form,
            title="New unit",
            is_edit=False,
            form_action_url=new_url,
        )
    try:
        row = IndicatorBankUnit(
            code=(form.code.data or "").strip().lower(),
            name=(form.name.data or "").strip(),
            sort_order=form.sort_order.data or 0,
            is_active=form.is_active.data,
            allows_disaggregation=form.allows_disaggregation.data,
        )
        langs = current_app.config.get("TRANSLATABLE_LANGUAGES") or getattr(
            Config, "TRANSLATABLE_LANGUAGES", []
        ) or []
        for lang in langs:
            field = getattr(form, f"name_{lang}", None)
            if field is not None:
                row.set_name_translation(lang, field.data or "")
        db.session.add(row)
        db.session.commit()
        if _wants_json_post():
            return json_ok(message=_("Unit created."))
        flash("Unit created.", "success")
        return redirect(url_for("system_admin.manage_measurement_lookups"))
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error("new_measurement_unit: %s", e, exc_info=True)
        if _wants_json_post():
            return json_bad_request(_("Could not create unit."))
        flash("Could not create unit.", "danger")
    return render_template(
        "admin/indicator_bank/measurement_lookup_unit_form.html",
        form=form,
        title="New unit",
        is_edit=False,
        form_action_url=new_url,
    )


@bp.route("/indicator-bank/measurement-lookups/units/<int:uid>/edit", methods=["GET", "POST"])
@permission_required("admin.indicator_bank.edit")
def edit_measurement_unit(uid: int):
    row = IndicatorBankUnit.query.get_or_404(uid)
    form = IndicatorBankUnitForm(editing_id=uid)
    p_url = url_for("system_admin.edit_measurement_unit", uid=uid)
    d_url = url_for("system_admin.delete_measurement_unit", uid=uid) if _unit_usage_count(uid) == 0 else None
    ucount = _unit_usage_count(uid)
    if request.method == "GET":
        if request.args.get("partial") != "1":
            return redirect(url_for("system_admin.manage_measurement_lookups", edit_unit=uid))
        form.code.data = row.code
        form.name.data = row.name
        form.sort_order.data = row.sort_order
        form.is_active.data = row.is_active
        form.allows_disaggregation.data = row.allows_disaggregation
        translations = row.name_translations if isinstance(row.name_translations, dict) else {}
        for lang in current_app.config.get("TRANSLATABLE_LANGUAGES") or []:
            f = getattr(form, f"name_{lang}", None)
            if f is not None:
                f.data = translations.get(lang, "")
        return _unit_partial(
            form,
            is_edit=True,
            row=row,
            form_action_url=p_url,
            delete_url=d_url,
            usage_count=ucount,
        )

    d_url_err = url_for("system_admin.delete_measurement_unit", uid=uid) if ucount == 0 else None
    if not form.validate_on_submit():
        if _wants_json_post():
            return (
                jsonify(
                    {
                        "success": False,
                        "errors": form.errors,
                        "form_html": _unit_partial(
                            form,
                            is_edit=True,
                            row=row,
                            form_action_url=p_url,
                            delete_url=d_url_err,
                            usage_count=ucount,
                        ),
                    }
                ),
                400,
            )
        return render_template(
            "admin/indicator_bank/measurement_lookup_unit_form.html",
            form=form,
            title=f"Edit unit: {row.code}",
            is_edit=True,
            row=row,
            usage_count=ucount,
            form_action_url=p_url,
        )

    n = ucount
    new_code = (form.code.data or "").strip().lower()
    if new_code != row.code and n > 0:
        if _wants_json_post():
            return json_bad_request(
                _("Code cannot be changed while indicators reference this unit.")
            )
        flash("Code cannot be changed while indicators reference this unit.", "danger")
    else:
        try:
            if n == 0 or new_code == row.code:
                row.code = new_code
            row.name = (form.name.data or "").strip()
            row.sort_order = form.sort_order.data or 0
            row.is_active = form.is_active.data
            row.allows_disaggregation = form.allows_disaggregation.data
            langs = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
            for lang in langs:
                field = getattr(form, f"name_{lang}", None)
                if field is not None:
                    row.set_name_translation(lang, field.data or "")
            flag_modified(row, "name_translations")
            db.session.add(row)
            ucode = (row.code or "")[:50] if row.code else None
            for ind in IndicatorBank.query.filter_by(indicator_unit_id=row.id).all():
                ind.unit = ucode
            for it in (
                FormItem.query.filter(
                    FormItem.item_type == "indicator",
                    FormItem.indicator_unit_id == row.id,
                )
                .all()
            ):
                it.unit = ucode
            db.session.commit()
            if _wants_json_post():
                return json_ok(message=_("Unit saved."))
            flash("Unit saved.", "success")
            return redirect(url_for("system_admin.manage_measurement_lookups"))
        except Exception as e:
            request_transaction_rollback()
            current_app.logger.error("edit_measurement_unit: %s", e, exc_info=True)
            if _wants_json_post():
                return json_bad_request(_("Could not save unit."))
            flash("Could not save unit.", "danger")
    return render_template(
        "admin/indicator_bank/measurement_lookup_unit_form.html",
        form=form,
        title=f"Edit unit: {row.code}",
        is_edit=True,
        row=row,
        usage_count=ucount,
        form_action_url=p_url,
    )


@bp.route("/indicator-bank/measurement-lookups/units/<int:uid>/delete", methods=["POST"])
@permission_required("admin.indicator_bank.edit")
def delete_measurement_unit(uid: int):
    row = IndicatorBankUnit.query.get_or_404(uid)
    if _unit_usage_count(uid) > 0:
        if is_json_request():
            return json_bad_request(
                _("This unit is still used by one or more indicators and cannot be deleted.")
            )
        flash(_("This unit is still used by one or more indicators and cannot be deleted."), "danger")
        return redirect(url_for("system_admin.manage_measurement_lookups", edit_unit=uid))
    try:
        db.session.delete(row)
        db.session.commit()
        if is_json_request():
            return json_ok(message=_("Unit deleted."))
        flash(_("Unit deleted."), "success")
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error("delete_measurement_unit: %s", e, exc_info=True)
        if is_json_request():
            return json_bad_request(_("Could not delete unit."))
        flash(_("Could not delete unit."), "danger")
        return redirect(url_for("system_admin.manage_measurement_lookups", edit_unit=uid))
    return redirect(url_for("system_admin.manage_measurement_lookups"))
