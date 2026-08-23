"""Child-process export jobs so WeasyPrint/Cairo cannot take down Flask."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from plugins.upr_visuals.raster import (
    PNG_EXPORT_SCALE,
    _BACKOFFICE_ROOT,
    render_pdf_bytes,
    render_png,
    summarize_child_log,
)

logger = logging.getLogger(__name__)


def run_export_job_file(job_path: str | Path) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("weasyprint").setLevel(logging.ERROR)
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    kind = str(job.get("kind") or "png")
    output = Path(job["output_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    html = Path(job["html_path"]).read_text(encoding="utf-8") if job.get("html_path") else ""
    dashboard_id = str(job.get("dashboard_id") or "combined")
    lang = str(job.get("lang") or "en")
    os.environ["UPR_VISUALS_LANG"] = lang

    if kind == "png":
        render_png(
            html,
            output,
            dashboard_id=dashboard_id,
            scale=float(job.get("scale") or PNG_EXPORT_SCALE),
        )
        return

    if kind == "pdf":
        logger.info("UPR export child rendering visuals PDF")
        output.write_bytes(render_pdf_bytes(html, dashboard_id=dashboard_id))
        logger.info("UPR export child visuals PDF done (%s bytes)", output.stat().st_size)
        return

    if kind == "narrative_pages":
        from plugins.upr_visuals.idml import folio_label, render_narrative_pdf_bytes

        payload = json.loads(Path(job["payload_path"]).read_text(encoding="utf-8"))
        styled = json.loads(Path(job["styled_path"]).read_text(encoding="utf-8"))
        logger.info("UPR export child rendering narrative pages (%s blocks)", len(styled or []))
        output.write_bytes(
            render_narrative_pdf_bytes(styled, folio=folio_label(payload.get("meta") or {}))
        )
        logger.info("UPR export child narrative pages done (%s bytes)", output.stat().st_size)
        return

    if kind == "narrative_pdf":
        from plugins.upr_visuals.idml import (
            folio_label,
            load_word_paragraphs,
            merge_report_pdfs,
            render_narrative_pdf_bytes,
            style_narrative_blocks,
        )

        payload = json.loads(Path(job["payload_path"]).read_text(encoding="utf-8"))
        meta = payload.get("meta") or {}
        logger.info("UPR export child rendering visuals PDF")
        visuals = render_pdf_bytes(html, dashboard_id="combined")
        if job.get("styled_path"):
            styled = json.loads(Path(job["styled_path"]).read_text(encoding="utf-8"))
        else:
            from plugins.upr_visuals.i18n import translate_styled_blocks

            word = Path(job["word_path"]).read_bytes()
            styled = translate_styled_blocks(
                style_narrative_blocks(
                    load_word_paragraphs(word),
                    country_name=str(meta.get("country_name") or ""),
                )
            )
        logger.info("UPR export child rendering narrative pages (%s blocks)", len(styled or []))
        narrative = render_narrative_pdf_bytes(styled, folio=folio_label(meta))
        logger.info("UPR export child combining PDFs")
        data = merge_report_pdfs(visuals, narrative, folio=folio_label(meta)) if styled else visuals
        output.write_bytes(data)
        logger.info("UPR export child combined PDF done (%s bytes)", output.stat().st_size)
        return

    if kind == "idml":
        from plugins.upr_visuals.idml import build_indesign_package

        payload = json.loads(Path(job["payload_path"]).read_text(encoding="utf-8"))
        word = Path(job["word_path"]).read_bytes() if job.get("word_path") else None
        pdf_bytes = render_pdf_bytes(html, dashboard_id="combined")
        work_dir = Path(job["work_dir"])
        work_dir.mkdir(parents=True, exist_ok=True)
        result = build_indesign_package(
            payload=payload,
            pdf_bytes=pdf_bytes,
            work_dir=work_dir,
            word_bytes=word,
        )
        output.write_bytes(result["zip_bytes"])
        return

    raise RuntimeError(f"Unknown export kind: {kind}")


def run_isolated(job: dict, *, timeout: float, on_progress=None) -> Path:
    """Run one export job in a child process and return the output path."""
    output_path = Path(job["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    job_path = output_path.with_suffix(output_path.suffix + ".job.json")
    job_path.write_text(json.dumps(job), encoding="utf-8")
    env = os.environ.copy()
    pythonpath = os.pathsep.join(
        path for path in (str(_BACKOFFICE_ROOT), env.get("PYTHONPATH", "")) if path
    )
    env["PYTHONPATH"] = pythonpath
    env["PYTHONUNBUFFERED"] = "1"
    if job.get("lang"):
        env["UPR_VISUALS_LANG"] = str(job.get("lang"))
    cmd = [
        sys.executable,
        "-c",
        "from plugins.upr_visuals.export_job import run_export_job_file; "
        "run_export_job_file(__import__('sys').argv[1])",
        str(job_path),
    ]
    kind = job.get("kind") or "png"
    logger.info("UPR export start %s %s", kind, job.get("dashboard_id") or "")
    started = time.monotonic()
    chunks: list[str] = []
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(_BACKOFFICE_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
        )
    except Exception:
        try:
            job_path.unlink()
        except OSError:
            pass
        raise

    def _pump() -> None:
        stream = proc.stdout
        if stream is None:
            return
        for line in stream:
            text = line.rstrip()
            if not text:
                continue
            chunks.append(text)
            if text.startswith(("INFO ", "WARNING ", "ERROR ", "UPR ")):
                logger.info("%s", text)

    pump = threading.Thread(target=_pump, name=f"upr-export-log-{kind}", daemon=True)
    pump.start()
    last_logged = -10
    try:
        while True:
            elapsed = time.monotonic() - started
            if elapsed > timeout:
                proc.kill()
                proc.wait(timeout=5)
                logger.error("UPR export timed out after %.0fs: %s", timeout, kind)
                raise TimeoutError(f"Export timed out for {kind}")
            if proc.poll() is not None:
                break
            secs = int(elapsed)
            if on_progress:
                on_progress({"elapsed": secs, "kind": kind})
            if secs - last_logged >= 10:
                logger.info("UPR export still running %s (%ss)", kind, secs)
                last_logged = secs
            time.sleep(1)
        pump.join(timeout=2)
        returncode = proc.returncode
    finally:
        try:
            job_path.unlink()
        except OSError:
            pass
    child_log = "\n".join(chunks).strip()
    useful = summarize_child_log(child_log)
    if useful:
        logger.warning("UPR export %s child:\n%s", kind, useful[-4000:])
    if returncode:
        logger.error("UPR export crashed for %s (exit %s)", kind, returncode)
        raise RuntimeError(useful or child_log or f"Export crashed (exit {returncode})")
    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise RuntimeError(f"Export produced no file for {kind}")
    logger.info(
        "UPR export done %s (%s bytes, %.0fs)",
        kind,
        output_path.stat().st_size,
        time.monotonic() - started,
    )
    return output_path
