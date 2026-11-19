"""NSD master import: upload, preview, run, status."""
import io
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, redirect, request, send_file, url_for
from flask_login import current_user
from werkzeug.utils import secure_filename

from app import db
from app.routes.admin.shared import admin_permission_required
from app.services.imports.import_change_log import (
    attach_import_change_log_to_activity,
    change_log_url_for,
    latest_import_run,
    list_import_runs,
    publish_import_log,
    set_import_audit_details,
)
from app.utils.forms.advanced_validation import validate_upload_extension_and_mime
from app.utils.api.api_helpers import get_json_safe
from app.utils.api.api_responses import json_bad_request, json_ok
from app.utils.files.file_parsing import EXCEL_EXTENSIONS

from plugins.nsd_report_forms import bp
from plugins.nsd_report_forms.plugin import NSD_ADMIN_PERMISSION
from plugins.nsd_report_forms.importer import apply as importer_apply
from plugins.nsd_report_forms.importer import jobs, layout, workbook

IMPORT_KIND = "nsd_master"
_STAT_LABELS = {
    "projects_created": "Projects created",
    "projects_updated": "Projects updated",
    "profiles": "Profiles written",
    "skipped_no_national_society": "Skipped (no National Society)",
    "assignments_created": "Assignments created",
    "entities_created": "Entities created",
    "access_grants": "Access grants",
    "users_created": "Users created",
    "group_memberships": "Group memberships",
    "schedule_rows": "Schedule rows",
    "reports_skipped_existing": "Reports left as-is",
    "quarterly_reports": "Quarterly reports",
    "final_reports": "Final reports",
    "values": "Values written",
}

MAX_UPLOAD_BYTES = 40 * 1024 * 1024
_FILE_ID = re.compile(r'^[0-9a-f]{32}$')


def _upload_dir() -> Path:
    d = Path(current_app.instance_path) / 'nsd_import_uploads'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stored_path(file_id: str):
    if not file_id or not _FILE_ID.match(file_id):
        return None
    p = _upload_dir() / f'{file_id}.xlsx'
    return p if p.is_file() else None


def _meta_path(path: Path) -> Path:
    return path.with_name(path.stem + '.meta.json')


def _read_meta(path: Path) -> dict:
    meta_path = _meta_path(path)
    if not meta_path.is_file():
        return {}
    try:
        payload = json.loads(meta_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_meta(path: Path, filename: str, size: int) -> None:
    payload = {
        'filename': filename,
        'size': size,
        'uploaded_at': datetime.now(timezone.utc).isoformat(),
    }
    _meta_path(path).write_text(json.dumps(payload), encoding='utf-8')


def _display_name(path: Path) -> str:
    name = str(_read_meta(path).get('filename') or '').strip()
    # Older uploads were stored as a random id only. Don't show that id as the file name.
    return name or 'Uploaded workbook'


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if value < 1024 or unit == 'GB':
            if unit == 'B':
                return f'{int(value)} B'
            return f'{value:.1f} {unit}'
        value /= 1024
    return f'{size} B'


def _format_when(value) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    text = str(value or '')
    if len(text) >= 16 and text[10] == 'T':
        return text[:10] + ' ' + text[11:16] + ' UTC'
    if text:
        return text
    return '—'


def list_disk_files(limit: int = 12) -> list:
    """Uploaded master workbooks, newest first, with the original file name."""
    try:
        paths = [p for p in _upload_dir().glob('*.xlsx') if p.is_file() and _FILE_ID.match(p.stem)]
    except OSError:
        return []
    rows = []
    for path in paths:
        meta = _read_meta(path)
        try:
            stat = path.stat()
        except OSError:
            continue
        uploaded = meta.get('uploaded_at') or stat.st_mtime
        sort_key = uploaded if isinstance(uploaded, str) else datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        size = meta.get('size') if isinstance(meta.get('size'), int) else stat.st_size
        stored_name = str(meta.get('filename') or '').strip()
        rows.append({
            'name': stored_name or 'Uploaded workbook',
            'found': True,
            'size_label': _format_bytes(int(size or 0)),
            'modified_label': _format_when(uploaded),
            'note': 'Uploaded master workbook' if stored_name else 'Original file name was not stored with this upload',
            'file_id': path.stem,
            'kind': 'stored',
            '_sort': sort_key,
        })
    rows.sort(key=lambda row: row['_sort'], reverse=True)
    for row in rows:
        row.pop('_sort', None)
    return rows[:limit]


def import_history():
    try:
        runs = list_import_runs(IMPORT_KIND)
    except Exception:
        current_app.logger.exception('NSD import history could not be read')
        runs = []
    return runs, latest_import_run(runs)


def _preview_payload(path: Path, file_id: str, filename: str) -> dict:
    book = workbook.parse(str(path))
    result = {
        'success': True,
        'file_id': file_id,
        'filename': filename,
        'errors': book.errors,
        'warnings': book.warnings,
        'sheets': book.sheets_found,
    }
    if not book.errors:
        result['analysis'] = importer_apply.analyze(book)
    return result


@bp.route('/', methods=['GET'])
@admin_permission_required(NSD_ADMIN_PERMISSION)
def import_page():
    """Legacy URL — import UI lives on the plugin settings page."""
    return redirect(url_for('nsd_settings.settings_page', tab='import'))


@bp.route('/sample', methods=['GET'])
@admin_permission_required(NSD_ADMIN_PERMISSION)
def download_blank():
    """An empty workbook with the right sheets and column headers."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, cols in layout.SHEETS.items():
        ws = wb.create_sheet(name)
        for i, c in enumerate(cols, 1):
            h = ws.cell(row=1, column=i, value=c.name)
            h.font = Font(bold=True, color='FFFFFF')
            h.fill = PatternFill('solid', fgColor='DC3545' if c.required else '6C757D')
            ws.cell(row=2, column=i, value=c.help).font = Font(italic=True, color='6C757D', size=9)
            ws.column_dimensions[h.column_letter].width = 22
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name='NSD_master_import_blank.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@bp.route('/upload', methods=['POST'])
@admin_permission_required(NSD_ADMIN_PERMISSION)
def upload():
    f = request.files.get('file')
    if not f or not f.filename:
        return json_bad_request('No file selected')
    valid, error_msg, _ext = validate_upload_extension_and_mime(f, EXCEL_EXTENSIONS)
    if not valid:
        return json_bad_request(error_msg or 'Invalid file type')
    data = f.read()
    if len(data) > MAX_UPLOAD_BYTES:
        return json_bad_request('File too large (max 40 MB)')
    file_id = uuid.uuid4().hex
    path = _upload_dir() / f'{file_id}.xlsx'
    path.write_bytes(data)
    filename = secure_filename(f.filename) or 'workbook.xlsx'
    _write_meta(path, filename, len(data))
    return json_ok(**_preview_payload(path, file_id, filename))


@bp.route('/stored/<file_id>/check', methods=['POST'])
@admin_permission_required(NSD_ADMIN_PERMISSION)
def check_stored(file_id):
    """Re-check a workbook that is already stored on disk."""
    path = _stored_path(file_id)
    if path is None:
        return json_bad_request('Uploaded file not found. Please upload it again.')
    return json_ok(**_preview_payload(path, file_id, _display_name(path)))


@bp.route('/run', methods=['POST'])
@admin_permission_required(NSD_ADMIN_PERMISSION)
def run_import():
    data = get_json_safe()
    path = _stored_path(str(data.get('file_id') or ''))
    if path is None:
        return json_bad_request('Uploaded file not found. Please upload it again.')
    if jobs.any_running():
        return json_bad_request('Another NSD import is still running.')
    overwrite = bool(data.get('overwrite_reports', False))
    user_id = current_user.id
    app = current_app._get_current_object()
    filename = _display_name(path)
    log_id = uuid.uuid4().hex
    set_import_audit_details(
        log_id=log_id,
        import_kind=IMPORT_KIND,
        filename=filename,
        dry_run=False,
        extra={'source': 'Uploaded file'},
    )
    job_id = jobs.create(user_id)

    def work():
        with app.app_context():
            try:
                book = workbook.parse(str(path))
                if book.errors:
                    message = '; '.join(book.errors[:5])
                    _safe_publish(log_id, filename, success=False, summary=message, user_id=user_id)
                    jobs.update(job_id, state='failed', error=message, finished=_now(),
                                result={'change_log_url': change_log_url_for(log_id)})
                    return
                result = importer_apply.run(
                    book, user_id, overwrite,
                    progress=lambda done, total, cur: jobs.update(job_id, done=done, total=total, current=cur),
                    cancelled=lambda: jobs.is_cancelled(job_id))
                state = 'cancelled' if result.get('cancelled') else 'done'
                _safe_publish(
                    log_id, filename,
                    success=not result.get('failed') and state == 'done',
                    summary=_nsd_summary(result, state),
                    stats=result.get('stats') or {},
                    messages=result.get('messages') or [],
                    failed=result.get('failed') or 0,
                    user_id=user_id,
                )
                result['change_log_id'] = log_id
                result['change_log_url'] = change_log_url_for(log_id)
                jobs.update(job_id, state=state, result=result, finished=_now())
            except Exception as exc:  # report, never crash the worker silently
                current_app.logger.exception('NSD import failed')
                message = f'{type(exc).__name__}: {str(exc)[:300]}'
                _safe_publish(log_id, filename, success=False, summary=message, user_id=user_id)
                jobs.update(job_id, state='failed', error=message, finished=_now(),
                            result={'change_log_url': change_log_url_for(log_id)})
            finally:
                db.session.remove()

    threading.Thread(target=work, daemon=True, name=f'nsd-import-{job_id[:8]}').start()
    return json_ok(success=True, job_id=job_id)


def _now():
    import time
    return time.time()


def _nsd_summary(result: dict, state: str) -> str:
    stats = result.get('stats') or {}
    created = stats.get('projects_created', 0)
    updated = stats.get('projects_updated', 0)
    failed = result.get('failed') or 0
    if state == 'cancelled':
        lead = 'Import cancelled'
    elif failed:
        lead = f'Import finished with {failed} project(s) failed'
    else:
        lead = 'Import finished'
    return f'{lead}: {created} created, {updated} updated.'


def _safe_publish(log_id: str, filename: str, **kwargs) -> None:
    try:
        _publish_nsd_log(log_id, filename, **kwargs)
    except Exception:
        current_app.logger.exception('NSD import change log failed')


def _publish_nsd_log(
    log_id: str,
    filename: str,
    *,
    success: bool,
    summary: str,
    user_id: int,
    stats: dict | None = None,
    messages: list | None = None,
    failed: int = 0,
) -> None:
    stats = dict(stats or {})
    counts = [
        {'label': _STAT_LABELS.get(key, key.replace('_', ' ')), 'value': value}
        for key, value in stats.items()
    ]
    if failed:
        counts.append({'label': 'Projects failed', 'value': failed})
    changes = []
    for key, value in stats.items():
        changes.append({
            'op': 'count',
            'label': _STAT_LABELS.get(key, key.replace('_', ' ')),
            'new_value': value,
        })
    for message in (messages or [])[:40]:
        changes.append({'op': 'note', 'label': str(message), 'new_value': str(message)})
    publish_import_log(
        kind=IMPORT_KIND,
        log_id=log_id,
        filename=filename,
        source='upload',
        dry_run=False,
        success=success,
        summary=summary,
        counts=counts,
        changes=changes,
        stats={
            'inserted': stats.get('projects_created', 0),
            'updated': stats.get('projects_updated', 0),
            'skipped': stats.get('reports_skipped_existing', 0),
            'errors': failed,
            'success': success,
            'dry_run': False,
            'warnings': list(messages or [])[:40],
        },
        audit=False,
    )
    attach_import_change_log_to_activity(
        log_id=log_id,
        user_id=user_id,
        extra={'summary': summary, 'rows_errors': failed},
    )


@bp.route('/status/<job_id>', methods=['GET'])
@admin_permission_required(NSD_ADMIN_PERMISSION)
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return json_bad_request('Unknown job')
    job.pop('user_id', None)
    return json_ok(success=True, job=job)


@bp.route('/cancel/<job_id>', methods=['POST'])
@admin_permission_required(NSD_ADMIN_PERMISSION)
def cancel(job_id):
    if not jobs.get(job_id):
        return json_bad_request('Unknown job')
    jobs.request_cancel(job_id)
    return json_ok(success=True)
