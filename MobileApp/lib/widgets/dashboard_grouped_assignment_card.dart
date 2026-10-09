import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../l10n/app_localizations.dart';
import '../models/shared/assignment.dart';
import '../theme/grouped_dashboard_palette.dart';
import '../utils/constants.dart';
import '../utils/ios_constants.dart';

/// Short uppercase section title used by the grouped dashboard, e.g. "OPEN · 3".
class DashboardSectionLabel extends StatelessWidget {
  const DashboardSectionLabel({super.key, required this.title, this.count});

  final String title;
  final int? count;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final label = count == null
        ? title.toUpperCase()
        : '${title.toUpperCase()}  ·  $count';
    return Text(
      label,
      style: IOSTextStyle.caption1(context).copyWith(
        fontWeight: FontWeight.w700,
        letterSpacing: 0.7,
        color: scheme.onSurface.withValues(alpha: 0.48),
      ),
    );
  }
}

/// One assignment as its own inset grouped card: hairline border, status edge,
/// compact badge, and a single metadata line.
class DashboardGroupedAssignmentCard extends StatelessWidget {
  const DashboardGroupedAssignmentCard({
    super.key,
    required this.assignment,
    this.onTap,
    this.showEnterDataButton = false,
    this.enterDataButtonText,
    this.onEnterData,
    this.onDownloadForOffline,
    this.onOfflineBundleDetails,
    this.hasOfflineFormSnapshot = false,
    this.offlineBundleOutdated = false,
    this.isDownloadingOfflineForm = false,
  });

  final Assignment assignment;
  final VoidCallback? onTap;
  final bool showEnterDataButton;
  final String? enterDataButtonText;
  final VoidCallback? onEnterData;
  final VoidCallback? onDownloadForOffline;
  final VoidCallback? onOfflineBundleDetails;
  final bool hasOfflineFormSnapshot;
  final bool offlineBundleOutdated;
  final bool isDownloadingOfflineForm;

  static const double radius = 14;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final isDark = theme.brightness == Brightness.dark;
    final localizations = AppLocalizations.of(context)!;
    final tone = _tone(context, assignment);
    final overdue = assignment.isOverdue;
    final cardTone = overdue ? _danger(context) : tone;
    final titleColor = isDark
        ? scheme.onSurface
        : const Color(AppConstants.defaultNavy);
    final metaColor = scheme.onSurface.withValues(alpha: 0.55);
    final cardColor = isDark
        ? Color.alphaBlend(
            cardTone.accent.withValues(alpha: 0.22),
            scheme.surfaceContainerHigh,
          )
        : cardTone.background;
    final borderColor = isDark
        ? (overdue
              ? cardTone.accent.withValues(alpha: 0.7)
              : scheme.outlineVariant.withValues(alpha: 0.45))
        : cardTone.border;

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Material(
        color: cardColor,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radius),
          side: BorderSide(color: borderColor),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: IntrinsicHeight(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                ColoredBox(
                  color: cardTone.accent,
                  child: const SizedBox(width: 6),
                ),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(14, 13, 12, 12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: Text(
                                _displayTitle(assignment),
                                style: IOSTextStyle.callout(context).copyWith(
                                  fontWeight: FontWeight.w600,
                                  height: 1.25,
                                  color: titleColor,
                                ),
                              ),
                            ),
                            const SizedBox(width: 10),
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                _StatusChip(label: tone.label, tone: tone),
                                if (overdue) ...[
                                  const SizedBox(height: 4),
                                  _StatusChip(
                                    label: localizations.overdue,
                                    tone: _danger(context),
                                  ),
                                ],
                              ],
                            ),
                          ],
                        ),
                        const SizedBox(height: 6),
                        Text(
                          _metaLine(context, localizations, assignment),
                          style: IOSTextStyle.footnote(
                            context,
                          ).copyWith(color: metaColor, height: 1.3),
                        ),
                        if ((showEnterDataButton && onEnterData != null) ||
                            _showOfflineRow) ...[
                          const SizedBox(height: 4),
                          Row(
                            children: [
                              if (_showOfflineRow)
                                _OfflineActions(
                                  isDownloading: isDownloadingOfflineForm,
                                  hasSnapshot: hasOfflineFormSnapshot,
                                  outdated: offlineBundleOutdated,
                                  onDownload: onDownloadForOffline,
                                  onDetails: onOfflineBundleDetails,
                                  color: metaColor,
                                ),
                              const Spacer(),
                              if (showEnterDataButton && onEnterData != null)
                                _EnterDataButton(
                                  label:
                                      enterDataButtonText ??
                                      localizations.enterData,
                                  color: titleColor,
                                  onPressed: onEnterData!,
                                ),
                            ],
                          ),
                        ],
                      ],
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

  bool get _showOfflineRow =>
      onDownloadForOffline != null ||
      onOfflineBundleDetails != null ||
      isDownloadingOfflineForm ||
      hasOfflineFormSnapshot;

  static String _displayTitle(Assignment assignment) {
    final template = assignment.templateName?.trim();
    final period = assignment.periodName?.trim();
    if (template != null &&
        template.isNotEmpty &&
        period != null &&
        period.isNotEmpty) {
      return '$template — $period';
    }
    return assignment.name;
  }

  static String _metaLine(
    BuildContext context,
    AppLocalizations localizations,
    Assignment assignment,
  ) {
    final percent = '${assignment.completionRate.toStringAsFixed(0)}%';
    final completion = localizations.completion.toLowerCase();
    final parts = <String>['$percent $completion'];
    final due = assignment.dueDate;
    if (due != null) {
      final locale = Localizations.localeOf(context).toString();
      final formatted = DateFormat.yMMMd(locale).format(due.toLocal());
      parts.add('${localizations.dueDate} $formatted');
    }
    return parts.join('  ·  ');
  }
}

class _StatusTone {
  const _StatusTone({
    required this.label,
    required this.foreground,
    required this.background,
    required this.border,
    required this.accent,
  });

  final String label;
  final Color foreground;
  final Color background;
  final Color border;
  final Color accent;
}

_StatusTone _toneFor(
  BuildContext context,
  String label,
  GroupedStatusColors c,
) {
  final isDark = Theme.of(context).brightness == Brightness.dark;
  if (!isDark) {
    return _StatusTone(
      label: label,
      foreground: c.foreground,
      background: c.background,
      border: c.border,
      accent: c.accent,
    );
  }
  return _StatusTone(
    label: label,
    foreground: Color.lerp(c.accent, GroupedDashboardPalette.onFill, 0.5)!,
    background: c.accent.withValues(alpha: 0.18),
    border: c.accent.withValues(alpha: 0.5),
    accent: c.accent,
  );
}

_StatusTone _danger(BuildContext context) => _toneFor(
  context,
  AppLocalizations.of(context)!.overdue,
  GroupedDashboardPalette.danger,
);

String _titleCase(String value) => value
    .split(' ')
    .where((word) => word.isNotEmpty)
    .map((word) => word[0].toUpperCase() + word.substring(1))
    .join(' ');

/// Status to colour mapping matches Backoffice `assignment_status_variant`.
_StatusTone _tone(BuildContext context, Assignment assignment) {
  final localizations = AppLocalizations.of(context)!;
  final status = assignment.status.toLowerCase().trim().replaceAll('_', ' ');
  final label = localizations.localizeStatus(status);

  switch (status) {
    case 'in progress':
      return _toneFor(context, label, GroupedDashboardPalette.pending);
    case 'submitted':
      return _toneFor(context, label, GroupedDashboardPalette.info);
    case 'approved':
      return _toneFor(context, label, GroupedDashboardPalette.success);
    case 'requires revision':
      return _toneFor(context, label, GroupedDashboardPalette.warning);
    case 'sent for review':
      return _toneFor(
        context,
        label == status ? _titleCase(status) : label,
        GroupedDashboardPalette.review,
      );
    case 'cancelled':
      return _toneFor(
        context,
        label == status ? _titleCase(status) : label,
        GroupedDashboardPalette.danger,
      );
    default:
      return _toneFor(
        context,
        label == status ? _titleCase(status) : label,
        GroupedDashboardPalette.neutral,
      );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.label, required this.tone});

  final String label;
  final _StatusTone tone;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: tone.background,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: tone.border),
      ),
      child: Text(
        label,
        style: IOSTextStyle.caption2(context).copyWith(
          fontWeight: FontWeight.w700,
          color: tone.foreground,
          height: 1.1,
        ),
      ),
    );
  }
}

class _EnterDataButton extends StatelessWidget {
  const _EnterDataButton({
    required this.label,
    required this.color,
    required this.onPressed,
  });

  final String label;
  final Color color;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: onPressed,
      style: TextButton.styleFrom(
        foregroundColor: color,
        visualDensity: VisualDensity.compact,
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 0),
        minimumSize: const Size(0, 32),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            style: IOSTextStyle.footnote(
              context,
            ).copyWith(fontWeight: FontWeight.w600, color: color),
          ),
          Icon(Icons.chevron_right_rounded, size: 18, color: color),
        ],
      ),
    );
  }
}

class _OfflineActions extends StatelessWidget {
  const _OfflineActions({
    required this.isDownloading,
    required this.hasSnapshot,
    required this.outdated,
    required this.onDownload,
    required this.onDetails,
    required this.color,
  });

  final bool isDownloading;
  final bool hasSnapshot;
  final bool outdated;
  final VoidCallback? onDownload;
  final VoidCallback? onDetails;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    return Row(
      children: [
        if (isDownloading)
          const SizedBox(
            width: 16,
            height: 16,
            child: CircularProgressIndicator(strokeWidth: 2),
          )
        else if (onDownload != null && (!hasSnapshot || outdated))
          IconButton(
            visualDensity: VisualDensity.compact,
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
            tooltip: localizations.downloadForOffline,
            icon: Icon(Icons.download_rounded, size: 18, color: color),
            onPressed: onDownload,
          ),
        if (hasSnapshot)
          IconButton(
            visualDensity: VisualDensity.compact,
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
            tooltip: localizations.offlineFormSaved,
            icon: Icon(
              outdated ? Icons.cloud_off_rounded : Icons.cloud_done_rounded,
              size: 18,
              color: outdated ? const Color(AppConstants.defaultRed) : color,
            ),
            onPressed: onDetails,
          ),
      ],
    );
  }
}
