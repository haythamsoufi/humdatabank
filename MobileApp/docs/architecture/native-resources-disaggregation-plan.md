# Plan: Native Resources & Disaggregation Analysis Screens (Flutter)

This document outlines how to replace the current **WebView-based** public flows (`ResourcesScreen`, `DisaggregationAnalysisScreen`) with **first-party Flutter UI**, reusing patterns established on the **home landing** work (hero/slideshow, glass AI card, FDRS explore section, l10n, theming, and asset discipline).

## Current state

| Screen | File | Implementation |
|--------|------|----------------|
| Resources | `lib/screens/public/resources_screen.dart` | `InAppWebView` → `UrlHelper.buildFrontendUrlWithLanguage('/resources', …)` + session injection, pull-to-refresh, tab vs standalone chrome |
| Disaggregation analysis | `lib/screens/public/disaggregation_analysis_screen.dart` | Same pattern for `/disaggregation-analysis` |

**Website parity (reference implementation):**

- **Resources:** `Website/pages/resources.js` — `getResources(page, perPage, search, type, locale)` for `publication` and `other`, pagination, search, expandable cards.
- **Disaggregation:** `Website/pages/disaggregation-analysis.js` — `getDataWithRelated`, `getFilterOptions`, `processDisaggregatedData`, `getCountriesList`, `MultiChart`, CSV/PNG export, heavy filter/chart state.

The mobile app already has a **`Resource`** model (`lib/models/shared/resource.dart`) aligned with JSON fields from the web API shape; disaggregation will need new models and a service layer.

---

## Lessons from home landing work (apply here)

1. **Composition over monoliths**  
   Split UI into focused widgets under something like `lib/widgets/resources/` and `lib/widgets/disaggregation/` (lists, filters, detail sheets, chart panels) rather than one huge screen file—same idea as `home_landing/` (`LandingHeroSliver`, `LandingGetStartedSection`, etc.).

2. **Slivers + scrolling**  
   Use `CustomScrollView` + slivers for long lists with optional sticky headers (section titles, filter chips), mirroring the home screen’s scroll model and avoiding nested scroll conflicts.

3. **Theme & design system**  
   Prefer `ColorScheme` (`secondary` for IFRC red accent, `surfaceContainerHigh`, `onSurfaceVariant`) and shared title rail patterns (`_LandingSectionTitle`-style row with accent bar) so Resources/Disagg feel consistent with **Get started** / home.

4. **Localization**  
   Add strings to ARB files, run codegen—no hard-coded copy. Mirror web keys where it helps content editors (`resources.*`, `disaggregationAnalysis.*` on web → parallel `AppLocalizations` entries).

5. **Images & assets**  
   Any bundled imagery (thumbnails fallbacks, onboarding hints) must be **listed in `pubspec.yaml`** (explicit paths for critical assets) and **committed**; missing files + `Image.asset` `errorBuilder` → invisible UI (hero slideshow lesson).

6. **Dense controls**  
   Avoid default `IconButton` / suffix constraints that fight `isDense` fields; use explicit `Material` + `InkWell` + `suffixIconConstraints` where needed (AI entry card lesson).

7. **Loading / error / empty**  
   Reuse patterns from `LandingGetStartedSection` + `_ErrorBlock`: `FutureBuilder`, retry, and clear empty states—not only spinners.

8. **Keep-alive & navigation**  
   Preserve `AutomaticKeepAliveClientMixin` where screens are tabs; keep **standalone vs tab** detection logic or replace with a single shell that receives a `bool embedded` argument to avoid duplicating AppBar/bottom bar behavior.

9. **Optional WebView escape hatch**  
   Until parity is complete, a “View full site” overflow action that opens the existing frontend URL (or in-app WebView) reduces risk for edge cases.

---

## Phase A — Resources (native)

**Goal:** List and open publications / other resources with search and pagination, without embedding the Next.js page.

### A.1 API & service

- Trace `getResources` in `Website/lib/apiService.js` (path, query params, auth expectations).
- Add `ResourcesApiService` (or extend `ApiService`) in MobileApp:  
  `Future<ResourcesPageResult> getResources({ required int page, int perPage, String? search, required String type, required String language })`.
- Map JSON → existing `Resource` model; add pagination fields (`total_pages`, `current_page`, etc.) in a small DTO.

### A.2 State

- `ResourcesProvider` or screen-local `Future`/notifier with:
  - separate loading for publications vs other (or unified with tab index),
  - search debounce (~300 ms),
  - pagination (infinite scroll or “Load more”).

### A.3 UI structure

- **App bar:** title, search (collapsible or dedicated field), optional language refresh on `LanguageProvider` change.
- **Body:** two sections (or `TabBar` / segmented control): **Publications** | **Other resources**—match web semantics.
- **List item:** card with thumbnail (`cached_network_image` if URL), title, type, date, chevron; tap → detail.
- **Detail:** full-screen route or bottom sheet: description, metadata, **open file / external link** via `url_launcher`, share sheet if useful.
- **Accessibility:** semantic labels, sufficient contrast on cards (light/dark).

### A.4 Routing & cutover

- Keep route name `AppRoutes.resources`.
- Replace `ResourcesScreen` body WebView with native scaffold; retain any drawer/FAB hooks the current screen exposes.
- Remove or gate WebView-only code paths once stable.

### A.5 QA checklist

- [ ] Anonymous vs authenticated (if API differs).
- [ ] All supported app languages.
- [ ] Empty list, API error, slow network, pagination boundary.
- [ ] Large thumbnails / broken image URLs.

---

## Phase B — Disaggregation analysis (native)

**Goal:** Mobile-appropriate analytics: filters → summarized metrics + charts, **not** a pixel-perfect port of the entire web dashboard on day one.

### B.1 Scope trimming (recommended)

The web page is very large (filters, many chart types, export, tooltips). Ship **incrementally**:

1. **MVP:** Country (and/or template) selection, year/period filters, one primary chart (e.g. breakdown by sex or age) + key figures card—backed by the same APIs the web uses.
2. **v2:** Additional breakdowns, second chart type, CSV export.
3. **v3:** PNG export, advanced tooltips, parity with web-only features as needed.

Document accepted gaps vs web in release notes.

### B.2 API & service

- Map `getDataWithRelated`, `getFilterOptions`, `getCountriesList`, and `processDisaggregatedData` (or equivalent server responses) from `Website/lib/apiService.js`.
- Implement `DisaggregationApiService` with typed responses; avoid duplicating heavy client-side “process” logic in Dart if the backend can return chart-ready series—otherwise port `processDisaggregatedData` carefully with tests.

### B.3 UI structure

- **Filter strip:** chips / bottom sheet for country, indicator/template, year—optimized for thumb reach.
- **Summary:** cards for totals (reuse typography from home explore section).
- **Charts:** `fl_chart` is already a dependency (also used in AI structured views); keep bar/line/pie widgets small and test on small phones.
- **Export:** CSV via `share_plus` or write to temp file + share; defer PNG until stable.

### B.4 Performance

- Debounce filter changes; cancel in-flight HTTP when a new filter is applied.
- Consider `RepaintBoundary` around charts if jank appears when scrolling.

### B.5 Routing & cutover

- Keep `AppRoutes.disaggregationAnalysis`; swap WebView for native shell.
- Same standalone/tab behavior as resources.

### B.6 QA checklist

- [ ] FDRS template / country combinations that return empty vs rich data.
- [ ] Locale and number formatting (`intl`) for axis labels.
- [ ] Dark mode chart colors (not only light `MultiChart` colors).

---

## Phase C — Shared infrastructure

- **Auth:** Reuse session/token rules from existing `ApiService` / `AuthProvider`; align with how the website calls public vs protected endpoints.
- **Config:** Base URL from `AppConfig` / env—no hard-coded hosts.
- **Telemetry:** Optional Sentry breadcrumbs for API failures (already in project).
- **Documentation:** Short `MobileApp/docs/...` note on which API routes each screen uses (update when Backoffice/Website changes).

---

## Suggested file layout (incremental)

```
lib/
  screens/public/
    resources_screen.dart          # thin shell: Provider + scaffold
    disaggregation_analysis_screen.dart
  widgets/resources/
    resources_list_section.dart
    resource_detail_sheet.dart
    ...
  widgets/disaggregation/
    disagg_filter_sheet.dart
    disagg_summary_cards.dart
    disagg_chart_panel.dart
  services/
    resources_api_service.dart
    disaggregation_api_service.dart
  providers/public/
    resources_provider.dart
    disaggregation_provider.dart   # optional
```

---

## Risk summary

| Risk | Mitigation |
|------|------------|
| API undocumented / drifts from web | Treat `Website/lib/apiService.js` as source of truth; add integration tests or manual contract checklist |
| Disagg scope creep | Time-box MVP; ship WebView fallback link |
| Chart package limits vs web | Accept simplified visuals; prioritize correctness and readability |
| Binary assets forgotten in git | Explicit `pubspec` entries + CI asset smoke test optional |

---

## Order of execution

1. **Resources native** (smaller surface, reuses `Resource` model).  
2. **Disaggregation MVP** (filters + one chart + summary).  
3. Expand disagg + remove WebView fallbacks when stakeholders sign off.

This sequence delivers user-visible value early and validates API usage before committing to full disaggregation parity.
