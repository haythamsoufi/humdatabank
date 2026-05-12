from app.utils.transactions import request_transaction_rollback
from app.utils.advanced_validation import validate_upload_extension_and_mime
from app.utils.file_parsing import parse_csv_or_excel_to_rows, CSV_EXCEL_EXTENSIONS
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_responses import (
    json_bad_request, json_ok, json_server_error,
    require_json_data, require_json_keys,
)
from app.utils.constants import LOOKUP_ROW_TEMP_ORDER
from flask import (
    render_template, request, flash, redirect, url_for,
    current_app, make_response, send_file,
)
from flask_login import current_user
from app import db
from app.models import (
    Country, IndicatorBank, LookupList, LookupListRow, NationalSociety,
)
from app.routes.admin.shared import permission_required
from sqlalchemy import func
from werkzeug.utils import secure_filename

from app.routes.admin.system_admin import bp
from app.routes.admin.system_admin.helpers import (
    _get_model_columns_config, _model_to_dict,
)


# === Lookup List Management Routes ===
@bp.route("/lists", methods=["GET"])
@permission_required('admin.templates.edit')
def manage_lists():
    """Manage lookup lists"""
    lists = LookupList.query.order_by(LookupList.name).all()

    system_lists = []

    country_count = Country.query.count()
    system_lists.append({
        'name': 'Country Map',
        'description': 'List of all countries in the system',
        'columns': 4,
        'rows': country_count,
        'url': url_for('system_admin.view_system_list', system_list_type='country_map')
    })

    indicator_count = IndicatorBank.query.count()
    system_lists.append({
        'name': 'Indicator Bank',
        'description': 'List of all indicators in the indicator bank',
        'columns': 3,
        'rows': indicator_count,
        'url': url_for('system_admin.view_system_list', system_list_type='indicator_bank')
    })

    ns_count = NationalSociety.query.count()
    system_lists.append({
        'name': 'National Society',
        'description': 'List of all national societies in the system',
        'columns': 4,
        'rows': ns_count,
        'url': url_for('system_admin.view_system_list', system_list_type='national_society')
    })

    return render_template("admin/lists/manage_lists.html",
                         lists=lists,
                         system_lists=system_lists,
                         title="Manage Lookup Lists")

@bp.route("/lists/create", methods=["GET", "POST"])
@permission_required('admin.templates.edit')
def create_lookup_list():
    """Create a new lookup list"""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()

            if not name:
                flash("Name is required.", "danger")
                return redirect(url_for(request.endpoint, **request.view_args))

            existing = LookupList.query.filter_by(name=name).first()
            if existing:
                flash(f"A lookup list with the name '{name}' already exists.", "danger")
                return redirect(url_for(request.endpoint, **request.view_args))

            columns_str = request.form.get('columns', '').strip()
            columns_config = []
            if columns_str:
                columns = [col.strip() for col in columns_str.split(',') if col.strip()]
                columns_config = [{"name": col, "type": "string"} for col in columns]

            new_list = LookupList(
                name=name,
                description=description,
                columns_config=columns_config
            )

            db.session.add(new_list)
            db.session.flush()

            flash(f"Lookup list '{name}' created successfully.", "success")
            return redirect(url_for("system_admin.manage_lists"))

        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")
            current_app.logger.error(f"Error creating lookup list: {e}", exc_info=True)

    return render_template("admin/lists/manage_lists.html",
                         title="Create Lookup List")

@bp.route("/lists/view/<int:list_id>", methods=["GET"])
@permission_required('admin.templates.edit')
def view_lookup_list(list_id):
    """View lookup list details"""
    lookup_list = LookupList.query.get_or_404(list_id)
    rows = lookup_list.rows.order_by(LookupListRow.order).all()
    return render_template("admin/lists/list_detail.html",
                         lookup_list=lookup_list,
                         rows=rows,
                         title=f"View Lookup List: {lookup_list.name}")

@bp.route("/lists/system/<system_list_type>", methods=["GET"])
@permission_required('admin.templates.edit')
def view_system_list(system_list_type):
    """View system list details (Country Map or Indicator Bank)"""
    if system_list_type == 'country_map':
        countries = Country.query.order_by(Country.name).all()
        columns_config = _get_model_columns_config(Country)

        rows_data = []
        for idx, country in enumerate(countries):
            country_data = _model_to_dict(country, columns_config)
            rows_data.append({
                'id': country.id,
                'order': idx,
                'data': country_data
            })

        class MockLookupList:
            def __init__(self):
                self.id = 'country_map'
                self.name = 'Country Map'
                self.description = 'List of all countries in the system'
                self.columns_config = columns_config
                self.is_system_list = True

        lookup_list = MockLookupList()
        return render_template("admin/lists/list_detail.html",
                             lookup_list=lookup_list,
                             rows=rows_data,
                             title="View System List: Country Map")

    elif system_list_type == 'indicator_bank':
        indicators = IndicatorBank.query.order_by(IndicatorBank.name).all()
        columns_config = _get_model_columns_config(IndicatorBank)

        rows_data = []
        for idx, indicator in enumerate(indicators):
            indicator_data = _model_to_dict(indicator, columns_config)
            rows_data.append({
                'id': indicator.id,
                'order': idx,
                'data': indicator_data
            })

        class MockLookupList:
            def __init__(self):
                self.id = 'indicator_bank'
                self.name = 'Indicator Bank'
                self.description = 'List of all indicators in the indicator bank'
                self.columns_config = columns_config
                self.is_system_list = True

        lookup_list = MockLookupList()
        return render_template("admin/lists/list_detail.html",
                             lookup_list=lookup_list,
                             rows=rows_data,
                             title="View System List: Indicator Bank")

    elif system_list_type == 'national_society':
        national_societies = NationalSociety.query.order_by(NationalSociety.name).all()
        columns_config = _get_model_columns_config(NationalSociety)

        rows_data = []
        for idx, ns in enumerate(national_societies):
            ns_data = _model_to_dict(ns, columns_config)
            rows_data.append({
                'id': ns.id,
                'order': idx,
                'data': ns_data
            })

        class MockLookupList:
            def __init__(self):
                self.id = 'national_society'
                self.name = 'National Society'
                self.description = 'List of all national societies in the system'
                self.columns_config = columns_config
                self.is_system_list = True

        lookup_list = MockLookupList()
        return render_template("admin/lists/list_detail.html",
                             lookup_list=lookup_list,
                             rows=rows_data,
                             title="View System List: National Society")

    else:
        flash("Invalid system list type.", "danger")
        return redirect(url_for("system_admin.manage_lists"))

@bp.route("/lists/edit/<int:list_id>", methods=["GET", "POST"])
@permission_required('admin.templates.edit')
def edit_lookup_list(list_id):
    """Edit basic lookup list properties"""
    lookup_list = LookupList.query.get_or_404(list_id)

    if request.method == 'POST':
        try:
            lookup_list.name = request.form.get('name', '').strip()
            lookup_list.description = request.form.get('description', '').strip()

            columns_str = request.form.get('columns', '').strip()
            if columns_str:
                columns = [col.strip() for col in columns_str.split(',') if col.strip()]
                lookup_list.columns_config = [{"name": col, "type": "string"} for col in columns]

            db.session.flush()
            flash(f"Lookup list '{lookup_list.name}' updated successfully.", "success")
            return redirect(url_for("system_admin.manage_lists"))

        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")
            current_app.logger.error(f"Error updating lookup list {list_id}: {e}", exc_info=True)

    return redirect(url_for("system_admin.manage_lists"))

@bp.route("/lists/delete/<int:list_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def delete_lookup_list(list_id):
    """Delete lookup list"""
    lookup_list = LookupList.query.get_or_404(list_id)

    try:
        LookupListRow.query.filter_by(lookup_list_id=list_id).delete()
        db.session.delete(lookup_list)
        db.session.flush()

        flash(f"Lookup list '{lookup_list.name}' deleted successfully.", "success")

    except Exception as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error deleting lookup list {list_id}: {e}", exc_info=True)

    return redirect(url_for("system_admin.manage_lists"))


# === Lookup List Import/Export Routes ===
@bp.route("/lists/import-template", methods=["GET"])
@permission_required('admin.templates.edit')
def download_lookup_list_import_template():
    """Serve a starter file for lookup list import (row 1 = column headers, then data rows)."""
    fmt = (request.args.get("format") or "xlsx").lower().strip()
    if fmt == "csv":
        content = (
            "Name,Code,Region\r\n"
            "Example Country,EX,Example Region\r\n"
        )
        resp = make_response(content)
        resp.headers["Content-Type"] = "text/csv; charset=utf-8"
        resp.headers["Content-Disposition"] = (
            'attachment; filename="lookup-list-import-template.csv"'
        )
        return resp
    if fmt == "xlsx":
        from io import BytesIO
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Data"
        ws.append(["Name", "Code", "Region"])
        ws.append(["Example Country", "EX", "Example Region"])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name="lookup-list-import-template.xlsx",
        )
    flash("Unsupported template format.", "warning")
    return redirect(url_for("system_admin.manage_lists"))


@bp.route("/lists/import", methods=["POST"])
@permission_required('admin.templates.edit')
def import_lookup_list():
    """Create a new lookup list from an uploaded CSV/XLS/XLSX file."""
    try:
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        file = request.files.get('file')
        if not name or not file or file.filename == '':
            flash("Name and file are required.", "danger")
            return redirect(url_for("system_admin.manage_lists"))

        filename = secure_filename(file.filename)
        valid, error_msg, ext = validate_upload_extension_and_mime(file, CSV_EXCEL_EXTENSIONS)
        if not valid:
            flash(error_msg or "Unsupported file type. Please upload CSV or XLSX.", "danger")
            if ext:
                current_app.logger.warning(
                    f"Rejected lookup list import - {error_msg} (ext: {ext})"
                )
            return redirect(url_for("system_admin.manage_lists"))

        new_list = LookupList(name=name, description=description)
        db.session.add(new_list)
        db.session.flush()

        columns, rows_data = parse_csv_or_excel_to_rows(file, filename)

        new_list.columns_config = [{"name": c, "type": "string"} for c in columns]
        order_counter = 1
        for row in rows_data:
            db.session.add(LookupListRow(lookup_list_id=new_list.id, data=row, order=order_counter))
            order_counter += 1

        db.session.flush()
        flash(f"Lookup list '{new_list.name}' imported successfully.", "success")
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error importing lookup list: {e}", exc_info=True)
        flash("Error importing lookup list.", "danger")
    return redirect(url_for("system_admin.manage_lists"))

@bp.route("/lists/<int:list_id>/import", methods=["POST"])
@permission_required('admin.templates.edit')
def import_into_lookup_list(list_id):
    """Import data into an existing list (append or replace)."""
    lookup_list = LookupList.query.get_or_404(list_id)
    mode = request.form.get('mode', 'append')
    file = request.files.get('file')
    if not file or file.filename == '':
        flash("No file selected.", "danger")
        return redirect(url_for("system_admin.view_lookup_list", list_id=list_id))
    try:
        filename = secure_filename(file.filename)

        valid, error_msg, ext = validate_upload_extension_and_mime(file, CSV_EXCEL_EXTENSIONS)
        if not valid:
            flash(error_msg or "Unsupported file type. Please upload CSV or XLSX.", "danger")
            if ext:
                current_app.logger.warning(
                    f"Rejected lookup list import - {error_msg} (ext: {ext})"
                )
            return redirect(url_for("system_admin.view_lookup_list", list_id=list_id))

        columns = [c.get('name') for c in (lookup_list.columns_config or [])]
        parsed_columns, parsed_rows = parse_csv_or_excel_to_rows(file, filename)
        if not columns:
            columns = parsed_columns
            lookup_list.columns_config = [{"name": c, "type": "string"} for c in columns]
        new_rows = [{k: row.get(k) for k in columns} for row in parsed_rows]

        if mode == 'replace':
            LookupListRow.query.filter_by(lookup_list_id=list_id).delete()
            db.session.flush()

        current_highest = db.session.query(func.coalesce(func.max(LookupListRow.order), 0)).filter_by(lookup_list_id=list_id).scalar() or 0
        order_counter = current_highest + 1
        for row in new_rows:
            db.session.add(LookupListRow(lookup_list_id=list_id, data=row, order=order_counter))
            order_counter += 1

        db.session.flush()
        flash("Data imported successfully.", "success")
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error importing data into lookup list {list_id}: {e}", exc_info=True)
        flash("Error importing data.", "danger")
    return redirect(url_for("system_admin.view_lookup_list", list_id=list_id))

@bp.route("/lists/<int:list_id>/export", methods=["GET"])
@permission_required('admin.templates.edit')
def export_lookup_list(list_id):
    """Export a lookup list to CSV for download with proper Arabic encoding."""
    lookup_list = LookupList.query.get_or_404(list_id)
    import csv
    from io import StringIO, BytesIO
    import codecs

    output = StringIO()
    columns = [c.get('name') for c in (lookup_list.columns_config or [])]
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()

    for row in lookup_list.rows.order_by(LookupListRow.order).all():
        writer.writerow({k: (row.data.get(k, '') if isinstance(row.data, dict) else '') for k in columns})

    csv_content = output.getvalue()

    bytes_output = BytesIO()
    bytes_output.write(codecs.BOM_UTF8)
    bytes_output.write(csv_content.encode('utf-8'))
    bytes_output.seek(0)

    response = make_response(bytes_output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f"attachment; filename={secure_filename((lookup_list.name or 'lookup_list'))}.csv"
    return response


# === Lookup List Row API Routes ===
@bp.route("/templates/lists/<int:list_id>/rows/<int:row_id>", methods=["PATCH"])
@permission_required('admin.templates.edit')
def update_lookup_list_row(list_id, row_id):
    """Update a specific row in a lookup list"""
    try:
        current_app.logger.info(f"Updating lookup list row: list_id={list_id}, row_id={row_id}")

        lookup_list = LookupList.query.get_or_404(list_id)
        row = LookupListRow.query.filter_by(id=row_id, lookup_list_id=list_id).first_or_404()

        data = get_json_safe()
        current_app.logger.info(f"Received data: {data}")
        err = require_json_data(data)
        if err:
            return err

        if isinstance(row.data, dict):
            current_app.logger.info(f"Updating existing data: {row.data} with {data}")
            updated_data = dict(row.data)
            updated_data.update(data)
            row.data = updated_data
            current_app.logger.info(f"Updated data before commit: {row.data}")
        else:
            current_app.logger.info(f"Setting new data: {data}")
            row.data = data

        db.session.add(row)
        current_app.logger.info(f"Row data before commit: {row.data}")

        try:
            db.session.flush()
            current_app.logger.info("Commit successful")
        except Exception as commit_error:
            current_app.logger.error(f"Commit failed: {commit_error}")
            request_transaction_rollback()
            raise commit_error

        db.session.refresh(row)
        current_app.logger.info(f"Row updated successfully. New data: {row.data}")

        verification_row = LookupListRow.query.get(row_id)
        current_app.logger.info(f"Verification - row data from DB: {verification_row.data}")

        return json_ok(message='Row updated successfully')

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error updating lookup list row {row_id}: {e}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE, success=False)

@bp.route("/templates/lists/<int:list_id>/rows/<int:row_id>/move", methods=["POST"])
@permission_required('admin.templates.edit')
def move_lookup_list_row(list_id, row_id):
    """Move a row to a new position in the list"""
    try:
        current_app.logger.info(f"Moving lookup list row: list_id={list_id}, row_id={row_id}")

        lookup_list = LookupList.query.get_or_404(list_id)
        row = LookupListRow.query.filter_by(id=row_id, lookup_list_id=list_id).first_or_404()

        data = get_json_safe()
        current_app.logger.info(f"Move data: {data}")
        err = require_json_keys(data, ['target_row_id'])
        if err:
            return err

        target_row_id = data.get('target_row_id')
        position = data.get('position', 'after')

        if not target_row_id:
            return json_bad_request('Target row ID required')

        target_row = LookupListRow.query.filter_by(id=target_row_id, lookup_list_id=list_id).first_or_404()

        all_rows = lookup_list.rows.order_by(LookupListRow.order).all()
        current_app.logger.info(f"All rows before move: {[(r.id, r.order) for r in all_rows]}")

        target_order = target_row.order
        if position == 'before':
            new_order = target_order
        else:
            new_order = target_order + 1

        current_order = row.order

        if current_order == new_order:
            return json_ok(message='Row already in position')

        row.order = LOOKUP_ROW_TEMP_ORDER
        db.session.flush()

        if current_order < new_order:
            lookup_list.rows.filter(
                LookupListRow.order > current_order,
                LookupListRow.order <= new_order
            ).update({
                LookupListRow.order: LookupListRow.order - 1
            })
        else:
            lookup_list.rows.filter(
                LookupListRow.order >= new_order,
                LookupListRow.order < current_order
            ).update({
                LookupListRow.order: LookupListRow.order + 1
            })

        row.order = new_order

        db.session.flush()

        final_rows = lookup_list.rows.order_by(LookupListRow.order).all()
        current_app.logger.info(f"All rows after move: {[(r.id, r.order) for r in final_rows]}")
        return json_ok(message='Row moved successfully')

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error moving lookup list row {row_id}: {e}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE, success=False)

@bp.route("/templates/lists/<int:list_id>/rows/<int:row_id>", methods=["DELETE"])
@permission_required('admin.templates.edit')
def delete_lookup_list_row(list_id, row_id):
    """Delete a specific row from a lookup list"""
    try:
        lookup_list = LookupList.query.get_or_404(list_id)
        row = LookupListRow.query.filter_by(id=row_id, lookup_list_id=list_id).first_or_404()

        remaining_rows = lookup_list.rows.filter(LookupListRow.id != row_id).order_by(LookupListRow.order).all()
        for i, remaining_row in enumerate(remaining_rows, 1):
            remaining_row.order = i

        db.session.delete(row)
        db.session.flush()

        return json_ok(message='Row deleted successfully')

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error deleting lookup list row {row_id}: {e}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE, success=False)

@bp.route("/api/templates/lists/<int:list_id>/rows", methods=["POST"])
@permission_required('admin.templates.edit')
def add_lookup_list_row(list_id):
    """Add a new row to a lookup list"""
    try:
        lookup_list = LookupList.query.get_or_404(list_id)

        data = get_json_safe()
        order = data.get('order')
        insert_after_order = data.get('insert_after_order')

        if insert_after_order is not None:
            new_order = insert_after_order + 1
            lookup_list.rows.filter(LookupListRow.order > insert_after_order).update({
                LookupListRow.order: LookupListRow.order + 1
            })
        elif order is not None:
            new_order = order
            lookup_list.rows.filter(LookupListRow.order >= order).update({
                LookupListRow.order: LookupListRow.order + 1
            })
        else:
            max_order = db.session.query(func.max(LookupListRow.order)).filter_by(lookup_list_id=list_id).scalar() or 0
            new_order = max_order + 1

        new_row = LookupListRow(
            lookup_list_id=list_id,
            data={},
            order=new_order
        )

        if new_row.data is None:
            new_row.data = {}

        db.session.add(new_row)
        db.session.flush()

        return json_ok(message='Row added successfully', row_id=new_row.id)

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error adding row to lookup list {list_id}: {e}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE, success=False)
