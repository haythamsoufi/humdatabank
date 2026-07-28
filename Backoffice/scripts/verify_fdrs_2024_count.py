"""One-off verification: FDRS Income Sources country counts for 2024."""
from sqlalchemy import func

from app import create_app
from app.extensions import db
from app.models import FormData, AssignedForm
from app.models.assignments import AssignmentEntityStatus
from app.services.ai.data.form_retrieval import get_form_field_values_for_all_countries
from app.services.data_retrieval_form_helpers import (
    resolve_template_by_identifier,
    resolve_form_items_by_label,
    formdata_has_value_filters,
    apply_bulk_rbac,
    resolve_bulk_allowed_country_ids,
    pick_most_recent_per_country,
    breakdown_from_disagg,
    extract_numeric_from_formdata,
)
from app.services.data_retrieval_shared import (
    get_effective_request_user,
    can_view_non_public_form_items,
    escape_like_pattern,
)


def main() -> None:
    app = create_app("development")
    with app.app_context():
        tool = get_form_field_values_for_all_countries(
            field_label_or_name="income sources",
            template_identifier="FDRS",
            assignment_period="2024",
        )
        print("=== TOOL (assignment_period=2024, no share filter) ===")
        print("countries_with_data:", tool.get("countries_with_data"))
        print("count:", tool.get("count"))
        periods = sorted({r.get("period_used") for r in tool.get("rows", [])})
        print("distinct period_used values:", periods)

        template = resolve_template_by_identifier("FDRS")
        items = resolve_form_items_by_label("income sources", template_id=int(template.id))
        item_ids = [int(i.id) for i in items]
        viewer = get_effective_request_user()
        can_see_ifrc = can_view_non_public_form_items(viewer)
        allowed = resolve_bulk_allowed_country_ids(250)
        pat = f"%{escape_like_pattern('2024')}%"

        q = (
            db.session.query(
                AssignmentEntityStatus.entity_id.label("country_id"),
                AssignmentEntityStatus.id.label("submission_id"),
                AssignedForm.period_name.label("period_name"),
                FormData.value.label("value"),
                FormData.disagg_data.label("disagg_data"),
            )
            .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
            .join(FormData, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
            .filter(
                AssignmentEntityStatus.entity_type == "country",
                FormData.form_item_id.in_(item_ids),
                AssignedForm.template_id == int(template.id),
                AssignedForm.period_name.ilike(pat, escape="\\"),
                formdata_has_value_filters(),
            )
        )
        q = apply_bulk_rbac(q, can_see_ifrc, allowed, join_form_item=True)
        records = q.all()
        print("\n=== INDEPENDENT SQL (period_name ILIKE %2024%) ===")
        print("raw submission rows:", len(records))

        by_country = {}
        for r in records:
            cid = int(r.country_id)
            breakdown = breakdown_from_disagg(r.disagg_data, None)
            total = extract_numeric_from_formdata(r.value, r.disagg_data)
            if total is None and breakdown:
                total = sum(breakdown.values())
            if total is None and not breakdown and r.value is None:
                continue
            by_country.setdefault(cid, []).append(
                {"submission_id": int(r.submission_id), "period_name": r.period_name}
            )
        print("countries with qualifying data:", len(by_country))
        picked = pick_most_recent_per_country(by_country)
        print("after pick_most_recent_per_country:", len(picked))

        dist = (
            db.session.query(
                AssignedForm.period_name,
                func.count(func.distinct(AssignmentEntityStatus.entity_id)),
            )
            .join(AssignmentEntityStatus, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
            .join(FormData, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
            .filter(
                AssignedForm.template_id == int(template.id),
                FormData.form_item_id.in_(item_ids),
                AssignedForm.period_name.ilike(pat, escape="\\"),
                AssignmentEntityStatus.entity_type == "country",
                formdata_has_value_filters(),
            )
            .group_by(AssignedForm.period_name)
            .all()
        )
        print("\nperiod_name breakdown (ILIKE %2024%):")
        for pname, cnt in sorted(dist, key=lambda x: (-x[1], str(x[0]))):
            print(f"  {pname!r}: {cnt} countries")

        exact = (
            db.session.query(func.count(func.distinct(AssignmentEntityStatus.entity_id)))
            .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
            .join(FormData, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
            .filter(
                AssignedForm.template_id == int(template.id),
                FormData.form_item_id.in_(item_ids),
                AssignedForm.period_name == "2024",
                AssignmentEntityStatus.entity_type == "country",
                formdata_has_value_filters(),
            )
            .scalar()
        )
        print("\nexact period_name == '2024' distinct countries:", exact)

        share = get_form_field_values_for_all_countries(
            field_label_or_name="income sources",
            template_identifier="FDRS",
            assignment_period="2024",
            matrix_share_rows=["Home Government", "Foreign Government"],
            matrix_share_column="Funding",
            min_share_pct=75,
            share_match="any",
        )
        print("\n=== TOOL with share filter >=75% ===")
        print("countries_with_data:", share.get("countries_with_data"))
        print("countries_matching_filter:", share.get("countries_matching_filter"))
        for r in share.get("rows", []):
            print(f"  {r.get('country_name')} | period={r.get('period_used')} | home={r.get('home_government_pct')}%")


if __name__ == "__main__":
    main()
