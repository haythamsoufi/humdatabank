"""P&B Progress service — Excel storage, Visuals tool subprocess build, output serving."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import timezone
from pathlib import Path
from typing import Any, ClassVar

from flask import Response, current_app, url_for
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import NotFound

from plugins.pb_progress.plugin_data_store import (
    PBProgressDataStore,
    SYSTEM_GENERATED_NAME,
)
from plugins.pb_progress.versions import (
    DEFAULT_VERSION,
    LEGACY_EXCEL_REL_PATH,
    LEGACY_OUTPUT_PREFIX,
    REPORT_VERSIONS,
    validate_version,
    version_storage_prefix,
)
from app.services.platform import storage_service
from app.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)

STORAGE_CATEGORY = "pb_progress"
EXCEL_NAME = "source/SG_Report.xlsx"
STATUS_NAME = "status.json"
BUILD_LOG_NAME = "build.log"
OUTPUT_DIR_NAME = "output/"
_PB_REPORT_FA_FIX = (
    '<link rel="stylesheet" href="/static/libs/fontawesome-6.5.0.min.css">'
    '<style id="pb-toolbar-fa-fix">'
    "#pb-report-toolbar .fa,#pb-report-toolbar .fas,#pb-report-toolbar .fa-solid"
    "{font-weight:900!important;font-family:'Font Awesome 6 Free'!important;}"
    "</style>"
)
_PB_REPORT_TOC_PIN_FIX = (
    '<style id="pb-report-toc-pin-fix-v4">'
    "#pb-scroll-headers{display:none!important;}"
    "#toc.pb-report-toc-pinned,#quarto-margin-sidebar #toc.pb-report-toc-pinned,"
    "#quarto-sidebar #toc.pb-report-toc-pinned{"
    "position:fixed!important;top:var(--pb-report-toolbar-height,0px)!important;"
    "right:1.25rem!important;left:auto!important;width:12.5rem!important;"
    "max-width:12.5rem!important;min-width:0!important;"
    "max-height:calc(100vh - var(--pb-report-toolbar-height,0px) - 1rem)!important;"
    "overflow-x:hidden!important;overflow-y:auto!important;z-index:998!important;"
    "margin:0!important;padding:0.5rem 0.65rem 0.75rem!important;"
    "box-sizing:border-box!important;background:#fff!important;border:1px solid #e8e8e8!important;"
    "border-radius:0.25rem!important;box-shadow:0 1px 3px rgba(0,0,0,.06)!important;"
    "display:block!important;visibility:visible!important;font-size:0.78rem!important;line-height:1.35!important;color:#444!important;}"
    "#toc.pb-report-toc-pinned #toc-title{margin:0 0 0.45rem!important;padding:0!important;"
    "font-size:0.65rem!important;font-weight:700!important;letter-spacing:0.05em!important;"
    "text-transform:uppercase!important;color:#777!important;border:0!important;}"
    "#toc.pb-report-toc-pinned .toc-list,#toc.pb-report-toc-pinned>ul{margin:0!important;padding:0!important;list-style:none!important;}"
    "#toc.pb-report-toc-pinned li{margin:0.12rem 0!important;}"
    "#toc.pb-report-toc-pinned ul ul{margin:0.1rem 0 0.2rem!important;padding-left:0.65rem!important;"
    "font-size:0.72rem!important;color:#666!important;}"
    "#toc.pb-report-toc-pinned .pb-toc-label,#toc.pb-report-toc-pinned .nav-link{display:block!important;"
    "padding:0.1rem 0!important;font-size:inherit!important;line-height:1.35!important;font-weight:500!important;}"
    "#pb-report-toc-host{display:contents!important;}"
    "#quarto-margin-sidebar #toc.pb-report-toc-pinned a,"
    "#quarto-sidebar #toc.pb-report-toc-pinned a,"
    "#toc.pb-report-toc-pinned a,"
    "#quarto-margin-sidebar #toc.pb-report-toc-pinned .nav-link,"
    "#quarto-sidebar #toc.pb-report-toc-pinned .nav-link,"
    "#toc.pb-report-toc-pinned .nav-link,"
    ".pb-toc-label{pointer-events:none!important;cursor:default!important;text-decoration:none!important;color:inherit!important;}"
    "</style>"
    '<script id="pb-report-toc-pin-script-v4">'
    "document.addEventListener('DOMContentLoaded',function(){"
    "function pin(){var toc=document.getElementById('toc');if(!toc)return;"
    "toc.classList.add('pb-report-toc-pinned');"
    "toc.style.removeProperty('--pb-toc-right');toc.style.removeProperty('--pb-toc-width');}"
    "window.addEventListener('pb-report-toolbar-resize',pin);"
    "setTimeout(pin,0);"
    "});</script>"
)
_PB_REPORT_TOC_HOST_FIX = (
    '<script id="pb-report-toc-host-fix">'
    "document.addEventListener('DOMContentLoaded',function(){"
    "function L(m,d){window.__pbReportTocDebug=window.__pbReportTocDebug||[];"
    "var e={msg:m,data:d||null,t:Date.now()};window.__pbReportTocDebug.push(e);"
    "console.log('[pb-report-toc]',m,d||'');}"
    "function W(m,d){L(m,d);console.warn('[pb-report-toc]',m,d||'');}"
    "function host(){return document.getElementById('quarto-margin-sidebar')"
    "||document.getElementById('quarto-sidebar')||document.getElementById('pb-report-toc-host');}"
    "function ensureHost(){var h=host();if(h)return h;"
    "h=document.createElement('div');h.id='pb-report-toc-host';document.body.appendChild(h);"
    "W('created fallback toc host (page-layout-full has no quarto sidebar)');return h;}"
    "function rebuild(){var panel=document.querySelector('.pb-lang-panel:not([hidden])')"
    "||document.querySelector('.pb-lang-panel');if(!panel){W('no active language panel');return;}"
    "var h=ensureHost(),toc=document.getElementById('toc');"
    "if(!toc){toc=document.createElement('nav');toc.id='toc';toc.setAttribute('role','doc-toc');"
    "toc.className='toc-active';toc.innerHTML='<h2 id=\"toc-title\">Table of contents</h2><ul class=\"toc-list\"></ul>';"
    "h.appendChild(toc);L('created #toc');}"
    "var list=toc.querySelector('.toc-list')||toc.querySelector('ul');if(!list){W('toc list missing');return;}"
    "list.innerHTML='';var parts=0,sections=0;"
    "panel.querySelectorAll('.report-part').forEach(function(part){"
    "var h2=part.querySelector('h2[data-anchor]');if(!h2)return;parts++;"
    "var li=document.createElement('li'),lbl=document.createElement('span');"
    "lbl.className='nav-link pb-toc-label';lbl.textContent=h2.textContent.trim();li.appendChild(lbl);"
    "var ul=document.createElement('ul');"
    "part.querySelectorAll('.report-section-title[data-anchor]').forEach(function(h3){sections++;"
    "var cli=document.createElement('li'),clbl=document.createElement('span');"
    "clbl.className='nav-link pb-toc-label';clbl.textContent=h3.textContent.trim();"
    "cli.appendChild(clbl);ul.appendChild(cli);});"
    "if(ul.children.length)li.appendChild(ul);list.appendChild(li);});"
    "L('rebuilt toc',{parts:parts,sections:sections,items:list.children.length});"
    "if(!parts)W('toc empty — no report parts in active panel');"
    "toc.classList.add('pb-report-toc-pinned');"
    "toc.style.removeProperty('--pb-toc-right');toc.style.removeProperty('--pb-toc-width');}"
    "setTimeout(function(){"
    "L('serve_output toc check',{hasToc:!!document.getElementById('toc'),"
    "hasMarginSidebar:!!document.getElementById('quarto-margin-sidebar'),"
    "hasQuartoSidebar:!!document.getElementById('quarto-sidebar'),"
    "layout:!!document.querySelector('.page-layout-full')});"
    "if(!document.getElementById('toc'))rebuild();"
    "else{var t=document.getElementById('toc');t.classList.add('pb-report-toc-pinned');"
    "t.style.removeProperty('--pb-toc-right');t.style.removeProperty('--pb-toc-width');"
    "L('toc already present — reapplied pin class');}"
    "},100);"
    "});</script>"
)
_PB_REPORT_TOOLBAR_WIDTH_FIX = (
    '<style id="pb-toolbar-full-width-fix">'
    "#pb-report-toolbar{width:100vw!important;max-width:100vw!important;"
    "margin-left:calc(50% - 50vw)!important;margin-right:calc(50% - 50vw)!important;"
    "padding-left:max(1rem,calc((100vw - 100%) / 2 + 1rem))!important;"
    "padding-right:max(1rem,calc((100vw - 100%) / 2 + 1rem))!important;"
    "border-radius:0!important;border-left:none!important;border-right:none!important;"
    "box-sizing:border-box!important;}"
    "</style>"
)
_PB_REPORT_TOOLBAR_TITLE_FIX = (
    '<style id="pb-toolbar-title-fix">'
    "#title-block-header .subtitle{display:none!important;}"
    "</style>"
    '<script id="pb-toolbar-title-script">'
    "document.addEventListener('DOMContentLoaded',function(){"
    "var sub=document.querySelector('#title-block-header .subtitle');"
    "var title=document.getElementById('pb-report-toolbar-title');"
    "if(!title)return;"
    "if(sub){var t=sub.textContent.replace(/^[\\s\"']+|[\\s\"']+$/g,'').trim();"
    "if(t)title.textContent=t;}"
    "});</script>"
)

HEARTBEAT_INTERVAL_SECONDS = 60

# Build defaults — baked in; no App Service variables required.
PB_BUILD_WORKERS_LOCAL = "1"
PB_BUILD_WORKERS_AZURE = "1"
PLAYWRIGHT_BROWSERS_PATH = "/home/site/playwright-browsers"
QUARTO_VERSION = "1.6.42"

_PLUGIN_DIR = Path(__file__).resolve().parent
_DEFAULT_VISUALS_TOOL_DIR = _PLUGIN_DIR / "visuals"


def _resolve_visuals_tool_dir() -> Path:
    try:
        override = current_app.config.get("PB_VISUALS_TOOL_DIR")
        if override:
            return Path(override).resolve()
    except RuntimeError:
        pass
    return _DEFAULT_VISUALS_TOOL_DIR


def _visuals_paths() -> tuple[Path, Path, Path]:
    tool_dir = _resolve_visuals_tool_dir()
    return tool_dir, tool_dir / "scripts" / "build_report.py", tool_dir / "report" / "output"

OUTPUT_LABELS = {
    "pb-report.html": "HTML Report",
    "pb-report-figures-all.zip": "Figures (all languages)",
    "pb-report-docx-all.zip": "Word (all languages)",
    "pb-report-pdf-all.zip": "PDF (all languages)",
    "gb-report.html": "HTML Report",
    "gb-report-figures-all.zip": "Figures (all languages)",
}
LANGUAGE_LABELS = {
    "english": "English",
    "french": "French",
    "spanish": "Spanish",
    "arabic": "Arabic",
}

BUILD_STAGE_ORDER: tuple[tuple[str, str], ...] = (
    ("preparing", "Preparing build"),
    ("figures", "Generating charts and dashboards"),
    ("partials", "Assembling report sections"),
    ("html", "Rendering HTML report"),
    ("figures_zip", "Packaging figure downloads"),
    ("word", "Generating Word documents"),
    ("pdf", "Generating PDF documents"),
    ("saving", "Saving outputs"),
)
BUILD_STAGE_LABELS = dict(BUILD_STAGE_ORDER)


class PBProgressService:
    """Orchestrates Excel upload, report generation, and output delivery."""

    _lock: ClassVar[threading.Lock] = threading.Lock()
    _states: ClassVar[dict[str, dict[str, Any]]] = {}
    _loaded_versions: ClassVar[set[str]] = set()
    _legacy_migrated: ClassVar[bool] = False
    _build_thread: ClassVar[threading.Thread | None] = None
    _build_version: ClassVar[str | None] = None

    @classmethod
    def _default_state(cls) -> dict[str, Any]:
        return {
            "status": "idle",
            "job_id": None,
            "started_at": None,
            "finished_at": None,
            "error": None,
            "build_stage": None,
            "output_names": [],
        }

    @classmethod
    def _version_label(cls, version: str) -> str:
        return REPORT_VERSIONS[validate_version(version)]["label"]

    @classmethod
    def _version_rel(cls, version: str, name: str) -> str:
        return f"{version_storage_prefix(version)}{name}"

    @classmethod
    def _excel_rel(cls, version: str) -> str:
        return cls._version_rel(version, EXCEL_NAME)

    @classmethod
    def _status_rel(cls, version: str) -> str:
        """Legacy path — only used when importing old status.json into plugin_data."""
        return cls._version_rel(version, STATUS_NAME)

    @classmethod
    def _excel_rel_for_source(cls, version: str) -> str:
        source = PBProgressDataStore.get_data_source(version)
        if source == "system":
            return cls._version_rel(version, SYSTEM_GENERATED_NAME)
        return cls._excel_rel(version)

    @classmethod
    def _output_rel(cls, version: str, filename: str) -> str:
        return cls._version_rel(version, f"{OUTPUT_DIR_NAME}{filename}")

    @classmethod
    def _state_for(cls, version: str) -> dict[str, Any]:
        version = validate_version(version)
        if version not in cls._states:
            cls._states[version] = cls._default_state()
        return cls._states[version]

    @classmethod
    def _migrate_legacy_storage(cls) -> None:
        PBProgressDataStore.migrate_legacy_storage_if_needed()
        if cls._legacy_migrated:
            return
        cls._legacy_migrated = True
        target = DEFAULT_VERSION
        try:
            if storage_service.exists(STORAGE_CATEGORY, cls._excel_rel(target)):
                return
            if storage_service.exists(STORAGE_CATEGORY, LEGACY_EXCEL_REL_PATH):
                excel_raw = storage_service.download(STORAGE_CATEGORY, LEGACY_EXCEL_REL_PATH)
                storage_service.upload(STORAGE_CATEGORY, cls._excel_rel(target), excel_raw)
            bucket = PBProgressDataStore.get_version_bucket(target)
            output_names = (bucket.get("status") or {}).get("output_names") or []
            for name in output_names:
                legacy_rel = f"{LEGACY_OUTPUT_PREFIX}{name}"
                if storage_service.exists(STORAGE_CATEGORY, legacy_rel):
                    blob = storage_service.download(STORAGE_CATEGORY, legacy_rel)
                    storage_service.upload(STORAGE_CATEGORY, cls._output_rel(target, name), blob)
            logger.info("Migrated legacy P&B progress binary storage to version %s", target)
        except Exception as exc:
            logger.warning("Legacy P&B progress binary migration skipped: %s", exc)

    @classmethod
    def _now_iso(cls) -> str:
        return utcnow().replace(tzinfo=timezone.utc).isoformat()

    @classmethod
    def _clear_orphaned_run(cls, version: str) -> None:
        """After a server restart, status.json may still say 'running' but no thread exists."""
        state = cls._state_for(version)
        if state.get("status") != "running":
            return
        if (
            cls._build_thread is not None
            and cls._build_thread.is_alive()
            and cls._build_version == version
        ):
            return
        state.update(
            {
                "status": "failed",
                "finished_at": cls._now_iso(),
                "error": "Generation was interrupted when the server restarted.",
                "build_stage": None,
            }
        )
        cls._persist_status(version)

    @classmethod
    def _reload_status_from_storage(cls, version: str) -> dict[str, Any] | None:
        try:
            status = PBProgressDataStore.get_version_status(version)
            return status if isinstance(status, dict) else None
        except Exception as exc:
            logger.warning("Failed to reload P&B progress status from plugin_data: %s", exc)
            return None

    @classmethod
    def _ensure_status_loaded(cls, version: str) -> None:
        cls._migrate_legacy_storage()
        version = validate_version(version)
        if version in cls._loaded_versions:
            cls._clear_orphaned_run(version)
            return
        cls._loaded_versions.add(version)
        persisted = cls._reload_status_from_storage(version)
        if persisted:
            cls._state_for(version).update(persisted)
        cls._clear_orphaned_run(version)

    @classmethod
    def _persist_status(cls, version: str, payload: dict[str, Any] | None = None) -> None:
        data = dict(payload or cls._state_for(version))
        data.pop("log_tail", None)
        PBProgressDataStore.save_version_status(version, data)

    @classmethod
    def _sanitize_build_line(cls, line: str) -> str:
        """Strip absolute paths from subprocess output before writing to server logs."""
        text = line.strip()
        if not text:
            return ""
        text = re.sub(r"[A-Za-z]:\\[^\s\"']+", "<path>", text)
        text = re.sub(r"/(?:home|app|Users|tmp|var)[^\s\"']*", "<path>", text)
        return text[:500]

    @classmethod
    def _log_build_step(
        cls,
        job_id: str,
        event: str,
        *,
        language: str | None = None,
        stage: str | None = None,
        detail: str | None = None,
        duration_s: float | None = None,
        level: int = logging.INFO,
    ) -> None:
        parts = [
            f"ts={cls._now_iso()}",
            f"job={job_id[:8]}",
            f"event={event}",
        ]
        if language:
            parts.append(f"lang={language}")
        if stage:
            parts.append(f"stage={stage}")
            label = BUILD_STAGE_LABELS.get(stage)
            if label:
                parts.append(f"stage_label={label}")
        if duration_s is not None:
            parts.append(f"duration_s={duration_s:.1f}")
        if detail:
            parts.append(f"detail={detail}")
        logger.log(level, "P&B progress build | %s", " | ".join(parts))

    @classmethod
    def _infer_build_stage(cls, line: str) -> str | None:
        """Map subprocess output to a coarse build stage — never expose raw logs to clients."""
        text = line.strip()
        lowered = text.lower()

        if "[generate_report_pdf]" in lowered:
            return "pdf" if "wrote" in lowered else "word"
        if "[generate_report_docx]" in lowered:
            return "word"
        if "[package_figures]" in lowered:
            return "figures_zip"
        if "output created:" in lowered and "pb-report.html" in lowered:
            return "html"
        if lowered == "pandoc" or lowered.startswith("pandoc "):
            return "html"
        if "[pre_render]" in lowered and "body:" in lowered:
            return "partials"
        if "[pre_render]" in lowered:
            return "figures"
        if text.startswith("[") and text.endswith("]") and "/" not in text:
            return "figures"
        if "[build_report]" in lowered:
            if "word" in lowered or "pdf" in lowered:
                return "word"
            if "pre-render" in lowered or "pre_render" in lowered:
                return "figures"
            if " render " in lowered and "pb-report.qmd" in lowered:
                return "figures"
        return None

    @classmethod
    def _advance_build_stage(cls, version: str, stage_id: str) -> bool:
        """Move to a new stage only when it is later in the pipeline (never go backward)."""
        state = cls._state_for(version)
        current_stage = state.get("build_stage")
        if cls._stage_index(stage_id) <= cls._stage_index(current_stage):
            return False
        cls._set_build_stage(version, stage_id)
        return True

    @classmethod
    def _stage_index(cls, stage_id: str | None) -> int:
        if not stage_id:
            return -1
        for index, (sid, _) in enumerate(BUILD_STAGE_ORDER):
            if sid == stage_id:
                return index
        return -1

    @classmethod
    def _build_stage_manifest(cls, current_stage: str | None) -> list[dict[str, str]]:
        current_index = cls._stage_index(current_stage)
        manifest: list[dict[str, str]] = []
        for index, (stage_id, label) in enumerate(BUILD_STAGE_ORDER):
            if current_index < 0:
                state = "pending"
            elif index < current_index:
                state = "done"
            elif index == current_index:
                state = "active"
            else:
                state = "pending"
            manifest.append({"id": stage_id, "label": label, "state": state})
        return manifest

    @classmethod
    def _set_build_stage(cls, version: str, stage_id: str) -> None:
        cls._state_for(version)["build_stage"] = stage_id

    @classmethod
    def _public_error_message(cls, exc: BaseException) -> str:
        """Return a client-safe error without filesystem paths or command details."""
        if isinstance(exc, subprocess.CalledProcessError):
            return "Report build failed. Contact an administrator if this persists."
        message = str(exc).strip()
        if not message:
            return "Report build failed."
        if any(marker in message for marker in (":\\", ":/", "/", "\\", "Running:", "python")):
            return "Report build failed. Contact an administrator if this persists."
        return message[:240]

    @classmethod
    def _attach_build_progress(cls, status: dict[str, Any]) -> dict[str, Any]:
        payload = dict(status)
        payload.pop("log_tail", None)
        stage_id = payload.get("build_stage")
        payload["build_stage_label"] = BUILD_STAGE_LABELS.get(stage_id, "")
        payload["build_stages"] = cls._build_stage_manifest(stage_id)
        return payload

    @classmethod
    def _resolve_quarto_exe(cls) -> str | None:
        """Resolve Quarto CLI — PATH, then known install locations (mirrors build_report.py)."""
        candidates: list[str | Path] = []
        env_exe = (os.environ.get("PB_QUARTO_EXE") or "").strip()
        if env_exe:
            candidates.append(env_exe)

        which = shutil.which("quarto")
        if which:
            candidates.append(which)

        if sys.platform == "win32":
            candidates.extend(
                [
                    Path(r"C:\Program Files\Quarto\bin\quarto.exe"),
                    Path(os.environ.get("LOCALAPPDATA", ""))
                    / "Programs"
                    / "Quarto"
                    / "bin"
                    / "quarto.cmd",
                ]
            )
        else:
            candidates.append(Path("/usr/bin/quarto"))

        for candidate in candidates:
            path = Path(candidate)
            if path.is_file():
                return str(path)
        return None

    @classmethod
    def _check_build_prerequisites(cls) -> None:
        issues: list[str] = []
        _tool_dir, build_script, _output_dir = _visuals_paths()
        if not build_script.is_file():
            issues.append(f"Build script not found: {build_script}")

        quarto_exe = cls._resolve_quarto_exe()
        if not quarto_exe:
            if sys.platform == "win32":
                issues.append(
                    "Quarto CLI not found. Install from https://quarto.org/docs/get-started/ "
                    "or ensure quarto.exe is on PATH."
                )
            else:
                issues.append(
                    f"Quarto CLI not found. On Azure Linux it is installed by entrypoint.sh "
                    f"(version {QUARTO_VERSION})."
                )
        else:
            logger.debug("P&B progress using Quarto at %s", quarto_exe)

        # Use find_spec instead of a live import so that playwright's .pyc
        # files are not written inside the Flask process.  A live
        # `import playwright.sync_api` caused the Werkzeug stat reloader to
        # detect the freshly-written __pycache__ entries (user site-packages is
        # not covered by Werkzeug's _stat_ignore_scan on Windows) and restart
        # Flask mid-build, emitting spurious [SCHED_SHUTDOWN] messages.
        try:
            import importlib.util
            if importlib.util.find_spec("playwright") is None:
                raise ImportError("playwright not found")
        except (ImportError, ValueError):
            issues.append(
                "Playwright is not installed. Run: pip install playwright "
                "&& playwright install chromium"
            )

        if issues:
            message = " | ".join(issues)
            logger.warning("P&B progress build prerequisites not met: %s", message)
            raise RuntimeError(message)

    @classmethod
    def _format_size(cls, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes / (1024 * 1024):.1f} MB"

    @classmethod
    def _label_for_output(cls, filename: str) -> str:
        if filename in OUTPUT_LABELS:
            return OUTPUT_LABELS[filename]
        stem = Path(filename).stem
        for prefix in ("pb-report-figures-", "gb-report-figures-"):
            if stem.startswith(prefix):
                slug = stem.replace(prefix, "")
                return f"Figures ({LANGUAGE_LABELS.get(slug, slug.title())})"
        for prefix in ("pb-report-", "gb-report-"):
            if stem.startswith(prefix):
                slug = stem.replace(prefix, "")
                ext = Path(filename).suffix.lower()
                lang = LANGUAGE_LABELS.get(slug, slug.title())
                if ext == ".pdf":
                    return f"PDF ({lang})"
                if ext == ".docx":
                    return f"Word ({lang})"
        return filename

    # Bare default copies (pb-report.docx, pb-report.pdf) are exact duplicates of the English
    # per-language files — suppress them from the manifest to avoid confusing duplicate entries.
    _SUPPRESS_DEFAULTS: frozenset[str] = frozenset({
        "pb-report.docx", "pb-report.pdf",
        "gb-report.docx", "gb-report.pdf",
    })

    @classmethod
    def _is_publishable_output(cls, filename: str) -> bool:
        if not filename or filename.startswith("_"):
            return False
        return filename not in cls._SUPPRESS_DEFAULTS

    @classmethod
    def _output_url(cls, version: str, filename: str) -> str:
        try:
            return url_for("pb_progress.serve_output", version=version, filename=filename)
        except RuntimeError:
            return f"/admin/data-exploration/pb-progress/{version}/output/{filename}"

    @classmethod
    def _resolve_output_names(
        cls,
        version: str,
        output_names: list[str] | None = None,
    ) -> list[str]:
        state = cls._state_for(version)
        names = list(output_names or state.get("output_names") or [])
        if names:
            return names
        _tool_dir, _build_script, report_output_dir = _visuals_paths()
        if not report_output_dir.is_dir():
            return []
        return sorted(
            p.name
            for p in report_output_dir.iterdir()
            if p.is_file() and cls._is_publishable_output(p.name)
        )

    _OUTPUT_SORT_KEY: dict[str, tuple[int, int]] = {
        "pb-report.html": (0, 0),
        "gb-report.html": (0, 0),
    }
    _LANG_ORDER = {"english": 0, "french": 1, "spanish": 2, "arabic": 3}
    _EXT_ORDER = {".docx": 0, ".pdf": 1, ".zip": 2}

    @classmethod
    def _output_sort_key(cls, name: str) -> tuple[int, int, int]:
        if name in cls._OUTPUT_SORT_KEY:
            return cls._OUTPUT_SORT_KEY[name]
        stem = Path(name).stem
        ext = Path(name).suffix.lower()
        for prefix in ("pb-report-figures-", "gb-report-figures-"):
            if stem.startswith(prefix):
                slug = stem.replace(prefix, "")
                lang_order = cls._LANG_ORDER.get(slug, 99)
                return (3, lang_order, 0)
        for prefix in ("pb-report-", "gb-report-"):
            if stem.startswith(prefix):
                slug = stem.replace(prefix, "")
                lang_order = cls._LANG_ORDER.get(slug, 99)
                ext_order = cls._EXT_ORDER.get(ext, 9)
                return (1, lang_order, ext_order)
        return (9, 0, 0)

    @classmethod
    def _build_output_manifest(
        cls,
        version: str,
        output_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        outputs: list[dict[str, Any]] = []
        names = sorted(cls._resolve_output_names(version, output_names), key=cls._output_sort_key)
        for name in names:
            if not cls._is_publishable_output(name):
                continue
            rel_name = cls._output_rel(version, name)
            if not storage_service.exists(STORAGE_CATEGORY, rel_name):
                continue
            size = storage_service.get_size(STORAGE_CATEGORY, rel_name)
            outputs.append(
                {
                    "name": name,
                    "label": cls._label_for_output(name),
                    "url": cls._output_url(version, name),
                    "size_bytes": size,
                    "size_label": cls._format_size(size) if size >= 0 else "",
                }
            )
        return outputs

    @classmethod
    def get_excel_info(cls, version: str) -> dict[str, Any] | None:
        version = validate_version(version)
        cls._ensure_status_loaded(version)
        state = cls._state_for(version)
        excel_meta = state.get("excel")
        if excel_meta:
            return excel_meta
        if not storage_service.exists(STORAGE_CATEGORY, cls._excel_rel(version)):
            return None
        size = storage_service.get_size(STORAGE_CATEGORY, cls._excel_rel(version))
        return {
            "filename": "SG Report.xlsx",
            "size_bytes": size,
            "size_label": cls._format_size(size) if size >= 0 else "",
            "uploaded_at": None,
        }

    @classmethod
    def store_excel(cls, version: str, file_storage: FileStorage) -> dict[str, Any]:
        version = validate_version(version)
        filename = (file_storage.filename or "").strip()
        if not filename.lower().endswith(".xlsx"):
            raise ValueError("Only .xlsx Excel files are supported.")

        max_bytes = int(current_app.config.get("MAX_UPLOAD_SIZE_BYTES") or (25 * 1024 * 1024))
        file_storage.stream.seek(0, os.SEEK_END)
        size_bytes = file_storage.stream.tell()
        file_storage.stream.seek(0)
        if size_bytes <= 0:
            raise ValueError("Uploaded file is empty.")
        if size_bytes > max_bytes:
            raise ValueError("Uploaded file exceeds the maximum allowed size.")

        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                file_storage.stream.seek(0)
                tmp.write(file_storage.read())
                temp_path = tmp.name

            from plugins.pb_progress.db_source import WorkbookValidationError, validate_uploaded_workbook

            validation = validate_uploaded_workbook(temp_path)
        except WorkbookValidationError as exc:
            raise ValueError(str(exc)) from exc
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

        file_storage.stream.seek(0)
        storage_service.upload(STORAGE_CATEGORY, cls._excel_rel(version), file_storage)

        uploaded_at = cls._now_iso()
        excel_info = {
            "filename": filename,
            "size_bytes": size_bytes,
            "size_label": cls._format_size(size_bytes),
            "uploaded_at": uploaded_at,
        }

        cls._ensure_status_loaded(version)
        state = cls._state_for(version)
        state["excel"] = excel_info
        if state.get("status") != "running":
            state["status"] = "idle"
            state["error"] = None
        cls._persist_status(version)
        result = cls._import_system_config_after_excel_upload(version, excel_info)
        result["validation"] = validation
        return result

    @classmethod
    def _import_system_config_after_excel_upload(
        cls,
        version: str,
        excel_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Load mapping, translations, and section order from the uploaded workbook."""
        result: dict[str, Any] = {"excel": excel_info}
        try:
            from plugins.pb_progress.db_source import DbSourceError, import_config_from_excel

            summary = import_config_from_excel(version)
            result["config_import"] = summary
            result["mapping"] = PBProgressDataStore.get_mapping_config(version)
            result["translations"] = PBProgressDataStore.get_translations_config(version)
            result["section_order"] = PBProgressDataStore.get_section_order_config(version)
        except DbSourceError as exc:
            logger.warning(
                "P&B Excel uploaded for %s but system config import failed: %s",
                version,
                exc,
            )
            result["config_import_error"] = str(exc)
        except Exception as exc:
            logger.exception("P&B Excel uploaded for %s but system config import failed", version)
            result["config_import_error"] = str(exc)
        return result

    @classmethod
    def get_status(cls, version: str) -> dict[str, Any]:
        version = validate_version(version)
        cls._ensure_status_loaded(version)
        state = cls._state_for(version)
        status = dict(state)
        status["version"] = version
        status["data_source"] = PBProgressDataStore.get_data_source(version)
        status["system_dataset_available"] = storage_service.exists(
            STORAGE_CATEGORY,
            cls._version_rel(version, SYSTEM_GENERATED_NAME),
        )
        status["excel"] = cls.get_excel_info(version)
        if status.get("data_source") == "system":
            status["mapping_ready"] = bool(PBProgressDataStore.get_mapping_config(version))
        if status.get("status") == "done":
            status["outputs"] = cls._build_output_manifest(version)
        else:
            status["outputs"] = status.get("outputs") or []
        return cls._attach_build_progress(status)

    @classmethod
    def get_public_status(cls, version: str) -> dict[str, Any]:
        """Consumer-facing status without import/build diagnostics."""
        status = cls.get_status(version)
        public = {
            "version": version,
            "status": status.get("status") or "idle",
            "finished_at": status.get("finished_at"),
            "outputs": status.get("outputs") or [],
        }
        if public["status"] == "running":
            public["build_stage_label"] = status.get("build_stage_label") or ""
        return public

    @classmethod
    def start_generation(cls, version: str, language: str = "all") -> str:
        version = validate_version(version)
        cls._check_build_prerequisites()
        cls._ensure_status_loaded(version)

        if cls._build_thread is not None and cls._build_thread.is_alive():
            running_label = cls._version_label(cls._build_version or DEFAULT_VERSION)
            raise RuntimeError(
                f"A report generation is already in progress ({running_label})."
            )

        with cls._lock:
            cls._clear_orphaned_run(version)
            state = cls._state_for(version)
            if state.get("status") == "running":
                raise RuntimeError("A report generation is already in progress.")

            source = PBProgressDataStore.get_data_source(version)
            if source == "system":
                from plugins.pb_progress.db_source import DbSourceError, generate_system_dataset as _generate_system_dataset

                try:
                    _generate_system_dataset(version)
                except DbSourceError as exc:
                    raise RuntimeError(str(exc)) from exc
            elif not storage_service.exists(STORAGE_CATEGORY, cls._excel_rel(version)):
                raise RuntimeError("Upload an Excel file before generating the report.")

            job_id = str(uuid.uuid4())
            started_at = cls._now_iso()
            state.update(
                {
                    "status": "running",
                    "job_id": job_id,
                    "started_at": started_at,
                    "heartbeat": started_at,
                    "finished_at": None,
                    "error": None,
                    "build_stage": "preparing",
                    "language": language or "all",
                    "outputs": [],
                    "output_names": [],
                }
            )
            cls._persist_status(version)

        cls._log_build_step(
            job_id,
            "queued",
            language=language or "all",
            stage="preparing",
            detail=f"version={version}",
        )

        app = current_app._get_current_object()
        cls._build_version = version
        cls._build_thread = threading.Thread(
            target=cls._run_build,
            args=(app, version, job_id, language or "all"),
            name=f"pb-progress-build-{version}-{job_id[:8]}",
            daemon=True,
        )
        cls._build_thread.start()
        return job_id

    @classmethod
    def _build_log_path(cls, version: str) -> Path:
        upload_root = Path(current_app.config.get("UPLOAD_FOLDER") or "instance/uploads")
        return upload_root / STORAGE_CATEGORY / version_storage_prefix(version) / BUILD_LOG_NAME

    @classmethod
    def _copy_outputs_to_storage(cls, version: str) -> list[str]:
        copied: list[str] = []
        _tool_dir, _build_script, report_output_dir = _visuals_paths()
        if not report_output_dir.is_dir():
            return copied
        for path in report_output_dir.iterdir():
            if not path.is_file() or not cls._is_publishable_output(path.name):
                continue
            with open(path, "rb") as handle:
                storage_service.upload(
                    STORAGE_CATEGORY,
                    cls._output_rel(version, path.name),
                    handle.read(),
                )
            copied.append(path.name)
        return copied

    @classmethod
    def _is_azure_storage(cls) -> bool:
        return (current_app.config.get("UPLOAD_STORAGE_PROVIDER") or "filesystem") == "azure_blob"

    @classmethod
    def _build_worker_cap(cls) -> str:
        """Cap Visuals tool ProcessPoolExecutor workers — lower on Azure to limit Chromium RAM."""
        return PB_BUILD_WORKERS_AZURE if cls._is_azure_storage() else PB_BUILD_WORKERS_LOCAL

    @classmethod
    def _build_env(cls, version: str, excel_path: str, language: str) -> dict[str, str]:
        env = os.environ.copy()
        env["PB_REPORT_EXCEL"] = str(Path(excel_path).resolve())
        env["PB_REPORT_LANGUAGE"] = language
        env["PB_REPORT_YEAR"] = REPORT_VERSIONS[version]["report_year"]
        env["PB_REPORT_LABEL"] = REPORT_VERSIONS[version]["label"]
        env["PB_FIGURES_RENDERER"] = "html"
        env["PB_BUILD_WORKERS"] = cls._build_worker_cap()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        quarto_exe = cls._resolve_quarto_exe()
        if quarto_exe:
            env["PB_QUARTO_EXE"] = quarto_exe

        if cls._is_azure_storage():
            env["PLAYWRIGHT_BROWSERS_PATH"] = PLAYWRIGHT_BROWSERS_PATH

        return env

    @classmethod
    def _consume_build_log_lines(
        cls,
        version: str,
        job_id: str,
        language: str,
        lines: list[str],
        *,
        current_stage: str,
        stage_started: float,
        build_started: float,
        last_heartbeat: float,
    ) -> tuple[str, float, float]:
        state = cls._state_for(version)
        for line in lines:
            sanitized = cls._sanitize_build_line(line)
            if sanitized:
                logger.debug(
                    "P&B progress build | ts=%s | job=%s | subprocess | %s",
                    cls._now_iso(),
                    job_id[:8],
                    sanitized,
                )
            stage = cls._infer_build_stage(line)
            now = time.time()
            with cls._lock:
                if state.get("job_id") != job_id:
                    continue
                if stage and cls._advance_build_stage(version, stage):
                    stage_duration = time.monotonic() - stage_started
                    cls._log_build_step(
                        job_id,
                        "stage_complete",
                        language=language,
                        stage=current_stage,
                        duration_s=stage_duration,
                    )
                    current_stage = stage
                    stage_started = time.monotonic()
                    cls._log_build_step(
                        job_id,
                        "stage_started",
                        language=language,
                        stage=stage,
                        detail=sanitized or None,
                    )
                    state["heartbeat"] = cls._now_iso()
                    cls._persist_status(version)
                    last_heartbeat = now
                elif now - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                    state["heartbeat"] = cls._now_iso()
                    cls._persist_status(version)
                    cls._log_build_step(
                        job_id,
                        "heartbeat",
                        language=language,
                        stage=current_stage,
                        duration_s=time.monotonic() - build_started,
                    )
                    last_heartbeat = now
        return current_stage, stage_started, last_heartbeat

    @classmethod
    def _tail_build_log(
        cls,
        log_path: Path,
        log_pos: int,
    ) -> tuple[int, list[str]]:
        if not log_path.is_file():
            return log_pos, []
        with open(log_path, encoding="utf-8", errors="replace") as handle:
            handle.seek(log_pos)
            chunk = handle.read()
            log_pos = handle.tell()
        if not chunk:
            return log_pos, []
        return log_pos, chunk.splitlines()

    @classmethod
    def _run_build(cls, app, version: str, job_id: str, language: str) -> None:
        """Background thread: run build_report.py, tail its log, update status.json."""
        temp_excel: str | None = None
        last_heartbeat = time.time()
        build_started = time.monotonic()
        stage_started = build_started
        current_stage = "preparing"
        state = cls._state_for(version)

        with app.app_context():
            try:
                visuals_tool_dir, build_script, _report_output_dir = _visuals_paths()
                if not build_script.is_file():
                    raise FileNotFoundError(f"Build script not found: {build_script}")

                excel_path = storage_service.get_absolute_path(
                    STORAGE_CATEGORY,
                    cls._excel_rel_for_source(version),
                )
                if cls._is_azure_storage():
                    temp_excel = excel_path

                env = cls._build_env(version, excel_path, language)
                cmd = [sys.executable, str(build_script), "--format", "html"]
                cls._log_build_step(
                    job_id,
                    "started",
                    language=language,
                    stage=current_stage,
                    detail=f"version={version} workers={env.get('PB_BUILD_WORKERS', '')}",
                )

                log_path = cls._build_log_path(version)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_pos = 0
                log_handle = open(log_path, "w", encoding="utf-8")
                try:
                    proc = subprocess.Popen(
                        cmd,
                        cwd=str(visuals_tool_dir),
                        env=env,
                        stdout=log_handle,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
                finally:
                    log_handle.close()

                while proc.poll() is None:
                    log_pos, lines = cls._tail_build_log(log_path, log_pos)
                    current_stage, stage_started, last_heartbeat = cls._consume_build_log_lines(
                        version,
                        job_id,
                        language,
                        lines,
                        current_stage=current_stage,
                        stage_started=stage_started,
                        build_started=build_started,
                        last_heartbeat=last_heartbeat,
                    )
                    time.sleep(0.5)

                log_pos, lines = cls._tail_build_log(log_path, log_pos)
                current_stage, stage_started, last_heartbeat = cls._consume_build_log_lines(
                    version,
                    job_id,
                    language,
                    lines,
                    current_stage=current_stage,
                    stage_started=stage_started,
                    build_started=build_started,
                    last_heartbeat=last_heartbeat,
                )
                if proc.wait() != 0:
                    raise subprocess.CalledProcessError(proc.returncode, cmd)

                current_stage = "saving"
                with cls._lock:
                    if state.get("job_id") == job_id:
                        cls._advance_build_stage(version, current_stage)
                        cls._persist_status(version)

                copied = cls._copy_outputs_to_storage(version)
                if not copied:
                    raise RuntimeError("Build completed but no output files were produced.")

                with cls._lock:
                    if state.get("job_id") != job_id:
                        return
                    state["output_names"] = copied
                    state.update(
                        {
                            "status": "done",
                            "finished_at": cls._now_iso(),
                            "error": None,
                            "build_stage": None,
                            "outputs": cls._build_output_manifest(version, copied),
                        }
                    )
                    cls._persist_status(version)
                cls._log_build_step(
                    job_id,
                    "completed",
                    language=language,
                    duration_s=time.monotonic() - build_started,
                    detail=f"version={version} output_count={len(copied)}",
                )
            except BaseException as exc:
                if isinstance(exc, KeyboardInterrupt):
                    raise
                cls._log_build_step(
                    job_id,
                    "failed",
                    language=language,
                    stage=current_stage,
                    duration_s=time.monotonic() - build_started,
                    detail=f"{type(exc).__name__}: {exc}",
                    level=logging.ERROR,
                )
                logger.exception("P&B progress report generation failed (job %s)", job_id[:8])
                with cls._lock:
                    if state.get("job_id") != job_id:
                        return
                    state.update(
                        {
                            "status": "failed",
                            "finished_at": cls._now_iso(),
                            "error": cls._public_error_message(exc),
                            "build_stage": None,
                        }
                    )
                    cls._persist_status(version)
            finally:
                if cls._build_version == version:
                    cls._build_version = None
                if temp_excel and os.path.exists(temp_excel):
                    try:
                        os.remove(temp_excel)
                    except OSError:
                        pass

    @classmethod
    def set_data_source(cls, version: str, source: str) -> str:
        version = validate_version(version)
        PBProgressDataStore.set_data_source(version, source)
        return PBProgressDataStore.get_data_source(version)

    @classmethod
    def generate_system_dataset(cls, version: str) -> dict[str, Any]:
        from plugins.pb_progress.db_source import generate_system_dataset as _generate

        version = validate_version(version)
        return _generate(version)

    @classmethod
    def compare_system_dataset(cls, version: str) -> dict[str, Any]:
        from plugins.pb_progress.db_source import compare_final_with_uploaded

        version = validate_version(version)
        return compare_final_with_uploaded(version)

    @classmethod
    def serve_system_dataset(cls, version: str):
        from flask import send_file

        version = validate_version(version)
        rel = cls._version_rel(version, SYSTEM_GENERATED_NAME)
        if not storage_service.exists(STORAGE_CATEGORY, rel):
            raise NotFound()
        path = storage_service.get_absolute_path(STORAGE_CATEGORY, rel)
        return send_file(path, as_attachment=True, download_name="system_generated.xlsx")

    @classmethod
    def serve_output(cls, version: str, filename: str):
        version = validate_version(version)
        safe_name = Path(filename).name
        if safe_name != filename:
            raise ValueError("Invalid filename.")
        rel_path = cls._output_rel(version, safe_name)
        if not storage_service.exists(STORAGE_CATEGORY, rel_path):
            from werkzeug.exceptions import NotFound

            raise NotFound()

        ext = Path(safe_name).suffix.lower()
        inline = ext in {".html", ".htm"}
        mimetype = None
        if ext == ".html":
            mimetype = "text/html"
        elif ext == ".pdf":
            mimetype = "application/pdf"
        elif ext == ".docx":
            mimetype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif ext == ".zip":
            mimetype = "application/zip"

        if inline:
            html = storage_service.download(STORAGE_CATEGORY, rel_path).decode("utf-8", errors="replace")
            for old_toc_fix in (
                "pb-report-toc-pin-fix-v2",
                "pb-report-toc-pin-fix-v3",
                "pb-report-toc-pin-script-v2",
                "pb-report-toc-pin-script-v3",
            ):
                html = re.sub(
                    rf'<style id="{old_toc_fix}"[^>]*>.*?</style>',
                    "",
                    html,
                    count=1,
                    flags=re.DOTALL,
                )
                html = re.sub(
                    rf'<script id="{old_toc_fix}"[^>]*>.*?</script>',
                    "",
                    html,
                    count=1,
                    flags=re.DOTALL,
                )
            if ("pb-report-toolbar" in html or "report-tools" in html) and 'id="pb-toolbar-fa-fix"' not in html:
                if "</head>" in html:
                    html = html.replace("</head>", _PB_REPORT_FA_FIX + "</head>", 1)
                else:
                    html = _PB_REPORT_FA_FIX + html
            if 'id="pb-report-toc-pin-fix-v4"' not in html and (
                "pb-language-panels" in html or "rebuildToc" in html
            ):
                if "</head>" in html:
                    html = html.replace("</head>", _PB_REPORT_TOC_PIN_FIX + "</head>", 1)
                else:
                    html = _PB_REPORT_TOC_PIN_FIX + html
            if 'id="pb-report-toc-host-fix"' not in html and (
                "pb-language-panels" in html or "rebuildToc" in html
            ):
                if "</body>" in html:
                    html = html.replace("</body>", _PB_REPORT_TOC_HOST_FIX + "</body>", 1)
                else:
                    html = html + _PB_REPORT_TOC_HOST_FIX
            if "pb-report-toolbar" in html and 'id="pb-toolbar-full-width-fix"' not in html:
                if "</head>" in html:
                    html = html.replace("</head>", _PB_REPORT_TOOLBAR_WIDTH_FIX + "</head>", 1)
                else:
                    html = _PB_REPORT_TOOLBAR_WIDTH_FIX + html
            if (
                "pb-report-toolbar" in html
                and 'id="pb-toolbar-title-fix"' not in html
                and "Interactive report" in html
            ):
                if "</head>" in html:
                    html = html.replace("</head>", _PB_REPORT_TOOLBAR_TITLE_FIX + "</head>", 1)
                else:
                    html = _PB_REPORT_TOOLBAR_TITLE_FIX + html
            response = Response(html, mimetype="text/html")
            response.cache_control.private = True
            response.cache_control.max_age = 300
            response.cache_control.no_transform = True
            return response

        response = storage_service.stream_response(
            STORAGE_CATEGORY,
            rel_path,
            filename=safe_name,
            mimetype=mimetype,
            as_attachment=not inline,
        )
        if inline:
            # The HTML report is static once generated; let browsers cache it for 5 minutes
            # so repeated tab-switches don't re-download the whole file.  'private' ensures
            # CDN/proxy caches never store it (it's behind authentication).
            response.cache_control.private = True
            response.cache_control.max_age = 300
            response.cache_control.no_transform = True
        return response
