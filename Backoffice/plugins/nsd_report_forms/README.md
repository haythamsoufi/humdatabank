# NSD funds (`nsd_report_forms`)

CBF monitoring of National Society Development funded projects inside the Databank,
on top of **core project reporting** (`app.models.projects.Project`, `entity_type=project`).

## Split of responsibilities

| Layer | Owns |
|---|---|
| **Core** | `project` table, Admin → Projects CRUD, per-project cycle assignments (`AssignedForm.scope=project_cycle`), EntityService / access via country |
| **This plugin** | CBF templates & field types, relative slots `Y1Q1`…`Final`, master Excel import, MOMO-style overview / PM / API |

## Admin UI

**Plugin settings (standard):** Admin → Plugins → NSD Report Forms → Settings  
(`/admin/plugins/nsd_report_forms/settings`) — Overview (status + tool links) and **Master import** tab.  
Legacy `/admin/nsd-import/` redirects to `?tab=import`.  
Legacy `/admin/nsd-projects/` and `/nsd-funds/pm-overview` redirect to **Admin → Projects** (`/admin/projects/`). PM pages are that list filtered to the manager email.

**Core project reporting (manual):**

1. **Admin → Projects** — create a project (reference, country, dates, contacts, …).
2. On the project detail page, **Add cycle** — create a per-project report assignment for `Y1Qn` or `Final` (hidden from Manage Assignments).
3. Focal points with **country** access (and the right assignment roles / NSD Access Groups) open those submissions.

**CBF master import** (automates projects + scheduled cycles):  
Settings → Master import. Needs **Admin: NSD funds** (or System Manager).  
Missing published templates (`NSD Quarterly report - CBF`, `NSD Final report - CBF`) are auto-created on first import/check.  
Inactive National Societies are matched (not skipped). Missing contact emails create users and add them to Access Groups **NSD Focal Points** (`ns_focal_email`, Final reports only) and **NSD PMs** (`ifrc_pm_email`, all report slots), with country access and Assignment Editor/Submitter.

## Assignment model

Each project report is its own `AssignedForm`:

- `scope = project_cycle`
- `project_id` → the core project
- `period_name = "<reference> · Y1Q2"` (unique with template)
- Exactly one AES (`entity_type=project`)

These rows are filtered out of **Manage Assignments** / Gantt / campaign counts. Manage them from the project page (close / reopen / add cycle).

## Install / migrate

1. Run migrations (`add_assigned_form_scope_project` adds `scope` + `project_id`).
2. Enable the **Projects** entity group in System Settings if it is not already on.
3. Legacy profile → project: `flask nsd-migrate-projects`
4. Shared slots → per-project cycles: `flask nsd-migrate-slots` (also runs as part of `nsd-migrate-projects`)
5. Ongoing CBF updates: Settings → Master import.
