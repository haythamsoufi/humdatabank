# Handover: Bilateral Support matrix overwrite, 18 September 2026

Investigation date: 5 October 2026. Source: five custom-format Postgres dumps in the repo root (`PGDMP`, not plain SQL). Read them with `pg_restore -a -t <table> -f -`, not a text search.

Dumps compared:

| File | Taken |
|---|---|
| `prod_dump-postgres-202609171017.sql` | 17 Sep 2026 10:17 — last dump with the full matrices |
| `prod_dump-postgres-202609182335.sql` | 18 Sep 2026 23:35 — first dump after the overwrite |
| `prod_dump-postgres-202609221725.sql` | 22 Sep 2026 17:25 |
| `prod_dump-postgres-202609301550.sql` | 30 Sep 2026 15:50 |
| `prod_dump-postgres-202610051127.sql` | 5 Oct 2026 11:27 |

## Answer

Nothing was deleted from `entity_activity_log` between these dumps. Every id in the 17 Sep dump is still in the 5 Oct dump. Ids added after 17 Sep (4622–5104) are contiguous, so nothing was inserted and then removed inside that window either.

There are older holes, already present on 17 Sep. The table’s first surviving row is id 3307 at 2026-06-30 09:45. Between 3307 and the max id 4621, 331 ids are absent. Two holes sit on focal form saves that have a `user_activity_log` row and no entity activity:

| Missing ids | Bracketed by surviving rows | Focal saves inside the hole with no entity activity |
|---|---|---|
| 3650–3794 (145 ids) | 3649 at 2026-08-11 09:56 and 3795 at 2026-08-11 19:43 | AES 1685 user 73 at 13:13; AES 1630 user 136 at 14:41 |
| 3817–3962 (146 ids) | 3816 at 2026-08-12 15:12 and 3963 at 2026-08-13 00:00 | AES 1630 user 136 at 17:29 |

Those holes are much larger than the form saves visible in `user_activity_log` that afternoon (a handful of `form_saved` rows, not 145). The missing ids were already gone before the first dump. These dumps cannot show what was in them.

On the bilateral form itself, focal matrix entry in July–August is in the log. Austria has 17 activities through the 4 Aug submission. The 18 Sep overwrite did not add one. That write is the import at 10:36, not a focal save.

The 17 September dump is the restore source for those matrices.

## The record that started this

| Field | Value |
|---|---|
| `form_data.id` | 288362 |
| `assignment_entity_status_id` | 4096 |
| `form_item_id` | 1433 (matrix, blank label, section 439 “Financial Overview”, template 23) |
| Assignment | `assigned_form` 34, period **Jan-Jun 2026**, template **Reporting - International Bilateral Support** |
| Entity | country 10, Austria (AUT) |
| AES status | `submitted` since 2026-08-04 10:38:36, `submitted_by_user_id` 156, `completion_rate` 100. Unchanged in all five dumps. `published_at` is null. |
| Created | 2026-07-29 10:26:43 by user 133 |

Other Austria rows on the same assignment were **not** touched: form items 1434 (PNS staff contributions, `form_data` 288363), 1488 and 1489 (comments). Scalar `value` on 288362 stayed null. The payload is `disagg_data` (`disagg_type=matrix`).

### Austria matrix

17 Sep dump, `submitted_at` 2026-08-04 10:37:09, `disagg_data` length 3526. Full partner-NS matrix (Lebanon 101, Ukraine 185, Afghanistan 1, Armenia 8, Ethiopia 59, and others), with SP1–SP5, EFs, and the three totals.

From the 18 Sep dump through the 5 Oct dump, `submitted_at` is 2026-09-18 10:36:30.028878 and `disagg_data` is only:

```json
{"10_Total Expenditure": 0, "10_Total Funding": 4243635, "10_Total Transferred to HNS": 1476641}
```

Key `10_` is Austria’s own country id, not a partner National Society. The funding and transfer figures match the previous **Ukraine (country 185)** row (`185_Total Funding` 4243635, `185_Total Transferred to HNS` 1476641). Ukraine expenditure had been 6568756 and is now 0. Do not assume that “copy one partner row, zero expenditure, rekey to the reporting country” holds for every society until it is checked.

## Blast radius (form_item 1433 only)

Same `assigned_form` 34. Compared 17 Sep vs 18 Sep only. Austria’s collapsed row is unchanged through 5 Oct; the other societies were not re-checked after 18 Sep.

All surviving rows were rewritten in the same second (10:36:30 or 10:36:31) from a multi-row matrix down to three keys: `{reporting_country_id}_Total Expenditure`, `_Total Funding`, `_Total Transferred to HNS`.

| AES | Country | 17 Sep length | 18 Sep payload |
|---|---|---|---|
| 4089 | Australia (9) | 1848 | `9_Total Expenditure` 24782, Funding 835159, Transferred 314780 |
| 4091 | Japan (83) | 1953 | `83_` Expenditure 0, Funding 67443, Transferred 67443 |
| 4093 | Malaysia (104) | 344 | `104_` Expenditure 0, Funding 36818, Transferred 0 |
| 4094 | New Zealand (125) | 1232 | `125_` all zeros |
| 4096 | Austria (10) | 3526 | `10_` Expenditure 0, Funding 4243635, Transferred 1476641 |
| 4097 | Belgium (16) | 2062 | `16_` Expenditure 0, Funding 842711, Transferred 80178 |
| 4100 | France (61) | 3521 | `61_` Expenditure 0, Funding 8457768, Transferred 1848960 |
| 4103 | Ireland (81) | 243 | `81_` all zeros |
| 4105 | Liechtenstein (98) | 162 | `98_` all zeros |
| 4109 | Norway (130) | 3628 | `130_` Expenditure 0, Funding 2495422, Transferred 262739 |
| 4110 | Spain (161) | 5539 | `161_` Expenditure 227889, Funding 227889, Transferred 218588 |
| 4111 | Sweden (172) | 3248 | `172_` Expenditure 0, Funding 1291637, Transferred 1207137 |
| 4112 | Switzerland (166) | 7432 | `166_` Expenditure 0, Funding 0, Transferred 11340 |
| 4114 | United Kingdom (181) | 5183 | `181_` all zeros |

Three `form_item` 1433 rows present on 17 Sep are **absent** on 18 Sep (this check was only for item 1433, not the rest of the submission):

| AES | Country | AES status on 18 Sep |
|---|---|---|
| 4099 | Finland (60) | pending |
| 4108 | Netherlands (123) | pending |
| 4120 | Testland (193) | pending |

Count of `form_item` 1433 rows: 17 on 17 Sep, 14 on 18 Sep.

## Recent entity activities

Table: `entity_activity_log`. Dashboard feed is `get_country_recent_activities` (`Backoffice/app/services/notification/core.py`), called from `Backoffice/app/routes/main/dashboard.py` with `days=30` for the first page.

Table size across dumps (no id was lost; growth equals new rows):

| Dump | Rows | Max id | Newest timestamp |
|---|---|---|---|
| 17 Sep | 984 | 4621 | 2026-09-17 06:29:38 |
| 18 Sep | 1020 | 4657 | 2026-09-18 17:54:14 |
| 22 Sep | 1060 | 4697 | 2026-09-22 14:41:28 |
| 30 Sep | 1298 | 4935 | 2026-09-30 13:12:40 |
| 5 Oct | 1467 | 5104 | 2026-10-05 09:15:56 |

Austria (`entity_type=country`, `entity_id=10`) has the same 17 rows in every dump. Nothing was added or removed. Last event is still the 4 August submission. There is no Austria activity in September at all.

Assignment 4096 activity ids, identical in every dump: 3461, 3510, 3513, 3514, 3515, 3516, 3539, 3540, 3541, 3544, 3545, 3546, 3547, 3548, 3549, 3550, 3551.

| When | Id | User | What |
|---|---|---|---|
| 2026-07-29 10:26:43 | 3461 | 133 Sonja Greiner (`sonja.greiner@roteskreuz.at`) | Fields added, including the matrix |
| 2026-07-31 | 3510, 3513–3516 | 133 | Staff matrix 1434 and comments 1489 |
| 2026-08-03 to 2026-08-04 10:37 | 3539, 3540, 3541, 3546, 3550 | 156 Sabrina Raff (`sabrina.raff@roteskreuz.at`) | Matrix and comments updates |
| 2026-08-04 morning | 3544, 3545, 3547–3549 | 133 | Comments 1489 |
| 2026-08-04 10:38:36 | 3551 | 156 | `activity.assignment_submitted` |

The 18 Sep dump has 21 activities timestamped that day (other countries: data updates, reopen, submit, approve). None is at 10:36, none has `assignment_id` 4096, and none is `activity.upr_excel_import` or `excel_import`.

Compared with `user_activity_log` on the 17 Sep dump (assignment id taken from the URL, entity activity counted when `assignment_id` matches within 15 seconds):

| Who | Result |
|---|---|
| Focal `form_submitted` | 82 matched, 2 unmatched |
| Focal `form_saved` | 697 matched, 210 unmatched at 15s; 23 still unmatched at 1 hour |
| User 1 `form_saved` | 2 matched, 662 unmatched |

The 662 user-1 rows are almost all `forms.view_edit_form` on 23 Jul, seconds apart, across many assignments. They are not focal entry. `log_entity_activity` commits on its own and rolls the session back if that commit fails (`Backoffice/app/services/notification/core.py`), which consumes a sequence id and leaves no row. A failed activity commit after the form save has already committed would look like a save with no entity activity.

Austria’s extra clicks (for example 31 Jul 11:15, user 133) sit about an hour from a logged save. The logged matrix edits are still there. Spain AES 4110 and Netherlands AES 4108 have focal `form_saved` / `form_submitted` on 22 Jul by user 40 with the nearest entity activity days away.

The dashboard still looks empty for Austria for two further reasons:

1. The 18 Sep overwrite never called `log_entity_activity`. Normal form save does, in `Backoffice/app/routes/forms/entry.py`. The per-assignment UPR Excel import also does, in `Backoffice/plugins/upr/excel/assignment_routes.py` (`summary_key` `activity.upr_excel_import`). The admin bulk runner does not.
2. Austria’s last real activity is 4 August. The dashboard window is 30 days, so those rows had already aged out of the default “recent” list on 3 September. They are still returned by a 365-day query (`load_more_activities`).

## Correlated request

`user_activity_log` id **92058**, user **1** Haytham ALSOUFI (`haytham.alsoufi@ifrc.org`), timestamp **2026-09-18 10:36:04.968859**.

- Endpoint `upr_excel_import.run_import`
- `POST /admin/upr-excel-import/run`
- HTTP 202 (async job queued)
- `context_data` is only `{endpoint, method, status_code}`. It never received `job_id`, `change_log_url`, or row counts.

`form_data.submitted_at` on the rewritten matrices is 26 seconds later (10:36:30). `submitted_at` on `form_data` is `onupdate=utcnow` (`DataEntryMixin`), so any update of the row stamps it. AES `submitted_at` and status did not move, which fits a direct data write rather than a user resubmit.

Code path: `Backoffice/plugins/upr/excel/import_routes.py` `run_import` → `UprExcelImportService.run_import` → `import_upr_excel_data.run_upr_import`. Default `template_ids` in that route are `[24, 22]`, not template 23. The audit row does not record which templates or rounds were posted, so that default is not proof of what ran. Same user, same minute, also created new assignments (`user_activity_log` 92059–92062), including template 23 period 2025 for country 30 at 10:40:15. That is a different action from the matrix rewrite.

Import change logs are not in Postgres. `Backoffice/app/services/imports/import_change_log.py` writes JSON plus JSONL under the `import_logs` storage category and is supposed to patch `change_log_url` onto the user-activity row. That patch did not land on id 92058. The next agent should look in production blob/filesystem `import_logs` for a log finalized around 10:36 UTC on 18 Sep 2026.

## Restore

Done on production on 5 October 2026 with `Backoffice/scripts/ops/restore_t23_bilateral_matrix_1433.py` (`--commit --force` after a dry-run). Scope was `form_item` 1433 on `assigned_form` 34, taken from the 17 Sep dump. 14 matrices were updated, 3 were inserted (Finland, Netherlands, Testland), and those three statuses were put back. Nothing was skipped. A second read of the 17 Sep dump matched all 17 live matrices, including Austria `form_data` 288362 (180 cells; Ukraine expenditure 6568756). Finland, Netherlands, and Testland received new `form_data` ids because the old rows had been deleted. Staff item 1434, comments, published snapshots, and template 33 were not written.

## Still open

1. Confirm whether Finland (4099), Netherlands (4108), and Testland (4120) lost only item 1433 or more of the submission.
2. Find the import log for `user_activity_log` 92058 and see whether template 23 / period Jan-Jun 2026 was in scope. If it was, fix the importer so it does not replace a partner-NS matrix with one row keyed by the reporting country id, and so it writes `entity_activity_log` (the assignment Excel import already does).
3. Do not look for deleted `entity_activity_log` rows. They are not missing. The gap is the unlogged 10:36 write, plus the 30-day dashboard window hiding August events.
