# In-app admin features (Backoffice)

This page maps **administrator-facing screens** in the Backoffice to what they do, which **RBAC permissions** typically gate them (see [Role recipes](user-guides/admin/role-recipes.md)), and how they relate to longer [user guides](README.md#user-guides-by-role). It mirrors the **Admin Panel** sidebar in `app/templates/core/layout.html` plus a few linked surfaces (for example RBAC and API keys) that live off those flows.

**Note:** The **System Manager** role bypasses most permission checks. Below, “permission *X*” means *X* **or** System Manager unless stated otherwise.

---

## General

### Main Dashboard (non-admin home)

**Where:** Top nav / sidebar **Dashboard** → `main.dashboard` (not under `/admin/`).

**Who:** Anyone with assignment access (`assignment.view` and related focal-point roles).

**What you get:** Your focal-point landing view (assignments, tasks, and org context). Described in [Navigation basics](user-guides/common/navigation.md) and [View your assignments](user-guides/focal-point/view-assignments.md).

---

### Admin Dashboard (overview)

**Where:** Admin → **Admin Dashboard** → `/admin/`.

**Who:** **System Manager only** (route is restricted with `system_manager_required`; the sidebar may show the link to users with `admin.analytics.view`, but the overview page itself is for System Managers).

**What you get:**

- **Statistic cards** (permission-gated) — Total users, admin vs focal-point role counts, templates, assignments, today’s successful logins; cards link into Users, Templates, Assignments, or Login logs where relevant.
- **Quick actions** — Shortcuts such as Add user, New assignment, New template, Indicator Bank, Resources, Settings (each shown only if the corresponding create/view/manage permission applies).
- **Security & audit** and **Translation coverage** widgets (`admin.analytics.view`) — Unresolved security events, high-risk actions, suspicious logins, failed-login rate; average indicator name/definition translation coverage by language with links to deeper analytics or Indicator Bank.
- **Items requiring attention** — Pending public submissions, overdue country assignments, unresolved security alerts with **View** jumps to the right list.
- **Recent activity (7 days)** — Successful logins, user activity events, active sessions.
- **Most active users (30 days)** — Ranked list with links to per-user analytics.
- **Data import tools** (System Manager, when KoBo route is registered) — KoBo Toolbox import wizard entry point.

---

### Document Management

**Where:** Admin → **Document Management** → `/admin/documents`.

**Who:** `admin.documents.manage`.

**What you get:** Admin-side handling of supporting / submitted documents (types, approvals, library context). User-facing detail: [Supporting documents (Admin)](user-guides/admin/supporting-documents.md).

---

### Translation Management

**Where:** Admin → **Translation Management** → `/admin/translations/manage`.

**Who:** `admin.translations.manage`.

**What you get:** Import/export and editing flows for UI and content translations, language matrices, and coordination with supported languages in System Configuration. Often used next to **Indicator Bank** translation work.

---

### Plugin Management

**Where:** Admin → **Plugin Management** → `/admin/plugins`.

**Who:** `admin.plugins.manage`.

**What you get:** List installed plugins, active flags, versions; enable/disable style administration when the plugin subsystem is present.

---

### System Configuration

**Where:** Admin → **System Configuration** → `/admin/settings`.

**Who:** `admin.settings.manage`.

**What you get:** Tabbed settings saved as organization-wide configuration:

| Tab | Typical contents |
|-----|------------------|
| **General** | Supported languages (chips + ordering), language flags, regional defaults. |
| **Data** | Lookup-backed options used across forms (document types, age groups, sex categories, etc.). |
| **Branding** | Organization name, logos, public-facing identity. |
| **Emails** | SMTP / mail templates and behaviour tied to outbound mail. |
| **Notifications** | System defaults that pair with the Notifications Center. |
| **AI** | Feature flags and limits for AI/RAG (complements server `env` secrets; see [AI configuration](setup/ai-configuration.md)). |

Header includes **app version** and an **Updates** check when implemented. Deep links from other admin pages may use hash fragments (for example `#emails`).

---

### Notifications Center

**Where:** Admin → **Notifications Center** → `/admin/notifications/center`.

**Who:** `admin.notifications.manage`.

**What you get:**

- **View All Notifications** — AG Grid of every notification in the system; column filters and column visibility.
- **Create Notification** — Compose sends to selected users or entities by **email** and/or **mobile push**, with delivery options and attachments.
- **Campaigns** — Scheduled or draft notification campaigns.

Operational guide: [Notifications and communications (Admin)](user-guides/admin/notifications-and-communications.md). Email infrastructure cross-reference: System Configuration → **Emails**.

---

### Documentation (in-app, admin)

**Where:** Admin → **Documentation** → `/admin/docs` (index and nested paths).

**Who:** `admin.docs.view`.

**What you get:** Browse the same markdown corpus as this handbook (including [workflows](workflows/README.md)) inside the app for onboarding and support.

---

## User Management

### Manage Users

**Where:** Admin → **Manage Users** → `/admin/users` (plus `/admin/users/new`, `/admin/users/<id>/edit`, access-request and RBAC URLs under `/admin/users/...`).

**Who:** `admin.users.view` (broader user admin actions use `admin.users.create`, `admin.users.edit`, `admin.users.delete`, `admin.users.roles.assign`, etc.).

**What you get:**

- Searchable/sortable user list, country and role visibility, activation controls.
- **User form** — Profile fields, password flows, country assignments, **RBAC roles** grouped (system, core, admin modules, assignment roles) when you have `admin.users.roles.assign` or read-only role display.
- **Access requests** — When `admin.access_requests.view` is granted, the page header links to the access-request queue (approve/reject extra country or access asks).
- **RBAC administration** — **System Manager only**: header links to **`/admin/users/roles/`**, **`/admin/users/permissions`**, and **`/admin/users/grants`** (roles, permission catalogue, explicit grants). Routes are additionally decorated with `admin.users.roles.assign`; in practice only System Managers can use these screens.

Guides: [Manage users](user-guides/admin/manage-users.md), [Add a user](user-guides/admin/add-user.md), [Role recipes](user-guides/admin/role-recipes.md).

---

## Form & Data Management

### Manage Templates (Form Builder)

**Where:** Admin → **Manage Templates** → `/admin/templates` (sections, items, versions, and related paths stay under `/admin/...` in the `form_builder` blueprint).

**Who:** `admin.templates.view` (create/edit/publish map to `admin.templates.create`, `admin.templates.edit`, …).

**What you get:** Full lifecycle for **form templates** — versions, sections and pages, **FormItem** definitions (indicators, questions, documents), relevance rules, calculated lists, repeat sections, preview, import/export helpers, and links to assignment usage. Guides: [Create a form template](user-guides/admin/create-template.md), [Edit a template](user-guides/admin/edit-template.md), [Form Builder (advanced)](user-guides/admin/form-builder-advanced.md).

---

### Manage Assignments

**Where:** Admin → **Manage Assignments** → `/admin/assignments` (and nested routes for public submissions, entity status, etc.).

**Who:** `admin.assignments.view` (creating or changing assignments: `admin.assignments.create` / `edit`; public URL flows: `admin.assignments.public_submissions.manage`).

**What you get:** Country and entity **assignment** lifecycle (`AssignmentEntityStatus` / AES), due dates, focal-point mapping, public form assignments, **public submissions** inbox and approval, and links to reporting cycles. Guides: [Create and manage assignments](user-guides/admin/manage-assignments.md), [Assignment lifecycle](user-guides/admin/assignment-lifecycle.md), [Public URL submissions](user-guides/admin/public-url-submissions.md), [Review and approve submissions](user-guides/admin/review-approve-submissions.md).

---

### Explore Data

**Where:** Admin → **Explore Data** → `/admin/data-exploration`.

**Who:** At least one of `admin.data_explore.data_table`, `admin.data_explore.analysis`, `admin.data_explore.compliance` (tabs hide if you lack the matching permission).

**What you get:**

- **Data Table** — Parameterized extraction of submission/form data into **AG Grid** (filtering, column visibility, export paths as implemented).
- **Analysis** — Same filtered cohort aggregated for **disaggregation / charts** (ApexCharts), including demographic breakdowns where configured.
- **Compliance** — **FDRS document compliance** view (annual report + audited financial statement rules over a selectable window), summary badges, downloadable tables.

Cross-guide: [Export and download data](user-guides/admin/export-download-data.md) for general export concepts; compliance logic is specific to this explorer.

---

## Website Management

### Manage Resources

**Where:** Admin → **Manage Resources** → `/admin/resources`.

**Who:** `admin.resources.manage`.

**What you get:** CRUD for public **resources** (files, metadata, languages) surfaced on the public website. Often coordinated with translations.

---

### Embed Content

**Where:** Admin → **Embed Content** → `/admin/embed-content`.

**Who:** `admin.resources.manage` (same permission as **Manage Resources**; embeds are an extension of website content).

**What you get:** Register **Power BI**, **Tableau**, or generic **iframe** embeds with URL validation, page slots, aspect ratio, and ordering — served to the public website within allowed categories.

---

## Reference Data

### Organizational Structure

**Where:** Admin → **Organizational Structure** → `/admin/organization`.

**Who:** `admin.organization.manage` and/or `admin.countries.view` (sidebar shows when either applies).

**What you get:** National Society **branches** and **sub-branches** per country, editable hierarchy aligned with mobile admin org APIs. Feeds assignment and country pickers across the stack.

---

### Indicator Bank

**Where:** Admin → **Indicator Bank** → `/admin/indicator_bank`.

**Who:** `admin.indicator_bank.view` (edits use additional indicator-bank permissions).

**What you get:** Central catalogue of **indicators** (definitions, disaggregation, translations) reused by the Form Builder. Guide: [Indicator Bank](user-guides/admin/indicator-bank.md).

---

## Analytics & Monitoring

### User Analytics

**Where:** Admin → **User Analytics** → `/admin/analytics/dashboard`, plus related routes under `/admin/analytics/` (login logs, session logs, per-user drill-down).

**Who:** `admin.analytics.view`.

**What you get:** Dated analytics for **logins**, **activity**, **security summaries**, **sessions**, top active users, and navigation into **Security events** lists. Distinct from the System Manager-only **`/admin/`** home card layout but overlapping metrics.

---

### Audit Trail

**Where:** Admin → **Audit Trail** → `/admin/analytics/audit-trail`.

**Who:** `admin.audit.view`.

**What you get:** Searchable **admin action** and activity history with consolidated descriptions (form context, entity resolution) for accountability.

---

### Security Dashboard

**Where:** Admin → **Security Dashboard** → `/admin/security/dashboard`.

**Who:** `admin.security.view`.

**What you get:** Rolling **security events** metrics (totals, unresolved count, severity breakdown), trend context, and drill-downs to investigations. Pairs with analytics security lists.

---

### Governance Dashboard

**Where:** Admin → **Governance** → `/admin/governance`.

**Who:** `admin.governance.view`.

**What you get:** Long-page **governance health** narrative with sticky section nav: composite **health score**, KPI strip, **data ownership**, **access control**, **quality**, **compliance**, **metadata**, and **policies** — designed for oversight and data-governance conversations. Complements [Data governance](user-guides/common/data-governance.md).

---

### API Management

**Where:** Admin → **API Management** → `/admin/api-management`.

**Who:** `admin.api.manage`.

**What you get:**

- **Summary cards** — Registry coverage (% of live routes documented in the static registry), total `/api` requests in the usage log, mean response time, HTTP success rate, distinct client IPs.
- **Endpoint Registry** — One **AG Grid** across **External `/api/v1`**, **Mobile `/api/mobile/v1`**, and **AI `/api/ai/v2`**: methods, paths, auth mode, permissions, rate limits, overlap hints, usage counters, registry flags. **Filter chips** for surfaces, **issues**, **overlaps**, **logged traffic**, **undocumented** live routes, **stale** registry rows, and **gaps**. Row styling for undocumented / stale / flagged. **Export Report** → Markdown (issues, overlaps, full table). Column filters, column visibility, match-count footer, **legend** for auth icons (public, Bearer API key, key-or-session, session, AI identity, mobile JWT, mobile RBAC, rate limits).
- **API URL Builder** — Endpoint picker, dynamic query fields, optional API key (**browser-only**, for assembling URLs), **Copy** / **Open**, and an in-page **Documentation** modal (auth modes, pagination, `date_from` / `date_to`, `sort` / `order`, compression).
- **Request Volume** — **Chart.js** chart with endpoint and period selectors (24h through yearly).

---

### API Key Management

**Where:** From API Management header **API Key Management**, or `/admin/api-management/api-keys` (legacy `/admin/api-keys` redirects here).

**Who:** `admin.api.manage` (or System Manager).

**What you get:** Create, label, rotate, and revoke **database-backed API keys** used by external integrations (`Authorization: Bearer …`). Operational practices: [Security — API key security](setup/security.md#api-key-security).

---

### System Monitoring

**Where:** Admin → **System Monitoring** → `/admin/monitoring` (and `/admin/monitoring/logs`, etc.).

**Who:** `admin.analytics.view` (same sidebar gate as User Analytics in the default layout).

**What you get:** **Live** operational views — recent application logs, log download/clear (where permitted), memory snapshot endpoints, system information JSON, optional test-error route in development. Intended for on-call inspection on top of hosting metrics.

---

## AI System

### AI Dashboard

**Where:** Admin → **AI Dashboard** → `/admin/ai/`.

**Who:** `admin.ai.manage`.

**What you get:** **System status** strip (agent enabled, OpenAI configured, LLM judge), **metric cards** (documents indexed, embedding counts, agent queries, success vs errors), and shortcuts into **Reasoning Traces** and **Review Queue** for LLM quality workflows. Configuration secrets remain in environment / System Configuration **AI** tab; see [AI configuration](setup/ai-configuration.md).

---

### Knowledge Base (AI Document Library)

**Where:** Admin → **Knowledge Base** → `/admin/ai/documents`.

**Who:** `admin.ai.manage`.

**What you get:** Upload/update **RAG documents**, chunking, embedding status, search testing, and alignment with chat document QA. Guide: [AI Document Library and embeddings](user-guides/admin/ai-document-library-and-embeddings.md).

---

### Reasoning Traces

**Where:** Admin → **Reasoning Traces** → `/admin/ai/traces` (review queue is linked from the AI dashboard and trace UI).

**Who:** `admin.ai.manage`.

**What you get:** Inspect **agent / tool traces** for debugging and quality review; links to **Review Queue** for structured human review of low-quality or flagged model outputs.

---

## Related: focal-point and common surfaces (not in Admin sidebar)

These are used heavily alongside admin work:

| Area | Entry | Notes |
|------|--------|--------|
| **Account settings** | Profile menu | Language, password, profile fields ([Account settings](user-guides/common/account-settings.md)). |
| **Notifications (user)** | Bell icon | Personal inbox; distinct from admin **Notifications Center**. |
| **Help Documentation** | Nav / profile | Public help docs blueprint (`help_docs`), separate from admin in-app **Documentation**. |
| **Forms / data entry** | Assignments | Focal-point data collection ([Fill and submit a form](user-guides/focal-point/submit-data.md)). |

---

## Permission quick reference (sidebar gates)

| Sidebar item | Typical permission |
|--------------|-------------------|
| Admin Dashboard | System Manager (see above) |
| Document Management | `admin.documents.manage` |
| Translation Management | `admin.translations.manage` |
| Plugin Management | `admin.plugins.manage` |
| System Configuration | `admin.settings.manage` |
| Notifications Center | `admin.notifications.manage` |
| Documentation (in-app) | `admin.docs.view` |
| Manage Users | `admin.users.view` |
| Manage Templates | `admin.templates.view` |
| Manage Assignments | `admin.assignments.view` |
| Explore Data | any of `admin.data_explore.*` |
| Manage Resources | `admin.resources.manage` |
| Embed Content | `admin.resources.manage` |
| Organizational Structure | `admin.organization.manage` / `admin.countries.view` |
| Indicator Bank | `admin.indicator_bank.view` |
| User Analytics | `admin.analytics.view` |
| Audit Trail | `admin.audit.view` |
| Security Dashboard | `admin.security.view` |
| Governance | `admin.governance.view` |
| API Management / API Keys | `admin.api.manage` |
| System Monitoring | `admin.analytics.view` |
| AI Dashboard / Knowledge Base / Reasoning Traces | `admin.ai.manage` |

For canonical permission names and bundles, prefer the **RBAC** screens (System Manager) or your organization’s role assignment policy.
