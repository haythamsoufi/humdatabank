"""SPEF icon and National Society logo resolution for UPR visuals."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PLUGIN_DIR = Path(__file__).resolve().parent
_PLUGIN_REACH_ICONS = {
    "EO": "icons/eo-emergency.png",
    "CC1": "icons/cc1-cross-cutting.png",
    "SP1": "icons/sp1-climate.png",
    "SP2": "icons/sp2-disasters.png",
    "SP3": "icons/sp3-health.png",
    "SP4": "icons/sp4-migration.png",
    "SP5": "icons/sp5-inclusion.png",
}

def _spef_icon_alias(code: str) -> str:
    upper = (code or "").strip().upper()
    if upper == "CC1":
        return "CC"
    if upper == "EFS":
        return "EF1"
    return upper


def _set_spef_icon_mode(*, inline: bool) -> None:
    try:
        from flask import g, has_app_context

        if has_app_context():
            g._upr_inline_spef_icons = bool(inline)
            for attr in ("_upr_spef_icon_srcs", "_upr_spef_icon_srcs_inline"):
                if hasattr(g, attr):
                    delattr(g, attr)
    except Exception:
        logger.debug("UPR visuals: could not set SPEF icon mode", exc_info=True)


def _inline_spef_icons() -> bool:
    try:
        from flask import g, has_app_context

        if has_app_context():
            return bool(getattr(g, "_upr_inline_spef_icons", False))
    except Exception:
        logger.debug("UPR visuals: could not read SPEF icon mode", exc_info=True)
    return False


def _load_spef_catalog_rows():
    """Active SPEF catalog rows — same source as the indicator-bank wizard."""
    from app.models.indicator_bank import IndicatorBankSpef

    return (
        IndicatorBankSpef.query.filter(IndicatorBankSpef.is_active.is_(True))
        .order_by(IndicatorBankSpef.sort_order, IndicatorBankSpef.code)
        .all()
    )


def _spef_catalog_icon_url(row) -> str:
    """Browser URL used by the indicator bank and assignment Visuals."""
    from app.utils.sector_logo_urls import spef_icon_url

    try:
        return spef_icon_url(row, via_api=True) or spef_icon_url(row) or ""
    except Exception:
        logger.debug("UPR visuals: SPEF catalog icon URL via API failed", exc_info=True)
        try:
            return spef_icon_url(row) or ""
        except Exception:
            logger.debug("UPR visuals: SPEF catalog icon URL fallback failed", exc_info=True)
            return ""


def _inline_local_icon(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        import base64
        import mimetypes

        data = path.read_bytes()
        if not data:
            return ""
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    except Exception:
        logger.debug("UPR visuals: could not inline local icon %s", path, exc_info=True)
        return ""


def _plugin_reach_icon_src(code: str, *, inline: bool) -> str:
    rel = _PLUGIN_REACH_ICONS.get((code or "").strip().upper())
    if not rel:
        return ""
    path = _PLUGIN_DIR / "static" / rel
    if inline:
        return _inline_local_icon(path)
    if not path.is_file():
        return ""
    try:
        from flask import url_for

        return url_for("upr_visuals.static_file", filename=rel)
    except Exception:
        logger.debug("UPR visuals: could not build reach icon URL for %s", rel, exc_info=True)
        return f"/upr-visuals/static/{rel}"


def _inline_spef_icon(row) -> str:
    filename = (getattr(row, "icon_filename", None) or "").strip()
    if not filename:
        return ""
    try:
        import base64
        import mimetypes

        from app.services.platform import storage_service as storage

        data = storage.download(storage.SYSTEM, f"spef/{filename}")
        if not data:
            return ""
        mime = mimetypes.guess_type(filename)[0] or "image/png"
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    except Exception:
        logger.debug("UPR visuals: could not inline SPEF icon %s", filename, exc_info=True)
        return ""


def _inline_ns_logo(filename: str) -> str:
    name = (filename or "").strip()
    if not name:
        return ""
    try:
        import base64
        import mimetypes

        from app.services.platform import storage_service as storage

        data = storage.download(storage.SYSTEM, f"ns/{name}")
        if not data:
            return ""
        mime = mimetypes.guess_type(name)[0] or "image/png"
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    except Exception:
        logger.debug("UPR visuals: could not inline NS logo %s", name, exc_info=True)
        return ""


def _ns_logo_src(ns, iso3: str, *, inline: bool = False) -> str:
    """Stored NS logo, else the public FDRS GitHub file for this ISO3."""
    filename = (getattr(ns, "logo_filename", None) or "").strip() if ns else ""
    if inline and filename:
        data_uri = _inline_ns_logo(filename)
        if data_uri:
            return data_uri
    if ns:
        try:
            from app.utils.sector_logo_urls import ns_logo_url

            url = ns_logo_url(ns, via_api=True) or ns_logo_url(ns)
            if url:
                return url
        except Exception:
            logger.debug("UPR visuals: NS logo URL via API failed", exc_info=True)
            try:
                from app.utils.sector_logo_urls import ns_logo_url

                url = ns_logo_url(ns) or ""
                if url:
                    return url
            except Exception:
                logger.debug("UPR visuals: NS logo URL fallback failed", exc_info=True)
    try:
        from app.utils.sector_logo_urls import github_ns_logo_url

        return github_ns_logo_url(iso3) or ""
    except Exception:
        logger.debug("UPR visuals: GitHub NS logo URL failed for %s", iso3, exc_info=True)
        return ""


def _remember_spef_icon(out: dict[str, str], code: str, src: str) -> None:
    out[code] = src
    alias = _spef_icon_alias(code)
    if alias != code:
        out.setdefault(alias, src)
    if code == "CC":
        out.setdefault("CC1", src)


def spef_icon_srcs(*, inline: bool | None = None) -> dict[str, str]:
    """Map SPEF catalog codes to icon src from the indicator bank.

    Browser preview and assignment Visuals use ``spef_icon_url`` (same helper as
    the indicator-bank SPEF catalog). PNG/PDF export can request data URIs.
    """
    use_inline = _inline_spef_icons() if inline is None else bool(inline)
    cache_attr = "_upr_spef_icon_srcs_inline" if use_inline else "_upr_spef_icon_srcs"
    try:
        from flask import g, has_app_context

        cached = getattr(g, cache_attr, None) if has_app_context() else None
        if isinstance(cached, dict):
            return cached
    except Exception:
        logger.debug("UPR visuals: could not read SPEF icon cache", exc_info=True)

    out: dict[str, str] = {}
    try:
        rows = _load_spef_catalog_rows()
    except Exception:
        logger.debug("UPR visuals: could not load SPEF catalog icons", exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            pass
        rows = []

    for row in rows:
        code = (getattr(row, "code", None) or "").strip().upper()
        if not code:
            continue
        src = ""
        if use_inline:
            # WeasyPrint cannot load Flask /indicator-bank URLs; only embed files.
            src = _inline_spef_icon(row)
        else:
            src = _spef_catalog_icon_url(row)
        if src:
            _remember_spef_icon(out, code, src)

    for code in _PLUGIN_REACH_ICONS:
        src = _plugin_reach_icon_src(code, inline=use_inline)
        if not src:
            continue
        if code == "EO" or not out.get(code):
            _remember_spef_icon(out, code, src)

    try:
        from flask import g, has_app_context

        if has_app_context():
            setattr(g, cache_attr, out)
    except Exception:
        logger.debug("UPR visuals: could not store SPEF icon cache", exc_info=True)
    return out


