# Workflow Documentation Schema

This document defines the standard format for workflow documentation files used by the chatbot to generate interactive tours.

## Overview

Workflow documents are structured markdown files that describe step-by-step processes in the system. The chatbot uses these documents to:

1. Answer "how to" questions from users
2. Generate interactive tours that guide users through the UI
3. Provide role-appropriate help based on user permissions

## File Location

Workflow documents are organized by role in the `docs/workflows/` directory:

```
docs/workflows/
  _schema.md              # This file
  admin/                  # Admin-only workflows
  focal-point/            # Focal point workflows
  common/                 # Workflows for all authenticated users
```

## Multi-Language Support

Workflow documents can be translated into multiple languages. The system supports:

- **English (en)** - Default language, stored in the main file
- **French (fr)** - French translation
- **Spanish (es)** - Spanish translation
- **Arabic (ar)** - Arabic translation (RTL supported)

### Translation File Naming

Translation files use the pattern: `{workflow-id}.{lang}.md`

```
docs/workflows/
  admin/
    add-user.md          # English (default)
    add-user.fr.md       # French translation
    add-user.ar.md       # Arabic translation
    add-user.es.md       # Spanish translation
```

### Translation File Structure

Translation files have the **same structure** as the English original. All text content should be translated:

- Frontmatter: `title`, `description`, `keywords`
- Body: Step titles, `Help` text, `Action` descriptions, Tips
- Keep unchanged: `id`, `roles`, `category`, `pages`, `Selector`, `Page`

### Translation Example

French translation (`add-user.fr.md`):

```yaml
---
id: add-user
title: Ajouter un Nouvel Utilisateur
description: Guide pour créer un nouveau compte utilisateur
roles: [admin]
category: user-management
keywords: [créer utilisateur, nouveau compte, inscription]
pages:
  - /admin/users
  - /admin/users/new
---
```

### Fallback Behavior

If a translation is not available for the user's preferred language, the system falls back to English.

## Document Structure

### Frontmatter (Required)

Each workflow document must begin with YAML frontmatter:

```yaml
---
id: unique-workflow-id
title: Human-Readable Title
description: Brief description of the workflow
roles: [admin]                    # Required roles: admin, focal_point, or both
category: category-name           # Category for grouping: user-management, data-entry, etc.
keywords: [keyword1, keyword2]    # Optional: additional search terms
pages:                            # List of pages involved in the workflow
  - /admin/users
  - /admin/users/new
---
```

### Frontmatter Fields

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `id` | Yes | string | Unique identifier (lowercase, hyphenated) |
| `title` | Yes | string | Human-readable title |
| `description` | Yes | string | Brief workflow description |
| `roles` | Yes | array | Required roles: `admin`, `focal_point` |
| `category` | Yes | string | Workflow category |
| `keywords` | No | array | Additional search terms |
| `pages` | Yes | array | URL paths involved |

### Document Body

The document body follows this structure:

```markdown
# Workflow Title

Brief introduction explaining what this workflow accomplishes.

## Prerequisites

List any requirements before starting:
- Required permissions
- Required data
- Other completed workflows

## Steps

### Step 1: Step Title
- **Page**: `/path/to/page`
- **Selector**: `CSS selector for element to highlight`
- **Action**: Brief description of what to do
- **Help**: Detailed help text shown in the tour tooltip

### Step 2: Step Title
...

## Tips

Optional section with additional tips and best practices.

## Related Workflows

Optional section linking to related workflows.
```

## Step Format

Each step in the `## Steps` section must include:

### Required Fields

| Field | Description | Example |
|-------|-------------|---------|
| **Page** | URL path where this step occurs | `/admin/users/new` |
| **Selector** | CSS selector for the UI element | `#user-details-panel` |
| **Help** | Tooltip text shown during tour | `Enter the user's email address...` |

### Optional Fields

| Field | Description | Example |
|-------|-------------|---------|
| **Action** | Brief action description | `Click the Save button` |
| **ActionText** | Button text in tooltip | `Continue`, `Next`, `Got it` |
| **Fields** | List of form fields (for forms) | See below |

### Selector Guidelines

Use specific, stable selectors that won't break with minor UI changes:

```markdown
<!-- Good selectors -->
- **Selector**: `a[href="/admin/users/new"]`
- **Selector**: `#user-details-panel`
- **Selector**: `form button[type="submit"]`
- **Selector**: `[data-testid="save-button"]`

<!-- Avoid -->
- **Selector**: `.btn.btn-primary` (too generic)
- **Selector**: `div > div > button` (fragile)
```

### Form Fields

For steps involving forms, document the fields:

```markdown
- **Fields**:
  - Email (required): User's email address, used for login
  - Name (required): User's full name
  - Role (required): Select Administrator or Focal Point
  - Password (required): Initial password (min 8 characters)
```

## Complete Example

```markdown
---
id: add-user
title: Add New User
description: Guide for creating a new user account in the system
roles: [admin]
category: user-management
keywords: [create user, new account, register, staff]
pages:
  - /admin/users
  - /admin/users/new
---

# Add New User

This workflow guides administrators through creating a new user account.

## Prerequisites

- Administrator role required
- Access to User Management section

## Steps

### Step 1: Navigate to User Management
- **Page**: `/admin/users`
- **Selector**: `a[href="/admin/users/new"]`
- **Action**: Click "Add New User" button
- **Help**: Click the "Add New User" button in the top-right corner to start creating a new user account.
- **ActionText**: Continue

### Step 2: Fill User Details
- **Page**: `/admin/users/new`
- **Selector**: `#user-details-panel`
- **Action**: Fill in the form fields
- **Help**: Enter the user's email, name, role, and set an initial password. All fields marked with * are required.
- **Fields**:
  - Email (required): User's email address, used for login
  - Name (required): User's full name
  - Role (required): Administrator or Focal Point
  - Password (required): Initial password

### Step 3: Configure Permissions
- **Page**: `/admin/users/new`
- **Selector**: `#entity-permissions-tab`
- **Action**: Click the Entity Permissions tab
- **Help**: Assign countries or organizational entities to the user. Focal Points must have at least one country assigned.
- **ActionText**: Next

### Step 4: Save User
- **Page**: `/admin/users/new`
- **Selector**: `form button[type="submit"]`
- **Action**: Click Save
- **Help**: Review all information and click "Create User" to complete. The user will receive an email with login credentials.
- **ActionText**: Got it

## Tips

- Users will receive an email with login credentials automatically
- Focal Points must be assigned at least one country to access data
- Administrators have full access to all countries and features
- Initial passwords should be changed on first login

## Related Workflows

- [Manage Users](manage-users.md) - Edit and deactivate existing users
- [Reset Password](reset-password.md) - Reset a user's password
```

## Categories

Use these standard categories for consistency:

| Category | Description |
|----------|-------------|
| `user-management` | User accounts, roles, permissions |
| `template-management` | Form templates and structure |
| `assignment-management` | Creating and managing assignments |
| `data-entry` | Filling out and submitting forms |
| `data-viewing` | Viewing submitted data and reports |
| `indicator-management` | Indicator bank and definitions |
| `country-management` | Country configuration |
| `system-settings` | System configuration |
| `account` | Personal account settings |
| `navigation` | General navigation help |

## Processing Notes

The workflow documentation service (`WorkflowDocsService`) processes these files to:

1. **Extract metadata** from frontmatter for filtering and indexing
2. **Parse steps** into structured tour configurations
3. **Generate embeddings** for semantic search via the RAG system
4. **Build tour configs** compatible with `InteractiveTour.js`

The LLM uses these documents to generate contextual responses that include:
- Summary of the workflow
- Step-by-step instructions
- Option to start an interactive tour
