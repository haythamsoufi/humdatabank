"""Excel import/export routes for countries and national societies."""
import io
import json
import os
from datetime import datetime

import pandas as pd
from flask import render_template, redirect, url_for, request, flash, current_app, send_file
from flask_wtf import FlaskForm

from app.models import db
from app.models.core import Country
from app.models.organization import (
    NationalSociety,
    NSBranch,
    NSSubBranch,
    NSLocalUnit,
    SecretariatDivision,
    SecretariatDepartment,
    SecretariatRegionalOffice,
    SecretariatClusterOffice,
)
from app.services.organization.country_service import (
    assign_country_fds_member_user,
    countries_with_fds_member_query,
    fds_member_user_display_name,
    parse_fds_member_user_id,
    resolve_fds_member_user_id_from_import,
)
from app.services.organization.secretariat_regional_office_service import (
    assign_country_secretariat_regional_office,
)
from app.routes.admin.shared import (
    admin_permission_required,
    admin_permission_required_any,
    permission_required,
    permission_required_any,
)
from app.utils.request_utils import is_json_request
from app.utils.entity_groups import get_enabled_entity_groups
from app.utils.transactions import no_auto_transaction, request_transaction_rollback
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_formatting import choices_from_query
from app.utils.api_responses import (
    json_bad_request,
    json_error,
    json_ok,
    json_select_options,
    json_server_error,
    require_json_data,
    require_json_keys,
)
from app.utils.error_handling import handle_json_view_exception
from config.config import Config
from app.forms.organization import (
    CountryForm,
    NationalSocietyForm,
    NSBranchForm,
    NSSubBranchForm,
    NSLocalUnitForm,
    SecretariatDivisionForm,
    SecretariatDepartmentForm,
    SecretariatRegionalOfficeForm,
    SecretariatClusterOfficeForm,
    collect_translations,
    clear_translation_fields,
    populate_translation_fields,
    count_missing_name_translations,
    count_missing_translations_for_fields,
    secretariat_translation_fields,
    secretariat_translation_jobs,
    regional_office_translation_fields,
    stream_entity_translation_events,
    commit_translation_entity,
)
from . import bp

# ==================== Countries Excel Export/Import ====================

FDS_MEMBER_USER_ID_COL = 'FDS Member User ID'
FDS_MEMBER_EMAIL_COL = 'FDS Member Email'
FDS_MEMBER_NAME_COL = 'FDS Member Name'


def _parse_excel_row_id(raw_value):
    """Return a positive integer ID from an Excel cell, or None if blank/invalid."""
    if raw_value is None or (isinstance(raw_value, float) and pd.isna(raw_value)):
        return None
    try:
        parsed = int(float(raw_value))
        return parsed if parsed > 0 else None
    except (ValueError, TypeError):
        return None


@bp.route('/countries/export', methods=['GET'])
@permission_required_any('admin.countries.view', 'admin.countries.edit', 'admin.organization.manage')
def export_countries():
    """Export all countries to an Excel file."""
    try:
        translatable = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
        display_names = getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", {}) or {}
        countries = countries_with_fds_member_query().order_by(Country.name).all()
        data = []
        for c in countries:
            fds_user = c.fds_member_user
            row = {
                'ID': c.id,
                'Name': c.name or '',
                'Short Name': c.short_name or '',
                'ISO3': c.iso3 or '',
                'ISO2': c.iso2 or '',
                'Region': c.region or '',
                'Status': c.status or 'Active',
                'Preferred Language': c.preferred_language_code or 'en',
                'Currency Code': c.currency_code or '',
                FDS_MEMBER_USER_ID_COL: c.fds_member_user_id or '',
                FDS_MEMBER_EMAIL_COL: (fds_user.email if fds_user else '') or '',
                FDS_MEMBER_NAME_COL: fds_member_user_display_name(fds_user) or '',
            }
            for code in translatable:
                header = display_names.get(code, code.upper())
                row[header] = (c.name_translations or {}).get(code, '') or ''
            data.append(row)
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Countries', index=False)
            ws = writer.sheets['Countries']
            for column in ws.columns:
                max_length = max(len(str(cell.value or '')) for cell in column)
                column_letter = column[0].column_letter
                ws.column_dimensions[column_letter].width = min(max_length + 2, 50)
        output.seek(0)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'countries_export_{timestamp}.xlsx',
        )
    except Exception as e:
        current_app.logger.error(f"Error exporting countries: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for('organization.index', tab='countries'))


@bp.route('/countries/template', methods=['GET'])
@permission_required_any('admin.countries.view', 'admin.countries.edit', 'admin.organization.manage')
def countries_template():
    """Download Excel template for countries import."""
    try:
        translatable = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
        display_names = getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", {}) or {}
        base_cols = [
            'Name', 'Short Name', 'ISO3', 'ISO2', 'Region', 'Status',
            'Preferred Language', 'Currency Code',
            FDS_MEMBER_USER_ID_COL, FDS_MEMBER_EMAIL_COL, FDS_MEMBER_NAME_COL,
        ]
        sample = [{
            'Name': 'Sample Country',
            'Short Name': 'Sample',
            'ISO3': 'XXX',
            'ISO2': 'XX',
            'Region': 'Other',
            'Status': 'Active',
            'Preferred Language': 'en',
            'Currency Code': 'USD',
            FDS_MEMBER_USER_ID_COL: '',
            FDS_MEMBER_EMAIL_COL: '',
            FDS_MEMBER_NAME_COL: '',
        }]
        for code in translatable:
            base_cols.append(display_names.get(code, code.upper()))
        df = pd.DataFrame(sample, columns=base_cols)
        for code in translatable:
            header = display_names.get(code, code.upper())
            df[header] = ''
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Countries Template', index=False)
            ws = writer.sheets['Countries Template']
            for column in ws.columns:
                max_length = max(len(str(cell.value or '')) for cell in column)
                column_letter = column[0].column_letter
                ws.column_dimensions[column_letter].width = min(max_length + 2, 50)
        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='countries_template.xlsx',
        )
    except Exception as e:
        current_app.logger.error(f"Error downloading countries template: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for('organization.index', tab='countries'))


@bp.route('/countries/import', methods=['POST'])
@permission_required_any('admin.countries.edit', 'admin.organization.manage')
def import_countries():
    """Import countries from an uploaded Excel file."""
    try:
        if 'excel_file' not in request.files:
            flash('No file selected.', 'danger')
            return redirect(url_for('organization.index', tab='countries'))
        file = request.files['excel_file']
        if not file or file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(url_for('organization.index', tab='countries'))
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            flash('Invalid file format. Please upload an Excel file (.xlsx or .xls).', 'danger')
            return redirect(url_for('organization.index', tab='countries'))

        # SECURITY: Validate file size (max 10MB for Excel imports)
        MAX_EXCEL_SIZE_MB = 10
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        if file_size > MAX_EXCEL_SIZE_MB * 1024 * 1024:
            flash(f'File too large. Maximum size is {MAX_EXCEL_SIZE_MB}MB.', 'danger')
            return redirect(url_for('organization.index', tab='countries'))

        # SECURITY: Validate MIME type to prevent file spoofing
        try:
            from app.utils.advanced_validation import AdvancedValidator
            file_ext = os.path.splitext(file.filename)[1].lower()
            is_valid_mime, detected_mime = AdvancedValidator.validate_mime_type(file, [file_ext])
            if not is_valid_mime:
                current_app.logger.warning(f"Excel import MIME mismatch: claimed {file_ext}, detected {detected_mime}")
                flash('File content does not match its extension. Please upload a valid Excel file.', 'danger')
                return redirect(url_for('organization.index', tab='countries'))
        except Exception as e:
            current_app.logger.warning(f"MIME validation error for Excel import: {e}")
            flash('Unable to validate file type. Please try again.', 'danger')
            return redirect(url_for('organization.index', tab='countries'))

        df = pd.read_excel(file, engine='openpyxl')
        required = ['Name', 'ISO3']
        missing = [c for c in required if c not in df.columns]
        if missing:
            flash(f'Missing required columns: {", ".join(missing)}', 'danger')
            return redirect(url_for('organization.index', tab='countries'))
        translatable = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
        display_names = getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", {}) or {}
        overwrite = request.form.get('overwrite_existing') == 'on'
        has_fds_member_cols = (
            FDS_MEMBER_USER_ID_COL in df.columns or FDS_MEMBER_EMAIL_COL in df.columns
        )
        imported = 0
        updated = 0
        errors = []
        for idx, row in df.iterrows():
            try:
                name = str(row['Name']).strip() if pd.notna(row.get('Name')) else ''
                iso3 = str(row['ISO3']).strip().upper() if pd.notna(row.get('ISO3')) else ''
                if not name or not iso3:
                    continue
                row_id = _parse_excel_row_id(row.get('ID')) if 'ID' in df.columns else None
                existing = None
                if overwrite and row_id:
                    existing = db.session.get(Country, row_id)
                elif not overwrite:
                    existing = Country.query.filter_by(iso3=iso3).first()
                    if existing:
                        errors.append(f'ISO3 "{iso3}" already exists (row {idx + 2})')
                        continue
                elif overwrite:
                    existing = Country.query.filter_by(iso3=iso3).first()
                trans = {}
                for code in translatable:
                    header = display_names.get(code, code.upper())
                    if header in df.columns and pd.notna(row.get(header)):
                        val = str(row[header]).strip()
                        if val:
                            trans[code] = val
                short_name = str(row['Short Name']).strip() if 'Short Name' in df.columns and pd.notna(row.get('Short Name')) else None
                short_name = short_name or None
                iso2 = str(row['ISO2']).strip().upper() if 'ISO2' in df.columns and pd.notna(row.get('ISO2')) else None
                iso2 = iso2 or None
                region_label = str(row['Region']).strip() if 'Region' in df.columns and pd.notna(row.get('Region')) else None
                region_label = region_label or None
                status = str(row['Status']).strip() if 'Status' in df.columns and pd.notna(row.get('Status')) else 'Active'
                status = status or 'Active'
                pref_lang = str(row['Preferred Language']).strip() if 'Preferred Language' in df.columns and pd.notna(row.get('Preferred Language')) else 'en'
                pref_lang = Country.normalize_language_code(pref_lang) if pref_lang else 'en'
                currency = str(row['Currency Code']).strip().upper() if 'Currency Code' in df.columns and pd.notna(row.get('Currency Code')) else None
                currency = currency or None
                target_country = existing
                if existing:
                    existing.name = name
                    existing.iso3 = iso3
                    existing.short_name = short_name
                    existing.iso2 = iso2
                    existing.secretariat_regional_office_id = None
                    assign_country_secretariat_regional_office(existing, region_label)
                    existing.status = status
                    existing.preferred_language = pref_lang
                    existing.currency_code = currency
                    existing.name_translations = trans
                    updated += 1
                else:
                    create_kwargs = dict(
                        name=name,
                        short_name=short_name,
                        iso3=iso3,
                        iso2=iso2,
                        region=region_label or 'Unassigned',
                        status=status,
                        preferred_language=pref_lang,
                        currency_code=currency,
                        name_translations=trans,
                    )
                    if row_id:
                        create_kwargs['id'] = row_id
                    target_country = Country(**create_kwargs)
                    assign_country_secretariat_regional_office(target_country, region_label)
                    db.session.add(target_country)
                    imported += 1

                if has_fds_member_cols:
                    raw_user_id = row.get(FDS_MEMBER_USER_ID_COL) if FDS_MEMBER_USER_ID_COL in df.columns else None
                    raw_email = row.get(FDS_MEMBER_EMAIL_COL) if FDS_MEMBER_EMAIL_COL in df.columns else None
                    if pd.isna(raw_user_id):
                        raw_user_id = None
                    if pd.isna(raw_email):
                        raw_email = None
                    db.session.flush()
                    try:
                        fds_user_id = resolve_fds_member_user_id_from_import(raw_user_id, raw_email)
                        assign_country_fds_member_user(target_country, fds_user_id)
                    except ValueError as exc:
                        errors.append(f'Row {idx + 2}: {exc}')
            except Exception as e:
                errors.append(f'Row {idx + 2}: error.')
        db.session.flush()
        if imported or updated:
            msg = f'Imported {imported} new countries'
            if updated:
                msg += f' and updated {updated} existing'
            flash(msg + '.', 'success')
        if errors:
            flash('Import issues: ' + '; '.join(errors[:5]) + ('...' if len(errors) > 5 else ''), 'warning')
        return redirect(url_for('organization.index', tab='countries'))
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error importing countries: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for('organization.index', tab='countries'))


# ==================== National Societies Excel Export/Import ====================

@bp.route('/national-societies/export', methods=['GET'])
@permission_required_any('admin.organization.manage', 'admin.countries.view')
def export_national_societies():
    """Export all national societies to an Excel file."""
    try:
        translatable = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
        display_names = getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", {}) or {}
        nss = NationalSociety.query.join(Country).order_by(Country.name, NationalSociety.display_order, NationalSociety.name).all()
        data = []
        for ns in nss:
            row = {
                'ID': ns.id,
                'Name': ns.name or '',
                'Code': ns.code or '',
                'Description': ns.description or '',
                'Country ISO3': ns.country.iso3 if ns.country else '',
                'Country Name': ns.country.name if ns.country else '',
                'Is Active': 'Yes' if ns.is_active else 'No',
                'Display Order': ns.display_order or 0,
            }
            for code in translatable:
                header = display_names.get(code, code.upper())
                row[header] = (ns.name_translations or {}).get(code, '') or ''
            if ns.part_of and isinstance(ns.part_of, list):
                row['Part Of (Categories)'] = ', '.join(str(p) for p in ns.part_of)
            else:
                row['Part Of (Categories)'] = ''
            data.append(row)
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='National Societies', index=False)
            ws = writer.sheets['National Societies']
            for column in ws.columns:
                max_length = max(len(str(cell.value or '')) for cell in column)
                column_letter = column[0].column_letter
                ws.column_dimensions[column_letter].width = min(max_length + 2, 50)
        output.seek(0)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'national_societies_export_{timestamp}.xlsx',
        )
    except Exception as e:
        current_app.logger.error(f"Error exporting national societies: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for('organization.index', tab='nss'))


@bp.route('/national-societies/template', methods=['GET'])
@permission_required_any('admin.organization.manage', 'admin.countries.view')
def national_societies_template():
    """Download Excel template for national societies import."""
    try:
        translatable = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
        display_names = getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", {}) or {}
        base_cols = ['Name', 'Code', 'Description', 'Country ISO3', 'Is Active', 'Display Order', 'Part Of (Categories)']
        name_cols = [display_names.get(code, code.upper()) for code in translatable]
        sample = [{
            'Name': 'Sample National Society',
            'Code': 'SNS',
            'Description': '',
            'Country ISO3': 'XXX',
            'Is Active': 'Yes',
            'Display Order': 0,
            'Part Of (Categories)': '',
        }]
        df = pd.DataFrame(sample, columns=base_cols)
        for header in name_cols:
            df[header] = ''
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='National Societies Template', index=False)
            ws = writer.sheets['National Societies Template']
            for column in ws.columns:
                max_length = max(len(str(cell.value or '')) for cell in column)
                column_letter = column[0].column_letter
                ws.column_dimensions[column_letter].width = min(max_length + 2, 50)
        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='national_societies_template.xlsx',
        )
    except Exception as e:
        current_app.logger.error(f"Error downloading national societies template: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for('organization.index', tab='nss'))


@bp.route('/national-societies/import', methods=['POST'])
@permission_required('admin.organization.manage')
def import_national_societies():
    """Import national societies from an uploaded Excel file."""
    try:
        if 'excel_file' not in request.files:
            flash('No file selected.', 'danger')
            return redirect(url_for('organization.index', tab='nss'))
        file = request.files['excel_file']
        if not file or file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(url_for('organization.index', tab='nss'))
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            flash('Invalid file format. Please upload an Excel file (.xlsx or .xls).', 'danger')
            return redirect(url_for('organization.index', tab='nss'))
        df = pd.read_excel(file, engine='openpyxl')
        required = ['Name', 'Country ISO3']
        missing = [c for c in required if c not in df.columns]
        if missing:
            flash(f'Missing required columns: {", ".join(missing)}', 'danger')
            return redirect(url_for('organization.index', tab='nss'))
        translatable = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
        display_names = getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", {}) or {}
        overwrite = request.form.get('overwrite_existing') == 'on'
        imported = 0
        updated = 0
        errors = []
        for idx, row in df.iterrows():
            try:
                name = str(row['Name']).strip() if pd.notna(row.get('Name')) else ''
                country_iso3 = str(row['Country ISO3']).strip().upper() if pd.notna(row.get('Country ISO3')) else ''
                if not name or not country_iso3:
                    continue
                country = Country.query.filter_by(iso3=country_iso3).first()
                if not country:
                    errors.append(f'Country ISO3 "{country_iso3}" not found (row {idx + 2})')
                    continue
                code_val = str(row['Code']).strip() if 'Code' in df.columns and pd.notna(row.get('Code')) else None
                code_val = code_val or None
                row_id = _parse_excel_row_id(row.get('ID')) if 'ID' in df.columns else None
                existing = None
                if overwrite and row_id:
                    existing = db.session.get(NationalSociety, row_id)
                elif not overwrite:
                    if code_val:
                        existing = NationalSociety.query.filter_by(code=code_val).first()
                    if not existing:
                        existing = NationalSociety.query.filter_by(name=name, country_id=country.id).first()
                    if existing:
                        errors.append(f'NS "{name}" for {country_iso3} already exists (row {idx + 2})')
                        continue
                elif overwrite:
                    if code_val:
                        existing = NationalSociety.query.filter_by(code=code_val).first()
                    if not existing:
                        existing = NationalSociety.query.filter_by(name=name, country_id=country.id).first()
                trans = {}
                for code in translatable:
                    header = display_names.get(code, code.upper())
                    if header in df.columns and pd.notna(row.get(header)):
                        val = str(row[header]).strip()
                        if val:
                            trans[code] = val
                description = str(row['Description']).strip() if 'Description' in df.columns and pd.notna(row.get('Description')) else None
                description = description or None
                is_active = True
                if 'Is Active' in df.columns and pd.notna(row.get('Is Active')):
                    v = str(row['Is Active']).strip().upper()
                    is_active = v in ('YES', 'TRUE', '1', 'ACTIVE')
                display_order = 0
                if 'Display Order' in df.columns and pd.notna(row.get('Display Order')):
                    try:
                        display_order = int(float(row['Display Order']))
                    except (ValueError, TypeError):
                        pass
                part_of = None
                part_of_col = 'Part Of (Categories)' if 'Part Of (Categories)' in df.columns else 'Part Of (Programs)'
                if part_of_col in df.columns and pd.notna(row.get(part_of_col)):
                    raw = str(row[part_of_col]).strip()
                    if raw:
                        part_of = [p.strip() for p in raw.split(',') if p.strip()]
                if existing:
                    existing.name = name
                    existing.code = code_val
                    existing.description = description
                    existing.country_id = country.id
                    existing.is_active = is_active
                    existing.display_order = display_order
                    existing.name_translations = trans
                    if part_of is not None:
                        existing.part_of = part_of
                    updated += 1
                else:
                    create_kwargs = dict(
                        name=name,
                        code=code_val,
                        description=description,
                        country_id=country.id,
                        is_active=is_active,
                        display_order=display_order,
                        name_translations=trans,
                        part_of=part_of,
                    )
                    if row_id:
                        create_kwargs['id'] = row_id
                    ns = NationalSociety(**create_kwargs)
                    db.session.add(ns)
                    imported += 1
            except Exception as e:
                errors.append(f'Row {idx + 2}: error.')
        db.session.flush()
        if imported or updated:
            msg = f'Imported {imported} new national societies'
            if updated:
                msg += f' and updated {updated} existing'
            flash(msg + '.', 'success')
        if errors:
            flash('Import issues: ' + '; '.join(errors[:5]) + ('...' if len(errors) > 5 else ''), 'warning')
        return redirect(url_for('organization.index', tab='nss'))
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error importing national societies: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for('organization.index', tab='nss'))
