import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;
import 'package:intl/intl.dart';

import '../l10n/app_localizations.dart';
import '../models/shared/assignment.dart';
import '../utils/constants.dart';
import '../utils/ios_constants.dart';
import 'shared/elevated_list_card.dart';

class AssignmentCard extends StatefulWidget {
  final Assignment assignment;
  final VoidCallback onTap;
  final VoidCallback? onEnterData;
  final bool showEnterDataButton;
  final String? enterDataButtonText;
  final Future<void> Function()? onDownloadForOffline;
  /// When a bundle exists, tapping the green offline icon opens details (e.g. sheet).
  final VoidCallback? onOfflineBundleDetails;
  final bool hasOfflineFormSnapshot;
  /// True when the saved bundle is older than the server's published form definition.
  final bool offlineBundleOutdated;
  final bool isDownloadingOfflineForm;

  const AssignmentCard({
    super.key,
    required this.assignment,
    required this.onTap,
    this.onEnterData,
    this.showEnterDataButton = false,
    this.enterDataButtonText,
    this.onDownloadForOffline,
    this.onOfflineBundleDetails,
    this.hasOfflineFormSnapshot = false,
    this.offlineBundleOutdated = false,
    this.isDownloadingOfflineForm = false,
  });

  @override
  State<AssignmentCard> createState() => _AssignmentCardState();
}

class _AssignmentCardState extends State<AssignmentCard>
    with SingleTickerProviderStateMixin {
  /// Repeating 0→1→0 while overdue; drives halo / outline flash.
  AnimationController? _overduePulse;

  @override
  void initState() {
    super.initState();
    if (widget.assignment.isOverdue) {
      _overduePulse = AnimationController(
        vsync: this,
        duration: const Duration(milliseconds: 1350),
      )..repeat(reverse: true);
    }
  }

  @override
  void didUpdateWidget(covariant AssignmentCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    final was = oldWidget.assignment.isOverdue;
    final now = widget.assignment.isOverdue;
    if (was == now) return;
    if (now) {
      _overduePulse ??= AnimationController(
        vsync: this,
        duration: const Duration(milliseconds: 1350),
      )..repeat(reverse: true);
    } else {
      _overduePulse?.dispose();
      _overduePulse = null;
    }
  }

  @override
  void dispose() {
    _overduePulse?.dispose();
    super.dispose();
  }

  /// Scales overdue glow intensity; [pulse] is 0..1 from [_overduePulse].
  static double _flashScale(double? pulse) {
    if (pulse == null) return 1.0;
    return 0.52 + 0.48 * pulse;
  }

  @override
  Widget build(BuildContext context) {
    if (widget.assignment.isOverdue && _overduePulse != null) {
      return AnimatedBuilder(
        animation: _overduePulse!,
        builder: (context, _) => _buildCard(context, _overduePulse!.value),
      );
    }
    return _buildCard(context, null);
  }

  /// [pulse] is null when not flashing; otherwise 0..1 for overdue modulation.
  Widget _buildCard(BuildContext context, double? pulse) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final overdue = widget.assignment.isOverdue;
    final baseSurface = elevatedListCardSurfaceColor(theme);

    final error = scheme.error;
    final isDark = theme.brightness == Brightness.dark;
    final f = _flashScale(pulse);
    final surfaceAlpha = (isDark ? 0.10 : 0.06) +
        (pulse != null ? 0.035 * pulse : 0.0);

    final cardPadEdge = IOSSpacing.mdOf(context) + 2;
    final cardPadBottom = IOSSpacing.smOf(context) + 2;

    Widget card = ElevatedListCard(
      marginBottom: 12,
      borderRadius: IOSDimensions.borderRadiusLargeOf(context),
      backgroundColor: overdue
          ? Color.alphaBlend(
              error.withValues(alpha: surfaceAlpha.clamp(0.0, 1.0)),
              baseSurface,
            )
          : null,
      outlineColor: overdue
          ? error.withValues(alpha: pulse != null ? 0.22 + 0.18 * f : 0.35)
          : scheme.outlineVariant.withValues(alpha: 0.42),
      boxShadow: overdue
          ? <BoxShadow>[
              BoxShadow(
                color: error.withValues(
                  alpha: (isDark ? 0.42 : 0.28) * f,
                ),
                blurRadius: 18,
                spreadRadius: 0,
                offset: const Offset(0, 2),
              ),
              BoxShadow(
                color: error.withValues(
                  alpha: (isDark ? 0.22 : 0.14) * f,
                ),
                blurRadius: 32,
                spreadRadius: 3 + 2 * (pulse ?? 0.5),
              ),
              BoxShadow(
                color: error.withValues(
                  alpha: (isDark ? 0.12 : 0.08) * f,
                ),
                blurRadius: 48,
                spreadRadius: 4 + 3 * (pulse ?? 0.5),
              ),
            ]
          : null,
      padding: EdgeInsets.fromLTRB(
        cardPadEdge,
        cardPadEdge,
        cardPadEdge,
        cardPadBottom,
      ),
      child: FlipListCard(
        frontBuilder: (ctx) => _buildFrontFace(ctx),
        backBuilder: (ctx) => _buildBackFace(ctx),
        footerBuilder: (ctx, flip) {
          if (flip.value < 0.5) return const SizedBox.shrink();
          if (widget.showEnterDataButton && widget.onEnterData != null) {
            return const SizedBox.shrink();
          }
          return _buildBackFooterActions(ctx);
        },
      ),
    );

    // Gentle horizontal + vertical nudge in sync with the pulse (overdue only).
    if (pulse != null) {
      final t = math.sin(pulse * math.pi);
      card = Transform.translate(
        offset: Offset(t * 2.6, t * 0.5),
        child: card,
      );
    }

    return card;
  }

  /// Enter data below the flip (tighter [ListCardFooterActions] than session logs).
  Widget _buildBackFooterActions(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;

    return ListCardFooterActions(
      dividerTopPadding: 10,
      gapAfterDivider: 2,
      child: Padding(
        padding: const EdgeInsets.only(top: 3),
        child: _enterDataActionButton(
          context,
          onPressed: widget.onTap,
          label: widget.enterDataButtonText ?? localizations.enterData,
        ),
      ),
    );
  }

  /// Blue compact action — avoids [TextButton.icon] default label line height (too tall).
  Widget _enterDataActionButton(
    BuildContext context, {
    required VoidCallback onPressed,
    required String label,
  }) {
    final blue = IOSColors.getSystemBlue(context);
    final theme = Theme.of(context);
    return InkWell(
      onTap: onPressed,
      borderRadius: BorderRadius.circular(6),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(2, 2, 2, 0),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Icon(Icons.edit_note_rounded, size: 16, color: blue),
            const SizedBox(width: 4),
            Text(
              label,
              style: theme.textTheme.labelLarge?.copyWith(
                color: blue,
                fontSize: 14,
                height: 1.05,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Color _getCompletionColor(BuildContext context, double completionRate) {
    if (completionRate >= 100) {
      return const Color(AppConstants.successColor);
    } else if (completionRate >= 80) {
      return const Color(AppConstants.successColor);
    } else if (completionRate >= 50) {
      return const Color(AppConstants.warningColor);
    } else if (completionRate >= 25) {
      return const Color(AppConstants.warningColor);
    } else {
      return const Color(AppConstants.errorColor);
    }
  }

  String _formatDate(BuildContext context, DateTime date) {
    final locale = Localizations.localeOf(context);
    if (locale.languageCode == 'ar') {
      DateFormat.useNativeDigitsByDefaultFor('ar', false);
    }
    final dateFormat = DateFormat('MMM d, y', locale.languageCode);
    String formatted = dateFormat.format(date);
    formatted = formatted
        .replaceAll('٠', '0')
        .replaceAll('١', '1')
        .replaceAll('٢', '2')
        .replaceAll('٣', '3')
        .replaceAll('٤', '4')
        .replaceAll('٥', '5')
        .replaceAll('٦', '6')
        .replaceAll('٧', '7')
        .replaceAll('٨', '8')
        .replaceAll('٩', '9');
    return formatted;
  }

  String _formatDateTime(BuildContext context, DateTime date) {
    final locale = Localizations.localeOf(context);
    if (locale.languageCode == 'ar') {
      DateFormat.useNativeDigitsByDefaultFor('ar', false);
    }
    final dateFormat = DateFormat('MMM d, y · HH:mm', locale.languageCode);
    String formatted = dateFormat.format(date.toLocal());
    formatted = formatted
        .replaceAll('٠', '0')
        .replaceAll('١', '1')
        .replaceAll('٢', '2')
        .replaceAll('٣', '3')
        .replaceAll('٤', '4')
        .replaceAll('٥', '5')
        .replaceAll('٦', '6')
        .replaceAll('٧', '7')
        .replaceAll('٨', '8')
        .replaceAll('٩', '9');
    return formatted;
  }

  Widget _assignmentBackDetail(
    BuildContext context, {
    required String label,
    required String value,
    IconData? icon,
    Color? valueColor,
    FontWeight? valueWeight,
  }) {
    if (value.isEmpty) {
      return const SizedBox.shrink();
    }
    final theme = Theme.of(context);
    final muted = theme.colorScheme.onSurface.withValues(alpha: 0.55);
    final valueStyle = IOSTextStyle.footnote(context).copyWith(
      color: valueColor ?? theme.colorScheme.onSurface.withValues(alpha: 0.9),
      fontWeight: valueWeight ?? FontWeight.w500,
      height: 1.3,
    );
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (icon != null) ...[
            Icon(
              icon,
              size: 15,
              color: theme.colorScheme.onSurface.withValues(alpha: 0.55),
            ),
            const SizedBox(width: 8),
          ],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: IOSTextStyle.caption2(context).copyWith(
                    color: muted,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.2,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  value,
                  style: valueStyle,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFrontFace(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final titleText = widget.assignment.periodName != null &&
            widget.assignment.periodName!.isNotEmpty
        ? '${widget.assignment.templateName ?? widget.assignment.name} - ${widget.assignment.periodName}'
        : widget.assignment.templateName ?? widget.assignment.name;

    final hasDueDate = widget.assignment.dueDate != null;

    final canEnter =
        widget.showEnterDataButton && widget.onEnterData != null;
    final hasOfflineExtras = widget.hasOfflineFormSnapshot &&
        widget.onOfflineBundleDetails != null;
    final showDownloadOffline = canEnter &&
        widget.onDownloadForOffline != null &&
        !widget.hasOfflineFormSnapshot;
    final showFooterActionStrip =
        canEnter || hasOfflineExtras || showDownloadOffline;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: EdgeInsets.only(top: IOSSpacing.xsOf(context) / 2),
              child: Icon(
                Icons.assignment_rounded,
                size: 22,
                color: scheme.onSurfaceVariant.withValues(alpha: 0.88),
              ),
            ),
            SizedBox(width: IOSSpacing.mdOf(context)),
            Expanded(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Text(
                      titleText,
                      style: IOSTextStyle.callout(context).copyWith(
                        fontWeight: FontWeight.w600,
                        height: 1.28,
                        color: scheme.onSurface,
                      ),
                    ),
                  ),
                  SizedBox(width: IOSSpacing.smOf(context)),
                  _StatusBadge(status: widget.assignment.status),
                ],
              ),
            ),
          ],
        ),
        SizedBox(height: IOSSpacing.mdOf(context)),
        Wrap(
          spacing: IOSSpacing.sm,
          runSpacing: IOSSpacing.sm - 2,
          children: [
            ListMetricChip(
              label: localizations.completion,
              value: '${widget.assignment.completionRate.toStringAsFixed(0)}%',
              variant: ListMetricChipVariant.completion,
              completionAccent: _getCompletionColor(
                context,
                widget.assignment.completionRate,
              ),
            ),
            ListMetricChip(
              label: hasDueDate ? localizations.dueDate : '',
              value: hasDueDate
                  ? _formatDate(context, widget.assignment.dueDate!)
                  : localizations.noDueDate,
              variant: hasDueDate
                  ? ListMetricChipVariant.dueDate
                  : ListMetricChipVariant.dueDateMissing,
              valueSuffix: hasDueDate && widget.assignment.isOverdue
                  ? localizations.overdue
                  : null,
            ),
          ],
        ),
        ListCardFooterActions(
          dividerTopPadding: 10,
          gapAfterDivider: 2,
          child: Padding(
            padding: const EdgeInsets.only(top: 3),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                if (!showFooterActionStrip)
                  const Spacer()
                else
                  Expanded(
                    child: Align(
                      alignment: AlignmentDirectional.centerStart,
                      child: Wrap(
                        spacing: 2,
                        runSpacing: 4,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: [
                          if (canEnter)
                            _enterDataActionButton(
                              context,
                              onPressed: widget.onEnterData!,
                              label: widget.enterDataButtonText ??
                                  localizations.enterData,
                            ),
                          if (showDownloadOffline)
                            _OfflineFormIconButton(
                              tooltip: localizations.downloadForOffline,
                              icon: Icons.download_for_offline_outlined,
                              busy: widget.isDownloadingOfflineForm,
                              color: scheme.onSurfaceVariant,
                              onPressed: widget.isDownloadingOfflineForm
                                  ? null
                                  : () {
                                      unawaited(
                                        widget.onDownloadForOffline!(),
                                      );
                                    },
                            ),
                          if (widget.hasOfflineFormSnapshot &&
                              widget.onOfflineBundleDetails != null)
                            _OfflineFormIconButton(
                              tooltip: localizations.offlineSavedCopyDetailsTooltip,
                              icon: Icons.offline_pin_rounded,
                              busy: false,
                              color: const Color(AppConstants.successColor),
                              showStaleBadge: widget.offlineBundleOutdated,
                              onPressed: widget.onOfflineBundleDetails,
                            ),
                        ],
                      ),
                    ),
                  ),
                _FlipCardButton(
                  color: scheme.onSurfaceVariant,
                  onPressed: FlipListCardScope.of(context).toggleFlip,
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildBackFace(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final isOverdue = widget.assignment.isOverdue;
    final completionColor =
        _getCompletionColor(context, widget.assignment.completionRate);

    String submittedLine = '';
    if (widget.assignment.showSubmittedByDetails) {
      final submitter = widget.assignment.submittedByUserName?.trim();
      if (submitter != null && submitter.isNotEmpty) {
        if (widget.assignment.submittedAt != null) {
          submittedLine =
              '$submitter\n${localizations.atDatetime(_formatDateTime(context, widget.assignment.submittedAt!))}';
        } else {
          submittedLine = submitter;
        }
      } else if (widget.assignment.submittedAt != null) {
        submittedLine = _formatDateTime(context, widget.assignment.submittedAt!);
      }
    }

    String contributorsValue = '';
    if (widget.assignment.contributorNames.isNotEmpty) {
      contributorsValue = widget.assignment.contributorNames.join(', ');
    }

    final publicLines = <String>[];
    if (widget.assignment.publicSubmissionCount != null &&
        widget.assignment.publicSubmissionCount! > 0) {
      publicLines.add(
        localizations.receivedCountSubmissionsUsingPublicLink(
          widget.assignment.publicSubmissionCount!,
        ),
      );
      if (widget.assignment.latestPublicSubmissionAt != null) {
        publicLines.add(
          localizations.latestDatetime(
            _formatDateTime(context, widget.assignment.latestPublicSubmissionAt!),
          ),
        );
      }
    }
    final publicBlock = publicLines.join('\n');

    final detailTiles = <Widget>[
      if (widget.assignment.assignedAt != null)
        _assignmentBackDetail(
          context,
          label: localizations.assignmentAssignedDate,
          value: _formatDateTime(context, widget.assignment.assignedAt!),
          icon: cupertino.CupertinoIcons.calendar,
        ),
      if (widget.assignment.statusTimestamp != null)
        _assignmentBackDetail(
          context,
          label: localizations.assignmentStatusUpdated,
          value: _formatDateTime(context, widget.assignment.statusTimestamp!),
          icon: cupertino.CupertinoIcons.time,
        ),
      if (widget.assignment.dueDate != null)
        _assignmentBackDetail(
          context,
          label: localizations.dueDate,
          value: _formatDate(context, widget.assignment.dueDate!),
          icon: cupertino.CupertinoIcons.flag,
          valueColor: isOverdue
              ? const Color(AppConstants.errorColor)
              : null,
          valueWeight: isOverdue ? FontWeight.w700 : FontWeight.w500,
        ),
      if (submittedLine.isNotEmpty)
        _assignmentBackDetail(
          context,
          label: localizations.assignmentSubmittedBy,
          value: submittedLine,
          icon: cupertino.CupertinoIcons.paperplane,
        ),
      if (widget.assignment.showApprovedByDetails &&
          widget.assignment.approvedByUserName != null &&
          widget.assignment.approvedByUserName!.trim().isNotEmpty)
        _assignmentBackDetail(
          context,
          label: localizations.assignmentApprovedBy,
          value: widget.assignment.approvedByUserName!.trim(),
          icon: cupertino.CupertinoIcons.check_mark_circled,
        ),
      if (contributorsValue.isNotEmpty)
        _assignmentBackDetail(
          context,
          label: localizations.contributors,
          value: contributorsValue,
          icon: cupertino.CupertinoIcons.person_2,
        )
      else if (widget.assignment.lastModifiedUserName != null &&
          widget.assignment.lastModifiedUserName!.trim().isNotEmpty)
        _assignmentBackDetail(
          context,
          label: localizations.lastModifiedBy,
          value: widget.assignment.lastModifiedUserName!.trim(),
          icon: cupertino.CupertinoIcons.person,
        ),
      if (publicBlock.isNotEmpty)
        _assignmentBackDetail(
          context,
          label: localizations.publicLink,
          value: publicBlock,
          icon: cupertino.CupertinoIcons.globe,
          valueColor: IOSColors.getSystemBlue(context),
          valueWeight: FontWeight.w600,
        ),
    ];

    final colGap = IOSSpacing.smOf(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: EdgeInsets.all(IOSSpacing.smOf(context) + 2),
          decoration: BoxDecoration(
            color: scheme.surfaceContainerHighest.withValues(alpha: 0.45),
            borderRadius: BorderRadius.circular(IOSDimensions.borderRadiusMediumOf(context)),
            border: Border.all(
              color: scheme.outlineVariant.withValues(alpha: 0.35),
              width: 0.5,
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(
                    '${widget.assignment.completionRate.toStringAsFixed(0)}%',
                    style: IOSTextStyle.title3(context).copyWith(
                      color: completionColor,
                    ),
                  ),
                  SizedBox(width: IOSSpacing.xsOf(context) + 2),
                  Text(
                    localizations.completion,
                    style: IOSTextStyle.footnote(context).copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
              SizedBox(height: IOSSpacing.smOf(context)),
              Container(
                height: 4,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(2),
                  color: scheme.outlineVariant.withValues(alpha: 0.25),
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(2),
                  child: LinearProgressIndicator(
                    value: widget.assignment.completionRate / 100,
                    minHeight: 4,
                    backgroundColor: Colors.transparent,
                    valueColor: AlwaysStoppedAnimation<Color>(
                      completionColor,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
        for (var i = 0; i < detailTiles.length; i += 2)
          if (i + 1 >= detailTiles.length)
            detailTiles[i]
          else
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(child: detailTiles[i]),
                SizedBox(width: colGap),
                Expanded(child: detailTiles[i + 1]),
              ],
            ),
      ],
    );
  }
}

/// Avoids [IconButton] default minimum height (~48px), which was stretching the footer row.
class _FlipCardButton extends StatelessWidget {
  const _FlipCardButton({
    required this.color,
    required this.onPressed,
  });

  final Color color;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onPressed,
      borderRadius: BorderRadius.circular(6),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(4, 4, 4, 0),
        child: Icon(Icons.flip_outlined, size: 19, color: color),
      ),
    );
  }
}

class _OfflineFormIconButton extends StatelessWidget {
  const _OfflineFormIconButton({
    required this.tooltip,
    required this.icon,
    required this.color,
    required this.busy,
    this.showStaleBadge = false,
    this.onPressed,
  });

  final String tooltip;
  final IconData icon;
  final Color color;
  final bool busy;
  final bool showStaleBadge;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Tooltip(
      message: tooltip,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(6),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(4, 4, 4, 0),
          child: busy
              ? SizedBox(
                  width: 19,
                  height: 19,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: color,
                  ),
                )
              : SizedBox(
                  width: 22,
                  height: 22,
                  child: Stack(
                    clipBehavior: Clip.none,
                    alignment: Alignment.center,
                    children: [
                      Icon(icon, size: 19, color: color),
                      if (showStaleBadge)
                        Positioned(
                          right: -3,
                          top: -4,
                          child: Container(
                            width: 14,
                            height: 14,
                            decoration: BoxDecoration(
                              color: const Color(AppConstants.warningColor),
                              shape: BoxShape.circle,
                              border: Border.all(
                                color: scheme.surface,
                                width: 1.2,
                              ),
                            ),
                            alignment: Alignment.center,
                            child: const Icon(
                              Icons.priority_high_rounded,
                              size: 10,
                              color: Colors.white,
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
}

class _StatusBadge extends StatelessWidget {
  final String status;

  const _StatusBadge({required this.status});

  Color _getStatusColor(BuildContext context) {
    switch (status.toLowerCase().trim()) {
      case 'approved':
        return const Color(AppConstants.successColor);
      case 'submitted':
        return const Color(0xFF0D9488);
      case 'in progress':
        // Yellow-500 — distinct from Pending (amber / [warningColor]).
        return const Color(0xFFEAB308);
      case 'requires revision':
        return const Color(AppConstants.errorColor);
      case 'pending':
        return const Color(AppConstants.warningColor);
      default:
        return const Color(AppConstants.textSecondary);
    }
  }

  IconData _iconForStatus() {
    switch (status.toLowerCase().trim()) {
      case 'approved':
        return Icons.verified_rounded;
      case 'submitted':
        return Icons.task_alt_rounded;
      case 'in progress':
        return Icons.hourglass_top_rounded;
      case 'requires revision':
        return Icons.edit_note_rounded;
      case 'pending':
        return Icons.schedule_rounded;
      default:
        return Icons.flag_rounded;
    }
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final statusColor = _getStatusColor(context);
    final localizedStatus = localizations.localizeStatus(status);
    final isDark = theme.brightness == Brightness.dark;

    // Tinted fill only (no blend onto grey surfaces — avoids muddy grey in the pill).
    final fill = statusColor.withValues(alpha: isDark ? 0.26 : 0.14);

    final radius = IOSDimensions.borderRadiusMediumOf(context);
    final gap = IOSSpacing.xsOf(context) + 1;

    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: IOSSpacing.xsOf(context) + 4,
        vertical: IOSSpacing.xsOf(context) + 1,
      ),
      decoration: BoxDecoration(
        color: fill,
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(
          color: statusColor.withValues(alpha: isDark ? 0.55 : 0.45),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: statusColor.withValues(alpha: isDark ? 0.18 : 0.12),
            blurRadius: 5,
            offset: const Offset(0, 1),
          ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            _iconForStatus(),
            size: IOSIconSize.scaled(context, 14),
            color: statusColor,
          ),
          SizedBox(width: gap),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 104),
            child: Text(
              localizedStatus,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              softWrap: false,
              style: IOSTextStyle.caption1(context).copyWith(
                color: statusColor,
                fontWeight: FontWeight.w700,
                letterSpacing: 0.15,
                height: 1.15,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
