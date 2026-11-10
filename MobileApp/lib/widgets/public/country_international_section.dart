import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:intl/intl.dart';

import '../../config/app_config.dart';
import '../../l10n/app_localizations.dart';
import '../../models/public/country_international_support.dart';
import '../../services/webview_service.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import 'indicator_trend.dart';

/// Institutional → International: UPR bilateral support embeds + summary.
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
    final embedUrl = _absoluteEmbedUrl(data.primaryEmbedPath);

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
        _SummaryGrid(isPns: isPns, summary: summary),
        if (data.partners.isNotEmpty) ...[
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
          for (final partner in data.partners.take(8))
            _PartnerRow(partner: partner),
        ],
        if (data.staffPresence.entries.isNotEmpty) ...[
          const SizedBox(height: 20),
          Text(
            isPns
                ? loc.countryDetailInternationalStaffPns
                : loc.countryDetailInternationalStaffHost,
            style: theme.textTheme.titleSmall?.copyWith(
              fontWeight: FontWeight.w700,
              color: context.navyTextColor,
            ),
          ),
          const SizedBox(height: 8),
          for (final entry in data.staffPresence.entries.take(8))
            _StaffRow(entry: entry),
        ],
        if (!data.hasSupport && embedUrl == null) ...[
          const SizedBox(height: 16),
          Text(
            loc.countryDetailInternationalEmpty,
            style: TextStyle(color: context.textSecondaryColor),
          ),
        ],
        if (embedUrl != null) ...[
          const SizedBox(height: 20),
          Text(
            isPns
                ? loc.countryDetailInternationalVisualsPns
                : loc.countryDetailInternationalVisualsHost,
            style: theme.textTheme.titleSmall?.copyWith(
              fontWeight: FontWeight.w700,
              color: context.navyTextColor,
            ),
          ),
          const SizedBox(height: 10),
          _SupportEmbedWebView(
            url: embedUrl,
            tall: isPns,
          ),
        ],
      ],
    );
  }

  static String? _absoluteEmbedUrl(String? path) {
    final raw = path?.trim();
    if (raw == null || raw.isEmpty) return null;
    if (raw.startsWith('http://') || raw.startsWith('https://')) return raw;
    final base = AppConfig.backendUrl.replaceAll(RegExp(r'/$'), '');
    if (raw.startsWith('/')) return '$base$raw';
    return '$base/$raw';
  }
}

class _SummaryGrid extends StatelessWidget {
  const _SummaryGrid({required this.isPns, required this.summary});

  final bool isPns;
  final CountryInternationalSummary summary;

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final partnerLabel = isPns
        ? loc.countryDetailInternationalCountriesSupported
        : loc.countryDetailInternationalSupportingPns;
    final partnerValue = isPns
        ? (summary.countriesSupported?.toString() ?? '—')
        : (summary.supportingPartners?.toString() ?? '—');

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
              _compactMoney(summary.funding),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            tile(
              loc.countryDetailInternationalRequirement,
              _compactMoney(summary.requirement),
            ),
            const SizedBox(width: 10),
            tile(
              loc.countryDetailInternationalExpenditure,
              _compactMoney(summary.expenditure),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            tile(
              isPns
                  ? loc.countryDetailInternationalStaffPns
                  : loc.countryDetailInternationalStaffHost,
              summary.staffPresence > 0
                  ? summary.staffPresence.toString()
                  : '—',
            ),
          ],
        ),
      ],
    );
  }
}

class _PartnerRow extends StatelessWidget {
  const _PartnerRow({required this.partner});

  final CountryInternationalPartner partner;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final funding = partner.funding;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: publicCardDecoration(context),
      child: Row(
        children: [
          Expanded(
            child: Text(
              partner.name,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodyMedium?.copyWith(
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          if (funding != null && funding > 0) ...[
            const SizedBox(width: 8),
            Text(
              _compactMoney(funding),
              style: TextStyle(
                fontWeight: FontWeight.w800,
                color: Color(AppConstants.ifrcRed),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _StaffRow extends StatelessWidget {
  const _StaffRow({required this.entry});

  final CountryInternationalStaffEntry entry;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final loc = AppLocalizations.of(context)!;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: publicCardDecoration(context),
      child: Row(
        children: [
          Expanded(
            child: Text(
              entry.name,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodyMedium?.copyWith(
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          if (entry.staff > 0) ...[
            const SizedBox(width: 8),
            Text(
              loc.countryDetailInternationalStaffCount(_staffCountLabel(entry.staff)),
              style: TextStyle(
                fontWeight: FontWeight.w800,
                color: Color(AppConstants.ifrcRed),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _SupportEmbedWebView extends StatefulWidget {
  const _SupportEmbedWebView({
    required this.url,
    required this.tall,
  });

  final String url;
  final bool tall;

  @override
  State<_SupportEmbedWebView> createState() => _SupportEmbedWebViewState();
}

class _SupportEmbedWebViewState extends State<_SupportEmbedWebView> {
  bool _loading = true;
  bool _failed = false;

  @override
  Widget build(BuildContext context) {
    final height = widget.tall ? 720.0 : 520.0;
    final settings = WebViewService.defaultSettings(allowMixedContent: true);

    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: DecoratedBox(
        decoration: publicCardDecoration(context),
        child: SizedBox(
          height: height,
          width: double.infinity,
          child: Stack(
            children: [
              InAppWebView(
                initialUrlRequest: URLRequest(url: WebUri(widget.url)),
                initialSettings: settings,
                gestureRecognizers: <Factory<OneSequenceGestureRecognizer>>{
                  Factory<OneSequenceGestureRecognizer>(
                    () => EagerGestureRecognizer(),
                  ),
                },
                shouldOverrideUrlLoading: (controller, action) async {
                  final uri = action.request.url;
                  if (uri != null && WebViewService.isUrlAllowed(uri)) {
                    return NavigationActionPolicy.ALLOW;
                  }
                  return NavigationActionPolicy.CANCEL;
                },
                onLoadStart: (controller, url) {
                  if (!mounted) return;
                  setState(() {
                    _loading = true;
                    _failed = false;
                  });
                },
                onLoadStop: (controller, url) async {
                  if (!mounted) return;
                  setState(() => _loading = false);
                  await WebViewService.applyPostCreationSettings(
                    controller,
                    allowMixedContent: true,
                  );
                },
                onReceivedError: (controller, request, error) {
                  if (!mounted) return;
                  if (request.isForMainFrame ?? true) {
                    setState(() {
                      _loading = false;
                      _failed = true;
                    });
                  }
                },
              ),
              if (_loading)
                ColoredBox(
                  color: Theme.of(context)
                      .colorScheme
                      .surface
                      .withValues(alpha: 0.4),
                  child: const Center(
                    child: SizedBox(
                      width: 28,
                      height: 28,
                      child: CircularProgressIndicator(strokeWidth: 2.5),
                    ),
                  ),
                ),
              if (_failed)
                ColoredBox(
                  color: context.cardColor,
                  child: Center(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Text(
                        AppLocalizations.of(context)!
                            .countryDetailInternationalUnavailable,
                        textAlign: TextAlign.center,
                        style: TextStyle(color: context.textSecondaryColor),
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

String _compactMoney(double value) {
  if (value <= 0) return '—';
  return NumberFormat.compactCurrency(symbol: '', decimalDigits: 1)
      .format(value)
      .trim();
}

String _staffCountLabel(double value) {
  if (value <= 0) return '0';
  if (value == value.roundToDouble()) {
    return value.round().toString();
  }
  return NumberFormat.compact().format(value).trim();
}
