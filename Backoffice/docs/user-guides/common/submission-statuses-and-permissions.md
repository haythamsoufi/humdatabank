# Submission statuses and what you can do (permissions guide)

Use this guide to understand why a button is missing/disabled (for example **Edit**, **Submit**, **Approve**, or **Reopen**).

## Two things control what you can do

1. **Your role(s)** (permissions)
2. **The current status** of the assignment/submission

If either one does not allow an action, you will not see it (or it will be disabled).

## Common roles (plain language)

- **Focal point (data entry)**: can enter data and submit (typically `assignment_editor_submitter`)
- **Approver**: can approve and reopen (typically `assignment_approver`)
- **Admin**: can manage users/templates/assignments (varies by admin roles)

## Common statuses (what they usually mean)

Status names can vary slightly by workflow, but they typically map to:

- **Not started**: no saved answers yet (or user has not opened it)
- **In progress / Draft**: some answers are saved, not submitted
- **Submitted**: sent for review (editing may be locked)
- **Approved**: accepted/finalized (editing usually locked)
- **Reopened / Returned**: sent back for correction (editing allowed again)
- **Closed / Archived** (if used): collection period ended; changes may be blocked

## What you can do (quick matrix)

This table shows the *typical* behavior.

| Status | Focal point (data entry) | Approver | Admin (assignment management) |
|---|---|---|---|
| Not started | Edit | View | View / Manage |
| In progress / Draft | Edit / Submit | View | View / Manage |
| Submitted | View (edit usually locked) | Approve / Reopen | View / Manage |
| Approved | View | View (may still reopen) | View / Manage |
| Reopened / Returned | Edit / Re-submit | View / Approve | View / Manage |

Notes:
- If you cannot **see** an assignment at all, it is usually a **country access** or **role** issue.
- Some setups allow admins/approvers to edit after submission; others do not.

## When buttons are missing (common causes)

### “Submit” is missing or disabled

Likely causes:
- A required field is missing
- Validation messages exist
- The assignment is already submitted/approved and is locked

What to do:
- Fix required/validation messages and try again
- If it is locked, ask an approver/admin to **Reopen** (if your workflow supports it)

### “Approve” is missing

Likely causes:
- You do not have the approver role (`assignment_approver`)
- The submission is not in a “Submitted” state yet

### “Reopen” is missing

Likely causes:
- The workflow does not allow reopening, or only certain roles can reopen
- The submission is already in progress (not submitted)

### “Edit” is missing

Likely causes:
- You only have a viewer role
- The status is submitted/approved and editing is locked

## If you’re still stuck

- [Troubleshooting (Focal point)](../focal-point/troubleshooting.md)
- [Getting help](getting-help.md)
- Ask your administrator if the issue is about access, roles, or workflow configuration.
