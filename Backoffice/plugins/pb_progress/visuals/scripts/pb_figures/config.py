import os
import shutil
from pathlib import Path



from .languages import INDICATOR_COLUMNS, LANG_COLUMNS, LANGUAGES, SP_LANG_COLUMNS



# IFRC brand colours extracted from P&B figures.twb

COLOR_VALUE = "#c22526"

COLOR_TARGET = "#f28e2b"

COLOR_GAP = "#c1c1c1"

COLOR_TEXT = "#000000"

COLOR_DIVIDER = "#d0d0d0"


# Line chart visual effects — derived from the active style preset (classic default)
from .styles import DEFAULT_STYLE, resolve_style  # noqa: E402

LINE_CHART_EFFECTS = resolve_style(DEFAULT_STYLE)["line_chart_effects"]


# Dashboard canvas sizes from Tableau (pixels at 96 DPI export)

DASHBOARD_SIZES = {

    "EF1": (827, 550),

    "EF2": (827, 670),

    "EF3": (827, 430),

    "EF4": (827, 900),

    "SP1": (827, 800),

    "SP2": (827, 800),

    "SP3": (827, 800),

    "SP4": (827, 1100),

    "SP5": (827, 800),

}



DEFAULT_EXCEL = Path(__file__).resolve().parents[2] / "SG Report.xlsx"

_DEFAULT_VISUALS_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = _DEFAULT_VISUALS_ROOT / "Figures"

BUILD_COPY_SUFFIX = "._build"


def visuals_build_root() -> Path | None:
    """Writable build workspace (Azure uploads dir); None uses plugin tree."""
    raw = (os.environ.get("PB_VISUALS_BUILD_ROOT") or "").strip()
    return Path(raw) if raw else None


def resolve_figures_output() -> Path:
    """Dashboard PNG download folder; uses writable workspace on Azure when set."""
    root = visuals_build_root()
    path = (root / "Figures") if root is not None else _DEFAULT_VISUALS_ROOT / "Figures"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_report_output() -> Path:
    """Quarto/DOCX/PDF output directory (always under the plugin report tree)."""
    path = _DEFAULT_VISUALS_ROOT / "report" / "output"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_readable(path: Path) -> bool:
    try:
        with path.open("rb"):
            return True
    except (PermissionError, OSError):
        return False


def resolve_excel(path: Path | str | None = None) -> Path:
    """Return a readable workbook path, copying if the source is locked in Excel."""
    if path is not None:
        src = Path(path)
    elif os.environ.get("PB_REPORT_EXCEL"):
        src = Path(os.environ["PB_REPORT_EXCEL"])
    else:
        src = DEFAULT_EXCEL

    if _is_readable(src):
        return src

    copy = src.with_name(f"{src.stem}{BUILD_COPY_SUFFIX}{src.suffix}")
    shutil.copy2(src, copy)
    if not _is_readable(copy):
        raise PermissionError(
            f"Cannot read {src.name} — close it in Excel and try again."
        )
    return copy


def build_workers(count: int) -> int:
    """Number of worker processes to use for `count` independent parallel jobs.

    Each worker launches its own Chromium instance via Playwright, so this is
    capped (not just set to os.cpu_count()) to avoid overloading the machine.
    Override with the PB_BUILD_WORKERS environment variable, e.g. PB_BUILD_WORKERS=1
    to force fully sequential behaviour for debugging.
    """
    if count <= 1:
        return 1

    env_value = os.environ.get("PB_BUILD_WORKERS")
    if env_value:
        try:
            cap = int(env_value)
        except ValueError:
            cap = min(4, os.cpu_count() or 4)
    else:
        cap = min(4, os.cpu_count() or 4)

    return max(1, min(count, cap))


def owns_excel_copy() -> bool:
    """True if this process is responsible for cleaning up the shared build copy.

    A parent process (build_report.py or pb-report.bat) that pre-creates the
    build copy signals this by exporting PB_REPORT_EXCEL before launching
    child scripts. Children must not delete a copy they don't own, or they
    will pull it out from under later steps in the same build.
    """
    return not os.environ.get("PB_REPORT_EXCEL")


def cleanup_build_copy(excel: Path | str | None = None, *, force: bool = False) -> None:
    """Delete the ._build temporary copy, if one was created by resolve_excel().

    Skips deletion when PB_REPORT_EXCEL is set in the environment, since that
    means an outer process owns the copy's lifecycle (pass force=True to
    override, e.g. from the outermost process itself).
    """
    if not force and not owns_excel_copy():
        return
    src = Path(excel) if excel else DEFAULT_EXCEL
    copy = src.with_name(f"{src.stem}{BUILD_COPY_SUFFIX}{src.suffix}")
    if copy.exists() and copy != src:
        try:
            copy.unlink()
        except OSError:
            pass

