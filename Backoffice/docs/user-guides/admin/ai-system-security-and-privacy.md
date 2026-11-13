# AI system: security and privacy

This document explains how the Backoffice AI assistant works, what data may be processed by external providers, and what technical controls are in place to reduce accidental leakage of sensitive information.

## Scope

- **In scope**: AI chat (`/api/ai/v1/*`), AI Knowledge Base / RAG, workflow-doc Q&A, and the security controls around them (DLP, PII scrubbing, audit events).
- **Out of scope**: general platform security (auth, RBAC, backups), except where it directly affects the AI system.

## High-level architecture

- **Frontend**: chat UI (floating widget + immersive view) in `app/static/js/chatbot/` (ES modules; DLP dialog in `dlp-policy.js`).
- **Backend**: Flask API endpoints for AI chat in `app/routes/ai.py` (HTTP + SSE) and `app/routes/ai_ws.py` (WebSocket).
- **Orchestration**: `app/services/ai/chat/engine.py` manages the chat flow (history, retrieval, provider calls).
- **Providers**: external LLMs/embeddings (e.g., OpenAI/Gemini/Azure OpenAI depending on environment) plus optional local components.

## What data can be sent to external providers

Depending on the request type and enabled features, the backend may send some combination of:

- **User message text**
- **Conversation history** (recent messages, as needed for continuity)
- **Sanitized page context** (UI state/context to help the assistant; some high-risk fields are removed)
- **Retrieved document/workflow chunks** (for RAG answers)

Important: some AI features require external API calls (e.g., chat completion, query rewriting, embeddings), so **preventing sensitive data from being sent** is a primary security goal.

## Core privacy/security controls

### 1) Data Loss Prevention (DLP) guard on outgoing messages

Before a message can be sent to an external AI provider, the backend runs a best‑effort DLP scan (regex-based) to detect common sensitive patterns, such as:

- emails, phone numbers
- JWTs / Bearer tokens / Basic auth credentials
- private keys (any PEM or PGP private key block, including a block pasted without its END line)
- passwords / passphrases, secrets / API keys — as `key: value` or `KEY=value` assignments (env files, JSON, YAML, connection strings such as `AccountKey=`), passwords in connection URLs (`postgres://…@host` with an embedded password), and well-known provider key formats (for example OpenAI `sk-…`, AWS `AKIA…`, GitHub `ghp_…`)
- IBANs (checksum-validated) and payment card numbers (Luhn-validated) to reduce false positives

Phone detection skips number shapes that are common in data questions: lists of years, large or thousands-grouped figures, dates, IP addresses and table columns.

**User experience**

- A message is never sent or stored with a detected value in it: when it goes through, each value is replaced by a placeholder such as `[REDACTED_EMAIL]`.
- In the default `confirm` mode, emails and phone numbers are masked automatically (configurable). Credentials, keys and financial identifiers open a dialog: **Mask & send** sends the masked message, **Cancel** returns the message to the user for editing and keeps nothing.
- In `block` mode the message is rejected whatever it contains; the dialog only offers to edit it.
- Website and mobile clients receive an error naming what was detected (for example "Sensitive information detected (password). Remove it and send your message again.").
- Form-builder AI panel messages keep their email addresses and phone numbers (imported questionnaires legitimately contain them), but are screened for every other kind.

**Implementation**

- DLP logic: `app/services/ai/chat/dlp.py` (`screen_ai_message`, `evaluate_ai_message`, `mask_sensitive_text`, `mask_conversation_history`)
- DLP is applied consistently across transports:
  - HTTP JSON chat
  - SSE streaming
  - WebSocket streaming
- Conversation history supplied by the client (edit/retry of an earlier message, anonymous chat) is masked server-side before it is stored or sent to a provider.

**Configuration**

DLP is configured directly in code (not environment variables):

- `Backoffice/config/config.py`
  - `AI_DLP_ENABLED`
  - `AI_DLP_MODE`: `warn` (mask everything and send), `confirm` (default; see above), `block`
  - `AI_DLP_AUTO_MASK_KINDS`: kinds that `confirm` mode masks without asking (default: `email`, `phone`)
  - `AI_DLP_MAX_SCAN_CHARS`

### 2) PII scrubbing / redaction before external calls

In addition to DLP (which can stop a request), the system also applies **PII scrubbing** (redaction) to reduce exposure when content must be sent externally (for example, to help the model answer). Scrubbing uses the same patterns as DLP, plus long opaque tokens.

Scrubbing is applied to:

- user message text
- the user turns of conversation history (assistant turns are the model's own output and are sent as-is)
- page context (recursively)
- some query-rewriting inputs and logs

Form-builder AI panel requests skip this scrubbing so imported questionnaire text is reproduced faithfully; DLP still screens them for credentials and financial identifiers.

Implementation:

- `app/services/ai/providers/formatting.py`: `scrub_pii_text`, `scrub_pii_context`
- `app/services/ai/chat/engine.py`: applies scrubbing before provider calls

### 3) Page context minimization

The frontend can send page context to help answer UI-related questions. The backend sanitizes and scrubs this data and intentionally removes high-risk fields (for example, URLs or large raw blobs) to reduce accidental leakage.

Implementation:

- `app/utils/ai/ai_utils.py`: shared helpers such as context sanitization
- `app/services/ai/providers/formatting.py`: recursive context scrubbing

### 4) Audit logging for DLP events (without storing message content)

When DLP detects sensitive patterns, the backend writes a **security audit event** so administrators can monitor how often the guard triggers and respond to risky behavior.

Security properties:

- The audit event **does not store the user’s message**.
- It stores only **counts and kinds** of findings (e.g., `{"kind":"jwt","count":1}`), plus metadata such as transport, endpoint, and identifiers.
- `context_data.action` records what happened: `auto_masked` (masked and sent without asking), `confirm_required` (user was shown the dialog), `sent_masked` (user chose Mask & send), or `blocked`.
- Severity is `high` for credentials, keys and financial identifiers when the user was stopped or chose to send, and `medium` when they were masked automatically (for example in `warn` mode). Contact details are `medium` and `low` on the same basis.

Implementation:

- `app/services/ai/chat/dlp.py`: `log_dlp_audit_event`
- Model: `app/models/system.py` (`SecurityEvent`, `context_data` JSON)
- Admin UI:
  - Security dashboard: `/admin/security/dashboard`
  - Security events list: `/admin/security/events`

To filter for AI DLP events, look for:

- `event_type = "ai_dlp_sensitive_detected"`

### 5) Auth and access control

- The AI endpoints are protected by the same Backoffice authentication mechanisms (session-based login, and Bearer token flows where applicable).
- Admin-only pages (security dashboard/events) require appropriate permissions (see `app/routes/admin/security_dashboard.py`).

## Operational guidance (admins)

### Recommended policy

- Treat the AI assistant as **untrusted for sensitive data**.
- Encourage users to:
  - avoid sending credentials, tokens, private keys, and personal data
  - replace real identifiers with placeholders when asking for help (e.g., “<TOKEN>”, “<EMAIL>”)

### Handling a DLP spike or incident

1. Review the recent security events under `/admin/security/events` and filter by `ai_dlp_sensitive_detected`.
2. Check metadata in `context_data` for patterns (transport, client, frequency, affected accounts).
3. Consider temporarily tightening DLP mode to `block` in `Backoffice/config/config.py` and redeploying if needed.
4. If secrets may have been exposed, rotate credentials (API keys, tokens) and review access logs.

## Limitations and expectations

- DLP is **best-effort** and pattern-based; it can miss sensitive content and can also produce false positives.
- PII scrubbing is also best-effort; it reduces risk but does not guarantee full removal.
- AI output can be incorrect; users should verify important information (the UI warns about this).

## Key code locations (reference)

| Area | Path |
|------|------|
| AI chat endpoints (HTTP + SSE) | `app/routes/ai.py` |
| AI chat endpoint (WebSocket) | `app/routes/ai_ws.py` |
| Chat orchestration | `app/services/ai/chat/engine.py` |
| DLP guard + audit events | `app/services/ai/chat/dlp.py` |
| DLP dialog (chat UI) | `app/static/js/chatbot/dlp-policy.js` |
| PII scrubbing helpers | `app/services/ai/providers/formatting.py` |
| Security events model | `app/models/system.py` |
| Admin security pages | `app/routes/admin/security_dashboard.py` |

## Related documentation

- [AI Use Policy](../common/ai-use-policy.md) — User-facing policy (acceptable use, responsibilities)
- [AI Chatbot](../common/ai-chatbot.md) — Chatbot usage, access levels, RBAC, and document privacy
- [AI Knowledge Base and embeddings](ai-document-library-and-embeddings.md)
- [Data handling and privacy](../../data-reporting/data-handling-and-privacy.md)

