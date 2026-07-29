# Indicator Bank Blazor app — migration to Humanitarian Databank Backoffice

**Audience:** IFRC Indicator Bank application team (`IFRC.IndicatorBank` Azure DevOps repo)  
**From:** Humanitarian Databank / Backoffice team  
**Purpose:** Describe the changes required in the Blazor public client so it reads indicator data from Backoffice instead of the legacy `IFRC.IndicatorBank.WebAPI`.

---

## Summary

Humanitarian Databank Backoffice now hosts the canonical Indicator Bank data (PostgreSQL) and exposes a **compatibility HTTP API** that mirrors the legacy IFRC Indicator Bank Web API contract.

The Blazor public UI **does not need a new API client**. The existing NSwag-generated `IndicatorBankClient` and route paths (`/Indicator`, `/Sector`, `/list-home`, etc.) stay as they are. The migration uses **minimal app changes**:

1. **Repoint** `OpenApiClient:IndicatorBankApi:Url` (and API key) to Backoffice.
2. **Hide** the “Admin site” and “Login” buttons in the header — there is no longer a reason for public users to sign in.
3. **Fix** sector image rendering on the home page (Backoffice returns raw image bytes, not SVG-only).

No router changes or admin redirects are required. Legacy admin routes can remain in the codebase; they are simply not linked from the public UI. Indicator management is done in Backoffice at `/admin/indicator_bank`.

After cutover, `IFRC.IndicatorBank.WebAPI`, the legacy SQL Server database, and `IFRC.IndicatorBank.SearchService` can be retired for the public site.

---

## Target architecture

```text
IFRC Indicator Bank Blazor public UI
        │  X-API-Key + X-Language
        ▼
Humanitarian Databank Backoffice compat routes
  /Indicator, /Sector, /list-home, /Indicator/search, …
        │
        ▼
PostgreSQL (indicator_bank, sectors, embeddings, common_word, …)
```

**Admin:** Indicator management lives in Backoffice at `/admin/indicator_bank`. For this migration, hide admin/login from the public header only — do **not** add redirects or router changes.

**Search:** Semantic search is served by Backoffice (`GET /Indicator/search` using pgvector embeddings). The legacy Python mpnet search microservice is no longer required for the public UI.

---

## What does not change

These existing pieces already work with Backoffice and require **no code changes**:

| Component | Why |
|-----------|-----|
| NSwag-generated `IndicatorBankClient.cs` | Compat API uses the same paths and response shapes |
| `OpenApiClientRegistration.cs` | Already sends `X-API-Key` on every request |
| `LanguageHeaderHandler.cs` | Already sends `X-Language` from the current culture |
| Public page components that call `IIndicatorClient`, `ISectorClient`, etc. | Same interfaces; only the base URL changes |
| `Routes.razor` and admin page components | No changes — admin routes stay in place, just not linked from the header |

---

## Required changes

### 1. Configuration — point API at Backoffice

Update `OpenApiClient:IndicatorBankApi` in each environment file under `IFRC.IndicatorBank.Client/`:

| File | `Url` | Notes |
|------|-------|-------|
| `appsettings.json` | `http://127.0.0.1:5000/` | Local Backoffice dev server |
| `appsettings.Debug.json` | `https://databank.ifrc.org/` | Production Backoffice (debug builds) |
| `appsettings.PreProd.json` | `https://databank-stage.ifrc.org/` | Staging Backoffice |
| `appsettings.Release.json` | `https://databank.ifrc.org/` | Production Backoffice |

Example (PreProd):

```json
"OpenApiClient": {
  "IndicatorBankApi": {
    "Url": "https://databank-stage.ifrc.org/",
    "Key": "<Backoffice API key for this environment>"
  }
}
```

**Before (legacy):**

| Environment | Old `Url` |
|-------------|-----------|
| Local | `https://localhost:7193` |
| PreProd | `https://ifrc-indicatorbank-staging.azurewebsites.net/` |
| Release | `https://ifrc-indicatorbank.azurewebsites.net/` |

**API key:** `Key` must be a valid Backoffice API key on the **same host** as `Url`. Coordinate with the Backoffice team to provision keys per environment (stored in Backoffice `api_keys` table). Without a matching key, all compat calls return **401**.

**Trailing slash:** Keep a trailing slash on `Url` (e.g. `https://databank-stage.ifrc.org/`) so relative client paths resolve correctly.

---

### 2. Header — hide admin and login buttons

**Update:** `IFRC.IndicatorBank.Client/Components/Header.razor`

Remove (or comment out):

- The **“Admin site”** button (`NavToAdminList` → `Routing.Admin`) and its click handler
- The public **“Login”** button (`MicrosoftIdentity/Account/SignIn`) and its click handler

This is intentionally minimal: no changes to `Routes.razor`, no redirect component, and no new routing logic. Public users no longer need Azure AD login because all public data is read via API key against Backoffice.

You can also remove unused `Login()` / `NavToAdminList()` methods if nothing else references them.

---

### 3. Home page — sector tile images

Backoffice returns sector logos as raw byte arrays (PNG, JPEG, SVG, etc.). The home page previously assumed SVG-only (`data:image/svg;base64,...`), which breaks some tiles.

**Update:** `IFRC.IndicatorBank.Client/Components/Pages/Public/Home.razor`

Replace the fixed SVG data URL with MIME detection, e.g.:

```csharp
private static string GetSectorImageDataUrl(byte[]? image)
{
    if (image is null || image.Length <= 10)
        return string.Empty;

    var mime = "image/png";
    if (image.Length >= 3 && image[0] == 0xFF && image[1] == 0xD8)
        mime = "image/jpeg";
    else if (image.Length >= 4 && image[0] == 0x89 && image[1] == 0x50)
        mime = "image/png";
    else if (image.Length >= 3 && image[0] == 0x47 && image[1] == 0x49)
        mime = "image/gif";
    else if (image[0] == 0x3C || (image.Length >= 5 && image[0] == 0xEF && image[1] == 0xBB && image[2] == 0xBF && image[3] == 0x3C))
        mime = "image/svg+xml";

    return $"data:{mime};base64,{Convert.ToBase64String(image)}";
}
```

Use in markup: `src="@GetSectorImageDataUrl(sector.Image)"`.

Optional: add `justify-content-center` on the sector tile container if layout regresses after image fixes.

---

## Backoffice compat API (reference)

Backoffice implements the legacy contract at **root paths** on the same host as the web app (not under `/api/v1`).

| Path | Method | Public UI usage |
|------|--------|-----------------|
| `/list-home` | GET | Home page sector tiles, counts, logos |
| `/Sector` | GET | Sector sidebar, suggestion form |
| `/Subsector` | GET | Flat subsector list (suggestion form) |
| `/Indicator` | GET | Indicator list, sector filter |
| `/Indicator/{id}` | GET | Indicator detail |
| `/Indicator/search` | GET | Semantic search |
| `/Indicator/tags` | GET | Tag dropdown |
| `/Indicator/selectOptions` | GET | Suggestion form options |
| `/Indicator/Suggestion` | POST | Public suggestion submit |
| `/CommonWord` | GET | Glossary tooltips |
| `/Excel` | GET | Public Excel export (header button) |

**Auth:** `X-API-Key` header (already set by your HTTP client registration).  
**Locale:** `X-Language` header (e.g. `fr`, `es`) — Backoffice returns translated name/definition where available.

**Suggestions:** `POST /Indicator/Suggestion` validates Google reCAPTCHA Enterprise on Backoffice. Ensure `RecaptchaConfig:SiteKey` in the Blazor app matches the Backoffice project; Backoffice must have `RECAPTCHA_PROJECT_ID` and `RECAPTCHA_API_KEY` set in staging/production.

---

## Verification checklist

Use this before promoting each environment.

### Backoffice (coordinate with Backoffice team)

- [ ] Compat routes respond on the target host (staging or production).
- [ ] API key for the Blazor app is created and active on that host.
- [ ] Indicator embeddings are synced (for vector search on `/Indicator/search`).
- [ ] reCAPTCHA env vars are set if testing suggestion submit.

### Blazor app

- [ ] `appsettings.*.json` — `IndicatorBankApi:Url` and `Key` match the target Backoffice host.
- [ ] Home page loads sector tiles with images and counts.
- [ ] Sector browse, indicator list, and indicator detail work.
- [ ] Search returns results.
- [ ] Excel export from the header downloads a workbook.
- [ ] Suggestion form loads options and submits successfully.
- [ ] Glossary tooltips load (`/CommonWord`).
- [ ] Header no longer shows “Admin site” or public “Login”.

### Smoke test (optional)

The Backoffice repo includes a script to hit all compat endpoints with an API key. Ask the Backoffice team to run it against staging/production, or run locally against a dev server:

```powershell
cd Backoffice
$env:PYTHONPATH = (Get-Location).Path
python scripts/dev/smoke_indicator_bank_compat.py YOUR_API_KEY
```

Pass `--base-url https://databank-stage.ifrc.org` (or production URL) to test a remote host.

---

## Known limitations

| Area | Status |
|------|--------|
| Public read paths (`GET /Indicator`, `/Sector`, `/Excel`, etc.) | Supported via compat layer |
| Public suggestion submit | Supported (+ reCAPTCHA on Backoffice) |
| Admin CRUD in Blazor | **Not linked** from public UI; management is in Backoffice `/admin/indicator_bank` |
| Direct navigation to legacy admin URLs | Still reachable if URL is known; out of scope for this minimal change |
| Excel **import** / translation export (`POST /Excel`, `GET /Excel/Translation`, …) | **Not** in compat layer; legacy admin endpoints only |

---

## Post-cutover decommissioning

After the public Blazor app is verified in staging and production:

| Legacy component | Action |
|------------------|--------|
| `IFRC.IndicatorBank.WebAPI` | Decommission |
| IFRC Indicator Bank SQL Server database | Decommission |
| `IFRC.IndicatorBank.SearchService` (mpnet) | Decommission |
| Blazor admin pages / WebAPI deploy pipelines | Remove when no longer needed |

---

## Questions / coordination

- **API keys per environment:** request from Humanitarian Databank Backoffice team.
- **Data or search issues:** Backoffice admin → Indicator Bank management and embedding sync.
- **Compat API behaviour:** contact the Humanitarian Databank team; reference implementation path on request (`indicator_bank_compat.py`).
