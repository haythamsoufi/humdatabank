# DREF monitoring

Tracks DREF and Imminent DREF operations inside the Backoffice from the approved GO stage through routine monitoring to closure. Emergency Appeals are not synced. The operational guide is at `/help/docs/dref-monitoring/overview` and in Admin Documentation at `/admin/docs/dref-monitoring/overview`.

The public GO `dref3` API supplies the approved stage (country, dates, allocation, and the 14 sectors). The plugin turns that stage into a draft monitoring plan. A National Society validates the plan, then files activity status, people reached, and reported expenditure on a schedule. Edits that stay inside the latest approved budget, people targeted, and dates apply immediately. Edits outside those bounds become a change request for the sign-off authority (National Society leadership or the IFRC delegation). Reported expenditure is indicative until delegation finance validates it in ERP.

Pages, flashes, and reminder text follow the signed-in user's language: English, French, Spanish, or Arabic. Arabic uses a right-to-left layout. Generated plan labels (sector names, "Deliver Health", units) are stored in English and shown in the current language. Text a person typed — notes, risk titles, custom activity titles, and report chapters — stays as written. Draft 0 language is chosen when the draft is generated, and in plugin settings for scheduled drafts. The on-page preview, the Word file, and the PDF follow that draft language, including Arabic right-to-left text and the Tajawal face in the PDF.

When a newer GO stage changes the allocation or the end date, the validated plan is copied forward as a new draft so the bounds move with the latest approval.

## Permissions

Assign a role, then either grant the user country access or add them on the operation (needed for Partner National Society staff).

| Role | What it allows |
|---|---|
| `dref_monitoring_entry` | File reports, funds, procurement, delays, feedback, and risks |
| `dref_monitoring_validation` | Also validate the plan and submitted reports |
| `dref_monitoring_review` | Also review reports, manage members, and sign off when the delegation is the authority |
| `dref_monitoring_portfolio` | Every operation, governance, and the Data Explorer tab |
| `admin_dref_monitoring` | Settings and a manual GO sync, plus portfolio access |

System managers can open settings without the admin role. Portfolio permission sees every operation. Other roles only see operations in their countries or operations they are a member of. A membership tier can narrow a higher role on that one operation.

## Settings

`/admin/plugins/dref_monitoring/settings` shows the last sync, the plan-validation window, reminder and escalation days, and the Draft 0 switch.

Draft 0 uses the Databank OpenAI provider (`OPENAI_API_KEY` and `OPENAI_MODEL`). It stays off until the switch is enabled. The model receives the approved request and the monitoring history, in English, French, Spanish, or Arabic, and returns GO chapter text. It does not receive names or community feedback. Every call is stored on the draft (model, prompt version, input hash, language, and whether the model was used). If the call fails, the document is still the monitoring tables. The National Society edits the chapters, then validation posts the report to GO when `GO_API_TOKEN` is set. The same document downloads as a Word file with heading styles and as a PDF. The daily job creates a draft when a reporting period falls due and when the operation end date is reached.

## Excel import

On an operation, upload an `.xlsx` workbook with a sheet named `Activities` and columns: Group, Activity, Indicator, Indicator type, Target, Unit, Budget CHF, Start, End, Beneficiary unit. Import replaces a draft plan, or opens a new draft version when the current plan is already validated.

## Schedule

Two jobs run while the plugin is active: a GO sync at 05:10 UTC, and reminders plus escalation at 06:00 UTC. Sync from GO on the settings page queues the same pull as a background job and the page polls its status and progress, so the request returns immediately. The sync reads the whole public dref3 feed, creates or updates a project for each operation whose ISO3 matches a Databank country, and sets that project to closed when GO has closed the operation. Escalation notifies operation members: data entry before and just after the due date, then validation, the delegation, and portfolio as the delay grows. The reminder opens the project cycle on the country dashboard. A plan that is still a draft is reminded to the validation tier from three days before its validation date until it is validated.

Validating a plan opens one cycle per reporting period on the template **DREF operational monitoring**. That template is a master form: every sector, and every emergency indicator from the indicator bank. An assignment lists only the indicators on that operation's monitoring plan, then the planned activities. Each indicator collects one target for the plan. It does not collect a reported total or a sex or age split. Wording, type, and which extra questions appear are set in `plugins/dref_monitoring/scripts/report_questions.py`, and `SECTOR_NAME_TO_KEY` there maps a databank sector name onto a GO sector key when the names differ. A focal point for that country files the current cycle from the country dashboard. Saving stores the answers on the assignment. Submit and approve on the cycle move the report from draft to submitted, then to validated or reviewed.

`flask dref-monitoring-sync` pulls GO. `flask dref-monitoring-backfill-projects` creates projects for operations already synced, and cycles where the latest plan is already validated.

## How to test

From `Backoffice/`:

```powershell
python scripts/ci/check_plugin_contract.py --plugin dref_monitoring
python -m pytest plugins/dref_monitoring/tests tests/unit/test_plugins/test_plugin_contract.py tests/unit/test_plugins/test_plugin_route_access.py tests/unit/test_plugins/test_first_party_plugins.py --no-cov
```

Restart the dev server, activate the plugin under Admin > Plugins, sign in with Act as Admin, and open `/admin/plugins/dref_monitoring/settings`.

Community feedback and the risk register are included as optional sections on the operation page. They are not sent to the language model.
