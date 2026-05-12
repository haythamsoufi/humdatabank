import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:intl/intl.dart';
import 'package:latlong2/latlong.dart';

import '../../config/app_config.dart';
import '../../config/fdrs_constants.dart';
import '../../di/service_locator.dart';
import '../../l10n/app_localizations.dart';
import '../../services/global_overview_data_service.dart';
import '../../utils/constants.dart';
import '../sheets/native_modal_sheet.dart';
import 'country_centroids_cache.dart';
import 'world_geojson_cache.dart';

/// Bubble markers vs filled country polygons (choropleth).
enum FdrsMapVisualMode { bubble, choropleth }

/// Bubbles up while pointers are active on the embedded home map so a parent
/// [CustomScrollView] can pause vertical scrolling and let [FlutterMap] handle
/// pan/pinch.
class FdrsEmbeddedMapPointerNotification extends Notification {
  FdrsEmbeddedMapPointerNotification({required this.activePointerCount});
  final int activePointerCount;
}

class FdrsEmbeddedMapPointerNotifier extends StatefulWidget {
  const FdrsEmbeddedMapPointerNotifier({super.key, required this.child});

  final Widget child;

  @override
  State<FdrsEmbeddedMapPointerNotifier> createState() =>
      _FdrsEmbeddedMapPointerNotifierState();
}

class _FdrsEmbeddedMapPointerNotifierState
    extends State<FdrsEmbeddedMapPointerNotifier> {
  int _count = 0;

  void _dispatch() {
    FdrsEmbeddedMapPointerNotification(activePointerCount: _count)
        .dispatch(context);
  }

  @override
  void dispose() {
    final was = _count;
    _count = 0;
    if (was != 0 && context.mounted) {
      FdrsEmbeddedMapPointerNotification(activePointerCount: 0)
          .dispatch(context);
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Listener(
      behavior: HitTestBehavior.deferToChild,
      onPointerDown: (_) {
        _count++;
        _dispatch();
      },
      onPointerUp: (_) {
        _count = (_count - 1).clamp(0, 64);
        _dispatch();
      },
      onPointerCancel: (_) {
        _count = (_count - 1).clamp(0, 64);
        _dispatch();
      },
      child: widget.child,
    );
  }
}

/// Returned from fullscreen so the home section can stay in sync.
class FdrsMapSessionSnapshot {
  const FdrsMapSessionSnapshot({
    required this.indicatorBankId,
    required this.selectedPeriod,
    required this.visualMode,
  });

  final int indicatorBankId;
  final String? selectedPeriod;
  final FdrsMapVisualMode visualMode;
}

String fdrsIndicatorTitle(AppLocalizations l10n, int indicatorBankId) {
  switch (indicatorBankId) {
    case FdrsConstants.indicatorVolunteers:
      return l10n.homeLandingGlobalIndicatorVolunteers;
    case FdrsConstants.indicatorStaff:
      return l10n.homeLandingGlobalIndicatorStaff;
    case FdrsConstants.indicatorBranches:
      return l10n.homeLandingGlobalIndicatorBranches;
    case FdrsConstants.indicatorLocalUnits:
      return l10n.homeLandingGlobalIndicatorLocalUnits;
    case FdrsConstants.indicatorBloodDonors:
      return l10n.homeLandingGlobalIndicatorBloodDonors;
    case FdrsConstants.indicatorFirstAid:
      return l10n.homeLandingGlobalIndicatorFirstAid;
    case FdrsConstants.indicatorPeopleReached:
      return l10n.homeLandingGlobalIndicatorPeopleReached;
    case FdrsConstants.indicatorIncome:
      return l10n.homeLandingGlobalIndicatorIncome;
    case FdrsConstants.indicatorExpenditure:
      return l10n.homeLandingGlobalIndicatorExpenditure;
    default:
      return '';
  }
}

String formatFdrsOverviewValue(double v, String locale) {
  if (v >= 1e9) {
    return '${(v / 1e9).toStringAsFixed(v >= 1e10 ? 0 : 1)}B';
  }
  if (v >= 1e6) {
    return '${(v / 1e6).toStringAsFixed(v >= 1e7 ? 0 : 1)}M';
  }
  if (v >= 1e3) {
    return '${(v / 1e3).toStringAsFixed(v >= 1e4 ? 0 : 1)}K';
  }
  final fmt = NumberFormat.decimalPattern(locale);
  if (v == v.roundToDouble()) {
    return fmt.format(v.round());
  }
  return fmt.format(double.parse(v.toStringAsFixed(2)));
}

int? countryIdForIso2(GlobalOverviewDataset data, String iso2Upper) {
  for (final e in data.countryIso2.entries) {
    if (e.value.toUpperCase() == iso2Upper) return e.key;
  }
  return null;
}

String? countryNameForIso2(GlobalOverviewDataset data, String iso2Upper) {
  final id = countryIdForIso2(data, iso2Upper);
  if (id == null) return null;
  return data.countryNames[id] ?? iso2Upper;
}

double? valueForIso2(GlobalOverviewDataset data, String iso2Upper) {
  final id = countryIdForIso2(data, iso2Upper);
  if (id == null) return null;
  final v = data.byCountryId[id];
  if (v == null || v <= 0) return null;
  return v;
}

/// Web Mercator without infinite horizontal wrapping — one world strip, no
/// side-scroll clones (see flutter_map `Epsg3857.replicatesWorldLongitude`).
final class _Epsg3857NoRepeat extends Epsg3857 {
  const _Epsg3857NoRepeat() : super();

  @override
  bool get replicatesWorldLongitude => false;
}

/// Valid Web Mercator latitudes plus full longitude; used to keep the camera
/// center over the map. [CameraConstraint.containCenter] always returns a
/// camera from [constrain] (unlike [CameraConstraint.contain], which can
/// return null), which matches flutter_map's assertion when [MapOptions] update.
final LatLngBounds _fdrsWorldMapBounds = LatLngBounds.unsafe(
  north: 85,
  south: -85,
  east: 180,
  west: -180,
);

MapOptions fdrsWorldMapOptions(
  ThemeData theme,
  CameraFit? initialFit, {
  double maxZoom = 22,
  double minZoom = 1,
  void Function(TapPosition tapPosition, LatLng point)? onTap,
}) {
  return MapOptions(
    crs: const _Epsg3857NoRepeat(),
    backgroundColor: theme.colorScheme.surfaceContainerHigh,
    initialCenter: const LatLng(20, 10),
    initialZoom: initialFit != null ? 1.2 : 1.4,
    initialCameraFit: initialFit,
    minZoom: minZoom,
    maxZoom: maxZoom,
    cameraConstraint: CameraConstraint.containCenter(
      bounds: _fdrsWorldMapBounds,
    ),
    onTap: onTap,
    interactionOptions: const InteractionOptions(flags: InteractiveFlag.all),
  );
}

/// IFRC-style Mapbox raster tiles (public token). Falls back to Carto when unset.
List<Widget> fdrsWorldMapTiles(ThemeData theme) {
  final isDark = theme.brightness == Brightness.dark;
  final token = AppConfig.mapboxAccessToken;
  if (token.isNotEmpty) {
    final stylePath = isDark ? 'mapbox/dark-v11' : 'mapbox/light-v11';
    final url =
        'https://api.mapbox.com/styles/v1/$stylePath/tiles/{z}/{x}/{y}?access_token=$token';
    return [
      TileLayer(urlTemplate: url, userAgentPackageName: 'hum_databank_app'),
    ];
  }
  return [
    TileLayer(
      urlTemplate: isDark
          ? 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'
          : 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
      subdomains: const ['a', 'b', 'c', 'd'],
      userAgentPackageName: 'hum_databank_app',
    ),
  ];
}

void showFdrsCountryInsightSheet({
  required BuildContext context,
  required AppLocalizations l10n,
  required String locale,
  required GlobalOverviewDataset data,
  required String iso2,
  required String indicatorLabel,
  required int indicatorBankId,
  required List<String> periodOptions,
}) {
  final theme = Theme.of(context);
  final name = countryNameForIso2(data, iso2.toUpperCase()) ?? iso2;
  final countryId = countryIdForIso2(data, iso2.toUpperCase());

  showModalBottomSheet<void>(
    context: context,
    backgroundColor: theme.colorScheme.surface,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (ctx) {
      final bottomInset = MediaQuery.viewPaddingOf(ctx).bottom;
      return Padding(
        padding: EdgeInsets.fromLTRB(20, 8, 20, 24 + bottomInset),
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
              indicatorLabel,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 16),
            if (countryId == null)
              Text(
                l10n.homeLandingGlobalMapCountryNoData,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              )
            else
              _FdrsCountryTrendLoader(
                l10n: l10n,
                locale: locale,
                theme: theme,
                indicatorBankId: indicatorBankId,
                periodOptions: periodOptions,
                countryId: countryId,
              ),
          ],
        ),
      );
    },
  );
}

class _FdrsCountryTrendLoader extends StatefulWidget {
  const _FdrsCountryTrendLoader({
    required this.l10n,
    required this.locale,
    required this.theme,
    required this.indicatorBankId,
    required this.periodOptions,
    required this.countryId,
  });

  final AppLocalizations l10n;
  final String locale;
  final ThemeData theme;
  final int indicatorBankId;
  final List<String> periodOptions;
  final int countryId;

  @override
  State<_FdrsCountryTrendLoader> createState() =>
      _FdrsCountryTrendLoaderState();
}

class _FdrsCountryTrendLoaderState extends State<_FdrsCountryTrendLoader> {
  final GlobalOverviewDataService _service = sl<GlobalOverviewDataService>();
  late Future<List<({String period, double? value})>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<({String period, double? value})>> _load() async {
    var periods = widget.periodOptions;
    if (periods.isEmpty) {
      periods = await _service.listFdrsPeriods();
    }
    if (periods.isEmpty) return [];
    final chrono = periods.reversed.toList();
    return _service.loadCountryIndicatorSeries(
      indicatorBankId: widget.indicatorBankId,
      locale: widget.locale,
      countryId: widget.countryId,
      periods: chrono,
    );
  }

  void _retry() {
    setState(() {
      _future = _load();
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = widget.theme;
    final l10n = widget.l10n;

    return FutureBuilder<List<({String period, double? value})>>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState == ConnectionState.waiting) {
          return SizedBox(
            height: 220,
            child: Center(
              child: CircularProgressIndicator(
                color: theme.colorScheme.secondary,
              ),
            ),
          );
        }
        if (snap.hasError) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                l10n.homeLandingGlobalLoadError,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.error,
                ),
              ),
              const SizedBox(height: 12),
              TextButton.icon(
                onPressed: _retry,
                icon: const Icon(Icons.refresh_rounded),
                label: Text(l10n.retry),
              ),
            ],
          );
        }
        final raw = snap.data ?? [];
        final withData = raw
            .where((e) => e.value != null && e.value! > 0)
            .toList();
        if (withData.isEmpty) {
          return Text(
            l10n.homeLandingGlobalMapCountryNoData,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          );
        }

        final maxY = withData
            .map((e) => e.value!)
            .reduce(math.max);
        final gridColor = theme.colorScheme.outlineVariant.withValues(
          alpha: theme.brightness == Brightness.dark ? 0.35 : 0.45,
        );
        final lineColor = Color(AppConstants.ifrcRed);

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              l10n.homeLandingGlobalMapCountryTrend,
              style: theme.textTheme.titleSmall?.copyWith(
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            SizedBox(
              height: 220,
              child: LineChart(
                LineChartData(
                  minX: 0,
                  maxX: (withData.length - 1).toDouble(),
                  minY: 0,
                  maxY: maxY > 0 ? maxY * 1.12 : 1,
                  clipData: const FlClipData.all(),
                  lineTouchData: LineTouchData(
                    enabled: true,
                    touchTooltipData: LineTouchTooltipData(
                      getTooltipItems: (touchedSpots) {
                        return touchedSpots.map((s) {
                          final i =
                              s.x.round().clamp(0, withData.length - 1);
                          final p = withData[i];
                          return LineTooltipItem(
                            '${p.period}\n'
                            '${formatFdrsOverviewValue(s.y, widget.locale)}',
                            TextStyle(
                              color: theme.colorScheme.onInverseSurface,
                              fontWeight: FontWeight.w600,
                              fontSize: 12,
                            ),
                          );
                        }).toList();
                      },
                    ),
                  ),
                  gridData: FlGridData(
                    show: true,
                    drawVerticalLine: false,
                    horizontalInterval:
                        maxY > 0 ? (maxY / 4).clamp(1, double.infinity) : 1,
                    getDrawingHorizontalLine: (value) => FlLine(
                      color: gridColor,
                      strokeWidth: 1,
                    ),
                  ),
                  borderData: FlBorderData(show: false),
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
                        interval: maxY > 0
                            ? (maxY / 3).clamp(1, double.infinity)
                            : 1,
                        getTitlesWidget: (value, meta) {
                          if (value < 0 || value > meta.max) {
                            return const SizedBox.shrink();
                          }
                          return Padding(
                            padding: const EdgeInsets.only(right: 6),
                            child: Text(
                              formatFdrsOverviewValue(value, widget.locale),
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
                        reservedSize: 32,
                        getTitlesWidget: (value, meta) {
                          final i = value.toInt();
                          if (i < 0 || i >= withData.length) {
                            return const SizedBox.shrink();
                          }
                          var label = withData[i].period;
                          if (label.length > 10) {
                            label = '${label.substring(0, 9)}…';
                          }
                          return Padding(
                            padding: const EdgeInsets.only(top: 6),
                            child: Text(
                              label,
                              style: theme.textTheme.labelSmall?.copyWith(
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          );
                        },
                      ),
                    ),
                  ),
                  lineBarsData: [
                    LineChartBarData(
                      color: lineColor,
                      barWidth: 3,
                      isStrokeCapRound: true,
                      dotData: FlDotData(
                        show: true,
                        getDotPainter: (spot, percent, bar, index) {
                          return FlDotCirclePainter(
                            radius: 4,
                            color: lineColor,
                            strokeWidth: 1,
                            strokeColor: theme.colorScheme.surface,
                          );
                        },
                      ),
                      spots: [
                        for (var i = 0; i < withData.length; i++)
                          FlSpot(
                            i.toDouble(),
                            withData[i].value!,
                          ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

/// Map stack: tiles + hit-tested bubble or choropleth layer.
class FdrsOverviewMap extends StatefulWidget {
  const FdrsOverviewMap({
    super.key,
    required this.theme,
    required this.visualMode,
    required this.circles,
    required this.choroplethPolygons,
    required this.initialFit,
    this.mapController,
    this.maxZoom = 22,
    this.polygonSimplification = 0,
    this.onCountryIso2Tapped,
    this.notifyParentScrollWhilePointersDown = false,
  });

  final ThemeData theme;
  final FdrsMapVisualMode visualMode;
  final List<CircleMarker<String>> circles;
  final List<Polygon<String>> choroplethPolygons;
  final CameraFit? initialFit;
  final MapController? mapController;
  final double maxZoom;
  final double polygonSimplification;
  final void Function(String iso2)? onCountryIso2Tapped;

  /// When true (embedded home map only), pointer events on the map notify
  /// ancestors so the page scroll view can yield to map pan/pinch.
  final bool notifyParentScrollWhilePointersDown;

  @override
  State<FdrsOverviewMap> createState() => _FdrsOverviewMapState();
}

class _FdrsOverviewMapState extends State<FdrsOverviewMap> {
  final LayerHitNotifier<String> _hitNotifier = ValueNotifier(null);

  @override
  void dispose() {
    _hitNotifier.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    Widget map = ClipRect(
      clipBehavior: Clip.hardEdge,
      child: FlutterMap(
        mapController: widget.mapController,
        options: fdrsWorldMapOptions(
          widget.theme,
          widget.initialFit,
          maxZoom: widget.maxZoom,
          onTap: widget.onCountryIso2Tapped == null
              ? null
              : (_, _) {
                  final hit = _hitNotifier.value;
                  if (hit == null || hit.hitValues.isEmpty) return;
                  HapticFeedback.selectionClick();
                  widget.onCountryIso2Tapped!(hit.hitValues.first);
                },
        ),
        children: [
          ...fdrsWorldMapTiles(widget.theme),
          widget.visualMode == FdrsMapVisualMode.bubble
              ? CircleLayer<String>(
                  hitNotifier: _hitNotifier,
                  circles: widget.circles,
                )
              : PolygonLayer<String>(
                  hitNotifier: _hitNotifier,
                  simplificationTolerance: widget.polygonSimplification,
                  drawInSingleWorld: false,
                  polygons: widget.choroplethPolygons,
                  drawLabelsLast: false,
                  polygonLabels: false,
                ),
        ],
      ),
    );

    if (widget.notifyParentScrollWhilePointersDown) {
      map = FdrsEmbeddedMapPointerNotifier(child: map);
    }
    return map;
  }
}

class FdrsMapModeToggle extends StatelessWidget {
  const FdrsMapModeToggle({
    super.key,
    required this.l10n,
    required this.mode,
    required this.onChanged,
  });

  final AppLocalizations l10n;
  final FdrsMapVisualMode mode;
  final ValueChanged<FdrsMapVisualMode> onChanged;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final isDark = theme.brightness == Brightness.dark;
    final track = cs.surfaceContainerHighest.withValues(
      alpha: isDark ? 0.55 : 0.65,
    );
    final border = cs.outlineVariant.withValues(alpha: isDark ? 0.35 : 0.28);

    Widget pill({
      required FdrsMapVisualMode value,
      required IconData icon,
      required String label,
    }) {
      final selected = mode == value;
      return Expanded(
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: () {
              if (!selected) {
                HapticFeedback.selectionClick();
                onChanged(value);
              }
            },
            borderRadius: BorderRadius.circular(20),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              curve: Curves.easeOutCubic,
              padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 10),
              decoration: BoxDecoration(
                color: selected ? cs.secondaryContainer : Colors.transparent,
                borderRadius: BorderRadius.circular(20),
                boxShadow: selected
                    ? [
                        BoxShadow(
                          color: cs.secondary.withValues(alpha: 0.12),
                          blurRadius: 8,
                          offset: const Offset(0, 2),
                        ),
                      ]
                    : null,
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    icon,
                    size: 18,
                    color: selected
                        ? cs.onSecondaryContainer
                        : cs.onSurfaceVariant,
                  ),
                  const SizedBox(width: 6),
                  Flexible(
                    child: Text(
                      label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.labelLarge?.copyWith(
                        fontWeight: selected
                            ? FontWeight.w700
                            : FontWeight.w500,
                        color: selected
                            ? cs.onSecondaryContainer
                            : cs.onSurfaceVariant,
                        letterSpacing: 0.1,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
    }

    return DecoratedBox(
      decoration: BoxDecoration(
        color: track,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: border, width: 1),
      ),
      child: Padding(
        padding: const EdgeInsets.all(4),
        child: Row(
          children: [
            pill(
              value: FdrsMapVisualMode.bubble,
              icon: Icons.bubble_chart_outlined,
              label: l10n.homeLandingGlobalMapModeBubble,
            ),
            pill(
              value: FdrsMapVisualMode.choropleth,
              icon: Icons.layers_outlined,
              label: l10n.homeLandingGlobalMapModeChoropleth,
            ),
          ],
        ),
      ),
    );
  }
}

/// Horizontally scrollable key-indicator picker (matches website indicator set).
class FdrsIndicatorScrollBar extends StatelessWidget {
  const FdrsIndicatorScrollBar({
    super.key,
    required this.l10n,
    required this.indicatorBankId,
    required this.onSelect,
    this.compact = false,
  });

  final AppLocalizations l10n;
  final int indicatorBankId;
  final ValueChanged<int> onSelect;
  final bool compact;

  static const List<int> _ids = [
    FdrsConstants.indicatorVolunteers,
    FdrsConstants.indicatorStaff,
    FdrsConstants.indicatorBranches,
    FdrsConstants.indicatorLocalUnits,
    FdrsConstants.indicatorBloodDonors,
    FdrsConstants.indicatorFirstAid,
    FdrsConstants.indicatorPeopleReached,
    FdrsConstants.indicatorIncome,
    FdrsConstants.indicatorExpenditure,
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final isDark = theme.brightness == Brightness.dark;
    final accent = cs.secondary;
    final baseLine = cs.outlineVariant.withValues(alpha: isDark ? 0.55 : 0.4);

    return DecoratedBox(
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: baseLine, width: 1)),
      ),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.only(bottom: 2),
        child: Row(
          children: [
            for (var i = 0; i < _ids.length; i++) ...[
              if (i > 0)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 2),
                  child: SizedBox(
                    height: 28,
                    child: Center(
                      child: Container(width: 1, height: 22, color: baseLine),
                    ),
                  ),
                ),
              _IndicatorChip(
                label: fdrsIndicatorTitle(l10n, _ids[i]),
                selected: indicatorBankId == _ids[i],
                accent: accent,
                onSurface: cs.onSurface,
                compact: compact,
                onTap: () {
                  HapticFeedback.selectionClick();
                  onSelect(_ids[i]);
                },
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _IndicatorChip extends StatelessWidget {
  const _IndicatorChip({
    required this.label,
    required this.selected,
    required this.accent,
    required this.onSurface,
    required this.compact,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final Color accent;
  final Color onSurface;
  final bool compact;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(4),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOutCubic,
          padding: EdgeInsets.symmetric(
            vertical: compact ? 9 : 12,
            horizontal: compact ? 10 : 12,
          ),
          decoration: BoxDecoration(
            border: Border(
              bottom: BorderSide(
                color: selected ? accent : Colors.transparent,
                width: selected ? 2.5 : 0,
              ),
            ),
          ),
          child: Text(
            label,
            textAlign: TextAlign.center,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: theme.textTheme.labelLarge?.copyWith(
              fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
              fontSize: compact ? 11 : 12.5,
              height: 1.2,
              color: selected ? accent : onSurface,
            ),
          ),
        ),
      ),
    );
  }
}

class FdrsChoroplethLegend extends StatelessWidget {
  const FdrsChoroplethLegend({
    super.key,
    required this.l10n,
    required this.lowColor,
    required this.highColor,
    this.lowLabel,
    this.highLabel,
  });

  final AppLocalizations l10n;
  final Color lowColor;
  final Color highColor;
  final String? lowLabel;
  final String? highLabel;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final border = theme.colorScheme.outlineVariant.withValues(
      alpha: isDark ? 0.55 : 0.4,
    );
    final lowText = lowLabel ?? l10n.homeLandingGlobalMapLegendLow;
    final highText = highLabel ?? l10n.homeLandingGlobalMapLegendHigh;
    return Material(
      color: theme.colorScheme.surface.withValues(alpha: 0.92),
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(side: BorderSide(color: border)),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              lowText,
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(width: 8),
            Container(
              width: 120,
              height: 8,
              decoration: BoxDecoration(
                border: Border.all(color: border, width: 0.5),
                gradient: LinearGradient(colors: [lowColor, highColor]),
              ),
            ),
            const SizedBox(width: 8),
            Text(
              highText,
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class FdrsWorldMapFullscreenPage extends StatefulWidget {
  const FdrsWorldMapFullscreenPage({
    super.key,
    required this.l10n,
    required this.theme,
    required this.locale,
    required this.initialDataset,
    required this.indicatorBankId,
    required this.selectedPeriod,
    required this.periodOptions,
    required this.visualMode,
    required this.reloadDataset,
  });

  final AppLocalizations l10n;
  final ThemeData theme;
  final String locale;
  final GlobalOverviewDataset initialDataset;
  final int indicatorBankId;
  final String? selectedPeriod;
  final List<String> periodOptions;
  final FdrsMapVisualMode visualMode;
  final Future<GlobalOverviewDataset> Function({
    required int indicatorBankId,
    required String? periodName,
  })
  reloadDataset;

  @override
  State<FdrsWorldMapFullscreenPage> createState() =>
      _FdrsWorldMapFullscreenPageState();
}

class _FdrsWorldMapFullscreenPageState
    extends State<FdrsWorldMapFullscreenPage> {
  late int _indicatorBankId;
  late String? _selectedPeriod;
  late FdrsMapVisualMode _visualMode;
  late Future<GlobalOverviewDataset> _datasetFuture;
  final MapController _mapController = MapController();

  @override
  void initState() {
    super.initState();
    _indicatorBankId = widget.indicatorBankId;
    _selectedPeriod = widget.selectedPeriod;
    _visualMode = widget.visualMode;
    _datasetFuture = Future.value(widget.initialDataset);
  }

  FdrsMapSessionSnapshot _snapshot() => FdrsMapSessionSnapshot(
    indicatorBankId: _indicatorBankId,
    selectedPeriod: _selectedPeriod,
    visualMode: _visualMode,
  );

  Future<void> _reload() {
    final f = widget.reloadDataset(
      indicatorBankId: _indicatorBankId,
      periodName: _selectedPeriod,
    );
    setState(() => _datasetFuture = f);
    return f;
  }

  void _selectIndicator(int id) {
    if (id == _indicatorBankId) return;
    setState(() {
      _indicatorBankId = id;
    });
    _reload();
  }

  void _onPeriodChanged(String? value) {
    if (value == null || value == _selectedPeriod) return;
    setState(() => _selectedPeriod = value);
    _reload();
  }

  void _showFullscreenMapOptionsSheet(
    BuildContext context,
    ThemeData theme,
    AppLocalizations l10n,
  ) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (BuildContext sheetContext) {
        final sheetBottomPad =
            MediaQuery.viewPaddingOf(sheetContext).bottom + 20;
        return NativeModalSheetScaffold(
          theme: theme,
          title: l10n.homeLandingGlobalMapFiltersTitle,
          closeTooltip: MaterialLocalizations.of(
            sheetContext,
          ).closeButtonTooltip,
          maxHeightFraction: 0.88,
          bodyExpands: false,
          onClose: () => Navigator.of(sheetContext).pop(),
          child: ListView(
            shrinkWrap: true,
            physics: const ClampingScrollPhysics(),
            padding: EdgeInsets.fromLTRB(20, 4, 20, sheetBottomPad),
            children: [
              FdrsMapModeToggle(
                l10n: l10n,
                mode: _visualMode,
                onChanged: (m) => setState(() => _visualMode = m),
              ),
              const SizedBox(height: 16),
              SizedBox(
                height: 44,
                child: FdrsIndicatorScrollBar(
                  l10n: l10n,
                  indicatorBankId: _indicatorBankId,
                  onSelect: _selectIndicator,
                  compact: true,
                ),
              ),
              if (widget.periodOptions.isNotEmpty) ...[
                const SizedBox(height: 16),
                if (widget.periodOptions.length > 1)
                  ReportingPeriodPickerField(
                    l10n: l10n,
                    periods: widget.periodOptions,
                    value: _selectedPeriod,
                    onChanged: _onPeriodChanged,
                    compact: false,
                  )
                else
                  Text(
                    l10n.homeLandingGlobalPeriod(
                      _selectedPeriod ?? widget.periodOptions.first,
                    ),
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                  ),
              ],
            ],
          ),
        );
      },
    );
  }

  CameraFit? _cameraFitForDataset(GlobalOverviewDataset data) {
    final cache = CountryCentroidsCache.instance;
    final points = data.geoPoints((iso) => cache[iso]);
    if (points.length >= 2) {
      final bounds = LatLngBounds.fromPoints(
        points.map((p) => p.point).toList(),
      );
      return CameraFit.bounds(
        bounds: bounds,
        padding: const EdgeInsets.fromLTRB(48, 64, 48, 100),
        maxZoom: 4.2,
      );
    }
    if (points.length == 1) {
      return CameraFit.coordinates(
        coordinates: [points.first.point],
        padding: const EdgeInsets.all(80),
        maxZoom: 4.5,
      );
    }
    return null;
  }

  @override
  void dispose() {
    _mapController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = widget.l10n;
    final theme = widget.theme;

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (bool didPop, Object? result) {
        if (!didPop) {
          Navigator.of(context).pop(_snapshot());
        }
      },
      child: FutureBuilder<GlobalOverviewDataset>(
        future: _datasetFuture,
        builder: (context, snap) {
          final showMapOptions =
              snap.hasData && !snap.hasError && snap.data != null;

          return Scaffold(
            backgroundColor: theme.colorScheme.surface,
            appBar: AppBar(
              title: Text(l10n.homeLandingExploreTitle),
              leading: IconButton(
                icon: const Icon(Icons.close),
                tooltip: MaterialLocalizations.of(context).closeButtonTooltip,
                onPressed: () => Navigator.of(context).pop(_snapshot()),
              ),
              actions: [
                if (showMapOptions)
                  IconButton(
                    icon: const Icon(Icons.tune_rounded),
                    tooltip: l10n.homeLandingGlobalMapFiltersTitle,
                    onPressed: () =>
                        _showFullscreenMapOptionsSheet(context, theme, l10n),
                  ),
              ],
            ),
            body: () {
              if (snap.connectionState == ConnectionState.waiting) {
                return Center(
                  child: CircularProgressIndicator(
                    color: theme.colorScheme.secondary,
                  ),
                );
              }
              if (snap.hasError || !snap.hasData) {
                return Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          l10n.homeLandingGlobalLoadError,
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 12),
                        TextButton(
                          onPressed: () => _reload(),
                          child: Text(l10n.retry),
                        ),
                      ],
                    ),
                  ),
                );
              }
              final data = snap.data!;

              final maxVal = data.byCountryId.values.fold<double>(
                0,
                (a, b) => a > b ? a : b,
              );

              final cache = CountryCentroidsCache.instance;
              final circles = <CircleMarker<String>>[];
              for (final p in data.geoPoints((iso) => cache[iso])) {
                final r = maxVal > 0
                    ? 6 + math.sqrt(p.value / maxVal) * 28
                    : 8.0;
                circles.add(
                  CircleMarker<String>(
                    point: p.point,
                    radius: r.clamp(5, 36),
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
              final border = theme.colorScheme.outlineVariant.withValues(
                alpha: isDark ? 0.45 : 0.35,
              );
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

              final initialFit = _cameraFitForDataset(data);
              final indicatorLabel = fdrsIndicatorTitle(l10n, _indicatorBankId);
              final safeBottom = MediaQuery.viewPaddingOf(context).bottom;

              return Stack(
                fit: StackFit.expand,
                clipBehavior: Clip.hardEdge,
                children: [
                  FdrsOverviewMap(
                    theme: theme,
                    visualMode: _visualMode,
                    circles: circles,
                    choroplethPolygons: polys,
                    initialFit: initialFit,
                    mapController: _mapController,
                    maxZoom: 18,
                    polygonSimplification: 0,
                    onCountryIso2Tapped: (iso2) {
                      showFdrsCountryInsightSheet(
                        context: context,
                        l10n: l10n,
                        locale: widget.locale,
                        data: data,
                        iso2: iso2,
                        indicatorLabel: indicatorLabel,
                        indicatorBankId: _indicatorBankId,
                        periodOptions: widget.periodOptions,
                      );
                    },
                  ),
                  PositionedDirectional(
                    bottom: 24 + safeBottom,
                    end: 12,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        _MapToolButton(
                          theme: theme,
                          icon: Icons.add,
                          tooltip: l10n.homeLandingGlobalMapZoomIn,
                          onPressed: () {
                            final z = _mapController.camera.zoom + 1;
                            _mapController.move(
                              _mapController.camera.center,
                              z.clamp(1, 18),
                            );
                          },
                        ),
                        const SizedBox(height: 8),
                        _MapToolButton(
                          theme: theme,
                          icon: Icons.remove,
                          tooltip: l10n.homeLandingGlobalMapZoomOut,
                          onPressed: () {
                            final z = _mapController.camera.zoom - 1;
                            _mapController.move(
                              _mapController.camera.center,
                              z.clamp(1, 18),
                            );
                          },
                        ),
                        const SizedBox(height: 8),
                        _MapToolButton(
                          theme: theme,
                          icon: Icons.center_focus_strong_outlined,
                          tooltip: l10n.homeLandingGlobalMapResetBounds,
                          onPressed: () {
                            final fit = _cameraFitForDataset(data);
                            if (fit != null) {
                              _mapController.fitCamera(fit);
                            }
                          },
                        ),
                      ],
                    ),
                  ),
                  if (_visualMode == FdrsMapVisualMode.choropleth)
                    PositionedDirectional(
                      bottom: 16 + safeBottom,
                      start: 12,
                      child: FdrsChoroplethLegend(
                        l10n: l10n,
                        lowColor: low,
                        highColor: high,
                      ),
                    ),
                ],
              );
            }(),
          );
        },
      ),
    );
  }
}

class _MapToolButton extends StatelessWidget {
  const _MapToolButton({
    required this.theme,
    required this.icon,
    required this.tooltip,
    required this.onPressed,
  });

  final ThemeData theme;
  final IconData icon;
  final String tooltip;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: theme.colorScheme.surface.withValues(alpha: 0.94),
      shape: const CircleBorder(),
      clipBehavior: Clip.antiAlias,
      child: IconButton(
        tooltip: tooltip,
        onPressed: onPressed,
        icon: Icon(icon, size: 22),
        color: theme.colorScheme.secondary,
      ),
    );
  }
}
