# NSD funds (`nsd_report_forms`)

CBF monitoring of National Society Development funded projects inside the Databank,
on top of **core project reporting** (`app.models.projects.Project`, `entity_type=project`).

## Split of responsibilities

| Layer | Owns |
|---|---|
| **Core** | `project` table, Admin → Projects CRUD, assign projects on an assignment, EntityService / access via country |
| **This plugin** | CBF templates & field types, relative slots `Y1Q1`…`Final`, master Excel import, MOMO-style overview / PM / API |

## Admin UI

**Plugin settings (standard):** Admin → Plugins → NSD Report Forms → Settings  
(`/admin/plugins/nsd_report_forms/settings`) — Overview (status + tool links) and **Master import** tab.  
Legacy `/admin/nsd-import/` redirects to `?tab=import`.  
Legacy `/admin/nsd-projects/` and `/nsd-funds/pm-overview` redirect to **Admin → Projects** (`/admin/projects/`). PM pages are that list filtered to the manager email.

**Core project reporting (manual):**

1. **Admin → Projects** — create a project (reference, country, dates, contacts, …).
2. **Admin → Manage Assignments** — create an assignment for the report template and period (e.g. a quarterly wave).
3. On the assignment, **Add entities → Projects** — attach the projects that must report.
4. Focal points with **country** access (and the right assignment roles) open those submissions.

**CBF master import** (automates steps 1–3 for workbooks / shared `Y1Qn` / `Final` slots):  
Settings → Master import. Needs **Admin: NSD funds** (or System Manager).  
Missing published templates (`NSD Quarterly report - CBF`, `NSD Final report - CBF`) are auto-created on first import/check.  
Inactive National Societies are matched (not skipped). Missing contact emails create users and add them to Access Groups **NSD Focal Points** (`ns_focal_email`, Final reports only) and **NSD PMs** (`ifrc_pm_email`, all report slots), with country access and Assignment Editor/Submitter.

## Install / migrate

1. Run migrations (`add_nsd_project_table` creates core `project`; `aes_entity_type_project` normalizes AES types; `ensure_core_project_table` is a no-op safety net if a draft `nsd_project` table was stamped earlier).
2. Enable the **Projects** entity group in System Settings if it is not already on.
3. Legacy data: `flask nsd-migrate-projects`
4. Ongoing CBF updates: Settings → Master import.
