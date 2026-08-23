"""Single-dashboard PNG/PDF/InDesign export for UPR visuals."""

from __future__ import annotations

import json
import logging
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Callable

from flask import current_app

from plugins.upr_visuals.catalog import DASHBOARD_BY_ID
from plugins.upr_visuals.data import (
    UprVisualsError,
    build_payload,
    filename_from_visual_title,
    title_for_export_filename,
)
from plugins.upr_visuals.export_job import run_isolated
from plugins.upr_visuals.i18n import export_locale, localize_export, translate_styled_blocks
from plugins.upr_visuals.raster import render_png_isolated
from plugins.upr_visuals.render import render_dashboard_html

logger = logging.getLogger(__name__)

STORAGE_CATEGORY = "upr_visuals"
RENDER_TIMEOUT_SECONDS = 120


def visual_export_filename(meta: dict[str, Any], dashboard_id: str, ext: str) -> str:
    suffix = ext.lstrip(".").lower()
    if dashboard_id == "combined":
        title = title_for_export_filename(meta)
        if title:
            return filename_from_visual_title(title, suffix)
    iso3 = filename_from_visual_title(str(meta.get("iso3") or "UNK"), "png")[:-4]
    round_code = filename_from_visual_title(
        str(meta.get("round_code") or meta.get("period_name") or "round"),
        "png",
    )[:-4]
    dash = filename_from_visual_title(dashboard_id, "png")[:-4]
    return f"{iso3}_{round_code}_{dash}.{suffix}"


class UprVisualsService:
    @classmethod
    def png_bytes(cls, aes_id: int, dashboard_id: str, *, lang: str = "en") -> tuple[bytes, str]:
        with export_locale(lang):
            payload, html = cls._dashboard_html(aes_id, dashboard_id)
            filename = visual_export_filename(payload.get("meta") or {}, dashboard_id, "png")
            tmp = Path(current_app.instance_path) / "upr_visuals_tmp" / f"{uuid.uuid4().hex}_{filename}"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            try:
                render_png_isolated(
                    html, tmp, dashboard_id=dashboard_id, timeout=RENDER_TIMEOUT_SECONDS
                )
                return tmp.read_bytes(), filename
            finally:
                try:
                    tmp.unlink()
                except OSError:
                    pass

    @classmethod
    def pdf_bytes(cls, aes_id: int, dashboard_id: str, *, lang: str = "en") -> tuple[bytes, str]:
        with export_locale(lang):
            payload, html = cls._dashboard_html(aes_id, dashboard_id)
            meta = payload.get("meta") or {}
            filename = visual_export_filename(meta, dashboard_id, "pdf")
            tmp = Path(current_app.instance_path) / "upr_visuals_tmp" / f"{uuid.uuid4().hex}_{filename}"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            html_path = tmp.with_suffix(tmp.suffix + ".html")
            html_path.write_text(html, encoding="utf-8")
            try:
                run_isolated(
                    {
                        "kind": "pdf",
                        "html_path": str(html_path),
                        "output_path": str(tmp),
                        "dashboard_id": dashboard_id,
                        "lang": lang,
                        "title": str(meta.get("document_title") or ""),
                    },
                    timeout=RENDER_TIMEOUT_SECONDS,
                )
                return tmp.read_bytes(), filename
            finally:
                for path in (tmp, html_path):
                    try:
                        path.unlink()
                    except OSError:
                        pass

    @classmethod
    def idml_zip_bytes(cls, aes_id: int, word_bytes: bytes | None = None, *, lang: str = "en") -> tuple[bytes, str]:
        from plugins.upr_visuals.data import filename_from_visual_title

        with export_locale(lang):
            payload, html = cls._dashboard_html(aes_id, "combined")
            title = title_for_export_filename(payload.get("meta") or {}) or "UPR visuals"
            filename = f"{filename_from_visual_title(title, 'zip')[:-4]} - InDesign.zip"
            work_dir = Path(current_app.instance_path) / "upr_visuals_tmp" / f"idml_{uuid.uuid4().hex}"
            work_dir.mkdir(parents=True, exist_ok=True)
            html_path = work_dir / "in.html"
            payload_path = work_dir / "payload.json"
            output = work_dir / filename
            html_path.write_text(html, encoding="utf-8")
            payload_path.write_text(json.dumps(payload), encoding="utf-8")
            job: dict[str, Any] = {
                "kind": "idml",
                "html_path": str(html_path),
                "payload_path": str(payload_path),
                "output_path": str(output),
                "work_dir": str(work_dir / "package"),
                "dashboard_id": "combined",
                "lang": lang,
            }
            if word_bytes:
                word_path = work_dir / "narrative.docx"
                word_path.write_bytes(word_bytes)
                job["word_path"] = str(word_path)
            try:
                run_isolated(job, timeout=RENDER_TIMEOUT_SECONDS)
                return output.read_bytes(), filename
            finally:
                shutil.rmtree(work_dir, ignore_errors=True)

    @classmethod
    def narrative_pdf_bytes(
        cls,
        aes_id: int,
        word_bytes: bytes,
        *,
        lang: str = "en",
        on_progress: Callable[..., Any] | None = None,
    ) -> tuple[bytes, str]:
        from plugins.upr_visuals.idml import (
            folio_label,
            load_word_paragraphs,
            merge_report_pdfs,
            style_narrative_blocks,
        )

        total = 5

        def notify(step: int, message: str, *, log: bool = True, **extra: Any) -> None:
            if log:
                logger.info("UPR narrative PDF %s/%s %s", step, total, message)
            if on_progress:
                on_progress(step=step, total=total, message=message, **extra)

        with export_locale(lang):
            def on_chrome(*, done: int, total: int, lang: str, elapsed: int | None = None, **_k: Any) -> None:
                notify(
                    1,
                    f"Translating visuals… {done} of {total}" if total else "Loading assignment data…",
                    log=done in {0, total},
                    elapsed=elapsed,
                    chunk_done=done,
                    chunk_total=total,
                )

            notify(1, "Loading assignment data…")
            payload, html = cls._dashboard_html(
                aes_id,
                "combined",
                on_progress=on_chrome if lang != "en" else None,
            )
            meta = payload.get("meta") or {}
            filename = visual_export_filename(meta, "combined", "pdf")
            if lang != "en":
                def on_translate(*, done: int, total: int, lang: str, elapsed: int | None = None, **_k: Any) -> None:
                    notify(
                        2,
                        f"Translating narrative… {done} of {total}",
                        log=done in {0, total},
                        elapsed=elapsed,
                        chunk_done=done,
                        chunk_total=total,
                    )

                notify(2, "Translating narrative…")
                styled = translate_styled_blocks(
                    style_narrative_blocks(
                        load_word_paragraphs(word_bytes),
                        country_name=str(meta.get("country_name") or ""),
                    ),
                    on_progress=on_translate,
                )
            else:
                notify(2, "Reading Word document…")
                styled = translate_styled_blocks(
                    style_narrative_blocks(
                        load_word_paragraphs(word_bytes),
                        country_name=str(meta.get("country_name") or ""),
                    )
                )
            work_dir = Path(current_app.instance_path) / "upr_visuals_tmp" / f"nar_{uuid.uuid4().hex}"
            work_dir.mkdir(parents=True, exist_ok=True)
            html_path = work_dir / "in.html"
            payload_path = work_dir / "payload.json"
            styled_path = work_dir / "styled.json"
            visuals_path = work_dir / "visuals.pdf"
            narrative_path = work_dir / "narrative.pdf"
            html_path.write_text(html, encoding="utf-8")
            payload_path.write_text(json.dumps(payload), encoding="utf-8")
            styled_path.write_text(json.dumps(styled), encoding="utf-8")
            try:
                notify(3, "Rendering visuals and narrative…")
                cls._render_isolated_parallel(
                    [
                        {
                            "kind": "pdf",
                            "html_path": str(html_path),
                            "output_path": str(visuals_path),
                            "dashboard_id": "combined",
                            "lang": lang,
                        },
                        {
                            "kind": "narrative_pages",
                            "payload_path": str(payload_path),
                            "styled_path": str(styled_path),
                            "output_path": str(narrative_path),
                            "lang": lang,
                        },
                    ],
                    on_tick=lambda elapsed: notify(
                        3,
                        "Rendering visuals and narrative…",
                        log=False,
                        elapsed=elapsed,
                    ),
                )
                notify(5, "Combining PDF…")
                visuals = visuals_path.read_bytes()
                narrative = narrative_path.read_bytes()
                data = merge_report_pdfs(visuals, narrative, folio=folio_label(meta)) if styled else visuals
                return data, filename
            finally:
                shutil.rmtree(work_dir, ignore_errors=True)

    @classmethod
    def _dashboard_html(
        cls,
        aes_id: int,
        dashboard_id: str,
        *,
        on_progress: Callable[..., Any] | None = None,
    ) -> tuple[dict[str, Any], str]:
        def build() -> tuple[dict[str, Any], str]:
            payload = build_payload(aes_id, inline_icons=True)
            if dashboard_id not in DASHBOARD_BY_ID:
                raise UprVisualsError(f"Unknown dashboard: {dashboard_id}")
            return payload, render_dashboard_html(payload, dashboard_id)

        return localize_export(build, on_progress=on_progress, aes_id=aes_id)

    @classmethod
    def _render_isolated_parallel(
        cls,
        jobs: list[dict[str, Any]],
        *,
        timeout: float = RENDER_TIMEOUT_SECONDS,
        on_tick: Callable[[int], None] | None = None,
    ) -> list[Path]:
        """Run isolated WeasyPrint children side by side.

        Progress stays on this thread so Flask/DB session use stays single-threaded.
        Each child still enforces *timeout* on its own process.
        """
        if not jobs:
            return []
        if len(jobs) == 1:
            return [run_isolated(jobs[0], timeout=timeout)]

        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = [pool.submit(run_isolated, job, timeout=timeout) for job in jobs]
            pending = set(futures)
            while pending:
                done, pending = wait(pending, timeout=1)
                if on_tick:
                    on_tick(int(time.monotonic() - started))
            return [fut.result() for fut in futures]

    @classmethod
    def _render_bulk_item(
        cls,
        job_dir: Path,
        *,
        payload: dict[str, Any],
        html: str,
        dashboard_id: str,
        folder: str,
        export_format: str,
        word_path: Path | None,
        lang: str = "en",
    ) -> tuple[Path, str]:
        meta = payload.get("meta") or {}
        token = uuid.uuid4().hex[:10]
        if export_format == "png":
            tmp = job_dir / f"{token}_{dashboard_id}.png"
            render_png_isolated(
                html, tmp, dashboard_id=dashboard_id, timeout=RENDER_TIMEOUT_SECONDS
            )
            return tmp, f"{folder}/{dashboard_id}.png"

        if export_format == "pdf":
            filename = visual_export_filename(meta, dashboard_id, "pdf")
            tmp = job_dir / f"{token}_{filename}"
            html_path = tmp.with_suffix(tmp.suffix + ".html")
            html_path.write_text(html, encoding="utf-8")
            job: dict[str, Any] = {
                "kind": "narrative_pdf" if word_path else "pdf",
                "html_path": str(html_path),
                "output_path": str(tmp),
                "dashboard_id": dashboard_id,
            }
            if word_path:
                payload_path = tmp.with_suffix(tmp.suffix + ".payload.json")
                payload_path.write_text(json.dumps(payload), encoding="utf-8")
                job["kind"] = "narrative_pdf"
                job["payload_path"] = str(payload_path)
                job["word_path"] = str(word_path)
                job["lang"] = lang
            try:
                run_isolated(job, timeout=RENDER_TIMEOUT_SECONDS)
            finally:
                for key in ("html_path", "payload_path"):
                    raw = job.get(key)
                    if not raw:
                        continue
                    try:
                        Path(raw).unlink()
                    except OSError:
                        pass
            return tmp, f"{folder}/{filename}"

        title = title_for_export_filename(meta) or "UPR visuals"
        filename = f"{filename_from_visual_title(title, 'zip')[:-4]} - InDesign.zip"
        tmp = job_dir / f"{token}_{filename}"
        html_path = tmp.with_suffix(".html")
        payload_path = tmp.with_suffix(".payload.json")
        html_path.write_text(html, encoding="utf-8")
        payload_path.write_text(json.dumps(payload), encoding="utf-8")
        work_dir = job_dir / f"idml_{token}"
        job = {
            "kind": "idml",
            "html_path": str(html_path),
            "payload_path": str(payload_path),
            "output_path": str(tmp),
            "work_dir": str(work_dir),
            "dashboard_id": "combined",
        }
        if word_path:
            job["word_path"] = str(word_path)
        job["lang"] = lang
        try:
            run_isolated(job, timeout=RENDER_TIMEOUT_SECONDS)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
            for extra in (html_path, payload_path):
                try:
                    extra.unlink()
                except OSError:
                    pass
        return tmp, f"{folder}/{filename}"
