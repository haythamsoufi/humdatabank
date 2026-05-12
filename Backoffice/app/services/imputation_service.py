"""
Imputation service for template-specific admin actions.

Currently supports Template ID 2: carry-forward imputation from previous year.
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from contextlib import suppress

from app.models import (
    db,
    AssignedForm,
    FormTemplate,
    FormItem,
    FormData,
    Country,
)
from app.models.assignments import AssignmentEntityStatus
from app.cli import reset_form_data_sequence_helper

logger = logging.getLogger(__name__)


class ImputationService:
    """Service methods for imputing data for special templates."""

    @staticmethod
    def impute_template_2(target_year: str) -> Dict[str, Any]:
        """
        Impute data for Template ID 2 for the given year by carrying forward
        the previous year's values per country and per form item into the
        imputed_value column.

        Rules:
        - Scope: Assigned forms with template_id=2 and period_name == target_year
        - For each country assignment (ACS) for that year:
          - Try to find previous year's ACS for the same country (period_name == prev_year)
          - For each form item of template 2:
            - Read previous year's FormData
            - If exists, write into current year's FormData.imputed_value
              (create FormData if missing)
            - Do not overwrite existing value/disagg_data; only set imputed_value
            - For numeric values: always store as whole numbers (integers)
            - For text/single_choice values: store as strings (e.g., "male", "female")
        - This runs regardless of ACS.status; it does not change status

        Returns a summary dict with counts.
        """

        template_id = 2
        year_str = str(target_year)
        try:
            prev_year_str = str(int(year_str) - 1)
        except Exception as e:
            logger.debug("Could not parse year for prev_year_str, using suffix fallback: %s", e)
            # e.g., "2025 Q1" -> "2024 Q1" (best-effort)
            parts = year_str.split()
            if parts and parts[0].isdigit():
                parts[0] = str(int(parts[0]) - 1)
                prev_year_str = " ".join(parts)
            else:
                prev_year_str = year_str  # fallback no-op

        # Validate template exists
        template = FormTemplate.query.get(template_id)
        if not template:
            return {
                "success": False,
                "error": f"Template {template_id} not found",
            }

        # Fetch all items under this template once
        form_items: List[FormItem] = (
            FormItem.query.filter_by(template_id=template_id).all()
        )
        logger.debug(
            "Imputation: template_id=%s items=%s target_period=%s source_period=%s",
            template_id,
            len(form_items),
            year_str,
            prev_year_str,
        )

        # Map items by id for quick access
        item_ids = [fi.id for fi in form_items]
        form_items_by_id = {fi.id: fi for fi in form_items}

        # Get all assignments for target and previous year
        target_assignments: List[AssignedForm] = (
            AssignedForm.query.filter_by(template_id=template_id, period_name=year_str).all()
        )

        prev_assignments_by_country: Dict[int, AssignedForm] = {}
        prev_assignments = AssignedForm.query.filter_by(template_id=template_id, period_name=prev_year_str).all()
        for af in prev_assignments:
            # Map country_id -> prev assignment via its AES entries
            for aes in af.country_statuses.all():
                if aes.country_id not in prev_assignments_by_country:
                    prev_assignments_by_country[aes.country_id] = af

        total_countries_processed = 0
        total_items_imputed = 0
        total_rows_created = 0
        total_rows_updated = 0

        for assignment in target_assignments:
            # For each country assignment in the target year
            for aes in assignment.country_statuses.all():
                country_id = aes.country_id
                country_name = aes.country.name if aes.country else f"country_id_{country_id}"
                prev_af = prev_assignments_by_country.get(country_id)
                if not prev_af:
                    continue
                # Find the prev year's AES for the same country
                prev_aes: Optional[AssignmentEntityStatus] = (
                    prev_af.country_statuses.filter_by(entity_id=country_id, entity_type='country').first()
                )
                if not prev_aes:
                    continue

                # For each item, copy prev data into current.imputed_value
                items_imputed_for_country = 0
                for item_id in item_ids:
                    # Get the form item to check its imputation method
                    form_item = form_items_by_id.get(item_id)
                    if not form_item:
                        continue

                    imputation_method = form_item.config.get('imputation_method', 'last_year') if form_item.config else 'last_year'

                    # Skip items that should not be imputed
                    if imputation_method == 'no_imputation':
                        continue

                    # Get source data based on method
                    source_data = None
                    source_periods = []

                    if imputation_method == 'three_year_avg':
                        # Get data from last 3 years
                        for year_offset in range(1, 4):  # 1, 2, 3 years back
                            source_year = str(int(year_str) - year_offset)
                            source_af = AssignedForm.query.filter_by(
                                template_id=template_id,
                                period_name=source_year
                            ).first()
                            if source_af:
                                source_aes = source_af.country_statuses.filter_by(entity_id=country_id, entity_type='country').first()
                                if source_aes:
                                    source_fd = FormData.query.filter_by(
                                        assignment_entity_status_id=source_aes.id,
                                        form_item_id=item_id,
                                    ).first()
                                    if source_fd:
                                        try:
                                            val = getattr(source_fd, "total_value", None)
                                            if val is None:
                                                val = getattr(source_fd, "value", None)
                                            if val is not None:
                                                # Coerce to float for robustness (Decimal/str -> float)
                                                coerced = float(val)
                                                source_data = source_data or []
                                                source_data.append(coerced)
                                                source_periods.append(source_year)
                                        except (ValueError, TypeError):
                                            # Non-numeric values are ignored for averaging.
                                            pass
                    else:  # last_year method
                        prev_fd: Optional[FormData] = FormData.query.filter_by(
                            assignment_entity_status_id=prev_aes.id,
                            form_item_id=item_id,
                        ).first()
                        if prev_fd:
                            try:
                                # For single_choice items, prioritize value field over total_value
                                # since text values like "Male" are stored in the value field
                                val = getattr(prev_fd, "value", None)
                                if val is not None and val != '':
                                    source_data = val
                                    source_periods = [prev_year_str]
                                else:
                                    # Fallback to total_value for numeric items
                                    val = getattr(prev_fd, "total_value", None)
                                    if val is not None:
                                        source_data = val
                                        source_periods = [prev_year_str]
                            except Exception as e:
                                logger.debug("Prev FormData missing expected attributes: %s", e)

                    if source_data is None:
                        continue

                    # When source row used disaggregation/matrix payload, carry it forward into imputed_disagg_data
                    # (this corresponds to FormData.disagg_data in the same way imputed_value corresponds to value).
                    source_disagg_data = None
                    try:
                        if imputation_method == 'last_year':
                            prev_fd: Optional[FormData] = FormData.query.filter_by(
                                assignment_entity_status_id=prev_aes.id,
                                form_item_id=item_id,
                            ).first()
                            if prev_fd and getattr(prev_fd, "disagg_data", None) is not None:
                                source_disagg_data = prev_fd.disagg_data
                    except Exception as e:
                        logger.debug("Could not get source disagg_data: %s", e)
                        source_disagg_data = None

                    # Calculate imputed value based on data type
                    if imputation_method == 'three_year_avg' and isinstance(source_data, list) and len(source_data) > 0:
                        # For three-year average, only handle numeric values
                        numeric_values = []
                        for val in source_data:
                            with suppress((ValueError, TypeError)):
                                numeric_values.append(float(val))

                        if numeric_values:
                            imputed_value = sum(numeric_values) / len(numeric_values)
                        else:
                            continue
                    elif imputation_method == 'last_year':
                        # For last year method, handle both numeric and text values
                        imputed_value = source_data
                    else:
                        continue

                    # Determine if this is a numeric or text value
                    is_numeric = False
                    try:
                        float(imputed_value)
                        is_numeric = True
                    except (ValueError, TypeError):
                        is_numeric = False

                    # Format the imputed value based on type
                    if is_numeric:
                        # For numeric values, always store as whole number
                        try:
                            f = float(imputed_value)
                            imputed_formatted = int(f)  # Always whole number
                        except (ValueError, TypeError):
                            continue
                    else:
                        # For text values (like single_choice), store as string
                        imputed_formatted = str(imputed_value)

                    # Use get_or_create pattern to avoid duplicate key errors
                    current_fd = FormData.query.filter_by(
                        assignment_entity_status_id=aes.id,
                        form_item_id=item_id,
                    ).first()

                    if current_fd:
                        # Update existing entry
                        current_fd.imputed_value = imputed_formatted
                        if source_disagg_data is not None:
                            current_fd.imputed_disagg_data = source_disagg_data
                        db.session.add(current_fd)
                        total_rows_updated += 1
                    else:
                        # Create new entry only if it doesn't exist
                        try:
                            current_fd = FormData(
                                assignment_entity_status_id=aes.id,
                                form_item_id=item_id,
                                imputed_value=imputed_formatted,
                                imputed_disagg_data=source_disagg_data,
                            )
                            db.session.add(current_fd)
                            db.session.flush()  # Flush to get the ID and check for conflicts
                            total_rows_created += 1
                        except Exception as e:
                            # If there's a conflict, try to get the existing entry
                            db.session.rollback()
                            current_fd = FormData.query.filter_by(
                                assignment_entity_status_id=aes.id,
                                form_item_id=item_id,
                            ).first()
                            if current_fd:
                                current_fd.imputed_value = imputed_formatted
                                if source_disagg_data is not None:
                                    current_fd.imputed_disagg_data = source_disagg_data
                                db.session.add(current_fd)
                                total_rows_updated += 1
                            else:
                                # If we still can't find it, skip this entry
                                logger.warning(
                                    "Imputation: could not create or find FormData for ACS %s, item %s",
                                    aes.id,
                                    item_id,
                                )
                                continue

                    items_imputed_for_country += 1
                    total_items_imputed += 1

                if items_imputed_for_country > 0:
                    total_countries_processed += 1

        db.session.commit()
        # Ensure form_data sequence is consistent after inserts
        with suppress(Exception):
            reset_form_data_sequence_helper()

        return {
            "success": True,
            "template_id": template_id,
            "target_period": year_str,
            "source_period": prev_year_str,
            "countries_processed": total_countries_processed,
            "items_imputed": total_items_imputed,
            "rows_created": total_rows_created,
            "rows_updated": total_rows_updated,
        }

    @staticmethod
    def impute_template_2_filtered(target_year: str, country_filter: Optional[str] = None, item_filter: Optional[str] = None, type_filter: Optional[str] = None, imputation_mode: str = 'missing_only') -> Dict[str, Any]:
        """
        Impute data for Template ID 2 for the given year with optional filters.

        Args:
            target_year: The year to impute data for
            country_filter: Optional country name to filter by
            item_filter: Optional item label to filter by
            type_filter: Optional item type to filter by
            imputation_mode: 'missing_only' to only fill missing data, 'all' to overwrite all data

        Returns:
            Summary dict with counts and success status

        Note:
            - For numeric values: always store as whole numbers (integers)
            - For text/single_choice values: store as strings (e.g., "male", "female")
        """
        template_id = 2
        year_str = str(target_year)
        try:
            prev_year_str = str(int(year_str) - 1)
        except Exception as e:
            logger.debug("Could not parse year for prev_year_str, using suffix fallback: %s", e)
            parts = year_str.split()
            if parts and parts[0].isdigit():
                parts[0] = str(int(parts[0]) - 1)
                prev_year_str = " ".join(parts)
            else:
                prev_year_str = year_str  # fallback no-op

        # Validate template exists
        template = FormTemplate.query.get(template_id)
        if not template:
            return {
                "success": False,
                "error": f"Template {template_id} not found",
            }

        # Fetch all items under this template
        form_items_query = FormItem.query.filter_by(template_id=template_id)

        # Apply item filter if specified
        if item_filter:
            form_items_query = form_items_query.filter(FormItem.label == item_filter)

        # Apply type filter if specified
        if type_filter:
            form_items_query = form_items_query.filter(FormItem.type == type_filter)

        form_items: List[FormItem] = form_items_query.all()

        if not form_items:
            filter_msg = []
            if item_filter:
                filter_msg.append(f"item filter '{item_filter}'")
            if type_filter:
                filter_msg.append(f"type filter '{type_filter}'")
            filter_text = f" with {' and '.join(filter_msg)}" if filter_msg else ""

            return {
                "success": False,
                "error": f"No form items found for template {template_id}{filter_text}",
            }

        # Map items by id for quick access
        item_ids = [fi.id for fi in form_items]

        # Get all assignments for target and previous year
        target_assignments: List[AssignedForm] = (
            AssignedForm.query.filter_by(template_id=template_id, period_name=year_str).all()
        )

        if len(target_assignments) == 0:
            return {
                "success": False,
                "error": f"No assignments found for template {template_id} and year {year_str}. Please create an assignment for this year first.",
            }

        prev_assignments_by_country: Dict[int, AssignedForm] = {}
        prev_assignments = AssignedForm.query.filter_by(template_id=template_id, period_name=prev_year_str).all()

        if len(prev_assignments) == 0:
            return {
                "success": False,
                "error": f"No assignments found for template {template_id} and previous year {prev_year_str}. Cannot impute without source data.",
            }

        for af in prev_assignments:
            # Map country_id -> prev assignment via its AES entries
            for aes in af.country_statuses.all():
                if aes.country_id not in prev_assignments_by_country:
                    prev_assignments_by_country[aes.country_id] = af

        total_countries_processed = 0
        total_items_imputed = 0
        total_rows_created = 0
        total_rows_updated = 0

        # Check if there are any countries that can be imputed
        target_country_ids = set()
        for assignment in target_assignments:
            for aes in assignment.country_statuses.all():
                if aes.country:
                    target_country_ids.add(aes.country_id)

        prev_country_ids = set(prev_assignments_by_country.keys())
        overlapping_countries = target_country_ids.intersection(prev_country_ids)

        if len(overlapping_countries) == 0:
            return {
                "success": False,
                "error": f"No countries found in both {year_str} and {prev_year_str}. Cannot impute without overlapping countries.",
            }

        for assignment in target_assignments:
            # For each country assignment in the target year
            for aes in assignment.country_statuses.all():
                country_id = aes.country_id
                country = aes.country
                if not country:
                    continue

                country_name = country.name

                # Apply country filter if specified
                if country_filter and country_name != country_filter:
                    continue

                prev_af = prev_assignments_by_country.get(country_id)
                if not prev_af:
                    continue

                # Find the prev year's AES for the same country
                prev_aes: Optional[AssignmentEntityStatus] = (
                    prev_af.country_statuses.filter_by(entity_id=country_id, entity_type='country').first()
                )
                if not prev_aes:
                    continue

                # For each item, copy prev data into current.imputed_value
                items_imputed_for_country = 0

                # Only emit per-country debug logs when explicitly filtering
                if country_filter and logger.isEnabledFor(logging.DEBUG):
                    logger.debug("Imputation (filtered): country=%s items_to_check=%s", country_name, len(item_ids))

                for item_id in item_ids:
                    # Get the form item to check its imputation method
                    form_item = next((fi for fi in form_items if fi.id == item_id), None)
                    if not form_item:
                        continue

                    # Apply item filter if specified
                    if item_filter and form_item.label != item_filter:
                        continue

                    imputation_method = form_item.config.get('imputation_method', 'last_year') if form_item.config else 'last_year'

                    # Skip items that should not be imputed
                    if imputation_method == 'no_imputation':
                        continue

                    # Get source data based on method
                    source_data = None
                    source_periods = []

                    if imputation_method == 'three_year_avg':
                        # Get data from last 3 years
                        for year_offset in range(1, 4):  # 1, 2, 3 years back
                            source_year = str(int(year_str) - year_offset)
                            source_af = AssignedForm.query.filter_by(
                                template_id=template_id,
                                period_name=source_year
                            ).first()
                            if source_af:
                                source_aes = source_af.country_statuses.filter_by(entity_id=country_id, entity_type='country').first()
                                if source_aes:
                                    source_fd = FormData.query.filter_by(
                                        assignment_entity_status_id=source_aes.id,
                                        form_item_id=item_id,
                                    ).first()
                                    if source_fd:
                                        with suppress(Exception):
                                            val = source_fd.total_value
                                            if val is None:
                                                val = source_fd.value
                                            if val is not None:
                                                # Coerce to float for robustness (Decimal/str -> float)
                                                coerced = float(val)
                                                source_data = source_data or []
                                                source_data.append(coerced)
                                                source_periods.append(source_year)
                    else:  # last_year method
                        prev_fd: Optional[FormData] = FormData.query.filter_by(
                            assignment_entity_status_id=prev_aes.id,
                            form_item_id=item_id,
                        ).first()
                        if prev_fd:
                            with suppress(Exception):
                                # For single_choice items, prioritize value field over total_value
                                # since text values like "Male" are stored in the value field
                                val = prev_fd.value
                                if val is not None and val != '':
                                    source_data = val
                                    source_periods = [prev_year_str]
                                else:
                                    # Fallback to total_value for numeric items
                                    val = prev_fd.total_value
                                    if val is not None:
                                        source_data = val
                                        source_periods = [prev_year_str]

                    if source_data is None:
                        continue

                    # Calculate imputed value based on data type
                    if imputation_method == 'three_year_avg' and isinstance(source_data, list) and len(source_data) > 0:
                        # For three-year average, only handle numeric values
                        numeric_values = []
                        for val in source_data:
                            with suppress((ValueError, TypeError)):
                                numeric_values.append(float(val))

                        if numeric_values:
                            imputed_value = sum(numeric_values) / len(numeric_values)
                        else:
                            continue
                    elif imputation_method == 'last_year':
                        # For last year method, handle both numeric and text values
                        imputed_value = source_data
                    else:
                        continue

                    # Determine if this is a numeric or text value
                    is_numeric = False
                    try:
                        float(imputed_value)
                        is_numeric = True
                    except (ValueError, TypeError):
                        is_numeric = False

                    # Format the imputed value based on type
                    if is_numeric:
                        # For numeric values, always store as whole number
                        try:
                            f = float(imputed_value)
                            imputed_formatted = int(f)  # Always whole number
                        except (ValueError, TypeError):
                            continue
                    else:
                        # For text values (like single_choice), store as string
                        imputed_formatted = str(imputed_value)

                    current_fd: Optional[FormData] = FormData.query.filter_by(
                        assignment_entity_status_id=aes.id,
                        form_item_id=item_id,
                    ).first()

                    # Check if we should impute based on mode and existing data
                    should_impute = True
                    if imputation_mode == 'missing_only' and current_fd:
                        # Check if there's already data (either value or imputed_value)
                        has_existing_data = (
                            (current_fd.value is not None and current_fd.value != '') or
                            (current_fd.disagg_data is not None) or
                            (current_fd.imputed_value is not None and current_fd.imputed_value != '') or
                            (getattr(current_fd, "imputed_disagg_data", None) is not None)
                        )
                        if has_existing_data:
                            should_impute = False

                    if should_impute:
                        if current_fd:
                            # Update existing entry
                            current_fd.imputed_value = imputed_formatted
                            # Carry-forward disagg payload for last_year method when present
                            if imputation_method == "last_year":
                                try:
                                    prev_fd: Optional[FormData] = FormData.query.filter_by(
                                        assignment_entity_status_id=prev_aes.id,
                                        form_item_id=item_id,
                                    ).first()
                                    if prev_fd and getattr(prev_fd, "disagg_data", None) is not None:
                                        current_fd.imputed_disagg_data = prev_fd.disagg_data
                                except Exception as e:
                                    logger.debug("Could not copy imputed_disagg_data from prev: %s", e)
                            db.session.add(current_fd)
                            total_rows_updated += 1
                        else:
                            # Create new entry only if it doesn't exist
                            try:
                                imputed_disagg_data = None
                                if imputation_method == "last_year":
                                    with suppress(Exception):
                                        prev_fd: Optional[FormData] = FormData.query.filter_by(
                                            assignment_entity_status_id=prev_aes.id,
                                            form_item_id=item_id,
                                        ).first()
                                        if prev_fd and getattr(prev_fd, "disagg_data", None) is not None:
                                            imputed_disagg_data = prev_fd.disagg_data
                                current_fd = FormData(
                                    assignment_entity_status_id=aes.id,
                                    form_item_id=item_id,
                                    imputed_value=imputed_formatted,
                                    imputed_disagg_data=imputed_disagg_data,
                                )
                                db.session.add(current_fd)
                                db.session.flush()  # Flush to get the ID and check for conflicts
                                total_rows_created += 1
                            except Exception as e:
                                # If there's a conflict, try to get the existing entry
                                db.session.rollback()
                                current_fd = FormData.query.filter_by(
                                    assignment_entity_status_id=aes.id,
                                    form_item_id=item_id,
                                ).first()
                                if current_fd:
                                    current_fd.imputed_value = imputed_formatted
                                    if imputation_method == "last_year":
                                        with suppress(Exception):
                                            prev_fd: Optional[FormData] = FormData.query.filter_by(
                                                assignment_entity_status_id=prev_aes.id,
                                                form_item_id=item_id,
                                            ).first()
                                            if prev_fd and getattr(prev_fd, "disagg_data", None) is not None:
                                                current_fd.imputed_disagg_data = prev_fd.disagg_data
                                    db.session.add(current_fd)
                                    total_rows_updated += 1
                                else:
                                    # If we still can't find it, skip this entry
                                    logger.warning(
                                        "Imputation (filtered): could not create or find FormData for ACS %s, item %s",
                                        aes.id,
                                        item_id,
                                    )
                                    continue

                        items_imputed_for_country += 1
                        total_items_imputed += 1

                if items_imputed_for_country > 0:
                    total_countries_processed += 1

        db.session.commit()
        # Ensure form_data sequence is consistent after inserts
        with suppress(Exception):
            reset_form_data_sequence_helper()

        return {
            "success": True,
            "template_id": template_id,
            "target_period": year_str,
            "source_period": prev_year_str,
            "countries_processed": total_countries_processed,
            "items_imputed": total_items_imputed,
            "rows_created": total_rows_created,
            "rows_updated": total_rows_updated,
        }
