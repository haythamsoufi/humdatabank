---
id: manage-assignments
title: Manage Assignments
description: Guide for viewing, editing, and managing existing form assignments
roles: [admin]
category: assignment-management
keywords: [edit assignment, view assignments, monitor progress, extend deadline, delete assignment, assignment status]
pages:
  - /admin/assignments
  - /admin/assignments/edit
---

# Manage Assignments

This workflow guides administrators through viewing, editing, and managing existing form assignments to countries and focal points.

## Prerequisites

- Administrator role required
- At least one existing assignment in the system

## Steps

### Step 1: Navigate to Assignment Management
- **Page**: `/admin/assignments`
- **Selector**: `.assignments-list, [data-testid="assignments-grid"]`
- **Action**: View the list of all assignments
- **Help**: The Assignments page shows all current and past assignments. You can see each assignment's period name, template, submission status, and public URL status.
- **ActionText**: Next

### Step 2: View Assignment Details
- **Page**: `/admin/assignments`
- **Selector**: `.assignment-row, [data-assignment-id]`
- **Action**: Review assignment information
- **Help**: Each assignment row shows the period name, template name, and submission progress. Use this to identify which assignments need attention.
- **ActionText**: Next

### Step 3: Monitor Submission Progress
- **Page**: `/admin/assignments`
- **Selector**: `.progress-indicator, .submission-status`
- **Action**: Check completion status
- **Help**: View which countries have submitted, which are in progress, and which are overdue. This helps you identify where follow-up is needed.
- **ActionText**: Next

## Editing an Assignment

### Step 1: Open Edit Form
- **Page**: `/admin/assignments`
- **Selector**: `a[href*="/admin/assignments/edit"], .edit-assignment-btn`
- **Action**: Click the edit icon next to the assignment
- **Help**: Click the edit icon (pencil) next to the assignment you want to modify. This opens the assignment edit form.
- **ActionText**: Continue

### Step 2: Update Assignment Details
- **Page**: `/admin/assignments/edit/<assignment_id>`
- **Selector**: `#assignment-details-panel, form`
- **Action**: Modify assignment information
- **Help**: You can update the template, period name, and deadline. Changes to the deadline will apply to all countries in the assignment.
- **Fields**:
  - Template: Change the form template (if needed)
  - Period Name: Update the assignment name
  - Deadline: Extend or modify the submission deadline

### Step 3: Add Countries to Assignment
- **Page**: `/admin/assignments/edit/<assignment_id>`
- **Selector**: `.add-countries-section, #add-countries-btn`
- **Action**: Add additional countries
- **Help**: If you need to add more countries to an existing assignment, use the "Add Countries" section. Select countries and click "Add" to include them.
- **ActionText**: Next

### Step 4: Save Changes
- **Page**: `/admin/assignments/edit/<assignment_id>`
- **Selector**: `button[type="submit"], .save-btn`
- **Action**: Click Save Changes
- **Help**: Click "Save Changes" to apply your updates. Focal points will be notified if new countries are added.
- **ActionText**: Got it

## Managing Public URLs

### View Public URL Status
- **Page**: `/admin/assignments`
- **Selector**: `.public-url-status, [data-public-url]`
- **Action**: Check if assignment has public URL
- **Help**: The assignments list shows whether each assignment has a public URL enabled. Public URLs allow submissions without login.

### Generate Public URL
- **Page**: `/admin/assignments`
- **Selector**: `.generate-public-url-btn, [data-action="generate-url"]`
- **Action**: Click "Generate Public URL"
- **Help**: If an assignment doesn't have a public URL, you can generate one. This allows public submissions without requiring login.

### Toggle Public URL Status
- **Page**: `/admin/assignments`
- **Selector**: `.toggle-public-url, [data-action="toggle-public"]`
- **Action**: Activate or deactivate public URL
- **Help**: Toggle the public URL on or off. When active, the public URL is accessible. When inactive, submissions are disabled.

### Copy Public URL
- **Page**: `/admin/assignments`
- **Selector**: `.copy-url-btn, [data-action="copy-url"]`
- **Action**: Click to copy URL
- **Help**: Copy the public URL to share with external users who need to submit data without logging in.

## Viewing Public Submissions

### View All Public Submissions
- **Page**: `/admin/assignments`
- **Selector**: `a[href="/admin/assignments/public-submissions"], .view-public-submissions-btn`
- **Action**: Click "View All Public Submissions"
- **Help**: See all public submissions across all assignments. This helps you monitor external submissions.

### View Assignment-Specific Submissions
- **Page**: `/admin/assignments`
- **Selector**: `.view-submissions-btn, [data-action="view-submissions"]`
- **Action**: Click "View Submissions" for a specific assignment
- **Help**: View and manage public submissions for a specific assignment. You can approve, reject, or review submissions.

## Deleting an Assignment

### Step 1: Confirm Deletion
- **Page**: `/admin/assignments`
- **Selector**: `.delete-assignment-btn, [data-action="delete"]`
- **Action**: Click the delete icon
- **Help**: Click the delete icon (trash) next to the assignment you want to remove. You'll be asked to confirm.

### Step 2: Confirm Deletion
- **Page**: `/admin/assignments`
- **Selector**: `.confirm-delete-btn, [data-confirm="delete"]`
- **Action**: Confirm deletion
- **Help**: Confirm that you want to delete the assignment. This will remove the assignment and all associated country statuses and data. This action cannot be undone.
- **ActionText**: Got it

## Timeline View

### Access Gantt Chart
- **Page**: `/admin/assignments`
- **Selector**: `a[href="/admin/assignments/gantt"], .timeline-view-btn`
- **Action**: Click "Timeline View"
- **Help**: View all assignments on a timeline/Gantt chart. This helps visualize deadlines and overlapping assignments.

## Tips

- Monitor the dashboard regularly for overdue submissions
- Use the timeline view to avoid scheduling conflicts
- Extend deadlines proactively if many countries are struggling
- Public URLs are useful for external data collection but require monitoring
- Review public submissions regularly to ensure data quality
- Consider sending reminders before deadlines approach

## Related Workflows

- [Create New Assignment](create-assignment.md) - Create a new assignment
- [Create Template](create-template.md) - Design forms before assigning
- [View Assignments](../focal-point/view-assignments.md) - Focal point perspective
