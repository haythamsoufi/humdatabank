# DREF and Emergency Appeal monitoring

Tracks DREF, Imminent DREF, and Emergency Appeal operations inside the Backoffice from the approved GO stage through routine monitoring to closure. Emergency Appeals come from the public GO `appeal` API (see "Emergency Appeals" below); DREF and Imminent DREF come from `dref3`. The operational guide is at `/help/docs/dref-monitoring/overview` and in Admin Documentation at `/admin/docs/dref-monitoring/overview`.

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

Draft 0 uses the Databank OpenAI provider (`OPENAI_API_KEY` and `OPENAI_MODEL`). It stays off until the switch is enabled. The model receives the approved request with its written application (saved at sync from the GO emergency page), the monitoring history, recent public GO field reports, documents filed for this operation (its DREF, operations updates and situation reports), and the previous draft. It writes in English, French, Spanish, or Arabic and returns GO chapter text, following per-chapter instructions (prompt version 3). A model can be set in plugin settings, with a separate one for final reports. It does not receive community feedback or contacts. Notes, delay reasons, and risks are sent as typed, so keep names and contact details out of them. Every call is stored on the draft (model, prompt version, input hash, language, and whether the model was used). If the call fails, the document is still the monitoring tables. The National Society edits the chapters, then validation posts the report to GO when `GO_API_TOKEN` is set. The same document downloads as a Word file with heading styles and as a PDF. The daily job creates a draft when a reporting period falls due and when the operation end date is reached.

**Editing the narrative.** Each chapter is edited in place in the preview, or on the **Narrative** tab, one card per chapter. Both views share one store and stay in sync. The toolbar offers bold, italic, underline, bullet and numbered lists, undo and redo. Chapters are saved as a small HTML subset (`p`, `br`, `strong`, `em`, `u`, `ul`, `ol`, `li`); everything else is stripped on the server, and a chapter is capped at 6,000 characters of text. Saves are automatic, and a chapter the server refuses stays marked unsaved with the reason. Each card can **reset to the AI text** or **rewrite with AI**. The rewrite is a background job for that one chapter, and the text streams into the card while it is written. Figures-only drafts and validated drafts refuse edits. Routes: `POST drafts/<id>/chapters` (save), `.../chapters/<key>/reset`, `.../chapters/<key>/generate`, `POST drafts/<id>/import.docx`. Old drafts that stored plain text open with that text in the first chapter.

**Word round trip.** The Word export marks text Databank writes from the figures with the *Generated text* and *Generated bullet* styles, and carries the draft reference in the file properties. **Import Word file** on the draft page reads a file edited in Word, matches chapters by their heading (in any of the four languages), and shows a review with the words before and after for each chapter. Nothing is stored until the person confirms. Tables and figure-generated text are skipped, text under unrecognised headings is listed as ignored, and a file exported from a different report gets a warning.

The entry form of each reporting cycle has **Operational update** and **Final report** buttons in its header, for people with data-entry access on the operation. The final report button appears only on the last cycle. Each opens a dialog that picks the narrative: AI-generated (only when the Draft 0 switch is on), written by hand, or data only. A data-only draft has the monitoring tables and no narrative chapters.

An AI draft runs as a background job (`dref.draft`, an `AIJob`), because a reasoning model takes a minute or more. The form posts with `Accept: application/json` and gets `202` with the job; `report_actions.js` then polls `GET /dref-monitoring/operations/<id>/drafts/jobs/<job_id>` and shows the stage (collecting figures, reading the application, field reports and documents, then "Writing chapter n of N", counted from the streamed reply) with a progress bar and a Cancel button (`POST .../cancel`, which stops the stream between chunks and stores no draft). The same request from the same person reuses the running job, and a reloaded operation or draft page picks the job up again. A job is visible only to the person who started it. A draft without a model (written by hand or data only) is still created in the request. Without JavaScript the form posts normally and the request waits for the model.

## Emergency Appeals

GO's `dref3` feed has no Emergency Appeals. Its rows tagged `EA` are DREFs allocated as loans against an appeal, and they share the appeal code. Real Emergency Appeals come from `https://goadmin.ifrc.org/api/v2/appeal/` (`atype=1`), read for active appeals and for appeals started since the configured year, whatever their status (settings: **Emergency Appeals**, default since 2025; the same page can switch them off).

- **Budget and people.** GO publishes the amount requested and the number of beneficiaries, not sector budgets, indicators, or activities (those are in the Emergency Plan of Action PDF). The plugin uses the amount requested as the approved total and the beneficiaries as the people targeted. The starting plan is an "Operation" group sized to the appeal budget.
- **Indicators from the bank.** The plan also gets one sector group per sector of the indicator bank, listing every indicator marked **Emergency** (`IndicatorBank.emergency`), each with its bank id, unit and type. Sector groups carry no budget. Every indicator starts switched on (`DrefIndicator.enabled`). They appear in the plan table like any other sector and indicator. In **Edit plan**, each indicator has a **Report on this indicator** checkbox and each sector has **Switch all on** and **Switch all off** (plus one pair for the whole plan); they save with the rest of the plan and its justification. A switched-off indicator stays on the plan, shown dimmed as "Not monitored", and is left out of the monitoring figures and the reporting form (`plan_indicator_filter`). At least one must be on to confirm. Switching an indicator on a confirmed plan opens a new draft, like adding a sector or activity, and the new draft keeps the switches. A draft appeal plan is topped up with bank indicators it lacks, on opening the plan tab and on every sync, so plans made earlier get them too; switches already set are kept. DREF plans are unchanged and never take bank indicators. Activities and Excel import work as before.
- **Same code as a loan.** The appeal stage is always the latest stage for its code, so a loan DREF never overrides the appeal budget. Loan stages stay as earlier baselines. A loan with no appeal row keeps the sector plan built from its DREF stage.
- **Status.** Active stays active. Frozen, Closed, and Archived close the operation.
- **Event details.** Districts, disaster date, people affected, and the written summary come from the public emergency page (`/api/v2/emergency/{event}/`). A page that cannot be read leaves the stored details as they are.
- **Reports.** Titles, the cover table, and the language-model prompt say Emergency Appeal. GO has no write endpoint for appeal reports, so a validated appeal report stays in the Databank and is downloaded as Word or PDF. It is never posted to GO.
- **Project.** The project keeps portfolio `DREF` and gets fund `EA`.
- **Failure.** When the appeal API cannot be read, the DREF pull still runs, stored appeals are held as they are, and loan stages of an appeal already stored are ignored until the next successful read.

## Reporting schedule

The monitoring plan tab shows the reporting frequency and a preview of every period it would open (period start, end, and due date), for DREFs and Emergency Appeals alike. The preview comes from `services/schedule.py` and uses the same `build_periods` the cycles use.

- **Frequency.** It is not read from the DREF application. `default_frequency` (`services/periods.py`) sets it once, when the operation is created: Imminent DREF and operations of 60 days or less are biweekly, longer ones monthly. It is stored in `reporting_frequency`. While the plan is a draft and no cycle exists, the plan tab changes it (the table updates without saving; **Use this frequency** saves it). After that, portfolio staff change it under Governance.
- **Periods.** Monthly periods end on the last day of a calendar month, biweekly ones are 14-day blocks, and each report is due on its period end. At most 36 periods are opened.
- **Start.** A DREF counts from its start date. An Emergency Appeal often began months or years earlier, so it counts from the day its plan is confirmed (the current month for monthly): that day is stored in `reporting_start` and never moves. An appeal that has not started yet keeps its start date.

Migration `dref_monitoring_appeal_plan` adds `dref_mon_indicator.enabled` and `dref_mon_operation.reporting_start`.

## Excel import

On an operation, upload an `.xlsx` workbook with a sheet named `Activities` and columns: Group, Activity, Indicator, Indicator type, Target, Unit, Budget CHF, Start, End, Beneficiary unit. Import replaces a draft plan, or opens a new draft version when the current plan is already validated. Group names must match the sectors of the latest GO stage, the ceilings come from GO and not from the sheet, and a sheet that goes past a sector budget is refused. Up to 2,000 rows and 5 MB.

## Schedule

Two jobs run while the plugin is active: a GO sync at 05:10 UTC, and reminders plus escalation at 06:00 UTC. Sync from GO on the settings page queues the same pull as a background job and the page polls its status and progress, so the request returns immediately. The sync reads the whole public dref3 feed and, unless switched off, the Emergency Appeals from the `appeal` API. It creates or updates a project for each operation whose ISO3 matches a Databank country, and sets that project to closed when GO has closed the operation. Escalation notifies operation members, and people who hold a DREF role and have access to the operation's country: data entry before and just after the due date, then validation, the delegation, and portfolio as the delay grows. The reminder opens the project cycle on the country dashboard. A plan that is still a draft is reminded to the validation tier from three days before its validation date until it is validated.

Validating a plan opens one cycle per reporting period on the template **DREF operational monitoring**. That template is a master form: every sector, and every emergency indicator from the indicator bank. An assignment lists only the indicators on that operation's monitoring plan, then the planned activities. Each indicator collects one target for the plan. It does not collect a reported total or a sex or age split. Wording, type, and which extra questions appear are set in `plugins/dref_monitoring/scripts/report_questions.py`, and `SECTOR_NAME_TO_KEY` there maps a databank sector name onto a GO sector key when the names differ. A focal point for that country files the current cycle from the country dashboard. Saving stores the answers on the assignment. Submit and approve on the cycle move the report from draft to submitted, then to validated or reviewed.

`flask dref-monitoring-sync` pulls GO. `flask dref-monitoring-backfill-projects` creates projects for operations already synced, and cycles where the latest plan is already validated.

## How to test

From `Backoffice/`:

```powershell
python scripts/ci/check_plugin_contract.py --plugin dref_monitoring
python -m pytest plugins/dref_monitoring/tests tests/unit/test_plugins/test_plugin_contract.py tests/unit/test_plugins/test_plugin_route_access.py tests/unit/test_plugins/test_first_party_plugins.py --no-cov
```

Restart the dev server, activate the plugin under Admin > Plugins, sign in with Act as Admin, and open `/admin/plugins/dref_monitoring/settings`.

Community feedback and the risk register are optional sections on the operation page. Community feedback is not sent to the language model. Risk titles, likelihood, impact, status, and mitigation notes are.
