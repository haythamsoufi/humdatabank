# AI system: security and privacy

This document explains how the Backoffice AI assistant works, what data may be processed by external providers, and what technical controls are in place to reduce accidental leakage of sensitive information.

## Scope

- **In scope**: AI chat (`/api/ai/v2/*`), AI Document Library / RAG, workflow-doc Q&A, and the security controls around them (DLP, PII scrubbing, audit events).
- **Out of scope**: general platform security (auth, RBAC, backups), except where it directly affects the AI system.

## High-level architecture

- **Frontend**: chat UI (floating widget + immersive view) in `app/static/js/chatbot.js`.
- **Backend**: Flask API endpoints for AI chat in `app/routes/ai.py` (HTTP + SSE) and `app/routes/ai_ws.py` (WebSocket).
- **Orchestration**: `app/services/ai_chat_engine.py` manages the chat flow (history, retrieval, provider calls).
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
- JWTs / Bearer tokens
- private keys
- passwords / secrets / API keys
- IBANs and payment card numbers (with Luhn check to reduce false positives)

**User experience**

- If sensitive patterns are detected, the assistant can require **user confirmation** (“Send anyway”) or **block** the message depending on configuration.
- The UI explains the risk and encourages removing the sensitive text.

**Implementation**

- DLP logic: `app/services/ai_dlp.py` (`analyze_text`, `evaluate_ai_message`)
- DLP is applied consistently across transports:
  - HTTP JSON chat
  - SSE streaming
  - WebSocket streaming

**Configuration**

DLP is configured directly in code (not environment variables):

- `Backoffice/config/config.py`
  - `AI_DLP_ENABLED`
  - `AI_DLP_MODE` (typical values: `warn`, `confirm`, `block`)
  - `AI_DLP_MAX_SCAN_CHARS`

### 2) PII scrubbing / redaction before external calls

In addition to DLP (which can stop a request), the system also applies **PII scrubbing** (redaction) to reduce exposure when content must be sent externally (for example, to help the model answer).

Scrubbing is applied to:

- user message text
- conversation history snippets
- page context (recursively)
- some query-rewriting inputs and logs

Implementation:

- `app/services/ai_providers.py`: `scrub_pii_text`, `scrub_pii_context`
- `app/services/ai_chat_engine.py`: applies scrubbing before provider calls

### 3) Page context minimization

The frontend can send page context to help answer UI-related questions. The backend sanitizes and scrubs this data and intentionally removes high-risk fields (for example, URLs or large raw blobs) to reduce accidental leakage.

Implementation:

- `app/utils/ai_utils.py`: shared helpers such as context sanitization
- `app/services/ai_providers.py`: recursive context scrubbing

### 4) Audit logging for DLP events (without storing message content)

When DLP detects sensitive patterns, the backend writes a **security audit event** so administrators can monitor how often the guard triggers and respond to risky behavior.

Security properties:

- The audit event **does not store the user’s message**.
- It stores only **counts and kinds** of findings (e.g., `{"kind":"jwt","count":1}`), plus metadata such as transport, endpoint, and identifiers.

Implementation:

- `app/services/ai_dlp.py`: `log_dlp_audit_event`
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
| Chat orchestration | `app/services/ai_chat_engine.py` |
| DLP guard + audit events | `app/services/ai_dlp.py` |
| PII scrubbing helpers | `app/services/ai_providers.py` |
| Security events model | `app/models/system.py` |
| Admin security pages | `app/routes/admin/security_dashboard.py` |

## Related documentation

- [AI Use Policy](../common/ai-use-policy.md) — User-facing policy (acceptable use, responsibilities)
- [AI Chatbot](../common/ai-chatbot.md) — Chatbot usage, access levels, RBAC, and document privacy
- [AI Document Library and embeddings](ai-document-library-and-embeddings.md)
- [Data handling and privacy](../common/data-handling-and-privacy.md)

