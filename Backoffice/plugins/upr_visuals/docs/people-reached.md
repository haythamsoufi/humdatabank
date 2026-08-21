# People reached — temporary Cross-cutting override

**Status:** temporary (2026-08-21)  
**Scope:** UPR visuals **People reached** dashboard only (report template 33).  
**Default (Tableau) behaviour:** one category per Strategic Priority, plus Cross-cutting (`CC1`) and Emergency Operations (`EO`). Each category shows the **highest** people-count indicator (`unit=People`, `type=Number`).

This file is the place to change or revert the override. Do not hunt through comments in `data.py` first.

## Current override

Cross-cutting is **hidden** on People reached. Its two T33 core indicators are handled as follows:

| Indicator | Bank id | Form section | People reached treatment |
|---|---|---|---|
| Number of people reached with emergency response and early recovery programmes. | `619` | Cross Cutting | Count under **Disasters and crises** (`SP2`). Included in that category’s max. |
| Number of people reached with long-term services and programmes. | — | Cross Cutting | **Dropped** (value unused). |

Other SP / EO categories are unchanged: still the highest people-count indicator in that area.

Cross-cutting is **not** removed from the rest of the plugin. Section mapping, core-indicator bars, colours, and labels still know about `CC1`.

## Where the knobs live

All of these are in [`catalog.py`](../catalog.py):

| Constant | Current value | Role |
|---|---|---|
| `REACH_CODES` | `("EO", *SP_CODES)` | Categories drawn on People reached. `CC1` is omitted so the column disappears. |
| `REACH_EMERGENCY_TO_SP2_NEEDLES` | `"emergency response and early recovery"` | Name match → remap to `SP2`. |
| `REACH_EMERGENCY_BANK_ID` | `619` | Same remap if the indicator bank id matches (label-independent). |
| `REACH_DROP_LONG_TERM_NEEDLES` | `"long-term services and programmes"` (plus hyphen/spacing variants) | Name match → exclude from the visual. |

The remapper is `override_people_reached_area()` in [`data.py`](../data.py). `_report_people_reached()` calls it for static form items and dynamic “Other Indicators” rows **before** `max_people_by_area()`.

`REACH_CODES` also drives `_reach_rows()` / `max_people_by_area()`, so leftover `CC1` candidates never appear as a category.

## How to change it later

### Restore Tableau-faithful People reached (undo this override)

1. In `catalog.py`, set `REACH_CODES = ("EO", "CC1", *SP_CODES)`.
2. In `data.py`, stop calling `override_people_reached_area()` from `_report_people_reached()` (use `_area_from_item()` / `_bank_area()` only). You can delete the helper and the `REACH_*` needle constants once unused.
3. Restore tests that expected a Cross-cutting column:
   - `test_max_people_by_area_keeps_highest_per_sp_and_ignores_cross_cutting`
   - `test_override_people_reached_area_moves_emergency_and_drops_long_term`
   - `test_report_people_reached_folds_emergency_into_disasters_and_drops_long_term`
   - `test_period_to_round` (`CC1` in `REACH_CODES`)
   - render fixtures in `test_formatters_render.py` that dropped the Cross-cutting chip
4. Restore `_report_people_reached`’s docstring to mention Cross-cutting again.
5. Mark this file obsolete or delete it.

### Keep Cross-cutting hidden, but use the long-term indicator

Remove or narrow `REACH_DROP_LONG_TERM_NEEDLES`, then either:

- remap that indicator to an existing `REACH_CODES` area (same pattern as emergency → `SP2`), or
- put `CC1` back into `REACH_CODES` if you want the category itself again.

### Move emergency-response reach somewhere other than SP2

Change the return value in `override_people_reached_area()` (today hard-coded to `"SP2"`) and the tests that assert Disasters and crises.

### Add another remapped / dropped indicator

Prefer a new needle (or bank id) on the catalog constants. Keep the override in `override_people_reached_area()` so Strategic Priorities / Enabling Functions bars are not affected.

## Tests

```text
pytest plugins/upr_visuals/tests/test_data_helpers.py plugins/upr_visuals/tests/test_formatters_render.py --no-cov
```

Key cases: remapper moves emergency → `SP2` and drops long-term; report payload has no `CC1` and SP2 is `max(existing SP2, emergency)`; render fixtures do not show “Cross-cutting”.

## Related

- [`snapshots/README.md`](../snapshots/README.md) — separate temporary overlay (IFRC Secretariat finance actuals for MYR26)
- Form guidance still lists both indicators under Cross Cutting: [`Backoffice/docs/data-reporting/data-guidance-upr.md`](../../../docs/data-reporting/data-guidance-upr.md)
