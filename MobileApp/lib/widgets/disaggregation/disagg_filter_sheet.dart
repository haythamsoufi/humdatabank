import 'package:flutter/material.dart';

import '../../config/fdrs_constants.dart';
import '../../l10n/app_localizations.dart';
import '../../models/disaggregation/disaggregation_overview.dart';
import '../../utils/constants.dart';
import '../../widgets/home_landing/fdrs_world_map.dart';
import '../../widgets/sheets/native_modal_sheet.dart';

class DisaggFilterBar extends StatelessWidget {
  const DisaggFilterBar({
    super.key,
    required this.filters,
    required this.periods,
    required this.countries,
    required this.loc,
    required this.showCountryFilter,
    required this.onOpenFilters,
    required this.onClearFilters,
  });

  final DisaggregationFilters filters;
  final List<String> periods;
  final List<DisaggregationCountryOption> countries;
  final AppLocalizations loc;
  final bool showCountryFilter;
  final VoidCallback onOpenFilters;
  final VoidCallback onClearFilters;

  String _periodLabel() {
    if (filters.periodName == null || filters.periodName!.isEmpty) {
      return loc.disaggFilterAllPeriods;
    }
    return filters.periodName!;
  }

  String _countryLabel() {
    if (filters.countryId == null) return loc.disaggFilterAllCountries;
    for (final c in countries) {
      if (c.id == filters.countryId) return c.name;
    }
    return loc.disaggFilterAllCountries;
  }

  String _indicatorLabel() {
    return fdrsIndicatorTitle(loc, filters.indicatorBankId);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                ActionChip(
                  avatar: Icon(Icons.tune, size: 18, color: cs.primary),
                  label: Text(loc.disaggFilterButton),
                  onPressed: onOpenFilters,
                ),
                const SizedBox(width: 8),
                _FilterChip(label: _periodLabel(), icon: Icons.calendar_today),
                if (showCountryFilter) ...[
                  const SizedBox(width: 8),
                  _FilterChip(label: _countryLabel(), icon: Icons.public),
                ],
                const SizedBox(width: 8),
                _FilterChip(label: _indicatorLabel(), icon: Icons.show_chart),
              ],
            ),
          ),
          if (filters.hasActiveFiltersFor(
            countryDetailsAvailable: showCountryFilter,
          )) ...[
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                onPressed: onClearFilters,
                icon: const Icon(Icons.clear_all, size: 18),
                label: Text(loc.disaggFilterClear),
                style: TextButton.styleFrom(
                  foregroundColor: Color(AppConstants.ifrcRed),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _FilterChip extends StatelessWidget {
  const _FilterChip({required this.label, required this.icon});

  final String label;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    return Chip(
      avatar: Icon(icon, size: 16, color: cs.onSurfaceVariant),
      label: Text(
        label,
        overflow: TextOverflow.ellipsis,
      ),
      visualDensity: VisualDensity.compact,
    );
  }
}

Future<DisaggregationFilters?> showDisaggFilterSheet({
  required BuildContext context,
  required AppLocalizations loc,
  required ThemeData theme,
  required DisaggregationFilters initial,
  required List<String> periods,
  required List<DisaggregationCountryOption> countries,
  required bool showCountryFilter,
}) {
  return showModalBottomSheet<DisaggregationFilters>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    backgroundColor: Colors.transparent,
    builder: (ctx) => _DisaggFilterSheet(
      loc: loc,
      theme: theme,
      initial: initial,
      periods: periods,
      countries: countries,
      showCountryFilter: showCountryFilter,
    ),
  );
}

class _DisaggFilterSheet extends StatefulWidget {
  const _DisaggFilterSheet({
    required this.loc,
    required this.theme,
    required this.initial,
    required this.periods,
    required this.countries,
    required this.showCountryFilter,
  });

  final AppLocalizations loc;
  final ThemeData theme;
  final DisaggregationFilters initial;
  final List<String> periods;
  final List<DisaggregationCountryOption> countries;
  final bool showCountryFilter;

  @override
  State<_DisaggFilterSheet> createState() => _DisaggFilterSheetState();
}

class _DisaggFilterSheetState extends State<_DisaggFilterSheet> {
  late String? _period;
  late int? _countryId;
  late int _indicatorId;

  static const _indicatorOptions = [
    FdrsConstants.indicatorPeopleReached,
    FdrsConstants.indicatorVolunteers,
    FdrsConstants.indicatorStaff,
    FdrsConstants.indicatorLocalUnits,
    FdrsConstants.indicatorBloodDonors,
    FdrsConstants.indicatorFirstAid,
  ];

  @override
  void initState() {
    super.initState();
    _period = widget.initial.periodName;
    _countryId = widget.initial.countryId;
    _indicatorId = widget.initial.indicatorBankId;
  }

  @override
  Widget build(BuildContext context) {
    final loc = widget.loc;
    final theme = widget.theme;

    return NativeModalSheetScaffold(
      theme: theme,
      title: loc.disaggFilterTitle,
      closeTooltip: loc.close,
      onClose: () => Navigator.of(context).pop(),
      bodyExpands: false,
      maxHeightFraction: 0.88,
      child: ListView(
        shrinkWrap: true,
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
        children: [
          Text(
            loc.disaggFilterPeriod,
            style: theme.textTheme.titleSmall?.copyWith(
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              ChoiceChip(
                label: Text(loc.disaggFilterAllPeriods),
                selected: _period == null,
                onSelected: (_) => setState(() => _period = null),
              ),
              for (final p in widget.periods)
                ChoiceChip(
                  label: Text(p),
                  selected: _period == p,
                  onSelected: (_) => setState(() => _period = p),
                ),
            ],
          ),
          if (widget.showCountryFilter) ...[
            const SizedBox(height: 20),
            Text(
              loc.disaggFilterCountry,
              style: theme.textTheme.titleSmall?.copyWith(
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            DropdownButtonFormField<int?>(
              key: ValueKey<int?>(_countryId),
              initialValue: _countryId,
              decoration: InputDecoration(
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                isDense: true,
              ),
              items: [
                DropdownMenuItem<int?>(
                  value: null,
                  child: Text(loc.disaggFilterAllCountries),
                ),
                for (final c in widget.countries)
                  DropdownMenuItem<int?>(
                    value: c.id,
                    child: Text(c.name, overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged: (v) => setState(() => _countryId = v),
            ),
          ],
          const SizedBox(height: 20),
          Text(
            loc.disaggFilterIndicator,
            style: theme.textTheme.titleSmall?.copyWith(
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          DropdownButtonFormField<int>(
            key: ValueKey<int>(_indicatorId),
            initialValue: _indicatorId,
            decoration: InputDecoration(
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
              isDense: true,
            ),
            items: [
              for (final id in _indicatorOptions)
                DropdownMenuItem<int>(
                  value: id,
                  child: Text(
                    fdrsIndicatorTitle(loc, id),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
            ],
            onChanged: (v) {
              if (v != null) setState(() => _indicatorId = v);
            },
          ),
          const SizedBox(height: 24),
          FilledButton(
            onPressed: () {
              Navigator.of(context).pop(
                DisaggregationFilters(
                  periodName: _period,
                  countryId: widget.showCountryFilter ? _countryId : null,
                  indicatorBankId: _indicatorId,
                ),
              );
            },
            style: FilledButton.styleFrom(
              minimumSize: const Size.fromHeight(48),
              backgroundColor: Color(AppConstants.ifrcRed),
            ),
            child: Text(loc.disaggFilterApply),
          ),
        ],
      ),
    );
  }
}
