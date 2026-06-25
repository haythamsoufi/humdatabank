import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../l10n/app_localizations.dart';
import '../../models/disaggregation/disaggregation_overview.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';

class DisaggSummaryCards extends StatelessWidget {
  const DisaggSummaryCards({
    super.key,
    required this.overview,
    required this.loc,
  });

  final DisaggregationOverview overview;
  final AppLocalizations loc;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final numberFormat = NumberFormat.compact(locale: loc.locale.languageCode);

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      child: Row(
        children: [
          Expanded(
            child: _StatCard(
              label: loc.disaggStatTotal,
              value: numberFormat.format(overview.total),
              icon: Icons.groups_outlined,
              accent: cs.primary,
              theme: theme,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: _StatCard(
              label: loc.disaggStatDisaggregationRate,
              value: '${overview.disaggregationRate.toStringAsFixed(1)}%',
              icon: Icons.pie_chart_outline,
              accent: Color(AppConstants.ifrcRed),
              theme: theme,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: _StatCard(
              label: loc.disaggStatRecords,
              value: '${overview.disaggregatedCount}/${overview.recordCount}',
              icon: Icons.fact_check_outlined,
              accent: cs.tertiary,
              theme: theme,
            ),
          ),
        ],
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard({
    required this.label,
    required this.value,
    required this.icon,
    required this.accent,
    required this.theme,
  });

  final String label;
  final String value;
  final IconData icon;
  final Color accent;
  final ThemeData theme;

  @override
  Widget build(BuildContext context) {
    final cs = theme.colorScheme;
    final bg = theme.isDarkTheme
        ? cs.surfaceContainerHighest
        : cs.surfaceContainerLow;
    final outline = cs.outline.withValues(
      alpha: theme.isDarkTheme ? 0.35 : 0.18,
    );

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 12),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: outline),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 18, color: accent),
          const SizedBox(height: 8),
          Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w700,
              color: cs.onSurface,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: theme.textTheme.labelSmall?.copyWith(
              color: cs.onSurfaceVariant,
              height: 1.2,
            ),
          ),
        ],
      ),
    );
  }
}

class DisaggHeroHeader extends StatelessWidget {
  const DisaggHeroHeader({super.key, required this.loc});

  final AppLocalizations loc;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final accent = Color(AppConstants.ifrcRed);

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(16, 12, 16, 8),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(18),
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: theme.isDarkTheme
              ? [
                  accent.withValues(alpha: 0.35),
                  cs.surfaceContainerHigh,
                ]
              : [
                  accent.withValues(alpha: 0.12),
                  cs.surfaceContainerLow,
                ],
        ),
        border: Border.all(
          color: accent.withValues(alpha: theme.isDarkTheme ? 0.45 : 0.22),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.analytics_outlined, color: accent, size: 22),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  loc.disaggregationAnalysis,
                  style: theme.textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            loc.disaggHeroDescription,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: cs.onSurfaceVariant,
              height: 1.35,
            ),
          ),
        ],
      ),
    );
  }
}
