"""Filesystem layout for UPR secondary snapshots."""

from __future__ import annotations

from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
SECONDARY_DIR = Path(__file__).resolve().parent
DATA_DIR = SECONDARY_DIR / "data"
MULTILATERAL_DIR = DATA_DIR / "multilateral"
EAS_SPRM_OPS_DIR = DATA_DIR / "eas_sprm_ops"
LEGACY_INFORM_RISK = PLUGIN_DIR / "geo" / "inform_risk.json"

# Global (not round-scoped) snapshot files.
GLOBAL_FILES = {
    "population": DATA_DIR / "population.json",
    "poverty": DATA_DIR / "poverty.json",
    "income_groups": DATA_DIR / "income_groups.json",
    "inform_risk": DATA_DIR / "inform_risk.json",
    "inform_severity": DATA_DIR / "inform_severity.json",
    "inform_climate": DATA_DIR / "inform_climate.json",
    "hdi": DATA_DIR / "hdi.json",
}

SOURCE_LABELS = {
    "population": "Total Population",
    "poverty": "Poverty",
    "income_groups": "Income Group",
    "inform_risk": "INFORM Risk",
    "inform_severity": "INFORM Severity",
    "inform_climate": "INFORM Climate Change",
    "hdi": "HDI",
    "multilateral": "Multilateral support",
    "eas_sprm_ops": "EAs SPRM/OPS",
}


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MULTILATERAL_DIR.mkdir(parents=True, exist_ok=True)
    EAS_SPRM_OPS_DIR.mkdir(parents=True, exist_ok=True)


def round_file(kind: str, round_code: str) -> Path:
    code = (round_code or "").strip().upper()
    if kind == "multilateral":
        return MULTILATERAL_DIR / f"{code}.json"
    if kind == "eas_sprm_ops":
        return EAS_SPRM_OPS_DIR / f"{code}.json"
    raise ValueError(f"unknown round-scoped kind: {kind}")
