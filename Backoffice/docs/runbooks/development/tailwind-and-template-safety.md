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

---

## 3. Client console hygiene

Controlled logging via guarded helpers (`CLIENT_CONSOLE_LOGGING` pattern). CI guardrail:

```bash
python Backoffice/scripts/check_no_console_saved_bypass.py
```

Bulk autofix tooling: `python Backoffice/scripts/gate_template_console_calls.py`.

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
