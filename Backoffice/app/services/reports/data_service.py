"""Execute report widgets and return chart/table payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.extensions import db
from app.models import IndicatorBank, ReportDefinition, User
from app.services.data_retrieval.aggregation import (
    AggregationFilters,
    aggregate_indicator,
    aggregate_indicator_by_country,
    aggregate_indicator_dashboard,
    aggregate_indicator_timeseries,
    assignment_list_rows,
    assignment_status_counts,
    indicator_value_rows,
)
from app.services.reports.definition_service import (
    ReportDefinitionService,
    narrow_id_list,
    resolve_user_scope,
)
from app.services.reports.footnote_service import resolve_dynamic_widget_footnote, resolve_widget_footnote
from app.services.reports.indicator_dashboard_helpers import dashboard_table_rows, ns_table_mode
from app.services.reports.indicator_rule_service import (
    resolve_indicator_bank_ids,
    resolve_indicator_bank_rows,
    resolve_indicators_grouped_by_spef,
    spef_section_title,
)


@dataclass
class FilterContext:
    template_ids: list[int] = field(default_factory=list)
    period_names: list[str] = field(default_factory=list)
    country_ids: list[int] = field(default_factory=list)
    assignment_statuses: list[str] = field(default_factory=lambda: ["submitted", "approved"])
    include_public_submissions: bool = False
    warnings: list[str] = field(default_factory=list)


class ReportDataService:
    @staticmethod
    def resolve_report_filters(
        report: ReportDefinition,
        user: User,
        runtime_overrides: dict[str, Any] | None = None,
    ) -> FilterContext:
        definition = report.definition_json or {}
        filters = definition.get("filters") or {}
        scope = report.scope_json or {}
        user_scope = resolve_user_scope(user)
        warnings: list[str] = []

        template_ids, w1 = narrow_id_list(
            (runtime_overrides or {}).get("template_ids") or filters.get("template_ids") or scope.get("template_ids"),
            user_scope["template_ids"],
        )
        country_ids, w2 = narrow_id_list(
            (runtime_overrides or {}).get("country_ids") or filters.get("country_ids") or scope.get("country_ids"),
            user_scope["country_ids"],
        )
        warnings.extend(w1)
        warnings.extend(w2)

        period_names = list(
            (runtime_overrides or {}).get("period_names")
            or filters.get("period_names")
            or []
        )
        statuses = list(
            (runtime_overrides or {}).get("assignment_statuses")
            or filters.get("assignment_statuses")
            or ["submitted", "approved"]
        )

        return FilterContext(
            template_ids=template_ids,
            period_names=period_names,
            country_ids=country_ids,
            assignment_statuses=statuses,
            include_public_submissions=bool(filters.get("include_public_submissions")),
            warnings=warnings,
        )

    @staticmethod
    def _resolve_indicator_ids(data_source: dict[str, Any], warnings: list[str]) -> list[int]:
        selection = data_source.get("indicator_selection") or {}
        if selection.get("mode") == "rule":
            rule = selection.get("rule") or {}
            ids = resolve_indicator_bank_ids(rule)
            if not ids:
                warnings.append("Indicator rule matched no indicators in the bank.")
            return ids
        ids = list(data_source.get("indicator_bank_ids") or [])
        if data_source.get("indicator_bank_id"):
            ids = [int(data_source["indicator_bank_id"])]
        return ids

    @staticmethod
    def _aggregation_filters(ctx: FilterContext, data_source: dict[str, Any]) -> AggregationFilters:
        warnings = list(ctx.warnings)
        ib_ids = ReportDataService._resolve_indicator_ids(data_source, warnings)
        return AggregationFilters(
            template_ids=ctx.template_ids,
            period_names=ctx.period_names,
            country_ids=ctx.country_ids,
            assignment_statuses=ctx.assignment_statuses,
            indicator_bank_ids=list(ib_ids),
            include_public_submissions=ctx.include_public_submissions,
        )

    @staticmethod
    def _primary_template_id(ctx: FilterContext) -> int | None:
        return ctx.template_ids[0] if ctx.template_ids else None

    @staticmethod
    def _finalize_widget_payload(widget: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        footnote = resolve_widget_footnote(widget)
        if footnote:
            payload["footnote"] = footnote
        return payload

    @staticmethod
    def _dynamic_widget_for_indicator(
        section: dict[str, Any],
        row: IndicatorBank,
        *,
        widget_type: str,
        kind: str,
        metric: str,
    ) -> dict[str, Any]:
        widget: dict[str, Any] = {
            "id": f"{section['id']}-dyn-{row.id}",
            "type": widget_type,
            "title": row.name or f"Indicator {row.id}",
            "data_source": {
                "kind": kind,
                "indicator_bank_id": row.id,
                "metric": metric,
                "indicator_selection": {"mode": "manual"},
            },
        }
        footnote = resolve_dynamic_widget_footnote(section, row)
        if footnote:
            widget["footnote"] = footnote
        return widget

    @staticmethod
    def expand_sections(definition: dict[str, Any]) -> list[dict[str, Any]]:
        """Expand sections with dynamic indicator rules into runtime widget lists."""
        expanded: list[dict[str, Any]] = []
        for section in definition.get("sections") or []:
            dyn = section.get("dynamic_indicators") or {}
            if not dyn.get("enabled"):
                expanded.append(section)
                continue
            rule = dyn.get("rule") or {}
            widget_type = dyn.get("widget_type") or "kpi"
            kind = dyn.get("data_source_kind") or "indicator_aggregate"
            metric = dyn.get("metric") or "sum"

            if dyn.get("group_by") == "spef_section":
                grouped = resolve_indicators_grouped_by_spef(rule)
                base_order = int(section.get("order") or 0)
                for idx, (spef_code, indicators) in enumerate(grouped):
                    widgets = [
                        ReportDataService._dynamic_widget_for_indicator(
                            section,
                            row,
                            widget_type=widget_type,
                            kind=kind,
                            metric=metric,
                        )
                        for row in indicators
                    ]
                    expanded.append(
                        {
                            "id": f"{section['id']}-{spef_code.lower()}",
                            "title": spef_section_title(indicators, spef_code),
                            "order": base_order + idx,
                            "footnote": section.get("footnote"),
                            "widgets": widgets,
                            "_dynamic_source_count": len(indicators),
                            "_spef_code": spef_code,
                        }
                    )
                continue

            rows = resolve_indicator_bank_rows(rule)
            widgets = [
                ReportDataService._dynamic_widget_for_indicator(
                    section,
                    row,
                    widget_type=widget_type,
                    kind=kind,
                    metric=metric,
                )
                for row in rows
            ]
            expanded.append({**section, "widgets": widgets, "_dynamic_source_count": len(rows)})
        return expanded

    @staticmethod
    def execute_widget(
        widget: dict[str, Any],
        ctx: FilterContext,
    ) -> dict[str, Any]:
        wtype = widget.get("type")
        title = widget.get("title") or ""
        data_source = widget.get("data_source") or {}

        if wtype == "text":
            return {
                "widget_id": widget.get("id"),
                "type": "text",
                "title": title,
                "content": widget.get("content") or "",
            }

        kind = data_source.get("kind")
        meta = {"warnings": list(ctx.warnings)}

        if kind == "assignment_status_counts":
            rows = assignment_status_counts(ReportDataService._aggregation_filters(ctx, data_source))
            if wtype == "kpi":
                total = sum(r["count"] for r in rows)
                return {
                    "widget_id": widget.get("id"),
                    "type": "kpi",
                    "title": title,
                    "value": total,
                    "meta": meta,
                }
            if wtype == "pie":
                return {
                    "widget_id": widget.get("id"),
                    "type": "pie",
                    "title": title,
                    "chart_payload": {
                        "type": "pie",
                        "title": title,
                        "slices": [{"label": r["status"], "value": r["count"]} for r in rows],
                    },
                    "meta": meta,
                }
            return {
                "widget_id": widget.get("id"),
                "type": "table",
                "title": title,
                "columns": ["status", "count"],
                "rows": rows,
                "meta": meta,
            }

        if kind == "assignment_list":
            limit = int(data_source.get("limit") or 500)
            rows = assignment_list_rows(ReportDataService._aggregation_filters(ctx, data_source), limit=limit)
            return {
                "widget_id": widget.get("id"),
                "type": "table",
                "title": title,
                "columns": ["country", "status", "completion_rate", "due_date"],
                "rows": rows,
                "meta": meta,
            }

        resolved_ids = ReportDataService._resolve_indicator_ids(data_source, meta["warnings"])

        if kind == "indicator_values":
            limit = int(data_source.get("limit") or 1000)
            rows = indicator_value_rows(ReportDataService._aggregation_filters(ctx, data_source), limit=limit)
            return {
                "widget_id": widget.get("id"),
                "type": "table",
                "title": title,
                "columns": ["indicator", "country_id", "period_name", "value", "num_value"],
                "rows": rows,
                "meta": meta,
            }

        if kind == "indicator_set_aggregate" and resolved_ids:
            template_id = ReportDataService._primary_template_id(ctx)
            period = ctx.period_names[0] if ctx.period_names else ""
            metric = data_source.get("metric") or "sum"
            table_rows = []
            if template_id:
                for ib_id in resolved_ids:
                    agg = aggregate_indicator(
                        template_id=template_id,
                        indicator_bank_id=int(ib_id),
                        period_name=period,
                        country_ids=ctx.country_ids or None,
                        assignment_statuses=ctx.assignment_statuses,
                    )
                    indicator = db.session.get(IndicatorBank, int(ib_id))
                    key = metric if metric in agg else "value"
                    val = agg.get(key if key != "sum" else "value")
                    table_rows.append(
                        {
                            "indicator": indicator.name if indicator else str(ib_id),
                            "indicator_bank_id": ib_id,
                            "value": val,
                            "implementing": agg.get("implementing"),
                            "reported_count": agg.get("reported_count"),
                        }
                    )
            return {
                "widget_id": widget.get("id"),
                "type": "table",
                "title": title,
                "columns": ["indicator", "value", "implementing", "reported_count"],
                "rows": table_rows,
                "meta": {**meta, "matched_indicators": len(resolved_ids)},
            }

        template_id = ReportDataService._primary_template_id(ctx)
        indicator_id = resolved_ids[0] if len(resolved_ids) == 1 else data_source.get("indicator_bank_id")
        metric = data_source.get("metric") or "sum"

        if len(resolved_ids) > 1 and kind in {"indicator_aggregate", "indicator_timeseries", "indicator_by_country", "indicator_by_dimension"}:
            if wtype == "kpi":
                return ReportDataService.execute_widget(
                    {
                        **widget,
                        "type": "table",
                        "title": title or "Indicators",
                        "data_source": {**data_source, "kind": "indicator_set_aggregate"},
                    },
                    ctx,
                )

        if kind == "indicator_aggregate" and template_id and indicator_id:
            period = ctx.period_names[0] if ctx.period_names else ""
            agg = aggregate_indicator(
                template_id=template_id,
                indicator_bank_id=int(indicator_id),
                period_name=period,
                country_ids=ctx.country_ids or None,
                assignment_statuses=ctx.assignment_statuses,
            )
            key = metric if metric in agg else "value"
            val = agg.get(key if key != "sum" else "value")
            indicator = db.session.get(IndicatorBank, int(indicator_id))
            return {
                "widget_id": widget.get("id"),
                "type": "kpi",
                "title": title,
                "value": val,
                "metric": indicator.name if indicator else str(indicator_id),
                "meta": meta,
            }

        if kind == "indicator_timeseries" and template_id and indicator_id and wtype == "line":
            series = aggregate_indicator_timeseries(
                template_id=template_id,
                indicator_bank_id=int(indicator_id),
                country_ids=ctx.country_ids or None,
                assignment_statuses=ctx.assignment_statuses,
            )
            indicator = db.session.get(IndicatorBank, int(indicator_id))
            metric_name = indicator.name if indicator else str(indicator_id)
            value_label = (indicator.unit or "Value").strip() if indicator else "Value"
            return {
                "widget_id": widget.get("id"),
                "type": "line",
                "title": title or metric_name,
                "chart_payload": {
                    "type": "line",
                    "metric": value_label,
                    "series": series,
                },
                "meta": meta,
            }

        if kind == "indicator_dashboard" and template_id and indicator_id and wtype in {"indicator_dashboard", "line"}:
            dashboard = aggregate_indicator_dashboard(
                template_id=template_id,
                indicator_bank_id=int(indicator_id),
                country_ids=ctx.country_ids or None,
                assignment_statuses=ctx.assignment_statuses,
                period_names=ctx.period_names or None,
            )
            indicator = db.session.get(IndicatorBank, int(indicator_id))
            metric_name = indicator.name if indicator else str(indicator_id)
            value_label = (indicator.unit or "Value").strip() if indicator else "Value"
            table_mode = ns_table_mode(
                indicator.type if indicator else None,
                indicator.unit if indicator else None,
            )
            show_reporting, show_implementing = dashboard_table_rows(ns_table_mode=table_mode)
            return {
                "widget_id": widget.get("id"),
                "type": "indicator_dashboard",
                "title": title or metric_name,
                "chart_payload": {
                    "type": "line",
                    "metric": value_label,
                    "series": dashboard["series"],
                },
                "dashboard": {
                    "years": dashboard["years"],
                    "values": dashboard["values"],
                    "reporting": dashboard["reporting"],
                    "implementing": dashboard["implementing"],
                    "show_reporting": show_reporting,
                    "show_implementing": show_implementing,
                    "table_labels": {
                        "year": "Year",
                        "reporting": "Reporting NS",
                        "implementing": "Implementing NS",
                    },
                },
                "meta": meta,
            }

        if kind in {"indicator_by_country", "indicator_by_dimension"} and template_id and indicator_id and wtype == "bar":
            countries = aggregate_indicator_by_country(
                template_id=template_id,
                indicator_bank_id=int(indicator_id),
                period_names=ctx.period_names,
                country_ids=ctx.country_ids or None,
                assignment_statuses=ctx.assignment_statuses,
                metric=metric,
            )
            indicator = db.session.get(IndicatorBank, int(indicator_id))
            metric_name = indicator.name if indicator else str(indicator_id)
            return {
                "widget_id": widget.get("id"),
                "type": "bar",
                "title": title,
                "chart_payload": {
                    "type": "bar",
                    "title": title or f"{metric_name} by country",
                    "metric": metric_name,
                    "categories": [{"label": c["country"], "value": c["value"]} for c in countries],
                    "orientation": "horizontal" if len(countries) > 6 else "vertical",
                },
                "meta": meta,
            }

        if kind == "categorical_counts" and wtype == "pie":
            rows = assignment_status_counts(ReportDataService._aggregation_filters(ctx, data_source))
            return {
                "widget_id": widget.get("id"),
                "type": "pie",
                "title": title,
                "chart_payload": {
                    "type": "pie",
                    "title": title,
                    "slices": [{"label": r["status"], "value": r["count"]} for r in rows],
                },
                "meta": meta,
            }

        if kind == "raw_data":
            limit = int(data_source.get("limit") or 500)
            rows = indicator_value_rows(ReportDataService._aggregation_filters(ctx, data_source), limit=limit)
            columns = data_source.get("columns") or ["indicator", "country_id", "period_name", "value"]
            return {
                "widget_id": widget.get("id"),
                "type": "table",
                "title": title,
                "columns": columns,
                "rows": rows,
                "meta": meta,
            }

        return {
            "widget_id": widget.get("id"),
            "type": wtype,
            "title": title,
            "error": "Unsupported widget configuration or missing template/indicator",
            "meta": meta,
        }

    @staticmethod
    def execute_report(
        report_id: int,
        user: User,
        runtime_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        report = ReportDefinitionService.get_report(report_id, user)
        ctx = ReportDataService.resolve_report_filters(report, user, runtime_overrides)
        definition = report.definition_json or {}
        widgets_out: dict[str, Any] = {}

        for section in ReportDataService.expand_sections(definition):
            for widget in section.get("widgets") or []:
                wid = widget.get("id")
                if not wid:
                    continue
                try:
                    payload = ReportDataService.execute_widget(widget, ctx)
                    widgets_out[wid] = ReportDataService._finalize_widget_payload(widget, payload)
                except Exception as exc:
                    widgets_out[wid] = {
                        "widget_id": wid,
                        "type": widget.get("type"),
                        "title": widget.get("title"),
                        "error": str(exc),
                        "meta": {"warnings": list(ctx.warnings)},
                    }

        return {
            "report_id": report.id,
            "sections": ReportDataService.expand_sections(definition),
            "widgets": widgets_out,
            "meta": {"warnings": ctx.warnings},
        }

    @staticmethod
    def execute_widget_by_id(
        report_id: int,
        widget_id: str,
        user: User,
        runtime_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        report = ReportDefinitionService.get_report(report_id, user)
        ctx = ReportDataService.resolve_report_filters(report, user, runtime_overrides)
        definition = report.definition_json or {}
        for section in ReportDataService.expand_sections(definition):
            for widget in section.get("widgets") or []:
                if widget.get("id") == widget_id:
                    return ReportDataService._finalize_widget_payload(
                        widget,
                        ReportDataService.execute_widget(widget, ctx),
                    )
        return {"widget_id": widget_id, "error": "Widget not found", "meta": {"warnings": ctx.warnings}}
