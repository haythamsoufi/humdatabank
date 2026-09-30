"""Fallback report metadata when SG Report.xlsx omits Translations."""

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
        "Arabic": "الأولويات الاستراتيجية",
    },
    "ui.part.ef": {
        "English": "Enabling Functions",
        "French": "Fonctions habilitantes",
        "Spanish": "Funciones de apoyo",
        "Arabic": "الوظائف التمكينية",
    },
    "ui.contents": {
        "English": "Contents",
        "French": "Sommaire",
        "Spanish": "Contenido",
        "Arabic": "المحتويات",
    },
    "ui.toc_expand": {
        "English": "Expand table of contents",
        "French": "Développer le sommaire",
        "Spanish": "Expandir índice",
        "Arabic": "توسيع جدول المحتويات",
    },
    "ui.toc_collapse": {
        "English": "Collapse table of contents",
        "French": "Réduire le sommaire",
        "Spanish": "Contraer índice",
        "Arabic": "طي جدول المحتويات",
    },
    "ui.not_available": {
        "English": "Not available yet",
        "French": "Pas encore disponible",
        "Spanish": "Aún no disponible",
        "Arabic": "غير متوفر بعد",
    },
    "ui.not_applicable": {
        "English": "n/a",
        "French": "s. o.",
        "Spanish": "n/a",
        "Arabic": "لا ينطبق",
    },
    "ui.national_societies": {
        "English": "National Societies",
        "French": "Sociétés nationales",
        "Spanish": "Sociedades Nacionales",
        "Arabic": "الجمعيات الوطنية",
    },
    "ui.table_reporting_row": {
        "English": "Reporting",
        "French": "Rapportant",
        "Spanish": "Informantes",
        "Arabic": "المبلّغة",
    },
    "ui.table_implementing_row": {
        "English": "Implementing",
        "French": "Mettant en œuvre",
        "Spanish": "Implementando",
        "Arabic": "المنفّذة",
    },
    "ui.year_header": {
        "English": "Year",
        "French": "Année",
        "Spanish": "Año",
        "Arabic": "السنة",
    },
    "footnote.default": {
        "English": (
            "*{year} data is based on reports received from {upr_ns} NSs through the unified "
            "reporting process and {fdrs_ns} NSs through FDRS. There is no complete overlap "
            "between the two data collection processes (in NSs and in indicators)."
        ),
        "French": (
            "* Les données de {year} reposent sur les rapports de {upr_ns} SN via le processus "
            "de rapport unifié et de {fdrs_ns} SN via le FDRS."
        ),
        "Spanish": (
            "* Los datos de {year} se basan en los informes de {upr_ns} Sociedades Nacionales "
            "a través del proceso unificado de presentación de informes y de {fdrs_ns} "
            "Sociedades Nacionales a través del FDRS."
        ),
        "Arabic": (
            "*تستند بيانات عام {year} إلى تقارير {upr_ns} جمعيات وطنية من خلال عملية التقارير "
            "الموحدة و{fdrs_ns} جمعية وطنية من خلال FDRS."
        ),
    },
}


def default_translations_bundle() -> tuple[dict[str, dict[str, str]], dict[str, list[str]], tuple[str, ...]]:
    return DEFAULT_TRANSLATIONS.copy(), {k: list(v) for k, v in DEFAULT_SECTION_ORDER.items()}, DEFAULT_PARTS_ORDER
