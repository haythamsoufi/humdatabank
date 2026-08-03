"""Export report widget payloads to Excel and PDF."""

from __future__ import annotations

import base64
import io
import re
from typing import Any

from flask import render_template

from app.models import ReportDefinition


class ReportExportService:
    @staticmethod
    def export_excel(report: ReportDefinition, run_result: dict[str, Any]) -> bytes:
        from openpyxl import Workbook
        from openpyxl.utils import get_column_letter

        wb = Workbook()
        summary = wb.active
        summary.title = "Summary"
        summary.append(["Report", report.title])
        summary.append(["Slug", report.slug])
        summary.append([])

        widgets = run_result.get("widgets") or {}
        for idx, (wid, payload) in enumerate(widgets.items()):
            title = payload.get("title") or wid
            sheet_name = re.sub(r"[^A-Za-z0-9 _-]", "", title)[:28] or f"Widget{idx + 1}"
            if idx == 0 and summary.title == "Summary":
                ws = summary
            else:
                ws = wb.create_sheet(title=sheet_name)
            ws.append(["Widget", title])
            if payload.get("type") == "kpi":
                ws.append(["Value", payload.get("value")])
                continue
            if payload.get("type") in {"table"} or payload.get("rows"):
                columns = payload.get("columns") or []
                rows = payload.get("rows") or []
                if columns:
                    ws.append(list(columns))
                for row in rows:
                    if isinstance(row, dict):
                        ws.append([row.get(c) for c in columns] if columns else list(row.values()))
                    else:
                        ws.append(list(row))
                continue
            chart = payload.get("chart_payload") or {}
            if chart.get("type") == "line":
                ws.append(["Year", "Value"])
                for pt in chart.get("series") or []:
                    ws.append([pt.get("x"), pt.get("y")])
            elif chart.get("type") == "bar":
                ws.append(["Label", "Value"])
                for cat in chart.get("categories") or []:
                    ws.append([cat.get("label"), cat.get("value")])
            elif chart.get("type") == "pie":
                ws.append(["Label", "Value"])
                for sl in chart.get("slices") or []:
                    ws.append([sl.get("label"), sl.get("value")])

        for sheet in wb.worksheets:
            for col_idx, _ in enumerate(sheet.iter_cols(min_row=1, max_row=1), start=1):
                sheet.column_dimensions[get_column_letter(col_idx)].width = 18

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    @staticmethod
    def export_pdf(
        report: ReportDefinition,
        run_result: dict[str, Any],
        *,
        chart_images: dict[str, str] | None = None,
    ) -> bytes:
        from flask import current_app, render_template

        chart_images = chart_images or {}
        html = render_template(
            "admin/reports/export_pdf.html",
            report=report,
            widgets=run_result.get("widgets") or {},
            chart_images=chart_images,
        )
        try:
            from weasyprint import CSS, HTML  # type: ignore
        except Exception as exc:
            raise RuntimeError("PDF generation is not available on this deployment.") from exc

        pdf_css = """
            @page { size: A4; margin: 18mm; }
            body { font-family: Arial, sans-serif; color: #111827; font-size: 11pt; }
            h1 { font-size: 18pt; margin-bottom: 8px; }
            h2 { font-size: 13pt; margin-top: 16px; border-bottom: 1px solid #ccc; }
            .widget { margin: 12px 0 20px; page-break-inside: avoid; }
            table { width: 100%; border-collapse: collapse; margin-top: 8px; }
            th, td { border: 1px solid #ddd; padding: 4px 6px; text-align: left; }
            th { background: #f3f4f6; }
            img { max-width: 100%; height: auto; }
        """
        return HTML(string=html).write_pdf(stylesheets=[CSS(string=pdf_css)])

    @staticmethod
    def decode_chart_images(raw: dict[str, Any] | None) -> dict[str, bytes]:
        if not raw:
            return {}
        decoded: dict[str, bytes] = {}
        for wid, data_url in raw.items():
            if not isinstance(data_url, str):
                continue
            match = re.match(r"^data:image/png;base64,(.+)$", data_url.strip())
            if not match:
                continue
            try:
                decoded[wid] = base64.b64decode(match.group(1))
            except Exception:
                continue
        return decoded
