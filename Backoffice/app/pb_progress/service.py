"""P&B Progress service — Excel storage, Visuals tool subprocess build, output serving."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import timezone
from pathlib import Path
from typing import Any, ClassVar

from flask import current_app, url_for
from werkzeug.datastructures import FileStorage

from app.services import storage_service
from app.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)

STORAGE_CATEGORY = "pb_progress"
EXCEL_REL_PATH = "source/SG_Report.xlsx"
STATUS_REL_PATH = "status.json"
BUILD_LOG_REL_PATH = "build.log"
OUTPUT_PREFIX = "output/"
OUTPUT_URL_PREFIX = "/admin/data-exploration/pb-progress/output/"

HEARTBEAT_INTERVAL_SECONDS = 60

# Build defaults — baked in; no App Service variables required.
PB_REPORT_YEAR = "2026"
PB_BUILD_WORKERS_LOCAL = "1"
PB_BUILD_WORKERS_AZURE = "1"
PLAYWRIGHT_BROWSERS_PATH = "/home/site/playwright-browsers"
QUARTO_VERSION = "1.6.42"

VISUALS_TOOL_DIR = Path(__file__).resolve().parents[2] / "Visuals tool"
BUILD_SCRIPT = VISUALS_TOOL_DIR / "scripts" / "build_report.py"
REPORT_OUTPUT_DIR = VISUALS_TOOL_DIR / "report" / "output"

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
    _state: ClassVar[dict[str, Any]] = {
        "status": "idle",
        "job_id": None,
        "started_at": None,
        "finished_at": None,
        "error": None,
        "build_stage": None,
        "output_names": [],
    }
    _loaded_status: ClassVar[bool] = False
    _build_thread: ClassVar[threading.Thread | None] = None

    @classmethod
    def _now_iso(cls) -> str:
        return utcnow().replace(tzinfo=timezone.utc).isoformat()

    @classmethod
    def _clear_orphaned_run(cls) -> None:
        """After a server restart, status.json may still say 'running' but no thread exists."""
        if cls._state.get("status") != "running":
            return
        if cls._build_thread is not None and cls._build_thread.is_alive():
            return
        cls._state.update(
            {
                "status": "failed",
                "finished_at": cls._now_iso(),
                "error": "Generation was interrupted when the server restarted.",
                "build_stage": None,
            }
        )
        cls._persist_status()

    @classmethod
    def _reload_status_from_storage(cls) -> dict[str, Any] | None:
        if not storage_service.exists(STORAGE_CATEGORY, STATUS_REL_PATH):
            return None
        try:
            raw = storage_service.download(STORAGE_CATEGORY, STATUS_REL_PATH)
            persisted = json.loads(raw.decode("utf-8"))
            return persisted if isinstance(persisted, dict) else None
        except Exception as exc:
            logger.warning("Failed to reload P&B progress status from storage: %s", exc)
            return None

    @classmethod
    def _ensure_status_loaded(cls) -> None:
        if cls._loaded_status:
            cls._clear_orphaned_run()
            return
        cls._loaded_status = True
        persisted = cls._reload_status_from_storage()
        if persisted:
            cls._state.update(persisted)
        cls._clear_orphaned_run()

    @classmethod
    def _persist_status(cls, payload: dict[str, Any] | None = None) -> None:
        data = dict(payload or cls._state)
        data.pop("log_tail", None)
        storage_service.upload(
            STORAGE_CATEGORY,
            STATUS_REL_PATH,
            json.dumps(data, indent=2).encode("utf-8"),
        )

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
    def _advance_build_stage(cls, stage_id: str) -> bool:
        """Move to a new stage only when it is later in the pipeline (never go backward)."""
        current_stage = cls._state.get("build_stage")
        if cls._stage_index(stage_id) <= cls._stage_index(current_stage):
            return False
        cls._set_build_stage(stage_id)
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
    def _set_build_stage(cls, stage_id: str) -> None:
        cls._state["build_stage"] = stage_id

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
        if not BUILD_SCRIPT.is_file():
            issues.append(f"Build script not found: {BUILD_SCRIPT}")

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
    def _output_url(cls, filename: str) -> str:
        try:
            return url_for("pb_progress.serve_output", filename=filename)
        except RuntimeError:
            # Background build thread has app context but no active HTTP request.
            return f"{OUTPUT_URL_PREFIX}{filename}"

    @classmethod
    def _resolve_output_names(cls, output_names: list[str] | None = None) -> list[str]:
        names = list(output_names or cls._state.get("output_names") or [])
        if names:
            return names
        if not REPORT_OUTPUT_DIR.is_dir():
            return []
        return sorted(
            p.name
            for p in REPORT_OUTPUT_DIR.iterdir()
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
    def _build_output_manifest(cls, output_names: list[str] | None = None) -> list[dict[str, Any]]:
        outputs: list[dict[str, Any]] = []
        names = sorted(cls._resolve_output_names(output_names), key=cls._output_sort_key)
        for name in names:
            if not cls._is_publishable_output(name):
                continue
            rel_name = f"{OUTPUT_PREFIX}{name}"
            if not storage_service.exists(STORAGE_CATEGORY, rel_name):
                continue
            size = storage_service.get_size(STORAGE_CATEGORY, rel_name)
            outputs.append(
                {
                    "name": name,
                    "label": cls._label_for_output(name),
                    "url": cls._output_url(name),
                    "size_bytes": size,
                    "size_label": cls._format_size(size) if size >= 0 else "",
                }
            )
        return outputs

    @classmethod
    def get_excel_info(cls) -> dict[str, Any] | None:
        cls._ensure_status_loaded()
        excel_meta = cls._state.get("excel")
        if excel_meta:
            return excel_meta
        if not storage_service.exists(STORAGE_CATEGORY, EXCEL_REL_PATH):
            return None
        size = storage_service.get_size(STORAGE_CATEGORY, EXCEL_REL_PATH)
        return {
            "filename": "SG Report.xlsx",
            "size_bytes": size,
            "size_label": cls._format_size(size) if size >= 0 else "",
            "uploaded_at": None,
        }

    @classmethod
    def store_excel(cls, file_storage: FileStorage) -> dict[str, Any]:
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

        storage_service.upload(STORAGE_CATEGORY, EXCEL_REL_PATH, file_storage)

        uploaded_at = cls._now_iso()
        excel_info = {
            "filename": filename,
            "size_bytes": size_bytes,
            "size_label": cls._format_size(size_bytes),
            "uploaded_at": uploaded_at,
        }

        cls._ensure_status_loaded()
        cls._state["excel"] = excel_info
        if cls._state.get("status") != "running":
            cls._state["status"] = "idle"
            cls._state["error"] = None
        cls._persist_status()
        return excel_info

    @classmethod
    def get_status(cls) -> dict[str, Any]:
        cls._ensure_status_loaded()
        status = dict(cls._state)
        status["excel"] = cls.get_excel_info()
        if status.get("status") == "done":
            status["outputs"] = cls._build_output_manifest()
        else:
            status["outputs"] = status.get("outputs") or []
        return cls._attach_build_progress(status)

    @classmethod
    def get_public_status(cls) -> dict[str, Any]:
        """Consumer-facing status without import/build diagnostics."""
        status = cls.get_status()
        public = {
            "status": status.get("status") or "idle",
            "finished_at": status.get("finished_at"),
            "outputs": status.get("outputs") or [],
        }
        if public["status"] == "running":
            public["build_stage_label"] = status.get("build_stage_label") or ""
        return public

    @classmethod
    def start_generation(cls, language: str = "all") -> str:
        cls._check_build_prerequisites()
        cls._ensure_status_loaded()

        if cls._build_thread is not None and cls._build_thread.is_alive():
            raise RuntimeError("A report generation is already in progress.")

        with cls._lock:
            cls._clear_orphaned_run()
            if cls._state.get("status") == "running":
                raise RuntimeError("A report generation is already in progress.")
            if not storage_service.exists(STORAGE_CATEGORY, EXCEL_REL_PATH):
                raise RuntimeError("Upload an Excel file before generating the report.")

            job_id = str(uuid.uuid4())
            started_at = cls._now_iso()
            cls._state.update(
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
            cls._persist_status()

        cls._log_build_step(
            job_id,
            "queued",
            language=language or "all",
            stage="preparing",
        )

        app = current_app._get_current_object()
        cls._build_thread = threading.Thread(
            target=cls._run_build,
            args=(app, job_id, language or "all"),
            name=f"pb-progress-build-{job_id[:8]}",
            daemon=True,
        )
        cls._build_thread.start()
        return job_id

    @classmethod
    def _build_log_path(cls) -> Path:
        upload_root = Path(current_app.config.get("UPLOAD_FOLDER") or "instance/uploads")
        return upload_root / STORAGE_CATEGORY / BUILD_LOG_REL_PATH

    @classmethod
    def _copy_outputs_to_storage(cls) -> list[str]:
        copied: list[str] = []
        if not REPORT_OUTPUT_DIR.is_dir():
            return copied
        for path in REPORT_OUTPUT_DIR.iterdir():
            if not path.is_file() or not cls._is_publishable_output(path.name):
                continue
            rel_name = f"{OUTPUT_PREFIX}{path.name}"
            with open(path, "rb") as handle:
                storage_service.upload(STORAGE_CATEGORY, rel_name, handle.read())
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
    def _build_env(cls, excel_path: str, language: str) -> dict[str, str]:
        env = os.environ.copy()
        env["PB_REPORT_EXCEL"] = str(Path(excel_path).resolve())
        env["PB_REPORT_LANGUAGE"] = language
        env["PB_REPORT_YEAR"] = PB_REPORT_YEAR
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
        job_id: str,
        language: str,
        lines: list[str],
        *,
        current_stage: str,
        stage_started: float,
        build_started: float,
        last_heartbeat: float,
    ) -> tuple[str, float, float]:
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
                if cls._state.get("job_id") != job_id:
                    continue
                if stage and cls._advance_build_stage(stage):
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
                    cls._state["heartbeat"] = cls._now_iso()
                    cls._persist_status()
                    last_heartbeat = now
                elif now - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                    cls._state["heartbeat"] = cls._now_iso()
                    cls._persist_status()
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
    def _run_build(cls, app, job_id: str, language: str) -> None:
        """Background thread: run build_report.py, tail its log, update status.json."""
        temp_excel: str | None = None
        last_heartbeat = time.time()
        build_started = time.monotonic()
        stage_started = build_started
        current_stage = "preparing"

        with app.app_context():
            try:
                if not BUILD_SCRIPT.is_file():
                    raise FileNotFoundError(f"Build script not found: {BUILD_SCRIPT}")

                excel_path = storage_service.get_absolute_path(STORAGE_CATEGORY, EXCEL_REL_PATH)
                if cls._is_azure_storage():
                    temp_excel = excel_path

                env = cls._build_env(excel_path, language)
                cmd = [sys.executable, str(BUILD_SCRIPT), "--format", "html"]
                cls._log_build_step(
                    job_id,
                    "started",
                    language=language,
                    stage=current_stage,
                    detail=f"workers={env.get('PB_BUILD_WORKERS', '')}",
                )

                log_path = cls._build_log_path()
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_pos = 0
                log_handle = open(log_path, "w", encoding="utf-8")
                try:
                    proc = subprocess.Popen(
                        cmd,
                        cwd=str(VISUALS_TOOL_DIR),
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
                    if cls._state.get("job_id") == job_id:
                        cls._advance_build_stage(current_stage)
                        cls._persist_status()

                copied = cls._copy_outputs_to_storage()
                if not copied:
                    raise RuntimeError("Build completed but no output files were produced.")

                with cls._lock:
                    if cls._state.get("job_id") != job_id:
                        return
                    cls._state["output_names"] = copied
                    cls._state.update(
                        {
                            "status": "done",
                            "finished_at": cls._now_iso(),
                            "error": None,
                            "build_stage": None,
                            "outputs": cls._build_output_manifest(copied),
                        }
                    )
                    cls._persist_status()
                cls._log_build_step(
                    job_id,
                    "completed",
                    language=language,
                    duration_s=time.monotonic() - build_started,
                    detail=f"output_count={len(copied)}",
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
                    if cls._state.get("job_id") != job_id:
                        return
                    cls._state.update(
                        {
                            "status": "failed",
                            "finished_at": cls._now_iso(),
                            "error": cls._public_error_message(exc),
                            "build_stage": None,
                        }
                    )
                    cls._persist_status()
            finally:
                if temp_excel and os.path.exists(temp_excel):
                    try:
                        os.remove(temp_excel)
                    except OSError:
                        pass

    @classmethod
    def serve_output(cls, filename: str):
        safe_name = Path(filename).name
        if safe_name != filename:
            raise ValueError("Invalid filename.")
        rel_path = f"{OUTPUT_PREFIX}{safe_name}"
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
