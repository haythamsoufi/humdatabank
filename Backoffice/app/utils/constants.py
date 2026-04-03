"""
Shared application constants used across routes, services, and utils.
"""

# Session key for the currently selected country in the UI
SELECTED_COUNTRY_ID_SESSION_KEY = 'selected_country_id'

# Standardized period name for self-reported submissions/assignments
SELF_REPORT_PERIOD_NAME = 'Self-Reported'

# Temporary order value when reordering lookup list rows (avoids conflicts during shift)
LOOKUP_ROW_TEMP_ORDER = 999999

# Default PostgreSQL advisory lock ID for session cleanup (override via SESSION_CLEANUP_LOCK_ID)
DEFAULT_SESSION_CLEANUP_LOCK_ID = 702345

# ---------------------------------------------------------------------------
# IFRC API Appeals Type IDs (Unified Planning: Plan, Mid-Year Report, Annual Report)
# ---------------------------------------------------------------------------
APPEALS_TYPE_IDS = frozenset({1851, 10009, 10011})
APPEALS_TYPE_DEFAULT_IDS_STR = '1851,10009,10011'
APPEALS_TYPE_LEGACY_MAPPING = {1851: 'Plan', 10009: 'MYR', 10011: 'AR'}
APPEALS_TYPE_DISPLAY_NAMES = {1851: 'Plan', 10009: 'Mid-Year Report', 10011: 'Annual Report'}

# ---------------------------------------------------------------------------
# Session and time-related constants
# ---------------------------------------------------------------------------
# WebSocket connection staleness / cleanup
SESSION_INACTIVITY_SECONDS = 300  # 5 minutes - WebSocket cleanup idle threshold
WS_HEARTBEAT_INTERVAL_SECONDS = 30
WS_INACTIVITY_STALE_SECONDS = 120  # 2 minutes - close connection after this idle time
DAILY_RATE_LIMIT_WINDOW_SECONDS = 86400  # 24 hours
CACHE_MAX_AGE_ONE_HOUR = 3600
PASSWORD_RESET_TOKEN_MAX_AGE_SECONDS = 3600  # 1 hour

# ---------------------------------------------------------------------------
# Log file limits (monitoring)
# ---------------------------------------------------------------------------
MAX_LOG_TAIL_LINES = 10000
MAX_LOG_ROTATION_KEEP_LINES = 50000

# ---------------------------------------------------------------------------
# Content size limits
# ---------------------------------------------------------------------------
MAX_NOTIFICATION_MESSAGE_LENGTH = 5000
MAX_ERROR_LOG_REQUEST_BYTES = 5000

# ---------------------------------------------------------------------------
# Data retrieval and form limits
# ---------------------------------------------------------------------------
DEFAULT_LIMIT_PERIODS = 12
MAX_LIMIT_PERIODS = 50
DEFAULT_LOOKUP_ROW_LIMIT = 500
DEFAULT_INDICATOR_CANDIDATES_LIMIT = 50
DEFAULT_MAX_COMPLETION_TOKENS = 1200
