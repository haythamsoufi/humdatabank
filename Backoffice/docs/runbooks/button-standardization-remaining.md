# Remaining templates – apply full button style

Apply the **same style** we use in entry form, form builder, and updated modals:

1. **Sharp corners** – no `rounded-md` / `rounded-lg` on action buttons.
2. **Color semantics** (from `theme.css`):
   - **Green** (`bg-green-600` / `.btn-confirm`): Submit, Deploy, Confirm, Add, Save (final), Export, Import, Approve, Update.
   - **Blue** (`bg-blue-600`): Preview, View, Edit, Reload, Save draft, Save (translations).
   - **Red** (`bg-red-600` / `.btn-danger-standard`): Delete, Remove, Reject, Decline.
   - **Gray/White** (`.btn-cancel` or `bg-white` + `border-gray-300`): Cancel, Close.
   - **Purple** (`professional-action-btn-purple`): Audit Trail, special view.
   - **Orange** (`professional-action-btn-orange`): Auto-translate, automation.
3. **Standard classes in modals/confirmations**: `.btn-confirm`, `.btn-cancel`, `.btn-danger-standard` so look and sharp corners are consistent.
4. **Page header actions**: `professional-action-btn professional-action-btn-green|blue|red|purple|orange` (no inline rounded; executive-header + theme give sharp corners).

---

## Forms

| Template | Apply full style to |
|----------|---------------------|
| `forms/form_builder/form_builder.html` | `#versions-modal-btn` → gray/secondary style, sharp. |
| `forms/entry_form/entry_form.html` | `#entry-form-loading-reload` → blue, sharp; Excel import submit → green, sharp. |
| `forms/form_builder/partials/_template_details.html` | Save template → `.btn-confirm`; Edit → blue, sharp; Cancel → `.btn-cancel`; `#template-access-btn`, `#add-page-btn` → standard colors + sharp. |
| `forms/form_builder/partials/_item_modal.html` | Small inline buttons: optional; use green/blue/gray + no rounded. |

---

## Admin – partially updated (finish full style)

| Template | Apply full style to |
|----------|---------------------|
| `admin/translations/manage_translations.html` | Submit → green/blue per action; remove rounded; modals → `.btn-confirm` / `.btn-cancel`. |
| `admin/assignments/manage_assignment.html` | `#bulk-enable-public-btn` → blue + sharp. Tab buttons: optional (tabs, not CTAs). |
| `admin/indicator_bank/indicator_bank.html` | Export All/Selected → green, sharp; styled-message Cancel/OK → `.btn-cancel` / `.btn-danger-standard`; Add Sector/Subsector → green or blue + sharp; refresh → green, reset → red, sharp. |
| `admin/documents/documents.html` | JS-built Approve → green, Decline → red; remove rounded; same classes as rest of app. |

---

## Admin – not yet using new style

| Template | Apply full style to |
|----------|---------------------|
| `admin/ai/documents.html` | Upload → blue/green; Refresh → gray/cancel style; Process → purple/orange; Search → blue; Import → green; Bulk Reprocess → blue, Bulk Delete → red; Open Upload → blue. All sharp, no rounded-md. |
| `admin/data_exploration/explore_data.html` | Apply Filters → blue; Clear Filters → gray. Sharp. |
| `admin/api_management.html` | Show Docs → blue; Open URL → green; Copy URL → blue. Sharp. |
| `admin/notifications/center.html` | Clear template → gray. Sharp. |
| `admin/analytics/audit_trail.html` | Submit filter → blue. Sharp. |
| `admin/analytics/security_events.html` | Filter submit → blue; Resolve modal Confirm → green, Cancel → `.btn-cancel`; JS resolve button → green. Sharp. |
| `admin/monitoring/system_monitoring.html` | Refresh → blue/gray; Clear logs → red; Prev/Next → gray. Sharp. |
| `admin/organization/index.html` | Auto-translate → orange (or purple). Sharp. |
| `admin/organization/_nss_component.html` | Add program → blue/green; Auto-translate → orange. Sharp. |
| `admin/user_management/access_requests.html` | JS Approve → green, Reject → red. Sharp. |

---

## Macros / shared

| Template | Apply full style to |
|----------|---------------------|
| `macros/translation_modal.html` | Auto-translate → green; Clear → `.btn-cancel`; tabs: optional. Sharp; match modal style used elsewhere. |

---

## Other areas (apply full style when touching)

Use the same rules: sharp corners, semantic colors, `.btn-confirm` / `.btn-cancel` / `.btn-danger-standard` in modals, and `professional-action-btn-*` for page headers.

- `admin/common_words/manage_common_words.html`
- `admin/resources/edit_resource.html`, `manage_resources.html`
- `admin/settings/manage_settings.html`
- `admin/plugin_management.html`, `plugin_settings.html`
- `admin/templates/templates.html`, `new_template.html`
- `admin/assignments/assignments.html`, `public_submissions.html`, `public_assignments.html`, `gantt_chart.html`
- `admin/lists/list_detail.html`, `manage_lists.html`
- `admin/publications/manage_publications.html`, `edit_publication.html`
- `admin/rbac/grants.html`, `roles.html`, `grant_form.html`, `role_form.html`
- `admin/indicator_bank/edit_indicator_bank.html`, `add_indicator_bank.html`, `sectors_subsectors.html`
- `admin/analytics/` (sessions, login_logs, activity_logs, admin_actions, user_detail, dashboard)
- `admin/view_indicator_suggestion.html`, `indicator_suggestions.html`
- `admin/ai/trace_detail.html`, `reasoning_traces.html`, `dashboard.html`
- `admin/security/dashboard.html`
- `core/dashboard.html`
- `auth/account_settings.html`, `login.html`, `reset_password.html`, etc.
- `components/auto_translate_modal.html`, `thumbnail_upload.html`, `enhanced_search_dropdown.html`, `country_dropdown.html`
- `forms/form_builder/partials/_versions_modal.html`, `_excel_modal.html`, `_question_modal.html`, `_variables_modal.html`
- `forms/entry_form/partials/dynamic_indicator_item.html`, `dynamic_indicators_interface.html`
- `notifications/center.html`, `tours/tours.html`
- `public/landing.html`

---

## Reference: the new style

- **Sharp corners**: No `rounded-md` / `rounded-lg` on action buttons; `theme.css` forces `border-radius: 0` for `button.bg-blue-600`, `button.bg-green-600`, `button.bg-red-600`, `button.bg-white`, `button.bg-gray-*`, `.btn-confirm`, `.btn-cancel`, `.btn-danger-standard`, `.professional-action-btn`.
- **Colors**: See `Backoffice/app/static/css/theme.css` (comment at top).
- **Modal/confirmation buttons**: Prefer `.btn-confirm`, `.btn-cancel`, `.btn-danger-standard` so all modals look the same.
- **Header actions**: `professional-action-btn professional-action-btn-{green|blue|red|purple|orange}` (see form_builder/entry_form page headers).
