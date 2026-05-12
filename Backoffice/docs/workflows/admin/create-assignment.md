---
id: create-assignment
title: Create New Assignment
description: Guide for creating a new form assignment to distribute templates to countries
roles: [admin]
category: assignment-management
keywords: [create assignment, assign form, distribute, task, deadline, country assignment, new assignment]
pages:
  - /admin/assignments
  - /admin/assignments/new
---

# Create New Assignment

This workflow guides administrators through creating a new form assignment to distribute templates to countries and focal points.

## Prerequisites

- Administrator role required
- At least one active form template with a published version
- Countries configured in the system

## Steps

### Step 1: Navigate to Assignment Management
- **Page**: `/admin/assignments`
- **Selector**: `a[href="/admin/assignments/new"], .create-assignment-btn`
- **Action**: Click "Create Assignment"
- **Help**: The Assignments page shows all current and past assignments. Click "Create Assignment" to distribute a form to countries.
- **ActionText**: Continue

### Step 2: Select Template
- **Page**: `/admin/assignments/new`
- **Selector**: `#template-select, select[name="template"]`
- **Action**: Choose the form template to assign
- **Help**: Select which form template you want to distribute. Only active templates with published versions appear in this list.
- **ActionText**: Next

### Step 3: Select Countries
- **Page**: `/admin/assignments/new`
- **Selector**: `#country-select, .country-selection`
- **Action**: Choose countries to receive the assignment
- **Help**: Select one or more countries to receive this assignment. You can select all countries or pick specific ones.
- **ActionText**: Next

### Step 4: Set Period Name
- **Page**: `/admin/assignments/new`
- **Selector**: `#period-name, input[name="period_name"]`
- **Action**: Enter a period name for this assignment
- **Help**: Give this assignment a descriptive period name (e.g., "Q1 2024 Data Collection" or "Annual Report 2024"). This helps identify the assignment later.
- **ActionText**: Next

### Step 5: Set Deadline
- **Page**: `/admin/assignments/new`
- **Selector**: `#deadline-input, input[type="date"], .deadline-picker`
- **Action**: Set the submission deadline
- **Help**: Choose a deadline for data submission. Focal points will see this deadline and receive reminders as it approaches.
- **Fields**:
  - Deadline Date (required): When submissions are due
  - Reminder Settings: Configure automatic reminders

### Step 6: Add Instructions
- **Page**: `/admin/assignments/new`
- **Selector**: `#instructions, textarea[name="instructions"]`
- **Action**: Add assignment-specific instructions
- **Help**: Provide any special instructions or context for this assignment. This message will be shown to focal points.
- **ActionText**: Next

### Step 7: Configure Public URL (Optional)
- **Page**: `/admin/assignments/new`
- **Selector**: `#generate-public-url, input[name="generate_public_url"]`
- **Action**: Enable public URL if needed
- **Help**: If you want to allow public submissions without login, check this option. You can activate or deactivate the public URL later.
- **ActionText**: Next

### Step 8: Review and Create
- **Page**: `/admin/assignments/new`
- **Selector**: `button[type="submit"], .create-btn`
- **Action**: Create the assignment
- **Help**: Review the assignment details and click "Create Assignment". Focal points will be notified and see the new task in their dashboard.
- **ActionText**: Got it

## Tips

- Set realistic deadlines considering time zones and holidays
- Use clear, specific instructions in assignment messages
- Choose a descriptive period name that makes it easy to identify the assignment later
- Only templates with published versions can be assigned
- You can add more countries to an assignment after creation by editing it

## Related Workflows

- [Manage Assignments](manage-assignments.md) - View, edit, and manage existing assignments
- [Create Template](create-template.md) - Design forms before assigning
- [View Assignments](../focal-point/view-assignments.md) - Focal point perspective
