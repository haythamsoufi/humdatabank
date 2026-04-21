# Workflows (interactive tours)

Workflow documents define step-by-step guides that the in-app AI chatbot can use to answer “how do I…?” questions and to run **interactive tours** that highlight UI elements.

## For users

In the Backoffice, open the chatbot and ask e.g. “How do I add a user?” or “How do I submit a form?”. When a workflow matches, you can start an interactive tour that walks you through the steps on the actual pages.

## For authors

- **[Authoring guide](AUTHORING_GUIDE.md)** – How to write workflow Markdown (frontmatter, steps, selectors), test via CLI/browser, and common pitfalls.

## Workflows by role

### Admin

- [Add a user](admin/add-user.md)
- [Manage users](admin/manage-users.md)
- [Create template](admin/create-template.md)
- [Create assignment](admin/create-assignment.md)
- [Manage assignments](admin/manage-assignments.md)
- [Admin action risk levels](admin/admin-action-risk-levels.md)

### Focal point

- [View assignments](focal-point/view-assignments.md)
- [Submit data](focal-point/submit-data.md)

### Common

- [Account settings](common/account-settings.md)
- [Navigation](common/navigation.md)

## Technical note

Workflows are parsed and can be synced to the vector store for RAG. See the authoring guide for `flask workflows list` / `flask workflows sync` and API endpoints.
