"""
Admin UI for central indicator measurement types and units.
"""
from flask import current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import func
from sqlalchemy.orm.attributes import flag_modified

from app import db
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


@bp.route("/indicator-bank/measurement-lookups", methods=["GET"])
@permission_required("admin.indicator_bank.edit")
def manage_measurement_lookups():
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


@bp.route("/indicator-bank/measurement-lookups/types/new", methods=["GET", "POST"])
@permission_required("admin.indicator_bank.edit")
def new_measurement_type():
    form = IndicatorBankTypeForm()
    if form.validate_on_submit():
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
            flash("Measurement type created.", "success")
            return redirect(url_for("system_admin.manage_measurement_lookups"))
        except Exception as e:
            request_transaction_rollback()
            current_app.logger.error("new_measurement_type: %s", e, exc_info=True)
            flash("Could not create type.", "danger")
    return render_template(
        "admin/indicator_bank/measurement_lookup_type_form.html",
        form=form,
        title="New measurement type",
        is_edit=False,
    )


@bp.route("/indicator-bank/measurement-lookups/types/<int:tid>/edit", methods=["GET", "POST"])
@permission_required("admin.indicator_bank.edit")
def edit_measurement_type(tid: int):
    row = IndicatorBankType.query.get_or_404(tid)
    form = IndicatorBankTypeForm(editing_id=tid)
    if request.method == "GET":
        form.code.data = row.code
        form.name.data = row.name
        form.sort_order.data = row.sort_order
        form.is_active.data = row.is_active
        translations = row.name_translations if isinstance(row.name_translations, dict) else {}
        for lang in current_app.config.get("TRANSLATABLE_LANGUAGES") or []:
            f = getattr(form, f"name_{lang}", None)
            if f is not None:
                f.data = translations.get(lang, "")

    if form.validate_on_submit():
        n = _type_usage_count(tid)
        new_code = (form.code.data or "").strip().lower()
        if new_code != row.code and n > 0:
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
                # Refresh denormalized type string on bank rows and form items
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
                flash("Measurement type saved.", "success")
                return redirect(url_for("system_admin.manage_measurement_lookups"))
            except Exception as e:
                request_transaction_rollback()
                current_app.logger.error("edit_measurement_type: %s", e, exc_info=True)
                flash("Could not save type.", "danger")
    return render_template(
        "admin/indicator_bank/measurement_lookup_type_form.html",
        form=form,
        title=f"Edit type: {row.code}",
        is_edit=True,
        row=row,
        usage_count=_type_usage_count(tid),
    )


@bp.route("/indicator-bank/measurement-lookups/units/new", methods=["GET", "POST"])
@permission_required("admin.indicator_bank.edit")
def new_measurement_unit():
    form = IndicatorBankUnitForm()
    if form.validate_on_submit():
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
            flash("Unit created.", "success")
            return redirect(url_for("system_admin.manage_measurement_lookups"))
        except Exception as e:
            request_transaction_rollback()
            current_app.logger.error("new_measurement_unit: %s", e, exc_info=True)
            flash("Could not create unit.", "danger")
    return render_template(
        "admin/indicator_bank/measurement_lookup_unit_form.html",
        form=form,
        title="New unit",
        is_edit=False,
    )


@bp.route("/indicator-bank/measurement-lookups/units/<int:uid>/edit", methods=["GET", "POST"])
@permission_required("admin.indicator_bank.edit")
def edit_measurement_unit(uid: int):
    row = IndicatorBankUnit.query.get_or_404(uid)
    form = IndicatorBankUnitForm(editing_id=uid)
    if request.method == "GET":
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

    if form.validate_on_submit():
        n = _unit_usage_count(uid)
        new_code = (form.code.data or "").strip().lower()
        if new_code != row.code and n > 0:
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
                flash("Unit saved.", "success")
                return redirect(url_for("system_admin.manage_measurement_lookups"))
            except Exception as e:
                request_transaction_rollback()
                current_app.logger.error("edit_measurement_unit: %s", e, exc_info=True)
                flash("Could not save unit.", "danger")
    return render_template(
        "admin/indicator_bank/measurement_lookup_unit_form.html",
        form=form,
        title=f"Edit unit: {row.code}",
        is_edit=True,
        row=row,
        usage_count=_unit_usage_count(uid),
    )
