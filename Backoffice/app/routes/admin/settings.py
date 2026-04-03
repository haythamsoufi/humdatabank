import json
import base64

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from app.utils.api_helpers import get_json_safe, GENERIC_ERROR_MESSAGE
from app.utils.request_utils import get_request_data
from app.utils.api_responses import json_bad_request, json_error, json_ok, json_server_error
from flask_login import login_required, current_user
from app.routes.admin.shared import admin_required, admin_permission_required
from config import Config
from contextlib import suppress

bp = Blueprint("settings", __name__, url_prefix="/admin")


# ---------------------------------------------------------------------------
# AI settings schema — defines groups, fields, types, and code defaults.
# ---------------------------------------------------------------------------

_PROVIDER_IDS = ('openai', 'azure', 'copilot', 'gemini')
_PROVIDERS_META = [
    {'id': 'openai', 'label': 'OpenAI', 'icon': 'fas fa-robot'},
    {'id': 'azure', 'label': 'Azure OpenAI', 'icon': 'fab fa-microsoft'},
    {'id': 'copilot', 'label': 'GitHub Copilot', 'icon': 'fab fa-github'},
    {'id': 'gemini', 'label': 'Google Gemini', 'icon': 'fas fa-gem'},
]


def _build_ai_groups():
    """Return AI settings groups with current effective values for the template.

    Each field dict contains: key, label, type, help, value, default, is_set, (options).
    ``is_set`` is 'db' when the value comes from the database, 'env' when it comes
    from an environment variable / Config, or '' when using the code default.
    """
    from app.utils.app_settings import get_ai_settings, AI_SENSITIVE_KEYS

    ai_db = get_ai_settings()

    # -- helpers ----------------------------------------------------------
    # Sensitive keys (API keys, secrets) are env-only: never read from or write to DB.
    # All other keys are DB-only: value from DB or code default, never from env.

    def _sensitive(key):
        return key in AI_SENSITIVE_KEYS

    def _effective(key, default=None):
        if _sensitive(key):
            return getattr(Config, key, default)
        db_v = ai_db.get(key)
        if db_v is not None and (not isinstance(db_v, str) or db_v.strip()):
            return db_v
        return default

    def _source(key):
        if _sensitive(key):
            config_v = getattr(Config, key, None)
            if config_v is not None and (not isinstance(config_v, str) or str(config_v).strip()):
                return 'env'
            return ''
        db_v = ai_db.get(key)
        if db_v is not None and (not isinstance(db_v, str) or db_v.strip()):
            return 'db'
        return ''

    def _bool_val(key, default=False):
        v = _effective(key, default)
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes')
        return bool(v)

    # Field-builder shortcuts (env_only=True for sensitive so template can render read-only)
    def txt(key, label, help_text='', default=''):
        return {'key': key, 'label': label, 'type': 'text', 'help': help_text,
                'value': _effective(key, default) or '', 'default': default, 'is_set': _source(key), 'env_only': _sensitive(key)}

    def pwd(key, label, help_text=''):
        return {'key': key, 'label': label, 'type': 'password', 'help': help_text,
                'value': '', 'default': '', 'is_set': _source(key), 'env_only': _sensitive(key)}

    def num(key, label, help_text='', default=0):
        v = _effective(key, default)
        try:
            v = int(v) if v is not None else default
        except (ValueError, TypeError):
            v = default
        return {'key': key, 'label': label, 'type': 'int', 'help': help_text,
                'value': v, 'default': default, 'is_set': _source(key), 'env_only': _sensitive(key)}

    def flt(key, label, help_text='', default=0.0):
        v = _effective(key, default)
        try:
            v = float(v) if v is not None else default
        except (ValueError, TypeError):
            v = default
        return {'key': key, 'label': label, 'type': 'float', 'help': help_text,
                'value': v, 'default': default, 'is_set': _source(key), 'env_only': _sensitive(key)}

    def bln(key, label, help_text='', default=False):
        return {'key': key, 'label': label, 'type': 'bool', 'help': help_text,
                'value': _bool_val(key, default), 'default': default, 'is_set': _source(key), 'env_only': _sensitive(key)}

    def sel(key, label, options, help_text='', default=''):
        return {'key': key, 'label': label, 'type': 'select', 'help': help_text,
                'value': str(_effective(key, default) or default), 'default': default,
                'options': options, 'is_set': _source(key), 'env_only': _sensitive(key)}

    # ── Provider priority ordering ────────────────────────────────────────
    raw_priority = ai_db.get('AI_PROVIDER_PRIORITY')
    provider_order: list = list(_PROVIDER_IDS)
    if raw_priority:
        try:
            parsed = json.loads(raw_priority) if isinstance(raw_priority, str) else raw_priority
            if isinstance(parsed, list):
                seen: set = set()
                ordered: list = []
                for pid in parsed:
                    if pid in _PROVIDER_IDS and pid not in seen:
                        ordered.append(pid)
                        seen.add(pid)
                for pid in _PROVIDER_IDS:
                    if pid not in seen:
                        ordered.append(pid)
                provider_order = ordered
        except Exception:
            pass

    _provider_fields_map = {
        'openai': [
            {'type': 'heading', 'label': 'OpenAI', 'key': '_h_openai'},
            pwd('OPENAI_API_KEY', 'API Key', 'Required. Used for chat, embeddings, and agent.'),
            txt('OPENAI_MODEL', 'Model', 'LLM model for chat and agent reasoning.', 'gpt-5-mini'),
        ],
        'azure': [
            {'type': 'heading', 'label': 'Azure OpenAI', 'key': '_h_azure'},
            pwd('AZURE_OPENAI_KEY', 'API Key', 'Azure-hosted OpenAI.'),
            txt('AZURE_OPENAI_ENDPOINT', 'Endpoint', 'Azure OpenAI endpoint URL.'),
            txt('AZURE_OPENAI_DEPLOYMENT', 'Deployment', 'Azure OpenAI deployment name.'),
            txt('AZURE_OPENAI_API_VERSION', 'API Version', 'Azure OpenAI API version string.'),
        ],
        'copilot': [
            {'type': 'heading', 'label': 'GitHub Copilot', 'key': '_h_copilot'},
            pwd('COPILOT_API_KEY', 'API Key', 'GitHub Copilot.'),
            txt('COPILOT_API_ENDPOINT', 'Endpoint', 'Copilot API endpoint URL.'),
            txt('COPILOT_MODEL', 'Model', 'Copilot model name.'),
        ],
        'gemini': [
            {'type': 'heading', 'label': 'Google Gemini', 'key': '_h_gemini'},
            pwd('GEMINI_API_KEY', 'API Key', 'Google Gemini.'),
        ],
    }

    # Build per-provider blocks for tabbed UI (each block: id, label, fields)
    _provider_blocks: list = []
    for _idx, _pid in enumerate(provider_order):
        _num = _idx + 1
        _suffix = ' (Primary)' if _idx == 0 else ' (Fallback)'
        _pfields = list(_provider_fields_map.get(_pid, []))
        if _pfields:
            _heading = dict(_pfields[0])
            _heading['label'] = f'{_num}. {_heading["label"]}{_suffix}'
            _block_fields = [_heading] + _pfields[1:]
            _meta = next((p for p in _PROVIDERS_META if p['id'] == _pid), {})
            _provider_blocks.append({
                'id': _pid,
                'label': _meta.get('label', _pid),
                'icon': _meta.get('icon', 'fas fa-key'),
                'fields': _block_fields,
            })

    _providers_meta_ordered = [p for pid in provider_order for p in _PROVIDERS_META if p['id'] == pid]
    _provider_other_fields = [
        {'type': 'heading', 'label': 'Other Provider Keys', 'key': '_h_other'},
        pwd('COHERE_API_KEY', 'Cohere API Key', 'Required when reranking provider is Cohere.'),
    ]
    # Flat fields list for groups that don't use provider_blocks (e.g. settings count)
    _all_provider_fields = []
    for _b in _provider_blocks:
        _all_provider_fields.extend(_b['fields'])
    _all_provider_fields.extend(_provider_other_fields)

    return [
        {
            'id': 'providers',
            'title': 'Providers & API Keys',
            'icon': 'fas fa-key',
            'description': 'Configure API keys for each AI provider. Click a provider to edit its settings; drag to change fallback order.',
            'provider_order': provider_order,
            'providers_meta_ordered': _providers_meta_ordered,
            'provider_blocks': _provider_blocks,
            'provider_other_fields': _provider_other_fields,
            'fields': _all_provider_fields,
        },
        {
            'id': 'core',
            'title': 'Core Features',
            'icon': 'fas fa-robot',
            'description': 'Enable or disable major AI capabilities.',
            'fields': [
                bln('CHATBOT_ENABLED', 'Chatbot Enabled', 'Enable the AI chatbot across the application.', True),
                {**num('CHATBOT_MAX_HISTORY', 'Chatbot Max History', 'Maximum messages kept in chat context.', 10),
                 'show_when': [{'field': 'CHATBOT_ENABLED', 'eq': True}]},
                {**bln('CHATBOT_ORG_ONLY', 'Restrict Chatbot to Org Users', 'When enabled, only users whose email address matches the organization\'s email domain (configured in Branding settings) can see and access the chatbot. All other authenticated users will have the chatbot hidden.', False),
                 'show_when': [{'field': 'CHATBOT_ENABLED', 'eq': True}]},
                bln('AI_AGENT_ENABLED', 'Agent Enabled', 'Enable agentic reasoning with tool use.', True),
                bln('AI_MULTIMODAL_ENABLED', 'Multimodal Enabled', 'Enable image extraction and analysis from documents.', True),
                bln('AI_OCR_ENABLED', 'OCR Enabled', 'Enable OCR for scanned PDFs (requires Tesseract).', True),
            ],
        },
        {
            'id': 'embedding',
            'title': 'Embedding Configuration',
            'icon': 'fas fa-project-diagram',
            'description': 'Configure document embedding for semantic search. Changing dimensions requires a DB migration and re-embedding.',
            'fields': [
                sel('AI_EMBEDDING_PROVIDER', 'Embedding Provider', [
                    {'value': 'openai', 'label': 'OpenAI'},
                    {'value': 'local', 'label': 'Local'},
                ], 'Provider for generating document embeddings.', 'openai'),
                {**txt('AI_EMBEDDING_MODEL', 'Embedding Model', 'Model name for embeddings.', 'text-embedding-3-small'),
                 'show_when': [{'field': 'AI_EMBEDDING_PROVIDER', 'eq': 'openai'}]},
                num('AI_EMBEDDING_DIMENSIONS', 'Embedding Dimensions', 'Must match the pgvector column. Changing requires migration.', 1536),
            ],
        },
        {
            'id': 'document',
            'title': 'Document Processing',
            'icon': 'fas fa-file-alt',
            'description': 'Configure how documents are processed, chunked, and indexed.',
            'fields': [
                num('AI_MAX_DOCUMENT_SIZE_MB', 'Max Document Size (MB)', 'Maximum file size for AI processing.', 50),
                num('AI_CHUNK_SIZE', 'Chunk Size (tokens)', 'Smaller = more precise, larger = more context.', 512),
                num('AI_CHUNK_OVERLAP', 'Chunk Overlap (tokens)', 'Overlap to maintain context across chunk boundaries.', 50),
                bln('AI_TABLE_EXTRACTION_ENABLED', 'Table Extraction', 'Extract tables from PDFs into structured chunks.', True),
                {**bln('AI_EXCLUDE_TABLE_TEXT_FROM_PDF_TEXT', 'Exclude Table Text from PDF', 'Remove table-area text from page text to avoid duplication.', True),
                 'show_when': [{'field': 'AI_TABLE_EXTRACTION_ENABLED', 'eq': True}]},
                {**bln('AI_TABLE_EXTRACT_COLORS_ENABLED', 'Extract Table Colors', 'Extract cell background colors (slower, raster sampling).', False),
                 'show_when': [{'field': 'AI_TABLE_EXTRACTION_ENABLED', 'eq': True}]},
            ],
        },
        {
            'id': 'search',
            'title': 'Search & Reranking',
            'icon': 'fas fa-search',
            'description': 'Configure vector search parameters and reranking behavior.',
            'fields': [
                num('AI_TOP_K_RESULTS', 'Top K Results', 'Number of results from semantic search.', 5),
                bln('AI_RERANK_ENABLED', 'Reranking Enabled', 'Rerank with cross-encoder for better precision.', False),
                {**sel('AI_RERANK_PROVIDER', 'Rerank Provider', [
                    {'value': 'cohere', 'label': 'Cohere'},
                    {'value': 'local', 'label': 'Local (cross-encoder)'},
                ], 'Provider for reranking results.', 'cohere'),
                 'show_when': [{'field': 'AI_RERANK_ENABLED', 'eq': True}]},
                {**num('AI_RERANK_TOP_K', 'Rerank Top K', 'Results to return after reranking.', 20),
                 'show_when': [{'field': 'AI_RERANK_ENABLED', 'eq': True}]},
                {**txt('AI_RERANK_LOCAL_MODEL', 'Local Rerank Model', 'Cross-encoder model for local reranking.', 'cross-encoder/ms-marco-MiniLM-L-6-v2'),
                 'show_when': [{'field': 'AI_RERANK_ENABLED', 'eq': True}, {'field': 'AI_RERANK_PROVIDER', 'eq': 'local'}]},
                {**txt('AI_RERANK_COHERE_MODEL', 'Cohere Rerank Model', 'Cohere reranking model name.', 'rerank-v3.5'),
                 'show_when': [{'field': 'AI_RERANK_ENABLED', 'eq': True}, {'field': 'AI_RERANK_PROVIDER', 'eq': 'cohere'}]},
                num('AI_DOCUMENT_DIVERSITY_MAX_CHUNKS_PER_DOC', 'Max Chunks per Document', 'Limit chunks per document in results (0 = no cap).', 10),
                num('AI_DOCUMENT_SEARCH_MAX_TOP_K_LIST', 'Max Top K (List Queries)', 'Max chunks for broad list-style queries.', 500),
                flt('AI_DOCUMENT_SEARCH_MIN_SCORE', 'Min Score Threshold', 'Minimum hybrid score to keep a chunk (0 disables).', 0.3),
                bln('AI_DOCUMENT_SEARCH_SANITIZE_QUERY', 'Sanitize Search Query', 'Simplify boolean-heavy queries for semantic retrieval.', True),
            ],
        },
        {
            'id': 'agent',
            'title': 'Agent & Function Calling',
            'icon': 'fas fa-cogs',
            'description': 'Configure agent behavior, function calling, and query processing.',
            'fields': [
                bln('AI_USE_NATIVE_FUNCTION_CALLING', 'Native Function Calling', 'Use provider-native function calling (recommended).', True),
                {**sel('AI_FUNCTION_CALLING_PROVIDER', 'Function Calling Provider', [
                    {'value': 'openai', 'label': 'OpenAI'},
                    {'value': 'gemini', 'label': 'Gemini'},
                ], 'Provider for function calling.', 'openai'),
                 'show_when': [{'field': 'AI_USE_NATIVE_FUNCTION_CALLING', 'eq': True}]},
                {**num('AI_AGENT_SEARCH_DOCS_MAX_CALLS', 'Max Document Search Calls', 'Max search_documents calls per agent run.', 5),
                 'show_when': [{'field': 'AI_AGENT_ENABLED', 'eq': True}]},
                {**num('AI_AGENT_MAX_COMPLETION_TOKENS', 'Max Completion Tokens', 'Max tokens per agent LLM turn (32768 allows full all-countries tables).', 32768),
                 'show_when': [{'field': 'AI_AGENT_ENABLED', 'eq': True}]},
                bln('AI_QUERY_REWRITE_ENABLED', 'Query Rewrite', 'Rewrite user messages before passing to agent/LLM.', True),
                {**txt('AI_QUERY_REWRITE_MODEL', 'Query Rewrite Model', 'Model for query rewrite (blank = same as main model).'),
                 'show_when': [{'field': 'AI_QUERY_REWRITE_ENABLED', 'eq': True}]},
                bln('AI_RESPONSE_REVISION_ENABLED', 'Response Revision', 'Polish final responses through LLM (increases cost).', False),
                {**num('AI_RESPONSE_REVISION_MAX_TOKENS', 'Revision Max Tokens', 'Max tokens for response revision.', 1500),
                 'show_when': [{'field': 'AI_RESPONSE_REVISION_ENABLED', 'eq': True}]},
                num('AI_MAX_MESSAGE_CHARS', 'Max Message Characters', 'Maximum characters per chat message.', 4000),
            ],
        },
        {
            'id': 'quality',
            'title': 'Quality Assurance',
            'icon': 'fas fa-clipboard-check',
            'description': 'Configure automatic quality evaluation of AI responses. The LLM judge sends a separate LLM call to rate each response for relevance, accuracy, and completeness.',
            'fields': [
                bln('AI_ANSWER_VERIFICATION_ENABLED', 'Answer Verification', 'Verify answer claims against source documents before responding.', True),
                bln('AI_GROUNDING_LLM_ENABLED', 'LLM Quality Judge', 'Run a separate LLM call to evaluate each response for relevance, accuracy, and completeness. Increases cost per query.', False),
                {**txt('AI_GROUNDING_LLM_MODEL', 'Judge Model', 'Model for quality evaluation (blank = same as main model). A smaller/cheaper model is recommended.'),
                 'show_when': [{'field': 'AI_GROUNDING_LLM_ENABLED', 'eq': True}]},
                {**flt('AI_GROUNDING_REVIEW_THRESHOLD', 'Review Threshold', 'Grounding score below this auto-queues the trace for human review.', 0.5),
                 'show_when': [{'field': 'AI_GROUNDING_LLM_ENABLED', 'eq': True}]},
            ],
        },
        {
            'id': 'indicators',
            'title': 'Indicator Resolution',
            'icon': 'fas fa-chart-bar',
            'description': 'Configure how user phrases are mapped to indicators in the Indicator Bank.',
            'fields': [
                sel('AI_INDICATOR_RESOLUTION_METHOD', 'Resolution Method', [
                    {'value': 'vector', 'label': 'Vector (semantic search)'},
                    {'value': 'vector_then_llm', 'label': 'Vector + LLM (most accurate)'},
                    {'value': 'keyword', 'label': 'Keyword (legacy ILIKE)'},
                ], 'How to map user phrases to indicators.', 'vector'),
                {**bln('AI_INDICATOR_LLM_DISAMBIGUATE', 'LLM Disambiguation', 'Use LLM to pick from top-k vector results.', True),
                 'show_when': [{'field': 'AI_INDICATOR_RESOLUTION_METHOD', 'eq': 'vector_then_llm'}]},
                {**num('AI_INDICATOR_TOP_K', 'Indicator Top K', 'Candidates from vector search.', 10),
                 'show_when': [{'field': 'AI_INDICATOR_RESOLUTION_METHOD', 'not_eq': 'keyword'}]},
                num('AI_INDICATOR_MAX_COUNTRIES', 'Max Countries', 'Max countries in bulk indicator tools.', 250),
            ],
        },
        {
            'id': 'caching',
            'title': 'Caching',
            'icon': 'fas fa-bolt',
            'description': 'Configure tool result caching to reduce redundant API calls.',
            'fields': [
                bln('AI_TOOL_CACHE_ENABLED', 'Tool Cache Enabled', 'Cache tool results to reduce repeated calls.', True),
                {**num('AI_TOOL_CACHE_TTL_SECONDS', 'Cache TTL (seconds)', 'Time-to-live for cached tool results.', 300),
                 'show_when': [{'field': 'AI_TOOL_CACHE_ENABLED', 'eq': True}]},
            ],
        },
        {
            'id': 'persistence',
            'title': 'Chat Persistence & Archiving',
            'icon': 'fas fa-archive',
            'description': 'Configure conversation retention, archiving, and export limits.',
            'fields': [
                bln('AI_CHAT_RETENTION_ENABLED', 'Retention Enabled', 'Enable automated archiving and purging.', True),
                {**sel('AI_CHAT_ARCHIVE_PROVIDER', 'Archive Provider', [
                    {'value': 'filesystem', 'label': 'Filesystem'},
                    {'value': 'azure_blob', 'label': 'Azure Blob Storage'},
                ], 'Where to store archived conversations.', 'filesystem'),
                 'show_when': [{'field': 'AI_CHAT_RETENTION_ENABLED', 'eq': True}]},
                {**num('AI_CHAT_ARCHIVE_AFTER_DAYS', 'Archive After (days)', 'Archive conversations older than this.', 90),
                 'show_when': [{'field': 'AI_CHAT_RETENTION_ENABLED', 'eq': True}]},
                {**num('AI_CHAT_PURGE_AFTER_DAYS', 'Purge After (days)', 'Delete conversations and archives older than this.', 365),
                 'show_when': [{'field': 'AI_CHAT_RETENTION_ENABLED', 'eq': True}]},
                {**txt('AI_CHAT_ARCHIVE_DIR', 'Archive Directory', 'Subfolder under UPLOAD_FOLDER for filesystem archives.', 'ai_chat_archives'),
                 'show_when': [{'field': 'AI_CHAT_RETENTION_ENABLED', 'eq': True}, {'field': 'AI_CHAT_ARCHIVE_PROVIDER', 'eq': 'filesystem'}]},
                {**num('AI_CHAT_MAINTENANCE_BATCH_SIZE', 'Maintenance Batch Size', 'Batch size for archive/purge jobs.', 200),
                 'show_when': [{'field': 'AI_CHAT_RETENTION_ENABLED', 'eq': True}]},
                num('AI_CHAT_EXPORT_MAX_MESSAGES', 'Export Max Messages', 'Max messages per export.', 5000),
                num('AI_CHAT_EXPORT_MAX_BYTES', 'Export Max Bytes', 'Max export file size in bytes.', 10485760),
                {**pwd('AI_CHAT_ARCHIVE_ENCRYPTION_KEY', 'Archive Encryption Key', 'Fernet key for archive encryption (optional).'),
                 'show_when': [{'field': 'AI_CHAT_RETENTION_ENABLED', 'eq': True}]},
                {**pwd('AI_CHAT_ARCHIVE_AZURE_CONNECTION_STRING', 'Azure Connection String', 'Azure Blob connection string (for azure_blob provider).'),
                 'show_when': [{'field': 'AI_CHAT_RETENTION_ENABLED', 'eq': True}, {'field': 'AI_CHAT_ARCHIVE_PROVIDER', 'eq': 'azure_blob'}]},
                {**txt('AI_CHAT_ARCHIVE_AZURE_CONTAINER', 'Azure Container Name', 'Azure Blob container name.', 'ai-chat-archives'),
                 'show_when': [{'field': 'AI_CHAT_RETENTION_ENABLED', 'eq': True}, {'field': 'AI_CHAT_ARCHIVE_PROVIDER', 'eq': 'azure_blob'}]},
                txt('REDIS_URL', 'Redis URL', 'Optional Redis for cross-worker rate limiting.'),
            ],
        },
    ]


def _normalize_localized_value(value):
    """Ensure localized values are returned as dicts keyed by ISO language code."""
    if isinstance(value, dict):
        normalized = {}
        for lang, text in value.items():
            if text is None:
                continue
            trimmed = str(text).strip()
            if trimmed:
                normalized[lang] = trimmed
        return normalized
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed:
            return {"en": trimmed}
    return {}

def _b64decode_utf8(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        return base64.b64decode(value.encode("ascii"), validate=True).decode("utf-8", errors="strict")
    except Exception as e:
        current_app.logger.debug("base64 decode failed: %s", e)
        return ""


@bp.route("/settings", methods=["GET", "POST"])
@admin_permission_required('admin.settings.manage')
def manage_settings():
    """Admin settings page. Currently supports managing supported languages."""
    from app.utils.app_settings import (
        get_supported_languages,
        set_supported_languages,
        get_show_language_flags,
        set_show_language_flags,
        get_document_types,
        set_document_types,
        get_age_groups,
        set_age_groups,
        get_sex_categories,
        set_sex_categories,
        get_list_translations,
        set_list_translations,
        get_enabled_entity_types,
        set_enabled_entity_types,
        get_organization_branding,
        set_organization_branding,
        get_chatbot_name,
        set_chatbot_name,
        get_ai_beta_access_settings,
        set_ai_beta_access_settings,
        get_all_email_templates,
        set_all_email_templates,
        get_template_metadata,
        get_notification_priorities,
        set_notification_priorities,
    )

    # Offer the full ISO-639-1 list in the UI (searchable multi-select in template).
    # Note: enabling a language only makes it selectable; actual UI translation still
    # depends on having translation catalogs under translations/<lang>/...
    all_known_languages = list(getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", {}).keys()) or list(
        Config.LANGUAGE_DISPLAY_NAMES.keys()
    )
    current_supported = get_supported_languages(default=Config.LANGUAGES)
    current_doc_types = get_document_types(default=Config.DOCUMENT_TYPES)
    current_age_groups = get_age_groups(default=Config.DEFAULT_AGE_GROUPS)
    current_sex_categories = get_sex_categories(default=Config.DEFAULT_SEX_CATEGORIES)
    current_entity_types = get_enabled_entity_types(default=Config.ENABLED_ENTITY_TYPES)
    current_show_language_flags = get_show_language_flags(default=True)
    current_branding = get_organization_branding()
    current_chatbot_name = get_chatbot_name(default="")
    org_name_translations = _normalize_localized_value(current_branding.get("organization_name"))
    org_short_name_translations = _normalize_localized_value(current_branding.get("organization_short_name"))
    org_name_en_value = org_name_translations.get("en", "")
    org_short_name_en_value = org_short_name_translations.get("en", "")
    if not org_name_en_value and isinstance(current_branding.get("organization_name"), str):
        org_name_en_value = current_branding.get("organization_name").strip()
    if not org_short_name_en_value and isinstance(current_branding.get("organization_short_name"), str):
        org_short_name_en_value = current_branding.get("organization_short_name").strip()
    org_name_translations_json = json.dumps(org_name_translations or {}, ensure_ascii=False)
    org_short_name_translations_json = json.dumps(org_short_name_translations or {}, ensure_ascii=False)
    current_email_templates = get_all_email_templates()
    current_template_metadata = get_template_metadata()

    # Translations for list-type settings
    doc_types_translations = get_list_translations("document_types")
    age_groups_translations = get_list_translations("age_groups")
    sex_categories_translations = get_list_translations("sex_categories")

    # AI settings groups for the template
    ai_groups = _build_ai_groups()
    ai_beta_settings = get_ai_beta_access_settings(default_enabled=False)
    ai_beta_enabled = bool(ai_beta_settings.get("enabled", False))
    ai_beta_allowed_user_ids = [int(uid) for uid in (ai_beta_settings.get("allowed_user_ids") or []) if str(uid).strip().isdigit()]
    ai_beta_user_options = []
    with suppress(Exception):
        from app.models import User

        users = (
            User.query.filter(User.active.is_(True))
            .order_by(User.email.asc())
            .all()
        )
        ai_beta_user_options = [
            {
                "id": int(user.id),
                "name": (str(getattr(user, "name", "") or "").strip() or str(getattr(user, "email", "") or "").strip()),
                "email": str(getattr(user, "email", "") or "").strip(),
            }
            for user in users
            if getattr(user, "id", None)
        ]

    # Notification priorities (per notification type)
    from app.models.enums import NotificationType
    notification_type_labels = [
        (nt.value, nt.value.replace("_", " ").title())
        for nt in NotificationType
    ]
    notification_priorities = get_notification_priorities()

    if request.method == "POST":
        data = get_request_data()
        # If the client sends a base64-wrapped payload, decode it into a form-like object.
        # This avoids WAF false positives on rich strings (JSON blobs, URLs, etc.) while keeping
        # server-side logic unchanged.
        try:
            payload = data.get("payload") or data.get("payload_b64")
        except Exception:
            payload = None
        if payload:
            try:
                from app.utils.request_utils import _JsonFormProxy  # local import to avoid API surface changes

                decoded = base64.b64decode(str(payload)).decode("utf-8")
                decoded_obj = json.loads(decoded)
                if not isinstance(decoded_obj, dict):
                    return json_bad_request("Invalid settings payload")
                data = _JsonFormProxy(decoded_obj)
            except Exception:
                return json_bad_request("Invalid settings payload")
        try:
            from flask_login import current_user
            user_id = current_user.id if current_user.is_authenticated else None
            previous_supported = set(current_supported or [])

            # Languages
            selected_list = data.getlist("languages") or []
            selected_set = {str(c).lower() for c in (selected_list or []) if str(c).strip()}
            selected_set.add("en")  # English is always enabled
            languages_order_raw = (data.get("languages_order") or "").strip()
            if languages_order_raw:
                ordered = [c.strip().lower() for c in languages_order_raw.split(",") if c and c.strip()]
                # Filter to what is actually selected, preserve posted order
                selected = [c for c in ordered if c in selected_set]
                # Append any selected languages that weren't included in the order payload
                for c in selected_list:
                    code = str(c).strip().lower()
                    if code and code in selected_set and code not in selected:
                        selected.append(code)
            else:
                selected = selected_list or ["en"]
            langs_ok = set_supported_languages(selected, user_id=user_id)

            # Show/hide flags in language selectors
            # Checkbox posts value only when checked; default to off when missing.
            show_flags = data.get("show_language_flags") == "1"
            flags_ok = set_show_language_flags(show_flags, user_id=user_id)

            # Document types (structured list of inputs)
            doc_types_list = data.getlist("document_types[]")
            docs_ok = set_document_types(doc_types_list, user_id=user_id)

            # Age groups (ordered list)
            age_groups_list = data.getlist("age_groups[]")
            ages_ok = set_age_groups(age_groups_list, user_id=user_id)

            # Sex categories (ordered list)
            sex_cats_list = data.getlist("sex_categories[]")
            sex_ok = set_sex_categories(sex_cats_list, user_id=user_id)

            # Translations for list-type settings (JSON hidden inputs)
            for skey in ("document_types", "age_groups", "sex_categories"):
                raw = data.get(f"{skey}_translations", "").strip()
                if raw:
                    try:
                        trans = json.loads(raw)
                        set_list_translations(skey, trans, user_id=user_id)
                    except (json.JSONDecodeError, ValueError):
                        pass

            entity_type_choices = data.getlist("enabled_entity_types[]")
            entity_types_ok = set_enabled_entity_types(entity_type_choices or ['countries'], user_id=user_id)

            # Chatbot display name
            chatbot_name_ok = True
            if "chatbot_name" in data:
                try:
                    chatbot_name_ok = set_chatbot_name(data.get("chatbot_name", ""), user_id=user_id)
                except ValueError:
                    flash("Chatbot name is invalid.", "danger")
                    chatbot_name_ok = False

            # Organization branding (JSON object with localized support)
            branding_ok = True
            if "organization_name_translations" in data or "organization_name_en" in data or "organization_name" in data:
                # Try to get translations from JSON hidden input (new modal approach)
                org_name_localized = {}
                org_short_name_localized = {}

                # Check for JSON translations from modals
                if "organization_name_translations" in data:
                    try:
                        translations_json = data.get("organization_name_translations", "").strip()
                        if translations_json:
                            org_name_localized = json.loads(translations_json)
                            # Filter out empty values
                            org_name_localized = {k: v for k, v in org_name_localized.items() if v and v.strip()}
                    except (json.JSONDecodeError, ValueError):
                        # Fall through to per-language collection
                        pass

                if "organization_short_name_translations" in data:
                    try:
                        translations_json = data.get("organization_short_name_translations", "").strip()
                        if translations_json:
                            org_short_name_localized = json.loads(translations_json)
                            # Filter out empty values
                            org_short_name_localized = {k: v for k, v in org_short_name_localized.items() if v and v.strip()}
                    except (json.JSONDecodeError, ValueError):
                        # Fall through to per-language collection
                        pass

                # Fallback: Collect from per-language fields (legacy approach)
                if not org_name_localized:
                    # Get supported languages
                    supported_langs = get_supported_languages(default=Config.LANGUAGES)

                    # Collect organization_name for each language
                    for lang in supported_langs:
                        name_key = f"organization_name_{lang}"
                        if name_key in data:
                            value = data.get(name_key, "").strip()
                            if value:
                                org_name_localized[lang] = value
                        # Also check legacy single field
                        elif lang == 'en' and "organization_name" in data:
                            value = data.get("organization_name", "").strip()
                            if value:
                                org_name_localized[lang] = value

                if not org_short_name_localized:
                    # Get supported languages
                    supported_langs = get_supported_languages(default=Config.LANGUAGES)

                    # Collect organization_short_name for each language
                    for lang in supported_langs:
                        short_name_key = f"organization_short_name_{lang}"
                        if short_name_key in data:
                            value = data.get(short_name_key, "").strip()
                            if value:
                                org_short_name_localized[lang] = value
                        # Also check legacy single field
                        elif lang == 'en' and "organization_short_name" in data:
                            value = data.get("organization_short_name", "").strip()
                            if value:
                                org_short_name_localized[lang] = value

                # Ensure at least English is provided for organization_name
                if not org_name_localized or 'en' not in org_name_localized:
                    # Try legacy field
                    legacy_name = data.get("organization_name", "").strip()
                    if legacy_name:
                        org_name_localized = {'en': legacy_name}
                    elif org_name_localized:
                        # If we have other languages but no English, use first available
                        first_lang = next(iter(org_name_localized.keys()))
                        org_name_localized['en'] = org_name_localized[first_lang]
                    else:
                        org_name_localized = {}

                # Build branding data
                branding_data = {
                    "organization_name": org_name_localized if org_name_localized else data.get("organization_name", "").strip(),
                    "organization_short_name": org_short_name_localized if org_short_name_localized else data.get("organization_short_name", "").strip(),
                    "organization_domain": data.get("organization_domain", "").strip(),
                    "organization_email_domain": data.get("organization_email_domain", "").strip(),
                    "organization_logo_path": data.get("organization_logo_path", "").strip(),
                    "organization_favicon_path": data.get("organization_favicon_path", "").strip(),
                    "organization_copyright_year": data.get("organization_copyright_year", "").strip(),
                    # Optional branding-managed external links
                    "indicator_details_url_template": data.get("indicator_details_url_template", "").strip(),
                    "propose_new_indicator_url": data.get("propose_new_indicator_url", "").strip(),
                }

                # Remove empty optional fields
                if not branding_data["organization_email_domain"]:
                    branding_data["organization_email_domain"] = branding_data["organization_domain"]
                if not branding_data["organization_logo_path"]:
                    branding_data.pop("organization_logo_path", None)
                if not branding_data.get("organization_favicon_path"):
                    branding_data.pop("organization_favicon_path", None)
                if not branding_data["organization_copyright_year"]:
                    from datetime import datetime
                    branding_data["organization_copyright_year"] = str(datetime.now().year)
                if not branding_data.get("indicator_details_url_template"):
                    branding_data.pop("indicator_details_url_template", None)
                if not branding_data.get("propose_new_indicator_url"):
                    branding_data.pop("propose_new_indicator_url", None)

                try:
                    branding_ok = set_organization_branding(branding_data, user_id=user_id)
                except ValueError as e:
                    flash("An error occurred. Please try again.", "danger")
                    branding_ok = False
            else:
                branding_ok = True

            # Email templates (multilingual: each key → {lang: content})
            templates_ok = True
            if data.get("email_templates_present") == "1":
                from app.utils.app_settings import EMAIL_TEMPLATE_KEYS
                email_templates_data: dict = {}
                for tpl_key in EMAIL_TEMPLATE_KEYS:
                    translations_field = f"{tpl_key}_translations"
                    raw_json = data.get(translations_field, "").strip()
                    if raw_json:
                        try:
                            lang_dict = json.loads(raw_json)
                            if isinstance(lang_dict, dict):
                                email_templates_data[tpl_key] = {
                                    lang: content
                                    for lang, content in lang_dict.items()
                                    if isinstance(content, str) and content.strip()
                                }
                            else:
                                email_templates_data[tpl_key] = {}
                        except (json.JSONDecodeError, ValueError):
                            email_templates_data[tpl_key] = {}
                    else:
                        email_templates_data[tpl_key] = {}
                template_metadata = {}
                metadata_raw = data.get("template_metadata_json", "").strip()
                if metadata_raw:
                    try:
                        template_metadata = json.loads(metadata_raw)
                        if not isinstance(template_metadata, dict):
                            template_metadata = {}
                    except (json.JSONDecodeError, ValueError):
                        template_metadata = {}
                try:
                    templates_ok = set_all_email_templates(
                        email_templates_data,
                        metadata=template_metadata,
                        user_id=user_id,
                    )
                except ValueError as e:
                    flash("Email template error.", "danger")
                    templates_ok = False
            else:
                templates_ok = True

            # Notification priorities
            notif_priorities_ok = True
            try:
                notif_priorities = {}
                for nt in NotificationType:
                    key = nt.value
                    val = data.get(f"notification_priority_{key}", "normal").strip().lower()
                    if val in ("normal", "high", "urgent", "low"):
                        notif_priorities[key] = val
                notif_priorities_ok = set_notification_priorities(notif_priorities, user_id=user_id)
            except Exception as e:
                current_app.logger.debug("set_notification_priorities failed: %s", e)
                notif_priorities_ok = False

            # AI Settings
            ai_ok = True
            if data.get("ai_settings_present") == "1":
                from app.utils.app_settings import get_ai_settings, set_ai_settings, AI_SENSITIVE_KEYS
                existing_ai = dict(get_ai_settings())
                # Sensitive keys are env-only; do not save from form
                existing_ai = {k: v for k, v in existing_ai.items() if k not in AI_SENSITIVE_KEYS}
                ai_schema_groups = _build_ai_groups()

                for group in ai_schema_groups:
                    for field in group['fields']:
                        if field['type'] == 'heading':
                            continue
                        key = field['key']
                        if key in AI_SENSITIVE_KEYS:
                            continue
                        form_key = f"ai_{key}"

                        if field['type'] == 'password':
                            if data.get(f"{form_key}_clear") == "1":
                                existing_ai.pop(key, None)
                            else:
                                new_val = data.get(form_key, '').strip()
                                if new_val:
                                    existing_ai[key] = new_val
                        elif field['type'] == 'bool':
                            existing_ai[key] = data.get(form_key) == '1'
                        elif field['type'] == 'int':
                            raw = data.get(form_key, '').strip()
                            if raw:
                                try:
                                    existing_ai[key] = int(raw)
                                except ValueError:
                                    existing_ai.pop(key, None)
                            else:
                                existing_ai.pop(key, None)
                        elif field['type'] == 'float':
                            raw = data.get(form_key, '').strip()
                            if raw:
                                try:
                                    existing_ai[key] = float(raw)
                                except ValueError:
                                    existing_ai.pop(key, None)
                            else:
                                existing_ai.pop(key, None)
                        elif field['type'] == 'select':
                            val = data.get(form_key, '').strip()
                            if val:
                                existing_ai[key] = val
                        else:
                            raw = data.get(form_key, '').strip()
                            if raw:
                                existing_ai[key] = raw
                            else:
                                existing_ai.pop(key, None)

                # Provider priority (serialized by drag-and-drop widget as JSON array)
                provider_priority_raw = data.get('ai_provider_priority', '').strip()
                if provider_priority_raw:
                    try:
                        plist = json.loads(provider_priority_raw)
                        if isinstance(plist, list):
                            seen_p: set = set()
                            valid_p: list = []
                            for _pid in plist:
                                if isinstance(_pid, str) and _pid in _PROVIDER_IDS and _pid not in seen_p:
                                    valid_p.append(_pid)
                                    seen_p.add(_pid)
                            for _pid in _PROVIDER_IDS:
                                if _pid not in seen_p:
                                    valid_p.append(_pid)
                            existing_ai['AI_PROVIDER_PRIORITY'] = json.dumps(valid_p)
                    except Exception:
                        pass

                try:
                    ai_ok = set_ai_settings(existing_ai, user_id=user_id)
                except Exception as e:
                    current_app.logger.debug("set_ai_settings failed: %s", e)
                    ai_ok = False

            # AI beta access gate (selected users + admins/system managers)
            ai_beta_ok = True
            try:
                beta_enabled = "1" in data.getlist("ai_beta_enabled")
                beta_allowed_user_ids = data.getlist("ai_beta_allowed_user_ids[]")
                ai_beta_ok = set_ai_beta_access_settings(
                    beta_enabled,
                    beta_allowed_user_ids,
                    user_id=user_id,
                )
            except Exception as e:
                current_app.logger.debug("set_ai_beta_access_settings failed: %s", e)
                ai_beta_ok = False

            if langs_ok and flags_ok and docs_ok and ages_ok and sex_ok and entity_types_ok and chatbot_name_ok and branding_ok and templates_ok and ai_ok and ai_beta_ok:
                # Update live app config for immediate effect
                current_app.config['SUPPORTED_LANGUAGES'] = get_supported_languages(default=Config.LANGUAGES)
                current_app.config['TRANSLATABLE_LANGUAGES'] = [c for c in current_app.config['SUPPORTED_LANGUAGES'] if c != 'en']
                current_app.config['SHOW_LANGUAGE_FLAGS'] = get_show_language_flags(default=True)
                current_app.config['DOCUMENT_TYPES'] = get_document_types(default=Config.DOCUMENT_TYPES)
                current_app.config['DEFAULT_AGE_GROUPS'] = get_age_groups(default=Config.DEFAULT_AGE_GROUPS)
                current_app.config['DEFAULT_SEX_CATEGORIES'] = get_sex_categories(default=Config.DEFAULT_SEX_CATEGORIES)
                current_app.config['ENABLED_ENTITY_TYPES'] = get_enabled_entity_types(default=Config.ENABLED_ENTITY_TYPES)
                current_app.config['ORGANIZATION_BRANDING'] = get_organization_branding()
                # Also update global Config so views referencing Config.LANGUAGES see changes
                with suppress(Exception):
                    Config.LANGUAGES = list(current_app.config['SUPPORTED_LANGUAGES'])
                    Config.TRANSLATABLE_LANGUAGES = list(current_app.config['TRANSLATABLE_LANGUAGES'])
                    Config.DOCUMENT_TYPES = list(current_app.config['DOCUMENT_TYPES'])
                    Config.DEFAULT_AGE_GROUPS = list(current_app.config['DEFAULT_AGE_GROUPS'])
                    Config.DEFAULT_SEX_CATEGORIES = list(current_app.config['DEFAULT_SEX_CATEGORIES'])
                    Config.ENABLED_ENTITY_TYPES = list(current_app.config['ENABLED_ENTITY_TYPES'])
                    Config.ORGANIZATION_BRANDING = dict(current_app.config['ORGANIZATION_BRANDING'])
                # Update Jinja globals to reflect changes without restart
                with suppress(Exception):
                    current_app.jinja_env.globals['SUPPORTED_LANGUAGES'] = current_app.config['SUPPORTED_LANGUAGES']
                    current_app.jinja_env.globals['TRANSLATABLE_LANGUAGES'] = current_app.config['TRANSLATABLE_LANGUAGES']
                    current_app.jinja_env.globals['SHOW_LANGUAGE_FLAGS'] = bool(current_app.config.get('SHOW_LANGUAGE_FLAGS', True))
                    current_app.jinja_env.globals['DOCUMENT_TYPES'] = current_app.config['DOCUMENT_TYPES']
                    current_app.jinja_env.globals['DEFAULT_AGE_GROUPS'] = current_app.config['DEFAULT_AGE_GROUPS']
                    current_app.jinja_env.globals['DEFAULT_SEX_CATEGORIES'] = current_app.config['DEFAULT_SEX_CATEGORIES']
                    current_app.jinja_env.globals['ENABLED_ENTITY_TYPES'] = current_app.config['ENABLED_ENTITY_TYPES']
                    current_app.jinja_env.globals['ORGANIZATION_BRANDING'] = current_app.config['ORGANIZATION_BRANDING']
                # Apply saved AI settings to live config
                if ai_ok and data.get("ai_settings_present") == "1":
                    with suppress(Exception):
                        from app.utils.app_settings import apply_ai_settings_to_config
                        apply_ai_settings_to_config(current_app)
                # Optionally refresh Babel context
                with suppress(Exception):
                    from flask_babel import refresh as babel_refresh
                    babel_refresh()

                # Prefetch language flags ONLY when supported languages change.
                with suppress(Exception):
                    if bool(current_app.config.get('SHOW_LANGUAGE_FLAGS', True)):
                        from app.utils.language_flags import prefetch_language_flags_to_local_cache
                        saved_supported = list(current_app.config.get('SUPPORTED_LANGUAGES') or [])
                        newly_added = sorted(set(saved_supported) - previous_supported)
                        if newly_added:
                            result = prefetch_language_flags_to_local_cache(
                                newly_added,
                                instance_path=current_app.instance_path,
                            )
                            # If some flags failed to download, warn but don't fail saving.
                            failed = result.get("failed") or []
                            if failed:
                                flash(
                                    f"Settings saved, but {len(failed)} flag(s) could not be downloaded. "
                                    f"Missing flags will show a placeholder until retried.",
                                    "warning",
                                )
                flash("Settings saved successfully.", "success")
                # Optional: restart app if requested
                if data.get('restart') == '1':
                    try:
                        import os
                        import time
                        # In debug with Werkzeug reloader, touch a watched Python module to trigger reload
                        if current_app.debug and os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
                            target_files = [
                                os.path.join(current_app.root_path, '__init__.py'),
                                os.path.join(os.path.dirname(current_app.root_path), 'config', 'config.py'),
                            ]
                            touched = False
                            for f in target_files:
                                if os.path.exists(f):
                                    now = time.time()
                                    os.utime(f, (now, now))
                                    touched = True
                            if touched:
                                flash("Development server reload triggered.", "warning")
                            else:
                                flash("Please restart the development server manually.", "warning")
                        else:
                            # For production, rely on external supervisor/orchestrator
                            flash("Please restart the application via your process manager to apply settings across all workers.", "warning")
                    except Exception as e:
                        current_app.logger.debug("config touch/restart failed: %s", e)
                        flash("Please restart the application manually to apply settings across all workers.", "warning")
            else:
                flash("Failed to save settings.", "danger")
        except Exception as e:
            flash("An error occurred. Please try again.", "danger")
        return redirect(url_for("settings.manage_settings"))

    return render_template(
        "admin/settings/manage_settings.html",
        all_known_languages=all_known_languages,
        language_names=Config.LANGUAGE_DISPLAY_NAMES,
        current_supported=current_supported,
        current_show_language_flags=current_show_language_flags,
        current_doc_types=current_doc_types,
        current_age_groups=current_age_groups,
        current_sex_categories=current_sex_categories,
        current_entity_types=current_entity_types,
        current_chatbot_name=current_chatbot_name,
        current_branding=current_branding,
        org_name_translations=org_name_translations,
        org_short_name_translations=org_short_name_translations,
        org_name_translations_json=org_name_translations_json,
        org_short_name_translations_json=org_short_name_translations_json,
        org_name_en_value=org_name_en_value,
        org_short_name_en_value=org_short_name_en_value,
        current_email_templates=current_email_templates,
        current_template_metadata=current_template_metadata,
        doc_types_translations=doc_types_translations,
        age_groups_translations=age_groups_translations,
        sex_categories_translations=sex_categories_translations,
        ai_groups=ai_groups,
        ai_beta_enabled=ai_beta_enabled,
        ai_beta_allowed_user_ids=ai_beta_allowed_user_ids,
        ai_beta_user_options=ai_beta_user_options,
        notification_type_labels=notification_type_labels,
        notification_priorities=notification_priorities,
        title="System Configuration",
    )


@bp.route("/api/settings/ai-reset", methods=["POST"])
@admin_permission_required("admin.settings.manage")
def api_ai_settings_reset():
    """Clear all DB-stored AI settings, reverting to env/code defaults."""
    from app.utils.app_settings import set_ai_settings, apply_ai_settings_to_config
    try:
        ok = set_ai_settings({}, user_id=getattr(current_user, 'id', None))
        if ok:
            with suppress(Exception):
                apply_ai_settings_to_config(current_app)
            return json_ok(message="AI settings reset to defaults.")
        return json_server_error("Failed to write settings.")
    except Exception as e:
        return json_server_error(GENERIC_ERROR_MESSAGE)


@bp.route("/api/settings/email-templates", methods=["POST"])
@admin_permission_required("admin.settings.manage")
def api_settings_email_templates():
    """
    Save email templates via JSON to avoid WAF false-positives on form-urlencoded blobs.

    Expects JSON:
      {
        "email_templates_b64": { "<tpl_key>": { "<lang>": "<base64 utf-8 html>" } },
        "template_metadata": { ... }   // optional
      }
    """
    from flask_login import current_user
    from app.utils.app_settings import EMAIL_TEMPLATE_KEYS, set_all_email_templates

    data = get_json_safe()
    templates_b64 = data.get("email_templates_b64") or {}
    metadata = data.get("template_metadata") or {}

    if templates_b64 and not isinstance(templates_b64, dict):
        return json_bad_request("email_templates_b64 must be an object")
    if metadata and not isinstance(metadata, dict):
        return json_bad_request("template_metadata must be an object")

    user_id = current_user.id if current_user.is_authenticated else None

    email_templates_data: dict = {}
    for tpl_key in EMAIL_TEMPLATE_KEYS:
        raw_lang_map = templates_b64.get(tpl_key) if isinstance(templates_b64, dict) else None
        if not raw_lang_map:
            email_templates_data[tpl_key] = {}
            continue
        if not isinstance(raw_lang_map, dict):
            email_templates_data[tpl_key] = {}
            continue

        decoded_langs: dict = {}
        for lang, encoded in raw_lang_map.items():
            if not isinstance(lang, str) or not lang.strip():
                continue
            decoded = _b64decode_utf8(encoded)
            if decoded and isinstance(decoded, str) and decoded.strip():
                decoded_langs[lang.strip()] = decoded
        email_templates_data[tpl_key] = decoded_langs

    try:
        ok = set_all_email_templates(email_templates_data, metadata=metadata, user_id=user_id)
    except ValueError as e:
        current_app.logger.warning("Email template validation failed: %s", e)
        return json_bad_request("Invalid email template data.")
    except Exception as e:
        current_app.logger.warning("Save email templates failed: %s", e, exc_info=True)
        return json_server_error("Failed to save email templates")

    return json_ok(success=ok)


@bp.route("/api/settings/languages", methods=["GET", "POST"])
@admin_permission_required('admin.settings.manage')
def api_languages_settings():
    """JSON API to get/update supported languages (for AJAX forms)."""
    from app.utils.app_settings import get_supported_languages, set_supported_languages, get_show_language_flags

    if request.method == "POST":
        previous_supported = set(current_app.config.get('SUPPORTED_LANGUAGES') or [])
        data = get_json_safe()
        langs = data.get("languages", [])
        if not isinstance(langs, list):
            return json_bad_request("languages must be a list")
        ok = set_supported_languages(langs)
        if ok:
            current_app.config['SUPPORTED_LANGUAGES'] = get_supported_languages(default=Config.LANGUAGES)
            current_app.config['TRANSLATABLE_LANGUAGES'] = [c for c in current_app.config['SUPPORTED_LANGUAGES'] if c != 'en']
            with suppress(Exception):
                Config.LANGUAGES = list(current_app.config['SUPPORTED_LANGUAGES'])
                Config.TRANSLATABLE_LANGUAGES = list(current_app.config['TRANSLATABLE_LANGUAGES'])
                current_app.jinja_env.globals['SUPPORTED_LANGUAGES'] = current_app.config['SUPPORTED_LANGUAGES']
                current_app.jinja_env.globals['TRANSLATABLE_LANGUAGES'] = current_app.config['TRANSLATABLE_LANGUAGES']
                from flask_babel import refresh as babel_refresh
                babel_refresh()
            # Prefetch flags ONLY if new languages were added.
            with suppress(Exception):
                if bool(get_show_language_flags(default=True)):
                    from app.utils.language_flags import prefetch_language_flags_to_local_cache
                    saved_supported = list(current_app.config.get('SUPPORTED_LANGUAGES') or [])
                    newly_added = sorted(set(saved_supported) - previous_supported)
                    if newly_added:
                        prefetch_language_flags_to_local_cache(
                            newly_added,
                            instance_path=current_app.instance_path,
                        )
            return json_ok(languages=current_app.config['SUPPORTED_LANGUAGES'])
        return json_server_error("Failed to persist settings")

    return json_ok(languages=get_supported_languages(default=Config.LANGUAGES))


@bp.route("/api/settings/check-updates", methods=["GET"])
@admin_permission_required('admin.settings.manage')
def api_check_updates():
    """Check GitHub for the latest release (or latest tag) and compare with current version."""
    import urllib.request
    import urllib.error

    repo = Config.GITHUB_REPO
    current = Config.APP_VERSION
    token = Config.GITHUB_TOKEN

    def _gh_request(api_path):
        """Make an authenticated (if token available) request to the GitHub API."""
        url = f"https://api.github.com{api_path}"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "Databank"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())

    # Try /releases/latest first, fall back to /tags if no releases exist
    try:
        data = _gh_request(f"/repos/{repo}/releases/latest")
        tag = data.get("tag_name", "").lstrip("vV")
        return json_ok(
            current_version=current,
            latest_version=tag,
            latest_name=data.get("name", tag),
            release_url=data.get("html_url", ""),
            published_at=data.get("published_at", ""),
            update_available=bool(tag and tag != current),
        )
    except urllib.error.HTTPError as e:
        if e.code != 404:
            msg = "GitHub API error"
            if e.code == 401:
                msg = "Invalid GITHUB_TOKEN — check your token"
            elif e.code == 403:
                msg = "GITHUB_TOKEN lacks permission or rate-limited"
            return json_error(f"{msg} ({e.code})", 502)
    except Exception as e:
        return json_error(GENERIC_ERROR_MESSAGE, 502)

    # Releases returned 404 — try tags as fallback
    try:
        tags = _gh_request(f"/repos/{repo}/tags?per_page=1")
        if tags and isinstance(tags, list) and len(tags) > 0:
            tag = tags[0].get("name", "").lstrip("vV")
            tag_url = f"https://github.com/{repo}/releases/tag/{tags[0].get('name', '')}"
            return json_ok(
                current_version=current,
                latest_version=tag,
                latest_name=tag,
                release_url=tag_url,
                published_at="",
                update_available=bool(tag and tag != current),
            )
        return json_ok(current_version=current, update_available=False, message="No releases or tags found")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            msg = "Repository not found"
            if not token:
                msg += " — if the repo is private, set GITHUB_TOKEN in your .env"
            return json_error(msg, 502)
        return json_error(f"GitHub API error ({e.code})", 502)
    except Exception as e:
        return json_error(GENERIC_ERROR_MESSAGE, 502)
