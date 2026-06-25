import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../../utils/theme_extensions.dart';

List<Color> disaggChartColors(ColorScheme cs) {
  return [
    cs.primary,
    cs.tertiary,
    cs.secondary,
    Color.alphaBlend(cs.primary.withValues(alpha: 0.62), cs.surface),
    Color.alphaBlend(cs.tertiary.withValues(alpha: 0.62), cs.surface),
    Color.alphaBlend(cs.secondary.withValues(alpha: 0.62), cs.surface),
    cs.error,
  ];
}

String disaggCompactAxisLabel(double value) {
  if (!value.isFinite) return '';
  final abs = value.abs();
  if (abs >= 1e9) return '${(value / 1e9).toStringAsFixed(1)}B';
  if (abs >= 1e6) return '${(value / 1e6).toStringAsFixed(1)}M';
  if (abs >= 1e3) return '${(value / 1e3).toStringAsFixed(1)}k';
  final r = value.roundToDouble();
  if ((value - r).abs() < 1e-6) return '${r.toInt()}';
  return value.toStringAsFixed(1);
}

TextStyle? disaggAxisLabelStyle(ThemeData theme) {
  final cs = theme.colorScheme;
  final muted = cs.onSurfaceVariant.withValues(alpha: 0.85);
  return theme.textTheme.labelSmall?.copyWith(
        fontSize: 10,
        height: 1.1,
        color: muted,
      ) ??
      TextStyle(fontSize: 10, height: 1.1, color: muted);
}

Color disaggGridLineColor(ThemeData theme) {
  return theme.colorScheme.outline.withValues(
    alpha: theme.isDarkTheme ? 0.22 : 0.14,
  );
}

SideTitles disaggBottomTitles({
  required ThemeData theme,
  required List<String> labels,
}) {
  return SideTitles(
    showTitles: true,
    reservedSize: 30,
    getTitlesWidget: (value, meta) {
      final index = value.toInt();
      if (index < 0 || index >= labels.length) {
        return const SizedBox.shrink();
      }
      return SideTitleWidget(
        meta: meta,
        space: 6,
        child: Text(
          labels[index],
          style: disaggAxisLabelStyle(theme),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      );
    },
  );
}

SideTitles disaggLeftTitles({required ThemeData theme}) {
  return SideTitles(
    showTitles: true,
    reservedSize: 42,
    getTitlesWidget: (value, meta) {
      if (value < meta.min || value > meta.max) {
        return const SizedBox.shrink();
      }
      return SideTitleWidget(
        meta: meta,
        space: 6,
        child: Text(
          disaggCompactAxisLabel(value),
          style: disaggAxisLabelStyle(theme),
        ),
      );
    },
  );
}
