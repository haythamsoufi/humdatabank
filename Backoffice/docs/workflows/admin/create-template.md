---
id: create-template
title: Create Form Template
description: Guide for creating a new form template with sections and fields
roles: [admin]
category: template-management
keywords: [new template, form builder, create form, design form, build template]
pages:
  - /admin/templates
  - /admin/templates/new
---

# Create Form Template

This workflow guides administrators through creating a new form template using the form builder.

## Prerequisites

- Administrator role required
- Access to Form & Data Management section
- Understanding of the data you want to collect

## Steps

### Step 1: Navigate to Template Management
- **Page**: `/admin/templates`
- **Selector**: `a[href="/admin/templates/new"], .create-template-btn`
- **Action**: Click "Create Template"
- **Help**: Click the "Create Template" button to start building a new form template.
- **ActionText**: Continue

### Step 2: Set Template Details
- **Page**: `/admin/templates/new`
- **Selector**: `#template-details, .template-info-panel`
- **Action**: Enter template name and description
- **Help**: Give your template a clear, descriptive name and add a description explaining its purpose. This helps users understand what the form is for.
- **Fields**:
  - Template Name (required): Clear, descriptive name
  - Description: Explain the template's purpose
  - Template Access: Choose who can view/edit this template (owner and shared admins)

### Step 3: Add Sections
- **Page**: `/admin/templates/new`
- **Selector**: `.add-section-btn, [data-action="add-section"]`
- **Action**: Click "Add Section"
- **Help**: Sections organize your form into logical groups. Add a section for each topic or category of questions.
- **ActionText**: Next

### Step 4: Configure Section
- **Page**: `/admin/templates/new`
- **Selector**: `.section-config, .section-panel`
- **Action**: Name the section and configure settings
- **Help**: Give each section a title and optional description. You can also set visibility conditions and permissions.
- **Fields**:
  - Section Title (required): Name for this section
  - Description: Optional instructions for users
  - Collapsible: Whether users can collapse the section

### Step 5: Add Form Items
- **Page**: `/admin/templates/new`
- **Selector**: `.add-item-btn, [data-action="add-item"]`
- **Action**: Add fields to the section
- **Help**: Add form items like text fields, numbers, dropdowns, and more. Link items to indicators from the Indicator Bank for standardized data collection.
- **ActionText**: Next

### Step 6: Configure Form Items
- **Page**: `/admin/templates/new`
- **Selector**: `.item-config, .form-item-panel`
- **Action**: Configure each form item
- **Help**: Set the label, field type, validation rules, and link to an indicator if applicable. Required fields must be filled by users.
- **Fields**:
  - Label (required): Question or field label
  - Field Type: Text, Number, Date, Dropdown, etc.
  - Required: Whether this field must be filled
  - Indicator: Link to Indicator Bank for standardization

### Step 7: Preview and Save
- **Page**: `/admin/templates/new`
- **Selector**: `button[type="submit"], .save-template-btn`
- **Action**: Save the template
- **Help**: Review your template structure in the preview, then click "Save Template" to create it. You can edit the template later if needed.
- **ActionText**: Got it

## Tips

- Use the Indicator Bank to link fields to standardized indicators
- Group related questions into sections for better organization
- Add descriptions to help users understand what to enter
- Test the template by creating a test assignment before deploying
- Templates can be duplicated to create variations

## Related Workflows

- [Manage Assignments](manage-assignments.md) - Assign templates to countries
