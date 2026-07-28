# Template & JS codemods

Bulk refactors for moving inline template JavaScript to static files, button migrations, and similar one-time codebase edits. Most were used during the inline-JS extraction work; kept for reuse if similar migrations are needed.

Run from `Backoffice/`:

```bash
python scripts/codemods/migrate_template_js.py app/templates/...
python scripts/codemods/fix_unsafe_gettext_embedding.py --apply
```

CI guardrails for templates live in `scripts/ci/` (`check_no_inline_js_in_diff.py`, `check_unsafe_gettext_embedding.py`, `gate_template_console_calls.py`).
