"""
AI fast-path helpers.

Implementations for specialized one-shot agent routes live next to their domains
(e.g. ``plugins.upr.ai.focus_area_analysis``). This package re-exports selected
entry points for stable imports and backward compatibility.
"""

from plugins.upr.ai.focus_area_analysis import run_unified_plans_focus_fastpath

__all__ = ["run_unified_plans_focus_fastpath"]
