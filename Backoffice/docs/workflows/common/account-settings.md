---
id: account-settings
title: Manage Account Settings
description: Guide for updating your profile, password, and preferences
roles: [admin, focal_point]
category: account
keywords: [profile, password, settings, preferences, change password, update profile]
pages:
  - /account-settings
---

# Manage Account Settings

This workflow guides you through updating your account settings, profile information, and password.

## Prerequisites

- Logged in to the system

## Steps

### Step 1: Navigate to Account Settings
- **Page**: `/account-settings`
- **Selector**: `.bg-white.p-6.rounded-lg.shadow-md`
- **Action**: Access your account settings
- **Help**: This is your account settings page where you can update your personal information, preferences, and password.
- **ActionText**: Next

### Step 2: Update Personal Information
- **Page**: `/account-settings`
- **Selector**: `input[name="name"], input[name="phone"], #profile_color`
- **Action**: Edit your profile details
- **Help**: Update your display name, phone number, and profile color. Your email address cannot be changed - it's your login ID.
- **ActionText**: Next

### Step 3: Configure Preferences
- **Page**: `/account-settings`
- **Selector**: `input[name="chatbot_enabled"], select[name="language"]`
- **Action**: Set your preferences
- **Help**: Enable or disable the AI chatbot assistant, and set your preferred language for the interface.
- **ActionText**: Next

### Step 4: Save Changes
- **Page**: `/account-settings`
- **Selector**: `button[type="submit"]`
- **Action**: Save your settings
- **Help**: Click "Save Changes" to apply your updates. Your settings will be saved immediately.
- **ActionText**: Got it

## Password Requirements

Your password must:
- Be at least 8 characters long
- Contain at least one uppercase letter
- Contain at least one lowercase letter
- Contain at least one number
- Not be a commonly used password

## Tips

- Change your password regularly for security
- Enable email notifications to stay updated on deadlines
- Set your correct timezone to see accurate deadline times
- Keep your contact information up to date

## Related Workflows

- [View Assignments](../focal-point/view-assignments.md) - Check your pending tasks
