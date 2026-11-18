# Assistant / IDE pointer

Canonical **tracked** engineering documentation for this repository is **[`docs/DEVELOPER-HANDBOOK.md`](docs/DEVELOPER-HANDBOOK.md)** — architecture, local setup (Backoffice, Website, Mobile), migrations policy, AI/RAG, mobile API surface, template/CSS conventions, and troubleshooting.

Do **not** grow long-lived duplicates here; edit the handbook so clones and reviewers stay aligned.

**Creating or changing a plugin (`Backoffice/plugins/**`)?** Follow the CI-enforced contract in [`Backoffice/plugins/README.md`](Backoffice/plugins/README.md#plugin-contract-enforced) (rules in `.cursor/rules/plugin-development.mdc`). Every plugin needs a guarded `/admin/plugins/<plugin_id>/settings` page, `plugin.json`, README and tests; start from `Backoffice/app/sample_plugin_package/`. The `Plugin contract` GitHub workflow blocks PRs and pushes to `main` otherwise.

Other entry points:

- **[`CONTRIBUTING.md`](CONTRIBUTING.md)** — branches, PRs, CI, collaboration  
- **[`docs/README.md`](docs/README.md)** — documentation index  
- **[`Backoffice/docs/README.md`](Backoffice/docs/README.md)** — Backoffice user & setup docs  
- **[`Backoffice/docs/runbooks/README.md`](Backoffice/docs/runbooks/README.md)** — operations & incidents  
