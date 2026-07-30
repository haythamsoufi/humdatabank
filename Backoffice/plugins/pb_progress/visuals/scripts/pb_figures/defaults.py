"""Fallback report metadata when SG Report.xlsx omits Translations/SectionOrder."""

from __future__ import annotations

DEFAULT_SECTION_ORDER: dict[str, list[str]] = {
    "cc": ["CC1"],
    "sp": ["SP1", "SP2", "SP3", "SP4", "SP5"],
    "ef": ["EF1", "EF2", "EF3", "EF4"],
}

DEFAULT_PARTS_ORDER: tuple[str, ...] = ("cc", "sp", "ef")

DEFAULT_TRANSLATIONS: dict[str, dict[str, str]] = {
    "report.title": {
        "English": "Plan & Budget Report — Figures",
        "French": "Rapport Plan et Budget — Graphiques",
        "Spanish": "Informe Plan y Presupuesto — Gráficos",
        "Arabic": "تقرير الخطة والميزانية — الأشكال البيانية",
    },
    "ui.part.cc": {
        "English": "Cross-cutting",
        "French": "Transversal",
        "Spanish": "Transversal",
        "Arabic": "قطاعات مشتركة",
    },
    "ui.part.sp": {
        "English": "Strategic Priorities",
        "French": "Priorités stratégiques",
        "Spanish": "Prioridades estratégicas",
        "Arabic": "الأولويات الاستراتégicas",
    },
    "ui.part.ef": {
        "English": "Enabling Functions",
        "French": "Fonctions habilitantes",
        "Spanish": "Funciones de apoyo",
        "Arabic": "الوظائف التمكينية",
    },
}


def default_translations_bundle() -> tuple[dict[str, dict[str, str]], dict[str, list[str]], tuple[str, ...]]:
    return DEFAULT_TRANSLATIONS.copy(), {k: list(v) for k, v in DEFAULT_SECTION_ORDER.items()}, DEFAULT_PARTS_ORDER
