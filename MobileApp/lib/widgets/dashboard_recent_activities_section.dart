import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

import '../l10n/app_localizations.dart';
import '../models/shared/dashboard_activity.dart';
import '../theme/grouped_dashboard_palette.dart';
import '../theme/grouped_sheet_style.dart';
import '../utils/constants.dart';
import '../utils/ios_constants.dart';
import 'dashboard_focal_points_section.dart';
import 'dashboard_grouped_assignment_card.dart';
import 'sheets/native_modal_sheet.dart';

/// Recent assignment changes for the selected entity's country.
///
/// Mirrors the back office dashboard: a "Last month" feed, filters when more
/// than one person or assignment appears, field-level lines, and load more.
class DashboardRecentActivitiesSection extends StatefulWidget {
  const DashboardRecentActivitiesSection({
    super.key,
    required this.entityLabel,
    required this.activities,
    required this.hasMore,
    required this.isLoading,
    required this.isLoadingMore,
    required this.onOpenAssignment,
    required this.onLoadMore,
  });

  final String entityLabel;
  final List<DashboardActivity> activities;
  final bool hasMore;
  final bool isLoading;
  final bool isLoadingMore;
  final ValueChanged<int> onOpenAssignment;
  final VoidCallback? onLoadMore;

  @override
  State<DashboardRecentActivitiesSection> createState() =>
      _DashboardRecentActivitiesSectionState();
}

class _DashboardRecentActivitiesSectionState
    extends State<DashboardRecentActivitiesSection> {
  String? _userFilter;
  String? _assignmentFilter;

  List<DashboardActivity> get _visible {
    return widget.activities.where((activity) {
      if (_userFilter != null && activity.filterUserId != _userFilter) {
        return false;
      }
      if (_assignmentFilter != null &&
          activity.filterTemplatePeriod != _assignmentFilter) {
        return false;
      }
      return true;
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final scheme = Theme.of(context).colorScheme;
    final users = _uniqueUsers(widget.activities);
    final assignments = _uniqueAssignments(widget.activities);
    final visible = _visible;
    final filtersActive = _userFilter != null || _assignmentFilter != null;

    return Padding(
      padding: const EdgeInsets.fromLTRB(0, 8, 0, 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 10, 20, 6),
            child: Row(
              children: [
                Expanded(
                  child: DashboardSectionLabel(
                    title: localizations.recentActivities,
                  ),
                ),
                Text(
                  localizations.lastMonth,
                  style: IOSTextStyle.caption1(context).copyWith(
                    color: scheme.onSurface.withValues(alpha: 0.45),
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          if (users.length > 1 || assignments.length > 1)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  if (users.length > 1)
                    GroupedFilterChip(
                      label: _userFilter == null
                          ? localizations.filterByUser
                          : _userName(users, _userFilter!),
                      selected: _userFilter != null,
                      onTap: () => _pickUser(localizations, users),
                    ),
                  if (assignments.length > 1)
                    GroupedFilterChip(
                      label:
                          _assignmentFilter ?? localizations.filterByAssignment,
                      selected: _assignmentFilter != null,
                      onTap: () => _pickAssignment(localizations, assignments),
                    ),
                  if (filtersActive)
                    GroupedFilterChip(
                      label: localizations.clear,
                      icon: Icons.close_rounded,
                      showChevron: false,
                      onTap: () {
                        setState(() {
                          _userFilter = null;
                          _assignmentFilter = null;
                        });
                      },
                    ),
                ],
              ),
            ),
          if (widget.isLoading && widget.activities.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 28),
              child: Center(
                child: SizedBox(
                  width: 22,
                  height: 22,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
            )
          else if (visible.isEmpty)
            _EmptyActivities(
              entityLabel: widget.entityLabel,
              filtered: filtersActive,
            )
          else
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Column(
                children: [
                  for (final activity in visible)
                    _ActivityCard(
                      activity: activity,
                      onOpen: activity.assignmentId == null
                          ? null
                          : () =>
                                widget.onOpenAssignment(activity.assignmentId!),
                    ),
                ],
              ),
            ),
          if (widget.hasMore && widget.onLoadMore != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
              child: OutlinedButton.icon(
                onPressed: widget.isLoadingMore
                    ? null
                    : () {
                        HapticFeedback.selectionClick();
                        widget.onLoadMore!();
                      },
                icon: widget.isLoadingMore
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.expand_more_rounded, size: 18),
                label: Text(
                  widget.isLoadingMore
                      ? localizations.loadingDashboard
                      : localizations.notificationsLoadMore,
                ),
              ),
            ),
        ],
      ),
    );
  }

  List<_FilterUser> _uniqueUsers(List<DashboardActivity> activities) {
    final byId = <String, _FilterUser>{};
    for (final activity in activities) {
      final user = activity.user;
      if (user == null) continue;
      byId.putIfAbsent(
        activity.filterUserId,
        () => _FilterUser(activity.filterUserId, user.displayName),
      );
    }
    final users = byId.values.toList()
      ..sort((a, b) => a.name.toLowerCase().compareTo(b.name.toLowerCase()));
    return users;
  }

  List<String> _uniqueAssignments(List<DashboardActivity> activities) {
    final titles = <String>{};
    for (final activity in activities) {
      final title = activity.filterTemplatePeriod;
      if (title.isNotEmpty) titles.add(title);
    }
    final list = titles.toList()..sort();
    return list;
  }

  String _userName(List<_FilterUser> users, String id) {
    for (final user in users) {
      if (user.id == id) return user.name;
    }
    return id;
  }

  void _pickUser(AppLocalizations localizations, List<_FilterUser> users) {
    showGroupedOptionPicker(
      context: context,
      title: localizations.filterByUser,
      closeTooltip: localizations.close,
      choices: [
        GroupedPickerChoice(
          label: localizations.allUsers,
          selected: _userFilter == null,
          onSelected: () => setState(() => _userFilter = null),
        ),
        for (final user in users)
          GroupedPickerChoice(
            label: user.name.isEmpty ? localizations.unknownUser : user.name,
            selected: _userFilter == user.id,
            onSelected: () => setState(() => _userFilter = user.id),
          ),
      ],
    );
  }

  void _pickAssignment(AppLocalizations localizations, List<String> titles) {
    showGroupedOptionPicker(
      context: context,
      title: localizations.filterByAssignment,
      closeTooltip: localizations.close,
      choices: [
        GroupedPickerChoice(
          label: localizations.allAssignments,
          selected: _assignmentFilter == null,
          onSelected: () => setState(() => _assignmentFilter = null),
        ),
        for (final title in titles)
          GroupedPickerChoice(
            label: title,
            selected: _assignmentFilter == title,
            onSelected: () => setState(() => _assignmentFilter = title),
          ),
      ],
    );
  }
}

class _FilterUser {
  const _FilterUser(this.id, this.name);
  final String id;
  final String name;
}

class _EmptyActivities extends StatelessWidget {
  const _EmptyActivities({required this.entityLabel, required this.filtered});

  final String entityLabel;
  final bool filtered;

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 8, 24, 16),
      child: Column(
        children: [
          Icon(
            filtered ? Icons.filter_alt_off_rounded : Icons.history_rounded,
            size: 36,
            color: scheme.onSurface.withValues(alpha: 0.3),
          ),
          const SizedBox(height: 8),
          Text(
            filtered
                ? localizations.noAssignmentsMatchFilters
                : localizations.noRecentActivities,
            style: IOSTextStyle.subheadline(context).copyWith(
              fontWeight: FontWeight.w600,
              color: scheme.onSurface.withValues(alpha: 0.7),
            ),
            textAlign: TextAlign.center,
          ),
          if (!filtered) ...[
            const SizedBox(height: 4),
            Text(
              '${localizations.activitiesFromOtherFocalPointsIn} $entityLabel ${localizations.willAppearHere}',
              style: IOSTextStyle.footnote(context).copyWith(
                color: scheme.onSurface.withValues(alpha: 0.55),
                height: 1.35,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ],
      ),
    );
  }
}

class _ActivityCard extends StatefulWidget {
  const _ActivityCard({required this.activity, required this.onOpen});

  final DashboardActivity activity;
  final VoidCallback? onOpen;

  @override
  State<_ActivityCard> createState() => _ActivityCardState();
}

class _ActivityCardState extends State<_ActivityCard> {
  bool _showAllChanges = false;

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final isDark = theme.brightness == Brightness.dark;
    final activity = widget.activity;
    final user = activity.user;
    final name = (user == null || user.displayName.isEmpty)
        ? localizations.unknownUser
        : user.displayName;
    final titleColor = isDark
        ? scheme.onSurface
        : const Color(AppConstants.defaultNavy);
    final borderColor = isDark
        ? scheme.outlineVariant.withValues(alpha: 0.45)
        : GroupedDashboardPalette.hairline;
    final changes = activity.changes.where((c) => c.text.trim().isNotEmpty);
    final changeList = changes.toList();
    final hidden = changeList.length > 3 && !_showAllChanges
        ? changeList.length - 3
        : 0;
    final shown = hidden > 0 ? changeList.take(3).toList() : changeList;

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Material(
        color: isDark
            ? scheme.surfaceContainerHigh
            : GroupedDashboardPalette.card,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: BorderSide(color: borderColor),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: widget.onOpen == null
              ? null
              : () {
                  HapticFeedback.lightImpact();
                  widget.onOpen!();
                },
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    CircleAvatar(
                      radius: 16,
                      backgroundColor: avatarColorFor(
                        user?.email.isNotEmpty == true ? user!.email : name,
                      ),
                      child: Text(
                        user?.initials ?? '?',
                        style: IOSTextStyle.caption2(context).copyWith(
                          fontWeight: FontWeight.w700,
                          color: GroupedDashboardPalette.onFill,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            name,
                            style: IOSTextStyle.subheadline(context).copyWith(
                              fontWeight: FontWeight.w700,
                              color: titleColor,
                              height: 1.2,
                            ),
                          ),
                          if (activity.timestamp != null)
                            Padding(
                              padding: const EdgeInsets.only(top: 2),
                              child: Text(
                                _formatTimestamp(context, activity.timestamp!),
                                style: IOSTextStyle.caption1(context).copyWith(
                                  color: scheme.onSurface.withValues(
                                    alpha: 0.5,
                                  ),
                                ),
                              ),
                            ),
                          if ((activity.assignmentTitle ?? '').isNotEmpty)
                            Padding(
                              padding: const EdgeInsets.only(top: 4),
                              child: Row(
                                children: [
                                  Icon(
                                    Icons.description_outlined,
                                    size: 13,
                                    color: scheme.onSurface.withValues(
                                      alpha: 0.45,
                                    ),
                                  ),
                                  const SizedBox(width: 4),
                                  Expanded(
                                    child: Text(
                                      activity.assignmentTitle!,
                                      maxLines: 2,
                                      overflow: TextOverflow.ellipsis,
                                      style: IOSTextStyle.caption1(context)
                                          .copyWith(
                                            fontWeight: FontWeight.w600,
                                            color: scheme.onSurface.withValues(
                                              alpha: 0.72,
                                            ),
                                          ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                        ],
                      ),
                    ),
                    if (activity.changeCount != null &&
                        activity.changeCount! > 1)
                      _ChangeBadge(
                        label: '${activity.changeCount}',
                        tone: GroupedDashboardPalette.neutral,
                      ),
                  ],
                ),
                if (activity.summary.trim().isNotEmpty) ...[
                  const SizedBox(height: 10),
                  _SummaryLine(
                    changeType: activity.changeType,
                    text: activity.summary.trim(),
                  ),
                ],
                if (shown.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  for (final change in shown)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 6),
                      child: _SummaryLine(
                        changeType: change.changeType,
                        text: change.text,
                        compact: true,
                      ),
                    ),
                  if (hidden > 0 || (_showAllChanges && changeList.length > 3))
                    Align(
                      alignment: AlignmentDirectional.centerStart,
                      child: TextButton(
                        onPressed: () {
                          setState(() => _showAllChanges = !_showAllChanges);
                        },
                        style: TextButton.styleFrom(
                          visualDensity: VisualDensity.compact,
                          padding: const EdgeInsets.symmetric(horizontal: 4),
                        ),
                        child: Text(
                          _showAllChanges
                              ? localizations.showLess
                              : '${localizations.show} $hidden ${hidden == 1 ? localizations.moreChange : localizations.moreChanges}',
                        ),
                      ),
                    ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _SummaryLine extends StatelessWidget {
  const _SummaryLine({
    required this.text,
    this.changeType,
    this.compact = false,
  });

  final String text;
  final String? changeType;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final scheme = Theme.of(context).colorScheme;
    final tone = _toneFor(changeType);
    final label = _labelFor(localizations, changeType);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (label != null) ...[
          _ChangeBadge(label: label, tone: tone),
          const SizedBox(width: 8),
        ],
        Expanded(
          child: Text(
            text,
            style:
                (compact
                        ? IOSTextStyle.caption1(context)
                        : IOSTextStyle.footnote(context))
                    .copyWith(
                      color: scheme.onSurface.withValues(alpha: 0.88),
                      height: 1.35,
                    ),
          ),
        ),
      ],
    );
  }
}

class _ChangeBadge extends StatelessWidget {
  const _ChangeBadge({required this.label, required this.tone});

  final String label;
  final GroupedStatusColors tone;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: tone.background,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: tone.border),
      ),
      child: Text(
        label,
        style: IOSTextStyle.caption2(
          context,
        ).copyWith(color: tone.foreground, fontWeight: FontWeight.w700),
      ),
    );
  }
}

GroupedStatusColors _toneFor(String? changeType) {
  switch (changeType) {
    case 'added':
      return GroupedDashboardPalette.success;
    case 'removed':
      return GroupedDashboardPalette.danger;
    case 'updated':
      return GroupedDashboardPalette.info;
    default:
      return GroupedDashboardPalette.neutral;
  }
}

String? _labelFor(AppLocalizations localizations, String? changeType) {
  switch (changeType) {
    case 'added':
      return localizations.added;
    case 'removed':
      return localizations.removed;
    case 'updated':
      return localizations.updated;
    default:
      return null;
  }
}

String _formatTimestamp(BuildContext context, DateTime date) {
  final locale = Localizations.localeOf(context);
  if (locale.languageCode == 'ar') {
    DateFormat.useNativeDigitsByDefaultFor('ar', false);
  }
  return DateFormat(
    'MMM d, y · HH:mm',
    locale.languageCode,
  ).format(date.toLocal());
}
