# Release Process

End-to-end checklist for safely releasing a code change to staging and production. Follow in order for every non-trivial change.

---

## 1. Branching Convention

```
main              ← production-ready
  └── staging     ← mirrors staging environment (optional; some teams deploy main → staging directly)
       └── feature/<short-description>   ← development branches
       └── fix/<short-description>       ← bug fix branches
       └── hotfix/<short-description>    ← emergency production fixes
```

- **Never commit directly to `main`** — always branch + PR.
- Branch names use kebab-case: `feature/add-country-filter`, `fix/waf-payload-size`.
- Keep branches short-lived; merge and delete within the same sprint where possible.

---

## 2. Pre-Release Checklist (Before Merging to Main)

### Code checks

```bash
# In Backoffice/ — confirm migration heads before writing any new migration
python -m flask db heads
# Must be exactly ONE head

# If adding a migration:
python -m flask db migrate -m "descriptive message"
python -m flask db heads   # confirm still ONE head after generating

# CI script — check templates do not bypass console logging guard
python Backoffice/scripts/check_no_console_saved_bypass.py
```

### CSS rebuild (always do this if templates changed)

```bash
cd Backoffice
npm run build:css
# Commit the updated app/static/css/output.css along with your template changes
```

> Missing this step is the most common cause of "classes are there but styles don't apply" bugs in production.

### Local smoke test

1. Start the app locally: `python run.py` in `Backoffice/`.
2. Login as System Manager.
3. Load at least one form and one admin page touched by your change.
4. Check browser console for CSP errors or JS exceptions.
5. If AI features changed: hit `GET /api/ai/v2/health` and send a test message.

---

## 3. Staging Deployment

1. Merge feature branch → staging (or main, depending on your workflow).
2. Azure App Service will deploy automatically if CI/CD is configured (see `deployment/azure-app-service.md`).
3. If deploying manually:
   ```bash
   # On the server or via az CLI
   python -m flask db upgrade
   # Then restart the web app / swap slot
   ```
4. **Staging smoke test:**
   - Anonymous: `GET /` (or your configured health landing route) → HTTP 200.
   - Authenticated: login as a focal point + load a form.
   - Admin: load the assignment management page.
   - AI: `GET /api/ai/v2/health` → `status: ok`.

---

## 4. Production Deployment

### Go / no-go criteria

| Check | Expected |
|-------|---------|
| Staging tests passing | All smoke tests green |
| Single migration head | `flask db heads` → 1 head |
| CSS rebuilt and committed | `output.css` matches templates |
| No open incident | No active production incident |
| Change window agreed | Team notified if downtime expected |

### Deploy sequence

```
1. Take DB snapshot (mandatory before any migration)
2. Deploy new code to staging slot
3. Run: python -m flask db upgrade  (on production DB)
4. Swap slots (staging → production)
5. Verify: smoke tests on production
6. Monitor: az webapp log tail ... for 10+ minutes post-swap
```

### Slot swap (Azure App Service)

```bash
az webapp deployment slot swap \
  --name <webapp-name> \
  --resource-group <rg-name> \
  --slot staging \
  --target-slot production
```

After swap, check **sticky settings** — `DATABASE_URL`, `SECRET_KEY`, `REDIS_URL`, `OPENAI_API_KEY` and other provider keys must be configured as **slot settings** (not swapped with slot) if they differ between slots.

---

## 5. Post-Deploy Verification

Run immediately after every production deploy:

```bash
# 1. Confirm migration applied
python -m flask db current
# Should match the latest revision in migrations/versions/

# 2. Confirm single head
python -m flask db heads

# 3. Tail logs for errors
az webapp log tail --name <webapp-name> --resource-group <rg-name>
```

Look for on startup:
- `WARNING ... unguarded admin route` → a new admin route was added without RBAC guard. Fix before next deploy.
- `ERROR ... migration` → migration failed; DB may be in a partial state — do not continue.

In browser:
- Open one admin page and one form page; confirm no JS console errors.
- Check any feature specifically changed in this release.

---

## 6. Rollback

### Safe rollback (within same migration revision)

If the new code has a bug but no schema change:
```bash
az webapp deployment slot swap \
  --name <webapp-name> --resource-group <rg-name> \
  --slot production --target-slot staging
# (swaps back to previous code)
```

### Migration rollback (handle with extreme care)

> Prefer a **forward fix** over `db downgrade` in production.

If a migration must be reversed:
1. Restore from the pre-deploy DB snapshot (fastest, cleanest).
2. OR write a forward migration that reverses the change and deploy it.
3. Only use `flask db downgrade <revision>` on staging/dev; in production, always prefer snapshot restore.

---

## 7. Emergency Hotfix Process

For a critical production bug that cannot wait for a normal release:

1. Branch from `main`: `git checkout -b hotfix/<description> main`
2. Make the minimal fix required.
3. Test locally and on staging (abbreviated smoke test).
4. PR into `main` — get at least one review if possible.
5. Deploy directly to production using the standard deploy sequence above.
6. After production is stable, backport the fix to any long-running feature branches.

---

## 8. Key Files Reference

| File / Path | What it controls |
|---|---|
| `Backoffice/run.py` | App entry point (`FLASK_APP` env var points here) |
| `Backoffice/requirements.txt` | Python dependencies — update and commit when adding packages |
| `Backoffice/app/static/css/output.css` | Compiled Tailwind CSS — must be rebuilt and committed with template changes |
| `Backoffice/migrations/versions/` | Migration history — one file per schema change |
| `Backoffice/assets/tailwind.config.js` | Tailwind configuration — update content paths when adding new template directories |
| `.github/workflows/` | CI/CD workflow definitions (if present) |
