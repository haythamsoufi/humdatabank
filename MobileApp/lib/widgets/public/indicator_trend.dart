import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

import '../../l10n/app_localizations.dart';
import '../../models/public/country_profile.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../disaggregation/disagg_chart_helpers.dart';

/// Server keys of the featured indicators, in display order.
const List<String> keyIndicatorOrder = [
  'volunteers',
  'staff',
  'branches',
  'local_units',
  'blood_donors',
  'first_aid',
  'people_reached',
  'income',
  'expenditure',
];

String keyIndicatorLabel(String key, AppLocalizations loc) {
  switch (key) {
    case 'volunteers':
      return loc.homeLandingGlobalIndicatorVolunteers;
    case 'staff':
      return loc.homeLandingGlobalIndicatorStaff;
    case 'branches':
      return loc.homeLandingGlobalIndicatorBranches;
    case 'local_units':
      return loc.homeLandingGlobalIndicatorLocalUnits;
    case 'blood_donors':
      return loc.homeLandingGlobalIndicatorBloodDonors;
    case 'first_aid':
      return loc.homeLandingGlobalIndicatorFirstAid;
    case 'people_reached':
      return loc.homeLandingGlobalIndicatorPeopleReached;
    case 'income':
      return loc.homeLandingGlobalIndicatorIncome;
    case 'expenditure':
      return loc.homeLandingGlobalIndicatorExpenditure;
    default:
      return key;
  }
}

String formatIndicatorValue(double value) {
  final rounded = value.roundToDouble();
  final isWhole = (value - rounded).abs() < 1e-6;
  return NumberFormat.decimalPattern().format(isWhole ? rounded : value);
}

BoxDecoration publicCardDecoration(BuildContext context) => BoxDecoration(
      color: context.cardColor,
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: context.borderColor),
    );

/// Card with a label, a large value and an optional caption (e.g. period).
class KeyFigureTile extends StatelessWidget {
  const KeyFigureTile({
    super.key,
    required this.label,
    required this.value,
    this.caption,
  });

  final String label;
  final String value;
  final String? caption;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      decoration: publicCardDecoration(context),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: theme.textTheme.bodySmall
                ?.copyWith(color: context.textSecondaryColor),
          ),
          const SizedBox(height: 4),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: AlignmentDirectional.centerStart,
            child: Text(
              value,
              style: TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w800,
                color: Color(AppConstants.ifrcRed),
              ),
            ),
          ),
          if (caption != null)
            Text(
              caption!,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.labelSmall
                  ?.copyWith(color: context.textSecondaryColor),
            ),
        ],
      ),
    );
  }
}

/// Full-bleed screen body with a back button floating over the top-left corner.
class HeroScreenFrame extends StatelessWidget {
  const HeroScreenFrame({
    super.key,
    required this.child,
    this.heroVisible = true,
  });

  final Widget child;

  /// When true the status bar sits over a dark hero, so its icons are light.
  final bool heroVisible;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final lightIcons = heroVisible || isDark;
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: lightIcons ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark,
      child: Stack(
        children: [
          Positioned.fill(child: child),
          PositionedDirectional(
            top: MediaQuery.paddingOf(context).top + 8,
            start: 8,
            child: Material(
              color: Colors.black38,
              shape: const CircleBorder(),
              child: IconButton(
                icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
                color: Colors.white,
                tooltip: MaterialLocalizations.of(context).backButtonTooltip,
                onPressed: () => Navigator.of(context).maybePop(),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Height of a hero banner: [bodyHeight] plus the status bar inset it extends under.
double heroHeight(BuildContext context, {double bodyHeight = 180}) =>
    bodyHeight + MediaQuery.paddingOf(context).top;

const String peopleReachedGroup = 'people_reached';

/// One People reached indicator, shown as a sub chip under its sector heading.
class ReachChoice {
  const ReachChoice({
    required this.key,
    required this.label,
    required this.section,
    required this.order,
  });

  final String key;
  final String label;
  final String section;
  final int order;
}

/// People reached indicators in server order; labels are short English names when available.
List<ReachChoice> buildReachChoices(
  Iterable<KeyIndicatorInfo> indicators,
  AppLocalizations loc,
) {
  final isEnglish = loc.locale.languageCode == 'en';
  final choices = [
    for (final indicator in indicators)
      if (indicator.group == peopleReachedGroup && indicator.key != null)
        ReachChoice(
          key: indicator.key!,
          label: (isEnglish
                  ? loc.reachIndicatorShortLabel(indicator.key!)
                  : null) ??
              indicator.name,
          section: indicator.sector ?? loc.homeLandingGlobalIndicatorPeopleReached,
          order: indicator.groupOrder ?? 0,
        ),
  ]..sort((a, b) => a.order.compareTo(b.order));
  return choices;
}

/// Chips for the headline indicators; People reached opens sub chips grouped by sector.
class KeyIndicatorSelector extends StatelessWidget {
  const KeyIndicatorSelector({
    super.key,
    required this.singleKeys,
    required this.reachChoices,
    required this.selectedKey,
    required this.onSelected,
  });

  /// Headline keys that have data, e.g. `volunteers`.
  final Set<String> singleKeys;
  final List<ReachChoice> reachChoices;
  final String selectedKey;
  final ValueChanged<String> onSelected;

  Widget _chip(
    BuildContext context, {
    required String label,
    required bool selected,
    required VoidCallback onTap,
    double fontSize = 13,
  }) {
    return ChoiceChip(
      label: Text(label),
      selected: selected,
      selectedColor: Color(AppConstants.ifrcRed),
      showCheckmark: false,
      labelStyle: TextStyle(
        color: selected ? Colors.white : context.textColor,
        fontWeight: FontWeight.w600,
        fontSize: fontSize,
      ),
      onSelected: (_) => onTap(),
    );
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final reachSelected = reachChoices.any((c) => c.key == selectedKey);
    final topKeys = [
      for (final key in keyIndicatorOrder)
        if (key == peopleReachedGroup
            ? reachChoices.isNotEmpty
            : singleKeys.contains(key))
          key,
    ];

    final sections = <String, List<ReachChoice>>{};
    for (final choice in reachChoices) {
      sections.putIfAbsent(choice.section, () => []).add(choice);
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          height: 40,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: topKeys.length,
            separatorBuilder: (_, _) => const SizedBox(width: 8),
            itemBuilder: (_, i) {
              final key = topKeys[i];
              final isGroup = key == peopleReachedGroup;
              return _chip(
                context,
                label: keyIndicatorLabel(key, loc),
                selected: isGroup ? reachSelected : key == selectedKey,
                onTap: () {
                  if (!isGroup) return onSelected(key);
                  if (!reachSelected) onSelected(reachChoices.first.key);
                },
              );
            },
          ),
        ),
        if (reachSelected)
          for (final entry in sections.entries) ...[
            Padding(
              padding: const EdgeInsets.only(top: 12, bottom: 4),
              child: Text(
                entry.key,
                style: theme.textTheme.labelLarge?.copyWith(
                  fontWeight: FontWeight.w700,
                  color: context.navyTextColor,
                ),
              ),
            ),
            Wrap(
              spacing: 8,
              runSpacing: 4,
              children: [
                for (final choice in entry.value)
                  _chip(
                    context,
                    label: choice.label,
                    selected: choice.key == selectedKey,
                    fontSize: 12,
                    onTap: () => onSelected(choice.key),
                  ),
              ],
            ),
          ],
      ],
    );
  }
}

/// Line chart of an indicator over reporting periods (oldest first, at least two points).
class IndicatorTrendChart extends StatelessWidget {
  const IndicatorTrendChart({super.key, required this.series});

  final List<CountryIndicatorPoint> series;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final lineColor = Color(AppConstants.ifrcRed);
    final spots = <FlSpot>[
      for (var i = 0; i < series.length; i++)
        FlSpot(i.toDouble(), series[i].value),
    ];
    final minY = spots.map((s) => s.y).reduce((a, b) => a < b ? a : b);
    final maxY = spots.map((s) => s.y).reduce((a, b) => a > b ? a : b);
    final padY = (maxY - minY).abs() < 1e-6 ? 1.0 : (maxY - minY) * 0.12;

    return SizedBox(
      height: 200,
      child: LineChart(
        LineChartData(
          minX: 0,
          maxX: (spots.length - 1).toDouble(),
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
            topTitles:
                const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles:
                const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            leftTitles: AxisTitles(sideTitles: disaggLeftTitles(theme: theme)),
            bottomTitles: AxisTitles(
              sideTitles: disaggBottomTitles(
                theme: theme,
                labels: [for (final p in series) p.period],
              ),
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
                  strokeColor: theme.colorScheme.surface,
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
