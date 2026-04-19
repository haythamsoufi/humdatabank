import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../../l10n/app_localizations.dart';
import '../../models/admin/admin_assignment.dart';
import '../../models/admin/admin_assignment_detail.dart';
import '../../providers/admin/assignments_provider.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/app_bar.dart';
import '../../config/routes.dart';
import '../../utils/admin_screen_view_logging_mixin.dart';

/// Assignment summary: loads full detail (entities, deadlines) from the mobile API.
class AssignmentDetailScreen extends StatefulWidget {
  const AssignmentDetailScreen({
    super.key,
    required this.assignment,
  });

  /// Snapshot from the list (used while loading and as fallback on error).
  final AdminAssignment assignment;

  @override
  State<AssignmentDetailScreen> createState() => _AssignmentDetailScreenState();
}

class _AssignmentDetailScreenState extends State<AssignmentDetailScreen>
    with AdminScreenViewLoggingMixin {
  @override
  String get adminScreenViewRoutePath =>
      AppRoutes.assignmentDetail(widget.assignment.id);

  AdminAssignmentDetail? _detail;
  bool _loading = true;
  String? _loadError;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _loadError = null;
    });
    final provider = Provider.of<AssignmentsProvider>(context, listen: false);
    final detail =
        await provider.fetchAssignmentDetail(widget.assignment.id);
    if (!mounted) return;
    setState(() {
      _detail = detail;
      _loading = false;
      if (detail == null) {
        _loadError = AppLocalizations.of(context)!.assignmentLoadDetailFailed;
      }
    });
  }

  String? _fmtIso(BuildContext context, String? iso) {
    if (iso == null || iso.isEmpty) return null;
    try {
      final dt = DateTime.parse(iso).toLocal();
      final locale = Localizations.localeOf(context).toLanguageTag();
      return DateFormat.yMMMd(locale).add_jm().format(dt);
    } catch (_) {
      return iso;
    }
  }

  String? _fmtDateOnly(BuildContext context, String? iso) {
    if (iso == null || iso.isEmpty) return null;
    try {
      final dt = DateTime.parse(iso);
      final locale = Localizations.localeOf(context).toLanguageTag();
      return DateFormat.yMMMd(locale).format(dt);
    } catch (_) {
      return iso;
    }
  }

  /// Single line: active/inactive for the assignment, then open vs closed (incl. expiry).
  String _assignmentCombinedStatus(
    AppLocalizations loc,
    AdminAssignmentDetail d,
  ) {
    final activity = d.isActive ? loc.active : loc.inactive;
    final closedOrOpen = (d.isClosed || d.isEffectivelyClosed)
        ? loc.assignmentClosed
        : loc.assignmentOpen;
    return '$activity, $closedOrOpen';
  }

  String _entityTypeLabel(String raw) {
    if (raw.isEmpty) return raw;
    return raw
        .split('_')
        .map((w) => w.isEmpty ? w : '${w[0].toUpperCase()}${w.substring(1)}')
        .join(' ');
  }

  /// Preserves first-seen type order from the API; sorts entities by name within each type.
  List<Widget> _entityGroupsByType(
    BuildContext context,
    AppLocalizations loc,
    List<AdminAssignmentEntityRow> entities,
  ) {
    final byType = <String, List<AdminAssignmentEntityRow>>{};
    for (final e in entities) {
      byType.putIfAbsent(e.entityType, () => []).add(e);
    }
    for (final list in byType.values) {
      list.sort(
        (a, b) => a.displayName.toLowerCase().compareTo(b.displayName.toLowerCase()),
      );
    }

    final out = <Widget>[];
    for (final entry in byType.entries) {
      final typeKey = entry.key;
      final list = entry.value;
      out.add(
        _CollapsibleEntityGroup(
          key: ValueKey(typeKey),
          typeLabel: _entityTypeLabel(typeKey),
          entities: list,
          tileBuilder: (e, {required bool showBottomDivider}) =>
              _entityTile(context, loc, e,
                  dense: true, showBottomDivider: showBottomDivider),
        ),
      );
    }
    return out;
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    final d = _detail;

    final period = d?.periodName ?? widget.assignment.periodName;
    final templateName =
        d?.templateName ?? widget.assignment.templateName ?? loc.templateMissing;
    final templateId = d?.templateId ?? widget.assignment.templateId;
    final hasPublicUrl = d?.hasPublicUrl ?? widget.assignment.hasPublicUrl;
    final isPublicActive = d?.isPublicActive ?? widget.assignment.isPublicActive;
    final publicUrlFromDetail = d?.publicUrl?.trim();
    final publicUrl = (publicUrlFromDetail != null && publicUrlFromDetail.isNotEmpty)
        ? publicUrlFromDetail
        : widget.assignment.publicUrl?.trim();
    final publicCount =
        d?.publicSubmissionCount ?? widget.assignment.publicSubmissionCount;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: loc.assignmentDetails,
      ),
      body: RefreshIndicator(
        color: Color(AppConstants.ifrcRed),
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: EdgeInsets.fromLTRB(16, 8, 16, 16 + bottomInset + 32),
          children: [
            if (_loading)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(2),
                  child: const LinearProgressIndicator(minHeight: 4),
                ),
              ),
            if (_loadError != null) ...[
              const SizedBox(height: 8),
              Material(
                color: theme.colorScheme.errorContainer.withValues(alpha: 0.35),
                borderRadius: BorderRadius.circular(8),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Row(
                    children: [
                      Icon(Icons.warning_amber_rounded,
                          color: theme.colorScheme.error),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _loadError!,
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: theme.colorScheme.onErrorContainer,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
            const SizedBox(height: 12),
            _labeledBlock(
              context,
              label: loc.assignmentReportingPeriod,
              child: Text(
                period,
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: theme.colorScheme.onSurface,
                ),
              ),
            ),
            const SizedBox(height: 16),
            _labeledBlock(
              context,
              label: loc.template,
              child: Text(
                templateName,
                style: TextStyle(
                  fontSize: 15,
                  height: 1.45,
                  fontWeight: FontWeight.w500,
                  color: context.textColor,
                ),
              ),
            ),
            if (templateId != null) ...[
              const SizedBox(height: 8),
              Text(
                '${loc.assignmentTemplateId}: $templateId',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: context.textSecondaryColor,
                ),
              ),
            ],
            if (d != null) ...[
              const SizedBox(height: 24),
              _sectionTitle(context, loc.assignmentScheduleSection),
              const SizedBox(height: 12),
              _labeledBlock(
                context,
                label: loc.assignmentAssignedDate,
                child: Text(
                  _fmtIso(context, d.assignedAtIso) ?? loc.nA,
                  style: TextStyle(
                    fontSize: 15,
                    height: 1.45,
                    color: context.textColor,
                  ),
                ),
              ),
              const SizedBox(height: 12),
              _labeledBlock(
                context,
                label: loc.assignmentExpiryDate,
                child: Text(
                  _fmtDateOnly(context, d.expiryDateIso) ?? loc.nA,
                  style: TextStyle(
                    fontSize: 15,
                    height: 1.45,
                    color: context.textColor,
                  ),
                ),
              ),
              const SizedBox(height: 12),
              _labeledBlock(
                context,
                label: loc.assignmentEarliestEntityDue,
                child: Text(
                  _fmtIso(context, d.earliestDueDateIso) ?? loc.nA,
                  style: TextStyle(
                    fontSize: 15,
                    height: 1.45,
                    color: context.textColor,
                  ),
                ),
              ),
              if (d.hasMultipleDueDates) ...[
                const SizedBox(height: 8),
                Text(
                  loc.assignmentMultipleDueDatesHint,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: context.textSecondaryColor,
                  ),
                ),
              ],
              const SizedBox(height: 24),
              _sectionTitle(context, loc.assignmentStateSection),
              const SizedBox(height: 12),
              _labeledBlock(
                context,
                label: loc.status,
                child: Text(
                  _assignmentCombinedStatus(loc, d),
                  style: TextStyle(
                    fontSize: 15,
                    height: 1.45,
                    color: context.textColor,
                  ),
                ),
              ),
              const SizedBox(height: 24),
              _sectionTitle(context, '${loc.entities} (${d.entities.length})'),
              const SizedBox(height: 12),
              if (d.entities.isEmpty)
                Text(
                  loc.noEntitiesAssigned,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: context.textSecondaryColor,
                  ),
                )
              else
                ..._entityGroupsByType(context, loc, d.entities),
            ],
            const SizedBox(height: 24),
            _sectionTitle(context, loc.publicLink),
            const SizedBox(height: 12),
            _labeledBlock(
              context,
              label: loc.assignmentHasPublicLink,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    hasPublicUrl ? Icons.link : Icons.link_off,
                    size: 20,
                    color: hasPublicUrl
                        ? theme.colorScheme.primary
                        : context.textSecondaryColor,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      hasPublicUrl ? loc.active : loc.inactive,
                      style: TextStyle(
                        fontSize: 15,
                        height: 1.45,
                        color: context.textColor,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            _labeledBlock(
              context,
              label: loc.publicLinkEnabled,
              child: Text(
                isPublicActive ? loc.active : loc.inactive,
                style: TextStyle(
                  fontSize: 15,
                  height: 1.45,
                  color: context.textColor,
                ),
              ),
            ),
            if (publicUrl != null && publicUrl.isNotEmpty) ...[
              const SizedBox(height: 12),
              _labeledBlock(
                context,
                label: loc.publicLink,
                trailing: IconButton(
                  icon: const Icon(Icons.copy, size: 20),
                  color: Color(AppConstants.ifrcRed),
                  tooltip: loc.copyLink,
                  onPressed: () async {
                    await Clipboard.setData(ClipboardData(text: publicUrl));
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(content: Text(loc.publicUrlCopied)),
                      );
                    }
                  },
                ),
                child: SelectableText(
                  publicUrl,
                  style: TextStyle(
                    fontSize: 14,
                    height: 1.45,
                    color: theme.colorScheme.primary,
                  ),
                ),
              ),
            ],
            if (publicCount != null && publicCount > 0) ...[
              const SizedBox(height: 12),
              _labeledBlock(
                context,
                label: loc.submissions,
                child: Text(
                  publicCount == 1
                      ? loc.received1SubmissionUsingPublicLink
                      : loc.receivedCountSubmissionsUsingPublicLink(publicCount),
                  style: TextStyle(
                    fontSize: 15,
                    height: 1.45,
                    color: context.textColor,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _sectionTitle(BuildContext context, String text) {
    final theme = Theme.of(context);
    return Text(
      text,
      style: theme.textTheme.titleSmall?.copyWith(
        fontWeight: FontWeight.w600,
        color: theme.colorScheme.onSurface,
        letterSpacing: 0.15,
      ),
    );
  }

  Widget _entityTile(
    BuildContext context,
    AppLocalizations loc,
    AdminAssignmentEntityRow e, {
    bool dense = false,
    bool showBottomDivider = false,
  }) {
    final theme = Theme.of(context);
    final due = _fmtIso(context, e.dueDateIso);
    final submitted = _fmtIso(context, e.submittedAtIso);

    final nameStyle = (dense
            ? theme.textTheme.bodyLarge
            : theme.textTheme.titleSmall) ??
        theme.textTheme.bodyLarge ??
        theme.textTheme.bodyMedium!;
    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Text(
                e.displayName,
                style: nameStyle.copyWith(
                  fontWeight: FontWeight.w600,
                  color: theme.colorScheme.onSurface,
                ),
              ),
            ),
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(4),
                border: Border.all(color: context.borderColor.withValues(alpha: 0.6)),
              ),
              child: Text(
                e.status,
                style: theme.textTheme.labelSmall?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ),
          ],
        ),
        if (due != null || submitted != null || e.isPublicAvailable) ...[
          SizedBox(height: dense ? 6 : 8),
          Wrap(
            spacing: 10,
            runSpacing: 6,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              if (due != null)
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.event_outlined,
                        size: dense ? 15 : 16, color: context.textSecondaryColor),
                    const SizedBox(width: 4),
                    Text(
                      due,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: context.textColor,
                      ),
                    ),
                  ],
                ),
              if (submitted != null)
                Text(
                  '${loc.entitySubmittedAt}: $submitted',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: context.textSecondaryColor,
                  ),
                ),
              if (e.isPublicAvailable)
                Text(
                  loc.entityPublicReporting,
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: theme.colorScheme.primary,
                    fontWeight: FontWeight.w600,
                  ),
                ),
            ],
          ),
        ],
      ],
    );

    if (dense) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
            child: body,
          ),
          if (showBottomDivider)
            Divider(height: 1, thickness: 1, color: context.borderColor),
        ],
      );
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Material(
        color: context.subtleSurfaceColor,
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: body,
        ),
      ),
    );
  }

  Widget _labeledBlock(
    BuildContext context, {
    required String label,
    required Widget child,
    Widget? trailing,
  }) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: theme.textTheme.labelLarge?.copyWith(
                  color: context.textSecondaryColor,
                ),
              ),
            ),
            ?trailing,
          ],
        ),
        const SizedBox(height: 8),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: context.subtleSurfaceColor,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: context.borderColor),
          ),
          child: child,
        ),
      ],
    );
  }
}

/// Collapsed by default: one row with type, count chip, expand control; expanded shows entity rows.
class _CollapsibleEntityGroup extends StatefulWidget {
  const _CollapsibleEntityGroup({
    super.key,
    required this.typeLabel,
    required this.entities,
    required this.tileBuilder,
  });

  final String typeLabel;
  final List<AdminAssignmentEntityRow> entities;
  final Widget Function(AdminAssignmentEntityRow e, {required bool showBottomDivider})
      tileBuilder;

  @override
  State<_CollapsibleEntityGroup> createState() => _CollapsibleEntityGroupState();
}

class _CollapsibleEntityGroupState extends State<_CollapsibleEntityGroup> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final count = widget.entities.length;

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: context.subtleSurfaceColor,
            border: Border.all(color: context.borderColor),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Material(
                color: Colors.transparent,
                child: InkWell(
                  onTap: () => setState(() => _expanded = !_expanded),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                    child: Row(
                      children: [
                        Icon(
                          _expanded ? Icons.expand_less : Icons.expand_more,
                          size: 22,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                        const SizedBox(width: 4),
                        Expanded(
                          child: Text(
                            widget.typeLabel,
                            style: theme.textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.w600,
                              color: theme.colorScheme.onSurface,
                            ),
                          ),
                        ),
                        DecoratedBox(
                          decoration: BoxDecoration(
                            color: theme.colorScheme.primary.withValues(alpha: 0.14),
                            borderRadius: BorderRadius.circular(999),
                          ),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 11,
                              vertical: 5,
                            ),
                            child: Text(
                              '$count',
                              style: theme.textTheme.labelLarge?.copyWith(
                                fontWeight: FontWeight.w800,
                                color: theme.colorScheme.primary,
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              if (_expanded) ...[
                Divider(height: 1, thickness: 1, color: context.borderColor),
                ColoredBox(
                  color: theme.colorScheme.surface.withValues(alpha: 0.4),
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(4, 2, 4, 6),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        for (var i = 0; i < widget.entities.length; i++)
                          widget.tileBuilder(
                            widget.entities[i],
                            showBottomDivider: i < widget.entities.length - 1,
                          ),
                      ],
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
