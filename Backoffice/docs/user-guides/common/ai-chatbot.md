# AI Chatbot

This guide explains how to use the AI chatbot, what it can do, how access and permissions work, and how document privacy controls affect what the assistant can find and reference.

## Overview

The AI chatbot is an assistant built into the Backoffice that can answer questions about your data, search uploaded documents, and help you navigate the platform. It is available as a **floating widget** on most pages and as a **full-screen immersive view** for longer conversations.

The chatbot uses Retrieval-Augmented Generation (RAG): when you ask a question, it can search the Databank, uploaded documents, and workflow guides, then use those results as context for its answer.

## Before you start

- You need an account in the Backoffice to use the chatbot. Anonymous access is limited (see [Access levels](#access-levels) below).
- The chatbot requires at least one AI provider to be configured by your administrator (e.g. OpenAI, Gemini, or Azure OpenAI).
- AI answers can be incorrect. Always verify important information.

---

## Using the chatbot

### Starting a conversation

1. Open the chatbot widget by clicking the chat icon in the bottom-right corner of any page, or navigate to the **full-screen immersive view** from the dashboard.
2. Type your question in the input field and press **Send** (or press Enter).
3. The assistant will process your question — you may see a "thinking" indicator while it retrieves data or searches documents.

### Quick prompts

The immersive view offers example prompts to help you get started:

- "How many volunteers in Bangladesh?"
- "Volunteers in Syria over time"
- "World heatmap of volunteers by country"
- "Number of branches in Kenya"
- "Staff and local units in Nigeria"

### Conversation management

- **New chat** — Start a fresh conversation at any time.
- **Search** — Find previous conversations by keyword.
- **Delete** — Remove a single conversation or clear all conversations. Deletion is permanent.

### Data source controls

The input area includes a **data sources** button (slider icon) that lets you choose which sources the assistant searches:

| Source | What it includes |
|--------|-----------------|
| **Databank** | Indicator values, country data, and form submissions stored in the platform |
| **System documents** | Documents uploaded to the AI Document Library by administrators |
| **UPR documents** | Unified Planning and Reporting documents |

You can enable or disable each source per message. Disabling a source means the assistant will not search or retrieve from it for that request.

### Editing and retrying

- **Edit** a sent message to rephrase your question. The assistant will regenerate its answer from the edited text.
- **Retry** an assistant response if the answer was unsatisfactory.
- **Copy** any assistant response to your clipboard.

### Feedback

Use the **Like** and **Dislike** buttons on any assistant message to provide feedback. This helps administrators monitor quality and improve the system.

---

## Access levels and roles (RBAC)

The chatbot respects the platform's role-based access control. Your role determines what data the assistant can access on your behalf.

### Access levels

| Access level | Who | Chatbot capabilities |
|--------------|-----|---------------------|
| **System Manager** | Platform-wide administrator | Full access to all data, documents, countries, and tools. Exempt from per-user daily rate limits. |
| **Admin** | Organization administrator | Full access to all data, documents, and countries. Standard rate limits apply. |
| **User** (focal point, view-only, etc.) | Regular authenticated user | Access limited to assigned countries. Documents filtered by privacy settings (see below). Standard rate limits apply. |
| **Public** (anonymous) | Unauthenticated visitor via the website | Only public documents visible. No conversation persistence. Stricter rate limits. |

### What each role can see through the chatbot

#### System Manager and Admin

- All indicator data for all countries
- All documents regardless of privacy settings
- All form templates, assignments, and submissions
- System statistics and user information
- All workflow guides

#### Focal point and other authenticated users

- Indicator data for **assigned countries only** — the assistant will not return data for countries you are not assigned to
- Documents marked as **public**, documents you **own**, and documents where your role is included in the document's **allowed roles** list
- Assignments and submissions for your assigned countries
- Workflow guides available to your role

#### Anonymous / Public users

- Only documents explicitly marked as **public** (and with no role restriction, or with `public` in the allowed roles list)
- General indicator data (not scoped to specific assignments)
- No conversation persistence — history exists only in the browser session

### Permissions passed to the assistant

When you send a message, the system builds an **access context** that includes:

- Your role and access level
- Your assigned country IDs (if applicable)
- A set of permission flags (e.g. whether you can view templates, assignments, documents, users)

This context travels with every request so the assistant and its tools enforce the same boundaries as the rest of the platform. The assistant cannot bypass your permissions — if you cannot see certain data in the Backoffice UI, the assistant cannot see it either.

---

## Document privacy

Documents in the AI Document Library have privacy controls that determine who can find them through the chatbot. These controls are set by administrators when uploading or managing documents.

### Privacy fields

Each document has two visibility settings:

| Field | Values | Effect |
|-------|--------|--------|
| **Public** (`is_public`) | Yes / No | If **Yes**, the document is visible to all users (including anonymous visitors), subject to the allowed-roles filter. If **No**, only the document owner, users whose role matches `allowed_roles`, and admins can see it. |
| **Allowed roles** (`allowed_roles`) | A list of roles, or empty | If **empty** (null), any user who passes the public/ownership check can see the document. If set (e.g. `admin`, `focal_point`), only users with a matching role (plus the owner and admins) can see it. |

### Effective visibility by combination

| `is_public` | `allowed_roles` | Who can find this document |
|-------------|-----------------|---------------------------|
| Yes | Empty | Everyone, including anonymous users |
| Yes | `[admin, focal_point]` | Anonymous users and any authenticated user whose role is in the list (plus admins/system managers) |
| No | Empty | Document owner + admins/system managers only |
| No | `[focal_point]` | Document owner + focal points + admins/system managers |

**Key rules:**

- **Admins and system managers always see all documents**, regardless of privacy settings.
- **Document owners always see their own documents**, regardless of privacy settings.
- **Anonymous users** only see documents where `is_public = Yes` and either `allowed_roles` is empty or includes `public`.

### How privacy affects chatbot answers

When you ask a question that involves document search, the assistant runs a similarity search (vector or hybrid) against the AI Document Library. Before returning results, the system applies a **permission filter** that enforces the rules above. Documents you are not authorized to see are excluded from the search results entirely — the assistant will not quote, summarize, or reference content from documents outside your access.

This means two users asking the same question may receive different answers if they have access to different sets of documents.

---

## What the assistant can do (tools)

The chatbot has access to a set of tools it can use to answer your questions. These tools query live platform data — they do not rely solely on pre-trained knowledge.

### Data retrieval tools

| Tool | What it does |
|------|-------------|
| **Get indicator value** | Retrieves a specific indicator value for a country and period |
| **Get indicator time series** | Retrieves historical values for an indicator across multiple years |
| **Get indicator metadata** | Returns the definition, unit, and other details about an indicator |
| **Get indicator values for all countries** | Retrieves a specific indicator across all countries (useful for comparisons and maps) |
| **Get country information** | Returns details about a country (National Society, region, etc.) |
| **Compare countries** | Side-by-side comparison of multiple countries on selected indicators |

### Form and assignment tools

| Tool | What it does |
|------|-------------|
| **Get form field value** | Retrieves a specific field value from a form submission |
| **Get assignment indicator values** | Retrieves indicator values from a specific assignment |
| **Get user assignments** | Lists your assignments (or all assignments for admins) |
| **Get template details** | Returns the structure and fields of a form template |

### Document search tools

| Tool | What it does |
|------|-------------|
| **List documents** | Lists available documents (filtered by your permissions) |
| **Search documents** | Semantic (vector) search across document content |
| **Search documents (hybrid)** | Combined keyword + semantic search for better recall |

### UPR tools

| Tool | What it does |
|------|-------------|
| **Get UPR KPI value** | Retrieves a Unified Planning and Reporting KPI value |
| **Get UPR KPI time series** | Historical UPR KPI values over time |
| **Get UPR KPI values for all countries** | UPR KPI values across all countries |
| **Analyze unified plans focus areas** | Analyzes focus areas across unified plans |

### Workflow and system tools

| Tool | What it does |
|------|-------------|
| **Get workflow guide** | Retrieves a step-by-step workflow guide (filtered by your role) |
| **Search workflow docs** | Searches workflow documentation (filtered by your role) |
| **Validate against guidelines** | Validates data against platform guidelines |
| **Get current user info** | Returns information about your account and permissions |
| **Get system statistics** | Platform-wide statistics (admin only) |

All tools respect your access level. For example, data retrieval tools will only return data for countries you are assigned to (unless you are an admin), and document tools will only return documents you are authorized to see.

---

## Rate limits

To ensure fair use and system stability, the chatbot applies rate limits:

| Limit | Authenticated users | System managers | Anonymous |
|-------|-------------------|-----------------|-----------|
| **Per minute** | 120 requests | 120 requests | 60 requests |
| **Per day (user)** | 1,000,000 | Exempt | N/A |
| **Per day (system-wide)** | 5,000,000 total across all users | — | — |

If you hit a rate limit, wait briefly before sending another message. The limit resets after the relevant time window.

---

## Privacy and security notices

The chatbot displays two important notices:

1. **"Don't share sensitive information."** — The system sends your messages to external AI providers for processing. Avoid including passwords, tokens, API keys, personal data, or other credentials.
2. **"AI can make mistakes. Check important information."** — AI-generated answers may be inaccurate. Always verify critical data against the source.

### Built-in protections

The platform includes several layers of protection to reduce accidental exposure of sensitive information:

- **Data Loss Prevention (DLP)** — Outgoing messages are scanned for common sensitive patterns (emails, tokens, keys, card numbers). Depending on configuration, the system may warn you, ask for confirmation, or block the message.
- **PII scrubbing** — Before content is sent to external providers, the system redacts detected personally identifiable information.
- **Page context minimization** — When the chatbot sends page context to help answer UI-related questions, high-risk fields (such as URLs) are removed.

For a summary of acceptable use and safeguards, see the [AI Use Policy](ai-use-policy.md). Ask your administrator if you need more detail on how security controls are configured.

---

## Tips

- **Be specific** — Include the country, indicator, and time period in your question for more precise answers.
- **Use data source controls** — If you only want answers from uploaded documents, disable the Databank source (and vice versa).
- **Check the source** — When the assistant references document content, verify it against the original document.
- **Use the immersive view** for longer analytical conversations — the full-screen layout is better for reading charts, tables, and detailed responses.
- **Export important conversations** before clearing them — deletion is permanent.

## Common problems

| Problem | What to check |
|---------|--------------|
| Chatbot is not available | Ask your administrator whether an AI provider is configured and enabled. |
| "No provider configured" error | At least one AI provider key (OpenAI, Gemini, or Azure) must be set in the environment. |
| Assistant cannot find a document I uploaded | Check the document’s privacy settings on the assignment or form (whether it is marked searchable) and whether processing has finished. If it should be searchable and still does not appear, ask your administrator. |
| Assistant returns data for the wrong country | Rephrase your question with the full country name. Check that you are assigned to that country. |
| Rate limit reached | Wait a minute and try again. If the problem persists, contact your administrator. |
| DLP warning on my message | The system detected a pattern that looks like sensitive data. Remove or replace the sensitive content and resend. |
| Conversation history is missing | If you are using the public/anonymous mode, conversations are not saved. Log in to persist conversations. |

## Related

- [AI Use Policy](ai-use-policy.md) — Acceptable use, data handling, and responsibilities
- [Data handling and privacy](data-handling-and-privacy.md) — Basic guidance on handling and sharing data safely
