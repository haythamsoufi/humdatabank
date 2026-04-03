# Workflow Authoring Guide

This guide documents best practices, considerations, and common pitfalls when creating workflow documentation for the interactive tour system.

## Overview

Workflow documents are structured Markdown files that define step-by-step guides. The chatbot uses these to answer "how to" questions and can trigger interactive tours that spotlight UI elements.

## File Structure

```
docs/workflows/
├── _schema.md              # Schema reference (prefix with _ to exclude from parsing)
├── AUTHORING_GUIDE.md      # This guide
├── admin/                  # Admin-only workflows
│   ├── add-user.md
│   └── manage-users.md
├── focal-point/            # Focal point workflows
│   └── submit-data.md
└── common/                 # Workflows for all roles
    └── navigation.md
```

## Frontmatter Requirements

```yaml
---
id: workflow-id            # Unique, URL-safe identifier (used in tour hash)
title: Workflow Title       # Human-readable title
description: Brief description
roles: [admin, focal_point] # Who can access this workflow
category: category-name     # For grouping (e.g., data-entry, user-management)
keywords: [keyword1, keyword2]  # For search matching
pages:                      # Pages involved in this workflow
  - /page1
  - /page2
---
```

## Step Definition Format

```markdown
### Step N: Step Title
- **Page**: `/path/to/page`
- **Selector**: `#element-id, .fallback-class`
- **Action**: Brief action description
- **Help**: Detailed help text shown in tooltip
- **ActionText**: Button label (default: "Next")
```

---

## Critical Considerations

### 1. Dynamic URL Paths

**Problem**: Routes like `/forms/assignment/123` have dynamic IDs that can't be hardcoded.

**Solution**: Use the base path without the ID. The tour system uses **prefix matching**.

```markdown
# ✅ CORRECT - Use base path
- **Page**: `/forms/assignment`

# ❌ WRONG - Don't include dynamic IDs
- **Page**: `/forms/assignment/123`
```

**How it works**:
- User is on `/forms/assignment/456`
- Step page is `/forms/assignment`
- Tour recognizes this as a match (prefix match)
- Back/forward navigation preserves the full URL with ID

### 2. CSS Selector Best Practices

**Always verify selectors against actual HTML templates.**

```markdown
# ✅ CORRECT - Use IDs when available (most reliable)
- **Selector**: `#section-navigation-sidebar`

# ✅ CORRECT - Provide fallbacks with comma separation
- **Selector**: `button[value="submit"], #fab-submit-btn, button.bg-green-600`

# ❌ WRONG - Made-up class names
- **Selector**: `.assignment-card, .submit-button`
```

**Selector priority**:
1. **IDs** (`#element-id`) - Most reliable
2. **Data attributes** (`[data-action="submit"]`) - Stable across styling changes
3. **Form attributes** (`button[value="submit"]`, `input[name="email"]`)
4. **Semantic classes** (`.section-link`, `.form-item`)
5. **Utility classes** (`.bg-green-600`) - Last resort, may change

### 3. Responsive Design / Hidden Elements

**Problem**: Elements may be hidden on certain screen sizes.

```html
<!-- This button is hidden on XL screens (≥1280px) -->
<button id="fab-submit-btn" class="xl:hidden ...">
```

**Solution**: Provide multiple selectors that work across screen sizes.

```markdown
# ✅ CORRECT - Multiple selectors for responsiveness
- **Selector**: `button[value="submit"], #fab-submit-btn`
```

### 4. Fixed/Absolute Positioned Elements

**Problem**: The tour system calls `scrollIntoView()` which breaks fixed/absolute elements like sidebars.

**Current behavior**: The tour system automatically detects `position: fixed` or `position: absolute` and skips scrolling for these elements.

**Tip**: If an element still moves unexpectedly, check if the spotlight CSS is overriding its position. The `chatbot-spotlight-target` class should NOT set `position: relative`.

### 5. Steps Requiring User Clicks on Specific Elements

**Problem**: Some steps need the user to click a specific element (like an assignment link) rather than a generic "Next" button. The tour can't know dynamic values like assignment IDs.

**Solution**: 
1. Change `ActionText` to guide the user
2. The tour will show a hint if user clicks the button instead of the element

```markdown
# ✅ CORRECT - Clear action text for user-click steps
### Step 2: Open the Data Entry Form
- **Page**: `/`
- **Selector**: `a[href*="/forms/assignment/"]`
- **Help**: Click on the assignment title (highlighted above) to open the form.
- **ActionText**: Click an Assignment
```

When user clicks "Click an Assignment" button instead of the actual link, they'll see: "👆 Click on the highlighted element above to continue"

### 6. Cross-Page Navigation

**How tours continue across pages**:

1. **Link interception**: When a step spotlights a link, clicking it adds the tour hash:
   - User clicks: `/forms/assignment/123`
   - Becomes: `/forms/assignment/123#chatbot-tour=workflow-id&step=3`

2. **Page load detection**: On page load, the tour system checks for the hash and continues

**Requirements for cross-page tours**:
- The spotlighted element must be a clickable link (`<a>` tag)
- The link's destination must match the next step's page (exact or prefix)

### 7. ActionText Guidelines

| Scenario | ActionText |
|----------|------------|
| Move to next step on same page | `Next` |
| User must click highlighted link | `Click [Element Name]` |
| Final step | `Got it` or `Done` |
| First step | `Continue` or `Let's Start` |

---

## Checklist for New Workflows

Before publishing a new workflow, verify:

- [ ] **Frontmatter complete**: All required fields present
- [ ] **Unique ID**: No collision with existing workflow IDs
- [ ] **Role restrictions**: Correct roles specified
- [ ] **Page paths verified**: Routes exist and use base paths for dynamic routes
- [ ] **Selectors tested**: Each selector matches actual HTML elements
- [ ] **Responsive tested**: Selectors work on mobile and desktop
- [ ] **Cross-page steps**: Links are properly intercepted
- [ ] **ActionText appropriate**: Clear guidance for each step type
- [ ] **Help text complete**: Each step has meaningful help text

## Testing Workflows

### Via CLI
```bash
# List all workflows
flask workflows list

# Show specific workflow details
flask workflows show submit-data

# Sync to vector store (for RAG)
flask workflows sync
```

### Via Browser
1. Open chatbot and ask: "How do I [workflow action]?"
2. Click "Start Interactive Tour"
3. Verify each step:
   - Element is highlighted correctly
   - Help text is visible and positioned well
   - Next/Back navigation works
   - Cross-page transitions preserve URLs

### Via API
```
GET /api/ai/documents/workflows
GET /api/ai/documents/workflows/{workflow-id}
GET /api/ai/documents/workflows/{workflow-id}/tour
```

---

## Common Issues & Solutions

### Issue: "Tour not found or has no steps"
**Cause**: Workflow file has parsing errors or step format is incorrect
**Solution**: Check YAML frontmatter syntax and step field format (`- **Field**: value`)

### Issue: Spotlight appears but element is off-screen
**Cause**: `scrollIntoView` on fixed elements
**Solution**: Already handled by tour system; if persists, check element's CSS position

### Issue: Clicking "Next" navigates to 404
**Cause**: Page path includes dynamic ID or route doesn't exist
**Solution**: Use base path (e.g., `/forms/assignment` not `/forms/assignment/123`)

### Issue: Tour doesn't continue after clicking link
**Cause**: Link's destination doesn't match next step's page
**Solution**: Ensure next step's page is a prefix of the link destination

### Issue: Element highlighted but tour tooltip not visible
**Cause**: Z-index conflict or element is in a modal/overlay
**Solution**: The tooltip uses `z-index: 2147480000`; check for higher z-index elements

---

## Template: New Workflow

```markdown
---
id: my-workflow
title: My Workflow Title
description: What this workflow helps users accomplish
roles: [admin, focal_point]
category: category-name
keywords: [keyword1, keyword2, keyword3]
pages:
  - /page1
  - /page2
---

# My Workflow Title

Brief description of what this workflow accomplishes.

## Prerequisites

- Prerequisite 1
- Prerequisite 2

## Steps

### Step 1: First Step Title
- **Page**: `/page1`
- **Selector**: `#element-id`
- **Action**: What the user should do
- **Help**: Detailed explanation shown in the tooltip. Be specific and helpful.
- **ActionText**: Continue

### Step 2: Second Step Title
- **Page**: `/page1`
- **Selector**: `.element-class, #fallback-id`
- **Action**: Next action
- **Help**: More detailed guidance for this step.
- **ActionText**: Next

### Step 3: Final Step
- **Page**: `/page2`
- **Selector**: `button[type="submit"]`
- **Action**: Complete the workflow
- **Help**: Final instructions and what to expect after completion.
- **ActionText**: Got it

## Tips

- Helpful tip 1
- Helpful tip 2

## Related Workflows

- [Related Workflow](related-workflow.md) - Brief description
```
