"""Load SG Report.xlsx and reproduce Tableau's federated data model.

Data sources (read-only — scripts never write to these sheets):

  Final            Fact table: one row per indicator × year × source.
                   Restore via Excel Power Query; do not paste static data here.
  Mapping          Indicator metadata and translations (header row 4).
  TotalReported    Denominator for "out of N NSs" labels.
  Translations     UI labels and section titles.
  SectionOrder     Report section display order.

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
    for optional in ("Translations", "SectionOrder"):
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


_MEASUREMENT_COLUMN_ALIASES = (
    "typeOfMeasurement",
    "Type of measurement",
    "TypeOfMeasurement",
)
_BANK_SHEET_NAMES = ("Indicator bank", "Indicator Bank")
_BANK_ID_COLUMNS = ("ID", "id", "indicator_bank_id")


def _normalize_unit(value: object) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() in {"percentage", "percent", "%"}:
        return "Percentage"
    return text


def _measurement_lookup(df: pd.DataFrame) -> pd.Series | None:
    measure_col = next((col for col in _MEASUREMENT_COLUMN_ALIASES if col in df.columns), None)
    id_col = next((col for col in _BANK_ID_COLUMNS if col in df.columns), None)
    if not measure_col or not id_col:
        return None
    bank = df.copy()
    bank[id_col] = bank[id_col].astype(str).str.strip()
    bank = bank[bank[id_col].ne("") & bank[measure_col].notna()]
    if bank.empty:
        return None
    return (
        bank.drop_duplicates(subset=[id_col], keep="first")
        .set_index(id_col)[measure_col]
        .map(_normalize_unit)
    )


def _apply_unit_lookup(mapping: pd.DataFrame, lookup: pd.Series) -> pd.DataFrame:
    if lookup is None or lookup.empty:
        return mapping
    if "Unit" not in mapping.columns:
        mapping["Unit"] = mapping["ID"].map(lookup)
        return mapping
    empty = mapping["Unit"].isna() | mapping["Unit"].astype(str).str.strip().eq("")
    mapping.loc[empty, "Unit"] = mapping.loc[empty, "ID"].map(lookup)
    return mapping


def _enrich_mapping_units(mapping: pd.DataFrame, excel_path: Path) -> pd.DataFrame:
    """Populate Mapping.Unit from typeOfMeasurement columns and Indicator bank sheet."""
    mapping = mapping.copy()
    mapping = _apply_unit_lookup(mapping, _measurement_lookup(mapping))

    for sheet_name in _BANK_SHEET_NAMES:
        try:
            bank = pd.read_excel(excel_path, sheet_name=sheet_name)
        except (ValueError, FileNotFoundError):
            continue
        mapping = _apply_unit_lookup(mapping, _measurement_lookup(bank))

    if "Unit" in mapping.columns:
        mapping["Unit"] = mapping["Unit"].map(_normalize_unit)
    return mapping


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
    """Normalized Mapping sheet with units enriched from typeOfMeasurement / Indicator bank."""
    path = resolve_excel(excel_path)
    mapping = load_sg_report(path)["mapping"].copy()
    mapping["ID"] = mapping["ID"].astype(str).str.strip()
    mapping = _enrich_mapping_units(mapping, path)
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
