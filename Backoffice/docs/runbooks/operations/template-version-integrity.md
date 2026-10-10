# Template version integrity

> **Who this is for:** developers and operators who see a template deploy refused, or who are about to deploy a template with a long history. Admin-facing behaviour is described in [Template versions](../../user-guides/admin/template-versions.md).

## What protects a deploy

| Layer | What it does | Where |
|---|---|---|
| Row lock | Create-draft and deploy lock the `form_template` row so two admins cannot change versions at once | `versions.py` (`_lock_template_for_version_change`) |
| Identity keys | `stable_key` on items and sections links the same field across versions; keys are never overwritten by position | `version_deploy_migration_service.py` |
| Duplicate guard | Deploy refuses (and changes nothing) if a version has the same key on more than one row | `_assert_unique_stable_keys` |
| Unmapped guard | Deploy refuses if submission rows exist on the old version but nothing could be matched | `migrate_submission_fks` |
| Acknowledgement | Deploy refuses until the admin acknowledges live fields with data that have no match in the new version | `deploy_template_version` (`acknowledge_orphaned_data`) |
| Entry-form guard | A data-entry save takes a share lock on the template and is refused if the form was rendered for an older published version | `entry_form_is_stale` (`routes/forms/helpers.py`) |
| Link rules | Linking draft to live fields is blocked for different kinds, and needs confirmation for data-type / indicator differences | `helpers/field_mapping.py` |
| Delete guard | A version with data (submissions, repeats, documents, AI validations, page statuses) cannot be deleted; the check fails closed | `delete_template_version` |
| Page guard | A page with workflow progress cannot be removed from the live version | `_handle_template_pages` |

Deploys are atomic: if the data move fails, the whole transaction is rolled back and the previous version stays live.

## Run the audit

Read-only. Run from `Backoffice/` (before the first deploy in an environment, and after any bulk import):

```bash
python scripts/ops/audit_template_versions.py            # all templates
python scripts/ops/audit_template_versions.py --template-id 22
python scripts/ops/audit_template_versions.py --json
```

Exit code `1` means a blocking finding.

| Finding | Blocking | Meaning and fix |
|---|---|---|
| `multiple_drafts` | Yes | More than one draft for a template. Keep one; discard the others in the Form Builder |
| `published_inconsistencies` | Yes | More than one published version, or `published_version_id` does not point at the published one. Fix with a reviewed SQL update, never by guessing |
| `duplicate_item_keys` / `duplicate_section_keys` | Yes | Two rows of one version share a `stable_key`. Give one row a new key (`app.utils.stable_key.generate_stable_key`) or unlink it in the field mapping page |
| `items_without_key` / `sections_without_key` | No | Older rows without keys. Deploy backfills by position, but running `python scripts/ops/backfill_stable_keys.py --dry-run` first makes the result reviewable |

## Deploy refused: quick triage

| Message | First step |
|---|---|
| `Cannot deploy: N field/section identity key(s) are shared by more than one …` | Run the audit for that template and fix the duplicates |
| `Cannot deploy: N submission row(s) exist on the previous version but no fields could be matched …` | Run `backfill_stable_keys.py --dry-run`, review, then run it for real. If it persists, use `scripts/archive/repair_version_deploy_migration.py` with the suggested arguments |
| `N field(s) in the live version hold submitted data but have no match …` | Not an error: the admin must acknowledge it on the deploy dialog or the field mapping page |
| `The selected version was not found for this template.` | A stale tab; reload |

## Database constraints: plan (decided: audit first, then enforce)

The checks above run in the application. The database does **not** yet enforce them, so a script, a manual SQL change or a bug can still create a state the app then refuses at deploy time. `uq_template_version_number` (unique `template_id`, `version_number`) already exists. The constraints still to add:

1. `form_template_version (template_id) WHERE status = 'draft'` unique: one draft per template
2. `form_item (version_id, stable_key) WHERE stable_key IS NOT NULL` unique
3. `form_section (version_id, stable_key) WHERE stable_key IS NOT NULL` unique

Decision: **audit every environment and fix findings first, then ship the migration in a later release.** Excel import now never assigns one key to two rows (`claimed_keys` in `_resolve_import_stable_key`), so enforcing them will not break imports.

Checklist before the enforcing migration is released:

- [ ] `python scripts/ops/audit_template_versions.py` exits `0` in every environment (dev, staging, production)
- [ ] Any `multiple_drafts`, `published_inconsistencies` and duplicate-key findings were fixed and the audit re-run
- [ ] The enforcing migration is reviewed. It checks for violations itself and aborts with the offending rows listed instead of failing half-way
- [ ] Released at a quiet time, with a database backup taken first ([Backup & restore](../data/backup-and-restore.md))

Until the migration ships, the application checks above are the only protection.

## Related

- [Template versions (admin guide)](../../user-guides/admin/template-versions.md)
- [Template versioning and submission data identity (design)](../../template-version-submission-identity.md)
- [Form operations](form-operations.md)
