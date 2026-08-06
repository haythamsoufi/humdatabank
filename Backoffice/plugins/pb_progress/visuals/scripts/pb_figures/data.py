"""Load SG Report.xlsx and reproduce Tableau's federated data model.

Data sources (read-only — scripts never write to these sheets):

  Final            Fact table: one row per indicator × year × source.
                   Restore via Excel Power Query; do not paste static data here.
  Mapping          Indicator metadata and translations (header row 4).
  TotalReported    Denominator for "out of N NSs" labels.
  Translations     UI labels and section titles.

Section display order comes from Indicator Bank SPEF (PB_REPORT_SECTION_ORDER at build time).

Tableau relationships replicated in build_model():
  Mapping.ID = Final.ID
  Final.Year + Final.Source = TotalReported.Year + TotalReported.Source
  section filter uses Mapping.Strategic Priority / Enabling Function
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from .config import resolve_excel

# Expected Final sheet columns (Tableau: [Final$], header row 1)
FINAL_COLUMNS = (
    "Index",
    "Strategic Priority / Enabling Function",
    "ID",
    "Source",
    "Year",
    "Value",
    "Implementing",
    "Count",
)

MAPPING_HEADER_ROW = 3  # 0-based pandas header row (Excel row 4)
SECTION_COLUMN = "Strategic Priority / Enabling Function"


class DataModelError(RuntimeError):
    """Raised when required Excel data sheets are missing or cannot be joined."""


def load_sg_report(excel_path: Path | str | None = None) -> dict[str, pd.DataFrame]:
    path = resolve_excel(excel_path)
    sheets: dict[str, pd.DataFrame] = {
        "mapping": pd.read_excel(path, sheet_name="Mapping", header=MAPPING_HEADER_ROW),
        "final": pd.read_excel(path, sheet_name="Final"),
        "total_reported": pd.read_excel(path, sheet_name="TotalReported"),
    }
    for optional in ("Translations",):
        try:
            sheets[optional.lower()] = pd.read_excel(path, sheet_name=optional)
        except ValueError:
            pass
    return sheets


def _validate_final(final: pd.DataFrame, excel_name: str) -> None:
    if final.empty:
        raise DataModelError(
            f"{excel_name} → Final sheet is empty. "
            "Restore the Power Query table on the Final sheet and refresh it."
        )

    missing = [col for col in FINAL_COLUMNS if col not in final.columns]
    if missing:
        raise DataModelError(
            f"{excel_name} → Final sheet is missing columns: {', '.join(missing)}. "
            f"Expected: {', '.join(FINAL_COLUMNS)}"
        )

    if final["ID"].isna().all():
        raise DataModelError(
            f"{excel_name} → Final sheet has no ID values. "
            "Check that the Power Query output includes the ID column."
        )


def _validate_mapping(mapping: pd.DataFrame, excel_name: str) -> None:
    if mapping.empty:
        raise DataModelError(f"{excel_name} → Mapping sheet is empty.")

    if "ID" not in mapping.columns:
        raise DataModelError(f"{excel_name} → Mapping sheet is missing an ID column.")


_TYPE_OF_MEASUREMENT_ALIASES = (
    "typeOfMeasurement",
    "Type of measurement",
    "TypeOfMeasurement",
)
_UNIT_OF_MEASUREMENT_ALIASES = (
    "unitOfMeasurement",
    "Unit of measurement",
    "UnitOfMeasurement",
)
_BANK_SHEET_NAMES = ("Indicator bank", "Indicator Bank")
_BANK_MAPPING_ID_COLUMNS = (
    "indicatorId",
    "indicator_id",
)
_BANK_ID_COLUMNS = ("ID", "id", "indicator_bank_id")


def chart_type_from_measurement(value: object) -> str | None:
    """Map Indicator bank typeOfMeasurement to report chart Type."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    key = text.lower().replace(" ", "")
    if key == "yesno":
        return "Distinct"
    if key == "number":
        return "Cumulative"
    return "Cumulative"


def normalize_type_of_measurement(value: object) -> str | None:
    """Normalize bank typeOfMeasurement for value formatting."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() in {"percentage", "percent", "%"}:
        return "Percentage"
    return text


def normalize_unit_of_measurement(value: object) -> str | None:
    """Normalize bank unitOfMeasurement for layout rules."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def _bank_id_column(df: pd.DataFrame, *, prefer_mapping_ids: bool) -> str | None:
    if prefer_mapping_ids:
        id_columns = (*_BANK_MAPPING_ID_COLUMNS, *_BANK_ID_COLUMNS)
    else:
        id_columns = _BANK_ID_COLUMNS
    return next((col for col in id_columns if col in df.columns), None)


def _bank_metadata_lookup(
    df: pd.DataFrame,
    *,
    prefer_mapping_ids: bool = False,
) -> pd.DataFrame | None:
    type_col = next((col for col in _TYPE_OF_MEASUREMENT_ALIASES if col in df.columns), None)
    unit_col = next((col for col in _UNIT_OF_MEASUREMENT_ALIASES if col in df.columns), None)
    id_col = _bank_id_column(df, prefer_mapping_ids=prefer_mapping_ids)
    if not id_col or (not type_col and not unit_col):
        return None

    bank = df.copy()
    bank[id_col] = bank[id_col].astype(str).str.strip()
    bank = bank[bank[id_col].ne("")]
    if bank.empty:
        return None

    bank = bank.drop_duplicates(subset=[id_col], keep="first").set_index(id_col)
    meta = pd.DataFrame(index=bank.index)
    if type_col:
        meta["typeOfMeasurement"] = bank[type_col].map(normalize_type_of_measurement)
        meta["Type"] = bank[type_col].map(chart_type_from_measurement)
    if unit_col:
        meta["Unit"] = bank[unit_col].map(normalize_unit_of_measurement)
    return meta


def _apply_bank_metadata(mapping: pd.DataFrame, bank_meta: pd.DataFrame | None) -> pd.DataFrame:
    if bank_meta is None or bank_meta.empty:
        return mapping
    for column in ("Type", "typeOfMeasurement", "Unit"):
        if column not in bank_meta.columns:
            continue
        mapped = mapping["ID"].map(bank_meta[column])
        has_bank_value = mapped.notna() & mapped.astype(str).str.strip().ne("")
        mapping.loc[has_bank_value, column] = mapped[has_bank_value]
    return mapping


def _enrich_mapping_from_bank(mapping: pd.DataFrame, excel_path: Path) -> pd.DataFrame:
    """Populate Type/Unit from Indicator bank (bank is authoritative)."""
    mapping = mapping.copy()
    for column in ("Type", "typeOfMeasurement", "Unit"):
        if column not in mapping.columns:
            mapping[column] = None

    for sheet_name in _BANK_SHEET_NAMES:
        try:
            bank = pd.read_excel(excel_path, sheet_name=sheet_name)
        except (ValueError, FileNotFoundError):
            continue
        mapping = _apply_bank_metadata(
            mapping,
            _bank_metadata_lookup(bank, prefer_mapping_ids=True),
        )
    return mapping


# Backwards-compatible alias used in tests.
_enrich_mapping_units = _enrich_mapping_from_bank


def _validate_join(model: pd.DataFrame, excel_name: str) -> None:
    if model.empty:
        raise DataModelError(
            f"{excel_name} → Final and Mapping could not be joined. "
            "Check that both sheets use the same ID values."
        )

    if model["Value"].notna().sum() == 0:
        raise DataModelError(
            f"{excel_name} → Join produced rows but no indicator values were found. "
            "Verify Final contains data for the indicators listed in Mapping."
        )


def load_mapping(excel_path: Path | str | None = None) -> pd.DataFrame:
    """Normalized Mapping sheet with Type/Unit enriched from Indicator bank."""
    path = resolve_excel(excel_path)
    mapping = load_sg_report(path)["mapping"].copy()
    mapping["ID"] = mapping["ID"].astype(str).str.strip()
    mapping = _enrich_mapping_from_bank(mapping, path)
    mapping["_mapping_order"] = range(len(mapping))
    return mapping.drop_duplicates(subset=["ID"], keep="first")


def build_model(
    excel_path: Path | str | None = None,
    *,
    validate: bool = True,
) -> pd.DataFrame:
    """
    Replicate Tableau relationships:
      Mapping.ID = Final.ID
      Final.Year + Final.Source = TotalReported.Year + TotalReported.Source
    """
    path = resolve_excel(excel_path)
    sheets = load_sg_report(path)
    mapping = load_mapping(path)
    final = sheets["final"].copy()
    total_reported = sheets["total_reported"].copy()

    if validate:
        _validate_final(final, path.name)
        _validate_mapping(mapping, path.name)

    final["ID"] = final["ID"].astype(str).str.strip()
    final = final[final["ID"].isin(mapping["ID"])]
    final["Year"] = final["Year"].astype(str)
    total_reported["Year"] = total_reported["Year"].astype(str)

    model = final.merge(mapping, on="ID", how="left", suffixes=("_final", "_map"))
    model = model.merge(
        total_reported,
        left_on=["Year", "Source_final"],
        right_on=["Year", "Source"],
        how="left",
    )
    model.rename(columns={"Source_final": "Source"}, inplace=True)

    section_col = f"{SECTION_COLUMN}_map"
    if section_col not in model.columns:
        section_col = SECTION_COLUMN
    model["section"] = model[section_col]

    if validate:
        _validate_join(model, path.name)

    return model


def latest_merged_total_reported(model: pd.DataFrame) -> str | None:
    tr = model.loc[model["Source"] == "Merged", ["Year", "TotalReported"]].drop_duplicates()
    if tr.empty:
        return None
    latest_year = tr["Year"].max()
    value = tr.loc[tr["Year"] == latest_year, "TotalReported"].iloc[0]
    return str(int(value)) if pd.notna(value) else None


def reporting_source_totals(
    excel_path: Path | str | None = None,
    *,
    year: str | int | None = None,
) -> dict[str, str | int | None]:
    """UPR/FDRS National Society counts from TotalReported for footnote substitution."""
    import os

    path = resolve_excel(excel_path)
    df = pd.read_excel(path, sheet_name="TotalReported", keep_default_na=False)
    if df.empty or not {"Source", "Year", "TotalReported"}.issubset(df.columns):
        raise DataModelError(f"{path.name} → TotalReported sheet is missing required columns.")

    df = df.copy()
    df["Year"] = df["Year"].astype(str).str.strip()
    df["Source"] = df["Source"].astype(str).str.strip()

    available_years = sorted(df["Year"].unique())
    if not available_years:
        raise DataModelError(f"{path.name} → TotalReported sheet has no year rows.")

    requested = str(year).strip() if year is not None else (os.environ.get("PB_REPORT_YEAR") or "").strip()
    if requested and requested in available_years:
        report_year = requested
    elif requested:
        prior = [value for value in available_years if value <= requested]
        report_year = prior[-1] if prior else available_years[-1]
    else:
        report_year = available_years[-1]

    subset = df[df["Year"] == report_year]

    def _count(source: str) -> int | None:
        rows = subset[subset["Source"] == source]
        if rows.empty:
            return None
        value = rows["TotalReported"].iloc[0]
        return int(value) if pd.notna(value) else None

    return {
        "year": report_year,
        "upr_ns": _count("UPR"),
        "fdrs_ns": _count("FDRS"),
    }
