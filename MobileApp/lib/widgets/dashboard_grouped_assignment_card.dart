import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

import '../l10n/app_localizations.dart';
import '../models/shared/assignment.dart';
import '../models/shared/project_dashboard_group.dart';
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
    this.showTitle = true,
    this.ignoreOverdue = false,
    this.embedded = false,
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

  /// Project cards draw the project name themselves and hide this title.
  final bool showTitle;

  /// Closed projects stay on the dashboard but are not drawn as overdue.
  final bool ignoreOverdue;

  /// Body only, so a project card can share one border and accent stripe.
  final bool embedded;

  static const double radius = 14;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final isDark = theme.brightness == Brightness.dark;
    final localizations = AppLocalizations.of(context)!;
    final tone = _tone(context, assignment);
    final overdue = !ignoreOverdue && assignment.isOverdue;
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

    final content = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (showTitle)
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
            if (showTitle) const SizedBox(width: 10),
            _StatusChip(label: tone.label, tone: tone),
          ],
        ),
        if (_dueLine(context, localizations, assignment) case final dueLine?) ...[
          const SizedBox(height: 6),
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Flexible(
                child: Text(
                  dueLine,
                  style: IOSTextStyle.footnote(context).copyWith(
                    color: overdue ? cardTone.accent : metaColor,
                    height: 1.3,
                    fontWeight: overdue ? FontWeight.w600 : FontWeight.w400,
                  ),
                ),
              ),
              if (overdue) ...[
                const SizedBox(width: 8),
                _StatusChip(label: localizations.overdue, tone: cardTone),
              ],
            ],
          ),
        ],
        const SizedBox(height: 8),
        LayoutBuilder(
          builder: (context, constraints) {
            final showEnter = showEnterDataButton && onEnterData != null;
            return Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                SizedBox(
                  width: constraints.maxWidth / 3,
                  child: _CompletionMeter(rate: assignment.completionRate),
                ),
                const Spacer(),
                if (_showOfflineRow)
                  _OfflineActions(
                    isDownloading: isDownloadingOfflineForm,
                    hasSnapshot: hasOfflineFormSnapshot,
                    outdated: offlineBundleOutdated,
                    onDownload: onDownloadForOffline,
                    onDetails: onOfflineBundleDetails,
                    color: metaColor,
                  ),
                if (showEnter)
                  _EnterDataButton(
                    label: enterDataButtonText ?? localizations.enterData,
                    color: titleColor,
                    onPressed: onEnterData!,
                  ),
              ],
            );
          },
        ),
      ],
    );

    if (embedded) return content;

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
          child: Stack(
            children: [
              PositionedDirectional(
                start: 0,
                top: 0,
                bottom: 0,
                width: 6,
                child: ColoredBox(color: cardTone.accent),
              ),
              Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(20, 13, 12, 12),
                child: content,
              ),
            ],
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

  static String? _dueLine(
    BuildContext context,
    AppLocalizations localizations,
    Assignment assignment,
  ) {
    final due = assignment.dueDate;
    if (due == null) return null;
    final locale = Localizations.localeOf(context).toString();
    final formatted = DateFormat.yMMMd(locale).format(due.toLocal());
    return '${localizations.dueDate} $formatted';
  }
}

/// Completion percent sitting on a short bar. Fill width is the rate; colour
/// follows the same bands as the Backoffice dashboard (green / amber / red).
class _CompletionMeter extends StatelessWidget {
  const _CompletionMeter({required this.rate});

  final double rate;

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final percent = rate.clamp(0, 100).toDouble();
    final color = _completionColor(percent);
    final track = Theme.of(
      context,
    ).colorScheme.onSurface.withValues(alpha: 0.12);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '${percent.toStringAsFixed(0)}% ${localizations.completed.toLowerCase()}',
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: IOSTextStyle.footnote(
            context,
          ).copyWith(color: color, fontWeight: FontWeight.w700, height: 1.2),
        ),
        const SizedBox(height: 5),
        ClipRRect(
          borderRadius: BorderRadius.circular(3),
          child: LinearProgressIndicator(
            value: percent / 100,
            minHeight: 4,
            backgroundColor: track,
            color: color,
          ),
        ),
      ],
    );
  }
}

Color _completionColor(double percent) {
  if (percent >= 80) return GroupedDashboardPalette.success.accent;
  if (percent >= 25) return GroupedDashboardPalette.pending.accent;
  return GroupedDashboardPalette.danger.accent;
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
    case 'canceled':
      return _toneFor(
        context,
        label == status ? _titleCase(status) : label,
        GroupedDashboardPalette.neutral,
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
      mainAxisSize: MainAxisSize.min,
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

/// One card per project. The active reporting cycle fills the body; other
/// rounds open from the Cycles control. A closed project is not drawn overdue.
class DashboardProjectGroupCard extends StatefulWidget {
  const DashboardProjectGroupCard({
    super.key,
    required this.group,
    this.onOpen,
    this.showEnterDataButton,
    this.enterDataButtonText,
    this.onEnterData,
    this.canSaveOffline,
    this.onDownloadForOffline,
    this.onOfflineBundleDetails,
    this.hasOfflineFormSnapshot,
    this.offlineBundleOutdated,
    this.isDownloadingOfflineForm,
  });

  final ProjectDashboardGroup group;
  final void Function(Assignment assignment)? onOpen;
  final bool Function(Assignment assignment)? showEnterDataButton;
  final String? enterDataButtonText;
  final void Function(Assignment assignment)? onEnterData;

  /// False when this cycle cannot be saved for offline use right now.
  final bool Function(Assignment assignment)? canSaveOffline;
  final void Function(Assignment assignment)? onDownloadForOffline;
  final void Function(Assignment assignment)? onOfflineBundleDetails;
  final bool Function(Assignment assignment)? hasOfflineFormSnapshot;
  final bool Function(Assignment assignment)? offlineBundleOutdated;
  final bool Function(Assignment assignment)? isDownloadingOfflineForm;

  @override
  State<DashboardProjectGroupCard> createState() =>
      _DashboardProjectGroupCardState();
}

class _DashboardProjectGroupCardState extends State<DashboardProjectGroupCard> {
  late int _index;

  @override
  void initState() {
    super.initState();
    _index = _clamped(widget.group.activeCycleIndex);
  }

  @override
  void didUpdateWidget(DashboardProjectGroupCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    final sameCycles = _sameCycleIds(oldWidget.group.cycles, widget.group.cycles);
    if (!sameCycles ||
        oldWidget.group.activeCycleIndex != widget.group.activeCycleIndex) {
      _index = _clamped(widget.group.activeCycleIndex);
    } else {
      _index = _clamped(_index);
    }
  }

  int _clamped(int index) {
    final last = widget.group.cycles.length - 1;
    if (last < 0) return 0;
    return index.clamp(0, last);
  }

  bool _sameCycleIds(List<Assignment> a, List<Assignment> b) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (a[i].id != b[i].id) return false;
    }
    return true;
  }

  @override
  Widget build(BuildContext context) {
    final group = widget.group;
    final cycle = group.cycleAt(_index);
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final isDark = theme.brightness == Brightness.dark;
    final localizations = AppLocalizations.of(context)!;
    final tone = _tone(context, cycle);
    final overdue = !group.projectClosed && cycle.isOverdue;
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
    final period = (cycle.periodName ?? '').trim();
    final showCycles = group.cycles.length > 1;
    final anyLate = group.cycles.any(
      (item) => projectCycleIsLate(item, DateTime.now()),
    );

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Material(
        color: cardColor,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(
            DashboardGroupedAssignmentCard.radius,
          ),
          side: BorderSide(color: borderColor),
        ),
        clipBehavior: Clip.antiAlias,
        child: Stack(
          children: [
            PositionedDirectional(
              start: 0,
              top: 0,
              bottom: 0,
              width: 6,
              child: ColoredBox(color: cardTone.accent),
            ),
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(20, 13, 12, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  InkWell(
                    onTap: widget.onOpen == null
                        ? null
                        : () => widget.onOpen!(cycle),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                  Text(
                    group.displayTitle,
                    style: IOSTextStyle.callout(context).copyWith(
                      fontWeight: FontWeight.w600,
                      height: 1.25,
                      color: titleColor,
                    ),
                  ),
                  if (group.showReference) ...[
                    const SizedBox(height: 2),
                    Text(
                      group.reference,
                      style: IOSTextStyle.caption1(context).copyWith(
                        color: metaColor,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                  const SizedBox(height: 6),
                  Text(
                    period.isEmpty
                        ? localizations.reportingCycle
                        : '${localizations.reportingCycle}: $period',
                    style: IOSTextStyle.footnote(context).copyWith(
                      color: titleColor,
                      height: 1.3,
                    ),
                  ),
                  const SizedBox(height: 4),
                  DashboardGroupedAssignmentCard(
                    assignment: cycle,
                    embedded: true,
                    showTitle: false,
                    ignoreOverdue: group.projectClosed,
                    showEnterDataButton:
                        widget.showEnterDataButton?.call(cycle) ?? false,
                    enterDataButtonText: widget.enterDataButtonText,
                    onEnterData: widget.onEnterData == null
                        ? null
                        : () => widget.onEnterData!(cycle),
                    onDownloadForOffline:
                        widget.onDownloadForOffline != null &&
                            (widget.canSaveOffline?.call(cycle) ?? false)
                        ? () => widget.onDownloadForOffline!(cycle)
                        : null,
                    onOfflineBundleDetails:
                        widget.onOfflineBundleDetails != null &&
                            (widget.hasOfflineFormSnapshot?.call(cycle) ?? false)
                        ? () => widget.onOfflineBundleDetails!(cycle)
                        : null,
                    hasOfflineFormSnapshot:
                        widget.hasOfflineFormSnapshot?.call(cycle) ?? false,
                    offlineBundleOutdated:
                        widget.offlineBundleOutdated?.call(cycle) ?? false,
                    isDownloadingOfflineForm:
                        widget.isDownloadingOfflineForm?.call(cycle) ?? false,
                  ),
                  if (showCycles) ...[
                    const SizedBox(height: 8),
                    Align(
                      alignment: AlignmentDirectional.centerEnd,
                      child: _CyclesButton(
                        count: group.cycles.length,
                        showOverdueDot: anyLate && !group.projectClosed,
                        onPressed: () => _openCycleSheet(context, cycle),
                      ),
                    ),
                  ],
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _openCycleSheet(BuildContext context, Assignment selected) async {
    final localizations = AppLocalizations.of(context)!;
    final group = widget.group;
    final today = DateTime.now();
    final picked = await showModalBottomSheet<int>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) {
        final scheme = Theme.of(sheetContext).colorScheme;
        return SafeArea(
          child: ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.fromLTRB(8, 0, 8, 12),
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
                child: Text(
                  localizations.reportingCycles,
                  style: IOSTextStyle.footnote(sheetContext).copyWith(
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.4,
                    color: scheme.onSurface.withValues(alpha: 0.55),
                  ),
                ),
              ),
              for (var i = 0; i < group.cycles.length; i++)
                _CycleTile(
                  cycle: group.cycles[i],
                  tag: projectCycleTag(
                    index: i,
                    activeIndex: group.activeCycleIndex,
                    cycle: group.cycles[i],
                    today: today,
                  ),
                  selected: group.cycles[i].id == selected.id,
                  onTap: () => Navigator.of(sheetContext).pop(i),
                ),
            ],
          ),
        );
      },
    );
    if (!mounted || picked == null) return;
    setState(() => _index = _clamped(picked));
  }
}

class _CyclesButton extends StatelessWidget {
  const _CyclesButton({
    required this.count,
    required this.showOverdueDot,
    required this.onPressed,
  });

  final int count;
  final bool showOverdueDot;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final scheme = Theme.of(context).colorScheme;
    return Tooltip(
      message: localizations.browseReportingCycles,
      child: OutlinedButton(
      onPressed: () {
        HapticFeedback.selectionClick();
        onPressed();
      },
      style: OutlinedButton.styleFrom(
        visualDensity: VisualDensity.compact,
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        side: BorderSide(color: scheme.outlineVariant),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.layers_outlined, size: 16, color: scheme.onSurface.withValues(alpha: 0.7)),
          const SizedBox(width: 6),
          Text(localizations.cycles),
          const SizedBox(width: 6),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
            decoration: BoxDecoration(
              color: scheme.onSurface.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(999),
            ),
            child: Text(
              '$count',
              style: IOSTextStyle.caption1(context).copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          if (showOverdueDot) ...[
            const SizedBox(width: 6),
            Container(
              width: 8,
              height: 8,
              decoration: const BoxDecoration(
                color: Color(AppConstants.defaultRed),
                shape: BoxShape.circle,
              ),
            ),
          ],
        ],
      ),
      ),
    );
  }
}

class _CycleTile extends StatelessWidget {
  const _CycleTile({
    required this.cycle,
    required this.tag,
    required this.selected,
    required this.onTap,
  });

  final Assignment cycle;
  final String tag;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final period = (cycle.periodName ?? '').trim();
    final title = period.isEmpty ? localizations.cycleFallback : period;
    final due = cycle.dueDate == null
        ? null
        : DateFormat.yMMMd(Localizations.localeOf(context).toString())
            .format(cycle.dueDate!.toLocal());
    final status = localizations.localizeStatus(cycle.status);
    final detail = due == null
        ? status
        : '${localizations.dueDate} $due · $status';

    return ListTile(
      selected: selected,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      title: Text(title),
      subtitle: Text(detail),
      trailing: _CycleTag(tag: tag),
      onTap: () {
        HapticFeedback.selectionClick();
        onTap();
      },
    );
  }
}

class _CycleTag extends StatelessWidget {
  const _CycleTag({required this.tag});

  final String tag;

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final (label, background, foreground) = switch (tag) {
      'current' => (
          localizations.cycleCurrent,
          const Color(0xFFDBEAFE),
          const Color(0xFF1E40AF),
        ),
      'overdue' => (
          localizations.overdue,
          const Color(0xFFFEE2E2),
          const Color(0xFFB91C1C),
        ),
      'upcoming' => (
          localizations.cycleUpcoming,
          const Color(0xFFF3F4F6),
          const Color(0xFF4B5563),
        ),
      _ => (
          localizations.cyclePast,
          const Color(0xFFF3F4F6),
          const Color(0xFF4B5563),
        ),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: IOSTextStyle.caption1(context).copyWith(
          color: foreground,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
