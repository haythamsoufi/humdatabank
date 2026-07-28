# Tailwind, static CSS, and template safety

Engineering checklist for UI changes touching Jinja templates, inline scripts, or Tailwind utilities in Backoffice.

---

## 1. Rebuild Tailwind CSS

Backoffice bundles Tailwind into `app/static/css/output.css`:

```bash
cd Backoffice
npm install
npm run build:css
# or continuous: npm run watch:css
```

If new utility classes appear “missing”, the bundle is stale — **refresh alone will not fix it**.

Semantic button variables live in `app/static/css/theme.css` and `components.css`; page-header actions use `executive-header.css`. Tailwind maps palette scales to those variables via `assets/tailwind.config.js`.

---

## 2. Content Security Policy and inline scripts

Inline `<script>` blocks require **`nonce="{{ csp_nonce() }}"`**. Larger logic belongs in externals under `app/static/js/`.

### Translated strings in inline JS and attributes

Flask-Babel/`{{ _(...) }}` output is Markup-safe and is **not** HTML-escaped inside `<script>` or attribute values. Apostrophes in French (and other locales) will break quoted JS literals if you embed translations raw.

| Context | Safe pattern |
|---------|----------------|
| Inline JS value | `{{ _('Label')|tojson|safe }}` or `{{ _('Label')|js }}` |
| JS string built from parts | `'<i></i>' + {{ _('Label')|tojson|safe }} + ' suffix'` |
| HTML attribute (`data-*`, `title`, `aria-*`, …) | `{{ _('Label')|forceescape }}` |

CI guardrail (diff + full template scan):

```bash
python Backoffice/scripts/ci/check_unsafe_gettext_embedding.py --all-templates
```

Batch fix existing templates:

```bash
python Backoffice/scripts/codemods/fix_unsafe_gettext_embedding.py --apply
```

See also `docs/DEVELOPER-HANDBOOK.md` (Template Safety Checklist).

---

## 3. Client console hygiene

Controlled logging via guarded helpers (`CLIENT_CONSOLE_LOGGING` pattern). CI guardrail:

```bash
python Backoffice/scripts/ci/check_no_console_saved_bypass.py
```

Bulk autofix tooling: `python Backoffice/scripts/ci/gate_template_console_calls.py`.

---

## 4. Dynamic HTML sanitization

Global helpers live in **`app/static/js/lib/safe-dom.js`** (`SafeDom.*`). **`sanitizeHtml`** / **`window.sanitizeHtml`** are wired from **`core/layout.html`**.

### What `sanitizeHtml` does

It strips **`script`, `iframe`, `object`, `embed`, `form`, `input`, `button`, `textarea`, `link`, `style`, `base`, `meta`**; removes **`on*`** event attributes and **`style`** attributes; blocks **`javascript:` / `vbscript:` / `data:`** on `href` / `src` / `action`.

Immersive chat / markdown pipelines may use a dedicated sanitizer — **do not** introduce another repo-wide HTML sanitizer for generic partials.

### When to use what

| Situation | Use |
|-----------|-----|
| Assign `innerHTML` with fetched HTML partial (AJAX `.text()` then DOM) | `SafeDom.sanitizeHtml(html)` or `window.sanitizeHtml(html)` |
| Building markup from dynamic strings (names, labels, values) | `escapeHtml` / `escapeHtmlAttr`, or DOM (`createElement`, `textContent`) |
| Clearing or inserting **static** literals | `innerHTML = ''` or fixed literals — no sanitizer needed |

Prefer DOM APIs over `innerHTML` when feasible.

---

## 5. Button design system (Backoffice)

Three layers — keep them aligned:

1. **CSS variables** — `app/static/css/theme.css` (`:root` semantics).
2. **Body / form / modal** — `.btn` + variants in `app/static/css/components.css`.
3. **Page header actions only** — `.professional-action-btn*` in `app/static/css/executive-header.css`.

Tailwind palette remap → semantic colours: `assets/tailwind.config.js`. After changing templates or Tailwind classes run **`npm run build:css`** (see §1).

**Colour semantics (mandatory for new buttons):**

| Colour | Class | Use for |
|--------|-------|---------|
| Teal (primary) | `btn-primary` / `professional-action-btn-blue` | Preview, Edit, Save draft, Open, Reload — navigate without committing |
| Green (success) | `btn-success` / `professional-action-btn-green` | Submit, Confirm, Add, Approve, Export, Import — commits |
| Red (danger) | `btn-danger` / `professional-action-btn-red` | Delete, Remove, Reject |
| Gray (secondary) | `btn-secondary` | Cancel, Close, Back |
| Orange (warning) | `btn-warning` / `professional-action-btn-orange` | Auto-translate, caution automation |
| Purple | `btn-purple` / `professional-action-btn-purple` | Audit Trail, analytics, special views |
| Slate | `btn-dark` / `professional-action-btn` (default) | Generic header actions |

Keep adjacent header actions visually distinct. **Sharp corners:** do not add `rounded-*` on system buttons (theme enforces this); **`rounded-full`** only for FAB / circular icon buttons.

Markup examples:

```html
<button class="btn btn-primary">Edit</button>
<button class="btn btn-success">Save</button>
<button class="professional-action-btn professional-action-btn-green">Export</button>
```

Backward-compatible aliases (prefer `.btn` for new code): `.btn-confirm` → success, `.btn-cancel` → secondary, `.btn-danger-standard` → danger.

---

## 6. Edge debugging

Azure CDN / IndexedDB oddities when forms cache locally: **`app/static/docs/AZURE_INDEXEDDB_DEBUGGING.md`**.

---

## 7. View-only entry form (`can_edit=false`) — checklist & TODOs

Assignment pages where the focal point (or other non-editor) can **view** but not **edit** omit the POST `<form id="focalDataEntryForm">`. Client modules that need assignment context must not assume that form exists.

**Already mitigated (2026-07):** matrix variable lookups / auto-load — `#entry-form-js-context` hidden block + `metadataContext.template_id`; static matrices call `resolveVariablesForAllRows()` on init. See `entry_form.html` near the `can_edit` form wrapper.

### Manual regression checks

When changing entry form templates or `app/static/js/forms/**`, verify as a **focal point on a closed or approved assignment** (no save/submit UI):

- [ ] Matrix variable columns populate (not empty cells)
- [ ] Matrix list-library rows restore from saved data
- [ ] Calculated-list dropdowns load options
- [ ] Section/item relevance (conditions) evaluates correctly, including plugin-backed fields once `data-plugin-data-ready`
- [ ] PDF export (if enabled) renders sections from read-only DOM
- [ ] Excel export (if enabled) still resolves assignment id
- [ ] Pagination and layout still apply across sections
- [ ] No auth-draft restore prompt overwriting server data on read-only pages

Also spot-check **system manager on the same assignment** — behaviour should match except edit controls appear.

### Engineering TODOs (preventive)

- [ ] **Unified wrapper:** always render `#focalDataEntryForm` — `<form method="POST">` when `can_edit`, `<div data-read-only="true">` when not — so layout, PDF export, conditions, and pagination share one root without enabling submission
- [ ] **Shared JS context helpers:** extract `getTemplateId()` / `getAssignmentEntityStatusId()` into `form-item-utils.js` (read `#entry-form-js-context`, `metadataContext`, URL, hidden inputs); use from matrix-handler and any future API callers
- [ ] **Matrix auto-load:** `matrix-handler.js` `autoLoadEntities()` should call `getAssignmentEntityStatusId()` instead of a raw `querySelector('input[name="assignment_entity_status_id"]')`
- [ ] **Audit `form#focalDataEntryForm` selectors:** `dynamic-indicators.js`, `repeat-sections.js` use `querySelector('form#…')` — confirm read-only paths are gated in templates or widen selectors to `#focalDataEntryForm`
- [ ] **Auth drafts:** keep init disabled on read-only (no accidental local draft restore); document in code comment if wrapper change re-enables `#focalDataEntryForm` as a div
- [ ] **Automated test:** render assignment entry page with `can_edit=False` and assert `#entry-form-js-context` + `metadataContext.template_id` present; optional JS unit test for context helper fallbacks

### Intentionally read-only (not bugs)

Do not “fix” these for view-only users: save/submit/FAB, document upload, matrix add-row UI, dynamic indicator add/remove, Excel import, co-editing presence banner.
