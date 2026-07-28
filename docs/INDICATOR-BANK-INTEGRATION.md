# Indicator Bank integration

This document describes the local IFRC Indicator Bank clone, how it is wired to Humanitarian Databank Backoffice, and what remains to retire the legacy stack.

## Local clone (not tracked in git)

The current IFRC Indicator Bank application is cloned from Azure DevOps for reference and deployment:

- **Remote:** `https://dev.azure.com/IFRC/IFRC.IndicatorBank/_git/IFRC.IndicatorBank`
- **Local path:** [`../IFRC.IndicatorBank/`](../IFRC.IndicatorBank/) (gitignored)

To refresh the clone:

```powershell
git -C IFRC.IndicatorBank pull
```

## Architecture (implemented)

```text
IFRC Indicator Bank Blazor public UI
        │  X-API-Key + X-Language
        ▼
Backoffice compat routes (root paths: /Indicator, /Sector, /list-home, …)
        │
        ▼
PostgreSQL (indicator_bank, sectors, embeddings, common_word, …)
```

- **Admin UI in the Blazor app is disabled.** Admin routes show a message that management lives in Backoffice (`/admin/indicator_bank`).
- **Public UI reads from Backoffice** via a compatibility Flask blueprint that mirrors the legacy IFRC Web API contract.
- **Semantic search** uses Backoffice `IndicatorResolutionService` (pgvector + OpenAI embeddings), not the legacy Python mpnet microservice.

## Backoffice compat API

Implementation: [`Backoffice/app/routes/api/indicator_bank_compat.py`](../Backoffice/app/routes/api/indicator_bank_compat.py)

| Path | Method | Purpose |
|------|--------|---------|
| `/Indicator` | GET | Paginated indicator list |
| `/Indicator/<id>` | GET | Indicator detail |
| `/Indicator/search` | GET | Vector search (ILIKE fallback) |
| `/Indicator/tags` | GET | Distinct tag list |
| `/Indicator/selectOptions` | GET | Suggestion form options |
| `/Indicator/Suggestion` | POST | Public suggestions (+ reCAPTCHA) |
| `/Sector` | GET | Sector/subsector tree |
| `/Subsector` | GET | Flat subsector list (suggestion form) |
| `/list-home` | GET | Home page sector tiles + counts/logos |
| `/CommonWord` | GET | Glossary tooltips |
| `/Excel` | GET | Public indicator export (legacy IFRC workbook layout) |

**Auth:** `X-API-Key` (Blazor client) or `Authorization: Bearer` (same keys as `/api/v1`).

**Locale:** `X-Language` header (e.g. `fr`) selects translated name/definition from JSONB fields.

**reCAPTCHA:** set `RECAPTCHA_PROJECT_ID`, `RECAPTCHA_API_KEY`, and optionally `RECAPTCHA_SITE_KEY` in Backoffice env. Action defaults to `SendSuggestion`.

## Blazor client configuration

Update `OpenApiClient:IndicatorBankApi` in:

- `IFRC.IndicatorBank.Client/appsettings.json` (local Backoffice, default `http://127.0.0.1:5000/`)
- `appsettings.PreProd.json` / `appsettings.Release.json` (set `Url` to your deployed Backoffice host)

The `Key` must match a valid Backoffice API key (`api_keys` table or `MOBILE_APP_API_KEY`).

## Pre-cutover checklist

1. **Align API keys** — `OpenApiClient:IndicatorBankApi:Key` in the Blazor appsettings must match a valid Backoffice API key (`api_keys` table) or `MOBILE_APP_API_KEY` in Backoffice `.env`. Without this, all compat calls return 401.
2. Run Backoffice locally (`http://127.0.0.1:5000` by default); smoke-test compat routes:
   ```powershell
   cd Backoffice
   $env:PYTHONPATH = (Get-Location).Path
   python scripts/dev/smoke_indicator_bank_compat.py YOUR_BACKOFFICE_API_KEY
   ```
3. Run the IFRC Blazor client with `appsettings.json` pointing at the same Backoffice host.
4. Ensure indicator embeddings exist (admin sync or `IndicatorResolutionService.sync_all()`) so `/Indicator/search` uses vector search; ILIKE fallback applies if embeddings are missing.
5. Set production `RECAPTCHA_*` env vars on Backoffice before testing suggestions in staging/production.

### Public UI endpoint coverage

| Blazor usage | Compat route | Status |
|--------------|--------------|--------|
| Home tiles | `GET /list-home` | Implemented |
| Sector sidebar / suggestion form | `GET /Sector`, `GET /Subsector` | Implemented |
| Indicator list / sector filter / search fallback | `GET /Indicator` | Implemented |
| Indicator detail | `GET /Indicator/{id}` | Implemented |
| Semantic search | `GET /Indicator/search` | Implemented (Backoffice pgvector) |
| Tag dropdown | `GET /Indicator/tags` | Implemented |
| Suggestion form options | `GET /Indicator/selectOptions` | Implemented |
| Suggestion submit | `POST /Indicator/Suggestion` | Implemented (+ reCAPTCHA) |
| Tooltip glossary | `GET /CommonWord` | Implemented |
| Excel export (header) | `GET /Excel` | Implemented (legacy IFRC column layout) |
| Admin pages | Redirect to Backoffice `/admin/indicator_bank` | Implemented |

### Known limitations

- **Excel import / translation export** still use legacy `POST /Excel`, `GET /Excel/Translation`, etc.; only public **`GET /Excel`** is implemented in the compat layer.
- **Admin auth** is separate: Azure AD login on the Indicator Bank app does not auto-login to Backoffice.

## Legacy stack retirement (post-verification)

After the public Blazor app is verified against Backoffice in staging/production:

| Component | Action |
|-----------|--------|
| `IFRC.IndicatorBank.WebAPI` | Decommission |
| IFRC Indicator Bank SQL Server DB | Decommission |
| `IFRC.IndicatorBank.SearchService` (Python mpnet) | Decommission |
| Blazor admin pages | Already blocked; can remove from codebase later |
| `IFRC_INDICATORBANK_API_*` sync-from-remote | Retire once Backoffice is sole source of truth |

## Related Backoffice code

- Compat layer: `Backoffice/app/routes/api/indicator_bank_compat.py`
- Admin: `Backoffice/app/routes/admin/system_admin/indicator_bank.py`
- Models: `Backoffice/app/models/indicator_bank.py`
- Public REST: `Backoffice/app/routes/api/indicators.py`
- Embeddings / search: `Backoffice/app/services/indicator_resolution_service.py`
