# Data Governance: How the System Supports It

This document describes how the Humanitarian Databank supports **data governance**: the policies and controls that ensure collected data is accessible only to authorized parties, consistent and reliable, traceable, and handled securely. It is intended for administrators, focal points, and others who need to understand how the platform supports governance over the data it collects.

## Scope of This Document

- **Data ownership** — Template Owners and Data Owners with explicit accountability per assignment
- **Access control and data scope** — Who can view and modify which data, with ghost-access detection
- **Data quality and consistency** — Validation, standard definitions, overdue tracking, and the submission workflow
- **Accountability and audit** — Attribution of administrative actions, submission/approval tracking, and activation audit
- **FDRS documents** — Annual Report and Audited Financial Statement coverage, monitored in Explore Data
- **Metadata** — Indicator definitions, form labels, and stale-suggestion detection
- **Data lifecycle** — From draft to approved, and how changes are controlled
- **Safe handling** — Exports, public links, and privacy practices
- **Operational practices** — Running reporting cycles and sustaining governance in daily use
- **Governance register** — Named controls, an issue register, and time-bounded risk acceptance

---

## Data Ownership

The platform implements a **two-tier data ownership model** that distinguishes accountability at different levels.

### Tier 1: Template Owner (template level)

A **Template Owner** is responsible for the *standard or definition* of data — what is measured and how.

- **Template Owner** (`FormTemplate.owned_by`) — Each form template can have an owner: the person responsible for the data standard it defines. Only users with admin-level template permissions appear in the Template Owner dropdown. Set this under **Admin Panel → Form Builder → Edit Template**.

### Tier 2: Data Owner (assignment level)

A **Data Owner** is accountable for the *actual data collected* in a specific reporting cycle.

- **Assignment Data Owner** (`AssignedForm.data_owner_id`) — Each assignment can have a designated data owner: the person accountable for data quality during that collection cycle. Only users with admin-level assignment permissions appear in the Data Owner dropdown (focal points are excluded since they are submitters, not owners). Set this under **Admin Panel → Assignments → Create/Edit Assignment**.
- When a new assignment is created and a template is selected, the system can pre-fill the data owner from the template's owner (`owned_by`).

### Tier 3: Focal Point (country level)

**Focal points** are the existing entity-level responsibility. A focal point is assigned to one or more countries and is responsible for entering and submitting data for those countries. Focal points are not data owners; they are the operational users who collect and submit.

### Organization Data (Countries, National Societies, National Society structure)

Organization data is the **authoritative reference** for geographic and structural scope across the platform: countries, National Societies, and — when the feature is enabled — National Society structure (branches, sub-branches, local units).

- **Countries** — The country list is maintained under **Admin Panel → Organization Management** (Countries tab). Only users with the required permissions may create, edit, or delete countries. This list underpins assignment scope (which countries are included in an assignment), user country access (which countries a focal point may access), and reporting (e.g. exports by country).
- **National Societies** — Each National Society is associated with one country. National Societies are managed under **Organization Management → National Societies**, and are used when reporting or assignments are scoped by National Society rather than, or in addition to, country.
- **National Society structure (branches, sub-branches, local units)** — When the National Society structure feature is enabled, the hierarchy is **Country → National Society branch → Sub-branch → Local unit**. Branches and sub-branches are associated with a country; local units belong to a branch or sub-branch. This structure is maintained under **Organization Management → National Society structure** and provides the canonical list of branches and local units used in forms, assignments, and reporting.

**Data owner and maintenance.** The **data owner** for all organization data is the **Federation-wide Data Systems team (FDS)**. FDS is responsible for the accuracy and governance of these master lists. Only users with the required permissions may modify the data in the system: **Edit countries** (`admin.countries.edit`) for countries, and **Manage organization** (`admin.organization.manage`) for the full structure. Read-only access uses **View countries** (`admin.countries.view`). Designated administrators (under FDS governance) maintain the data so that form data, assignments, and exports stay aligned with a single hierarchy.

Keeping organization data accurate ensures correct attribution, access control that matches the intended structure, and exports and reports that respect organizational boundaries.

*See:* [User roles and permissions](../admin/user-roles.md) (for roles that include countries and organization management)

### Indicator Bank (glossary of standard definitions)

The **Indicator Bank** is a centrally maintained **business glossary** of indicator definitions (name, unit, definition, and optionally calculation rules). It does not store submitted values — those are in form data and tied to assignments and entities (e.g. country or National Society).

Only users with Indicator Bank permissions (e.g. **Indicator Bank manager**) may view, create, edit, archive, or review indicator suggestions. The Indicator Bank defines *what* is measured; form data records *who* reported *which* value and *when*. Keep definitions stable over time; when the meaning of a measure changes, add a new indicator so historical data stays interpretable.

Central management of definitions avoids conflicting interpretations across countries and periods and supports comparable reporting.

*See:* [Indicator Bank (admin)](../admin/indicator-bank.md)

### Summary

| Data type | Owner | Where maintained | Role in governance |
|-----------|-------|------------------|---------------------|
| Countries, National Societies, National Society structure | **FDS** (Federation-wide Data Systems team) | Admin Panel → Organization Management | Authoritative scope for assignments, user access, and reporting |
| Indicator definitions (glossary terms) | **Indicator Bank managers** | Admin Panel → Indicator Bank | Standard definitions used across templates and assignments |
| Form template standards | **Template Owner** (single user per template) | Admin Panel → Form Builder | Defines what data is collected and how |
| Assignment data (collection cycle) | **Data Owner** (single user per assignment) | Admin Panel → Assignments | Accountable for data quality during the reporting cycle |
| Form submission values | **Focal Point** (per country/entity) | Entry forms, submissions, exports | Data attributed to the submitting entity |

### Dropdown filtering for ownership roles

To maintain clear separation of concerns, the platform filters user dropdowns based on role:

| Dropdown | Shows | Excludes | Reason |
|----------|-------|----------|--------|
| Template Owner | Users with admin template permissions | Focal points, view-only users | Only admins should own data standards |
| Assignment Data Owner | Users with admin assignment permissions | Focal points, view-only users | Focal points submit data; owners are accountable for it |
| Shared Access (template) | Users with admin roles | Non-admin users | Template sharing is an admin-level concern |

---

## 1. Access Control and Data Scope

The system restricts access so that users may view and act only on data they are authorized to access.

### Role-based access control (RBAC)

- Users are assigned **roles** that define permitted actions (view, edit, submit, approve, manage templates, etc.).
- **Assignment roles** (e.g. viewer, editor/submitter, approver) determine whether a user may only view data, enter and submit it, or approve it.
- **Admin roles** govern access to templates, assignments, users, countries, indicators, content, analytics, and security/audit features.
- Actions not permitted by a user's role are unavailable; relevant buttons and pages are hidden or disabled.

*See:* [User roles and permissions](../admin/user-roles.md)

### Country and assignment scope

- **Country (or entity) assignment** determines *which* assignments and submission data a user may see.
- A focal point typically has access only to assignments for the countries to which they are assigned.
- Administrators with assignment-management access see assignments according to their permissions; scope may be further limited by configuration.
- If a user cannot access an assignment, the cause is typically **country access** or **role**, rather than the data itself.

*See:* [Submission statuses and what you can do](submission-statuses-and-permissions.md), [Troubleshooting access (Admin)](../admin/troubleshooting-access.md)

### Ghost access detection

The governance register (control **ACC-01**) lists deactivated users who still hold roles. They cannot sign in, but the role returns if the account is switched back on. Each row links to Edit User.

Control **ACC-02** lists people who have country access and no role. Unused permissions in the catalog, and roles that currently have no members, are not treated as failures.

### Summary

| Concern | How the system supports it |
|---------|----------------------------|
| Who may view data | Roles and country/entity assignment; users see only data they are authorized to access |
| Who may modify data | Users with edit/submit or admin roles; approvers may reopen for corrections |
| Who may export | Users with access to the assignment and entry form; export may be enabled per template |
| Ghost access | Governance register ACC-01 lists deactivated accounts that still hold a role |
| Country access without a role | Governance register ACC-02 |

---

## 2. Data Quality and Consistency

The system supports consistent, fit-for-purpose data through standard definitions (Indicator Bank), validation and required fields, and a clear submission and approval workflow.

### Indicator Bank (standard definitions)

Linking form fields to indicators in the Indicator Bank ensures the same measure is reported the same way across countries, time periods, and templates. See [Data ownership](#data-ownership) for who maintains it.

*See:* [Indicator Bank (admin)](../admin/indicator-bank.md)

### Validation and required fields

**Required fields** and **validation rules** (e.g. numeric format, ranges) prevent submission until the form meets minimum quality. Validation messages appear in the form and block submission until resolved. Administrators define these in the Form Builder.

*See:* [Form Builder (advanced)](../admin/form-builder-advanced.md), [Edit a template](../admin/edit-template.md)

### Submission and approval workflow

Data moves through **statuses** (e.g. not started → in progress → submitted → approved). **Submit** sends for review; **Approve** accepts it; **Reopen** returns it for correction. Where edit lock is used, data is considered final only after approval.

The system records **who submitted** (`submitted_by_user_id`) and **who approved** (`approved_by_user_id`) each entity status change, providing a clear audit trail of accountability.

*See:* [Submission statuses and what you can do](submission-statuses-and-permissions.md), [Review and approve submissions](../admin/review-approve-submissions.md)

### Overdue tracking and severity

The **Governance Dashboard** tracks overdue submissions with severity buckets:

| Severity | Threshold | Meaning |
|----------|-----------|---------|
| **Critical** | > 30 days overdue | Requires immediate attention |
| **High** | > 8 days overdue | Needs follow-up |
| **Medium** | > 1 day overdue | Recently overdue |

The dashboard also detects **never-started assignments** (active assignments where every entity is still in "Pending" status) and **assignments with no entities** (created but never assigned to any country).

### Summary

| Concern | How the system supports it |
|---------|----------------------------|
| Consistent definitions | Indicator Bank; form fields linked to indicators |
| Minimum completeness | Required fields and validation rules block submission until satisfied |
| Clear final state | Submission and approval workflow; statuses and, where used, edit lock after submit |
| Overdue tracking | Governance Dashboard with severity buckets (critical/high/medium) |
| Never-started detection | Dashboard flags active assignments where no country has begun work |
| Attribution | `submitted_by` and `approved_by` tracked per entity status change |

---

## 3. Accountability and Audit

### Admin action logging and risk levels

The system logs administrative actions (who did what, when) and assigns each a **risk level** (high, medium, low). **High-risk** actions (e.g. user deletion, system manager role changes) automatically create **security events** and are highlighted for review. All actions form part of the **audit trail** for compliance and troubleshooting.

*See:* [Admin action risk levels](../../workflows/admin/admin-action-risk-levels.md)

High- and critical-risk actions appear in the **Security Dashboard** and in admin action logs; actions can be filtered by risk level.

### Assignment lifecycle audit

The system tracks who activated and deactivated assignments:

- `activated_by_user_id` — recorded when an assignment is activated or reopened
- `deactivated_by_user_id` — recorded when an assignment is deactivated or closed

This ensures every lifecycle change is attributed to a specific user.

### Submission accountability

For each country/entity status within an assignment:

- `submitted_by_user_id` — recorded when a focal point submits data
- `approved_by_user_id` — recorded when an administrator approves the submission

These fields are set automatically at the moment of the action and cannot be edited, providing tamper-resistant attribution.

### Summary

| Concern | How the system supports it |
|---------|----------------------------|
| Attribution of changes | Admin actions logged with user, action type, description, and target |
| Review of sensitive actions | Risk levels; high-risk actions generate security events and appear in the Security Dashboard |
| Assignment lifecycle | `activated_by` and `deactivated_by` tracked for each assignment |
| Submission attribution | `submitted_by` and `approved_by` tracked per entity status change |
| Compliance | Full audit trail of admin actions for review and reporting |

---

## 4. FDRS documents

Annual Report and Audited Financial Statement coverage is monitored in **Explore Data → Compliance**, not on the governance register.

---

## 5. Metadata Completeness

Good metadata supports discoverability and consistency. The Governance Dashboard tracks:

- **Indicators with definition** — percentage of active indicators that have a non-empty definition field
- **Form items with label** — percentage of form items across all templates that have a display label
- **Archived indicators** — count of indicators moved to archive status
- **Published templates never assigned** — templates that have been published but never used in an assignment (potential waste or oversight)
- **Stale suggestions** — indicator suggestions submitted more than 30 days ago that haven't been reviewed

---

## 6. Data Lifecycle and Control of Changes

When the path from draft to approved is clear and changes are controlled, governance is easier to maintain.

### Statuses and permissions

Each submission has a **status** (e.g. not started, in progress, submitted, approved, reopened). What a user can do (edit, submit, approve, reopen) depends on **role** and **current status**. This prevents ad hoc edits after submission unless the workflow allows reopen.

*See:* [Submission statuses and what you can do](submission-statuses-and-permissions.md)

### Reopen and corrections

**Reopen** (by approvers or administrators) returns a submission so the focal point can correct and resubmit. The choice between reopening and creating a new assignment is a process decision; document reopenings (e.g. in comments or procedures) so the audit trail stays clear.

*See:* [Review and approve submissions](../admin/review-approve-submissions.md)

### Duplicates and public submissions

For **public URL** submissions, the system does not prevent duplicates. Define and document how duplicates are handled (e.g. keep latest, keep best, manual review) and what "minimum quality" means (required fields, documents), then apply the validation and approval workflow consistently.

*See:* [Public URL submissions](../admin/public-url-submissions.md)

### Summary

| Concern | How the system supports it |
|---------|----------------------------|
| Clear lifecycle | Statuses (draft → submitted → approved) and role-based actions |
| Controlled changes after submit | Reopen by approver; edit lock where configured |
| Duplicates and quality for public URLs | Governance checklist and consistent process; validation and review in the platform |

---

## 7. Safe Handling of Data

Governance includes how data is exported, shared, and protected.

### Exports (Excel, PDF)

Exports are available to users with access to the assignment and entry form; the template controls whether Excel or PDF is enabled. Treat exports as sensitive: do not share via public links, store in approved locations, keep an unmodified copy of raw exports, and document any manual cleaning.

*See:* [Export and download data](../admin/export-download-data.md), [Exports: how to interpret files](../admin/exports-how-to-interpret.md)

### Public URL submissions

Public URLs allow submission without login and can be shared widely, so they carry higher risk.
Before use: define who may submit and how the URL is shared, how duplicates are handled, what "minimum quality" means, and when the link will be disabled (e.g. after the deadline). Monitor submissions and disable the link when the collection period ends.

*See:* [Public URL submissions](../admin/public-url-submissions.md)

### Data handling and privacy

Reduce risk by avoiding unnecessary personal identifiers in submissions and attachments, and by defining who may access sensitive data, how long it is retained, and how it is shared. The platform provides access control and audit; your organization defines what to collect and how to store and share exports.

*See:* [Data handling and privacy](data-handling-and-privacy.md)

### Summary

| Concern | How the system supports it |
|---------|----------------------------|
| Who may export | Access to assignment and entry form; export enabled on template |
| Safe use of exports | Documentation and practices; platform provides access control and audit |
| Public URLs | Governance checklist, monitoring, and disabling when not in use |
| Privacy and sensitivity | Data handling guidance; access control and audit in the platform |

---

## 8. Governance register

**Admin Panel → Governance** (`admin.governance.view`) is the operating record for data governance. It is a control register, not a health score.

Each control states:

- the rule
- who is accountable
- the live check
- the result: **passing**, **gap**, **accepted**, **not applicable**, or **not evaluated**

A gap opens one issue. The issue stays open until the check passes. Someone with `admin.governance.manage` can accept the risk: a written reason and a review date, at most one year out. On that date the issue reopens if the gap is still there. Acceptances are written to the admin action log.

The checks are limited to facts the platform can prove:

| Control | Rule |
|---------|------|
| OWN-01 | Every open assignment has a data owner |
| OWN-02 | Every published template has an owner |
| OWN-03 | Every country on an open assignment has a focal point |
| ACC-01 | Deactivated accounts do not keep roles |
| ACC-02 | Country access is not granted without a role |
| ACC-03 | Approvals in the last 90 days record the approver |
| RPT-01 | No open country submission is more than 30 days overdue |
| RPT-02 | No open assignment is still unstarted after its due date |
| MET-01 | Active (non-archived) indicators have a definition |
| MET-02 | Indicator suggestions are not left pending for more than 30 days |
| LIF-01 | Active public submission links have an expiry date |

Reporting discipline is timeliness. Validation rules, the FDRS data-quality score, and FDRS document compliance stay in their own tools. The page also keeps the focal-point register for every country, which is wider than OWN-03.

Open issues link to the screen that fixes them. Assignments with no data owner open Assignments filtered with `?no_data_owner=1`. Ghost users and accounts with country access but no role open Edit User.

---

## 9. Operational Practices That Support Governance

The following practices help sustain governance in daily use.

### Running a reporting cycle

- **Before launch:** Agree the reporting period, participating countries, and what "good quality" means (required documents, validation expectations). Assign a **Data Owner** for the assignment.
- **Access:** Confirm that focal points have the correct roles and country access before the assignment is opened.
- **During collection:** Monitor progress (not started, in progress, submitted, overdue) and use validation and reminders to improve completeness. Use the governance register for submissions more than 30 days overdue on open assignments.
- **Review:** Use a consistent checklist (e.g. required fields, outliers, consistency) when approving submissions.
- **After the cycle:** Document decisions (for example deadline extensions, the duplicate rule for public submissions, known issues) for the next cycle. If a governance gap is accepted rather than fixed, record that on the register with a review date.

*See:* [Run a reporting cycle (admin playbook)](../admin/run-a-reporting-cycle.md)

### Templates and consistency

- Use the Indicator Bank and link form fields to indicators when comparable data across countries and periods is required.
- Assign a **Template Owner** to every published template so there is a clear owner for the data standard.
- Avoid substantial template changes mid-cycle; use a new assignment or new version when definitions or structure change significantly.
- Test validation and required fields (e.g. with a small assignment) before full rollout.

*See:* [Create a template](../admin/create-template.md), [Edit a template (Form Builder)](../admin/edit-template.md)

### User and role management

- Assign roles according to need; avoid over-granting (e.g. system manager only for personnel who require full control).
- Document the rationale for role and country access grants so that access reviews and audits are straightforward.
- Use the audit trail and Security Dashboard to review high-risk actions (e.g. user deletion, role changes).
- Regularly review the governance register for deactivated accounts that still hold roles, and remove the role.
- Review users with entity permissions but no RBAC role — they may need a role assigned or their entity access removed.

*See:* [User roles and permissions](../admin/user-roles.md), [Manage users](../admin/manage-users.md)

---

## Quick Reference: Governance Features in the Platform

| Area | Feature | Reference |
|------|---------|-----------|
| **Governance register** | Controls, open issues, risk acceptance | Admin Panel → Governance |
| **Data ownership** | Template Owner (per template) | Admin Panel → Form Builder → Edit Template |
| **Data ownership** | Data Owner (per assignment) | Admin Panel → Assignments → Create/Edit |
| **Data ownership** | Organization data (FDS) | This document — [Data ownership](#data-ownership) |
| Access | Roles (RBAC), country/entity assignment | [User roles and permissions](../admin/user-roles.md) |
| Access | Deactivated accounts that still hold a role | Governance register → ACC-01 |
| Access | Permitted actions by status | [Submission statuses and permissions](submission-statuses-and-permissions.md) |
| Quality | Standard definitions | [Indicator Bank](../admin/indicator-bank.md) |
| Quality | Validation, required fields | [Form Builder (advanced)](../admin/form-builder-advanced.md), [Edit template](../admin/edit-template.md) |
| Quality | Overdue work on open assignments | Governance register → RPT-01 |
| Quality | Review and approval | [Review and approve submissions](../admin/review-approve-submissions.md) |
| Accountability | Admin action log, risk levels | [Admin action risk levels](../../workflows/admin/admin-action-risk-levels.md) |
| Accountability | `submitted_by` / `approved_by` tracking | Automatic on status changes |
| Accountability | `activated_by` / `deactivated_by` tracking | Automatic on assignment lifecycle changes |
| FDRS documents | Annual Report and Audited Financial Statement coverage | Explore Data → Compliance |
| Metadata | Active indicators without a definition | Governance register → MET-01 |
| Metadata | Suggestions pending more than 30 days | Governance register → MET-02 |
| Lifecycle | Statuses, reopen | [Submission statuses](submission-statuses-and-permissions.md), [Review and approve](../admin/review-approve-submissions.md) |
| Safe handling | Exports | [Export and download data](../admin/export-download-data.md) |
| Safe handling | Public URLs | [Public URL submissions](../admin/public-url-submissions.md) |
| Safe handling | Privacy and sensitivity | [Data handling and privacy](data-handling-and-privacy.md) |
| Operations | End-to-end cycle | [Run a reporting cycle](../admin/run-a-reporting-cycle.md) |

---

## Database Fields Supporting Governance

The following fields were added to support governance accountability:

### `AssignedForm` (assignment level)

| Field | Purpose |
|-------|---------|
| `data_owner_id` | User accountable for data quality during this collection cycle |
| `activated_by_user_id` | User who activated or reopened the assignment |
| `deactivated_by_user_id` | User who deactivated or closed the assignment |

### `AssignmentEntityStatus` (per-country status within an assignment)

| Field | Purpose |
|-------|---------|
| `submitted_by_user_id` | User who submitted the data for this entity |
| `approved_by_user_id` | User who approved the submission for this entity |

### `governance_issue` (control register)

| Field | Purpose |
|-------|---------|
| `control_code` | The control this row tracks (one row per control) |
| `status` | `open`, `accepted`, or `resolved` |
| `acceptance_reason` / `accepted_until` | Recorded risk acceptance and the date it expires |

---

## Appendix: Alignment with Microsoft Purview

For organizations using or evaluating **Microsoft Purview**, the following mapping shows how this document's structure and language align with Purview's data governance framework.

| Purview concept | Humanitarian Databank equivalent |
|-----------------|----------------------------------|
| **Data owner** (individual or group responsible for managing a data asset) | **Template Owner** (template level); **Data Owner** (assignment level); **FDS** (organization data) |
| **Data steward** (maintaining nomenclature, data quality standards, and rules) | **Indicator Bank managers**; administrators who define validation and required fields |
| **Glossary / Glossary terms** (business vocabulary and definitions) | Indicator Bank as a business glossary of standard indicator definitions |
| **Governance domain** (boundary for governance, ownership, discovery) | Platform-level governance boundary (organization data, Indicator Bank) and assignment/entity scope for collected data |
| **Access control / RBAC** | Roles and permissions; country and entity assignment; export controls; ghost access detection |
| **Classification / Sensitivity** (sensitivity labels, treatment of sensitive data) | Data handling and privacy guidance; treatment of sensitive data in submissions and exports |
| **Audit trail** | Admin action logging with risk levels; `submitted_by` / `approved_by` / `activated_by` / `deactivated_by` attribution; Security Dashboard for high-risk actions |
| **Data quality** (completeness, consistency, conformity, etc.) | Required fields, validation rules, standard definitions, submission and approval workflow, overdue tracking with severity buckets |
| **Workflow** (validation and approval) | Submission statuses; approve; reopen |
| **Controls and issues** | Governance register: named controls, one issue per gap, time-bounded risk acceptance |

*See:* [Microsoft Purview data governance glossary](https://learn.microsoft.com/en-us/purview/data-governance-glossary), [Get started with data governance in Microsoft Purview](https://learn.microsoft.com/en-us/purview/data-governance-get-started)

---

## Related Documentation

- [Data handling and privacy](data-handling-and-privacy.md) — Practices for submissions, exports, and public URLs
- [How the platform works](../getting-started/how-it-works.md) — Templates, assignments, and submission flow
- [Getting help](getting-help.md)
