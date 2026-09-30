"""FDRS document compliance endpoints for Data Explorer."""

from __future__ import annotations

import logging
from io import BytesIO

from flask import request, send_file
from sqlalchemy.orm import selectinload

from app.models import (
    AssignedForm,
    AssignmentEntityStatus,
    Country,
    FormItem,
    SubmittedDocument,
)
from app.routes.admin.shared import permission_required
from app.services.data_quality.helpers import (
    build_compliance_document_lookups,
    compliance_country_activity,
    compliance_doc_status_counts_toward_requirement,
    list_exploration_period_names,
)
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_ok, json_server_error
from app.utils.data_quality_constants import FDRS_TEMPLATE_ID
from plugins.fdrs import bp
from plugins.fdrs.data_quality.fdrs_v1_catalog import (
    COMPLIANCE_DOC_TYPES,
    fdrs_compliance_doc_label_matches,
)

logger = logging.getLogger(__name__)


def _compliance_countries():
    """Every country, with National Societies loaded for activity tagging."""
    return (
        Country.query
        .options(selectinload(Country.national_societies))
        .order_by(Country.name)
        .all()
    )




@bp.route("/admin/data-exploration/compliance", methods=["GET"])
@permission_required('admin.data_explore.compliance')
def get_compliance_data():
    """
    Get compliance data for FDRS template (ID 21).

    Query params:
    - reference_year: The most recent year to measure from (e.g., 2024 means check 2024, 2023, 2022)

    Returns document upload status for each country across the last 3 periods,
    and determines compliance based on:
    - At least one approved Annual Report in the past 3 years
    - At least one approved Audited Financial Statement in the past 3 years
    Pending or rejected documents are shown in the grid but do not count as compliant.
    """
    try:
        # Get reference year from query params (optional)
        reference_year = request.args.get('reference_year', type=int)

        # All FDRS periods (closed/deactivated assignments and saved data included).
        all_periods = list_exploration_period_names(FDRS_TEMPLATE_ID)

        # Extract available years from period names (assuming format like "2024" or "2024-2025")
        available_years = set()
        for period in all_periods:
            # Try to extract year from period name
            import re
            years_in_period = re.findall(r'20\d{2}', str(period))
            for y in years_in_period:
                available_years.add(int(y))
        available_years = sorted(available_years, reverse=True)

        # If reference_year is provided, filter periods to those containing that year or earlier (up to 3 years back)
        if reference_year:
            target_years = [reference_year, reference_year - 1, reference_year - 2]
            periods = []
            for period in all_periods:
                # Check if any target year is in this period
                years_in_period = re.findall(r'20\d{2}', str(period))
                for y in years_in_period:
                    if int(y) in target_years:
                        periods.append(period)
                        break
                if len(periods) >= 3:
                    break
        else:
            # Default: get the last 3 periods
            periods = all_periods[:3]

        periods = list(reversed(periods))

        if not periods:
            return json_ok(
                success=True,
                data=[],
                periods=[],
                available_years=available_years,
                reference_year=reference_year,
                doc_types=COMPLIANCE_DOC_TYPES,
                message="No FDRS assignment periods found",
            )

        # All countries. Inactive countries and National Societies stay in the
        # grid (tagged) and are excluded from counts unless include_inactive=1.
        include_inactive = request.args.get("include_inactive", "").lower() in ("1", "true", "yes")
        countries = _compliance_countries()

        # Get document fields from FDRS template that match our compliance doc types
        doc_items = (
            FormItem.query
            .filter(
                FormItem.template_id == FDRS_TEMPLATE_ID,
                FormItem.item_type == 'document_field',
                FormItem.archived == False
            )
            .all()
        )

        # Map document field labels to their IDs
        doc_item_map = {}
        all_doc_item_ids = []
        for item in doc_items:
            label = item.label.strip() if item.label else ""
            for doc_type in COMPLIANCE_DOC_TYPES:
                if fdrs_compliance_doc_label_matches(label, doc_type):
                    if doc_type not in doc_item_map:
                        doc_item_map[doc_type] = []
                    doc_item_map[doc_type].append(item.id)
                    all_doc_item_ids.append(item.id)
                    break

        # Create reverse mapping: item_id -> doc_type
        item_id_to_doc_type = {}
        for doc_type, item_ids in doc_item_map.items():
            for item_id in item_ids:
                item_id_to_doc_type[item_id] = doc_type

        # ========== OPTIMIZED BULK QUERIES ==========
        # Instead of N+1 queries, we fetch everything in just 4 queries total

        # 1. Get all assignments for the selected periods (1 query)
        assignments = (
            AssignedForm.query
            .filter(
                AssignedForm.template_id == FDRS_TEMPLATE_ID,
                AssignedForm.period_name.in_(periods)
            )
            .all()
        )
        assignment_map = {a.period_name: a for a in assignments}
        assignment_ids = [a.id for a in assignments]

        # 2. Get all AssignmentEntityStatus records for these assignments (1 query)
        all_aes = []
        if assignment_ids:
            all_aes = (
                AssignmentEntityStatus.query
                .filter(
                    AssignmentEntityStatus.assigned_form_id.in_(assignment_ids),
                    AssignmentEntityStatus.entity_type == 'country'
                )
                .all()
            )

        # Build lookup: (assignment_id, country_id) -> aes
        aes_lookup = {}
        aes_ids = []
        for aes in all_aes:
            aes_lookup[(aes.assigned_form_id, aes.entity_id)] = aes
            aes_ids.append(aes.id)

        # 3. Get all SubmittedDocuments for these AES records and doc item types (1 query)
        submitted_docs = []
        if aes_ids and all_doc_item_ids:
            submitted_docs = (
                SubmittedDocument.query
                .filter(
                    SubmittedDocument.assignment_entity_status_id.in_(aes_ids),
                    SubmittedDocument.form_item_id.in_(all_doc_item_ids)
                )
                .all()
            )

        _, _, doc_status_lookup = build_compliance_document_lookups(
            submitted_docs, item_id_to_doc_type
        )

        # ========== PROCESS DATA IN MEMORY ==========
        compliance_data = []
        pending_validation_countries = []

        for country in countries:
            country_periods = []
            has_annual_report = False
            has_audited_financial = False
            pending_validation_documents = []

            for period in periods:
                period_docs = {doc_type: "missing" for doc_type in COMPLIANCE_DOC_TYPES}

                assignment = assignment_map.get(period)
                if assignment:
                    aes = aes_lookup.get((assignment.id, country.id))
                    if aes:
                        for doc_type in COMPLIANCE_DOC_TYPES:
                            doc_status = doc_status_lookup.get((aes.id, doc_type), "missing")
                            period_docs[doc_type] = doc_status
                            if compliance_doc_status_counts_toward_requirement(doc_status):
                                if doc_type == "Annual Report":
                                    has_annual_report = True
                                elif doc_type == "Audited Financial Statement":
                                    has_audited_financial = True
                            if doc_status == "pending":
                                pending_validation_documents.append({
                                    "period": period,
                                    "doc_type": doc_type,
                                })

                country_periods.append({
                    "period": period,
                    "documents": period_docs
                })

            # Determine compliance: must have at least 1 Annual Report AND 1 Audited Financial Statement
            is_compliant = has_annual_report and has_audited_financial
            activity = compliance_country_activity(country)

            country_row = {
                "country_id": country.id,
                "country_name": country.name,
                "country_iso3": country.iso3,
                "region": country.region,
                "periods": country_periods,
                "is_compliant": is_compliant,
                "has_annual_report": has_annual_report,
                "has_audited_financial": has_audited_financial,
                "counts_in_compliance": activity["counts_in_compliance"],
                "activity_tags": activity["activity_tags"],
            }
            compliance_data.append(country_row)

            if not is_compliant and pending_validation_documents:
                pending_validation_countries.append({
                    "country_id": country.id,
                    "country_name": country.name,
                    "pending_documents": pending_validation_documents,
                    "counts_in_compliance": activity["counts_in_compliance"],
                })

        return json_ok(
            success=True,
            data=compliance_data,
            periods=periods,
            available_years=available_years,
            reference_year=reference_year,
            doc_types=COMPLIANCE_DOC_TYPES,
            include_inactive=include_inactive,
            pending_validation_notice={
                "count": len(pending_validation_countries),
                "countries": pending_validation_countries,
            },
        )

    except Exception as e:
        logger.error("Error fetching compliance data: %s", e, exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


@bp.route("/admin/data-exploration/compliance/download", methods=["GET"])
@permission_required('admin.data_explore.compliance')
def download_compliance_excel():
    """
    Download compliance data as an Excel file.

    Query params:
    - reference_year: The most recent year to measure from (e.g., 2024 means check 2024, 2023, 2022)
    """
    try:
        import openpyxl
        import re
        from openpyxl.styles import Font, Fill, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        from datetime import datetime

        # Get reference year from query params (optional)
        reference_year = request.args.get('reference_year', type=int)

        # All FDRS periods (closed/deactivated assignments and saved data included).
        all_periods = list_exploration_period_names(FDRS_TEMPLATE_ID)

        # If reference_year is provided, filter periods to those containing that year or earlier (up to 3 years back)
        if reference_year:
            target_years = [reference_year, reference_year - 1, reference_year - 2]
            periods = []
            for period in all_periods:
                # Check if any target year is in this period
                years_in_period = re.findall(r'20\d{2}', str(period))
                for y in years_in_period:
                    if int(y) in target_years:
                        periods.append(period)
                        break
                if len(periods) >= 3:
                    break
        else:
            # Default: get the last 3 periods
            periods = all_periods[:3]

        periods = list(reversed(periods))

        include_inactive = request.args.get("include_inactive", "").lower() in ("1", "true", "yes")
        countries = _compliance_countries()

        # Get document fields from FDRS template
        doc_items = (
            FormItem.query
            .filter(
                FormItem.template_id == FDRS_TEMPLATE_ID,
                FormItem.item_type == 'document_field',
                FormItem.archived == False
            )
            .all()
        )

        # Map document field labels to their IDs
        doc_item_map = {}
        all_doc_item_ids = []
        for item in doc_items:
            label = item.label.strip() if item.label else ""
            for doc_type in COMPLIANCE_DOC_TYPES:
                if fdrs_compliance_doc_label_matches(label, doc_type):
                    if doc_type not in doc_item_map:
                        doc_item_map[doc_type] = []
                    doc_item_map[doc_type].append(item.id)
                    all_doc_item_ids.append(item.id)
                    break

        # Create reverse mapping: item_id -> doc_type
        item_id_to_doc_type = {}
        for doc_type, item_ids in doc_item_map.items():
            for item_id in item_ids:
                item_id_to_doc_type[item_id] = doc_type

        # ========== OPTIMIZED BULK QUERIES ==========
        # Get all assignments for the selected periods (1 query)
        assignments = (
            AssignedForm.query
            .filter(
                AssignedForm.template_id == FDRS_TEMPLATE_ID,
                AssignedForm.period_name.in_(periods)
            )
            .all()
        )
        assignment_map = {a.period_name: a for a in assignments}
        assignment_ids = [a.id for a in assignments]

        # Get all AssignmentEntityStatus records (1 query)
        all_aes = []
        if assignment_ids:
            all_aes = (
                AssignmentEntityStatus.query
                .filter(
                    AssignmentEntityStatus.assigned_form_id.in_(assignment_ids),
                    AssignmentEntityStatus.entity_type == 'country'
                )
                .all()
            )

        aes_lookup = {}
        aes_ids = []
        for aes in all_aes:
            aes_lookup[(aes.assigned_form_id, aes.entity_id)] = aes
            aes_ids.append(aes.id)

        # Get all SubmittedDocuments (1 query)
        submitted_docs = []
        if aes_ids and all_doc_item_ids:
            submitted_docs = (
                SubmittedDocument.query
                .filter(
                    SubmittedDocument.assignment_entity_status_id.in_(aes_ids),
                    SubmittedDocument.form_item_id.in_(all_doc_item_ids)
                )
                .all()
            )

        _, _, doc_status_lookup = build_compliance_document_lookups(
            submitted_docs, item_id_to_doc_type
        )

        # Create workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "FDRS Compliance"

        # Define styles
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
        compliant_fill = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
        non_compliant_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
        inactive_fill = PatternFill(start_color="F3F4F6", end_color="F3F4F6", fill_type="solid")
        inactive_font = Font(color="6B7280")
        yes_font = Font(color="059669")
        no_font = Font(color="DC2626")
        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        center_align = Alignment(horizontal='center', vertical='center')

        # Build headers dynamically based on periods
        # Row 1: Country | period1 (merged) | period2 (merged) | ... | Compliance Status
        # Row 2: (empty) | Annual Report | Audited Financial Statement | ... | (empty)

        num_periods = len(periods)
        num_doc_types = len(COMPLIANCE_DOC_TYPES)
        data_start_col = 2

        # First header row
        ws.cell(row=1, column=1, value="Country").font = header_font
        ws.cell(row=1, column=1).fill = header_fill
        ws.cell(row=1, column=1).alignment = center_align
        ws.cell(row=1, column=1).border = thin_border
        ws.merge_cells(start_row=1, start_column=1, end_row=2, end_column=1)

        for idx, period in enumerate(periods):
            period_start_col = data_start_col + (idx * num_doc_types)
            period_end_col = period_start_col + num_doc_types - 1
            cell = ws.cell(row=1, column=period_start_col, value=period)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align
            cell.border = thin_border
            if num_doc_types > 1:
                ws.merge_cells(
                    start_row=1,
                    start_column=period_start_col,
                    end_row=1,
                    end_column=period_end_col,
                )

        # Compliance Status + activity (inactive country / NS) headers
        compliance_col = data_start_col + (num_periods * num_doc_types)
        activity_col = compliance_col + 1
        ws.cell(row=1, column=compliance_col, value="Compliance Status").font = header_font
        ws.cell(row=1, column=compliance_col).fill = header_fill
        ws.cell(row=1, column=compliance_col).alignment = center_align
        ws.cell(row=1, column=compliance_col).border = thin_border
        ws.merge_cells(start_row=1, start_column=compliance_col, end_row=2, end_column=compliance_col)
        ws.cell(row=1, column=activity_col, value="Activity").font = header_font
        ws.cell(row=1, column=activity_col).fill = header_fill
        ws.cell(row=1, column=activity_col).alignment = center_align
        ws.cell(row=1, column=activity_col).border = thin_border
        ws.merge_cells(start_row=1, start_column=activity_col, end_row=2, end_column=activity_col)

        # Second header row with document types under each period
        for idx, _period in enumerate(periods):
            period_start_col = data_start_col + (idx * num_doc_types)
            for doc_idx, doc_type in enumerate(COMPLIANCE_DOC_TYPES):
                cell = ws.cell(row=2, column=period_start_col + doc_idx, value=doc_type)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = center_align
                cell.border = thin_border

        # Add borders to merged cells in row 2 for Country, Compliance Status, and Activity
        for col in [1, compliance_col, activity_col]:
            cell = ws.cell(row=2, column=col)
            cell.border = thin_border

        # Write data (using pre-fetched lookups) - one row per country
        row_num = 3
        counted_countries = 0
        excluded_countries = 0
        for country in countries:
            has_annual_report = False
            has_audited_financial = False
            activity = compliance_country_activity(country)
            counts = bool(activity["counts_in_compliance"])
            if counts or include_inactive:
                counted_countries += 1
            if not counts:
                excluded_countries += 1

            # Build period_docs data and determine compliance
            period_docs_map = {}
            for period in periods:
                period_docs = {doc_type: "missing" for doc_type in COMPLIANCE_DOC_TYPES}
                assignment = assignment_map.get(period)
                if assignment:
                    aes = aes_lookup.get((assignment.id, country.id))
                    if aes:
                        for doc_type in COMPLIANCE_DOC_TYPES:
                            doc_status = doc_status_lookup.get((aes.id, doc_type), "missing")
                            period_docs[doc_type] = doc_status
                            if compliance_doc_status_counts_toward_requirement(doc_status):
                                if doc_type == "Annual Report":
                                    has_annual_report = True
                                elif doc_type == "Audited Financial Statement":
                                    has_audited_financial = True
                period_docs_map[period] = period_docs

            is_compliant = has_annual_report and has_audited_financial

            # Write single row for country
            name_cell = ws.cell(row=row_num, column=1, value=country.name)
            name_cell.border = thin_border
            if not counts:
                name_cell.font = inactive_font
                name_cell.fill = inactive_fill

            # Document columns grouped by period
            for idx, period in enumerate(periods):
                period_start_col = data_start_col + (idx * num_doc_types)
                for doc_idx, doc_type in enumerate(COMPLIANCE_DOC_TYPES):
                    cell = ws.cell(row=row_num, column=period_start_col + doc_idx)
                    doc_status = period_docs_map.get(period, {}).get(doc_type, "missing")
                    if doc_status == "approved":
                        cell.value = "Approved"
                        cell.font = yes_font
                    elif doc_status == "pending":
                        cell.value = "Pending"
                        cell.font = Font(color="D97706")
                    elif doc_status == "rejected":
                        cell.value = "Rejected"
                        cell.font = Font(color="DC2626")
                    else:
                        cell.value = "Missing"
                        cell.font = no_font
                    cell.alignment = center_align
                    cell.border = thin_border
                    if not counts:
                        cell.font = inactive_font
                        cell.fill = inactive_fill

            # Compliance Status
            cell = ws.cell(row=row_num, column=compliance_col)
            cell.value = "Compliant" if is_compliant else "Non-Compliant"
            if counts:
                cell.fill = compliant_fill if is_compliant else non_compliant_fill
            else:
                cell.font = inactive_font
                cell.fill = inactive_fill
            cell.alignment = center_align
            cell.border = thin_border

            activity_cell = ws.cell(row=row_num, column=activity_col)
            activity_labels = [
                "No National Society" if tag == "no_national_society" else tag
                for tag in activity["activity_tags"]
            ]
            activity_cell.value = "Active" if counts else ", ".join(activity_labels) or "Inactive"
            activity_cell.font = inactive_font if not counts else Font(color="166534")
            activity_cell.fill = inactive_fill if not counts else compliant_fill
            activity_cell.alignment = center_align
            activity_cell.border = thin_border

            row_num += 1

        # Adjust column widths dynamically
        ws.column_dimensions[get_column_letter(1)].width = 30  # Country
        for idx in range(num_periods * num_doc_types):
            ws.column_dimensions[get_column_letter(data_start_col + idx)].width = 18
        ws.column_dimensions[get_column_letter(compliance_col)].width = 18  # Compliance Status
        ws.column_dimensions[get_column_letter(activity_col)].width = 28  # Activity

        # Freeze header rows (data starts at row 3)
        ws.freeze_panes = 'A3'

        # Add summary sheet
        ws_summary = wb.create_sheet("Summary")
        ws_summary.cell(row=1, column=1, value="FDRS Document Compliance Summary").font = Font(bold=True, size=14)
        ws_summary.cell(row=2, column=1, value=f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        if reference_year:
            ws_summary.cell(row=3, column=1, value=f"Reference Year: {reference_year} (analyzing {reference_year}, {reference_year-1}, {reference_year-2})")
        ws_summary.cell(row=4, column=1, value=f"Periods analyzed: {', '.join(periods)}")

        ws_summary.cell(row=6, column=1, value="Countries in counts:").font = Font(bold=True)
        ws_summary.cell(row=6, column=2, value=counted_countries)
        ws_summary.cell(row=7, column=1, value="Excluded (inactive country or National Society):").font = Font(bold=True)
        ws_summary.cell(row=7, column=2, value=0 if include_inactive else excluded_countries)
        if include_inactive:
            ws_summary.cell(row=8, column=1, value="Inactive countries and National Societies are included in the counts.")
        else:
            ws_summary.cell(row=8, column=1, value="Inactive countries and National Societies are listed in the table but excluded from the counts.")
        ws_summary.cell(row=9, column=1, value="Compliance Rule:").font = Font(bold=True)
        ws_summary.cell(row=9, column=2, value="At least 1 approved Annual Report AND 1 approved Audited Financial Statement in the past 3 years")

        # Save to BytesIO
        output = BytesIO()
        wb.save(output)
        output.seek(0)

        # Generate filename with timestamp and reference year
        year_suffix = f"_{reference_year}" if reference_year else ""
        filename = f"FDRS_Compliance{year_suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )

    except ImportError:
        logger.error("openpyxl not installed for Excel export")
        return json_server_error("Excel export requires openpyxl library")
    except Exception as e:
        logger.error("Error generating compliance Excel: %s", e, exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)
