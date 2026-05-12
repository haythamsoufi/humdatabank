import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../di/service_locator.dart';
import '../../l10n/app_localizations.dart';
import '../../models/shared/unified_planning_document.dart';
import '../../providers/public/public_resources_provider.dart';
import '../../services/ifrc_unified_planning_service.dart';
import '../../services/storage_service.dart';
import '../../services/unified_planning_analytics_filter_cache.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/app_bar.dart';
import 'unified_planning_participation_map_screen.dart';

/// Dashboard aggregating IFRC unified planning documents, with document types
/// grouped under each calendar year.
class UnifiedPlanningAnalyticsScreen extends StatefulWidget {
  const UnifiedPlanningAnalyticsScreen({super.key});

  @override
  State<UnifiedPlanningAnalyticsScreen> createState() =>
      _UnifiedPlanningAnalyticsScreenState();
}

class _UnifiedPlanningAnalyticsScreenState
    extends State<UnifiedPlanningAnalyticsScreen> {
  final UnifiedPlanningAnalyticsFilterCache _filterCache =
      UnifiedPlanningAnalyticsFilterCache(sl<StorageService>());

  UnifiedPlanningAnalyticsFilterCriteria _criteria =
      UnifiedPlanningAnalyticsFilterCriteria.inclusive;

  List<UnifiedPlanningDocument>? _lastDocsForReconcile;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      final loaded = await _filterCache.load();
      if (!mounted) return;
      final p = context.read<PublicResourcesProvider>();
      final docs = p.unifiedPlanningDocuments;
      final next = docs.isEmpty ? loaded : loaded.reconcileWithDocuments(docs);
      setState(() => _criteria = next);
      if (docs.isNotEmpty &&
          jsonEncode(next.toJson()) != jsonEncode(loaded.toJson())) {
        await _filterCache.save(next);
      }
      if (!mounted) return;
      if (p.unifiedPlanningDocuments.isEmpty && !p.unifiedPlanningLoading) {
        p.loadUnifiedPlanningDocuments();
      }
    });
  }

  void _scheduleReconcileIfNeeded(List<UnifiedPlanningDocument> docs) {
    if (docs.isEmpty || !mounted) return;
    if (identical(docs, _lastDocsForReconcile)) return;
    _lastDocsForReconcile = docs;
    final next = _criteria.reconcileWithDocuments(docs);
    if (jsonEncode(next.toJson()) == jsonEncode(_criteria.toJson())) return;
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      setState(() => _criteria = next);
      await _filterCache.save(next);
    });
  }

  Future<void> _openFilterSheet(
    BuildContext context, {
    required AppLocalizations loc,
    required ThemeData theme,
    required List<UnifiedPlanningDocument> allDocs,
  }) async {
    final years = allDocs.map((e) => e.year).whereType<int>().toSet().toList()
      ..sort((a, b) => b.compareTo(a));
    final hasUnknown = allDocs.any((e) => e.year == null);
    final typeKeys =
        allDocs.map(UnifiedPlanningDocument.typeKey).toSet().toList()
          ..sort((a, b) => a.toLowerCase().compareTo(b.toLowerCase()));

    final screenH = MediaQuery.sizeOf(context).height;
    final result =
        await showModalBottomSheet<UnifiedPlanningAnalyticsFilterCriteria>(
          context: context,
          isScrollControlled: true,
          useSafeArea: true,
          showDragHandle: true,
          constraints: BoxConstraints(
            maxWidth: MediaQuery.sizeOf(context).width,
            maxHeight: screenH * 0.88,
          ),
          builder: (ctx) => _AnalyticsFilterSheet(
            loc: loc,
            theme: theme,
            initial: _criteria,
            yearOptions: years,
            hasUnknownYear: hasUnknown,
            typeKeys: typeKeys,
          ),
        );
    if (result != null && mounted) {
      setState(() => _criteria = result);
      await _filterCache.save(result);
    }
  }

  String? _errorMessage(AppLocalizations loc, String? code) {
    switch (code) {
      case 'unified_error_config':
        return loc.unifiedPlanningErrorConfig;
      case 'unified_error_credentials':
        return loc.unifiedPlanningErrorCredentials;
      case 'unified_error_ifrc_auth':
        return loc.unifiedPlanningErrorIfrcAuth;
      case 'unified_error_ifrc':
        return loc.unifiedPlanningErrorIfrc;
      default:
        return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final bottomPad = MediaQuery.viewPaddingOf(context).bottom + 16;

    return Consumer<PublicResourcesProvider>(
      builder: (context, provider, _) {
        final docs = provider.unifiedPlanningDocuments;
        final loading = provider.unifiedPlanningLoading;
        final err = _errorMessage(loc, provider.unifiedPlanningErrorCode);

        _scheduleReconcileIfNeeded(docs);

        Widget body;
        if (loading && docs.isEmpty) {
          body = _AnalyticsLoading(theme: theme, bottomPad: bottomPad);
        } else if (err != null && docs.isEmpty) {
          body = DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  theme.colorScheme.surface,
                  Color.lerp(
                        theme.colorScheme.surface,
                        theme.colorScheme.primary,
                        theme.brightness == Brightness.dark ? 0.09 : 0.045,
                      ) ??
                      theme.colorScheme.surface,
                ],
              ),
            ),
            child: ListView(
              padding: EdgeInsets.fromLTRB(24, 24, 24, bottomPad),
              children: [_ErrorCard(message: err, theme: theme)],
            ),
          );
        } else {
          final filtered = docs
              .where(_criteria.matches)
              .toList(growable: false);
          final stats = _UnifiedPlanningStats.from(filtered);

          body = RefreshIndicator(
            onRefresh: () => provider.loadUnifiedPlanningDocuments(),
            color: theme.colorScheme.primary,
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    theme.colorScheme.surface,
                    Color.lerp(
                          theme.colorScheme.surface,
                          theme.colorScheme.primary,
                          theme.brightness == Brightness.dark ? 0.09 : 0.045,
                        ) ??
                        theme.colorScheme.surface,
                  ],
                ),
              ),
              child: ListView(
                padding: EdgeInsets.fromLTRB(16, 8, 16, bottomPad),
                children: [
                  _SummaryGrid(loc: loc, stats: stats, theme: theme),
                  const SizedBox(height: 22),
                  _SectionTitle(
                    loc.unifiedPlanningAnalyticsByYearType,
                    theme: theme,
                  ),
                  const SizedBox(height: 10),
                  _YearTypeGroupedByYearSection(
                    entries: stats.byYearType,
                    maxBarCount: stats.maxYearTypeCount,
                    loc: loc,
                    theme: theme,
                  ),
                ],
              ),
            ),
          );
        }

        return Scaffold(
          backgroundColor: theme.scaffoldBackgroundColor,
          appBar: AppAppBar(
            title: loc.unifiedPlanningAnalyticsTitle,
            leading: IconButton(
              icon: const Icon(Icons.arrow_back_rounded),
              onPressed: () => Navigator.of(context).pop(),
              tooltip: MaterialLocalizations.of(context).backButtonTooltip,
            ),
            automaticallyImplyLeading: false,
            actions: [
              IconButton(
                tooltip: loc.unifiedPlanningAnalyticsMapTooltip,
                onPressed: docs.isEmpty
                    ? null
                    : () {
                        Navigator.of(context).push<void>(
                          MaterialPageRoute<void>(
                            settings: const RouteSettings(
                              name: '/unified-planning-participation-map',
                            ),
                            builder: (ctx) =>
                                UnifiedPlanningParticipationMapScreen(
                                  documents: docs,
                                  initialCriteria: _criteria,
                                ),
                          ),
                        );
                      },
                icon: const Icon(Icons.public_rounded),
              ),
              IconButton(
                tooltip: loc.unifiedPlanningAnalyticsFiltersTooltip,
                onPressed: docs.isEmpty
                    ? null
                    : () => _openFilterSheet(
                        context,
                        loc: loc,
                        theme: theme,
                        allDocs: docs,
                      ),
                icon: Badge(
                  isLabelVisible: _criteria.isRestricted,
                  smallSize: 7,
                  backgroundColor: theme.colorScheme.primary,
                  child: const Icon(Icons.filter_list_rounded),
                ),
              ),
            ],
          ),
          body: body,
        );
      },
    );
  }
}

class _YearTypeCount {
  const _YearTypeCount({
    required this.year,
    required this.typeKey,
    required this.count,
  });

  final int? year;
  final String typeKey;
  final int count;
}

class _YearTypeYearGroup {
  const _YearTypeYearGroup({
    required this.year,
    required this.rows,
    required this.yearTotal,
  });

  final int? year;
  final List<_YearTypeCount> rows;
  final int yearTotal;
}

List<_YearTypeYearGroup> _groupYearTypesByYear(List<_YearTypeCount> flat) {
  final map = <int?, List<_YearTypeCount>>{};
  for (final e in flat) {
    map.putIfAbsent(e.year, () => []).add(e);
  }
  for (final list in map.values) {
    list.sort((a, b) {
      final c = b.count.compareTo(a.count);
      if (c != 0) return c;
      return a.typeKey.toLowerCase().compareTo(b.typeKey.toLowerCase());
    });
  }
  final years = map.keys.toList()
    ..sort((a, b) {
      if (a == null && b == null) return 0;
      if (a == null) return 1;
      if (b == null) return -1;
      return b.compareTo(a);
    });
  return [
    for (final y in years)
      _YearTypeYearGroup(
        year: y,
        rows: map[y]!,
        yearTotal: map[y]!.fold<int>(0, (s, e) => s + e.count),
      ),
  ];
}

class _UnifiedPlanningStats {
  _UnifiedPlanningStats({
    required this.total,
    required this.distinctCountries,
    required this.distinctTypes,
    required this.recentCount,
    required this.byYearType,
  });

  final int total;
  final int distinctCountries;
  final int distinctTypes;
  final int recentCount;
  final List<_YearTypeCount> byYearType;

  int get maxYearTypeCount => byYearType.isEmpty
      ? 1
      : byYearType.map((e) => e.count).reduce((a, b) => a > b ? a : b);

  static _UnifiedPlanningStats from(List<UnifiedPlanningDocument> docs) {
    // Match fetchDocuments: one row per unifiedPlanningListDedupeKey(url).
    final seenKeys = <String>{};
    final uniqueDocs = <UnifiedPlanningDocument>[];
    for (final d in docs) {
      if (seenKeys.add(
        IfrcUnifiedPlanningService.unifiedPlanningListDedupeKey(d.url),
      )) {
        uniqueDocs.add(d);
      }
    }

    final yearTypeCounts = <({int? year, String typeKey}), int>{};
    final distinctCountryIds = <String>{};
    final distinctTypeKeys = <String>{};
    var recent = 0;

    for (final d in uniqueDocs) {
      if (d.isPublishedWithinLastThreeDays) recent++;

      final typeKey = UnifiedPlanningDocument.typeKey(d);
      distinctTypeKeys.add(typeKey);

      final ytKey = (year: d.year, typeKey: typeKey);
      yearTypeCounts[ytKey] = (yearTypeCounts[ytKey] ?? 0) + 1;

      final idKey = UnifiedPlanningDocument.countryIdentityKey(d);
      if (idKey != null) distinctCountryIds.add(idKey);
    }

    final byYearType =
        yearTypeCounts.entries
            .map(
              (e) => _YearTypeCount(
                year: e.key.year,
                typeKey: e.key.typeKey,
                count: e.value,
              ),
            )
            .toList()
          ..sort((a, b) {
            final ay = a.year;
            final by = b.year;
            if (ay != null && by != null) {
              final cy = by.compareTo(ay);
              if (cy != 0) return cy;
            } else if (ay == null && by != null) {
              return 1;
            } else if (ay != null && by == null) {
              return -1;
            }
            final ct = a.typeKey.toLowerCase().compareTo(
              b.typeKey.toLowerCase(),
            );
            if (ct != 0) return ct;
            return b.count.compareTo(a.count);
          });

    return _UnifiedPlanningStats(
      total: uniqueDocs.length,
      distinctCountries: distinctCountryIds.length,
      distinctTypes: distinctTypeKeys
          .where((k) => k != '__type_unknown__')
          .length,
      recentCount: recent,
      byYearType: byYearType,
    );
  }
}

class _AnalyticsLoading extends StatelessWidget {
  const _AnalyticsLoading({required this.theme, required this.bottomPad});

  final ThemeData theme;
  final double bottomPad;

  @override
  Widget build(BuildContext context) {
    final accent = theme.colorScheme.primary;
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            theme.colorScheme.surface,
            Color.lerp(
                  theme.colorScheme.surface,
                  theme.colorScheme.primary,
                  theme.brightness == Brightness.dark ? 0.09 : 0.045,
                ) ??
                theme.colorScheme.surface,
          ],
        ),
      ),
      child: Center(
        child: Padding(
          padding: EdgeInsets.fromLTRB(32, 32, 32, bottomPad),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              SizedBox(
                width: 40,
                height: 40,
                child: CircularProgressIndicator(
                  strokeWidth: 3,
                  color: accent,
                  backgroundColor: accent.withValues(alpha: 0.14),
                ),
              ),
              const SizedBox(height: 20),
              Text(
                AppLocalizations.of(context)!.unifiedPlanningAnalyticsTitle,
                textAlign: TextAlign.center,
                style: theme.textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: context.textColor,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.text, {required this.theme});

  final String text;
  final ThemeData theme;

  @override
  Widget build(BuildContext context) {
    final top = theme.colorScheme.primary;
    final bottom =
        Color.lerp(
          top,
          Color(AppConstants.ifrcNavy),
          theme.brightness == Brightness.dark ? 0.35 : 0.55,
        ) ??
        top;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Container(
          width: 4,
          height: 22,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(2),
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [top, bottom],
            ),
            boxShadow: [
              BoxShadow(
                color: top.withValues(alpha: 0.22),
                blurRadius: 6,
                offset: const Offset(0, 2),
              ),
            ],
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            text,
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w700,
              letterSpacing: -0.2,
              color: context.textColor,
            ),
          ),
        ),
      ],
    );
  }
}

class _SummaryGrid extends StatelessWidget {
  const _SummaryGrid({
    required this.loc,
    required this.stats,
    required this.theme,
  });

  final AppLocalizations loc;
  final _UnifiedPlanningStats stats;
  final ThemeData theme;

  @override
  Widget build(BuildContext context) {
    final gap = 10.0;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: _SummaryMetricTile(
                label: loc.unifiedPlanningAnalyticsTotal,
                value: '${stats.total}',
                icon: Icons.description_outlined,
                theme: theme,
              ),
            ),
            SizedBox(width: gap),
            Expanded(
              child: _SummaryMetricTile(
                label: loc.unifiedPlanningAnalyticsCountries,
                value: '${stats.distinctCountries}',
                icon: Icons.flag_outlined,
                theme: theme,
              ),
            ),
          ],
        ),
        SizedBox(height: gap),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: _SummaryMetricTile(
                label: loc.unifiedPlanningAnalyticsTypes,
                value: '${stats.distinctTypes}',
                icon: Icons.category_outlined,
                theme: theme,
              ),
            ),
            SizedBox(width: gap),
            Expanded(
              child: _SummaryMetricTile(
                label: loc.unifiedPlanningAnalyticsRecent,
                value: '${stats.recentCount}',
                icon: Icons.fiber_new_rounded,
                theme: theme,
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _SummaryMetricTile extends StatelessWidget {
  const _SummaryMetricTile({
    required this.label,
    required this.value,
    required this.icon,
    required this.theme,
  });

  final String label;
  final String value;
  final IconData icon;
  final ThemeData theme;

  @override
  Widget build(BuildContext context) {
    final accent = theme.colorScheme.primary;
    final isDark = theme.brightness == Brightness.dark;
    final fill = Color.alphaBlend(
      accent.withValues(alpha: isDark ? 0.07 : 0.05),
      theme.colorScheme.surfaceContainerHighest.withValues(
        alpha: isDark ? 0.38 : 0.5,
      ),
    );
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14),
        color: fill,
        border: Border.all(
          color: theme.colorScheme.outlineVariant.withValues(alpha: 0.38),
        ),
        boxShadow: [
          BoxShadow(
            color: theme.ambientShadow(),
            blurRadius: 10,
            offset: const Offset(0, 4),
            spreadRadius: -2,
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            DecoratedBox(
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(10),
                color: theme.colorScheme.primaryContainer.withValues(
                  alpha: isDark ? 0.48 : 0.62,
                ),
                border: Border.all(color: accent.withValues(alpha: 0.16)),
              ),
              child: Padding(
                padding: const EdgeInsets.all(8),
                child: Icon(icon, size: 20, color: accent),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    value,
                    style: theme.textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.w800,
                      letterSpacing: -0.4,
                      color: context.textColor,
                      height: 1.1,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    label,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: context.textSecondaryColor,
                      height: 1.2,
                      fontWeight: FontWeight.w500,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _YearTypeGroupedByYearSection extends StatelessWidget {
  static const int _maxTypesPerYear = 14;

  const _YearTypeGroupedByYearSection({
    required this.entries,
    required this.maxBarCount,
    required this.loc,
    required this.theme,
  });

  final List<_YearTypeCount> entries;
  final int maxBarCount;
  final AppLocalizations loc;
  final ThemeData theme;

  String _yearHeading(int? year) =>
      year != null ? '$year' : loc.unifiedPlanningAnalyticsUnknownYear;

  String _typeLabel(String typeKey) => typeKey == '__type_unknown__'
      ? loc.unifiedPlanningAnalyticsUnknownType
      : typeKey;

  @override
  Widget build(BuildContext context) {
    final groups = _groupYearTypesByYear(entries);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (var gi = 0; gi < groups.length; gi++) ...[
          if (gi > 0) const SizedBox(height: 16),
          DecoratedBox(
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(16),
              color: theme.colorScheme.surfaceContainerHighest.withValues(
                alpha: theme.brightness == Brightness.dark ? 0.35 : 0.42,
              ),
              border: Border.all(
                color: theme.colorScheme.outlineVariant.withValues(alpha: 0.35),
              ),
              boxShadow: [
                BoxShadow(
                  color: theme.ambientShadow(),
                  blurRadius: 12,
                  offset: const Offset(0, 5),
                  spreadRadius: -2,
                ),
              ],
            ),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      Expanded(
                        child: Text(
                          _yearHeading(groups[gi].year),
                          style: theme.textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.w800,
                            letterSpacing: -0.2,
                            color: context.textColor,
                          ),
                        ),
                      ),
                      DecoratedBox(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(20),
                          color: theme.colorScheme.primaryContainer.withValues(
                            alpha: theme.brightness == Brightness.dark
                                ? 0.5
                                : 0.72,
                          ),
                          border: Border.all(
                            color: theme.colorScheme.primary.withValues(
                              alpha: 0.2,
                            ),
                          ),
                        ),
                        child: Padding(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 12,
                            vertical: 5,
                          ),
                          child: Text(
                            '${groups[gi].yearTotal}',
                            style: theme.textTheme.labelLarge?.copyWith(
                              fontWeight: FontWeight.w800,
                              color: theme.colorScheme.onPrimaryContainer,
                              height: 1,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Divider(
                    height: 1,
                    thickness: 1,
                    color: context.dividerColor.withValues(alpha: 0.45),
                  ),
                  const SizedBox(height: 12),
                  for (
                    var j = 0;
                    j < groups[gi].rows.length && j < _maxTypesPerYear;
                    j++
                  ) ...[
                    if (j > 0) const SizedBox(height: 12),
                    _BarRow(
                      label: _typeLabel(groups[gi].rows[j].typeKey),
                      count: groups[gi].rows[j].count,
                      max: maxBarCount,
                      theme: theme,
                    ),
                  ],
                  if (groups[gi].rows.length > _maxTypesPerYear)
                    Padding(
                      padding: const EdgeInsets.only(top: 10),
                      child: Text(
                        loc.unifiedPlanningAnalyticsMore(
                          groups[gi].rows.length - _maxTypesPerYear,
                        ),
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: context.textSecondaryColor,
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _BarRow extends StatefulWidget {
  const _BarRow({
    required this.label,
    required this.count,
    required this.max,
    required this.theme,
  });

  final String label;
  final int count;
  final int max;
  final ThemeData theme;

  @override
  State<_BarRow> createState() => _BarRowState();
}

class _BarRowState extends State<_BarRow> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  double _target = 0;

  double _fraction() {
    final m = widget.max;
    if (m <= 0) return 0;
    return (widget.count / m).clamp(0.0, 1.0);
  }

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 780),
    );
    _target = _fraction();
    _controller.forward();
  }

  @override
  void didUpdateWidget(covariant _BarRow oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.count != widget.count || oldWidget.max != widget.max) {
      _target = _fraction();
      _controller.forward(from: 0);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = widget.theme;
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final eased = Curves.easeOutCubic.transform(_controller.value);
        final widthFactor = eased * _target;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    widget.label,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: context.textColor,
                      fontWeight: FontWeight.w500,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: 10),
                DecoratedBox(
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surface.withValues(alpha: 0.65),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(
                      color: theme.colorScheme.outlineVariant.withValues(
                        alpha: 0.35,
                      ),
                    ),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 3,
                    ),
                    child: Text(
                      '${widget.count}',
                      style: theme.textTheme.labelLarge?.copyWith(
                        fontWeight: FontWeight.w800,
                        color: context.textColor,
                        height: 1,
                      ),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            _GradientProgressTrack(widthFactor: widthFactor, theme: theme),
          ],
        );
      },
    );
  }
}

/// Filled track with brand gradient; [widthFactor] is 0–1 (animated in [_BarRow]).
class _GradientProgressTrack extends StatelessWidget {
  const _GradientProgressTrack({
    required this.widthFactor,
    required this.theme,
  });

  final double widthFactor;
  final ThemeData theme;

  @override
  Widget build(BuildContext context) {
    final brand = Color(AppConstants.ifrcRed);
    final brandDeep = Color(AppConstants.ifrcDarkRed);
    final isLight = theme.brightness == Brightness.light;
    // Light: grey divider on grey cards disappears — use a light trough + outline.
    final track = isLight
        ? theme.colorScheme.surface
        : context.dividerColor.withValues(alpha: 0.5);
    final trackBorder = theme.colorScheme.outlineVariant.withValues(
      alpha: isLight ? 0.6 : 0.42,
    );
    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: track,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: trackBorder),
        ),
        child: SizedBox(
          height: 9,
          child: Stack(
            fit: StackFit.expand,
            children: [
              Align(
                alignment: Alignment.centerLeft,
                child: FractionallySizedBox(
                  widthFactor: widthFactor.clamp(0.0, 1.0),
                  heightFactor: 1,
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.centerLeft,
                        end: Alignment.centerRight,
                        colors: [brand, Color.lerp(brand, brandDeep, 0.55)!],
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: brand.withValues(alpha: 0.45),
                          blurRadius: 10,
                          spreadRadius: -2,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.message, required this.theme});

  final String message;
  final ThemeData theme;

  @override
  Widget build(BuildContext context) {
    final err = const Color(AppConstants.errorColor);
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        color: err.withValues(
          alpha: theme.brightness == Brightness.dark ? 0.14 : 0.08,
        ),
        border: Border.all(color: err.withValues(alpha: 0.28)),
        boxShadow: [
          BoxShadow(
            color: err.withValues(alpha: 0.12),
            blurRadius: 16,
            offset: const Offset(0, 6),
            spreadRadius: -4,
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            DecoratedBox(
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: err.withValues(alpha: 0.18),
                border: Border.all(color: err.withValues(alpha: 0.35)),
              ),
              child: const Padding(
                padding: EdgeInsets.all(8),
                child: Icon(
                  Icons.info_outline_rounded,
                  size: 22,
                  color: Color(AppConstants.errorColor),
                ),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Text(
                message,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: context.textColor,
                  height: 1.45,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

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

class _AnalyticsFilterSheet extends StatefulWidget {
  const _AnalyticsFilterSheet({
    required this.loc,
    required this.theme,
    required this.initial,
    required this.yearOptions,
    required this.hasUnknownYear,
    required this.typeKeys,
  });

  final AppLocalizations loc;
  final ThemeData theme;
  final UnifiedPlanningAnalyticsFilterCriteria initial;
  final List<int> yearOptions;
  final bool hasUnknownYear;
  final List<String> typeKeys;

  @override
  State<_AnalyticsFilterSheet> createState() => _AnalyticsFilterSheetState();
}

class _AnalyticsFilterSheetState extends State<_AnalyticsFilterSheet> {
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
    // Cap scroll region: short content keeps a compact sheet; long lists scroll inside.
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
              Navigator.of(context).pop(_draft.seal());
            },
            child: Text(loc.unifiedPlanningAnalyticsFilterApply),
          ),
        ],
      ),
    );
  }
}
