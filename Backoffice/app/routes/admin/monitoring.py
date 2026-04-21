# File: Backoffice/app/routes/admin/monitoring.py
"""
System Monitoring Module - Memory logs and system monitoring
"""

from flask import Blueprint, render_template, request, current_app, send_file, abort, redirect, url_for, flash
from flask_login import current_user, login_required
from app.routes.admin.shared import admin_required, admin_permission_required
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_error, json_error_handler, json_not_found, json_ok, json_server_error
from app.utils.constants import MAX_LOG_ROTATION_KEEP_LINES, MAX_LOG_TAIL_LINES
from app.services.monitoring.memory import memory_monitor
from app.services.monitoring.system import system_monitor
from flask_babel import gettext as _
import os
import re
import io
from datetime import datetime
from contextlib import suppress

bp = Blueprint("monitoring", __name__, url_prefix="/admin")


@bp.route("/monitoring", methods=["GET"])
@admin_permission_required('admin.analytics.view')
def system_monitoring():
    """System monitoring dashboard with memory logs."""
    try:
        # Get memory log file path
        log_file_path = memory_monitor.get_log_file_path()

        # Check if memory monitoring is enabled
        memory_monitoring_enabled = current_app.config.get('MEMORY_MONITORING_ENABLED', False)

        # Get log file info
        log_file_exists = False
        log_file_size = 0
        log_file_modified = None

        if log_file_path and os.path.exists(log_file_path):
            log_file_exists = True
            log_file_size = os.path.getsize(log_file_path)
            log_file_modified = datetime.fromtimestamp(os.path.getmtime(log_file_path))

        # Get current memory usage
        current_memory = None
        if memory_monitoring_enabled:
            try:
                current_memory = memory_monitor.get_memory_usage()
            except Exception as e:
                current_app.logger.warning(f"Failed to get current memory usage: {e}")

        # Get system log file path
        system_log_file_path = system_monitor.get_log_file_path()
        system_monitoring_enabled = current_app.config.get('SYSTEM_MONITORING_ENABLED', False)

        # Get system log file info
        system_log_file_exists = False
        system_log_file_size = 0
        system_log_file_modified = None

        if system_log_file_path and os.path.exists(system_log_file_path):
            system_log_file_exists = True
            system_log_file_size = os.path.getsize(system_log_file_path)
            system_log_file_modified = datetime.fromtimestamp(os.path.getmtime(system_log_file_path))

        # Get application log file path (if enabled)
        application_log_file_path = getattr(current_app, 'application_log_file_path', None)
        application_log_enabled = current_app.config.get('APPLICATION_LOG_FILE_ENABLED', True)
        application_log_file_exists = False
        application_log_file_size = 0
        application_log_file_modified = None

        if application_log_file_path and os.path.exists(application_log_file_path):
            application_log_file_exists = True
            application_log_file_size = os.path.getsize(application_log_file_path)
            application_log_file_modified = datetime.fromtimestamp(os.path.getmtime(application_log_file_path))

        return render_template(
            "admin/monitoring/system_monitoring.html",
            title=_("System Monitoring"),
            memory_monitoring_enabled=memory_monitoring_enabled,
            system_monitoring_enabled=system_monitoring_enabled,
            log_file_path=log_file_path,
            log_file_exists=log_file_exists,
            log_file_size=log_file_size,
            log_file_modified=log_file_modified,
            system_log_file_path=system_log_file_path,
            system_log_file_exists=system_log_file_exists,
            system_log_file_size=system_log_file_size,
            system_log_file_modified=system_log_file_modified,
            application_log_file_path=application_log_file_path,
            application_log_enabled=application_log_enabled,
            application_log_file_exists=application_log_file_exists,
            application_log_file_size=application_log_file_size,
            application_log_file_modified=application_log_file_modified,
            current_memory=current_memory
        )
    except Exception as e:
        current_app.logger.error(f"Error loading system monitoring page: {e}", exc_info=True)
        return render_template(
            "admin/monitoring/system_monitoring.html",
            title=_("System Monitoring"),
            error=GENERIC_ERROR_MESSAGE
        )


def _read_log_file_tail(file_path, max_lines=None):
    """
    Efficiently read the last N lines from a log file.
    Uses reverse reading to avoid loading entire file into memory.
    """
    if max_lines is None:
        max_lines = MAX_LOG_TAIL_LINES
    try:
        file_size = os.path.getsize(file_path)
        # If file is small (< 1MB), read normally
        if file_size < 1024 * 1024:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return [line.strip() for line in f.readlines()[-max_lines:]]

        # For large files, read from end
        lines = []
        with open(file_path, 'rb') as f:
            # Seek to end
            f.seek(0, 2)
            file_size = f.tell()

            # Read in chunks from the end
            chunk_size = min(8192, file_size)
            position = file_size
            buffer = b''

            while len(lines) < max_lines and position > 0:
                # Calculate how much to read
                read_size = min(chunk_size, position)
                position -= read_size
                f.seek(position)

                # Read chunk
                chunk = f.read(read_size)
                buffer = chunk + buffer

                # Process complete lines
                while b'\n' in buffer and len(lines) < max_lines:
                    line, buffer = buffer.rsplit(b'\n', 1)
                    if line:
                        with suppress(Exception):
                            lines.insert(0, line.decode('utf-8', errors='ignore').strip())

                # If we've read the whole file, process remaining buffer
                if position == 0 and buffer:
                    with suppress(Exception):
                        lines.insert(0, buffer.decode('utf-8', errors='ignore').strip())
                    break

        return lines[-max_lines:]  # Return last max_lines

    except Exception as e:
        current_app.logger.error(f"Error reading log file {file_path}: {e}")
        return []


def _rotate_log_file_if_needed(file_path, max_size_mb=50):
    """
    Rotate log file if it exceeds max_size_mb.
    Keeps only the last 50% of the file.
    """
    try:
        if not os.path.exists(file_path):
            return

        file_size = os.path.getsize(file_path)
        max_size_bytes = max_size_mb * 1024 * 1024

        if file_size > max_size_bytes:
            current_app.logger.warning(f"Log file {file_path} exceeds {max_size_mb}MB ({file_size / 1024 / 1024:.2f}MB), rotating...")

            # Read last 50% of file
            lines_to_keep = _read_log_file_tail(file_path, max_lines=MAX_LOG_ROTATION_KEEP_LINES)

            # Write back only the last portion
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines_to_keep))
                if lines_to_keep:
                    f.write('\n')

            new_size = os.path.getsize(file_path)
            current_app.logger.info(f"Log file rotated: {file_size / 1024 / 1024:.2f}MB -> {new_size / 1024 / 1024:.2f}MB")

    except Exception as e:
        current_app.logger.error(f"Error rotating log file {file_path}: {e}")


@bp.route("/monitoring/logs", methods=["GET"])
@admin_permission_required('admin.analytics.view')
@json_error_handler('Read monitoring logs')
def get_monitoring_logs():
    """API endpoint to get all monitoring logs (memory + system) with pagination and filtering."""
    # Get all log file paths
    memory_log_path = memory_monitor.get_log_file_path()
    system_log_path = system_monitor.get_log_file_path()
    application_log_path = getattr(current_app, 'application_log_file_path', None)

    # Check if at least one log file exists
    memory_exists = memory_log_path and os.path.exists(memory_log_path)
    system_exists = system_log_path and os.path.exists(system_log_path)
    application_exists = application_log_path and os.path.exists(application_log_path)

    if not memory_exists and not system_exists and not application_exists:
        return json_not_found('No monitoring log files found. Monitoring may not be enabled.', success=False, error='No monitoring log files found. Monitoring may not be enabled.')

    # Rotate log files if they're too large (check max once per minute to avoid overhead)
    import time
    last_rotation_check = getattr(get_monitoring_logs, '_last_rotation_check', 0)
    current_time = time.time()
    if current_time - last_rotation_check > 60:  # Check at most once per minute
        if memory_exists:
            _rotate_log_file_if_needed(memory_log_path)
        if system_exists:
            _rotate_log_file_if_needed(system_log_path)
        if application_exists:
            _rotate_log_file_if_needed(application_log_path)
        get_monitoring_logs._last_rotation_check = current_time

    # Get query parameters
    from app.utils.api_pagination import validate_pagination_params
    page, per_page = validate_pagination_params(request.args, default_per_page=100, max_per_page=500)
    search = request.args.get('search', '').strip()
    log_source = request.args.get('log_source', 'all')  # all, memory, system, application
    log_level_param = request.args.get('log_level', 'all')  # comma-separated: error,warning,info,verbose or 'all'

    # Parse log levels - if 'all' or empty, include all levels
    if log_level_param == 'all' or not log_level_param:
        log_levels = ['error', 'warning', 'info', 'verbose']
    else:
        log_levels = [level.strip() for level in log_level_param.split(',') if level.strip()]

    # Limit max lines to read to prevent memory issues
    max_lines_to_read = 20000  # Read max 20k lines from each file

    # Read and combine log files (only tail of files)
    all_lines = []

    # Read memory logs (only tail)
    if memory_exists:
        memory_lines = _read_log_file_tail(memory_log_path, max_lines=max_lines_to_read)
        for line in memory_lines:
            if line:  # Skip empty lines
                all_lines.append(('memory', line))

    # Read system logs (only tail)
    if system_exists:
        system_lines = _read_log_file_tail(system_log_path, max_lines=max_lines_to_read)
        for line in system_lines:
            if line:  # Skip empty lines
                all_lines.append(('system', line))

    # Read application logs (only tail)
    if application_exists:
        application_lines = _read_log_file_tail(application_log_path, max_lines=max_lines_to_read)
        for line in application_lines:
            if line:  # Skip empty lines
                all_lines.append(('application', line))

    # Sort by timestamp (assuming log format: [YYYY-MM-DD HH:MM:SS] ...)
    def extract_timestamp(log_entry):
        log_type, line = log_entry
        timestamp_match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', line)
        if timestamp_match:
            try:
                return datetime.strptime(timestamp_match.group(1), '%Y-%m-%d %H:%M:%S')
            except Exception as e:
                current_app.logger.debug("log timestamp parse failed: %s", e)
                return datetime.min
        return datetime.min

    all_lines.sort(key=extract_timestamp, reverse=True)  # Newest first

    # Filter lines by log source and log level
    filtered_lines = []

    for log_type, line in all_lines:
        line_lower = line.lower()

        # Apply search filter
        if search and search.lower() not in line_lower:
            continue

        # Apply log source filter
        if log_source != 'all' and log_type != log_source:
            continue

        # Apply log level filter
        if log_levels:
            # Detect log level from the line using standardized patterns
            # Priority order: explicit Flask format > system log format > simple patterns

            # Pattern 1: Flask standard format: [timestamp] LEVELNAME in module: message
            flask_error = re.search(r'\]\s+ERROR\s+in\s+', line, re.IGNORECASE)
            flask_warning = re.search(r'\]\s+WARNING\s+in\s+', line, re.IGNORECASE)
            flask_info = re.search(r'\]\s+INFO\s+in\s+', line, re.IGNORECASE)
            flask_debug = re.search(r'\]\s+DEBUG\s+in\s+', line, re.IGNORECASE)

            # Pattern 2: System log format: [timestamp] LEVELNAME: message
            system_error = re.search(r'\]\s+ERROR\s*:', line, re.IGNORECASE)
            system_warning = re.search(r'\]\s+WARNING\s*:', line, re.IGNORECASE)
            system_info = re.search(r'\]\s+INFO\s*:', line, re.IGNORECASE)
            system_debug = re.search(r'\]\s+DEBUG\s*:', line, re.IGNORECASE)

            # Pattern 3: Simple patterns: LEVELNAME: (at start or after space/bracket)
            simple_error = re.search(r'(?:^|\s|\[)ERROR\s*:', line, re.IGNORECASE)
            simple_warning = re.search(r'(?:^|\s|\[)WARNING\s*:', line, re.IGNORECASE)
            simple_info = re.search(r'(?:^|\s|\[)INFO\s*:', line, re.IGNORECASE)
            simple_debug = re.search(r'(?:^|\s|\[)DEBUG\s*:', line, re.IGNORECASE)

            # Determine the actual log level of this line (priority: Flask > System > Simple)
            line_log_level = None

            if flask_error or system_error or simple_error:
                line_log_level = 'error'
            elif flask_warning or system_warning or simple_warning:
                line_log_level = 'warning'
            elif flask_info or system_info or simple_info:
                line_log_level = 'info'
            elif flask_debug or system_debug or simple_debug:
                line_log_level = 'verbose'  # Map DEBUG to verbose
            else:
                # Line has no explicit log level
                if log_type == 'memory' or log_type == 'system':
                    line_log_level = 'info'
                else:
                    line_log_level = 'verbose'

            # Check if the line's log level is in the selected levels
            if line_log_level not in log_levels:
                continue

        filtered_lines.append((log_type, line))

    # Extract just the log text for response (keep type for frontend)
    log_entries = [{'type': log_type, 'text': line} for log_type, line in filtered_lines]

    # Paginate
    total_lines = len(log_entries)
    total_pages = (total_lines + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_entries = log_entries[start_idx:end_idx]

    return json_ok(
        success=True,
        logs=[entry['text'] for entry in paginated_entries],
        log_types=[entry['type'] for entry in paginated_entries],
        pagination={
            'page': page,
            'per_page': per_page,
            'total': total_lines,
            'total_pages': total_pages
        }
    )



@bp.route("/monitoring/logs/download", methods=["GET"])
@admin_permission_required('admin.analytics.view')
def download_monitoring_logs():
    """Download monitoring logs (combined memory + system logs)."""
    try:
        memory_log_path = memory_monitor.get_log_file_path()
        system_log_path = system_monitor.get_log_file_path()

        memory_exists = memory_log_path and os.path.exists(memory_log_path)
        system_exists = system_log_path and os.path.exists(system_log_path)

        if not memory_exists and not system_exists:
            abort(404, description="No monitoring log files found")

        # Create combined log content
        combined_log = io.StringIO()

        combined_log.write("=" * 80 + "\n")
        combined_log.write("MONITORING LOGS - Combined Memory and System Logs\n")
        combined_log.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        combined_log.write("=" * 80 + "\n\n")

        if memory_exists:
            combined_log.write("=" * 80 + "\n")
            combined_log.write("MEMORY LOGS\n")
            combined_log.write("=" * 80 + "\n")
            with open(memory_log_path, 'r', encoding='utf-8') as f:
                combined_log.write(f.read())
            combined_log.write("\n\n")

        if system_exists:
            combined_log.write("=" * 80 + "\n")
            combined_log.write("SYSTEM LOGS\n")
            combined_log.write("=" * 80 + "\n")
            with open(system_log_path, 'r', encoding='utf-8') as f:
                combined_log.write(f.read())
            combined_log.write("\n")

        # Create BytesIO from string
        output = io.BytesIO()
        output.write(combined_log.getvalue().encode('utf-8'))
        output.seek(0)

        return send_file(
            output,
            mimetype='text/plain',
            as_attachment=True,
            download_name=f'monitoring_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
        )

    except Exception as e:
        current_app.logger.error(f"Error downloading monitoring logs: {e}", exc_info=True)
        abort(500, description="An error occurred.")


@bp.route("/monitoring/logs/clear", methods=["POST"])
@admin_permission_required('admin.analytics.view')
@json_error_handler('Clear monitoring logs')
def clear_monitoring_logs():
    """Clear all monitoring log files (memory + system + application)."""
    memory_log_path = memory_monitor.get_log_file_path()
    system_log_path = system_monitor.get_log_file_path()
    application_log_path = getattr(current_app, 'application_log_file_path', None)

    cleared_files = []

    # Clear memory log
    if memory_log_path and os.path.exists(memory_log_path):
        with open(memory_log_path, 'w', encoding='utf-8') as f:
            f.write('')
        cleared_files.append('memory')

    # Clear system log
    if system_log_path and os.path.exists(system_log_path):
        with open(system_log_path, 'w', encoding='utf-8') as f:
            f.write('')
        cleared_files.append('system')

    # Clear application log
    if application_log_path and os.path.exists(application_log_path):
        with open(application_log_path, 'w', encoding='utf-8') as f:
            f.write('')
        cleared_files.append('application')

    if cleared_files:
        current_app.logger.info(f"Monitoring log files cleared by {current_user.email}: {', '.join(cleared_files)}")
        return json_ok(
            success=True,
            message=f'All monitoring log files cleared successfully ({", ".join(cleared_files)})'
        )
    else:
        return json_not_found('No log files found to clear', success=False, error='No log files found to clear')


@bp.route("/monitoring/memory/current", methods=["GET"])
@admin_permission_required('admin.analytics.view')
@json_error_handler('Get current memory')
def get_current_memory():
    """API endpoint to get current memory usage."""
    if not current_app.config.get('MEMORY_MONITORING_ENABLED', False):
        return json_error('Memory monitoring is not enabled', 400, success=False, error='Memory monitoring is not enabled')

    memory = memory_monitor.get_memory_usage()
    top_allocations = memory_monitor.get_top_memory_allocations(limit=10)

    return json_ok(success=True, memory=memory, top_allocations=top_allocations)


@bp.route("/monitoring/system/current", methods=["GET"])
@admin_permission_required('admin.analytics.view')
@json_error_handler('Get system metrics')
def get_current_system_metrics():
    """API endpoint to get current system metrics."""
    if not current_app.config.get('SYSTEM_MONITORING_ENABLED', False):
        return json_error('System monitoring is not enabled', 400, success=False, error='System monitoring is not enabled')

    metrics = system_monitor.get_system_metrics()

    return json_ok(success=True, metrics=metrics)


@bp.route("/monitoring/system/logs", methods=["GET"])
@admin_permission_required('admin.analytics.view')
@json_error_handler('Read system logs')
def get_system_logs():
    """API endpoint to get system logs with pagination and filtering."""
    log_file_path = system_monitor.get_log_file_path()

    if not log_file_path or not os.path.exists(log_file_path):
        return json_not_found(
            'System log file not found. System monitoring may not be enabled.',
            success=False,
            error='System log file not found. System monitoring may not be enabled.'
        )

    # Get query parameters
    from app.utils.api_pagination import validate_pagination_params
    page, per_page = validate_pagination_params(request.args, default_per_page=100, max_per_page=500)
    search = request.args.get('search', '').strip()

    # Read log file
    with open(log_file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Filter lines
    filtered_lines = []
    for line in lines:
        line_lower = line.lower()

        # Apply search filter
        if search and search.lower() not in line_lower:
            continue

        filtered_lines.append(line.strip())

    # Reverse to show newest first
    filtered_lines.reverse()

    # Paginate
    total_lines = len(filtered_lines)
    total_pages = (total_lines + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_lines = filtered_lines[start_idx:end_idx]

    return json_ok(
        success=True,
        logs=paginated_lines,
        pagination={
            'page': page,
            'per_page': per_page,
            'total': total_lines,
            'total_pages': total_pages
        }
    )


@bp.route("/monitoring/test-error", methods=["GET", "POST"])
@admin_permission_required('admin.analytics.view')
def test_error_notification():
    """
    Test endpoint to trigger error notification and verify system manager alerts.

    This endpoint tests the system manager notification system by directly
    calling the notification logic, bypassing the DEBUG mode check so it
    can be tested on localhost.

    WARNING: This will send actual email notifications to system managers.
    Only use this for testing the notification system.
    """
    from app.services.security.monitoring import SecurityMonitor
    from app.services.email.service import send_security_alert
    from app.models import User
    from app.utils.datetime_helpers import utcnow

    try:
        from app.models.rbac import RbacUserRole, RbacRole
    except ImportError:
        RbacUserRole = None
        RbacRole = None

    # Get request method to determine response format
    from app.utils.request_utils import is_json_request
    is_json = is_json_request() or request.args.get('format') == 'json'

    # Create test error message
    error_message = (
        f"TEST ERROR: This is a test error triggered by {current_user.email if current_user.is_authenticated else 'unknown user'} "
        f"at {datetime.now().isoformat()} to verify system manager error notification system."
    )
    error_url = request.url
    user_id = current_user.id if current_user.is_authenticated else None
    ip_address = request.remote_addr if request else 'Unknown'

    # Create security event for test error
    try:
        SecurityMonitor.log_security_event(
            event_type='internal_server_error',
            severity='critical',
            description=f'Test Error Notification: {error_message[:200]}',
            context_data={
                'url': error_url,
                'endpoint': request.endpoint if request else None,
                'method': request.method if request else None,
                'is_test': True
            },
            user_id=user_id
        )
    except Exception as e:
        current_app.logger.error(f"Failed to log test security event: {e}", exc_info=True)

    # Send email alert to system managers (bypassing DEBUG check for testing)
    email_sent = False
    manager_emails = []

    try:
        # Get all system managers (RBAC-only)
        if RbacUserRole and RbacRole:
            managers = (
                User.query.join(RbacUserRole, User.id == RbacUserRole.user_id)
                .join(RbacRole, RbacUserRole.role_id == RbacRole.id)
                .filter(RbacRole.code == "system_manager")
                .filter(User.active.is_(True))
                .all()
            )
        else:
            managers = []

        if managers:
            manager_emails = [m.email for m in managers if m.email]
            if manager_emails:
                # Send to system managers found in database
                success = send_security_alert(
                    event_type='internal_server_error',
                    severity='critical',
                    description=f'Test Error Notification: {error_message[:200]}',
                    ip_address=ip_address,
                    user_id=user_id,
                    timestamp=utcnow().isoformat(),
                    recipients=manager_emails
                )
                if success:
                    email_sent = True
                    current_app.logger.info(f"Test security alert sent to {len(manager_emails)} system managers: {', '.join(manager_emails)}")
                else:
                    current_app.logger.error(f"Failed to send test security alert to system managers: {manager_emails}")
            else:
                current_app.logger.warning("System managers found but none have email addresses configured")
        else:
            current_app.logger.warning("No active system managers found in database for error notification")
    except Exception as email_error:
        current_app.logger.error(f"Failed to send test error notification email: {email_error}", exc_info=True)

    # After sending notification, raise an exception to trigger 500 error handler
    # This simulates a real server error and shows the error page
    # Note: The notification was already sent above (bypassing DEBUG check),
    # so even if DEBUG=True, the email was sent. The 500 handler won't send
    # another email in DEBUG mode, but that's fine since we already sent it.
    raise Exception(error_message)
