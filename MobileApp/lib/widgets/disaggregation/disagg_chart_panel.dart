import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../../l10n/app_localizations.dart';
import '../../models/disaggregation/disaggregation_overview.dart';
import '../../utils/theme_extensions.dart';
import 'disagg_chart_helpers.dart';

class DisaggChartPanel extends StatelessWidget {
  const DisaggChartPanel({
    super.key,
    required this.overview,
    required this.tab,
    required this.loc,
  });

  final DisaggregationOverview overview;
  final DisaggregationChartTab tab;
  final AppLocalizations loc;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final bg = theme.isDarkTheme
        ? cs.surfaceContainerHighest
        : cs.surfaceContainerLow;
    final outline = cs.outline.withValues(
      alpha: theme.isDarkTheme ? 0.35 : 0.18,
    );

    Widget chart;
    String title;
    switch (tab) {
      case DisaggregationChartTab.bySex:
        title = loc.disaggTabBySex;
        chart = _BreakdownBarChart(
          items: overview.bySex,
          theme: theme,
        );
      case DisaggregationChartTab.byAge:
        title = loc.disaggTabByAge;
        chart = _BreakdownBarChart(
          items: overview.byAge,
          theme: theme,
        );
      case DisaggregationChartTab.byCountry:
        title = loc.disaggTabByCountry;
        chart = _CountryBarChart(
          items: overview.byCountry.take(8).toList(),
          theme: theme,
        );
      case DisaggregationChartTab.byRegion:
        title = loc.disaggTabByRegion;
        chart = _RegionBarChart(
          items: overview.byRegion,
          theme: theme,
        );
      case DisaggregationChartTab.trends:
        title = loc.disaggTabTrends;
        chart = _TrendLineChart(
          items: overview.trends,
          theme: theme,
        );
    }

    final hasData = switch (tab) {
      DisaggregationChartTab.bySex => overview.bySex.isNotEmpty,
      DisaggregationChartTab.byAge => overview.byAge.isNotEmpty,
      DisaggregationChartTab.byCountry => overview.byCountry.isNotEmpty,
      DisaggregationChartTab.byRegion => overview.byRegion.isNotEmpty,
      DisaggregationChartTab.trends => overview.trends.length > 1,
    };

    return Container(
      margin: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 10),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: outline),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            title,
            style: theme.textTheme.titleSmall?.copyWith(
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 12),
          if (!hasData)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 32),
              child: Text(
                loc.disaggNoData,
                textAlign: TextAlign.center,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: cs.onSurfaceVariant,
                ),
              ),
            )
          else
            RepaintBoundary(child: chart),
        ],
      ),
    );
  }
}

class DisaggTabSelector extends StatelessWidget {
  const DisaggTabSelector({
    super.key,
    required this.selected,
    required this.onChanged,
    required this.loc,
    required this.countryDetailsAvailable,
  });

  final DisaggregationChartTab selected;
  final ValueChanged<DisaggregationChartTab> onChanged;
  final AppLocalizations loc;
  final bool countryDetailsAvailable;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final geoTab = countryDetailsAvailable
        ? DisaggregationChartTab.byCountry
        : DisaggregationChartTab.byRegion;
    final geoLabel = countryDetailsAvailable
        ? loc.disaggTabByCountry
        : loc.disaggTabByRegion;
    final geoIcon = countryDetailsAvailable
        ? Icons.flag_outlined
        : Icons.public_outlined;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      child: SegmentedButton<DisaggregationChartTab>(
        segments: [
          ButtonSegment(
            value: DisaggregationChartTab.bySex,
            label: Text(loc.disaggTabBySex, overflow: TextOverflow.ellipsis),
            icon: const Icon(Icons.wc_outlined, size: 16),
          ),
          ButtonSegment(
            value: DisaggregationChartTab.byAge,
            label: Text(loc.disaggTabByAge, overflow: TextOverflow.ellipsis),
            icon: const Icon(Icons.cake_outlined, size: 16),
          ),
          ButtonSegment(
            value: geoTab,
            label: Text(geoLabel, overflow: TextOverflow.ellipsis),
            icon: Icon(geoIcon, size: 16),
          ),
          ButtonSegment(
            value: DisaggregationChartTab.trends,
            label: Text(loc.disaggTabTrends, overflow: TextOverflow.ellipsis),
            icon: const Icon(Icons.timeline_outlined, size: 16),
          ),
        ],
        selected: {
          selected == DisaggregationChartTab.byCountry ||
                  selected == DisaggregationChartTab.byRegion
              ? geoTab
              : selected,
        },
        onSelectionChanged: (s) => onChanged(s.first),
        showSelectedIcon: false,
        style: ButtonStyle(
          visualDensity: VisualDensity.compact,
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
          textStyle: WidgetStatePropertyAll<TextStyle?>(
            theme.textTheme.labelSmall,
          ),
        ),
      ),
    );
  }
}

class _BreakdownBarChart extends StatelessWidget {
  const _BreakdownBarChart({
    required this.items,
    required this.theme,
  });

  final List<DisaggregationBreakdownItem> items;
  final ThemeData theme;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) return const SizedBox.shrink();
    final cs = theme.colorScheme;
    final colors = disaggChartColors(cs);
    final labels = items.map((e) => e.category).toList();
    final maxY = items.map((e) => e.value).reduce((a, b) => a > b ? a : b);
    final padY = maxY <= 0 ? 1.0 : maxY * 0.15;

    return SizedBox(
      height: 220,
      child: BarChart(
        BarChartData(
          maxY: maxY + padY,
          gridData: FlGridData(
            show: true,
            drawVerticalLine: false,
            getDrawingHorizontalLine: (_) =>
                FlLine(color: disaggGridLineColor(theme), strokeWidth: 1),
          ),
          borderData: FlBorderData(show: false),
          titlesData: FlTitlesData(
            topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            leftTitles: AxisTitles(sideTitles: disaggLeftTitles(theme: theme)),
            bottomTitles: AxisTitles(
              sideTitles: disaggBottomTitles(theme: theme, labels: labels),
            ),
          ),
          barGroups: [
            for (var i = 0; i < items.length; i++)
              BarChartGroupData(
                x: i,
                barRods: [
                  BarChartRodData(
                    toY: items[i].value,
                    color: colors[i % colors.length],
                    width: 18,
                    borderRadius: const BorderRadius.vertical(
                      top: Radius.circular(6),
                    ),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}

class _CountryBarChart extends StatelessWidget {
  const _CountryBarChart({
    required this.items,
    required this.theme,
  });

  final List<DisaggregationCountryItem> items;
  final ThemeData theme;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) return const SizedBox.shrink();
    final cs = theme.colorScheme;
    final colors = disaggChartColors(cs);
    final labels = items.map((e) => _shortCountry(e.name)).toList();
    final maxY = items.map((e) => e.value).reduce((a, b) => a > b ? a : b);
    final padY = maxY <= 0 ? 1.0 : maxY * 0.15;

    return SizedBox(
      height: 240,
      child: BarChart(
        BarChartData(
          maxY: maxY + padY,
          gridData: FlGridData(
            show: true,
            drawVerticalLine: false,
            getDrawingHorizontalLine: (_) =>
                FlLine(color: disaggGridLineColor(theme), strokeWidth: 1),
          ),
          borderData: FlBorderData(show: false),
          titlesData: FlTitlesData(
            topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            leftTitles: AxisTitles(sideTitles: disaggLeftTitles(theme: theme)),
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 34,
                getTitlesWidget: (value, meta) {
                  final index = value.toInt();
                  if (index < 0 || index >= labels.length) {
                    return const SizedBox.shrink();
                  }
                  return SideTitleWidget(
                    meta: meta,
                    space: 4,
                    child: Transform.rotate(
                      angle: -0.45,
                      child: Text(
                        labels[index],
                        style: disaggAxisLabelStyle(theme),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  );
                },
              ),
            ),
          ),
          barGroups: [
            for (var i = 0; i < items.length; i++)
              BarChartGroupData(
                x: i,
                barRods: [
                  BarChartRodData(
                    toY: items[i].value,
                    color: colors[i % colors.length],
                    width: 16,
                    borderRadius: const BorderRadius.vertical(
                      top: Radius.circular(6),
                    ),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }

  String _shortCountry(String name) {
    if (name.length <= 10) return name;
    return '${name.substring(0, 9)}…';
  }
}

class _RegionBarChart extends StatelessWidget {
  const _RegionBarChart({
    required this.items,
    required this.theme,
  });

  final List<DisaggregationRegionItem> items;
  final ThemeData theme;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) return const SizedBox.shrink();
    final cs = theme.colorScheme;
    final colors = disaggChartColors(cs);
    final labels = items.map((e) => _shortRegion(e.region)).toList();
    final maxY = items.map((e) => e.value).reduce((a, b) => a > b ? a : b);
    final padY = maxY <= 0 ? 1.0 : maxY * 0.15;

    return SizedBox(
      height: 240,
      child: BarChart(
        BarChartData(
          maxY: maxY + padY,
          gridData: FlGridData(
            show: true,
            drawVerticalLine: false,
            getDrawingHorizontalLine: (_) =>
                FlLine(color: disaggGridLineColor(theme), strokeWidth: 1),
          ),
          borderData: FlBorderData(show: false),
          titlesData: FlTitlesData(
            topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            leftTitles: AxisTitles(sideTitles: disaggLeftTitles(theme: theme)),
            bottomTitles: AxisTitles(
              sideTitles: disaggBottomTitles(theme: theme, labels: labels),
            ),
          ),
          barGroups: [
            for (var i = 0; i < items.length; i++)
              BarChartGroupData(
                x: i,
                barRods: [
                  BarChartRodData(
                    toY: items[i].value,
                    color: colors[i % colors.length],
                    width: 22,
                    borderRadius: const BorderRadius.vertical(
                      top: Radius.circular(6),
                    ),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }

  String _shortRegion(String name) {
    if (name.length <= 12) return name;
    return '${name.substring(0, 11)}…';
  }
}

class _TrendLineChart extends StatelessWidget {
  const _TrendLineChart({
    required this.items,
    required this.theme,
  });

  final List<DisaggregationTrendItem> items;
  final ThemeData theme;

  @override
  Widget build(BuildContext context) {
    if (items.length < 2) return const SizedBox.shrink();
    final cs = theme.colorScheme;
    final spots = <FlSpot>[
      for (var i = 0; i < items.length; i++)
        FlSpot(i.toDouble(), items[i].total),
    ];
    final minY = spots.map((s) => s.y).reduce((a, b) => a < b ? a : b);
    final maxY = spots.map((s) => s.y).reduce((a, b) => a > b ? a : b);
    final padY = (maxY - minY).abs() < 1e-6 ? 1.0 : (maxY - minY) * 0.12;
    final labels = items.map((e) => e.period).toList();
    final lineColor = context.linkOnSurfaceColor;

    return SizedBox(
      height: 220,
      child: LineChart(
        LineChartData(
          minX: 0,
          maxX: (items.length - 1).toDouble(),
          minY: minY - padY,
          maxY: maxY + padY,
          gridData: FlGridData(
            show: true,
            drawVerticalLine: false,
            getDrawingHorizontalLine: (_) =>
                FlLine(color: disaggGridLineColor(theme), strokeWidth: 1),
          ),
          borderData: FlBorderData(show: false),
          titlesData: FlTitlesData(
            topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            leftTitles: AxisTitles(sideTitles: disaggLeftTitles(theme: theme)),
            bottomTitles: AxisTitles(
              sideTitles: disaggBottomTitles(theme: theme, labels: labels),
            ),
          ),
          lineBarsData: [
            LineChartBarData(
              spots: spots,
              isCurved: true,
              color: lineColor,
              barWidth: 3,
              dotData: FlDotData(
                show: true,
                getDotPainter: (_, _, _, _) => FlDotCirclePainter(
                  radius: 4,
                  color: lineColor,
                  strokeWidth: 2,
                  strokeColor: cs.surface,
                ),
              ),
              belowBarData: BarAreaData(
                show: true,
                color: lineColor.withValues(alpha: 0.12),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class DisaggCountryCoverageList extends StatelessWidget {
  const DisaggCountryCoverageList({
    super.key,
    required this.items,
    required this.loc,
  });

  final List<DisaggregationCountryItem> items;
  final AppLocalizations loc;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final cs = theme.colorScheme;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            loc.disaggCoverageTitle,
            style: theme.textTheme.titleSmall?.copyWith(
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 10),
          ...items.take(12).map((item) {
            final rate = item.disaggregationRate.clamp(0, 100);
            return Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          item.name,
                          style: theme.textTheme.bodyMedium?.copyWith(
                            fontWeight: FontWeight.w600,
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      Text(
                        '${rate.toStringAsFixed(0)}%',
                        style: theme.textTheme.labelMedium?.copyWith(
                          color: cs.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(4),
                    child: LinearProgressIndicator(
                      value: rate / 100,
                      minHeight: 6,
                      backgroundColor: cs.surfaceContainerHighest,
                      color: cs.primary,
                    ),
                  ),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }
}

class DisaggRegionCoverageList extends StatelessWidget {
  const DisaggRegionCoverageList({
    super.key,
    required this.items,
    required this.loc,
  });

  final List<DisaggregationRegionItem> items;
  final AppLocalizations loc;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final cs = theme.colorScheme;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            loc.disaggRegionCoverageTitle,
            style: theme.textTheme.titleSmall?.copyWith(
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 10),
          ...items.map((item) {
            final rate = item.disaggregationRate.clamp(0, 100);
            return Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          item.region,
                          style: theme.textTheme.bodyMedium?.copyWith(
                            fontWeight: FontWeight.w600,
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      Text(
                        '${rate.toStringAsFixed(0)}%',
                        style: theme.textTheme.labelMedium?.copyWith(
                          color: cs.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(
                    loc.disaggRegionCountryCount(item.countryCount),
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: cs.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 6),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(4),
                    child: LinearProgressIndicator(
                      value: rate / 100,
                      minHeight: 6,
                      backgroundColor: cs.surfaceContainerHighest,
                      color: cs.primary,
                    ),
                  ),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }
}

class DisaggPublicInsightsBanner extends StatelessWidget {
  const DisaggPublicInsightsBanner({
    super.key,
    required this.loc,
    this.onLogin,
  });

  final AppLocalizations loc;
  final VoidCallback? onLogin;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      child: Material(
        color: cs.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(14),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.info_outline, color: cs.primary, size: 20),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      loc.disaggPublicInsightsTitle,
                      style: theme.textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      loc.disaggPublicInsightsBody,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: cs.onSurfaceVariant,
                        height: 1.35,
                      ),
                    ),
                    if (onLogin != null) ...[
                      const SizedBox(height: 8),
                      TextButton(
                        onPressed: onLogin,
                        child: Text(loc.disaggLoginForCountries),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
