"""One-off smoke test for cairosvg + WeasyPrint render stack."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from pb_figures.donut_chart import render_donut_svg  # noqa: E402
from pb_figures.line_chart import render_line_chart_svg  # noqa: E402
from pb_figures.render_pdf import prepare_html_for_pdf, render_report_pdf  # noqa: E402
from pb_figures.svg_raster import write_svg_png  # noqa: E402


def main() -> None:
    svg = render_donut_svg({"value": 75, "target": 100, "value_label": "75%"})
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        donut_png = tmp_path / "donut.png"
        write_svg_png(svg, donut_png, width=64, height=64)
        assert donut_png.stat().st_size > 100

        line_svg = render_line_chart_svg(
            {
                "values": [1, 2, 3],
                "value_labels": ["1", "2", "3"],
                "annual_target": 3,
                "annual_target_label": "3",
            },
            481,
            show_value_labels=True,
            show_target_labels=True,
            target_label="Target",
        )
        line_png = tmp_path / "line.png"
        write_svg_png(line_svg, line_png, width=481, height=110)
        assert line_png.stat().st_size > 100

        prepared = prepare_html_for_pdf(
            '<html><body><div class="pb-lang-panel" data-lang="English"></div>'
            '<div class="pb-lang-panel" data-lang="French" hidden></div></body></html>',
            "English",
        )
        assert 'data-lang="French"' in prepared

        report_html = SCRIPTS.parent / "report" / "output" / "pb-report.html"
        if report_html.is_file():
            pdf = tmp_path / "report.pdf"
            render_report_pdf(report_html, pdf, language="English")
            assert pdf.stat().st_size > 1000
            print(f"PDF from built report OK ({pdf.stat().st_size} bytes)")
        else:
            from weasyprint import HTML

            pdf = tmp_path / "minimal.pdf"
            HTML(string="<html><body><p>ok</p></body></html>").write_pdf(pdf)
            assert pdf.stat().st_size > 100
            print("Minimal WeasyPrint PDF OK (no built report HTML on disk)")

    print("Integration smoke: ALL OK")


if __name__ == "__main__":
    main()
