"""Default P&B report translations and section order for builds without full Excel metadata."""

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
}


def default_translations_config_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for code, labels in DEFAULT_TRANSLATIONS.items():
        rows.append(
            {
                "id": code,
                "EN": labels.get("English", ""),
                "FR": labels.get("French", ""),
                "SP": labels.get("Spanish", ""),
                "AR": labels.get("Arabic", ""),
            }
        )
    return rows


def default_section_order_config_rows() -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    for part in DEFAULT_PARTS_ORDER:
        for order, section in enumerate(DEFAULT_SECTION_ORDER.get(part, []), start=1):
            rows.append({"part": part, "section": section, "order": order})
    return rows
