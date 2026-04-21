import os
import re
from flask import current_app


def _abs(path: str) -> str:
    return os.path.abspath(path or '')


def get_upload_base_path() -> str:
    """Return absolute uploads base directory from config."""
    base = current_app.config.get('UPLOAD_FOLDER', 'uploads')
    return _abs(base)


def get_resource_upload_path() -> str:
    """Return absolute resources root under uploads."""
    return _abs(os.path.join(get_upload_base_path(), 'resources'))


def get_admin_documents_upload_path() -> str:
    """Return absolute admin documents root under uploads."""
    return _abs(os.path.join(get_upload_base_path(), 'admin_documents'))


def get_submissions_upload_path() -> str:
    """Return absolute submissions root under uploads."""
    return _abs(os.path.join(get_upload_base_path(), 'submissions'))


def get_system_upload_path() -> str:
    """Return absolute system files root under uploads."""
    return _abs(os.path.join(get_upload_base_path(), 'system'))


def get_sector_logo_path() -> str:
    """Return absolute path for sector logos."""
    return _abs(os.path.join(get_system_upload_path(), 'sectors'))


def get_subsector_logo_path() -> str:
    """Return absolute path for subsector logos."""
    return _abs(os.path.join(get_system_upload_path(), 'subsectors'))


def get_temp_upload_path() -> str:
    """Return absolute path for temporary files."""
    return _abs(os.path.join(get_upload_base_path(), 'temp'))


def get_plugin_upload_path(plugin_name: str) -> str:
    """Return absolute path for plugin-specific uploads.

    Args:
        plugin_name: The name of the plugin

    Returns:
        Absolute path to the plugin's upload directory
    """
    base = _abs(os.path.join(get_upload_base_path(), 'plugins'))
    return _abs(os.path.join(base, plugin_name))


_WINDOWS_DRIVE_PREFIX = re.compile(r'^[A-Za-z]:[\\/]')


def normalize_stored_relative_path(value: str, root_folder: str | None = None) -> str:
    """Normalize a stored relative path to a consistent forward-slash form.
    - Strips Windows drive prefixes
    - Converts backslashes to forward slashes
    - Trims leading slashes
    - If root_folder is provided, strips any leading '<root_folder>/' prefix
    """
    rel = (value or '').strip()
    if _WINDOWS_DRIVE_PREFIX.match(rel):
        rel = os.path.basename(rel)
    rel = rel.replace('\\', '/').strip('/')
    if root_folder:
        prefix = f"{root_folder.strip('/')}/"
        if rel.startswith(prefix):
            rel = rel[len(prefix):]
    return rel


def resolve_under(base_dir: str, rel_path: str) -> str:
    """Resolve a relative path under a base dir and ensure it stays under base.
    Returns the absolute resolved path. Does not check file existence.
    """
    safe_rel = normalize_stored_relative_path(rel_path)
    candidate = _abs(os.path.join(base_dir, *([p for p in safe_rel.split('/') if p])))
    base_real = os.path.realpath(base_dir)
    cand_real = os.path.realpath(candidate)
    if not cand_real.startswith(base_real + os.sep) and cand_real != base_real:
        raise PermissionError('Resolved path escapes base directory')
    return cand_real


# Convenience resolvers for resources
def resolve_resource_file(rel_path: str) -> str:
    return resolve_under(get_resource_upload_path(), normalize_stored_relative_path(rel_path))


def resolve_resource_thumbnail(rel_path: str) -> str:
    rel = normalize_stored_relative_path(rel_path)
    # Thumbnails live anywhere under resources root; caller controls subfolder
    return resolve_under(get_resource_upload_path(), rel)


# Convenience resolvers for admin documents
def resolve_admin_document(rel_path: str) -> str:
    return resolve_under(get_admin_documents_upload_path(), normalize_stored_relative_path(rel_path))


def resolve_admin_document_thumbnail(rel_path: str) -> str:
    rel = normalize_stored_relative_path(rel_path)
    return resolve_under(get_admin_documents_upload_path(), rel)


# Convenience resolvers for submissions
def resolve_submission_file(rel_path: str) -> str:
    """Resolve a path under the legacy ``uploads/submissions/`` tree only.

    Prefer :func:`resolve_submitted_document_file` for ``SubmittedDocument.storage_path`` values,
    which may live at upload root (entity repo) or under ``submissions/``.
    """
    return resolve_under(get_submissions_upload_path(), normalize_stored_relative_path(rel_path))


def resolve_submitted_document_file(rel_path: str) -> str:
    """Resolve ``SubmittedDocument`` storage_path to an absolute filesystem path (local provider)."""
    from app.services import storage_service as ss

    rel = normalize_stored_relative_path(rel_path)
    cat = ss.submitted_document_rel_storage_category(rel)
    if cat == ss.SUBMISSIONS:
        return resolve_under(get_submissions_upload_path(), rel)
    if cat == ss.ENTITY_REPO_ROOT:
        return resolve_under(get_upload_base_path(), rel)
    return resolve_admin_document(rel)


# Convenience resolvers for system files
def resolve_sector_logo(filename: str) -> str:
    """Resolve a sector logo filename to absolute path."""
    return resolve_under(get_sector_logo_path(), normalize_stored_relative_path(filename))


def resolve_subsector_logo(filename: str) -> str:
    """Resolve a subsector logo filename to absolute path."""
    return resolve_under(get_subsector_logo_path(), normalize_stored_relative_path(filename))


def resolve_temp_file(rel_path: str) -> str:
    """Resolve a relative path to a temporary file."""
    return resolve_under(get_temp_upload_path(), normalize_stored_relative_path(rel_path))


def resolve_plugin_file(plugin_name: str, rel_path: str) -> str:
    """Resolve a relative path to a plugin file."""
    base = get_plugin_upload_path(plugin_name)
    return resolve_under(base, normalize_stored_relative_path(rel_path))


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def secure_join_filename(folder_rel: str | None, filename: str) -> str:
    """Join a folder (relative) and filename safely (no traversal), return forward-slash rel."""
    name = os.path.basename(filename)
    rel_folder = normalize_stored_relative_path(folder_rel or '')
    if rel_folder:
        return f"{rel_folder}/{name}"
    return name


def save_submission_document(
    file_storage,
    assignment_id: int,
    filename: str,
    is_public: bool = False,
    form_id: int = None,
    submission_id: int = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
) -> str:
    """Save a submission document and return path relative to ``UPLOAD_FOLDER`` (entity repo root).

    *entity_type* and *entity_id* are required. Paths (no ``submissions/`` or ``assignments/`` segments).
    ``form_item_id`` is not part of the path (it lives on ``SubmittedDocument``; filenames are UUID-suffixed).

    * Assignments: ``{type}/{id}/{aes_id}/…``
    * Public: ``{type}/{id}/public/{form_id}/{submission_id}/…``

    Args:
        file_storage: The file storage object from Flask request
        assignment_id: Assignment entity status ID (AES id) for non-public submissions (ignored when ``is_public``)
        filename: The secured filename
        is_public: Whether this is a public submission
        form_id: Assigned form ID (required if is_public=True)
        submission_id: Public submission ID (required if is_public=True)
        entity_type: Entity slug (e.g. ``country``)
        entity_id: Entity primary key
    """
    from app.services import storage_service as _ss

    if entity_type is None or entity_id is None:
        raise ValueError("entity_type and entity_id are required for submission document storage")
    try:
        et = _ss.normalize_standalone_entity_type_slug(str(entity_type))
        eid = int(entity_id)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid entity_type or entity_id for submission document storage") from exc

    if is_public:
        if form_id is None or submission_id is None:
            raise ValueError("form_id and submission_id are required for public submissions")
        rel_prefix = f"{et}/{eid}/public/{int(form_id)}/{int(submission_id)}"
    else:
        rel_prefix = f"{et}/{eid}/{int(assignment_id)}"

    import uuid
    name, ext = os.path.splitext(os.path.basename(filename))
    unique_filename = f"{name}_{uuid.uuid4().hex[:8]}{ext}"

    full_rel = f"{rel_prefix}/{unique_filename}"
    saved_rel = _ss.upload(_ss.ENTITY_REPO_ROOT, full_rel, file_storage)
    return saved_rel


_ALLOWED_LOGO_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
_MAX_LOGO_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


def save_system_logo(file_storage, item_name: str, item_type: str, is_sector: bool = True) -> str:
    """Save a system logo (sector or subsector) and return the filename.

    Args:
        file_storage: The file storage object from Flask request
        item_name: The name of the item (for filename generation)
        item_type: The type of item (e.g., 'sector', 'subsector')
        is_sector: True for sector, False for subsector

    Returns:
        The saved filename (relative to the logo directory)

    Raises:
        ValueError: If the file type is not allowed or file is too large.
    """
    import uuid
    from werkzeug.utils import secure_filename

    if not file_storage or not file_storage.filename:
        return None

    filename = secure_filename(file_storage.filename)
    name, ext = os.path.splitext(filename)

    if ext.lower() not in _ALLOWED_LOGO_EXTENSIONS:
        raise ValueError(
            f"Logo file type '{ext}' is not allowed. "
            f"Allowed: {', '.join(sorted(_ALLOWED_LOGO_EXTENSIONS))}"
        )

    file_storage.seek(0, 2)
    file_size = file_storage.tell()
    file_storage.seek(0)
    if file_size > _MAX_LOGO_SIZE_BYTES:
        raise ValueError(
            f"Logo file is too large ({file_size // 1024}KB). Maximum size is {_MAX_LOGO_SIZE_BYTES // (1024*1024)}MB."
        )

    unique_filename = f"{secure_filename(item_name)}_{item_type}_{uuid.uuid4().hex[:8]}{ext}"

    from app.services import storage_service as _ss
    sub = "sectors" if is_sector else "subsectors"
    _ss.upload(_ss.SYSTEM, f"{sub}/{unique_filename}", file_storage)
    return unique_filename
