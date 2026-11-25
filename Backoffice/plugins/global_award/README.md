# Global Award (`global_award`)

Imports the IFRC MARC logframe as a published form template and one project per country. The Data Explorer tab, presentation and A4 report read the submitted project cycles.

## Permissions

- `admin.global_award.manage` — plugin settings and the MARC import (also System Manager).
- `admin.data_explore.global_award` — the Global Award tab in Data Explorer.

## Settings

Admin → Plugins → Global Award → Settings (`/admin/plugins/global_award/settings`). The Import tab has two sub-tabs, one per workbook, each with its own files-on-disk list, Preview option and change-log history. The overview links to the project list.

## The two workbooks

1. **Logframe** (`Annex 4 … Global Award Framework`, sheet `Logframe_Mastersheet`): the published template and one project per country. Import it first.
2. **Sectoral Interventions** (sheets `Sectoral interventions`, `PMER Focal Points`, `Project Managers`; the other sheets are ignored). For each country project it stores the sectors, pillar and source in `plan_data.sectoral`, and the people in `plan_data.contacts`. The first PMER focal point is also written to the project's focal person, the first project manager to its manager. Re-importing the logframe keeps these keys.

**Regional fallback.** A country uses the PMER focal points and project managers listed for it. When none are listed (Lebanon, Syria, Eswatini, Madagascar, Zimbabwe have no PMER focal point), it uses the region office of its region (`Africa – Regional`, `Region Office - AP`, …). The region comes from the Region column of the `Sectoral interventions` sheet. A country with neither is reported (Panama has no PMER focal point). A project manager row for `Pacific Islands` covers every country listed under it.

**Users.** Everyone named in the two contact sheets, including HQ and region office staff, becomes a user: no password, no welcome email (they sign in through SSO, or an admin sends the welcome email from Manage Users), role `assignment_viewer`. Each user joins the `Global Award` Access Group (created if missing, code `group_global_award`) and gets access to the countries they are the resolved focal point for, when that country has a project. Users that already exist are not changed apart from the group and country access. They are listed after every run: in the CLI output, in a notice on the settings page, and in the change log.

CLI, from `Backoffice/` (`$env:FLASK_APP = "run.py"`):

```powershell
python -m flask global-award-import                      # logframe
python -m flask global-award-sectoral-import --dry-run   # sectoral workbook, nothing saved
python -m flask global-award-sectoral-import
```

## Project → settings → reports

The import creates a core `Project` (portfolio `Global Award`) and report cycles through `ensure_project_cycle_assignment` (`Y1Q1`, `Y1Q2`, `Y1Q3`, `Final`). Those cycles stay `AssignedForm` rows with `scope=project_cycle`. PDF, Excel, review and access are edited once on the project row under Admin → Assignments and copied onto every report. This plugin supplies the official slots, dates and the published template through `BasePlugin.get_project_report_types`. It does not add an extra audience; access groups chosen on the project apply to every report.

`/admin/projects/` redirects to Admin → Assignments filtered to projects.

## How to test

From `Backoffice/`:

```powershell
python -m pytest plugins/global_award/tests -q
```

Open Admin → Assignments as an admin, filter Type to Project, open a Global Award project, enable Export PDF on Settings, save, and open one of its reports. The entry form shows the PDF button. Adding a report from the Reports tab inherits the same flags.
