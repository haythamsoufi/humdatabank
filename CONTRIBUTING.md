# Contributing to Humanitarian Databank

Humanitarian Databank exists to help humanitarian actors collect, steward, and share **indicator and form data** responsibly—across languages, countries, and teams. Contributions should make that easier for **focal points, analysts, and the public**, not only for other developers.

This repo is a **monorepo**: **Backoffice** (Flask), **Website** (Next.js), and **MobileApp** (Flutter). Day-to-day setup, conventions, and “where to change things” live in [`CLAUDE.md`](CLAUDE.md) and each app’s README.

## How we like to work

We build in the open with **pragmatic iteration**: small, reviewable changes, real usage, and fixes when something misbehaves in production or staging. Many of us use **AI-assisted editing** (and other automation) to move faster—that is fine **as long as you still understand and test what ships**.

When you open a PR, reviewers should be able to see **what changed, why it matters for users or operators**, and how you **checked** it (manual steps, scripts, or tests). Prefer clarity over polish; prefer a focused diff over a drive-by refactor across unrelated modules.

**Humanitarian context matters in code reviews too.** Indicators, disaggregation, country assignments, and translations touch real programmes and reporting. Be explicit about data-shape and permission implications when your change affects forms, APIs, or exports.

## Before you code

- Skim [`CLAUDE.md`](CLAUDE.md) for migrations (single migration head), CSRF/fetch patterns, Tailwind rebuild for Backoffice templates, and environment notes.
- Do not commit secrets, `.env` files, database dumps, or service account JSON. Follow root `.gitignore` and app-specific env examples.
- Security issues: [`SECURITY.md`](SECURITY.md).

## Collaboration workflow

1. Branch from `main` with a short, descriptive name (e.g. `fix/backoffice-csrf`, `feature/website-maps`).
2. Keep commits and PRs **scoped** to one concern where possible.
3. Open a PR into `main` with a clear title and a description that answers **what**, **why**, and **how you verified**.
4. Link issues with `Fixes #123` when applicable; respond to review feedback before merge.

### Where changes usually land

| Area | Typical focus |
|------|----------------|
| `Backoffice/` | Flask, SQLAlchemy, migrations, admin routes, auth, exports, AI/RAG features |
| `Website/` | Next.js public UI, maps, dataviz, accessibility, performance |
| `MobileApp/` | Flutter, offline behaviour, platform packaging |

## CI, automation, and repo settings

The project uses GitHub **rulesets**, **Dependabot**, **CodeQL**, and related workflows under [`.github/`](.github/). Root [`.github/workflows/`](.github/workflows/) is what Actions actually runs (workflows nested only under an app folder are easy to miss).

If you maintain the repo and need to inspect or update branch rules:

```bash
gh ruleset list --repo OWNER/REPO
gh ruleset check main --repo OWNER/REPO
```

After editing [`.github/ruleset-protect-main.json`](.github/ruleset-protect-main.json), apply updates with the GitHub API (`gh api ... rulesets/RULESET_ID`) as documented in that file’s surrounding maintainer notes—or mirror the same policy in **Settings → Rules → Rulesets**.
- **Branch ruleset** “Protect main” — pull requests required to update `main`, merge methods allowed, stale review dismissal, **resolved review threads required before merge**, no force-push, no branch deletion, and a **required status check** named **`Analyze (CodeQL)`** (see [`.github/ruleset-protect-main.json`](.github/ruleset-protect-main.json); `do_not_enforce_on_create` on that rule avoids blocking brand-new branches).
- **Secret scanning** and **secret scanning push protection** (`gh repo edit`).
- **Dependabot version PRs** — off (no `.github/dependabot.yml`). Dependency bumps are manual unless you add that config back.
- **Code scanning** — [`.github/workflows/codeql.yml`](.github/workflows/codeql.yml) for `javascript-typescript` and `python` over `Backoffice/` and `Website/` (see [`.github/codeql/codeql-config.yml`](.github/codeql/codeql-config.yml)).
- **Dependency Review** on pull requests — [`.github/workflows/dependency-review.yml`](.github/workflows/dependency-review.yml).

Automation detail (for reference): CodeQL in [`.github/workflows/codeql.yml`](.github/workflows/codeql.yml) with [`.github/codeql/codeql-config.yml`](.github/codeql/codeql-config.yml); dependency review in [`.github/workflows/dependency-review.yml`](.github/workflows/dependency-review.yml). If you add a new **required** check to the ruleset, confirm the exact check name in a PR’s **Checks** tab after the first run (e.g. existing **`Analyze (CodeQL)`**).

### Appendix: maintainer snippets (`gh`)

Replace `OWNER/humdatabank` with your org/user and repo name.

```bash
gh repo edit OWNER/humdatabank --delete-branch-on-merge --allow-update-branch
gh repo edit OWNER/humdatabank --enable-auto-merge
```

Update an existing ruleset (ruleset id appears in the GitHub UI URL):

```bash
gh api repos/OWNER/humdatabank/rulesets/RULESET_ID -X PUT --input .github/ruleset-protect-main.json
```

Create the ruleset on a new repo:

```bash
gh api repos/OWNER/humdatabank/rulesets --method POST --input .github/ruleset-protect-main.json
```

On some GitHub plans, ruleset REST calls can return **403** for private repos; use the web UI under **Settings → Rules** in that case.

## Questions

Open a **GitHub issue** for bugs, features, or process questions. For sensitive security topics, use [`SECURITY.md`](SECURITY.md).
