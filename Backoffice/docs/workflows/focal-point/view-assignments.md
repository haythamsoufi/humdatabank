---
id: view-assignments
title: View Your Assignments
description: Guide for focal points to view and manage their pending assignments
roles: [focal_point, admin]
category: data-entry
keywords: [my tasks, pending, deadline, assignments, dashboard, todo]
pages:
  - /
---

# View Your Assignments

This workflow guides focal points through viewing their pending assignments and understanding their tasks.

## Prerequisites

- Focal Point role required
- Assigned to at least one country

## Steps

### Step 1: Access Your Dashboard
- **Page**: `/`
- **Selector**: `.bg-white.p-6.rounded-lg.shadow-md, .grid.gap-4`
- **Action**: View your dashboard
- **Help**: Your dashboard shows all your pending assignments. Each card shows the form name, due date, completion status, and progress percentage.
- **ActionText**: Next

### Step 2: Review Assignment Cards
- **Page**: `/`
- **Selector**: `.p-4.rounded-lg.shadow-md, .bg-gray-50.border`
- **Action**: Review each assignment
- **Help**: Each assignment card shows the template name, period, due date, and current status. Overdue assignments have a red border and "Overdue" badge.
- **ActionText**: Next

### Step 3: Open an Assignment
- **Page**: `/`
- **Selector**: `a[href*="/forms/assignment/"], .p-4.rounded-lg a`
- **Action**: Click to open the form
- **Help**: Click on the assignment title to open the data entry form. You can see completion percentage and status before clicking.
- **ActionText**: Click an Assignment

## Understanding Assignment Status

| Status | Meaning |
|--------|---------|
| **Pending** | Not started yet |
| **In Progress** | Started but not submitted |
| **Submitted** | Completed and submitted |
| **Overdue** | Past deadline, not submitted |

## Tips

- Check your dashboard regularly for new assignments
- Start early to avoid last-minute issues
- Your progress is saved automatically as you work
- You can contact your administrator if you have questions about an assignment
- Use the notifications panel to see recent updates

## Related Workflows

- [Submit Data](submit-data.md) - Complete and submit a form
