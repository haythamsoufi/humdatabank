import 'package:flutter/material.dart';

import '../../l10n/app_localizations.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import 'indicator_trend.dart';

/// Active IFRC GO emergencies for a country, or operations for a region.
class GoOperationsSnapshot {
  final bool available;
  final bool supported;
  final int activeDrefs;
  final int activeAppeals;
  final int peopleTargeted;
  final double amountRequested;
  final double amountFunded;
  final List<GoOperation> operations;
  final List<GoCountryOperations> byCountry;

  const GoOperationsSnapshot({
    required this.available,
    required this.supported,
    required this.activeDrefs,
    required this.activeAppeals,
    required this.peopleTargeted,
    required this.amountRequested,
    required this.amountFunded,
    required this.operations,
    required this.byCountry,
  });

  factory GoOperationsSnapshot.fromJson(Map<String, dynamic> json) {
    final summary = Map<String, dynamic>.from(json['summary'] as Map? ?? const {});
    return GoOperationsSnapshot(
      available: json['available'] != false,
      supported: json['supported'] != false,
      activeDrefs: _whole(summary['active_drefs']),
      activeAppeals: _whole(summary['active_appeals']),
      peopleTargeted: _whole(summary['people_targeted']),
      amountRequested: _number(summary['amount_requested']),
      amountFunded: _number(summary['amount_funded']),
      operations: _mapList(json['operations']).map(GoOperation.fromJson).toList(),
      byCountry:
          _mapList(json['by_country']).map(GoCountryOperations.fromJson).toList(),
    );
  }

  bool get hasActiveOperations => activeDrefs + activeAppeals > 0 || operations.isNotEmpty;
}

class GoOperation {
  final String name;
  final String appealType;
  final String? disasterType;
  final String? countryName;
  final int peopleTargeted;
  final double amountRequested;
  final double amountFunded;

  const GoOperation({
    required this.name,
    required this.appealType,
    required this.peopleTargeted,
    required this.amountRequested,
    required this.amountFunded,
    this.disasterType,
    this.countryName,
  });

  factory GoOperation.fromJson(Map<String, dynamic> json) {
    return GoOperation(
      name: json['name']?.toString() ?? '',
      appealType: json['appeal_type']?.toString() ?? '',
      disasterType: json['disaster_type']?.toString(),
      countryName: json['country_name']?.toString(),
      peopleTargeted: _whole(json['people_targeted']),
      amountRequested: _number(json['amount_requested']),
      amountFunded: _number(json['amount_funded']),
    );
  }

  double get fundingRatio {
    if (amountRequested <= 0) return 0;
    final ratio = amountFunded / amountRequested;
    if (ratio < 0) return 0;
    if (ratio > 1) return 1;
    return ratio;
  }
}

class GoCountryOperations {
  final String name;
  final int operations;
  final int peopleTargeted;

  const GoCountryOperations({
    required this.name,
    required this.operations,
    required this.peopleTargeted,
  });

  factory GoCountryOperations.fromJson(Map<String, dynamic> json) {
    return GoCountryOperations(
      name: json['name']?.toString() ?? '',
      operations: _whole(json['operations']),
      peopleTargeted: _whole(json['people_targeted']),
    );
  }
}

/// Emergencies block for the country page, or operations block for a region.
class GoOperationsSection extends StatelessWidget {
  const GoOperationsSection({
    super.key,
    this.title,
    required this.snapshot,
    required this.loading,
    required this.failed,
    required this.onRetry,
    this.showCountries = false,
  });

  /// Omitted when a parent tab already names this block.
  final String? title;
  final GoOperationsSnapshot? snapshot;
  final bool loading;
  final bool failed;
  final VoidCallback onRetry;
  final bool showCountries;

  @override
  Widget build(BuildContext context) {
    if (snapshot != null && !snapshot!.supported) return const SizedBox.shrink();
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    final heading = title;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (heading != null && heading.isNotEmpty) ...[
          Text(
            heading,
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w700,
              color: context.navyTextColor,
            ),
          ),
          const SizedBox(height: 12),
        ],
        if (loading)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Center(
              child: SizedBox(
                width: 24,
                height: 24,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            ),
          )
        else if (failed || snapshot == null || !snapshot!.available)
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                loc.emergenciesUnavailable,
                style: TextStyle(color: context.textSecondaryColor),
              ),
              TextButton(onPressed: onRetry, child: Text(loc.retry)),
            ],
          )
        else if (!snapshot!.hasActiveOperations)
          Text(
            loc.emergenciesNone,
            style: TextStyle(color: context.textSecondaryColor),
          )
        else ...[
          _summary(context, loc, snapshot!),
          const SizedBox(height: 12),
          if (showCountries && snapshot!.byCountry.isNotEmpty) ...[
            _countryBars(context, loc, snapshot!.byCountry),
            const SizedBox(height: 4),
          ],
          for (final operation in snapshot!.operations) ...[
            _OperationRow(operation: operation),
            const SizedBox(height: 8),
          ],
        ],
      ],
    );
  }

  Widget _summary(BuildContext context, AppLocalizations loc, GoOperationsSnapshot data) {
    final coverage = data.amountRequested <= 0
        ? null
        : '${(100 * data.amountFunded / data.amountRequested).round()}%';
    return Column(
      children: [
        Row(
          children: [
            Expanded(
              child: KeyFigureTile(
                label: loc.emergenciesActiveDrefs,
                value: '${data.activeDrefs}',
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: KeyFigureTile(
                label: loc.emergenciesActiveAppeals,
                value: '${data.activeAppeals}',
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(
              child: KeyFigureTile(
                label: loc.emergenciesPeopleTargeted,
                value: formatIndicatorValue(data.peopleTargeted.toDouble()),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: KeyFigureTile(
                label: loc.emergenciesFunding,
                value: coverage ?? '—',
                caption: data.amountRequested <= 0
                    ? null
                    : loc.emergenciesFundedOf(
                        _formatChf(data.amountFunded),
                        _formatChf(data.amountRequested),
                      ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _countryBars(
    BuildContext context,
    AppLocalizations loc,
    List<GoCountryOperations> countries,
  ) {
    final maxPeople = countries.fold<int>(
      1,
      (max, row) => row.peopleTargeted > max ? row.peopleTargeted : max,
    );
    final theme = Theme.of(context);
    final red = Color(AppConstants.ifrcRed);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          loc.emergenciesByCountry,
          style: theme.textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 8),
        for (final row in countries) ...[
          Row(
            children: [
              Expanded(
                child: Text(
                  row.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
                ),
              ),
              Text(
                formatIndicatorValue(row.peopleTargeted.toDouble()),
                style: theme.textTheme.bodySmall?.copyWith(color: context.textSecondaryColor),
              ),
            ],
          ),
          const SizedBox(height: 4),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: row.peopleTargeted / maxPeople,
              minHeight: 8,
              backgroundColor: context.navyBackgroundColor(opacity: 0.08),
              color: red,
            ),
          ),
          const SizedBox(height: 10),
        ],
      ],
    );
  }
}

class _OperationRow extends StatelessWidget {
  const _OperationRow({required this.operation});

  final GoOperation operation;

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final meta = [
      if (operation.disasterType != null && operation.disasterType!.isNotEmpty)
        operation.disasterType!,
      if (operation.countryName != null && operation.countryName!.isNotEmpty)
        operation.countryName!,
      if (operation.peopleTargeted > 0)
        formatIndicatorValue(operation.peopleTargeted.toDouble()),
    ].join(' · ');

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: publicCardDecoration(context),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  operation.name,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w700),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                operation.appealType,
                style: theme.textTheme.labelSmall?.copyWith(
                  color: Color(AppConstants.ifrcRed),
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          if (meta.isNotEmpty) ...[
            const SizedBox(height: 2),
            Text(
              meta,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodySmall?.copyWith(color: context.textSecondaryColor),
            ),
          ],
          if (operation.amountRequested > 0) ...[
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: operation.fundingRatio,
                minHeight: 8,
                backgroundColor: context.navyBackgroundColor(opacity: 0.08),
                color: Color(AppConstants.ifrcRed),
              ),
            ),
            const SizedBox(height: 4),
            Text(
              loc.emergenciesFundedOf(
                _formatChf(operation.amountFunded),
                _formatChf(operation.amountRequested),
              ),
              style: theme.textTheme.labelSmall?.copyWith(color: context.textSecondaryColor),
            ),
          ],
        ],
      ),
    );
  }
}

String _formatChf(double value) {
  final abs = value.abs();
  if (abs >= 1000000000) return '${(value / 1000000000).toStringAsFixed(1)}B';
  if (abs >= 1000000) return '${(value / 1000000).toStringAsFixed(1)}M';
  if (abs >= 1000) return '${(value / 1000).toStringAsFixed(0)}K';
  return formatIndicatorValue(value);
}

int _whole(Object? raw) => _number(raw).round();

double _number(Object? raw) {
  if (raw is num) return raw.toDouble();
  return double.tryParse(raw?.toString() ?? '') ?? 0;
}

List<Map<String, dynamic>> _mapList(Object? raw) => raw is List
    ? raw.whereType<Map>().map((row) => Map<String, dynamic>.from(row)).toList()
    : const [];
