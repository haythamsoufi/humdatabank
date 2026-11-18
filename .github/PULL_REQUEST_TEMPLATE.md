## Summary

<!-- What does this PR change and why? -->

## Scope

- [ ] Backoffice
- [ ] Website
- [ ] MobileApp
- [ ] Docs / tooling only

## Checklist

- [ ] I read relevant notes in [Developer handbook](../docs/DEVELOPER-HANDBOOK.md) / app README (migrations, CSS build, env vars).
- [ ] No secrets or local-only files are included (`.env`, `*.db`, service account JSON, etc.).
- [ ] For Backoffice UI/template changes: Tailwind rebuilt if new classes were added (`npm run build:css` in `Backoffice/`).

## Plugin changes (skip if none under `Backoffice/plugins/` or `Backoffice/app/plugins/`)

- [ ] Read the [plugin contract](../Backoffice/plugins/README.md#plugin-contract-enforced); `python scripts/ci/check_plugin_contract.py` passes locally.
- [ ] Settings page exists at `/admin/plugins/<plugin_id>/settings`, is permission-guarded, and I opened it in the browser.
- [ ] `plugin.json` and `plugin.py` agree on `plugin_id` / `version`; id is in `BUNDLED_PLUGIN_IDS`.
- [ ] Plugin `README.md` and tests are included; no new `EXEMPT` entries.

## Testing

<!-- How was this verified? e.g. manual steps, pytest, `npm run lint` -->

## Screenshots / recordings

<!-- Optional, for UI changes -->
