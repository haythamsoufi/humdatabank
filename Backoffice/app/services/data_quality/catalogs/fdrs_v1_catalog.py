"""
FDRS v1 QoD indicator catalog (from IFRC Quality of Data methodology PDF).

KPI codes match indicator_bank.fdrs_kpi_code values on template 21 (published).
Run `python scripts/dump_data_quality_catalog.py` to verify mappings after template changes.
"""

from app.utils.data_quality_constants import FDRS_TEMPLATE_ID

FDRS_TEMPLATE_ID = FDRS_TEMPLATE_ID  # re-export

# 7 Governance & Structure indicators (note 2)
GOVERNANCE_KPI_CODES = (
    "KPI_noBranches",
    "KPI_noLocalUnits",
    "KPI_PeopleVol",
    "KPI_PStaff",
    "KPI_noVolCoveredAI",
    "KPI_PStaffCoveredAI",
    "KPI_GB",
)

# 17 People Reached indicators (note 6)
REACH_KPI_CODES = (
    "KPI_DonBlood",
    "KPI_TrainFA",
    "KPI_ReachDRER",
    "KPI_ReachLTSPD",
    "KPI_ReachDRR",
    "KPI_ReachS",
    "KPI_ReachL",
    "KPI_ReachH",
    "KPI_ReachHPM",
    "KPI_ReachHI",
    "KPI_ReachWASH",
    "KPI_ReachM",
    "KPI_Climate",
    "KPI_ClimateHeat",
    "KPI_ReachCTP",
    "KPI_ReachSI",
    "KPI_ReachRCRCEd",
)

# 3 governance indicators included in disaggregation denominator (20 total)
DISAGG_GOVERNANCE_KPI_CODES = (
    "KPI_PeopleVol",
    "KPI_PStaff",
    "KPI_GB",
)

DISAGG_INDICATOR_KPI_CODES = REACH_KPI_CODES + DISAGG_GOVERNANCE_KPI_CODES

FINANCE_TOTAL_INCOME = "KPI_IncomeLC_CHF"
FINANCE_TOTAL_EXPENDITURE = "KPI_expenditureLC_CHF"

# 14 income source KPI codes (note 5) — dynamic finance fields when present
INCOME_SOURCE_KPI_CODES = (
    "h_gov_CHF",
    "f_gov_CHF",
    "ind_CHF",
    "corp_CHF",
    "found_CHF",
    "un_CHF",
    "pooled_f_CHF",
    "ngo_CHF",
    "si_CHF",
    "iga_CHF",
    "other_CHF",
    "KPI_incomeFromNSsLC_CHF",
    "ifrc_CHF",
    "icrc_CHF",
)

COMPLIANCE_DOC_TYPES = ("Annual Report", "Audited Financial Statement")

# FDRS section groups for timeliness (matched by section name substring)
TIMELINESS_SECTION_GROUPS = (
    ("governance", ("governance", "structure")),
    ("finance", ("finance", "partnership")),
    ("reach", ("reach",)),
)

TIMELINESS_CUTOFF_MONTH = 11
TIMELINESS_CUTOFF_DAY = 30

# Pillar weights (PDF)
WEIGHT_DOCUMENTS = 0.2
WEIGHT_REPORTING = 0.3
WEIGHT_DISAGGREGATION = 0.3
WEIGHT_TIMELINESS = 0.1
WEIGHT_VALIDATION = 0.1
