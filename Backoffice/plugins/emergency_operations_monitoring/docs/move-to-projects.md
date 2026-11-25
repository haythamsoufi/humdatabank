# Move Emergency Operations onto projects

Validating a Emergency Operations plan should create a project and one reporting cycle per period. Those cycles show on the country dashboard the same way other project reports do.

The country does not report from **Analytics & Monitoring → Emergency Operations**. A focal point for that country opens the project card on the country dashboard and fills the current cycle.

## What the country sees

Each DREF appeal becomes one project:

| Project field | Source |
|---|---|
| `reference` | Appeal code, for example `MDRMM024` |
| `portfolio` | `Emergency Operations` |
| `fund` | Appeal type: DREF, i-DREF, or EA |
| `country_id` | Databank country matched from the GO ISO3 code |
| `title` | Disaster name |
| `start_date`, `end_date` | Approved operation dates |
| `amount_granted` | Approved allocation (CHF) |
| `status` | `Open` while the operation is monitored. `Closed` when GO marks it closed |
| `plan_data` | Pointer to the DREF operation id |

When the plan is validated, each reporting period becomes a project cycle through `ensure_project_cycle_assignment` in `app/services/projects/service.py`. That creates an `AssignedForm` with `scope=project_cycle` and one `AssignmentEntityStatus` for the project. The cycle carries the period start, period end, and due date. The due date is the period end.

The country dashboard already includes project assignments for projects in that country (`dashboard_assignment_entity_filter`) and collapses them into one card (`group_dashboard_project_assignments`). The card shows the current cycle. The cycle list opens the other rounds. No new dashboard card is required, and the focal point does not need a Emergency Operations role to open it.

Cycle labels use the period, for example `MDRMM024 · 2026-08`. `parse_cycle_slot` already returns whatever follows ` · `, so the label does not have to be `Y1Q1`. The quarterly **Add cycle** button on the project page stays the NSD control (`project_add_cycle` only publishes NSD templates). DREF cycles are generated from the operation dates.

## What happens at each step

| Moment | Result |
|---|---|
| GO sync | Create or update the project. Store `project_id` on the DREF operation. |
| Plan validated | Open one cycle per reporting period. Store `assigned_form_id` on the period. |
| GO update that changes the approved total, end date, or sector ceilings | Copy the plan into a new draft and set the workflow back to `plan_draft`. Submitted cycles stay. New periods are added when that plan is validated again. |
| GO marks the operation closed | Set the project status to closed. `sync_project_cycle_closure` closes its cycles. |

Reporting cadence stays as it is today. Imminent DREF and operations of about 60 days or less report every two weeks. Longer operations report monthly.

## The form on the cycle

The form on each cycle is the existing template **Emergency Operations**. Validating a plan replaces its contents in place: one section per sector selected on the plan, emergency indicators from the indicator bank, and the other fields as questions. Question wording lives in `plugins/emergency_operations_monitoring/scripts/report_questions.py`.

Saving the cycle stores those answers on the assignment. Bounds checks, change requests, date history, and Draft 0 keep reading the `dref_mon_*` tables, which the operation page still maintains.

Assignment status is the report status:

| Assignment | DREF report |
|---|---|
| Draft | Draft. **Save** on the cycle. |
| Submitted | Submitted by the National Society. |
| Approval steps on the template | National Society validation, then IFRC delegation review. |

The separate submit, validate, and review buttons on the DREF operation page are no longer the path the country uses.

Activity budgets entered on the cycle stay indicative until delegation finance validates them in the ERP.

## What stays in the plugin

These stay on the DREF operation and are not replaced by the project:

- GO `dref3` sync, baselines, and the sync log
- Plan generation, National Society validation of the plan, and rebase when GO re-baselines the allocation
- Within-bounds edits and change requests
- Draft 0, the on-page preview, and the Word and PDF export
- The portfolio tab in Data Explorer
- Community feedback and the risk register

Reminders and escalation keep the same ladder (three days before the due date, then validation, delegation, and portfolio). The link in the notification opens the assignment on the country dashboard, using the cycle due date.

## Data links

Add:

- `dref_mon_operation.project_id` → `project.id`
- `dref_mon_period.assigned_form_id` → `assigned_form.id`

`upsert_project` is the write path for the project row. `ensure_project_cycle_assignment` is the write path for each cycle. Both already exist.

## Backfill

Operations already synced, including plans that are already validated, get a one-time command:

1. Create or update the project for every operation that has a country.
2. Where the latest plan is validated, create the missing cycles and attach them to the periods.

An operation with no matching Databank country cannot become a project until the country exists. Those operations stay on the DREF operation page until the ISO3 matches.

## Build order

1. Link the operation to a project and upsert that project during sync.
2. On plan validation, create the cycles and attach them to the periods.
3. Publish the per-operation template (sector sections, emergency indicators, and scripted questions), and map assignment submit and approval onto the report status.
4. Backfill current operations.
5. Point reminders at the assignment.
6. Check as a country focal point: the dashboard card is there, the current cycle opens, and a saved report is stored on the operation.

## Verification

- Contract check: `python scripts/ci/check_plugin_contract.py --plugin emergency_operations_monitoring`
- Plugin tests, plus a test that validating a plan creates one project and one cycle per period, and that a second validation does not duplicate cycles.
- Browser: act as a focal point for the operation’s country, open the country dashboard, open the DREF project card, save the current cycle, and confirm the figures are on the DREF operation.
