import 'package:flutter/material.dart';

import '../../l10n/app_localizations.dart';
import '../../models/public/country_international_support.dart';
import '../../models/public/support_flow.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import 'indicator_trend.dart';
import 'support_flow_panel.dart';

/// Institutional → International: bilateral support, staff, and a native flow map.
class CountryInternationalSection extends StatelessWidget {
  const CountryInternationalSection({
    super.key,
    required this.support,
    required this.loading,
    required this.failed,
    required this.isPnsHint,
    required this.onRetry,
  });

  final CountryInternationalSupport? support;
  final bool loading;
  final bool failed;

  /// From the country profile when the international payload has not loaded yet.
  final bool isPnsHint;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    if (loading && support == null) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 24),
        child: Center(
          child: SizedBox(
            width: 28,
            height: 28,
            child: CircularProgressIndicator(strokeWidth: 2.5),
          ),
        ),
      );
    }

    if (failed && support == null) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Column(
          children: [
            Text(
              loc.countryDetailInternationalUnavailable,
              textAlign: TextAlign.center,
              style: TextStyle(color: context.textSecondaryColor),
            ),
            TextButton(
              onPressed: onRetry,
              child: Text(loc.retry),
            ),
          ],
        ),
      );
    }

    final data = support;
    if (data == null) return const SizedBox.shrink();

    final isPns = data.isPns || isPnsHint;
    final summary = data.summary;
    final bars = mergeInternationalFundingBars(
      partners: data.partners,
      staff: data.staffPresence.entries,
    );
    final maxFunding = bars.fold<double>(0, (max, row) {
      return row.funding > max ? row.funding : max;
    });

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          isPns
              ? loc.countryDetailInternationalPnsTitle
              : loc.countryDetailInternationalHostTitle,
          style: theme.textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.w700,
            color: context.navyTextColor,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          isPns
              ? loc.countryDetailInternationalPnsLead
              : loc.countryDetailInternationalHostLead,
          style: theme.textTheme.bodySmall?.copyWith(
            color: context.textSecondaryColor,
            height: 1.35,
          ),
        ),
        if (summary.year != null) ...[
          const SizedBox(height: 4),
          Text(
            loc.countryDetailInternationalYear(summary.year!),
            style: theme.textTheme.labelMedium?.copyWith(
              color: context.textSecondaryColor,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
        const SizedBox(height: 14),
        _SummaryGrid(
          isPns: isPns,
          summary: summary,
          staffTotal: data.staffPresence.staffTotal,
        ),
        if (bars.isNotEmpty) ...[
          const SizedBox(height: 20),
          Text(
            isPns
                ? loc.countryDetailInternationalCountriesSupported
                : loc.countryDetailInternationalSupportingPns,
            style: theme.textTheme.titleSmall?.copyWith(
              fontWeight: FontWeight.w700,
              color: context.navyTextColor,
            ),
          ),
          const SizedBox(height: 8),
          for (final row in bars)
            _FundingBar(
              row: row,
              maxFunding: maxFunding,
              staffLabel: row.staff > 0
                  ? loc.countryDetailInternationalStaffCount(
                      formatStaffCount(row.staff),
                    )
                  : null,
            ),
        ],
        if (!data.hasSupport && bars.isEmpty) ...[
          const SizedBox(height: 16),
          Text(
            loc.countryDetailInternationalEmpty,
            style: TextStyle(color: context.textSecondaryColor),
          ),
        ],
        const SizedBox(height: 20),
        SupportFlowPanel(
          title: isPns
              ? loc.countryDetailInternationalVisualsPns
              : loc.countryDetailInternationalVisualsHost,
          initialYear: summary.year,
          initialPns: isPns ? data.iso3 : null,
          initialRecipient: isPns ? null : data.iso3,
          showNetworkCharts: isPns,
        ),
      ],
    );
  }
}

class _SummaryGrid extends StatelessWidget {
  const _SummaryGrid({
    required this.isPns,
    required this.summary,
    required this.staffTotal,
  });

  final bool isPns;
  final CountryInternationalSummary summary;
  final double staffTotal;

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final partnerLabel = isPns
        ? loc.countryDetailInternationalCountriesSupported
        : loc.countryDetailInternationalSupportingPns;
    final partnerValue = isPns
        ? (summary.countriesSupported?.toString() ?? '—')
        : (summary.supportingPartners?.toString() ?? '—');
    final staffLabel = isPns
        ? loc.countryDetailInternationalStaffPns
        : loc.countryDetailInternationalStaffPresent;
    final staffValue = isPns
        ? (summary.staffPresence > 0 ? summary.staffPresence.toString() : '—')
        : (staffTotal > 0 ? formatStaffCount(staffTotal) : '—');

    Widget tile(String label, String value) => Expanded(
          child: KeyFigureTile(label: label, value: value),
        );

    return Column(
      children: [
        Row(
          children: [
            tile(partnerLabel, partnerValue),
            const SizedBox(width: 10),
            tile(
              loc.countryDetailInternationalFunding,
              formatSupportAmount(summary.funding),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            tile(
              loc.countryDetailInternationalRequirement,
              formatSupportAmount(summary.requirement),
            ),
            const SizedBox(width: 10),
            tile(
              loc.countryDetailInternationalExpenditure,
              formatSupportAmount(summary.expenditure),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            tile(staffLabel, staffValue),
          ],
        ),
      ],
    );
  }
}

class _FundingBar extends StatelessWidget {
  const _FundingBar({
    required this.row,
    required this.maxFunding,
    required this.staffLabel,
  });

  final InternationalFundingBar row;
  final double maxFunding;
  final String? staffLabel;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final fraction = maxFunding <= 0 ? 0.0 : (row.funding / maxFunding).clamp(0.0, 1.0);
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  row.name,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              if (row.funding > 0) ...[
                const SizedBox(width: 8),
                Text(
                  formatSupportAmount(row.funding),
                  style: TextStyle(
                    fontWeight: FontWeight.w800,
                    color: Color(AppConstants.ifrcRed),
                  ),
                ),
              ],
            ],
          ),
          if (row.funding > 0) ...[
            const SizedBox(height: 4),
            ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: SizedBox(
                height: 10,
                child: Stack(
                  children: [
                    const Positioned.fill(child: ColoredBox(color: Color(0x14011E41))),
                    FractionallySizedBox(
                      widthFactor: fraction <= 0 ? 0 : (fraction < 0.04 ? 0.04 : fraction),
                      child: ColoredBox(color: Color(AppConstants.ifrcRed)),
                    ),
                  ],
                ),
              ),
            ),
          ],
          if (staffLabel != null) ...[
            const SizedBox(height: 4),
            Text(
              staffLabel!,
              style: theme.textTheme.bodySmall?.copyWith(
                color: context.textSecondaryColor,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
