# Global Award (`global_award`)

Imports the IFRC MARC logframe as a published form template and one project per country. The Data Explorer tab, presentation and A4 report read the submitted project cycles.

## Permissions

- `admin.global_award.manage` — plugin settings and the MARC import (also System Manager).
- `admin.data_explore.global_award` — the Global Award tab in Data Explorer.

## Settings

Admin → Plugins → Global Award → Settings (`/admin/plugins/global_award/settings`). The import panel uploads the logframe workbook and links to the project list.

## Project → settings → reports

The import creates a core `Project` (portfolio `Global Award`) and report cycles through `ensure_project_cycle_assignment` (`Y1Q1`, `Y1Q2`, `Y1Q3`, `Final`). Those cycles stay `AssignedForm` rows with `scope=project_cycle`. PDF, Excel, review and access are edited once on the project row under Admin → Assignments and copied onto every report. This plugin supplies the official slots, dates and the published template through `BasePlugin.get_project_report_types`. It does not add an extra audience; access groups chosen on the project apply to every report.

`/admin/projects/` redirects to Admin → Assignments filtered to projects.

## How to test

From `Backoffice/`:

```powershell
python -m pytest plugins/global_award/tests -q
```

Open Admin → Assignments as an admin, filter Type to Project, open a Global Award project, enable Export PDF on Settings, save, and open one of its reports. The entry form shows the PDF button. Adding a report from the Reports tab inherits the same flags.
