# NSD funds (`nsd_report_forms`)

CBF monitoring of National Society Development funded projects inside the Databank,
on top of **core project reporting** (`app.models.projects.Project`, `entity_type=project`).

## Split of responsibilities

| Layer | Owns |
|---|---|
| **Core** | `project` table, one project row on Admin → Assignments, shared `ProjectAssignment` settings copied onto per-project cycles (`AssignedForm.scope=project_cycle`), EntityService / access via country |
| **This plugin** | CBF templates & field types, relative slots `Y1Q1`…`Final`, master Excel import, MOMO-style overview / PM / API |

## Admin UI

**Plugin settings (standard):** Admin → Plugins → NSD Report Forms → Settings  
(`/admin/plugins/nsd_report_forms/settings`) — Overview (status + tool links) and **Master import** tab.  
Legacy `/admin/nsd-import/` redirects to `?tab=import`.  
Legacy `/admin/nsd-projects/` and `/nsd-funds/pm-overview` redirect to **Admin → Assignments** filtered to projects (`/admin/assignments?type=project`). PM pages are that list filtered to the manager email. `/admin/projects/` redirects to the same list.

**Monitoring tab:** Admin → Assignments → a programme (for example `/admin/assignments/projects/portfolio/NSD#monitoring`) is the portfolio dashboard for
reporting and progress: KPI tiles, report pipeline, deadlines by month, regional view, implementation assessment,
spending pace and follow-up worklists (overdue, due soon, needs attention, ending soon, manager workload, data gaps) with
CSV export. It is core (`app/services/projects/monitoring.py`) and works from report statuses and due dates alone; this
plugin supplies the overall/activities assessment and spending to date of the quarterly and final reports through the
`BasePlugin.get_project_report_answers` hook (`badges.project_report_answers`).

**Core project reporting (manual):**

1. **Admin → Assignments → New project** — create a project (reference, country, dates, contacts, …).
2. Open the project row. **Settings** (PDF, Excel, review, access groups, data owner) is saved once and copied onto every report. **Reports** adds `Y1Qn` or `Final`. Each report keeps its own dates and open or closed state. Plugin audiences stay: Final includes focal points and project managers; quarterly reports include project managers. Admin-chosen groups are added on top.
3. Focal points with **country** access (and the right assignment roles / NSD Access Groups) open those submissions. The entry form reads the flags on the report, which match the project settings.

**CBF master import** (automates projects + scheduled cycles):  
Settings → Master import. Needs **Admin: NSD funds** (or System Manager).  
The tab uses the standard Excel dropzone. Uploaded workbooks stay on disk (name, size, upload time), and each run records a last-import line plus a change log.  
Missing published templates (`NSD Quarterly report - CBF`, `NSD Final report - CBF`) are auto-created on first import/check.  
Inactive National Societies are matched (not skipped). Missing contact emails create users and add them to Access Groups **NSD Focal Points** (`ns_focal_email`, Final reports only) and **NSD PMs** (`ifrc_pm_email`, all report slots), with country access and Assignment Editor/Submitter.

## Assignment model

Each project report is its own `AssignedForm`:

- `scope = project_cycle`
- `project_id` → the core project
- `period_name = "<reference> · Y1Q2"` (unique with template)
- Exactly one AES (`entity_type=project`)

These rows are filtered out of campaign lists, Gantt and campaign counts. The Assignments page shows one row per project. Settings live on `ProjectAssignment` and are copied onto the reports when an admin saves, and onto a report when it is first created. A later import does not overwrite a report that already exists. Close, reopen and dates stay on the report.

## Install / migrate

1. Run migrations (`add_assigned_form_scope_project` adds `scope` + `project_id`).
2. Enable the **Projects** entity group in System Settings if it is not already on.
3. Legacy profile → project: `flask nsd-migrate-projects`
4. Shared slots → per-project cycles: `flask nsd-migrate-slots` (also runs as part of `nsd-migrate-projects`)
5. Ongoing CBF updates: Settings → Master import.
