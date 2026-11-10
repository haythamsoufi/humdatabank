import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../l10n/app_localizations.dart';
import '../../models/public/country_project.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import 'indicator_trend.dart';

/// Active projects for the country page. Hidden when the country has none.
class CountryProjectsSection extends StatelessWidget {
  const CountryProjectsSection({
    super.key,
    required this.projects,
    required this.failed,
    required this.onRetry,
  });

  /// Null while the request is still in flight.
  final List<CountryProject>? projects;
  final bool failed;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final loaded = projects;
    if (!failed && (loaded == null || loaded.isEmpty)) {
      return const SizedBox.shrink();
    }

    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(top: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            loc.countryDetailProjects,
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w700,
              color: context.navyTextColor,
            ),
          ),
          const SizedBox(height: 12),
          if (failed || loaded == null)
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  loc.countryDetailProjectsUnavailable,
                  style: TextStyle(color: context.textSecondaryColor),
                ),
                TextButton(onPressed: onRetry, child: Text(loc.retry)),
              ],
            )
          else
            for (final project in loaded) ...[
              _ProjectCard(project: project),
              const SizedBox(height: 10),
            ],
        ],
      ),
    );
  }
}

class _ProjectCard extends StatelessWidget {
  const _ProjectCard({required this.project});

  final CountryProject project;

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final locale = Localizations.localeOf(context).toString();
    final dates = _dateRange(project.startDate, project.endDate, locale);
    final tags = [
      if (project.portfolio != null) project.portfolio!,
      if (project.fund != null) project.fund!,
    ];

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: publicCardDecoration(context),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: tags.isEmpty
                    ? const SizedBox.shrink()
                    : Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: [for (final tag in tags) _Tag(label: tag)],
                      ),
              ),
              const SizedBox(width: 8),
              _StatusPill(status: project.status),
            ],
          ),
          if (tags.isNotEmpty) const SizedBox(height: 10),
          Text(
            project.heading,
            style: theme.textTheme.titleSmall?.copyWith(
              fontWeight: FontWeight.w700,
            ),
          ),
          if (project.showsReference) ...[
            const SizedBox(height: 2),
            Text(
              project.reference,
              style: theme.textTheme.bodySmall?.copyWith(
                color: context.textSecondaryColor,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
          if (project.organizationName != null) ...[
            const SizedBox(height: 4),
            Text(
              project.organizationName!,
              style: theme.textTheme.bodySmall?.copyWith(
                color: context.textSecondaryColor,
              ),
            ),
          ],
          if (dates != null) ...[
            const SizedBox(height: 8),
            Text(dates, style: theme.textTheme.bodyMedium),
          ],
          if (project.amountGranted != null) ...[
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: Text(
                    loc.countryDetailProjectAmount,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: context.textSecondaryColor,
                    ),
                  ),
                ),
                Text(
                  '${formatIndicatorValue(project.amountGranted!)} CHF',
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.w800,
                    color: Color(AppConstants.ifrcRed),
                  ),
                ),
              ],
            ),
          ],
          if (project.fundingModality != null) ...[
            const SizedBox(height: 8),
            Text(
              project.fundingModality!,
              style: theme.textTheme.bodySmall?.copyWith(
                color: context.textSecondaryColor,
              ),
            ),
          ],
          if (project.categories != null) ...[
            const SizedBox(height: 4),
            Text(
              project.categories!,
              style: theme.textTheme.bodySmall?.copyWith(
                color: context.textSecondaryColor,
              ),
            ),
          ],
          if (project.plannedOverview != null) ...[
            const SizedBox(height: 10),
            Text(
              project.plannedOverview!,
              style: theme.textTheme.bodyMedium?.copyWith(height: 1.35),
            ),
          ],
        ],
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: context.navyTextColor.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          color: context.navyTextColor,
        ),
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final active = status.toLowerCase() == 'active';
    final color = active ? Color(AppConstants.ifrcRed) : context.navyTextColor;
    final label = switch (status.toLowerCase()) {
      'active' => loc.countryDetailProjectStatusActive,
      'open' => loc.countryDetailProjectStatusOpen,
      _ => status,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          color: color,
        ),
      ),
    );
  }
}

String? _dateRange(String? start, String? end, String locale) {
  final startLabel = _formatMonth(start, locale);
  final endLabel = _formatMonth(end, locale);
  if (startLabel != null && endLabel != null) return '$startLabel – $endLabel';
  return startLabel ?? endLabel;
}

String? _formatMonth(String? iso, String locale) {
  if (iso == null || iso.isEmpty) return null;
  final parts = iso.split('-');
  if (parts.length < 2) return iso;
  final year = int.tryParse(parts[0]);
  final month = int.tryParse(parts[1]);
  final day = parts.length > 2 ? int.tryParse(parts[2]) : 1;
  if (year == null || month == null || day == null) return iso;
  final date = DateTime(year, month, day);
  try {
    return DateFormat.yMMM(locale).format(date);
  } catch (_) {
    return DateFormat.yMMM().format(date);
  }
}
