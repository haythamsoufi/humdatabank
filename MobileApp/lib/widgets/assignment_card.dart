import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;
import '../models/shared/assignment.dart';
import '../utils/constants.dart';
import '../utils/theme_extensions.dart';
import '../utils/ios_constants.dart';
import '../l10n/app_localizations.dart';
import 'package:intl/intl.dart';

class AssignmentCard extends StatelessWidget {
  final Assignment assignment;
  final VoidCallback onTap;
  final VoidCallback? onEnterData;
  final bool showEnterDataButton;
  final String? enterDataButtonText;
  final bool isExpanded;
  final VoidCallback? onToggleExpand;

  const AssignmentCard({
    super.key,
    required this.assignment,
    required this.onTap,
    this.onEnterData,
    this.showEnterDataButton = false,
    this.enterDataButtonText,
    this.isExpanded = false,
    this.onToggleExpand,
  });

  @override
  Widget build(BuildContext context) {
    if (!isExpanded) {
      return _buildCompactView(context);
    }
    return _buildExpandedView(context);
  }

  // Get completion color based on percentage ranges
  Color _getCompletionColor(BuildContext context, double completionRate) {
    if (completionRate >= 100) {
      // 100% - Green (success)
      return const Color(AppConstants.successColor);
    } else if (completionRate >= 80) {
      // 80-99% - Light green/teal
      return const Color(0xFF10B981); // emerald-500
    } else if (completionRate >= 50) {
      // 50-79% - Yellow/Orange (warning)
      return const Color(AppConstants.warningColor);
    } else if (completionRate >= 25) {
      // 25-49% - Orange/Red
      return const Color(0xFFF97316); // orange-500
    } else {
      // < 25% - Red (error)
      return const Color(AppConstants.errorColor);
    }
  }

  Widget _buildCompactView(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    // Get current locale for date formatting
    final locale = Localizations.localeOf(context);
    // Format date with localized month names but keep Western numerals
    String formatDate(DateTime date) {
      // Disable native digits for Arabic to keep Western numerals (0-9)
      if (locale.languageCode == 'ar') {
        DateFormat.useNativeDigitsByDefaultFor('ar', false);
      }
      final dateFormat = DateFormat('MMM d, y', locale.languageCode);
      String formatted = dateFormat.format(date);
      // Replace any Indic numerals with Western numerals as a safety measure
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
    final isOverdue = assignment.isOverdue;
    final completionColor = _getCompletionColor(context, assignment.completionRate);

    return Material(
      color: Colors.transparent,
      child: cupertino.CupertinoButton(
        padding: EdgeInsets.zero,
        minSize: 0,
        color: Colors.transparent,
        onPressed: onToggleExpand ?? onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 72),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
            child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              // Content
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Title, status, and completion rate - all on one line if space allows
                    Wrap(
                      crossAxisAlignment: WrapCrossAlignment.center,
                      spacing: IOSSpacing.sm,
                      runSpacing: IOSSpacing.xs,
                      children: [
                        // Title
                        Text(
                          assignment.periodName != null &&
                                  assignment.periodName!.isNotEmpty
                              ? '${assignment.templateName ?? assignment.name} - ${assignment.periodName}'
                              : assignment.templateName ?? assignment.name,
                          style: IOSTextStyle.body(context).copyWith(
                            fontWeight: FontWeight.w400,
                          ),
                        ),
                        // Status badge
                        _StatusBadge(status: assignment.status),
                        // Completion rate
                        Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              width: 5,
                              height: 5,
                              decoration: BoxDecoration(
                                color: completionColor,
                                shape: BoxShape.circle,
                              ),
                            ),
                            SizedBox(width: IOSSpacing.xs),
                            Text(
                              '${assignment.completionRate.toStringAsFixed(0)}%',
                              style: IOSTextStyle.footnote(context),
                            ),
                          ],
                        ),
                      ],
                    ),
                    // Due date on separate line if available
                    if (assignment.dueDate != null) ...[
                      SizedBox(height: IOSSpacing.xs / 2),
                      Text(
                        formatDate(assignment.dueDate!),
                        style: IOSTextStyle.footnote(context).copyWith(
                          color: isOverdue
                              ? const Color(AppConstants.errorColor)
                              : theme.colorScheme.onSurface.withOpacity(0.6),
                          fontWeight: isOverdue ? FontWeight.w600 : FontWeight.w400,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              // Chevron icon - iOS style
              Icon(
                cupertino.CupertinoIcons.chevron_right,
                size: 13,
                color: theme.colorScheme.onSurface.withOpacity(0.25),
              ),
            ],
          ),
          ),
        ),
      ),
    );
  }

  Widget _buildExpandedView(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    // Get current locale for date formatting
    final locale = Localizations.localeOf(context);
    // Format date with localized month names but keep Western numerals
    String formatDate(DateTime date) {
      // Disable native digits for Arabic to keep Western numerals (0-9)
      if (locale.languageCode == 'ar') {
        DateFormat.useNativeDigitsByDefaultFor('ar', false);
      }
      final dateFormat = DateFormat('MMM d, y', locale.languageCode);
      String formatted = dateFormat.format(date);
      // Replace any Indic numerals with Western numerals as a safety measure
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
    final isOverdue = assignment.isOverdue;
    final completionColor = _getCompletionColor(context, assignment.completionRate);

    return Material(
      color: Colors.transparent,
      child: Column(
        children: [
          // Header with collapse button
          cupertino.CupertinoButton(
            padding: EdgeInsets.zero,
            minSize: 0,
            color: Colors.transparent,
            onPressed: onToggleExpand,
            child: ConstrainedBox(
              constraints: const BoxConstraints(minHeight: 72),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                child: Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        // Title and status - on same line if space allows
                        Wrap(
                          crossAxisAlignment: WrapCrossAlignment.center,
                          spacing: IOSSpacing.sm,
                          runSpacing: 4,
                          children: [
                            // Title
                            Text(
                              assignment.periodName != null &&
                                      assignment.periodName!.isNotEmpty
                                  ? '${assignment.templateName ?? assignment.name} - ${assignment.periodName}'
                                  : assignment.templateName ?? assignment.name,
                              style: IOSTextStyle.body(context).copyWith(
                                fontWeight: FontWeight.w400,
                              ),
                            ),
                            // Status badge
                            _StatusBadge(status: assignment.status),
                          ],
                        ),
                        // Due date on separate line if available
                        if (assignment.dueDate != null) ...[
                          const SizedBox(height: 4),
                          Text(
                            formatDate(assignment.dueDate!),
                            style: IOSTextStyle.footnote(context).copyWith(
                              color: isOverdue
                                  ? const Color(AppConstants.errorColor)
                                  : theme.colorScheme.onSurface.withOpacity(0.6),
                              fontWeight: isOverdue ? FontWeight.w600 : FontWeight.w400,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                  Icon(
                    cupertino.CupertinoIcons.chevron_up,
                    size: 13,
                    color: theme.colorScheme.onSurface.withOpacity(0.25),
                  ),
                ],
              ),
              ),
            ),
          ),
          // Expanded content
          cupertino.CupertinoButton(
            padding: EdgeInsets.zero,
            minSize: 0,
            color: Colors.transparent,
            onPressed: onTap,
            child: Container(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Completion Progress Section
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Text(
                                  '${assignment.completionRate.toStringAsFixed(0)}%',
                                  style: IOSTextStyle.title3(context).copyWith(
                                    color: completionColor,
                                  ),
                                ),
                                const SizedBox(width: 6),
                                Text(
                                  localizations.completion,
                                  style: IOSTextStyle.footnote(context),
                                ),
                              ],
                            ),
                            const SizedBox(height: 10),
                            // iOS-style progress bar
                            Container(
                              height: 3,
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(1.5),
                                color: theme.dividerColor.withOpacity(0.2),
                              ),
                              child: ClipRRect(
                                borderRadius: BorderRadius.circular(1.5),
                                child: LinearProgressIndicator(
                                  value: assignment.completionRate / 100,
                                  minHeight: 3,
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
                      if (showEnterDataButton && onEnterData != null) ...[
                        const SizedBox(width: 12),
                        cupertino.CupertinoButton(
                          onPressed: onEnterData,
                          padding: EdgeInsets.zero,
                          minSize: 0,
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 16,
                              vertical: 8,
                            ),
                            decoration: BoxDecoration(
                              color: IOSColors.getSystemBlue(context),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Text(
                              enterDataButtonText ?? localizations.enterData,
                              style: IOSTextStyle.subheadline(context).copyWith(
                                fontWeight: FontWeight.w600,
                                color: Colors.white,
                              ),
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                  // Additional Info
                  if (assignment.lastModifiedUserName != null ||
                      (assignment.isPublic &&
                          assignment.publicSubmissionCount != null)) ...[
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 12,
                      runSpacing: 8,
                      children: [
                        if (assignment.lastModifiedUserName != null)
                          Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                cupertino.CupertinoIcons.person,
                                size: 14,
                                color: theme.colorScheme.onSurface.withOpacity(0.6),
                              ),
                              const SizedBox(width: 4),
                              Text(
                                assignment.lastModifiedUserName!,
                                style: IOSTextStyle.footnote(context),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ],
                          ),
                        if (assignment.isPublic &&
                            assignment.publicSubmissionCount != null)
                          Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                cupertino.CupertinoIcons.globe,
                                size: 14,
                                color: IOSColors.getSystemBlue(context),
                              ),
                              const SizedBox(width: 4),
                              Text(
                                '${assignment.publicSubmissionCount} public',
                                style: IOSTextStyle.footnote(context).copyWith(
                                  color: IOSColors.getSystemBlue(context),
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ],
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
    );
  }

  Color _getStatusColor(BuildContext context) {
    switch (assignment.status.toLowerCase()) {
      case 'approved':
        return const Color(AppConstants.successColor);
      case 'in progress':
        return context.navyTextColor;
      case 'requires revision':
        return const Color(AppConstants.errorColor);
      case 'pending':
        return const Color(AppConstants.warningColor);
      default:
        return const Color(AppConstants.textSecondary);
    }
  }

  IconData _getStatusIcon() {
    switch (assignment.status.toLowerCase()) {
      case 'approved':
        return Icons.check_circle;
      case 'in progress':
        return Icons.work;
      case 'requires revision':
        return Icons.warning;
      case 'pending':
        return Icons.pending;
      default:
        return Icons.info;
    }
  }
}

class _StatusBadge extends StatelessWidget {
  final String status;

  const _StatusBadge({required this.status});

  Color _getStatusColor(BuildContext context) {
    switch (status.toLowerCase()) {
      case 'approved':
        return const Color(AppConstants.successColor);
      case 'in progress':
        return context.navyTextColor;
      case 'requires revision':
        return const Color(AppConstants.errorColor);
      case 'pending':
        return const Color(AppConstants.warningColor);
      default:
        return const Color(AppConstants.textSecondary);
    }
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final statusColor = _getStatusColor(context);
    final localizedStatus = localizations.localizeStatus(status);
    final theme = Theme.of(context);

    // iOS-style minimal badge
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: 6,
        vertical: 2,
      ),
      decoration: BoxDecoration(
        color: statusColor.withOpacity(0.1),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        localizedStatus,
        style: IOSTextStyle.caption2(context).copyWith(
          color: statusColor,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
