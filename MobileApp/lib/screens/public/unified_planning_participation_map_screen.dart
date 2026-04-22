import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../../l10n/app_localizations.dart';
import '../../models/shared/unified_planning_document.dart';
import '../../services/ifrc_unified_planning_service.dart';
import '../../services/unified_planning_analytics_filter_cache.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/home_landing/fdrs_world_map.dart';
import '../../widgets/home_landing/world_geojson_cache.dart';

/// Choropleth of how many filtered year + document-type combinations each
/// country has published.
class UnifiedPlanningParticipationMapScreen extends StatefulWidget {
  const UnifiedPlanningParticipationMapScreen({
    super.key,
    required this.documents,
    required this.initialCriteria,
  });

  final List<UnifiedPlanningDocument> documents;
  final UnifiedPlanningAnalyticsFilterCriteria initialCriteria;

  @override
  State<UnifiedPlanningParticipationMapScreen> createState() =>
      _UnifiedPlanningParticipationMapScreenState();
}

class _UnifiedPlanningParticipationMapScreenState
    extends State<UnifiedPlanningParticipationMapScreen> {
  static const Map<String, String> _iso3Overrides = {'OSA': 'XK'};

  late UnifiedPlanningAnalyticsFilterCriteria _criteria;
  Map<String, String> _iso3ToIso2 = {};
  bool _geoReady = false;

  @override
  void initState() {
    super.initState();
    _criteria = widget.initialCriteria;
    _loadAssets();
  }

  Future<void> _loadAssets() async {
    final isoRaw = await rootBundle.loadString('assets/data/iso3_to_iso2.json');
    final isoDecoded = jsonDecode(isoRaw);
    final isoMap = <String, String>{};
    if (isoDecoded is Map<String, dynamic>) {
      isoDecoded.forEach((k, v) {
        if (k.toString().isNotEmpty && v != null) {
          isoMap[k.toString().toUpperCase()] = v.toString().toUpperCase();
        }
      });
    }
    await WorldGeoJsonCache.instance.ensureLoaded();
    if (!mounted) return;
    setState(() {
      _iso3ToIso2 = {...isoMap, ..._iso3Overrides};
      _geoReady = true;
    });
  }

  String? _resolveIso2(String? raw) {
    if (raw == null) return null;
    final u = raw.trim().toUpperCase();
    if (u.isEmpty) return null;
    if (u.length == 2) return u;
    if (u.length == 3) return _iso3ToIso2[u];
    return null;
  }

  List<UnifiedPlanningDocument> _uniqueDocs(
    List<UnifiedPlanningDocument> docs,
  ) {
    final seen = <String>{};
    final out = <UnifiedPlanningDocument>[];
    for (final d in docs) {
      if (seen.add(
        IfrcUnifiedPlanningService.unifiedPlanningListDedupeKey(d.url),
      )) {
        out.add(d);
      }
    }
    return out;
  }

  _ParticipationModel _computeModel(AppLocalizations loc) {
    final unique = _uniqueDocs(widget.documents);
    final filtered = unique.where(_criteria.matches).toList(growable: false);
    final expectedKeys = <String>{};
    final byIso = <String, Set<String>>{};
    final nameByIso = <String, String>{};
    final unmappedCountries = <String>{};

    for (final d in filtered) {
      final tk = UnifiedPlanningDocument.typeKey(d);
      final key = _slotKey(d.year, tk);
      expectedKeys.add(key);
    }

    for (final d in filtered) {
      final tk = UnifiedPlanningDocument.typeKey(d);
      final slot = _slotKey(d.year, tk);
      final iso = _resolveIso2(d.countryCode);
      if (iso != null) {
        byIso.putIfAbsent(iso, () => <String>{}).add(slot);
        nameByIso[iso] = (d.countryName?.trim().isNotEmpty ?? false)
            ? d.countryName!.trim()
            : iso;
      } else {
        final idKey = UnifiedPlanningDocument.countryIdentityKey(d);
        if (idKey != null) unmappedCountries.add(idKey);
      }
    }

    final expectedCount = expectedKeys.length;
    final valueByIso = <String, double>{};
    var full = 0;
    var partial = 0;

    for (final e in byIso.entries) {
      if (expectedCount <= 0) break;
      final covered = e.value
          .where(expectedKeys.contains)
          .length; // intersection size
      valueByIso[e.key] = covered.toDouble();
      if (covered >= expectedCount) {
        full++;
      } else if (covered > 0) {
        partial++;
      }
    }

    return _ParticipationModel(
      expectedSlotCount: expectedCount,
      expectedLabel: expectedCount > 0
          ? loc.unifiedPlanningParticipationSlotsLabel('$expectedCount')
          : loc.unifiedPlanningParticipationNoSlots,
      valueByIso2Upper: valueByIso,
      maxValue: expectedCount > 0 ? expectedCount.toDouble() : 1,
      fullCountries: full,
      partialCountries: partial,
      unmappedCountryCount: unmappedCountries.length,
      nameByIso2Upper: nameByIso,
      expectedKeys: expectedKeys,
      byIsoSlots: byIso,
    );
  }

  static String _slotKey(int? year, String typeKey) =>
      '${year ?? -999999}\x1f$typeKey';

  void _openFilterSheet(
    BuildContext context,
    AppLocalizations loc,
    ThemeData theme,
  ) {
    final all = widget.documents;
    final years = all.map((e) => e.year).whereType<int>().toSet().toList()
      ..sort((a, b) => b.compareTo(a));
    final hasUnknown = all.any((e) => e.year == null);
    final typeKeys = all.map(UnifiedPlanningDocument.typeKey).toSet().toList()
      ..sort((a, b) => a.toLowerCase().compareTo(b.toLowerCase()));

    final screenH = MediaQuery.sizeOf(context).height;
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: true,
      constraints: BoxConstraints(
        maxWidth: MediaQuery.sizeOf(context).width,
        maxHeight: screenH * 0.88,
      ),
      builder: (ctx) => _ParticipationMapFilterSheet(
        loc: loc,
        theme: theme,
        initial: _criteria,
        yearOptions: years,
        hasUnknownYear: hasUnknown,
        typeKeys: typeKeys,
        onApply: (next) {
          Navigator.of(ctx).pop();
          setState(() => _criteria = next);
        },
      ),
    );
  }

  void _onCountryTap(
    BuildContext context, {
    required AppLocalizations loc,
    required ThemeData theme,
    required _ParticipationModel model,
    required String iso2,
  }) {
    final name = model.nameByIso2Upper[iso2] ?? iso2;
    final slots = model.byIsoSlots[iso2];
    final expected = model.expectedSlotCount;
    final covered = slots == null
        ? 0
        : slots.where(model.expectedKeys.contains).length;
    String status;
    if (expected <= 0) {
      status = loc.unifiedPlanningParticipationSheetNone;
    } else if (covered >= expected) {
      status = loc.unifiedPlanningParticipationSheetFull;
    } else if (covered > 0) {
      status = loc.unifiedPlanningParticipationSheetPartial;
    } else {
      status = loc.unifiedPlanningParticipationSheetNone;
    }

    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: theme.colorScheme.surface,
      builder: (ctx) {
        return Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                name,
                style: theme.textTheme.titleLarge?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                iso2,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 16),
              Text(
                loc.unifiedPlanningParticipationSheetSlots(
                  '$covered',
                  '$expected',
                ),
                style: theme.textTheme.bodyLarge?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                status,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.primary,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final bottomPad = MediaQuery.viewPaddingOf(context).bottom;

    if (!_geoReady) {
      return Scaffold(
        appBar: AppAppBar(
          title: loc.unifiedPlanningParticipationMapTitle,
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_rounded),
            onPressed: () => Navigator.of(context).pop(),
            tooltip: MaterialLocalizations.of(context).backButtonTooltip,
          ),
          automaticallyImplyLeading: false,
        ),
        body: Center(
          child: CircularProgressIndicator(color: theme.colorScheme.primary),
        ),
      );
    }

    final model = _computeModel(loc);
    final isDark = theme.brightness == Brightness.dark;
    final border = theme.colorScheme.outlineVariant.withValues(
      alpha: isDark ? 0.45 : 0.35,
    );
    final noData = theme.colorScheme.surfaceContainerHighest.withValues(
      alpha: isDark ? 0.35 : 0.5,
    );
    final fillFull = isDark
        ? const Color(AppConstants.semanticSuccessOnDarkSoft)
        : const Color(AppConstants.semanticSuccessOnLightStrong);
    final fillPartial = isDark
        ? const Color(AppConstants.semanticNotificationOrangeDarkUnread)
        : const Color(AppConstants.semanticNotificationOrangeTextStrongLight);

    final polys = _discreteParticipationPolygons(
      model: model,
      fillNoData: noData,
      fillFull: fillFull,
      fillPartial: fillPartial,
      borderColor: border,
    );

    final worldBounds = LatLngBounds(
      const LatLng(-85, -180),
      const LatLng(85, 180),
    );
    final initialFit = CameraFit.bounds(
      bounds: worldBounds,
      padding: const EdgeInsets.fromLTRB(8, 8, 8, 8),
      maxZoom: 4.2,
    );

    final statsLine = loc.unifiedPlanningParticipationStats(
      model.fullCountries,
      model.partialCountries,
      model.unmappedCountryCount,
    );

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: loc.unifiedPlanningParticipationMapTitle,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded),
          onPressed: () => Navigator.of(context).pop(),
          tooltip: MaterialLocalizations.of(context).backButtonTooltip,
        ),
        automaticallyImplyLeading: false,
        actions: [
          IconButton(
            tooltip: loc.unifiedPlanningAnalyticsFiltersTooltip,
            onPressed: () => _openFilterSheet(context, loc, theme),
            icon: Badge(
              isLabelVisible: _criteria.isRestricted,
              smallSize: 7,
              backgroundColor: theme.colorScheme.primary,
              child: const Icon(Icons.tune_rounded),
            ),
          ),
        ],
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 10, 16, 6),
            child: Row(
              children: [
                Icon(
                  Icons.filter_alt_outlined,
                  size: 18,
                  color: theme.colorScheme.primary,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    model.expectedLabel,
                    style: theme.textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w700,
                      color: context.textColor,
                    ),
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Text(
              statsLine,
              style: theme.textTheme.labelMedium?.copyWith(
                color: context.textSecondaryColor,
              ),
            ),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  border: Border.all(
                    color: theme.colorScheme.outlineVariant.withValues(
                      alpha: isDark ? 0.55 : 0.4,
                    ),
                  ),
                ),
                child: ClipRect(
                  child: FdrsOverviewMap(
                    theme: theme,
                    visualMode: FdrsMapVisualMode.choropleth,
                    circles: const [],
                    choroplethPolygons: polys,
                    initialFit: initialFit,
                    maxZoom: 22,
                    polygonSimplification: 0,
                    onCountryIso2Tapped: (iso2) => _onCountryTap(
                      context,
                      loc: loc,
                      theme: theme,
                      model: model,
                      iso2: iso2,
                    ),
                  ),
                ),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 10, 16, 8),
            child: _ParticipationMapLegend(
              theme: theme,
              fullColor: fillFull,
              partialColor: fillPartial,
              noDataColor: noData,
              fullLabel: loc.unifiedPlanningParticipationLegendFull,
              partialLabel: loc.unifiedPlanningParticipationLegendPartial,
              noDataLabel: loc.unifiedPlanningParticipationLegendNoData,
            ),
          ),
          SizedBox(height: bottomPad > 0 ? bottomPad : 8),
        ],
      ),
    );
  }
}

class _ParticipationModel {
  _ParticipationModel({
    required this.expectedSlotCount,
    required this.expectedLabel,
    required this.valueByIso2Upper,
    required this.maxValue,
    required this.fullCountries,
    required this.partialCountries,
    required this.unmappedCountryCount,
    required this.nameByIso2Upper,
    required this.expectedKeys,
    required this.byIsoSlots,
  });

  final int expectedSlotCount;
  final String expectedLabel;
  final Map<String, double> valueByIso2Upper;
  final double maxValue;
  final int fullCountries;
  final int partialCountries;
  final int unmappedCountryCount;
  final Map<String, String> nameByIso2Upper;
  final Set<String> expectedKeys;
  final Map<String, Set<String>> byIsoSlots;
}

List<Polygon<String>> _discreteParticipationPolygons({
  required _ParticipationModel model,
  required Color fillNoData,
  required Color fillFull,
  required Color fillPartial,
  required Color borderColor,
  double borderStrokeWidth = 0.5,
}) {
  final expected = model.expectedSlotCount;
  final polys = <Polygon<String>>[];
  for (final s in WorldGeoJsonCache.instance.shells) {
    final v = model.valueByIso2Upper[s.iso2];
    final Color fill;
    if (expected <= 0 || v == null || v <= 0) {
      fill = fillNoData;
    } else if (v >= expected) {
      fill = fillFull;
    } else {
      fill = fillPartial;
    }
    polys.add(
      Polygon<String>(
        points: s.outer,
        holePointsList: s.holes.isEmpty ? null : s.holes,
        color: fill,
        borderStrokeWidth: borderStrokeWidth,
        borderColor: borderColor,
        hitValue: s.iso2,
      ),
    );
  }
  return polys;
}

class _ParticipationMapLegend extends StatelessWidget {
  const _ParticipationMapLegend({
    required this.theme,
    required this.fullColor,
    required this.partialColor,
    required this.noDataColor,
    required this.fullLabel,
    required this.partialLabel,
    required this.noDataLabel,
  });

  final ThemeData theme;
  final Color fullColor;
  final Color partialColor;
  final Color noDataColor;
  final String fullLabel;
  final String partialLabel;
  final String noDataLabel;

  @override
  Widget build(BuildContext context) {
    final isDark = theme.brightness == Brightness.dark;
    final border = theme.colorScheme.outlineVariant.withValues(
      alpha: isDark ? 0.55 : 0.4,
    );
    return Material(
      color: theme.colorScheme.surface.withValues(alpha: 0.92),
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(side: BorderSide(color: border)),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        child: Wrap(
          spacing: 16,
          runSpacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            _legendItem(color: fullColor, label: fullLabel, border: border),
            _legendItem(
              color: partialColor,
              label: partialLabel,
              border: border,
            ),
            _legendItem(color: noDataColor, label: noDataLabel, border: border),
          ],
        ),
      ),
    );
  }

  Widget _legendItem({
    required Color color,
    required String label,
    required Color border,
  }) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 14,
          height: 14,
          decoration: BoxDecoration(
            color: color,
            border: Border.all(color: border, width: 0.5),
          ),
        ),
        const SizedBox(width: 6),
        Text(
          label,
          style: theme.textTheme.labelSmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      ],
    );
  }
}

class _ParticipationMapFilterSheet extends StatefulWidget {
  const _ParticipationMapFilterSheet({
    required this.loc,
    required this.theme,
    required this.initial,
    required this.yearOptions,
    required this.hasUnknownYear,
    required this.typeKeys,
    required this.onApply,
  });

  final AppLocalizations loc;
  final ThemeData theme;
  final UnifiedPlanningAnalyticsFilterCriteria initial;
  final List<int> yearOptions;
  final bool hasUnknownYear;
  final List<String> typeKeys;
  final void Function(UnifiedPlanningAnalyticsFilterCriteria criteria) onApply;

  @override
  State<_ParticipationMapFilterSheet> createState() =>
      _ParticipationMapFilterSheetState();
}

class _ParticipationMapFilterSheetState
    extends State<_ParticipationMapFilterSheet> {
  late _AnalyticsFilterDraft _draft;

  @override
  void initState() {
    super.initState();
    _draft = _AnalyticsFilterDraft.fromCriteria(widget.initial);
  }

  String _typeLabel(String key) => key == '__type_unknown__'
      ? widget.loc.unifiedPlanningAnalyticsUnknownType
      : key;

  @override
  Widget build(BuildContext context) {
    final loc = widget.loc;
    final theme = widget.theme;
    final bottomInset = MediaQuery.viewPaddingOf(context).bottom;
    final screenH = MediaQuery.sizeOf(context).height;
    final scrollMax = (screenH * 0.5).clamp(200.0, 400.0);

    return Padding(
      padding: EdgeInsets.only(
        left: 16,
        right: 16,
        top: 12,
        bottom: 12 + bottomInset,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  loc.unifiedPlanningAnalyticsFiltersTitle,
                  style: theme.textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.w700,
                    color: context.textColor,
                  ),
                ),
              ),
              TextButton(
                onPressed: () {
                  setState(() {
                    _draft = _AnalyticsFilterDraft.fromCriteria(
                      UnifiedPlanningAnalyticsFilterCriteria.inclusive,
                    );
                  });
                },
                child: Text(loc.unifiedPlanningAnalyticsFilterReset),
              ),
            ],
          ),
          const SizedBox(height: 8),
          ConstrainedBox(
            constraints: BoxConstraints(maxHeight: scrollMax),
            child: ListView(
              shrinkWrap: true,
              physics: const ClampingScrollPhysics(),
              children: [
                Text(
                  loc.unifiedPlanningAnalyticsFilterYears,
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: context.textColor,
                  ),
                ),
                const SizedBox(height: 10),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    FilterChip(
                      label: Text(loc.unifiedPlanningAnalyticsFilterAllYears),
                      selected: _draft.allYears,
                      onSelected: (_) => setState(() {
                        _draft.allYears = true;
                        _draft.years.clear();
                        _draft.includeUnknownYear = true;
                      }),
                    ),
                    if (widget.hasUnknownYear)
                      FilterChip(
                        label: Text(loc.unifiedPlanningAnalyticsUnknownYear),
                        selected: !_draft.allYears && _draft.includeUnknownYear,
                        onSelected: (sel) => setState(() {
                          _draft.allYears = false;
                          _draft.includeUnknownYear = sel;
                        }),
                      ),
                    for (final y in widget.yearOptions)
                      FilterChip(
                        label: Text('$y'),
                        selected: !_draft.allYears && _draft.years.contains(y),
                        onSelected: (sel) => setState(() {
                          _draft.allYears = false;
                          if (sel) {
                            _draft.years.add(y);
                          } else {
                            _draft.years.remove(y);
                          }
                        }),
                      ),
                  ],
                ),
                const SizedBox(height: 22),
                Text(
                  loc.unifiedPlanningAnalyticsFilterRounds,
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: context.textColor,
                  ),
                ),
                const SizedBox(height: 10),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    FilterChip(
                      label: Text(loc.unifiedPlanningAnalyticsFilterAllRounds),
                      selected: _draft.allTypes,
                      onSelected: (_) => setState(() {
                        _draft.allTypes = true;
                        _draft.typeKeys.clear();
                      }),
                    ),
                    for (final tk in widget.typeKeys)
                      FilterChip(
                        label: Text(_typeLabel(tk)),
                        selected:
                            !_draft.allTypes && _draft.typeKeys.contains(tk),
                        onSelected: (sel) => setState(() {
                          _draft.allTypes = false;
                          if (sel) {
                            _draft.typeKeys.add(tk);
                          } else {
                            _draft.typeKeys.remove(tk);
                          }
                        }),
                      ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: () {
              if (!_draft.validate()) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text(loc.unifiedPlanningAnalyticsFilterInvalid),
                  ),
                );
                return;
              }
              widget.onApply(_draft.seal());
            },
            child: Text(loc.unifiedPlanningAnalyticsFilterApply),
          ),
        ],
      ),
    );
  }
}

/// Local duplicate of analytics filter draft (same shape as main analytics screen).
class _AnalyticsFilterDraft {
  _AnalyticsFilterDraft.fromCriteria(UnifiedPlanningAnalyticsFilterCriteria c)
    : allYears = c.allYears,
      years = Set<int>.from(c.years),
      includeUnknownYear = c.includeUnknownYear,
      allTypes = c.allTypes,
      typeKeys = Set<String>.from(c.typeKeys);

  bool allYears;
  Set<int> years;
  bool includeUnknownYear;
  bool allTypes;
  Set<String> typeKeys;

  UnifiedPlanningAnalyticsFilterCriteria seal() {
    return UnifiedPlanningAnalyticsFilterCriteria(
      allYears: allYears,
      years: Set<int>.from(years),
      includeUnknownYear: includeUnknownYear,
      allTypes: allTypes,
      typeKeys: Set<String>.from(typeKeys),
    );
  }

  bool validate() {
    if (!allYears) {
      if (years.isEmpty && !includeUnknownYear) return false;
    }
    if (!allTypes && typeKeys.isEmpty) return false;
    return true;
  }
}
