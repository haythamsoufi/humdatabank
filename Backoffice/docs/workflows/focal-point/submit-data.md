---
id: submit-data
title: Submit Form Data
description: Guide for focal points to fill out and submit form data
roles: [focal_point, admin]
category: data-entry
keywords: [fill form, enter data, submit, complete assignment, data entry]
pages:
  - /
  - /forms/assignment
---

# Submit Form Data

This workflow guides focal points through filling out and submitting form data for their assignments.

## Prerequisites

- Focal Point role required
- An active assignment for your country
- Data ready to enter

## Steps

### Step 1: Find Your Assignment on Dashboard
- **Page**: `/`
- **Selector**: `.bg-white.p-6.rounded-lg.shadow-md, .grid.gap-4`
- **Action**: Locate your assigned form
- **Help**: Your dashboard shows all forms assigned to you. Look for forms with status "In Progress" or "Not Started". Click on a form to begin entering data.
- **ActionText**: Continue

### Step 2: Open the Data Entry Form
- **Page**: `/`
- **Selector**: `a[href*="/forms/assignment/"], a[href*="view_edit_form"], .p-4.rounded-lg.shadow-md a`
- **Action**: Click to open the form
- **Help**: Click on the assignment title (highlighted above) to open the data entry form. The tour will continue on the form page.
- **ActionText**: Click an Assignment

### Step 3: Navigate Form Sections
- **Page**: `/forms/assignment`
- **Selector**: `#section-navigation-sidebar, .section-link`
- **Action**: View available sections
- **Help**: The form is organized into sections shown in the left sidebar. Click a section name to jump to it. Each section shows a completion indicator.
- **ActionText**: Next

### Step 4: Fill in Required Fields
- **Page**: `/forms/assignment`
- **Selector**: `#main-form-area, #sections-container`
- **Action**: Enter your data
- **Help**: Fill in each field with the appropriate data. Required fields are marked with an asterisk (*). Your changes are auto-saved as you work.
- **ActionText**: Next

### Step 5: Submit the Form
- **Page**: `/forms/assignment`
- **Selector**: `button[value="submit"], #fab-submit-btn, button.bg-green-600`
- **Action**: Click Submit
- **Help**: Once all required fields are complete, click the green Submit button to finalize your data. On mobile, use the floating action button. You'll receive a confirmation message.
- **ActionText**: Got it

## Saving Your Progress

- Your data is automatically saved as you work
- You can leave and return at any time
- Look for the "Last saved" indicator to confirm saves
- Use "Save Draft" to explicitly save your current progress

## Tips

- Gather all your data before starting to avoid interruptions
- Use the comment fields to document data sources
- Check validation messages carefully before submitting
- You can edit submitted data if allowed by your administrator
- Export your submission as PDF for your records

## Related Workflows

- [View Assignments](view-assignments.md) - See all your pending tasks
