"""OpenAI tool-spec dicts and planner metadata for UPR (Unified Plan Report) tools.

Centralises the four UPR tool specifications so they can be imported by
the tool registry, query planner, and fastpath modules without circular
dependencies.
"""

# ---------------------------------------------------------------------------
# Tool name sets
# ---------------------------------------------------------------------------

UPR_TOOL_NAMES = {
    "get_upr_kpi_value",
    "get_upr_kpi_timeseries",
    "get_upr_kpi_values_for_all_countries",
    "analyze_unified_plans_focus_areas",
}

UPR_KPI_TOOL_NAMES = {
    "get_upr_kpi_value",
    "get_upr_kpi_timeseries",
    "get_upr_kpi_values_for_all_countries",
}

UPR_BULK_TOOL_NAMES = {"get_upr_kpi_values_for_all_countries"}

UPR_CACHEABLE_TOOLS = {
    "get_upr_kpi_value",
    "get_upr_kpi_timeseries",
    "get_upr_kpi_values_for_all_countries",
    "analyze_unified_plans_focus_areas",
}

# ---------------------------------------------------------------------------
# OpenAI function-calling tool specs  (copied verbatim from registry.py)
# ---------------------------------------------------------------------------

UPR_TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "get_upr_kpi_value",
            "description": "Get UPR KPI values from document-extracted metadata (branches, local_units, volunteers, staff). Use for single-country 'how many' questions when the user allows documents. Do NOT use if the user asked for 'databank only', 'database only', 'indicator bank only', or 'not documents' — use get_indicator_value instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "country_identifier": {
                        "type": "string",
                        "description": "Country name (e.g., 'Syria'), ISO3 code (e.g., 'SYR'), or country ID"
                    },
                    "metric": {
                        "type": "string",
                        "description": "One of: 'branches', 'local_units', 'volunteers', 'staff' (best-effort normalization applied)"
                    }
                },
                "required": ["country_identifier", "metric"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_upr_kpi_timeseries",
            "description": "Get a UPR KPI time series (best value per document-year) for ONE country from document metadata. Use when the user asks for 'over time', 'trend', 'by year', 'time series' for branches/volunteers/staff/local_units AND the user allows documents. Returns points with year + value, suitable for rendering a line chart. When only document sources are enabled (no databank), prefer this over get_indicator_timeseries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "country_identifier": {
                        "type": "string",
                        "description": "Country name (e.g., 'Syria'), ISO3 code (e.g., 'SYR'), or country ID"
                    },
                    "metric": {
                        "type": "string",
                        "description": "One of: 'branches', 'local_units', 'volunteers', 'staff'"
                    }
                },
                "required": ["country_identifier", "metric"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_upr_kpi_values_for_all_countries",
            "description": "Get UPR KPI values (branches, local_units, volunteers, staff) for ALL countries from document-extracted metadata (Unified Plans). Use ONLY when: (1) the user explicitly asked for 'from UPR', 'from Unified Plans', or 'from documents' for this metric — then use this tool only and add a clear note that values are from UPR documents; OR (2) to FILL GAPS after get_indicator_values_for_all_countries — add only countries that have no FDRS value. For volunteers/staff/branches/local units, FDRS (get_indicator_values_for_all_countries) is the primary source; call it first. Do NOT use if the user asked for 'databank only'. Returns rows (country_id, country_name, iso3, region, value, source). Each row's 'region' is the platform operational region. When the user asks for 'continent', use this field as operational region — do not add a separate continent column or use model knowledge.",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric": {
                        "type": "string",
                        "description": "One of: 'branches', 'local_units', 'volunteers', 'staff'"
                    }
                },
                "required": ["metric"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_unified_plans_focus_areas",
            "description": (
                "Analyze Unified Plan documents in one pass and classify which plans mention a focus area or theme. "
                "Works for any thematic area: built-in areas (cash, cea, livelihoods, social_protection) and "
                "any other federation-relevant theme such as migration, displacement, migration_displacement, climate, "
                "mhpss, pgi, health, disaster_risk_reduction, or any free-text label (use underscores). "
                "Returns per-plan flags, country-grouped counts, and plans where none of the target areas are found. "
                "USE THIS TOOL — not get_indicator_value — whenever the user asks which Unified Plans include, "
                "mention, prioritise, or address a topic (e.g. 'migration and displacement included in 2026 Unified Plans'). "
                "Pass the relevant theme(s) in the 'areas' parameter using snake_case keys."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "areas": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Focus area keys to evaluate (use snake_case). "
                            "Built-in: 'cash', 'cea', 'livelihoods', 'social_protection'. "
                            "Extended: 'migration', 'displacement', 'migration_displacement', "
                            "'climate', 'mhpss', 'pgi', 'health', 'disaster_risk_reduction'. "
                            "Any other free-text label (e.g. 'nutrition', 'water_sanitation') is also accepted "
                            "and will be matched using auto-generated keyword patterns. "
                            "If omitted, defaults to the four built-in areas."
                        )
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of Unified Plan documents to analyze (1-1000).",
                        "default": 500
                    }
                },
                "required": []
            }
        }
    },
]

# ---------------------------------------------------------------------------
# Query-planner metadata  (UPR subset of ai_query_planner tables)
# ---------------------------------------------------------------------------

UPR_PLANNER_ENTRIES = {
    "required_by_tool": {
        "get_upr_kpi_value": {"country_identifier", "metric"},
        "get_upr_kpi_timeseries": {"country_identifier", "metric"},
        "get_upr_kpi_values_for_all_countries": {"metric"},
        "analyze_unified_plans_focus_areas": set(),
    },
    "kind_map": {
        "get_upr_kpi_value": "single_value",
        "get_upr_kpi_timeseries": "timeseries",
        "analyze_unified_plans_focus_areas": "unified_plans_focus",
    },
    "allowed_tools": {
        "get_upr_kpi_value",
        "get_upr_kpi_timeseries",
        "get_upr_kpi_values_for_all_countries",
        "analyze_unified_plans_focus_areas",
    },
}
