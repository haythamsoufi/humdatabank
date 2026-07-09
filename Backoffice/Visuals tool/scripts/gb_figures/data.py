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
  section filter uses Final.Strategic Priority / Enabling Function
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import resolve_excel

# Expected Final sheet columns (Tableau: [Final$], header row 1)
FINAL_COLUMNS = (
    "Index",
    "GB Indicator",
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


def _validate_join(final: pd.DataFrame, mapping: pd.DataFrame, model: pd.DataFrame, excel_name: str) -> None:
    final_ids = set(final["ID"].dropna().astype(str).str.strip())
    mapping_ids = set(mapping["ID"].dropna().astype(str).str.strip())
    unmatched = sorted(final_ids - mapping_ids)
    if unmatched:
        sample = ", ".join(unmatched[:5])
        suffix = "…" if len(unmatched) > 5 else ""
        raise DataModelError(
            f"{excel_name} → {len(unmatched)} Final ID(s) have no match in Mapping "
            f"(e.g. {sample}{suffix})."
        )

    if model.empty:
        raise DataModelError(
            f"{excel_name} → Final and Mapping could not be joined. "
            "Check that both sheets use the same ID values."
        )

    unmapped = model[mapping.columns.intersection(model.columns).tolist()].isna().all(axis=1).sum()
    if unmapped == len(model):
        raise DataModelError(
            f"{excel_name} → Join produced rows but no Mapping metadata was attached. "
            "Verify Mapping.ID matches Final.ID."
        )


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
    mapping = sheets["mapping"].copy()
    final = sheets["final"].copy()
    total_reported = sheets["total_reported"].copy()

    if validate:
        _validate_final(final, path.name)
        _validate_mapping(mapping, path.name)

    mapping["ID"] = mapping["ID"].astype(str).str.strip()
    final["ID"] = final["ID"].astype(str).str.strip()
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

    # Tableau uses Strategic Priority from Final for worksheet filters.
    section_col = f"{SECTION_COLUMN}_final"
    if section_col not in model.columns:
        section_col = SECTION_COLUMN
    model["section"] = model[section_col]

    if validate:
        _validate_join(final, mapping, model, path.name)

    return model


def latest_merged_total_reported(model: pd.DataFrame) -> str | None:
    tr = model.loc[model["Source"] == "Merged", ["Year", "TotalReported"]].drop_duplicates()
    if tr.empty:
        return None
    latest_year = tr["Year"].max()
    value = tr.loc[tr["Year"] == latest_year, "TotalReported"].iloc[0]
    return str(int(value)) if pd.notna(value) else None
