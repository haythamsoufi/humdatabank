# Template versions: draft, deploy and roll back

Every change that affects how a form is filled in goes through a **version**. This guide explains what happens to submitted data when you create, deploy, roll back or delete a version, and what the system checks for you.

## The short version

- You never edit the live form while people are filling it in. You work on a **draft**, then **deploy** it.
- On deploy, answers already submitted are **carried over** to the same fields in the new version.
- Fields you removed are **not deleted**. Their data stays on the archived version.
- If something looks wrong, you can **roll back** by deploying the archived version again.

## Version states

| State | Meaning | Who sees it |
|---|---|---|
| **Draft** | Work in progress. Only one draft can exist per template. | Admins in the Form Builder |
| **Published** | The live version. Exactly one per template. | Focal points filling in assignments |
| **Archived** | A previous live version. Its structure and data are kept. | Admins (can be re-deployed) |

## Create a new version

1. Open the template in the Form Builder and click **Versions**.
2. Click **Add New Version**. The draft is a full copy of the version you were viewing: structure, rules, variables, translations and settings.
3. Edit the draft freely. Nothing changes for focal points until you deploy.

Notes:

- Only one draft can exist at a time. Deploy or discard the current draft first.
- Rules, conditions, list filters, section "entry label" fields and variables in the draft keep working: they are re-pointed to the copied fields.

## Field identity: how the system knows two fields are "the same"

Each field and section has a hidden **identity key**. A copy keeps the key of the original, so after deploy the system knows that "Number of volunteers" in version 3 is the same field as in version 2, even if you renamed it or moved it.

- If you **rename, move or reword** a field, the identity stays and the data follows.
- If you **delete a field and add a new one**, the new field has a new identity and starts empty.
- Keys are never overwritten by position. Position is only used to repair older templates that predate identity keys.

## Review the field mapping before deploying

Open **Versions → Review field mapping** (the link icon) on the draft.

| Badge | Meaning | What deploy does |
|---|---|---|
| **Linked** | Same identity as a live field | Data is carried over |
| **Suggested** | The system guessed a match by position | Confirm or choose another field |
| **New field** | No live counterpart | Starts empty |
| **Orphaned** | Live field with no match in the draft | Data stays on the archived version |

### Linking a draft field to a live field

Use this when you replaced a field and want its answers to follow.

- **Different kinds of field cannot be linked** (for example a question and a matrix, or a standard section and a repeat section). Their data is stored differently.
- If the kinds match but the **data type** (for example number vs text) or the **indicator** differs, you are asked to confirm. Existing answers are carried over as they are, so a number field linked to a text field may show unexpected values.
- If the live field is already linked to another draft field, you are asked whether to move the link. The other draft field becomes a new field.
- **Mark as new field** removes a link so the field starts empty.

## Deploy

Click **Deploy**. The system:

1. Checks that every indicator field has a valid indicator.
2. Checks that no two fields of the draft share an identity (if they do, the deploy stops and nothing changes).
3. Moves answers, repeat rows, dynamic indicator data, uploaded documents and page workflow status to the matching fields and pages of the new version.
4. Re-points template variables that read a field.
5. Archives the previous version and publishes the new one.
6. Recalculates completion rates and clears cached form structure.

If any step fails, the deploy is cancelled as a whole: the previous version stays live.

### Fields that hold data but are removed in the draft

If live fields with submitted data have no match in the draft, you must **acknowledge** this:

- In the Form Builder, the confirmation dialog lists how many fields are affected. Confirming deploys.
- On the field mapping page, tick the checkbox next to **Deploy**.

Nothing is deleted. The data stays on the archived version, but it no longer appears in the entry form or in exports of the live version. If you did not intend this, link the fields instead (see above) or go back to the builder.

### While people are entering data

- A deploy waits for a save in progress, so the saved answers are carried over.
- A focal point who opened the form **before** the deploy and clicks **Save** **after** it sees: *"This form was updated while you were working on it. Reload the page…"*. Their save is refused rather than silently lost; after reloading they re-enter the unsaved changes.
- Schedule large deploys outside peak reporting hours and tell focal points to save before you deploy.

## Roll back

Open **Versions** and deploy an **archived** version. Answers entered since are carried back, and fields that an earlier deploy archived are restored. The same acknowledgement applies if fields added after that version hold data.

## Discard a draft or delete a version

- **Discard draft** removes the draft and its structure. It never affects the live version.
- **Delete version** is available for non-published versions only. It is **blocked** while any submitted data, repeat instance, uploaded document, AI validation or page status is linked to the version. Archive instead of deleting.
- Versions you delete do not renumber the others. A new draft always takes the next free number.

## Pages

If the template is paginated, a page that already has workflow progress (for example "submitted") **cannot be removed** from the live version. Create a draft, remove the page there and deploy it. Pages with no progress can be removed freely.

## Duplicating a template

**Duplicate** creates an independent template from the live version. Variables that read a field are re-pointed to the copy of that field, so the new template never reads data from the old one.

## Deploy stopped: what the messages mean

| Message | Cause | What to do |
|---|---|---|
| *The selected version was not found for this template.* | Stale page or wrong link | Reload the Form Builder |
| *Cannot deploy this version: N indicator item(s) have missing/invalid indicator references.* | Indicator fields without an indicator | Fix the marked fields |
| *N field(s) in the live version hold submitted data but have no match…* | Removed fields with data | Review the mapping, then acknowledge |
| *Cannot deploy: N field/section identity key(s) are shared by more than one…* | Two fields share an identity | Ask a developer to run the template version audit (see the runbook) |
| *Cannot deploy: N submission row(s) exist on the previous version but no fields could be matched…* | Older template without identity keys | Ask a developer to run the identity key backfill |
| *Cannot delete this version: N data record(s) are linked…* | Data exists on that version | Keep the version archived |
| *Cannot remove page …* | Page has workflow progress | Remove it in a new draft |

## Good practice

- Make **one deploy per reporting change**, and test the draft with a one-country assignment first.
- Review the field mapping page every time you rename or restructure fields.
- Prefer **renaming** a field over deleting and re-adding it, so data follows.
- Avoid changing the **data type** of a field that already holds data. Add a new field instead.
- Do not delete archived versions you might need to roll back to.

## Related

- [Edit a template (Form Builder)](edit-template.md)
- [Form Builder (advanced)](form-builder-advanced.md)
- [Troubleshooting templates and assignments](troubleshooting-templates-and-assignments.md)
