# NSD funds (`nsd_report_forms`)

Monitoring and reporting of National Society Development (NSD) funded projects (CBF first) inside the Databank,
replacing the MOMO proof of concept. Everything is plugin code and form-builder templates; the plugin adds no tables
and relies on one core entity type, the initiative.

## What it contains

| Part | Where |
|---|---|
| Two form field types: outcome / output tracking table (`nsd_logframe`), small add-row list (`nsd_list`) | `plugin.py`, `static/js`, `templates/field*.html` |
| Entry-form behaviour for templates named "NSD ...": locked project information, traffic-light selectors, empty repeat sections | `static/js/nsd-report-forms.js` |
| Master Excel import (preview, background run, safe to repeat) | `importer/`, `routes.py`, `templates/nsd_import/` |
| Admin project overview (MOMO-style list and project page) | `routes_overview.py`, `overview/`, `templates/nsd_projects/` |
| Personal page for IFRC project managers (`/nsd-funds/pm-overview`) | `routes_pm.py`, `templates/nsd_pm/` |
| Explore Data tab "NSD funds" | `plugin.py` (`get_data_explorer_tab`), `templates/nsd_explorer/` |
| Read-only API for other systems (`/api/v1/nsd-funds/deadlines`, `/projects`, `/kpis`; API key, `submissions:read`) | `api_routes.py`, `api_kpis.py` |
| Roles and permissions (seeded by the plugin) | `plugin.py` (`get_seed_roles`, `get_seed_permissions`) |
| Access for new accounts from project contact emails | `access_on_create.py` |
| KPI badges on the dashboard report cards (core hook `get_assignment_badges`) | `badges.py` |

## Data model

Every project is an **initiative** (core entity type, `app/models/initiatives.py`): reference, title, National Society
(its country follows from it) and an active flag. One assignment is one reporting period of one template, and holds one
row per initiative with its own due date, status and answers:

| Template | Assignments (periods) | Notes |
|---|---|---|
| NSD Project profile - CBF | `Project` | the project record; inactive, never a task |
| NSD Quarterly report - CBF | `Y1Q1` ... `Y3Q4` | one per quarter that occurs in the schedule |
| NSD Final report - CBF | `Final` | |

Project information inside a report is a locked copy written by the import and refreshed on every import. Reports of a
closed project that were never started are `cancelled` (shown under past assignments) and go back to `pending` if the
project reopens. The plugin adds no tables; everything is in the core template, assignment and form-data tables.

The import page has a step that deletes assignments of the earlier layout (one assignment per project report, period
`<reference> Y1Q2`, given to the country). It only matches that exact shape and refuses to run before the new layout
has reports.

## Access

| Who | How | Sees |
|---|---|---|
| NSD team | role "Admin: NSD funds" (seeded) | project overview, import, all NSD reports, assignment management |
| NS focal point, IFRC project manager | entity permission on their initiative, granted by the import from the contact emails and when a new account is created (never removed automatically) | the reports of their own projects, on their dashboard |
| Everyone else | nothing to do | no NSD reports; a country permission does not cover the initiatives of that country |

Limit the final report to project managers with the assignment's "Who can access this assignment" (Access Groups);
there is one Final assignment, so this is set once. The personal page `/nsd-funds/pm-overview` needs the permission
`nsd_funds.pm_overview` (in the admin role; give it to project managers through a role of your choice).

## Install

The plugin ships with the repository. After deploying:

1. Run the migrations (the initiative table) and restart once, so the field types, role and permissions are loaded.
2. Settings: enable the entity type "Funded Initiatives".
3. Create the three CBF templates with the form builder's Excel import (names as above) and publish them.
4. Explore Data > NSD funds > NSD master import: upload the workbook, check the preview, run it.
5. Set the audience of the Final assignment.
