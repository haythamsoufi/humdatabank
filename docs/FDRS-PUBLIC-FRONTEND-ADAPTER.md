# FDRS public frontend adapter

How [data.ifrc.org](https://data.ifrc.org/) can keep calling the same paths and JSON shapes, while the numbers come from Humanitarian Databank Backoffice.

This is separate from the Indicator Bank Blazor cutover (`INDICATOR-BANK-APP-TEAM-HANDOFF.md`). That site reads the indicator catalogue. data.ifrc.org reads FDRS time series, National Society profiles, documents, and page content from `https://data-api.ifrc.org`.

## Goal

Leave the Angular client in place. Serve the contract it already compiles in, from published Backoffice data.

## Status

Implemented in the FDRS plugin:

| Piece | Where |
|---|---|
| Routes (`/api/lastpublishedyear`, `/api/entities/ns[/<doncode>]`, `/api/data`, `/api/dataimputed`, `/api/KpiImputedValue`, `/api/globalvalidationdata`, `/api/kpivalue`) | `Backoffice/plugins/fdrs/public_compat_routes.py` |
| Code translation, published-snapshot query, response trees | `Backoffice/plugins/fdrs/services/fdrs_public_adapter.py` |
| Society reference | `national_societies.fdrs_don_code` and zone columns (`flask fdrs-societies import`) |
| Seeding | `flask fdrs-societies import` / `link` (`app/cli_commands/fdrs_societies.py`) |
| `apiKey` query alias | `query_api_key_value()` in `app/services/security/api_authentication.py` |
| `/csv/export` and `/csv/exportns` (`excel=1` for `.xlsx`) | Published snapshot, one row per society, year and KPI code |
| `GET /api/documents` | Publications (`resource_type = publication`, subcategory → `EveryoneCounts` / `Analysis` / `FrontendVideo`) and, with `ns`, public approved submitted documents |
| Forward to `https://data-api.ifrc.org` for `embeddedcontent`, `smarttran`, `tran`, `offices`, `documentSubscribe` | Always. Uses `FDRS_DATA_API_KEY`. `FDRS_DATA_API_BASE` overrides the host |
| Tests | `Backoffice/tests/unit/test_plugins/test_fdrs_public_compat.py` |

Not implemented: translations, embeds and offices (see [Content that is not the indicator bank](#content-that-is-not-the-indicator-bank)). `/api/documents` reads Manage Resources publications and public approved submitted documents. `/csv/export` and `/csv/exportns` are files of the published snapshot.

### Set up

1. Run the migration (`flask db upgrade`).
2. Seed the societies from the legacy list: `flask fdrs-societies import --from-api` (dry run), then add `--apply`. `FDRS_DATA_API_BASE` and `FDRS_DATA_API_KEY` supply the source. Societies it reports as having no country need a matching `country.iso3` / `iso2`, then `flask fdrs-societies link --apply`. A re-run only fills blanks; `--overwrite` replaces edited values.
3. Create an API key in Admin → API Keys with the **`content:read`** capability and **"allow API key in query string"** on. The client sends the key in the URL, so a key without that setting gets `403`. Raise its rate limit: the default is 60 requests a minute per key, and every visitor shares the one key the site ships.
4. Mark the FDRS form items the site shows as `privacy = public` and publish them with Manage Publication. Anything else is invisible here, including the income-sources matrix (item 943), the network-support matrices (919, 929) and the President / Secretary General sex questions (924, 934).
5. Browser calls from data.ifrc.org are cross-origin. Add that origin to `CORS_ALLOWED_ORIGINS`; `/api/*` already goes through Flask-CORS. `/csv/*` is a plain link and needs no CORS entry.

`FDRS_DATA_API_KEY` is the key already used for FDRS sync against data-api.ifrc.org. `FDRS_DATA_API_BASE` defaults to `https://data-api.ifrc.org`. Set it only to point at a different legacy host. If Backoffice takes over the `data-api.ifrc.org` hostname, this base must stay the old origin under another hostname. A base equal to the request host is refused with `502`.

The production bundle initialises its FDRS client once:

```text
fdrsHttpService.initialize("https://data-api.ifrc.org/api/", "<apiKey>")
```

Every call is `base + relativePath`, and every call adds `apiKey` as a query parameter. CSV links are absolute on the same host (`/csv/export`, `/csv/export?excel=1`, `/csv/exportns?doncode=`). GO appeals, Mapbox, YouTube, and Tableau stay on their own hosts.

## Recommendation

Add a Backoffice compatibility blueprint, the same idea as `indicator_bank_compat`, that answers the legacy paths and reshapes published FDRS rows into the nested JSON the site already parses.

Put that blueprint on a host whose path layout matches the client:

| Option | Frontend change | When to use it |
|---|---|---|
| **A. Take over `data-api.ifrc.org`** | None. DNS or the app gateway sends `/api/*` and `/csv/*` to Backoffice. | Preferred cutover. The base URL, the CSV links, and the compiled `apiKey` keep working. |
| **B. New host, same paths** | One config change: `fdrsHttpService.initialize("https://<new-host>/api/", key)`, plus the three CSV `href`s. | Use if `data-api.ifrc.org` must stay up in parallel (staging, shadow read). |

Do not invent a new prefix such as `/api/v1/fdrs-compat`. The client concatenates paths onto `…/api/`, so the routes have to be `/api/data`, `/api/entities/ns`, and so on. Those paths do not collide with Backoffice `/api/v1`, `/api/mobile/v1`, or `/api/ai/v2`.

```text
data.ifrc.org  (unchanged Angular app)
        │  GET /api/data?indicator=…&year=…&apiKey=…
        │  GET /api/entities/ns
        │  GET /csv/export
        ▼
data-api.ifrc.org   ← option A, or a new host (option B)
        │
        ▼
Backoffice blueprint  fdrs_public_compat
        │  published FDRS snapshot only (template 21, privacy = public)
        ▼
PostgreSQL   form_data.published_*  +  indicator_bank.fdrs_kpi_code
             + a small FDRS society reference (DON code, zone, coordinates)
```

Auth stays the query parameter the client already sends. Backoffice accepts `apiKey`, `apikey` and `api_key` in the query string, plus `Authorization: Bearer` and `X-API-Key` for other callers. The key must hold `content:read`, and the query-string form works only for keys with `allow_query_api_key`. Do not switch this client to `X-API-Key` or `Authorization: Bearer`; that would be a frontend change. A missing or unknown key returns `401`.

The adapter reads only the published snapshot (`published_value`, `published_numeric_value`, `published_disagg_data`, `published_source`, `published_at`). A cell that has an unpublished edit still returns the last published figure. `showunpublished=true` is accepted and ignored.

## What the client sends

Confirmed against the live bundle and `fdrs_api_endpoints.xlsx`.

### Paths

| Method | Path | Used for |
|---|---|---|
| GET | `/api/lastpublishedyear` | Default reporting year |
| GET | `/api/entities/ns` | Society list for maps and filters |
| GET | `/api/entities/ns/<doncode>` | Society profile |
| GET | `/api/data` | KPI series, comparisons, age/sex, leadership, income sources, network support |
| GET | `/api/dataimputed` | Imputed income/expenditure and people-reached charts |
| GET | `/api/KpiImputedValue` | Imputed map layer |
| GET | `/api/globalvalidationdata` | Volunteer total; zone filter is applied in the browser |
| GET | `/api/kpivalue` | One KPI per society. The public site no longer calls this for digital maturity |
| GET | `/api/documents` | Everyone Counts, analysis, videos, society documents |
| GET | `/api/embeddedcontent` | Dashboard embeds |
| GET | `/api/smarttran` | Page translations |
| GET | `/api/tran` | Key-highlight strings |
| GET | `/api/offices` | Office map |
| POST | `/api/documentSubscribe` | Document mailing list |
| GET | `/csv/export` | Full CSV download |
| GET | `/csv/export?excel=1` | Excel download |
| GET | `/csv/exportns?doncode=` | One-society CSV |

These stay outside the adapter:

| Call | Host |
|---|---|
| `GET /api/v2/appeal/aggregated` and `…/?iso3=` | `https://goadmin.ifrc.org` |
| Mapbox country bounds | `https://api.mapbox.com` |
| YouTube oEmbed | `https://www.youtube.com/oembed` |
| About-page chart | Tableau |

### Query parameters

| Parameter | Values the client sends |
|---|---|
| `apiKey` | On every FDRS call |
| `indicator` | Comma-separated KPI codes (see below) |
| `year` | Calendar year |
| `KPI_Don_Code` | One DON code, or several comma-separated |
| `kpicode` | One KPI code. Map calls append `_IP` |
| `zon_code` | `S1`–`S5`. Omitted when the UI selection is World |
| `showunpublished` | `true` on `kpivalue`. Ignore it |
| `type` | Documents: `FrontendVideo`, `EveryoneCounts`, `Analysis`. Embeds: `OVERVIEW-INTERNATIONAL`, `GLOBAL-INITIATIVES`, `OCAC`, `BOCA`, `UNIFIED-PLANNING` |
| `isglobal` | `true` for global document lists |
| `ns` | DON code, for society documents |
| `page` | Translation page: `frontend.<page>`, or unprefixed `country` and `nsname` |
| `key`, `langcode` | Key-highlight lookup (`tran`) |

Zones:

| Code | Name |
|---|---|
| `S1` | Africa |
| `S2` | Americas |
| `S3` | Asia Pacific |
| `S4` | Europe and Central Asia |
| `S5` | Middle East and North Africa |
| *(omitted)* | World |

### Indicator codes

Headline codes the dropdown sends:

| Group | Codes |
|---|---|
| General | `KPI_PeopleVol_Tot`, `KPI_PStaff_Tot`, `KPI_DonBlood_Tot`, `KPI_TrainFA_Tot`, `KPI_IncomeLC_CHF`, `KPI_expenditureLC_CHF`, `KPI_GB_Tot`, `KPI_noLocalUnits`, `KPI_noBranches` |
| People reached | `KPI_ReachLTSPD_CPD`, `KPI_ReachDRER_CPD`, `KPI_ReachDRR_CPD`, `KPI_ReachS_CPD`, `KPI_ReachCTP_CPD`, `KPI_ReachL_CPD`, `KPI_ReachH_CPD`, `KPI_ReachHPM_CPD`, `KPI_ReachHI_CPD`, `KPI_ReachWASH_CPD`, `KPI_ReachM_CPD`, `KPI_ReachSI_CPD`, `KPI_ReachRCRCEd_CPD`, `KPI_Climate_CPD`, `KPI_ClimateHeat_CPD` |

Other fixed values:

| Codes | Call |
|---|---|
| `KPI_IncomeLC_CHF_IP,KPI_expenditureLC_CHF_IP` | `GET /api/dataimputed?year=` |
| `h_gov_CHF,f_gov_CHF,ind_CHF,corp_CHF,found_CHF,un_CHF,pooled_f_CHF,ngo_CHF,si_CHF,iga_CHF,KPI_incomeFromNSsLC_CHF,ifrc_CHF,icrc_CHF,other_CHF` | `GET /api/data?year=` and the same list with `KPI_Don_Code` on a society profile |
| `KPI_pr_sex,KPI_sg_sex` | `GET /api/data?year=&KPI_Don_Code=` |
| `supported1,received_support1` | `GET /api/data?KPI_Don_Code=` |

Sex and age are not extra query parameters. The client derives response ids:

- Sex chart: request `indicator` is the selected code unchanged (`KPI_PeopleVol_Tot`). The response must contain series `KPI_PeopleVol_Tot_M` and `KPI_PeopleVol_Tot_F`.
- Age chart: `_Tot` and `_CPD` are stripped first, so the request is `indicator=KPI_PeopleVol`. The response must contain `KPI_PeopleVol_M_age_<band>` and `KPI_PeopleVol_F_age_<band>`.
- Age bands: `6_12`, `13_17`, `18_29`, `30_39`, `40_49`, `50_59`, `60_69`, `70_79`, `80`.

Imputed map calls append `_IP` and use `KpiImputedValue`, not `/api/data`.

## Response shapes the client parses

`/api/data` and `/api/dataimputed` share one tree. `data[].id` is the indicator code. The next `data[].id` is the DON code. The leaves are `{ year, value }`.

```json
{
  "data": [
    {
      "id": "KPI_PeopleVol_Tot",
      "data": [
        {
          "id": "DKEN001",
          "data": [
            { "year": 2023, "value": 1500 },
            { "year": 2024, "value": 1600 }
          ]
        }
      ]
    }
  ]
}
```

The age/sex mapper does `response.data.filter(series => expectedIds.includes(series.id))`, then finds the society with `series.data.find(row => row.id == doncode)`. A request for `indicator=KPI_PeopleVol` has to return the age-band series ids, not only a single `KPI_PeopleVol` series. Comma-separated `indicator` values each become one series (income sources work this way).

`GET /api/KpiImputedValue` is a flat list. `source == "I"` is what the map treats as imputed:

```json
[
  { "doncode": "DKEN001", "value": 1600, "source": "I" }
]
```

`GET /api/globalvalidationdata?year=` is a list of `{ "ZoneCode": "S1", "IntValue": 123456 }`. The world total is the row whose `ZoneCode` is empty. The client picks the row; the adapter should return every zone plus the world row.

`GET /api/entities/ns` is an array. Fields the client reads:

| Field | Use |
|---|---|
| `KPI_DON_code` | Society id in every other call |
| `NSO_DON_name` | Display name |
| `NSO_ZON_name` | Zone label |
| `ZON_Code` | `S1`–`S5` |
| `iso_3`, `iso_2` | Country codes; ISO3 is then sent to GO |
| `lat`, `long` | Map pin |
| `admission_date` | Profile (`dd.MM.yyyy`) |
| `Url` | Society website link |

`GET /api/entities/ns/<doncode>` is one object with those fields.

`GET /api/kpivalue` rows are filtered in the browser with `row.doncode`. Include `doncode` and `value`.

`GET /api/documents` is read as `response[0].documents`.

`GET /api/embeddedcontent` rows include `Id`, `TitleEn` / `TitleEs` / `TitleFr` / `TitleAr`, the matching `Text*` fields, and `EmbedCode`.

`GET /api/smarttran` rows include `LanguageCode`, `Page`, `Name`, `Value`.

`GET /api/offices` rows include `name`, `officetype`, `lat`, `long`, `covering`.

`POST /api/documentSubscribe` body is `{ "email", "name", "organization" }`.

`/csv/export` and `/csv/exportns` return a file, not JSON.

## How a legacy code becomes a Backoffice cell

Backoffice does not store one row per public KPI string. Headline indicators live on the indicator bank as `fdrs_kpi_code` **without** `_Tot`, `_CPD`, or `_IP`. Sex and age live in `published_disagg_data` on that same cell. Income-source codes are matrix rows. `KPI_pr_sex` and `KPI_sg_sex` are form questions (President and Secretary General), not bank codes.

Resolve in this order:

1. If the code ends in `_IP`, strip it and resolve the base. `_IP` means reported **plus** imputed: every published cell counts. Without `_IP`, a cell whose `published_source` is `imputed` is dropped (reported only).
2. Strip a trailing `_Tot` or `_CPD` to get the bank code (`KPI_PeopleVol_Tot` → `KPI_PeopleVol`, `KPI_ReachH_CPD` → `KPI_ReachH`). `KPI_IncomeLC_CHF`, `KPI_expenditureLC_CHF`, `KPI_noLocalUnits`, and `KPI_noBranches` are already bank codes.
3. If the remainder ends in `_M` or `_F`, or in `_M_age_<band>` / `_F_age_<band>`, the bank code is the part before that suffix. The number comes from `published_disagg_data` (male/female, then the age band). Bands already used in Backoffice are `6_12`, `13_17`, `18_29`, `30_39`, `40_49`, `50_59`, `60_69`, `70_79`, `80`.
4. Income-source codes (`h_gov_CHF`, `f_gov_CHF`, `ind_CHF`, `corp_CHF`, `found_CHF`, `un_CHF`, `pooled_f_CHF`, `ngo_CHF`, `si_CHF`, `iga_CHF`, `other_CHF`, `KPI_incomeFromNSsLC_CHF`, `ifrc_CHF`, `icrc_CHF`) are published matrix rows on the FDRS finance item, not `indicator_bank` rows.
5. `KPI_pr_sex` and `KPI_sg_sex` are the published President and Secretary General sex questions.
6. `supported1` and `received_support1` are the published network-support values. The client splits `value` on commas and treats the pieces as DON codes, so the adapter keeps that comma-separated text. Backoffice stores one matrix cell per counterpart (`{society name}_{column}`) and has lost the legacy slot numbers, so slot 1 carries every counterpart and `supported2` … `supported10` return nothing. `supported1_amount` returns the matching amounts in the same order. Counterpart names are mapped back to DON codes through `national_societies.name`, then ISO3.
7. `year` matches the calendar year of `AssignedForm.period_name` (FDRS periods are stored as the year, for example `2024`).
8. `KPI_Don_Code` matches the society reference below, then the country’s published row. When several DON codes are passed, return each of them under that indicator.

`/api/data` and `/api/dataimputed` run the same code, so the `_IP` rule above decides what is included. `/api/KpiImputedValue` returns every society that has a published value for `kpicode` and `year`; `source` is `"I"` for an imputed cell and `"R"` for a reported one. When `zon_code` is present, limit rows to societies in that zone.

Sex and age series are added to the reply only when the request carries `KPI_Don_Code`. A request for `KPI_PeopleVol_Tot` then also returns `KPI_PeopleVol_Tot_M` and `_F`; a request for the bare `KPI_PeopleVol` also returns the 18 `KPI_PeopleVol_{M,F}_age_<band>` series. The world-wide map call does not get them, which would triple its size. If the production client turns out to send the sex or age request without `KPI_Don_Code`, change `resolve_requested(..., society_scoped=...)`.

When a code is unknown, private, or has no published value for the filters, its series is left out. If nothing matches, the reply is `{ "data": [] }`.

`/api/lastpublishedyear` returns a bare JSON number. With no published data it returns the previous calendar year.

`/api/KpiImputedValue` and `/api/globalvalidationdata` use the latest published year when `year` is missing. `/api/kpivalue` resolves `kpicode` like any other bank code and returns `[]` when `kpicode` is omitted. The public site no longer requests `KPIDigitalPeople`, `KPIDigitalProcess`, or `KPIDigitalTechnology`.

`/api/lastpublishedyear` is the greatest year that has any published public FDRS value.

`/api/globalvalidationdata` sums published `KPI_PeopleVol` for that year, reported and imputed: one row per `S1`–`S5` (0 when a zone has no data), plus a world row with an empty `ZoneCode`. Whether the legacy figure includes imputed volunteers is an assumption; compare one year against the live API before cutover.

## Society reference the adapter needs

`Country` has ISO codes, name, and region. It does not have a FDRS DON code, `S1`–`S5`, coordinates, admission date, or website. `NationalSociety.code` is not the DON code (`DKEN001` and similar).

`national_societies` holds the society the public site selects. FDRS-only fields sit on that row (`fdrs_don_code`, `fdrs_zone_code`, `fdrs_zone_name`, coordinates, admission date, website). A row with no `fdrs_don_code` is hidden from these endpoints.

| Column | Legacy field |
|---|---|
| `fdrs_don_code` | `KPI_DON_code` |
| `country_id` | join to `country` (iso2 / iso3) |
| `name` | `NSO_DON_name` |
| `country.iso2`, `country.iso3` | `iso_2`, `iso_3` |
| `fdrs_zone_code` | `ZON_Code` (`S1`–`S5`) |
| `fdrs_zone_name` | `NSO_ZON_name` (defaults to the zone table above) |
| `latitude`, `longitude` | `lat`, `long` |
| `admission_date`, `admission_date_note` | `admission_date` (served as `dd.MM.yyyy`), `admission_date_note` |
| `currency_code`, `fdrs_search_string` | `cur_code`, `SearchString` |
| `website`, `facebook`, `twitter`, `other_social` | `Url` (also served as `url`), `facebook`, `twitter`, `othersocial` |
| `is_active` | Hidden from every endpoint when false |

Seed it once from the current `GET /api/entities/ns` payload (`flask fdrs-societies import`). A DON code is stored on the National Society for that ISO code. A code with no `country` match is reported and skipped, because every National Society belongs to a country. Re-import fills blanks; `--overwrite` replaces edited values. Data endpoints join through `country_id`.

## Content that is not the indicator bank

Numbers can move first. The rest of the homepage is content the published-data feed does not store.

| Endpoint | Backoffice today | Adapter approach |
|---|---|---|
| `/api/data`, `/api/dataimputed`, `/api/KpiImputedValue`, `/api/globalvalidationdata`, `/api/lastpublishedyear` | Published FDRS snapshot | **Done** (phase 1) |
| `/api/entities/ns` | `national_societies` rows that have `fdrs_don_code` | **Done** (phase 1) |
| `/api/kpivalue` | Published snapshot for the requested `kpicode`. Omitted `kpicode` returns `[]` | **Done** |
| `/csv/export`, `/csv/exportns` | Published snapshot, long file (`KPI_DON_code`, year, `KPI_code`, `Value`, `source`). `excel=1` is the same rows as `.xlsx` | **Done** |
| `/api/documents` | Manage Resources publications when `type` / `isglobal` is set. `ns` is that society's public approved submitted documents. Shape is `[{code, documents}]` | **Done** |
| `/api/embeddedcontent`, `/api/smarttran`, `/api/tran`, `/api/offices`, `/api/documentSubscribe` | Not stored as FDRS CMS content | Phase 3. Same forward or `501` until an editor exists in Backoffice |

Translations, embeds, offices, and the mailing list are always relayed to `https://data-api.ifrc.org`. Backoffice replaces the caller’s key with `FDRS_DATA_API_KEY`. The upstream path is fixed in code and redirects are not followed. The relay adds a hop and the legacy API’s latency to those paths.

## Implementation sketch

The routes live on the FDRS plugin blueprint with no prefix, so the paths are exactly `/api/data` and so on. Admin → API Management lists them under the **FDRS public frontend** filter, and the URL builder on that page can call them (it sends the key as `Authorization: Bearer`).

Rules the code enforces:

- Public items on FDRS template 21 only (`privacy = public`).
- Published columns only. An unpublished edit never appears; `showunpublished` is accepted and ignored.
- No pagination. The client expects the full tree for the indicators it asked for. There is no server-side cache; responses carry `Cache-Control: public, max-age=300`. Add a cache keyed on `(indicator set, year, don codes, zone)` if load requires it.
- A cell published twice for one society and year (for example two assignments sharing a period) resolves to the most recently published one.
- Unknown, private or empty code: that series is omitted.
- A missing or unknown key is `401`. A key without `content:read`, or one sent in the query string without the opt-in, is `403`.
- Up to 200 indicator codes per request; the rest are ignored.

## Cutover

1. Seed the society reference (`flask fdrs-societies import`) and check that no society is reported without a country.
2. On staging, point a copy of the frontend (option B) at the adapter.
3. Compare, for one year and `KPI_PeopleVol_Tot`, `KPI_IncomeLC_CHF`, one `_IP` map call, one age-band series, `globalvalidationdata`, and `supported1` for one society, the adapter JSON with a live `data-api.ifrc.org` response. Society ids, years, and values should match the published snapshot. Drift is expected where Backoffice has republished and the legacy API has not, or the reverse.
4. Cutover. With the passthrough on, send the whole `/api/*` and `/csv/*` surface to Backoffice (option A or B). Without it, send only the paths marked done above and keep documents, CSV, translations, embeds, offices and subscribe on the legacy upstream through a gateway.
5. After documents and CSV are served from Backoffice, retire the legacy data API for this site.

GO, Mapbox, YouTube, and Tableau do not move.
