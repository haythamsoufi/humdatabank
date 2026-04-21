from flask import Blueprint, render_template, request
from sqlalchemy import func, case
from datetime import datetime, timedelta
from app.models.api_usage import APIUsage
from app.models import IndicatorBank, Sector, SubSector, FormTemplate, Country, User
from app import db
from app.routes.admin.shared import admin_permission_required
from flask import current_app
from app.utils.datetime_helpers import utcnow
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_ok, json_server_error
from app.utils.sql_utils import safe_ilike_pattern

bp = Blueprint('api_management', __name__, url_prefix='/admin')

# ---------------------------------------------------------------------------
# Unified Endpoint Registry
# Canonical source of truth for every API surface in the system.
#
# surface values:
#   'v1'     – External data API  (/api/v1/*)
#   'mobile' – Flutter mobile API (/api/mobile/v1/*)
#   'ai'     – AI chat + documents (/api/ai/v2/* and /api/ai/documents/*)
#
# auth values (consistent vocabulary across surfaces):
#   'public'             – no auth required
#   'api_key'            – @require_api_key (Bearer: DB api_keys row, or MOBILE_APP_API_KEY env if no row)
#   'api_key_or_session' – @require_api_key_or_session or runtime authenticate_api_request()
#   'session'            – @login_required (Flask-Login session)
#   'ai_session'         – resolve_ai_identity() (session or AI Bearer JWT)
#   'user'               – @mobile_auth_required (mobile JWT or session)
#   'rbac'               – @mobile_auth_required(permission=…)
#
# flag types:
#   'mismatch'  – client calls endpoint with wrong auth mode
#   'contract'  – API payload contract broken (client ≠ server expectations)
#   'bug'       – server-side code bug on this endpoint
#   'policy'    – authorization policy inconsistency
#   'unused'    – endpoint defined/registered but not called by any consumer
#   'minor'     – low-priority improvement opportunity
# ---------------------------------------------------------------------------

# ── External Data API  /api/v1/* ─────────────────────────────────────────────
EXTERNAL_API_REGISTRY = [
    # ── Submissions ───────────────────────────────────────────────────────────
    {'group': 'Submissions', 'path': '/api/v1/submissions', 'methods': ['GET'],
     'auth': 'api_key_or_session', 'rate_limited': False,
     'description': 'List submissions; API key gets paginated view, session/Basic returns all accessible',
     'consumers': 'External integrations'},
    {'group': 'Submissions', 'path': '/api/v1/submissions/<submission_id>', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Full detail for one assigned or public submission'},

    # ── Form Templates & Items ─────────────────────────────────────────────────
    {'group': 'Templates & Form Items', 'path': '/api/v1/templates', 'methods': ['GET'],
     'auth': 'api_key_or_session', 'rate_limited': False,
     'description': 'Template list; pagination differs by auth type'},
    {'group': 'Templates & Form Items', 'path': '/api/v1/templates/<template_id>', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Full template structure (pages, sections, items)'},
    {'group': 'Templates & Form Items', 'path': '/api/v1/templates/<template_id>/data', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Paginated form data for one template'},
    {'group': 'Templates & Form Items', 'path': '/api/v1/form-items', 'methods': ['GET'],
     'auth': 'api_key_or_session', 'rate_limited': False,
     'description': 'Form items listing with optional filters'},
    {'group': 'Templates & Form Items', 'path': '/api/v1/form-items/<item_id>', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Single form item detail'},
    {'group': 'Templates & Form Items', 'path': '/api/v1/lookup-lists', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Paginated lookup lists used for dynamic field options'},
    {'group': 'Templates & Form Items', 'path': '/api/v1/lookup-lists/<list_id>', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Lookup list detail with all rows'},
    {'group': 'Templates & Form Items', 'path': '/api/v1/assigned-forms', 'methods': ['GET'],
     'auth': 'api_key_or_session', 'rate_limited': True,
     'description': 'Assigned form IDs and their associated country IDs'},

    # ── Form Data ──────────────────────────────────────────────────────────────
    {'group': 'Form Data', 'path': '/api/v1/data', 'methods': ['GET'],
     'auth': 'api_key_or_session', 'rate_limited': True, 'featured': True,
     'description': 'Filtered form data rows; API key paginates, session/Basic returns all accessible'},
    {'group': 'Form Data', 'path': '/api/v1/data/tables', 'methods': ['GET'],
     'auth': 'api_key_or_session', 'rate_limited': False, 'featured': True,
     'description': 'Denormalised data rows + related form_items and countries tables in one response'},
    {'group': 'Form Data', 'path': '/api/v1/countries/<country_id>/data', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Paginated form data scoped to one country'},

    # ── Countries & Geography ──────────────────────────────────────────────────
    {'group': 'Countries & Geography', 'path': '/api/v1/countrymap', 'methods': ['GET'],
     'auth': 'api_key_or_session', 'rate_limited': True,
     'description': 'Country list/map payload with optional locale, filters, and pagination',
     'overlaps': ['/api/mobile/v1/data/countrymap']},
    {'group': 'Countries & Geography', 'path': '/api/v1/nationalsocietymap', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'National societies list with optional locale, filters, and pagination'},
    {'group': 'Countries & Geography', 'path': '/api/v1/periods', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Distinct period names from assigned and public data'},

    # ── Indicator Bank ─────────────────────────────────────────────────────────
    {'group': 'Indicator Bank', 'path': '/api/v1/indicator-bank', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Indicator bank listing with filters and pagination',
     'overlaps': ['/api/mobile/v1/data/indicator-bank']},
    {'group': 'Indicator Bank', 'path': '/api/v1/indicator-bank/<indicator_id>', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Single indicator detail by ID',
     'overlaps': ['/api/mobile/v1/data/indicator-bank/<indicator_id>']},
    {'group': 'Indicator Bank', 'path': '/api/v1/indicator-suggestions', 'methods': ['GET', 'POST'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'List or submit indicator suggestions',
     'overlaps': ['/api/mobile/v1/data/indicator-suggestions']},
    {'group': 'Indicator Bank', 'path': '/api/v1/indicator-suggestions/<suggestion_id>', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Single suggestion detail'},
    {'group': 'Indicator Bank', 'path': '/api/v1/indicator-suggestions/<suggestion_id>/status', 'methods': ['PUT'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Update suggestion status (approve, reject, etc.)'},

    # ── Sectors ────────────────────────────────────────────────────────────────
    {'group': 'Sectors', 'path': '/api/v1/sectors', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Active sectors list'},
    {'group': 'Sectors', 'path': '/api/v1/subsectors', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Active subsectors list'},
    {'group': 'Sectors', 'path': '/api/v1/sectors-subsectors', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Combined sectors + nested subsectors payload',
     'overlaps': ['/api/mobile/v1/data/sectors-subsectors']},

    # ── Users ──────────────────────────────────────────────────────────────────
    {'group': 'Users', 'path': '/api/v1/users', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Paginated user directory with optional role/search filters'},
    {'group': 'Users', 'path': '/api/v1/users/<user_id>', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Single user detail'},
    {'group': 'Users', 'path': '/api/v1/user/profile', 'methods': ['GET', 'PUT', 'PATCH'],
     'auth': 'session', 'rate_limited': False,
     'description': 'Current user profile — read or update (session only)'},
    {'group': 'Users', 'path': '/api/v1/dashboard', 'methods': ['GET'],
     'auth': 'session', 'rate_limited': False,
     'description': 'Session user dashboard (assignments, entities, notifications)'},

    # ── Documents & Resources ──────────────────────────────────────────────────
    {'group': 'Documents & Resources', 'path': '/api/v1/submitted-documents', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Paginated submitted documents with country, type, language, status filters'},
    {'group': 'Documents & Resources', 'path': '/api/v1/resources', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Resources library with pagination and filters',
     'overlaps': ['/api/mobile/v1/data/resources']},
    {'group': 'Documents & Resources', 'path': '/api/v1/uploads/sectors/<filename>', 'methods': ['GET'],
     'auth': 'public', 'rate_limited': False,
     'description': 'Stream a sector logo file from system storage'},
    {'group': 'Documents & Resources', 'path': '/api/v1/uploads/subsectors/<filename>', 'methods': ['GET'],
     'auth': 'public', 'rate_limited': False,
     'description': 'Stream a subsector logo file from system storage'},

    # ── Quiz ───────────────────────────────────────────────────────────────────
    {'group': 'Quiz', 'path': '/api/v1/quiz/leaderboard', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Top users by quiz score',
     'overlaps': ['/api/mobile/v1/data/quiz/leaderboard']},
    {'group': 'Quiz', 'path': '/api/v1/quiz/submit-score', 'methods': ['POST'],
     'auth': 'session', 'rate_limited': False,
     'description': 'Add score to the current user (session only)'},

    # ── System ─────────────────────────────────────────────────────────────────
    {'group': 'System', 'path': '/api/v1/csrf-token', 'methods': ['GET'],
     'auth': 'session', 'rate_limited': False,
     'description': 'Issue a CSRF token for session-backed clients (e.g. mobile session mode)'},
    {'group': 'System', 'path': '/api/v1/common-words', 'methods': ['GET'],
     'auth': 'api_key', 'rate_limited': True,
     'description': 'Active common words / tooltip glossary for a language'},
    {'group': 'System', 'path': '/api/v1/variables/resolve', 'methods': ['POST'],
     'auth': 'session', 'rate_limited': False,
     'description': 'Resolve template variable expressions for the logged-in user'},
    {'group': 'System', 'path': '/api/v1/matrix/auto-load-entities', 'methods': ['POST'],
     'auth': 'session', 'rate_limited': False,
     'description': 'Resolve matrix auto-load entity IDs for a saved context (template/period/item/AES)'},
    {'group': 'System', 'path': '/api/v1/platform-error', 'methods': ['POST'],
     'auth': 'public', 'rate_limited': True,
     'description': 'Accept JSON from static error pages (403/502/503) to log platform events'},
]

# ── AI Chat API  /api/ai/v2/* ─────────────────────────────────────────────────
AI_API_REGISTRY = [
    # ── Chat ──────────────────────────────────────────────────────────────────
    {'group': 'Chat', 'path': '/api/ai/v2/chat', 'methods': ['POST'],
     'auth': 'ai_session', 'rate_limited': True,
     'description': 'Non-streaming chat request; anonymous allowed if Website proxy secret matches',
     'consumers': 'Backoffice, Website, Mobile'},
    {'group': 'Chat', 'path': '/api/ai/v2/chat/stream', 'methods': ['POST'],
     'auth': 'ai_session', 'rate_limited': True,
     'description': 'SSE streaming chat; same identity and proxy rules as /chat',
     'consumers': 'Backoffice, Website, Mobile'},
    {'group': 'Chat', 'path': '/api/ai/v2/chat/cancel', 'methods': ['POST'],
     'auth': 'ai_session', 'rate_limited': True,
     'description': 'Signal SSE stream cancellation by request_id'},
    {'group': 'Chat', 'path': '/api/ai/v2/ws', 'methods': ['WS'],
     'auth': 'ai_session', 'rate_limited': True,
     'description': 'WebSocket streaming chat (requires flask-sock)',
     'consumers': 'Backoffice, Mobile'},
    {'group': 'Chat', 'path': '/api/ai/v2/feedback', 'methods': ['POST'],
     'auth': 'ai_session', 'rate_limited': True,
     'description': 'Submit like/dislike feedback on a reasoning trace'},

    # ── Conversations ──────────────────────────────────────────────────────────
    {'group': 'Conversations', 'path': '/api/ai/v2/conversations', 'methods': ['GET', 'DELETE'],
     'auth': 'ai_session', 'rate_limited': True,
     'description': 'List current user conversations (GET) or delete all (DELETE, requires confirm param)'},
    {'group': 'Conversations', 'path': '/api/ai/v2/conversations/<conversation_id>', 'methods': ['GET', 'DELETE'],
     'auth': 'ai_session', 'rate_limited': False,
     'description': 'Get messages for a conversation (GET) or delete it entirely (DELETE)'},
    {'group': 'Conversations', 'path': '/api/ai/v2/conversations/<conversation_id>/clear-inflight', 'methods': ['POST'],
     'auth': 'ai_session', 'rate_limited': True,
     'description': 'Clear stale inflight metadata on a conversation'},
    {'group': 'Conversations', 'path': '/api/ai/v2/conversations/<conversation_id>/export', 'methods': ['GET'],
     'auth': 'ai_session', 'rate_limited': True,
     'description': 'Download conversation history as JSON export'},
    {'group': 'Conversations', 'path': '/api/ai/v2/conversations/<conversation_id>/messages', 'methods': ['POST'],
     'auth': 'ai_session', 'rate_limited': True,
     'description': 'Append a persisted message to a conversation (e.g. client-side errors)'},
    {'group': 'Conversations', 'path': '/api/ai/v2/conversations/<conversation_id>/import', 'methods': ['POST'],
     'auth': 'ai_session', 'rate_limited': True,
     'description': 'Bulk-import client-side message history (e.g. mobile offline sync)'},

    # ── Tools & Tokens ────────────────────────────────────────────────────────
    {'group': 'Tools & Tokens', 'path': '/api/ai/v2/table/export', 'methods': ['POST'],
     'auth': 'ai_session', 'rate_limited': True,
     'description': 'Build and return Excel file from AI chat table rows'},
    {'group': 'Tools & Tokens', 'path': '/api/ai/v2/token', 'methods': ['GET'],
     'auth': 'session', 'rate_limited': False,
     'description': 'Issue short-lived AI JWT for Website / Mobile clients (@login_required)',
     'consumers': 'Website, Mobile (AiChatService)'},
    {'group': 'Tools & Tokens', 'path': '/api/ai/v2/health', 'methods': ['GET'],
     'auth': 'public', 'rate_limited': False,
     'description': 'AI stack health check (optional ?probe=embedding for RAG status)'},
]

# ── AI Documents / RAG API  /api/ai/documents/* ───────────────────────────────
# Flask-Login session (not the /api/ai/v2 chat JWT). Variable names MUST match
# url_map so the live scanner treats these as documented.
AI_DOCUMENTS_API_REGISTRY = [
    {'group': 'Documents (RAG)', 'path': '/api/ai/documents/upload', 'methods': ['POST'],
     'auth': 'session', 'rate_limited': True,
     'description': 'Multipart upload; requires admin.documents.manage'},
    {'group': 'Documents (RAG)', 'path': '/api/ai/documents/<document_id>/reprocess', 'methods': ['POST'],
     'auth': 'session', 'rate_limited': True,
     'description': 'Re-chunk and re-embed an existing document'},
    {'group': 'Documents (RAG)', 'path': '/api/ai/documents/', 'methods': ['GET'],
     'auth': 'session', 'rate_limited': False,
     'description': 'Paginated list of AI documents visible to the current user'},
    {'group': 'Documents (RAG)', 'path': '/api/ai/documents/<document_id>', 'methods': ['GET', 'PATCH', 'DELETE'],
     'auth': 'session', 'rate_limited': True,
     'description': 'Get metadata (optional include_chunks), update fields, or delete document + embeddings'},
    {'group': 'Documents (RAG)', 'path': '/api/ai/documents/<document_id>/download', 'methods': ['GET'],
     'auth': 'session', 'rate_limited': False,
     'description': 'Download original file or redirect to trusted source_url'},
    {'group': 'Documents (RAG)', 'path': '/api/ai/documents/search', 'methods': ['POST'],
     'auth': 'session', 'rate_limited': True,
     'description': 'Vector / hybrid similarity search over embedded chunks'},
    {'group': 'Documents (RAG)', 'path': '/api/ai/documents/answer', 'methods': ['POST'],
     'auth': 'session', 'rate_limited': True,
     'description': 'Document-grounded Q&A (RAG) over the user-visible corpus'},
    {'group': 'Documents (RAG)', 'path': '/api/ai/documents/ws', 'methods': ['GET'],
     'auth': 'session', 'rate_limited': False,
     'description': 'WebSocket stream for document QA (requires admin.ai.manage when enabled)'},

    {'group': 'Workflow docs', 'path': '/api/ai/documents/workflows/sync', 'methods': ['POST'],
     'auth': 'session', 'rate_limited': False,
     'description': 'Admin: re-index workflow markdown from disk into the vector store'},
    {'group': 'Workflow docs', 'path': '/api/ai/documents/workflows', 'methods': ['GET'],
     'auth': 'session', 'rate_limited': False,
     'description': 'List workflow documentation entries (role-filtered for non-admins)'},
    {'group': 'Workflow docs', 'path': '/api/ai/documents/workflows/<workflow_id>', 'methods': ['GET'],
     'auth': 'session', 'rate_limited': False,
     'description': 'Single workflow doc + tour config'},
    {'group': 'Workflow docs', 'path': '/api/ai/documents/workflows/<workflow_id>/tour', 'methods': ['GET'],
     'auth': 'session', 'rate_limited': False,
     'description': 'Interactive tour JSON for a workflow (lang query param)'},
    {'group': 'Workflow docs', 'path': '/api/ai/documents/workflows/search', 'methods': ['GET'],
     'auth': 'session', 'rate_limited': False,
     'description': 'Keyword search over workflow documentation'},

    {'group': 'IFRC API import', 'path': '/api/ai/documents/ifrc-api/types', 'methods': ['GET'],
     'auth': 'session', 'rate_limited': True,
     'description': 'IFRC PublicSiteTypes-derived document type list (admin.documents.manage)'},
    {'group': 'IFRC API import', 'path': '/api/ai/documents/ifrc-api/filter-options', 'methods': ['GET'],
     'auth': 'session', 'rate_limited': True,
     'description': 'Filter options for IFRC appeals (country vs type axes)'},
    {'group': 'IFRC API import', 'path': '/api/ai/documents/ifrc-api/list', 'methods': ['GET'],
     'auth': 'session', 'rate_limited': True,
     'description': 'List IFRC API documents matching filters; marks already-imported URLs'},
    {'group': 'IFRC API import', 'path': '/api/ai/documents/ifrc-api/import', 'methods': ['POST'],
     'auth': 'session', 'rate_limited': True,
     'description': 'Import one document from an IFRC API URL'},
    {'group': 'IFRC API import', 'path': '/api/ai/documents/ifrc-api/import-bulk', 'methods': ['POST'],
     'auth': 'session', 'rate_limited': True,
     'description': 'Start parallel bulk IFRC import job; returns job_id'},
    {'group': 'IFRC API import', 'path': '/api/ai/documents/ifrc-api/import-bulk/<job_id>/status', 'methods': ['GET'],
     'auth': 'session', 'rate_limited': False,
     'description': 'Poll bulk import job and per-item status'},
    {'group': 'IFRC API import', 'path': '/api/ai/documents/ifrc-api/import-bulk/<job_id>/cancel', 'methods': ['POST'],
     'auth': 'session', 'rate_limited': False,
     'description': 'Request cancellation of a bulk import job (best-effort)'},
]

# ── Mobile App API  /api/mobile/v1/* ─────────────────────────────────────────
# auth values:
#   'public'  – no token required (anyone reaching the server can call it)
#   'user'    – @mobile_auth_required (JWT or session, no RBAC check)
#   'rbac'    – @mobile_auth_required(permission=…) (user + RBAC gate)
#
# flag types:
#   'mismatch'  – Flutter client calls endpoint with wrong auth mode
#   'contract'  – API payload contract broken (client ≠ server expectations)
#   'bug'       – Server-side code bug on this endpoint
#   'policy'    – Authorization policy inconsistency
#   'unused'    – Endpoint defined but not wired in any Flutter provider
#   'minor'     – Low-priority improvement opportunity
# ---------------------------------------------------------------------------
MOBILE_ENDPOINT_REGISTRY = [
    # ── AUTH ──────────────────────────────────────────────────────────────────
    {'group': 'Auth', 'path': '/api/mobile/v1/auth/token', 'methods': ['POST'],
     'auth': 'public', 'rate_limited': True,
     'description': 'Issue JWT access + refresh tokens (password login)',
     'flutter': 'AuthService'},
    {'group': 'Auth', 'path': '/api/mobile/v1/auth/refresh', 'methods': ['POST'],
     'auth': 'public', 'rate_limited': True,
     'description': 'Refresh JWT access token using refresh token',
     'flutter': 'AuthService'},
    {'group': 'Auth', 'path': '/api/mobile/v1/auth/exchange-session', 'methods': ['POST'],
     'auth': 'user',
     'description': 'Exchange session cookie for JWT tokens (Azure/SSO login)',
     'flutter': 'AuthService'},
    {'group': 'Auth', 'path': '/api/mobile/v1/auth/session', 'methods': ['GET'],
     'auth': 'user',
     'description': 'Validate current session / check login state',
     'flutter': 'AuthService'},
    {'group': 'Auth', 'path': '/api/mobile/v1/auth/logout', 'methods': ['POST'],
     'auth': 'user',
     'description': 'Logout and invalidate session / tokens',
     'flutter': 'AuthService'},
    {'group': 'Auth', 'path': '/api/mobile/v1/auth/change-password', 'methods': ['POST'],
     'auth': 'user',
     'description': 'Change authenticated user password',
     'flutter': 'AuthService'},
    {'group': 'Auth', 'path': '/api/mobile/v1/auth/profile', 'methods': ['GET', 'PUT', 'PATCH'],
     'auth': 'user',
     'description': 'Get or update authenticated user profile',
     'flutter': 'AuthService / UserProfileService'},

    # ── NOTIFICATIONS ─────────────────────────────────────────────────────────
    {'group': 'Notifications', 'path': '/api/mobile/v1/notifications', 'methods': ['GET'],
     'auth': 'user',
     'description': 'List user notifications',
     'flutter': 'NotificationService'},
    {'group': 'Notifications', 'path': '/api/mobile/v1/notifications/count', 'methods': ['GET'],
     'auth': 'user',
     'description': 'Get unread notification count',
     'flutter': 'NotificationService'},
    {'group': 'Notifications', 'path': '/api/mobile/v1/notifications/mark-read', 'methods': ['POST'],
     'auth': 'user',
     'description': 'Mark notifications as read',
     'flutter': 'NotificationService'},
    {'group': 'Notifications', 'path': '/api/mobile/v1/notifications/mark-unread', 'methods': ['POST'],
     'auth': 'user',
     'description': 'Mark notifications as unread',
     'flutter': 'NotificationService'},
    {'group': 'Notifications', 'path': '/api/mobile/v1/notifications/preferences', 'methods': ['GET', 'POST'],
     'auth': 'user',
     'description': 'Get or update notification preferences',
     'flutter': 'NotificationService'},

    # ── DEVICES ───────────────────────────────────────────────────────────────
    {'group': 'Devices', 'path': '/api/mobile/v1/devices/register', 'methods': ['POST'],
     'auth': 'user',
     'description': 'Register device token for push notifications',
     'flutter': 'PushNotificationService'},
    {'group': 'Devices', 'path': '/api/mobile/v1/devices/unregister', 'methods': ['POST'],
     'auth': 'user',
     'description': 'Unregister device from push notifications',
     'flutter': 'PushNotificationService'},
    {'group': 'Devices', 'path': '/api/mobile/v1/devices/heartbeat', 'methods': ['POST'],
     'auth': 'user',
     'description': 'Device presence heartbeat',
     'flutter': 'PushNotificationService'},

    # ── PUBLIC DATA ───────────────────────────────────────────────────────────
    {'group': 'Public Data', 'path': '/api/mobile/v1/data/countrymap', 'methods': ['GET'],
     'auth': 'public', 'rate_limited': True,
     'description': 'Country list with locale support — publicly accessible, rate-limited',
     'flutter': 'CountriesScreen / CountriesWidget',
     'overlaps': ['/api/v1/countrymap']},
    {'group': 'Public Data', 'path': '/api/mobile/v1/data/sectors-subsectors', 'methods': ['GET'],
     'auth': 'public', 'rate_limited': True,
     'description': 'Sectors and nested subsectors list',
     'flutter': 'IndicatorBankProvider',
     'overlaps': ['/api/v1/sectors-subsectors']},
    {'group': 'Public Data', 'path': '/api/mobile/v1/data/indicator-bank', 'methods': ['GET'],
     'auth': 'public', 'rate_limited': True,
     'description': 'Public indicator bank listing (up to 2 000/page)',
     'flutter': 'IndicatorBankProvider',
     'overlaps': ['/api/v1/indicator-bank']},
    {'group': 'Public Data', 'path': '/api/mobile/v1/data/indicator-bank/<indicator_id>', 'methods': ['GET'],
     'auth': 'public',
     'description': 'Single indicator detail (public)',
     'flutter': 'IndicatorDetailScreen',
     'overlaps': ['/api/v1/indicator-bank/<indicator_id>']},
    {'group': 'Public Data', 'path': '/api/mobile/v1/data/indicator-suggestions', 'methods': ['POST'],
     'auth': 'public', 'rate_limited': True,
     'description': 'Submit a new indicator suggestion',
     'flutter': 'IndicatorBankScreen',
     'overlaps': ['/api/v1/indicator-suggestions']},
    {'group': 'Public Data', 'path': '/api/mobile/v1/data/periods', 'methods': ['GET'],
     'auth': 'public', 'rate_limited': True,
     'description': 'List available reporting periods',
     'flutter': 'GlobalOverviewDataService'},
    {'group': 'Public Data', 'path': '/api/mobile/v1/data/fdrs-overview', 'methods': ['GET'],
     'auth': 'public', 'rate_limited': True,
     'description': (
         'FDRS aggregated totals per country (GET). Required query: indicator_bank_id. '
         'Optional: template_id, period_name, locale. Path has no <id> segment — ID is only in the query string.'
     ),
     'flutter': 'GlobalOverviewDataService'},
    {'group': 'Public Data', 'path': '/api/mobile/v1/data/resources', 'methods': ['GET'],
     'auth': 'public', 'rate_limited': True,
     'description': (
         'Resources/publications library (search, type, locale). '
         'Use grouped=true (no search) for subgroup sections; otherwise paginated list. '
         'No auth required; same content family as /api/v1/resources (API key there).'
     ),
     'flutter': 'PublicResourcesProvider',
     'overlaps': ['/api/v1/resources']},
    {'group': 'Public Data', 'path': '/api/mobile/v1/data/unified-planning-config', 'methods': ['GET'],
     'auth': 'public', 'rate_limited': True,
     'description': (
         'IFRC GO PublicSiteAppeals base URL and unified planning AppealsTypeId list '
         '(Plan, Mid-Year Report, Annual Report) for client-side IFRC document fetch.'
     ),
     'flutter': 'PublicResourcesProvider'},
    {'group': 'Public Data', 'path': '/api/mobile/v1/data/unified-planning-thumbnail', 'methods': ['GET'],
     'auth': 'public', 'rate_limited': True,
     'description': (
         'JPEG first page of an IFRC PDF for grid thumbnails (query: url). '
         'Server fetches PDF with IFRC credentials; returns image/jpeg, not JSON.'
     ),
     'flutter': 'UnifiedPlanningPdfThumbnailCache'},
    {'group': 'Public Data', 'path': '/api/mobile/v1/data/quiz/leaderboard', 'methods': ['GET'],
     'auth': 'public', 'rate_limited': True,
     'description': 'Quiz global leaderboard — publicly accessible, rate-limited',
     'flutter': 'LeaderboardProvider',
     'overlaps': ['/api/v1/quiz/leaderboard']},
    {'group': 'Public Data', 'path': '/api/mobile/v1/data/quiz/submit-score', 'methods': ['POST'],
     'auth': 'user',
     'description': 'Submit quiz score — user_name derived from current_user, only score required from client',
     'flutter': 'QuizGameProvider'},

    # ── USER ──────────────────────────────────────────────────────────────────
    {'group': 'User', 'path': '/api/mobile/v1/user/dashboard', 'methods': ['GET'],
     'auth': 'user',
     'description': 'User-scoped dashboard data (entities, assignments)',
     'flutter': 'DashboardRepository'},

    # ── ANALYTICS ─────────────────────────────────────────────────────────────
    {'group': 'Analytics', 'path': '/api/mobile/v1/analytics/screen-view', 'methods': ['POST'],
     'auth': 'user', 'rate_limited': True,
     'description': 'Track in-app screen view event',
     'flutter': 'ScreenViewTracker (AppConfig.mobileScreenViewEndpoint)'},

    # ── ADMIN — USERS ─────────────────────────────────────────────────────────
    {'group': 'Admin: Users', 'path': '/api/mobile/v1/admin/users', 'methods': ['GET'],
     'auth': 'rbac', 'permission': 'admin.users.view',
     'description': 'List all users',
     'flutter': 'ManageUsersProvider'},
    {'group': 'Admin: Users', 'path': '/api/mobile/v1/admin/users/<user_id>', 'methods': ['GET'],
     'auth': 'rbac', 'permission': 'admin.users.view',
     'description': 'Get user details',
     'flutter': 'ManageUsersProvider'},
    {'group': 'Admin: Users', 'path': '/api/mobile/v1/admin/users/<user_id>', 'methods': ['PUT', 'PATCH'],
     'auth': 'rbac', 'permission': 'admin.users.edit',
     'description': 'Update user details / role assignment',
     'flutter': 'ManageUsersProvider'},
    {'group': 'Admin: Users', 'path': '/api/mobile/v1/admin/users/<user_id>/activate', 'methods': ['POST'],
     'auth': 'rbac', 'permission': 'admin.users.deactivate',
     'description': 'Activate a user account',
     'flutter': 'ManageUsersProvider'},
    {'group': 'Admin: Users', 'path': '/api/mobile/v1/admin/users/<user_id>/deactivate', 'methods': ['POST'],
     'auth': 'rbac', 'permission': 'admin.users.deactivate',
     'description': 'Deactivate a user account',
     'flutter': 'ManageUsersProvider'},
    {'group': 'Admin: Users', 'path': '/api/mobile/v1/admin/users/rbac-roles', 'methods': ['GET'],
     'auth': 'rbac', 'permission': 'admin.users.view',
     'description': 'List available RBAC role definitions',
     'flutter': 'ManageUsersProvider'},

    # ── ADMIN — ACCESS REQUESTS ───────────────────────────────────────────────
    {'group': 'Admin: Access', 'path': '/api/mobile/v1/admin/access-requests', 'methods': ['GET'],
     'auth': 'rbac', 'permission': 'admin.access_requests.view',
     'description': 'List pending access requests',
     'flutter': 'AccessRequestsProvider'},
    {'group': 'Admin: Access', 'path': '/api/mobile/v1/admin/access-requests/<request_id>/approve', 'methods': ['POST'],
     'auth': 'rbac', 'permission': 'admin.access_requests.approve',
     'description': 'Approve a single access request',
     'flutter': 'AccessRequestsProvider'},
    {'group': 'Admin: Access', 'path': '/api/mobile/v1/admin/access-requests/approve-all', 'methods': ['POST'],
     'auth': 'rbac', 'permission': 'admin.access_requests.approve',
     'description': 'Approve all pending access requests',
     'flutter': 'AccessRequestsProvider'},
    {'group': 'Admin: Access', 'path': '/api/mobile/v1/admin/access-requests/<request_id>/reject', 'methods': ['POST'],
     'auth': 'rbac', 'permission': 'admin.access_requests.reject',
     'description': 'Reject an access request',
     'flutter': 'AccessRequestsProvider'},

    # ── ADMIN — ANALYTICS ─────────────────────────────────────────────────────
    {'group': 'Admin: Analytics', 'path': '/api/mobile/v1/admin/analytics/dashboard-stats', 'methods': ['GET'],
     'auth': 'rbac', 'permission': 'admin.analytics.view',
     'description': 'Admin dashboard statistics (users, submissions, etc.)',
     'flutter': 'AdminDashboardProvider'},
    {'group': 'Admin: Analytics', 'path': '/api/mobile/v1/admin/analytics/dashboard-activity', 'methods': ['GET'],
     'auth': 'rbac', 'permission': 'admin.analytics.view',
     'description': 'Recent admin dashboard activity feed',
     'flutter': 'UserAnalyticsProvider'},
    {'group': 'Admin: Analytics', 'path': '/api/mobile/v1/admin/analytics/login-logs', 'methods': ['GET'],
     'auth': 'rbac', 'permission': 'admin.analytics.view',
     'description': 'Login event logs',
     'flutter': 'LoginLogsProvider'},
    {'group': 'Admin: Analytics', 'path': '/api/mobile/v1/admin/analytics/session-logs', 'methods': ['GET'],
     'auth': 'rbac', 'permission': 'admin.analytics.view',
     'description': 'Session logs',
     'flutter': 'SessionLogsProvider'},
    {'group': 'Admin: Analytics', 'path': '/api/mobile/v1/admin/analytics/sessions/<session_id>/end', 'methods': ['POST'],
     'auth': 'rbac', 'permission': 'admin.analytics.view',
     'description': 'Force-terminate a live user session',
     'flutter': 'SessionLogsProvider'},
    {'group': 'Admin: Analytics', 'path': '/api/mobile/v1/admin/analytics/audit-trail', 'methods': ['GET'],
     'auth': 'rbac', 'permission': 'admin.audit.view',
     'description': 'System audit trail events',
     'flutter': 'AuditTrailProvider'},
    {'group': 'Admin: Analytics', 'path': '/api/mobile/v1/admin/notifications/send', 'methods': ['POST'],
     'auth': 'rbac', 'permission': 'admin.notifications.manage',
     'description': 'Send push notification to selected users',
     'flutter': 'AdminDashboardProvider',
     'flags': [{'type': 'unused',
                'note': 'AppConfig.mobileAdminSendNotificationEndpoint is defined but not '
                        'wired in any provider — endpoint exists on backend, never called.'}]},

    # ── ADMIN — CONTENT ───────────────────────────────────────────────────────
    {'group': 'Admin: Content', 'path': '/api/mobile/v1/admin/content/templates', 'methods': ['GET'],
     'auth': 'rbac', 'permission': 'admin.templates.view',
     'description': 'List form templates',
     'flutter': 'TemplatesProvider'},
    {'group': 'Admin: Content', 'path': '/api/mobile/v1/admin/content/templates/<template_id>/delete', 'methods': ['POST'],
     'auth': 'rbac', 'permission': 'admin.templates.delete',
     'description': 'Delete a form template',
     'flutter': 'TemplatesProvider'},
    {'group': 'Admin: Content', 'path': '/api/mobile/v1/admin/content/assignments', 'methods': ['GET'],
     'auth': 'rbac', 'permission': 'admin.assignments.view',
     'description': 'List form assignments',
     'flutter': 'AssignmentsProvider'},
    {'group': 'Admin: Content', 'path': '/api/mobile/v1/admin/content/assignments/<assignment_id>/delete', 'methods': ['POST'],
     'auth': 'rbac', 'permission': 'admin.assignments.delete',
     'description': 'Delete a form assignment',
     'flutter': 'AssignmentsProvider'},
    {'group': 'Admin: Content', 'path': '/api/mobile/v1/admin/content/assignments/<assignment_id>/toggle-public', 'methods': ['POST'],
     'auth': 'rbac', 'permission': 'admin.assignments.public_submissions.manage',
     'description': 'Toggle public visibility of an assignment',
     'flutter': 'AssignmentsProvider'},
    {'group': 'Admin: Content', 'path': '/api/mobile/v1/admin/content/assignments/<assignment_id>/generate-url', 'methods': ['POST'],
     'auth': 'rbac', 'permission': 'admin.assignments.public_submissions.manage',
     'description': 'Generate public submission URL for an assignment',
     'flutter': 'AssignmentsProvider'},
    {'group': 'Admin: Content', 'path': '/api/mobile/v1/admin/content/documents', 'methods': ['GET'],
     'auth': 'rbac', 'permission': 'admin.documents.manage',
     'description': 'List submitted documents',
     'flutter': 'DocumentManagementProvider'},
    {'group': 'Admin: Content', 'path': '/api/mobile/v1/admin/content/documents/<document_id>/delete', 'methods': ['POST'],
     'auth': 'rbac', 'permission': 'admin.documents.manage',
     'description': 'Delete a submitted document',
     'flutter': 'DocumentManagementProvider'},
    {'group': 'Admin: Content', 'path': '/api/mobile/v1/admin/content/resources', 'methods': ['GET'],
     'auth': 'rbac', 'permission': 'admin.resources.manage',
     'description': 'List resources',
     'flutter': 'ResourcesManagementProvider'},
    {'group': 'Admin: Content', 'path': '/api/mobile/v1/admin/content/resources/<resource_id>/delete', 'methods': ['POST'],
     'auth': 'rbac', 'permission': 'admin.resources.manage',
     'description': 'Delete a resource',
     'flutter': 'ResourcesManagementProvider'},
    {'group': 'Admin: Content', 'path': '/api/mobile/v1/admin/content/indicator-bank', 'methods': ['GET'],
     'auth': 'rbac', 'permission': 'admin.indicator_bank.view',
     'description': 'Admin indicator bank listing (includes archived)',
     'flutter': 'IndicatorBankAdminProvider'},
    {'group': 'Admin: Content', 'path': '/api/mobile/v1/admin/content/indicator-bank/<indicator_id>', 'methods': ['GET'],
     'auth': 'rbac', 'permission': 'admin.indicator_bank.view',
     'description': 'Get a single indicator bank item',
     'flutter': 'IndicatorBankAdminProvider'},
    {'group': 'Admin: Content', 'path': '/api/mobile/v1/admin/content/indicator-bank/<indicator_id>/edit', 'methods': ['POST'],
     'auth': 'rbac', 'permission': 'admin.indicator_bank.edit',
     'description': 'Edit indicator bank item fields',
     'flutter': 'IndicatorBankAdminProvider'},
    {'group': 'Admin: Content', 'path': '/api/mobile/v1/admin/content/indicator-bank/<indicator_id>/archive', 'methods': ['POST'],
     'auth': 'rbac', 'permission': 'admin.indicator_bank.edit',
     'description': 'Archive an indicator bank item',
     'flutter': 'IndicatorBankAdminProvider'},
    {'group': 'Admin: Content', 'path': '/api/mobile/v1/admin/content/indicator-bank/<indicator_id>/delete', 'methods': ['POST'],
     'auth': 'rbac', 'permission': 'admin.indicator_bank.delete',
     'description': 'Delete an indicator bank item',
     'flutter': 'IndicatorBankAdminProvider'},
    {'group': 'Admin: Content', 'path': '/api/mobile/v1/admin/content/translations', 'methods': ['GET'],
     'auth': 'rbac', 'permission': 'admin.translations.manage',
     'description': 'List translations for admin review',
     'flutter': 'TranslationManagementProvider'},
    {'group': 'Admin: Content', 'path': '/api/mobile/v1/admin/content/translations/sources', 'methods': ['GET'],
     'auth': 'rbac', 'permission': 'admin.translations.manage',
     'description': 'Distinct gettext #: file paths for mobile source filter',
     'flutter': 'TranslationManagementProvider'},
    {'group': 'Admin: Content', 'path': '/api/mobile/v1/admin/content/translations/<translation_id>', 'methods': ['POST'],
     'auth': 'rbac', 'permission': 'admin.translations.manage',
     'description': 'Update a translation string',
     'flutter': 'TranslationManagementProvider'},

    # ── ADMIN — ORG ───────────────────────────────────────────────────────────
    {'group': 'Admin: Org', 'path': '/api/mobile/v1/admin/org/branches/<country_id>', 'methods': ['GET'],
     'auth': 'rbac', 'permission': 'admin.organization.manage',
     'description': 'List NS branches for a country (consistent with /admin/org/structure)',
     'flutter': '— (AppConfig constant defined, not yet wired in any provider)'},
    {'group': 'Admin: Org', 'path': '/api/mobile/v1/admin/org/subbranches/<branch_id>', 'methods': ['GET'],
     'auth': 'rbac', 'permission': 'admin.organization.manage',
     'description': 'List NS sub-branches for a branch (consistent with /admin/org/structure)',
     'flutter': '— (AppConfig constant defined, not yet wired in any provider)'},
    {'group': 'Admin: Org', 'path': '/api/mobile/v1/admin/org/structure', 'methods': ['GET'],
     'auth': 'rbac', 'permission': 'admin.organization.manage',
     'description': 'Full org structure as flat lists (countries, branches, sub-branches)',
     'flutter': 'OrganizationalStructureProvider'},
]

# Combined registry — single source of truth for all API surfaces
ENDPOINT_REGISTRY = (
    [dict(e, surface='v1')     for e in EXTERNAL_API_REGISTRY] +
    [dict(e, surface='ai')     for e in AI_API_REGISTRY] +
    [dict(e, surface='ai')     for e in AI_DOCUMENTS_API_REGISTRY] +
    [dict(e, surface='mobile') for e in MOBILE_ENDPOINT_REGISTRY]
)


def _count_unique_overlap_pairs(endpoints: list[dict]) -> int:
    """Undirected pairs from registry `overlaps` (same logical v1 ↔ mobile analogue counted once)."""
    pairs: set[tuple[str, str]] = set()
    for ep in endpoints:
        p = (ep.get('path') or '').strip()
        for o in ep.get('overlaps') or []:
            o = str(o).strip()
            if p and o:
                pairs.add(tuple(sorted((p, o))))
    return len(pairs)


# ---------------------------------------------------------------------------
# Live route scanner
# ---------------------------------------------------------------------------
import re as _re

# Methods Flask adds to every route that we never want to surface
_SKIP_METHODS = frozenset({'HEAD', 'OPTIONS'})

# Prefixes we care about
_API_PREFIXES = ('/api/v1/', '/api/mobile/v1/', '/api/ai/v2/', '/api/ai/')

# AI-surface path heuristic: auth via resolve_ai_identity() inline (no decorator)
_AI_AUTH_HEURISTIC = 'ai_session'

# Flask uses <type:name> — strip the type annotation for comparison
def _normalize_path(path: str) -> str:
    return _re.sub(r'<[^:>]+:([^>]+)>', r'<\1>', path)


def _surface_for_path(path: str) -> str:
    if path.startswith('/api/mobile/v1/'):
        return 'mobile'
    if path.startswith('/api/ai/'):
        return 'ai'
    if path.startswith('/api/v1/'):
        return 'v1'
    return 'other'


def _auth_for_view(view_fn) -> tuple[str, str | None]:
    """Return (auth_type, permission) by reading _ep_auth/_ep_permission tags."""
    auth = getattr(view_fn, '_ep_auth', None)
    perm = getattr(view_fn, '_ep_permission', None)
    return auth, perm


def scan_flask_routes(app) -> dict:
    """
    Scan the live Flask url_map and compare against ENDPOINT_REGISTRY.

    Returns a dict with:
      live          – list of dicts for every /api/* route found in url_map
      undocumented  – routes in url_map but NOT in the registry
      stale         – registry entries whose path is NOT in url_map
      coverage_pct  – float (0–100)
    """
    # ── Build a normalised set of registry paths ──────────────────────────
    registry_paths: set[str] = {
        _normalize_path(ep['path'])
        for ep in ENDPOINT_REGISTRY
    }

    # ── Walk the live url_map ─────────────────────────────────────────────
    live: list[dict] = []
    live_paths: set[str] = set()

    for rule in app.url_map.iter_rules():
        path = rule.rule
        if not any(path.startswith(p) for p in _API_PREFIXES):
            continue

        methods = sorted(rule.methods - _SKIP_METHODS)
        norm   = _normalize_path(path)
        surface = _surface_for_path(path)

        view_fn  = app.view_functions.get(rule.endpoint)
        ep_auth, ep_perm = _auth_for_view(view_fn) if view_fn else (None, None)

        # For AI routes without a decorator tag, fall back to heuristic
        if ep_auth is None and surface == 'ai':
            ep_auth = _AI_AUTH_HEURISTIC

        live.append({
            'path':       norm,
            'raw_path':   path,
            'methods':    methods,
            'surface':    surface,
            'ep_auth':    ep_auth,    # None means "not tagged"
            'ep_perm':    ep_perm,
            'endpoint':   rule.endpoint,
            'in_registry': norm in registry_paths,
        })
        live_paths.add(norm)

    # ── Undocumented: in url_map but not in registry ──────────────────────
    undocumented = [r for r in live if not r['in_registry']]

    # ── Stale: in registry but path not found in url_map ─────────────────
    stale_paths = registry_paths - live_paths
    stale = [ep for ep in ENDPOINT_REGISTRY if _normalize_path(ep['path']) in stale_paths]

    total_live = len(live_paths)
    documented = total_live - len(undocumented)
    coverage   = (documented / total_live * 100) if total_live else 100.0

    return {
        'live':          live,
        'undocumented':  undocumented,
        'stale':         stale,
        'coverage_pct':  round(coverage, 1),
        'total_live':    total_live,
        'documented':    documented,
    }


def _ep_surface_filter_disabled(grid_rows: list[dict]) -> dict[str, bool]:
    """Per chip: True if that filter matches zero rows (same rules as registry grid JS)."""

    def row_matches(row: dict, surface: str) -> bool:
        if surface == 'flagged':
            return bool(row.get('has_flags'))
        if surface == 'overlap':
            return bool(row.get('has_overlap'))
        if surface == 'has_stats':
            return bool(row.get('has_stats'))
        if surface == 'undocumented':
            return bool(row.get('undocumented'))
        if surface == 'stale':
            return bool(row.get('stale'))
        if surface == 'gaps':
            return bool(row.get('gaps'))
        return (row.get('surface') or '') == surface

    keys = (
        'v1',
        'mobile',
        'ai',
        'flagged',
        'overlap',
        'has_stats',
        'undocumented',
        'stale',
        'gaps',
    )
    return {k: not any(row_matches(r, k) for r in grid_rows) for k in keys}


def _endpoint_registry_grid_rows(all_endpoints: list[dict]) -> list[dict]:
    """JSON-serializable rows for AG Grid (Endpoint Registry)."""
    rows: list[dict] = []
    for ep in all_endpoints:
        surf = ep.get('surface') or ''
        grp = ep.get('group') or ''
        path = ep.get('path') or ''
        if surf == 'v1':
            group_label = f'External /v1 — {grp}'
        elif surf == 'mobile':
            group_label = f'Mobile — {grp}'
        elif surf == 'ai':
            if path.startswith('/api/ai/documents'):
                group_label = f'AI Documents — {grp}'
            else:
                group_label = f'AI /v2 — {grp}'
        else:
            group_label = grp or '—'
        desc = ep.get('description') or ''
        flags = ep.get('flags') or []
        overlaps = ep.get('overlaps') or []
        methods = list(ep.get('methods') or [])
        consumers = ep.get('flutter') or ep.get('consumers') or ''
        tr = int(ep.get('total_requests') or 0)
        rows.append({
            'registryGroup': group_label,
            'surface': surf,
            'path': path,
            'pathLower': path.lower(),
            'pathSearch': f'{path.lower()} {desc.lower()} {grp.lower()} {consumers.lower()}',
            'description': desc,
            'methods': methods,
            'methodsStr': ', '.join(methods),
            'auth': ep.get('auth') or '',
            'permission': ep.get('permission') or '',
            'consumers': consumers,
            'total_requests': tr,
            'success_rate': float(ep.get('success_rate') or 0),
            'featured': bool(ep.get('featured')),
            'has_flags': bool(flags),
            'has_overlap': bool(overlaps),
            'has_stats': tr > 0,
            'undocumented': bool(ep.get('undocumented')),
            'stale': bool(ep.get('stale')),
            'gaps': bool(ep.get('undocumented') or ep.get('stale')),
            'rate_limited': bool(ep.get('rate_limited')),
            'overlapPaths': list(overlaps),
            'flags': [{'type': f.get('type'), 'note': f.get('note') or ''} for f in flags],
        })
    return rows


@bp.route('/api-management')
@admin_permission_required('admin.api.manage')
def api_management():
    # ── Live route scan ───────────────────────────────────────────────────────
    # Compare url_map to the registry so undocumented / stale routes surface immediately.
    scan = scan_flask_routes(current_app._get_current_object())

    # Mark stale registry entries (path not found in live url_map)
    stale_paths = {_normalize_path(ep['path']) for ep in scan['stale']}

    # ── Unified endpoint registry ─────────────────────────────────────────────
    # Make mutable copies so we can attach runtime stats without mutating module-level dicts
    all_endpoints = [dict(ep) for ep in ENDPOINT_REGISTRY]

    # Stamp stale flag on registry entries whose path is no longer live
    for ep in all_endpoints:
        if _normalize_path(ep['path']) in stale_paths:
            ep['stale'] = True

    # Append undocumented live routes at the end (shown with warning badge)
    for live_ep in scan['undocumented']:
        # Best-guess auth from decorator tag; fall back to '?' for truly unknown
        auth = live_ep['ep_auth'] or '?'
        all_endpoints.append({
            'surface':      live_ep['surface'],
            'group':        'Undocumented',
            'path':         live_ep['path'],
            'methods':      live_ep['methods'],
            'auth':         auth,
            'permission':   live_ep['ep_perm'] or '',
            'description':  '⚠ Route exists in Flask url_map but is not in the registry.',
            'consumers':    '',
            'rate_limited': False,
            'total_requests': 0,
            'success_rate': 100,
            'undocumented': True,
        })

    # Attach usage stats from APIUsage (covers /api/v1 traffic; mobile/AI show 0)
    for ep in all_endpoints:
        filter_prefix = ep['path'].split('<')[0].split('{')[0]
        endpoint_stats = APIUsage.query.filter(
            APIUsage.api_endpoint.like(f"{filter_prefix}%")
        ).with_entities(
            func.count().label('total_requests'),
            func.sum(case((APIUsage.status_code < 400, 1), else_=0)).label('successful_requests'),
        ).first()

        ep['total_requests'] = endpoint_stats.total_requests if endpoint_stats else 0
        ep['success_rate'] = (
            endpoint_stats.successful_requests / endpoint_stats.total_requests * 100
            if endpoint_stats and endpoint_stats.total_requests > 0 else 100
        )

    # ── Per-surface summary ───────────────────────────────────────────────────
    def _surface_summary(surface_key):
        eps = [e for e in all_endpoints if e['surface'] == surface_key]
        return {
            'total':        len(eps),
            'public':       sum(1 for e in eps if e['auth'] == 'public'),
            'flagged':      sum(1 for e in eps if e.get('flags')),
            'overlapping':  sum(1 for e in eps if e.get('overlaps')),
            'rate_limited': sum(1 for e in eps if e.get('rate_limited')),
            'with_stats':   sum(1 for e in eps if e['total_requests'] > 0),
        }

    surface_summary = {
        'v1':     _surface_summary('v1'),
        'ai':     _surface_summary('ai'),
        'mobile': _surface_summary('mobile'),
    }
    surface_summary['all'] = {
        'total':          len(all_endpoints),
        'flagged':        sum(1 for e in all_endpoints if e.get('flags')),
        # Unique v1↔mobile analogue pairs (registry may list both endpoints; grid filter still matches each row)
        'overlapping':    _count_unique_overlap_pairs(all_endpoints),
        'with_stats':     sum(1 for e in all_endpoints if e['total_requests'] > 0),
        'undocumented':   len(scan['undocumented']),
        'stale':          len(scan['stale']),
        'coverage_pct':   scan['coverage_pct'],
        'documented_live_paths': scan['documented'],
        'total_live_paths': scan['total_live'],
    }

    # ── v1 endpoints for URL builder (keeps existing dropdown working) ─────────
    v1_endpoints = [
        {**ep, 'method': '/'.join(ep['methods'])}
        for ep in all_endpoints if ep['surface'] == 'v1'
    ]

    # ── Legacy `api_endpoints` list kept for the chart endpoint selector ───────
    # (sorted by total_requests descending so the selector shows busiest first)
    api_endpoints = sorted(v1_endpoints, key=lambda x: x['total_requests'], reverse=True)

    # ── Data for URL-builder dropdowns ────────────────────────────────────────
    templates = FormTemplate.query.all()
    templates.sort(key=lambda t: t.name if t.name else '')
    countries = Country.query.order_by(Country.name.asc()).all()
    users = User.query.order_by(User.name.asc()).all()

    sector_options     = [s.name for s in Sector.query.order_by(Sector.name.asc()).all()]
    sub_sector_options = [ss.name for ss in SubSector.query.order_by(SubSector.name.asc()).all()]
    type_options       = [
        t[0] for t in
        db.session.query(IndicatorBank.type).distinct().order_by(IndicatorBank.type.asc()).all()
    ]

    # ── Overall stats (APIUsage — covers v1 traffic only) ────────────────────
    total_requests    = APIUsage.query.count()
    avg_response_time = db.session.query(func.avg(APIUsage.response_time)).scalar() or 0
    success_rate      = (
        APIUsage.query.filter(APIUsage.status_code < 400).count() / total_requests * 100
        if total_requests > 0 else 100
    )
    unique_ips = APIUsage.query.with_entities(APIUsage.ip_address).distinct().count()

    # Chart data — last 24 h hourly breakdown (v1 traffic)
    last_24h  = utcnow() - timedelta(days=1)
    stats     = APIUsage.query.filter(
        APIUsage.api_endpoint.like('/api/%'),
        APIUsage.timestamp >= last_24h,
    ).all()
    hour_counts = {}
    for record in stats:
        hour = record.timestamp.strftime('%H:00')
        hour_counts[hour] = hour_counts.get(hour, 0) + 1
    all_hours = {}
    current   = utcnow()
    for i in range(24):
        hour = (current - timedelta(hours=i)).strftime('%H:00')
        all_hours[hour] = hour_counts.get(hour, 0)
    chart_data = [{'label': h, 'count': c} for h, c in reversed(all_hours.items())]

    endpoint_registry_grid_rows = _endpoint_registry_grid_rows(all_endpoints)
    ep_surface_filter_disabled = _ep_surface_filter_disabled(endpoint_registry_grid_rows)

    return render_template(
        'admin/api_management.html',
        # Unified registry
        all_endpoints=all_endpoints,
        endpoint_registry_grid_rows=endpoint_registry_grid_rows,
        ep_surface_filter_disabled=ep_surface_filter_disabled,
        surface_summary=surface_summary,
        # Backward-compat for URL builder + chart selector
        endpoints=api_endpoints,
        # Overview stats (v1 / APIUsage)
        total_requests=total_requests,
        avg_response_time=avg_response_time,
        success_rate=success_rate,
        unique_ips=unique_ips,
        chart_data=chart_data,
        # URL builder dropdowns
        sector_options=sector_options,
        sub_sector_options=sub_sector_options,
        type_options=type_options,
        templates=templates,
        countries=countries,
        users=users,
        # Legacy — keep mobile_summary accessible if needed elsewhere
        mobile_summary=surface_summary['mobile'],
    )



@bp.route('/api-management/stats')
@admin_permission_required('admin.api.manage')
def api_stats():
    try:
        period = request.args.get('period', 'daily')
        endpoint = request.args.get('endpoint', 'all')
        current_app.logger.debug(f"Fetching stats for period: {period}, endpoint: {endpoint}")

        # Debug: Check total records in APIUsage table
        total_records = APIUsage.query.count()
        current_app.logger.debug(f"Total APIUsage records: {total_records}")

        # Debug: Show recent records
        recent_records = APIUsage.query.order_by(APIUsage.timestamp.desc()).limit(5).all()
        for record in recent_records:
            current_app.logger.debug(f"Recent record: {record.api_endpoint} at {record.timestamp}")

        # Get all API requests that start with /api/
        base_query = APIUsage.query.filter(APIUsage.api_endpoint.like('/api/%'))

        # Filter by specific endpoint if requested
        if endpoint != 'all':
            base_query = base_query.filter(APIUsage.api_endpoint.ilike(safe_ilike_pattern(endpoint)))
            current_app.logger.debug(f"Filtering by endpoint: {endpoint}")

        api_records = base_query.all()
        current_app.logger.debug(f"API records found: {len(api_records)}")

        if period == 'daily':
            # Get hourly stats for the last 24 hours
            last_24h = utcnow() - timedelta(days=1)
            current_app.logger.debug(f"Looking for records since: {last_24h}")

            stats = base_query.filter(APIUsage.timestamp >= last_24h).all()
            current_app.logger.debug(f"Records in last 24h: {len(stats)}")

            # Group by hour using Python
            hour_counts = {}
            for record in stats:
                hour = record.timestamp.strftime('%H:00')
                hour_counts[hour] = hour_counts.get(hour, 0) + 1
                current_app.logger.debug(f"Record at {record.timestamp} -> hour {hour}")

            current_app.logger.debug(f"Hour counts: {hour_counts}")

            # Fill in missing hours with zeros
            all_hours = {}
            current = utcnow()
            for i in range(24):
                hour = (current - timedelta(hours=i)).strftime('%H:00')
                all_hours[hour] = hour_counts.get(hour, 0)

            formatted_stats = [{'label': h, 'count': c} for h, c in reversed(all_hours.items())]

        elif period == 'weekly':
            # Get daily stats for the last 7 days
            last_7d = utcnow() - timedelta(days=7)
            stats = base_query.filter(APIUsage.timestamp >= last_7d).all()

            # Group by day
            day_counts = {}
            for record in stats:
                day = record.timestamp.strftime('%Y-%m-%d')
                day_counts[day] = day_counts.get(day, 0) + 1

            # Fill in missing days with zeros
            all_days = {}
            current = utcnow()
            for i in range(7):
                day = (current - timedelta(days=i)).strftime('%Y-%m-%d')
                all_days[day] = day_counts.get(day, 0)

            formatted_stats = [{'label': d, 'count': c} for d, c in reversed(all_days.items())]

        elif period == 'monthly':
            # Get daily stats for the last 30 days
            last_30d = utcnow() - timedelta(days=30)
            stats = base_query.filter(APIUsage.timestamp >= last_30d).all()

            # Group by day
            day_counts = {}
            for record in stats:
                day = record.timestamp.strftime('%Y-%m-%d')
                day_counts[day] = day_counts.get(day, 0) + 1

            # Fill in missing days with zeros
            all_days = {}
            current = utcnow()
            for i in range(30):
                day = (current - timedelta(days=i)).strftime('%Y-%m-%d')
                all_days[day] = day_counts.get(day, 0)

            formatted_stats = [{'label': d, 'count': c} for d, c in reversed(all_days.items())]

        else:  # yearly
            # Get monthly stats for the last year
            last_year = utcnow() - timedelta(days=365)
            stats = base_query.filter(APIUsage.timestamp >= last_year).all()

            # Group by month
            month_counts = {}
            for record in stats:
                month = record.timestamp.strftime('%Y-%m')
                month_counts[month] = month_counts.get(month, 0) + 1

            # Fill in missing months with zeros
            all_months = {}
            current = utcnow()
            for i in range(12):
                month = (current - timedelta(days=i*30)).strftime('%Y-%m')
                all_months[month] = month_counts.get(month, 0)

            formatted_stats = [{'label': m, 'count': c} for m, c in reversed(all_months.items())]

        current_app.logger.debug(f"Found {len(stats)} records")
        current_app.logger.debug(f"Formatted stats: {formatted_stats}")

        return json_ok(stats=formatted_stats)

    except Exception as e:
        current_app.logger.error(f"Error in api_stats: {str(e)}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)
