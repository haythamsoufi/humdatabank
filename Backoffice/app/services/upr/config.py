"""
UPR-related AI feature flags and tuning parameters (``AI_UPR_*``).

Callers should use :func:`get_upr_config` instead of scattering
``current_app.config.get("AI_UPR_...")`` across services. Values are read from
Flask's application config with per-key try/except so a bad value for one key
does not break the rest. Outside an active application context, the static
defaults are returned without touching ``current_app``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from flask import current_app, has_app_context

logger = logging.getLogger(__name__)

_DEFAULTS: Dict[str, Any] = {
    "ai_upr_vision_kpi_enabled": False,
    "ai_upr_vision_max_pages": 8,
    "ai_upr_vision_dpi": 150,
    "ai_upr_vision_clip_top_frac": 0.0,
    "ai_upr_visual_chunking_enabled": True,
    "ai_upr_layout_kpi_enabled": True,
    "ai_upr_vision_model": "",
}


def get_upr_config() -> Dict[str, Any]:
    """Load all ``AI_UPR_*`` settings from ``current_app.config``.

    Returns a new dict whose keys are lowercase versions of the config names
    (e.g. ``ai_upr_vision_kpi_enabled`` for ``AI_UPR_VISION_KPI_ENABLED``).

    When not inside a Flask application context, returns a copy of the module
    defaults and does not access ``current_app``.
    """
    out = dict(_DEFAULTS)
    if not has_app_context():
        return out

    cfg = current_app.config

    try:
        out["ai_upr_vision_kpi_enabled"] = bool(
            cfg.get("AI_UPR_VISION_KPI_ENABLED", _DEFAULTS["ai_upr_vision_kpi_enabled"])
        )
    except Exception as e:
        logger.debug("AI_UPR_VISION_KPI_ENABLED parse failed: %s", e)

    try:
        out["ai_upr_vision_max_pages"] = int(
            cfg.get("AI_UPR_VISION_MAX_PAGES", _DEFAULTS["ai_upr_vision_max_pages"])
        )
    except Exception as e:
        logger.debug("AI_UPR_VISION_MAX_PAGES parse failed: %s", e)

    try:
        out["ai_upr_vision_dpi"] = int(
            cfg.get("AI_UPR_VISION_DPI", _DEFAULTS["ai_upr_vision_dpi"])
        )
    except Exception as e:
        logger.debug("AI_UPR_VISION_DPI parse failed: %s", e)

    try:
        out["ai_upr_vision_clip_top_frac"] = float(
            cfg.get("AI_UPR_VISION_CLIP_TOP_FRAC", _DEFAULTS["ai_upr_vision_clip_top_frac"])
        )
    except Exception as e:
        logger.debug("AI_UPR_VISION_CLIP_TOP_FRAC parse failed: %s", e)

    try:
        out["ai_upr_visual_chunking_enabled"] = bool(
            cfg.get(
                "AI_UPR_VISUAL_CHUNKING_ENABLED",
                _DEFAULTS["ai_upr_visual_chunking_enabled"],
            )
        )
    except Exception as e:
        logger.debug("AI_UPR_VISUAL_CHUNKING_ENABLED parse failed: %s", e)

    try:
        out["ai_upr_layout_kpi_enabled"] = bool(
            cfg.get("AI_UPR_LAYOUT_KPI_ENABLED", _DEFAULTS["ai_upr_layout_kpi_enabled"])
        )
    except Exception as e:
        logger.debug("AI_UPR_LAYOUT_KPI_ENABLED parse failed: %s", e)

    try:
        raw_model = cfg.get("AI_UPR_VISION_MODEL", _DEFAULTS["ai_upr_vision_model"])
        out["ai_upr_vision_model"] = str(raw_model) if raw_model is not None else ""
    except Exception as e:
        logger.debug("AI_UPR_VISION_MODEL parse failed: %s", e)

    return out


__all__ = ["get_upr_config"]
