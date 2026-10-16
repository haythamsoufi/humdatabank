# NSD funds (`nsd_report_forms`)

Monitoring and reporting of National Society Development (NSD) funded projects (CBF first) inside the Databank,
replacing the standalone MOMO system. Everything is plugin code and form-builder templates; no table is added to core.

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

## Data model

Projects live under their **country**. Each project has a hidden project record (an inactive assignment of the
"NSD Project profile - CBF" template, period `<reference> Project`) and one assignment per report
(`<reference> Y1Q2`, `<reference> Final`), all given to the project's country. Project information inside a report is a
locked copy written by the import and refreshed on every import.

## Roles

| Role | Sees | Notes |
|---|---|---|
| Admin: NSD funds | everything NSD, overview, import | plus assignment management |
| Assignment: NSD NS focal point | quarterly reports of their countries | never the final report |
| Assignment: NSD IFRC project manager | quarterly and final reports of their countries, personal PM page | supersedes the focal role |

The import limits every NSD assignment to these roles with core's assignment access control
(`AssignedForm.allowed_roles`), so ordinary assignment roles with country access do not see NSD reports.
Contact emails in the project records give existing users their country access and role on import, and new accounts
get them when they are created.

## Install

Install the plugin zip (Admin > Plugin Management) and restart once so the field types, roles and permissions are
loaded. Create the three CBF templates from the Excel files provided by the NSD team, then use Explore Data >
NSD funds > NSD master import.
