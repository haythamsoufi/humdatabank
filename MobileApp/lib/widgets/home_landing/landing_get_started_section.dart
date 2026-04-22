import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_map/flutter_map.dart';

import '../../config/fdrs_constants.dart';
import '../../di/service_locator.dart';
import '../../l10n/app_localizations.dart';
import '../../services/global_overview_data_service.dart';
import '../../utils/constants.dart';
import 'country_centroids_cache.dart';
import 'fdrs_world_map.dart';
import 'world_geojson_cache.dart';
import '../sheets/native_modal_sheet.dart';

class LandingShortcutItem {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const LandingShortcutItem({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });
}

/// Modern “Get started” hub: horizontal shortcuts + native map (FDRS).
class LandingGetStartedSection extends StatefulWidget {
  const LandingGetStartedSection({
    super.key,
    required this.l10n,
    required this.locale,
    required this.shortcuts,
  });

  final AppLocalizations l10n;
  final String locale;
  final List<LandingShortcutItem> shortcuts;

  @override
  State<LandingGetStartedSection> createState() =>
      _LandingGetStartedSectionState();
}

class _LandingGetStartedSectionState extends State<LandingGetStartedSection> {
  final GlobalOverviewDataService _service = sl<GlobalOverviewDataService>();
  late Future<void> _mapAssets;
  late Future<GlobalOverviewDataset> _datasetFuture;
  List<String> _periodOptions = [];
  String? _selectedPeriod;
  int _indicatorBankId = FdrsConstants.indicatorVolunteers;
  FdrsMapVisualMode _mapVisualMode = FdrsMapVisualMode.bubble;

  @override
  void initState() {
    super.initState();
    _mapAssets = Future.wait([
      CountryCentroidsCache.instance.ensureLoaded(),
      WorldGeoJsonCache.instance.ensureLoaded(),
    ]);
    _datasetFuture = _loadPeriodsThenData();
  }

  @override
  void didUpdateWidget(covariant LandingGetStartedSection oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.locale != widget.locale) {
      setState(() {
        _datasetFuture = _loadPeriodsThenData();
      });
    }
  }

  Future<GlobalOverviewDataset> _loadPeriodsThenData() async {
    final periods = await _service.listFdrsPeriods();
    if (!mounted) {
      throw OverviewLoadException('disposed');
    }
    setState(() {
      _periodOptions = periods;
      if (_selectedPeriod == null || !_periodOptions.contains(_selectedPeriod)) {
        _selectedPeriod = periods.isNotEmpty ? periods.first : null;
      }
    });
    return _service.loadOverview(
      indicatorBankId: _indicatorBankId,
      locale: widget.locale,
      periodName: _selectedPeriod,
    );
  }

  Future<GlobalOverviewDataset> _loadDataOnly() {
    return _service.loadOverview(
      indicatorBankId: _indicatorBankId,
      locale: widget.locale,
      periodName: _selectedPeriod,
    );
  }

  void _selectIndicator(int id) {
    if (id == _indicatorBankId) return;
    setState(() {
      _indicatorBankId = id;
      _datasetFuture = _loadDataOnly();
    });
  }

  void _onPeriodChanged(String? value) {
    if (value == null || value == _selectedPeriod) return;
    setState(() {
      _selectedPeriod = value;
      _datasetFuture = _loadDataOnly();
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = widget.l10n;

    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _LandingSectionTitle(text: l10n.homeLandingShortcutsHeading),
          const SizedBox(height: 14),
          SizedBox(
            height: 108,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: widget.shortcuts.length,
              separatorBuilder: (context, index) => const SizedBox(width: 12),
              itemBuilder: (context, index) {
                final item = widget.shortcuts[index];
                return _ShortcutStripTile(item: item);
              },
            ),
          ),
          const SizedBox(height: 24),
          _LandingSectionTitle(text: l10n.homeLandingExploreTitle),
          const SizedBox(height: 6),
          Text(
            l10n.homeLandingExploreSubtitle,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
              height: 1.4,
            ),
          ),
          const SizedBox(height: 14),
          FdrsIndicatorScrollBar(
            l10n: l10n,
            indicatorBankId: _indicatorBankId,
            onSelect: _selectIndicator,
          ),
          const SizedBox(height: 14),
          if (_periodOptions.length > 1) ...[
            ReportingPeriodPickerField(
              l10n: l10n,
              periods: _periodOptions,
              value: _selectedPeriod,
              onChanged: _onPeriodChanged,
            ),
            const SizedBox(height: 12),
          ],
          FutureBuilder<void>(
            future: _mapAssets,
            builder: (context, snap) {
              return FutureBuilder<GlobalOverviewDataset>(
                future: _datasetFuture,
                builder: (context, dsSnap) {
                  if (dsSnap.connectionState == ConnectionState.waiting) {
                    return SizedBox(
                      height: 320,
                      child: Center(
                        child: CircularProgressIndicator(
                          color: theme.colorScheme.secondary,
                        ),
                      ),
                    );
                  }
                  if (dsSnap.hasError) {
                    return _ErrorBlock(
                      message: l10n.homeLandingGlobalLoadError,
                      onRetry: () {
                        setState(() {
                          _datasetFuture = _loadPeriodsThenData();
                        });
                      },
                    );
                  }
                  final data = dsSnap.data!;
                  if (data.byCountryId.isEmpty) {
                    return Padding(
                      padding: const EdgeInsets.symmetric(vertical: 24),
                      child: Center(
                        child: Text(
                          l10n.homeLandingGlobalEmpty,
                          textAlign: TextAlign.center,
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ),
                    );
                  }
                  return _OverviewBody(
                    l10n: l10n,
                    theme: theme,
                    locale: widget.locale,
                    data: data,
                    mapVisualMode: _mapVisualMode,
                    onMapVisualModeChanged: (mode) {
                      setState(() => _mapVisualMode = mode);
                    },
                    indicatorBankId: _indicatorBankId,
                    selectedPeriod: _selectedPeriod,
                    periodOptions: _periodOptions,
                    onApplyFullscreenSnapshot: (snapshot) {
                      setState(() {
                        _indicatorBankId = snapshot.indicatorBankId;
                        _selectedPeriod = snapshot.selectedPeriod;
                        _mapVisualMode = snapshot.visualMode;
                        _datasetFuture = _loadDataOnly();
                      });
                    },
                    reloadDataset: ({
                      required int indicatorBankId,
                      required String? periodName,
                    }) =>
                        _service.loadOverview(
                          indicatorBankId: indicatorBankId,
                          locale: widget.locale,
                          periodName: periodName,
                        ),
                  );
                },
              );
            },
          ),
        ],
      ),
    );
  }
}

/// Section label: typography-first, hairline rule (no rounded “badge” chrome).
class _LandingSectionTitle extends StatelessWidget {
  const _LandingSectionTitle({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final line = cs.outlineVariant.withValues(
      alpha: theme.brightness == Brightness.dark ? 0.5 : 0.35,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          text,
          style: theme.textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.w700,
            letterSpacing: -0.3,
            height: 1.2,
            color: cs.onSurface,
          ),
        ),
        const SizedBox(height: 10),
        Container(height: 1, color: line),
      ],
    );
  }
}

/// Flat shortcut tile: sharp rectangle, hairline frame, no elevation (editorial / list hybrid).
class _ShortcutStripTile extends StatelessWidget {
  const _ShortcutStripTile({required this.item});

  final LandingShortcutItem item;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final isDark = theme.brightness == Brightness.dark;
    final accent = cs.secondary;
    final iconBg = accent.withValues(alpha: isDark ? 0.18 : 0.1);
    final borderColor = cs.outlineVariant.withValues(alpha: isDark ? 0.5 : 0.32);

    return Material(
      color: cs.surface,
      elevation: 0,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        side: BorderSide(color: borderColor),
      ),
      clipBehavior: Clip.hardEdge,
      child: InkWell(
        onTap: () {
          HapticFeedback.lightImpact();
          item.onTap();
        },
        splashColor: accent.withValues(alpha: 0.1),
        highlightColor: accent.withValues(alpha: 0.05),
        child: SizedBox(
          width: 268,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 14, 10, 14),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                ColoredBox(
                  color: iconBg,
                  child: SizedBox(
                    width: 44,
                    height: 44,
                    child: Icon(item.icon, size: 22, color: accent),
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.center,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        item.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w600,
                          color: cs.onSurface,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        item.subtitle,
                        maxLines: 3,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: cs.onSurfaceVariant,
                          fontSize: 12,
                          height: 1.28,
                        ),
                      ),
                    ],
                  ),
                ),
                Icon(
                  Icons.chevron_right_rounded,
                  size: 22,
                  color: cs.onSurface.withValues(alpha: isDark ? 0.45 : 0.35),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ErrorBlock extends StatelessWidget {
  const _ErrorBlock({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 32),
      child: Column(
        children: [
          Icon(
            Icons.cloud_off_outlined,
            size: 40,
            color: theme.colorScheme.onSurfaceVariant,
          ),
          const SizedBox(height: 12),
          Text(
            message,
            textAlign: TextAlign.center,
            style: theme.textTheme.bodyMedium,
          ),
          const SizedBox(height: 12),
          TextButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh),
            label: Text(AppLocalizations.of(context)!.retry),
          ),
        ],
      ),
    );
  }
}

/// Top countries for the selected indicator (complements the map).
class _OverviewTopCountriesBar extends StatelessWidget {
  const _OverviewTopCountriesBar({
    required this.theme,
    required this.l10n,
    required this.locale,
    required this.data,
    required this.indicatorLabel,
  });

  final ThemeData theme;
  final AppLocalizations l10n;
  final String locale;
  final GlobalOverviewDataset data;
  final String indicatorLabel;

  @override
  Widget build(BuildContext context) {
    final top = data.topByValue(8);
    if (top.isEmpty) {
      return const SizedBox.shrink();
    }
    final maxY = top.map((e) => e.value).reduce(math.max);
    final rodColor = Color(AppConstants.ifrcRed);
    final gridColor = theme.colorScheme.outlineVariant
        .withValues(alpha: theme.brightness == Brightness.dark ? 0.35 : 0.45);

    String shortLabel(int countryId) {
      final name = data.countryNames[countryId];
      if (name != null && name.isNotEmpty) {
        const maxChars = 18;
        return name.length <= maxChars
            ? name
            : '${name.substring(0, maxChars - 1)}…';
      }
      final iso = data.countryIso2[countryId];
      if (iso != null && iso.isNotEmpty) {
        return iso.toUpperCase();
      }
      return '#$countryId';
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          l10n.homeLandingGlobalTopCountries,
          style: theme.textTheme.titleSmall?.copyWith(
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          indicatorLabel,
          style: theme.textTheme.labelSmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 10),
        SizedBox(
          height: 232,
          child: BarChart(
            BarChartData(
              alignment: BarChartAlignment.spaceAround,
              maxY: maxY > 0 ? maxY * 1.12 : 1,
              barTouchData: const BarTouchData(enabled: false),
              titlesData: FlTitlesData(
                show: true,
                topTitles: const AxisTitles(
                  sideTitles: SideTitles(showTitles: false),
                ),
                rightTitles: const AxisTitles(
                  sideTitles: SideTitles(showTitles: false),
                ),
                leftTitles: AxisTitles(
                  sideTitles: SideTitles(
                    showTitles: true,
                    reservedSize: 44,
                    interval: maxY > 0 ? (maxY / 3).clamp(1, double.infinity) : 1,
                    getTitlesWidget: (value, meta) {
                      if (value < 0 || value > meta.max) {
                        return const SizedBox.shrink();
                      }
                      return Padding(
                        padding: const EdgeInsets.only(right: 6),
                        child: Text(
                          formatFdrsOverviewValue(value, locale),
                          style: theme.textTheme.labelSmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                          textAlign: TextAlign.end,
                        ),
                      );
                    },
                  ),
                ),
                bottomTitles: AxisTitles(
                  sideTitles: SideTitles(
                    showTitles: true,
                    reservedSize: 68,
                    getTitlesWidget: (value, meta) {
                      final i = value.toInt();
                      if (i < 0 || i >= top.length) {
                        return const SizedBox.shrink();
                      }
                      final labelStyle = theme.textTheme.labelSmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      );
                      return SideTitleWidget(
                        meta: meta,
                        space: 2,
                        angle: -math.pi / 4,
                        fitInside: SideTitleFitInsideData.fromTitleMeta(
                          meta,
                          distanceFromEdge: 4,
                        ),
                        child: Text(
                          shortLabel(top[i].key),
                          style: labelStyle,
                          maxLines: 1,
                          softWrap: false,
                          overflow: TextOverflow.ellipsis,
                        ),
                      );
                    },
                  ),
                ),
              ),
              gridData: FlGridData(
                show: true,
                drawVerticalLine: false,
                horizontalInterval: maxY > 0 ? maxY / 4 : 1,
                getDrawingHorizontalLine: (value) => FlLine(
                  color: gridColor,
                  strokeWidth: 1,
                ),
              ),
              borderData: FlBorderData(show: false),
              barGroups: [
                for (var i = 0; i < top.length; i++)
                  BarChartGroupData(
                    x: i,
                    barsSpace: 6,
                    barRods: [
                      BarChartRodData(
                        toY: top[i].value,
                        width: 14,
                        color: rodColor.withValues(alpha: 0.85),
                        borderRadius: const BorderRadius.vertical(
                          top: Radius.circular(4),
                        ),
                      ),
                    ],
                  ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _OverviewBody extends StatelessWidget {
  const _OverviewBody({
    required this.l10n,
    required this.theme,
    required this.locale,
    required this.data,
    required this.mapVisualMode,
    required this.onMapVisualModeChanged,
    required this.indicatorBankId,
    required this.selectedPeriod,
    required this.periodOptions,
    required this.onApplyFullscreenSnapshot,
    required this.reloadDataset,
  });

  final AppLocalizations l10n;
  final ThemeData theme;
  final String locale;
  final GlobalOverviewDataset data;
  final FdrsMapVisualMode mapVisualMode;
  final ValueChanged<FdrsMapVisualMode> onMapVisualModeChanged;
  final int indicatorBankId;
  final String? selectedPeriod;
  final List<String> periodOptions;
  final ValueChanged<FdrsMapSessionSnapshot> onApplyFullscreenSnapshot;
  final Future<GlobalOverviewDataset> Function({
    required int indicatorBankId,
    required String? periodName,
  }) reloadDataset;

  @override
  Widget build(BuildContext context) {
    final cache = CountryCentroidsCache.instance;
    final points = data.geoPoints((iso) => cache[iso]);
    final maxVal = data.byCountryId.values.fold<double>(
      0,
      (a, b) => a > b ? a : b,
    );

    CameraFit? initialFit;
    if (points.length >= 2) {
      final bounds = LatLngBounds.fromPoints(
        points.map((p) => p.point).toList(),
      );
      initialFit = CameraFit.bounds(
        bounds: bounds,
        padding: const EdgeInsets.fromLTRB(28, 24, 28, 36),
        maxZoom: 4.2,
      );
    } else if (points.length == 1) {
      initialFit = CameraFit.coordinates(
        coordinates: [points.first.point],
        padding: const EdgeInsets.all(72),
        maxZoom: 4.5,
      );
    }

    final circles = <CircleMarker<String>>[];
    for (final p in points) {
      final r = maxVal > 0
          ? 6 + math.sqrt(p.value / maxVal) * 24
          : 8.0;
      circles.add(
        CircleMarker<String>(
          point: p.point,
          radius: r.clamp(5, 32),
          color: Color(AppConstants.ifrcRed).withValues(alpha: 0.45),
          borderStrokeWidth: 1,
          borderColor: Colors.white24,
          hitValue: p.iso2,
        ),
      );
    }

    final valueByIso = <String, double>{};
    for (final e in data.byCountryId.entries) {
      final iso = data.countryIso2[e.key];
      if (iso != null && e.value > 0) {
        valueByIso[iso.toUpperCase()] = e.value;
      }
    }

    final isDark = theme.brightness == Brightness.dark;
    final border = theme.colorScheme.outlineVariant
        .withValues(alpha: isDark ? 0.45 : 0.35);
    final noData = theme.colorScheme.surfaceContainerHighest
        .withValues(alpha: isDark ? 0.35 : 0.5);
    final low = Color(AppConstants.ifrcRed).withValues(alpha: 0.12);
    final high = Color(AppConstants.ifrcRed).withValues(alpha: 0.78);

    final polys = WorldGeoJsonCache.instance.buildChoroplethPolygons(
      fillNoData: noData,
      fillLow: low,
      fillHigh: high,
      valueByIso2Upper: valueByIso,
      maxValue: maxVal,
      borderStrokeWidth: 0.5,
      borderColor: border,
    );

    final indicatorLabel = fdrsIndicatorTitle(l10n, indicatorBankId);
    final frame = theme.colorScheme.outlineVariant
        .withValues(alpha: isDark ? 0.55 : 0.4);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        FdrsMapModeToggle(
          l10n: l10n,
          mode: mapVisualMode,
          onChanged: onMapVisualModeChanged,
        ),
        const SizedBox(height: 10),
        DecoratedBox(
          decoration: BoxDecoration(
            border: Border.all(color: frame, width: 1),
          ),
          child: ClipRect(
            child: SizedBox(
              height: 240,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  FdrsOverviewMap(
                    theme: theme,
                    visualMode: mapVisualMode,
                    circles: circles,
                    choroplethPolygons: polys,
                    initialFit: initialFit,
                    maxZoom: 22,
                    polygonSimplification: 0,
                    notifyParentScrollWhilePointersDown: true,
                    onCountryIso2Tapped: (iso2) {
                      showFdrsCountryInsightSheet(
                        context: context,
                        l10n: l10n,
                        locale: locale,
                        data: data,
                        iso2: iso2,
                        indicatorLabel: indicatorLabel,
                        indicatorBankId: indicatorBankId,
                        periodOptions: periodOptions,
                      );
                    },
                  ),
                  PositionedDirectional(
                    top: 0,
                    end: 0,
                    child: Material(
                      color: theme.colorScheme.surface.withValues(alpha: 0.94),
                      surfaceTintColor: Colors.transparent,
                      elevation: 0,
                      shape: const RoundedRectangleBorder(),
                      child: InkWell(
                        onTap: () async {
                          final snap =
                              await Navigator.of(context)
                                  .push<FdrsMapSessionSnapshot?>(
                            MaterialPageRoute<FdrsMapSessionSnapshot?>(
                              settings: const RouteSettings(name: '/world-map-fullscreen'),
                              fullscreenDialog: true,
                              builder: (ctx) => FdrsWorldMapFullscreenPage(
                                l10n: l10n,
                                theme: theme,
                                locale: locale,
                                initialDataset: data,
                                indicatorBankId: indicatorBankId,
                                selectedPeriod: selectedPeriod,
                                periodOptions: periodOptions,
                                visualMode: mapVisualMode,
                                reloadDataset: reloadDataset,
                              ),
                            ),
                          );
                          if (snap != null && context.mounted) {
                            onApplyFullscreenSnapshot(snap);
                          }
                        },
                        child: Tooltip(
                          message: l10n.homeLandingGlobalMapOpenFullscreen,
                          child: Padding(
                            padding: const EdgeInsets.all(10),
                            child: Icon(
                              Icons.fullscreen_rounded,
                              color: theme.colorScheme.secondary,
                              size: 22,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        if (mapVisualMode == FdrsMapVisualMode.choropleth) ...[
          const SizedBox(height: 8),
          FdrsChoroplethLegend(
            l10n: l10n,
            lowColor: low,
            highColor: high,
          ),
        ],
        const SizedBox(height: 12),
        _OverviewTopCountriesBar(
          theme: theme,
          l10n: l10n,
          locale: locale,
          data: data,
          indicatorLabel: indicatorLabel,
        ),
        const SizedBox(height: 6),
        Text(
          l10n.homeLandingGlobalMapHint,
          style: theme.textTheme.labelSmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      ],
    );
  }
}
