# Committed production artifacts: history purge and credential rotation

> **Status:** the files below were **untracked** (`git rm -r --cached`) and ignored via `.gitignore`. They are **still in git history**. Purging history and rotating credentials are follow-up actions that need repo-owner approval and a coordinated force-push. Nothing in this runbook has been executed.

## What was committed

| Path | Content | Sensitivity |
|---|---|---|
| `Backoffice/prod-logs-incident/` (about 1,730 files, 7.5 MB) | Kudu/App Service log download (`LogFiles`, `deployments`) from a production incident | 492 distinct client IP addresses (personal data), the production hostname, `ARRAffinity` cookies, deploy actor / repository names. A scan of the parsed logs found **no** bearer tokens or passwords (Authorization values were truncated), but treat the set as confidential. |
| `Backoffice/prod_data_sample.json` | Sample export of production data | Production records (potentially personal data) |
| `Backoffice/instance/*` | Local Flask instance / cache files | May contain cached data and local config |
| `localhost.har` (history only, commits `3448326c`, `a6e02b26`) | Browser HAR capture | May contain session cookies / CSRF tokens / API responses |
| Repo root `*.pdf`, `*.twb`, `Backoffice/scripts/ops/restore_myr26_after_upr_master_import.payload.json.gz` | Country reports, Tableau workbooks, a restore payload | Business data, still **tracked** (see "Optional untracking") |

Root cause: the `instance/` ignore rule existed but the files had been added before/around it (ignore rules do not affect tracked files), there was no rule for incident log downloads or data samples, and the root `.gitignore` ignored `.dockerignore`, so there was no build-context filter either (a `Backoffice/.dockerignore` now exists and is un-ignored).

## Already done in the working tree

```bash
git rm -r --cached Backoffice/prod-logs-incident Backoffice/prod_data_sample.json Backoffice/instance
# .gitignore updated (artifact patterns, azure-credentials-*.txt, /*.pdf, !Backoffice/.dockerignore)
```

Commit these with the rest of the change set (the index already contains the deletions). Files stay on disk for anyone who still needs them.

## Optional untracking (needs a product decision)

```bash
git rm --cached -- "Bangladesh - Midyear Reporting 2026 - Unified Country Report 22 sept (1).pdf" \
  "Bangladesh UPL MYR 2026.pdf" \
  "comments round 2 - Bangladesh - Midyear Reporting 2026 - Unified Country Report edits 1.pdf" \
  "edits - Bangladesh - Midyear Reporting 2026 - Unified Country Report.pdf" \
  "UPR Visuals.twb" "Orignal flow/UPR Visuals.twb"
git rm --cached Backoffice/scripts/ops/restore_myr26_after_upr_master_import.payload.json.gz  # only if it is not needed by the runbook
```

## History purge (repository owner, coordinated)

1. Announce a freeze; ask contributors to push or stash their work.
2. Work on a **fresh mirror clone**, not a working checkout:

   ```bash
   git clone --mirror git@github.com:<org>/<repo>.git purge.git && cd purge.git
   git filter-repo \
     --path Backoffice/prod-logs-incident \
     --path Backoffice/prod_data_sample.json \
     --path Backoffice/instance \
     --path localhost.har \
     --invert-paths
   ```

   (`git filter-repo` from <https://github.com/newren/git-filter-repo>; BFG Repo-Cleaner is an alternative.) Add further paths from the optional list if they should go too.
3. Verify: `git log --all -- Backoffice/prod-logs-incident Backoffice/prod_data_sample.json` is empty and `gitleaks detect --log-opts="--all"` is clean.
4. Force-push all refs: `git push --force --mirror` (branch protection must be temporarily relaxed by an admin).
5. Ask GitHub Support to purge cached views / dangling commits and PR refs (`refs/pull/*`) that still reference the old objects; forks and clones keep the data until they are deleted or re-cloned.
6. Every contributor re-clones (do not merge old branches back in). Close/rebase open PRs.

## Rotation and clean-up checklist

No live credentials were found in the artifacts, so rotation is precautionary and proportional:

- [ ] Confirm with the incident owner what the `prod_data_sample.json` export contained; if it held personal data, follow the organisation's data-breach assessment process (the repo may have been readable by more people than the data).
- [ ] Treat the 492 client IPs as personal data in that assessment.
- [ ] Invalidate sessions: rotate `SECRET_KEY` only if there is evidence the HAR or logs held live session cookies (this logs every user out). Rotate `MOBILE_JWT_SECRET` / `AI_JWT_SECRET` only on evidence of token exposure.
- [ ] Rotate the App Service publish profile / deployment credentials and any CI deploy secret whose name or identity appears in `deployments/` logs.
- [ ] Rotate the database password if any connection string appeared in the HAR or instance files (grep the mirror before purge).
- [ ] Retire container image tags built before the SSH hardening (they contain the fixed `root:Docker!` credential and shared host keys).
- [ ] Add/verify secret scanning: `.github` gitleaks workflow, `scripts/ci/scan_secrets.py` and GitHub push protection are enabled on the repository.

## Prevention

- `.gitignore` covers incident log dumps, data samples, `instance/`, HAR files and Azure credential exports.
- `Backoffice/.dockerignore` keeps these out of image build contexts.
- Do not commit incident material; store it in the incident SharePoint/ticket and reference it from the runbook.
