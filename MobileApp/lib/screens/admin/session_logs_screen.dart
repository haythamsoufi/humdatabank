import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../../l10n/app_localizations.dart';
import '../../models/admin/session_log_item.dart';
import '../../providers/admin/session_logs_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../widgets/admin_filter_panel.dart';
import '../../widgets/admin_filters_bottom_sheet.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/shared/elevated_list_card.dart';
import '../../config/routes.dart';
import '../../utils/admin_screen_view_logging_mixin.dart';

/// Whole minutes from [a] to [b] (truncated toward zero); null if either is null.
int? _sessionMinutesBetween(DateTime? a, DateTime? b) {
  if (a == null || b == null) return null;
  final d = b.difference(a);
  if (d.isNegative) return 0;
  return d.inMinutes;
}

/// User session list (aligned with web `/admin/analytics/sessions`).
class SessionLogsScreen extends StatefulWidget {
  const SessionLogsScreen({super.key});

  @override
  State<SessionLogsScreen> createState() => _SessionLogsScreenState();
}

class _SessionLogsScreenState extends State<SessionLogsScreen>
    with AdminScreenViewLoggingMixin {
  final _emailController = TextEditingController();
  final _minDurationController = TextEditingController();
  bool _activeOnly = false;
  String? _endingSessionId;

  @override
  String get adminScreenViewRoutePath => AppRoutes.sessionLogs;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<SessionLogsProvider>().refresh();
    });
  }

  @override
  void dispose() {
    _emailController.dispose();
    _minDurationController.dispose();
    super.dispose();
  }

  int? _parseMinDuration() {
    final t = _minDurationController.text.trim();
    if (t.isEmpty) return null;
    return int.tryParse(t);
  }

  void _applyFilters() {
    final p = context.read<SessionLogsProvider>();
    p.setFilters(
      userEmail: _emailController.text,
      activeOnly: _activeOnly,
      minDurationMinutes: _parseMinDuration(),
    );
    p.refresh();
  }

  /// Active sessions first, then most recent activity first (last activity → start → end).
  static DateTime _sessionLogSortTime(SessionLogItem log) {
    for (final iso in [
      log.lastActivityIso,
      log.sessionStartIso,
      log.sessionEndIso,
    ]) {
      if (iso != null && iso.isNotEmpty) {
        try {
          return DateTime.parse(iso);
        } catch (_) {}
      }
    }
    return DateTime.fromMillisecondsSinceEpoch(0);
  }

  static List<SessionLogItem> _sortedSessionLogs(List<SessionLogItem> items) {
    final copy = List<SessionLogItem>.from(items);
    copy.sort((a, b) {
      if (a.isActive != b.isActive) {
        return a.isActive ? -1 : 1;
      }
      return _sessionLogSortTime(b).compareTo(_sessionLogSortTime(a));
    });
    return copy;
  }

  void _clearFilters() {
    setState(() {
      _emailController.clear();
      _minDurationController.clear();
      _activeOnly = false;
    });
    final p = context.read<SessionLogsProvider>();
    p.setFilters(
      userEmail: null,
      activeOnly: false,
      minDurationMinutes: null,
    );
    p.refresh();
  }

  Future<void> _openFiltersBottomSheet() async {
    final loc = AppLocalizations.of(context)!;
    await showAdminFiltersBottomSheet<void>(
      context: context,
      builder: (sheetContext, setModalState) {
        return AdminFilterPanel(
          title: loc.adminFilters,
          surfaceCard: false,
          actions: AdminFilterPanelActions(
            applyLabel: loc.adminFiltersApply,
            clearLabel: loc.adminFiltersClear,
            onApply: () {
              _applyFilters();
              Navigator.of(sheetContext).pop();
            },
            onClear: () {
              _clearFilters();
              setModalState(() {});
              Navigator.of(sheetContext).pop();
            },
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextField(
                controller: _emailController,
                decoration: InputDecoration(
                  labelText: loc.email,
                  hintText: loc.sessionLogsEmailHint,
                ),
                keyboardType: TextInputType.emailAddress,
                autocorrect: false,
              ),
              AdminFilterPanel.fieldGap,
              TextField(
                controller: _minDurationController,
                decoration: InputDecoration(
                  labelText: loc.sessionLogsMinDuration,
                ),
                keyboardType: TextInputType.number,
                autocorrect: false,
              ),
              AdminFilterPanel.fieldGap,
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                dense: true,
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                title: Text(loc.sessionLogsActiveOnly),
                value: _activeOnly,
                onChanged: (v) {
                  setState(() => _activeOnly = v);
                  setModalState(() {});
                },
              ),
            ],
          ),
        );
      },
    );
  }

  Future<void> _confirmForceLogout(
    BuildContext context,
    SessionLogsProvider provider,
    SessionLogItem session,
    AppLocalizations loc,
  ) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(loc.sessionLogsForceLogout),
        content: Text(loc.sessionLogsForceLogoutConfirm),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: Text(loc.cancel),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text(loc.sessionLogsForceLogout),
          ),
        ],
      ),
    );
    if (ok != true) return;
    if (!context.mounted) return;

    final auth = context.read<AuthProvider>();
    final messenger = ScaffoldMessenger.of(context);
    setState(() => _endingSessionId = session.sessionId);
    final loggedSelfOut =
        await provider.forceLogoutSession(session.sessionId);
    if (!mounted) return;
    setState(() => _endingSessionId = null);

    if (loggedSelfOut) {
      await auth.logout();
      return;
    }
    if (provider.error != null) {
      messenger.showSnackBar(
        SnackBar(content: Text(provider.error!)),
      );
    } else {
      messenger.showSnackBar(
        SnackBar(content: Text(loc.sessionLogsEndedOk)),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final provider = context.watch<SessionLogsProvider>();

    return Scaffold(
      appBar: AppAppBar(
        title: loc.sessionLogsTitle,
        actions: [
          IconButton(
            icon: const Icon(Icons.tune),
            tooltip: loc.adminFilters,
            onPressed: _openFiltersBottomSheet,
          ),
        ],
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
            child: Text(
              loc.sessionLogsTotalCount(provider.total),
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),
          ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () => provider.refresh(),
              child: _buildBody(context, provider, loc),
            ),
          ),
        ],
      ),
    );
  }

  /// Scroll padding: base gap + system inset (nav bar / home indicator) + extra air below last row.
  EdgeInsets _listPadding(BuildContext context) {
    final bottom = MediaQuery.paddingOf(context).bottom;
    return EdgeInsets.fromLTRB(16, 0, 16, 32 + bottom + 16);
  }

  Widget _buildBody(
    BuildContext context,
    SessionLogsProvider provider,
    AppLocalizations loc,
  ) {
    if (provider.isLoading && provider.items.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: _listPadding(context),
        children: [
          SizedBox(
            height: MediaQuery.of(context).size.height * 0.35,
            child: const Center(child: CircularProgressIndicator()),
          ),
        ],
      );
    }

    if (provider.error != null && provider.items.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: _listPadding(context).copyWith(left: 24, right: 24, top: 24),
        children: [
          Icon(Icons.history, size: 48, color: Theme.of(context).colorScheme.error),
          const SizedBox(height: 16),
          Text(
            provider.error!,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyLarge,
          ),
          const SizedBox(height: 24),
          Center(
            child: FilledButton.icon(
              onPressed: () => provider.refresh(),
              icon: const Icon(Icons.refresh),
              label: Text(loc.retry),
            ),
          ),
        ],
      );
    }

    if (provider.items.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: _listPadding(context),
        children: [
          SizedBox(height: MediaQuery.of(context).size.height * 0.2),
          Center(child: Text(loc.sessionLogsNoEntries)),
        ],
      );
    }

    final dateFmt = DateFormat.yMMMd().add_jm();
    final sortedItems = _sortedSessionLogs(provider.items);

    return ListView.builder(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: _listPadding(context),
      itemCount: sortedItems.length + (provider.hasMore ? 1 : 0),
      itemBuilder: (context, i) {
        if (i >= sortedItems.length) {
          return Padding(
            padding: const EdgeInsets.only(top: 16),
            child: Center(
              child: provider.isLoadingMore
                  ? const CircularProgressIndicator()
                  : TextButton(
                      onPressed: () => provider.loadMore(),
                      child: Text(loc.sessionLogsLoadMore),
                    ),
            ),
          );
        }
        final log = sortedItems[i];
        return _SessionTile(
          log: log,
          dateFmt: dateFmt,
          localizations: loc,
          busy: _endingSessionId == log.sessionId,
          onForceLogout: log.isActive
              ? () => _confirmForceLogout(context, provider, log, loc)
              : null,
        );
      },
    );
  }
}

/// Leading icon for a session row: desktop, or mobile as Android vs Apple from OS/UA.
IconData _sessionDeviceLeadingIcon(SessionLogItem log) {
  final dt = log.deviceType?.toLowerCase().trim() ?? '';
  if (dt != 'mobile') {
    return Icons.laptop_mac;
  }
  final os = log.operatingSystem?.toLowerCase() ?? '';
  final ua = log.userAgent?.toLowerCase() ?? '';
  final s = '$os $ua';

  if (s.contains('iphone') ||
      s.contains('ipad') ||
      s.contains('ipod') ||
      s.contains('ios') ||
      s.contains('ipados')) {
    return Icons.apple;
  }
  if (s.contains('android')) {
    return Icons.android;
  }
  return Icons.smartphone;
}

Future<void> showSessionPathBreakdownSheet(
  BuildContext context,
  SessionLogItem log,
  AppLocalizations loc,
) async {
  final scheme = Theme.of(context).colorScheme;
  final textTheme = Theme.of(context).textTheme;
  final entries = log.sortedPathEntries;

  await showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (ctx) {
      final bottom = MediaQuery.paddingOf(ctx).bottom;
      final maxH = MediaQuery.sizeOf(ctx).height * 0.55;
      final Widget body = entries.isEmpty
          ? Text(
              loc.sessionLogsPathBreakdownEmpty,
              style: textTheme.bodyMedium?.copyWith(
                color: scheme.onSurfaceVariant,
              ),
            )
          : ConstrainedBox(
              constraints: BoxConstraints(maxHeight: maxH),
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: entries.length,
                separatorBuilder: (context, _) => Divider(
                  height: 1,
                  color: scheme.outlineVariant.withValues(alpha: 0.5),
                ),
                itemBuilder: (c, i) {
                  final e = entries[i];
                  final label = e.key == '_other'
                      ? loc.sessionLogsPathOtherBucket
                      : e.key;
                  return ListTile(
                    dense: true,
                    contentPadding:
                        const EdgeInsets.symmetric(horizontal: 4, vertical: 0),
                    title: Text(
                      label,
                      style: textTheme.bodySmall?.copyWith(
                        fontFamily: 'monospace',
                        fontSize: 12,
                      ),
                    ),
                    trailing: Text(
                      '${e.value}',
                      style: textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  );
                },
              ),
            );
      return SafeArea(
        child: Padding(
          padding: EdgeInsets.fromLTRB(16, 8, 16, 16 + bottom),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                loc.sessionLogsPathBreakdownTitle,
                style: textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
              ),
              if (entries.isEmpty && log.pageViews > 0) ...[
                const SizedBox(height: 8),
                Text(
                  '${loc.sessionLogsPageViews}: ${log.pageViews}',
                  style: textTheme.bodySmall?.copyWith(
                    color: scheme.onSurfaceVariant,
                  ),
                ),
              ],
              const SizedBox(height: 12),
              body,
            ],
          ),
        ),
      );
    },
  );
}

class _SessionTile extends StatefulWidget {
  const _SessionTile({
    required this.log,
    required this.dateFmt,
    required this.localizations,
    required this.busy,
    this.onForceLogout,
  });

  final SessionLogItem log;
  final DateFormat dateFmt;
  final AppLocalizations localizations;
  final bool busy;
  final VoidCallback? onForceLogout;

  @override
  State<_SessionTile> createState() => _SessionTileState();
}

class _SessionTileState extends State<_SessionTile>
    with SingleTickerProviderStateMixin {
  late AnimationController _flipController;
  late Animation<double> _flipAnimation;

  @override
  void initState() {
    super.initState();
    _flipController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 400),
    );
    _flipAnimation = CurvedAnimation(
      parent: _flipController,
      curve: Curves.easeInOutCubic,
    );
  }

  @override
  void dispose() {
    _flipController.dispose();
    super.dispose();
  }

  void _toggleFlip() {
    if (_flipController.isCompleted) {
      _flipController.reverse();
    } else {
      _flipController.forward();
    }
  }

  @override
  Widget build(BuildContext context) {
    final loc = widget.localizations;
    DateTime? start;
    DateTime? lastAct;
    DateTime? end;
    try {
      if (widget.log.sessionStartIso != null) {
        start = DateTime.parse(widget.log.sessionStartIso!);
      }
      if (widget.log.lastActivityIso != null) {
        lastAct = DateTime.parse(widget.log.lastActivityIso!);
      }
      if (widget.log.sessionEndIso != null) {
        end = DateTime.parse(widget.log.sessionEndIso!);
      }
    } catch (_) {}

    final userName = widget.log.userName?.trim();
    final userEmail = widget.log.userEmail?.trim();
    final displayName = (userName != null && userName.isNotEmpty)
        ? userName
        : loc.sessionLogsUnknownUser;

    final scheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    const activeBadgeGreen = Color(0xFF16A34A);
    final Color statusColor =
        widget.log.isActive ? activeBadgeGreen : scheme.outline;
    final statusLabel = widget.log.isActive
        ? loc.sessionLogsStatusActive
        : loc.sessionLogsStatusEnded;

    final startStr =
        start != null ? widget.dateFmt.format(start.toLocal()) : '—';
    final lastStr = lastAct != null
        ? widget.dateFmt.format(lastAct.toLocal())
        : loc.sessionLogsNoActivity;
    final activeMinutes = widget.log.activeDurationMinutes ??
        _sessionMinutesBetween(start, lastAct);
    final activeStr = activeMinutes != null
        ? loc.sessionLogsMinutes(activeMinutes)
        : '—';

    final wallMinutes = widget.log.durationMinutes ??
        _sessionMinutesBetween(start, end);
    final sessionLengthStr = wallMinutes != null
        ? loc.sessionLogsMinutes(wallMinutes)
        : '—';

    final cardSurface = elevatedListCardSurfaceColor(Theme.of(context));

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Material(
        color: cardSurface,
        elevation: 0,
        shadowColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
        clipBehavior: Clip.antiAlias,
        child: AnimatedBuilder(
          animation: _flipAnimation,
          builder: (context, _) {
            final showFront = _flipAnimation.value < 0.5;
            final angle = _flipAnimation.value * math.pi;
            return Padding(
              padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  GestureDetector(
                    onTap: _toggleFlip,
                    behavior: HitTestBehavior.opaque,
                    child: Transform(
                      transform: Matrix4.identity()
                        ..setEntry(3, 2, 0.001)
                        ..rotateY(angle),
                      alignment: Alignment.center,
                      child: angle <= math.pi / 2
                          ? _buildFrontFace(
                              context,
                              scheme: scheme,
                              textTheme: textTheme,
                              displayName: displayName,
                              email: (userEmail != null && userEmail.isNotEmpty)
                                  ? userEmail
                                  : null,
                              deviceIcon:
                                  _sessionDeviceLeadingIcon(widget.log),
                              statusColor: statusColor,
                              statusLabel: statusLabel,
                              activeStr: activeStr,
                            )
                          : Transform(
                              transform: Matrix4.identity()..rotateY(math.pi),
                              alignment: Alignment.center,
                              child: _buildBackFace(
                                context,
                                scheme: scheme,
                                textTheme: textTheme,
                                loc: loc,
                                startStr: startStr,
                                lastStr: lastStr,
                                sessionLengthStr: sessionLengthStr,
                              ),
                            ),
                    ),
                  ),
                  if (showFront)
                    ListCardFooterActions(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          if (widget.log.isActive &&
                              widget.onForceLogout != null)
                            Expanded(
                              child: Align(
                                alignment: AlignmentDirectional.centerStart,
                                child: TextButton.icon(
                                  onPressed:
                                      widget.busy ? null : widget.onForceLogout,
                                  icon: widget.busy
                                      ? SizedBox(
                                          width: 16,
                                          height: 16,
                                          child: CircularProgressIndicator(
                                            strokeWidth: 2,
                                            color: scheme.error,
                                          ),
                                        )
                                      : Icon(
                                          Icons.logout_rounded,
                                          size: 18,
                                          color: scheme.error,
                                        ),
                                  label: Text(loc.sessionLogsForceLogout),
                                  style: TextButton.styleFrom(
                                    foregroundColor: scheme.error,
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 8, vertical: 4),
                                    minimumSize: Size.zero,
                                    tapTargetSize:
                                        MaterialTapTargetSize.shrinkWrap,
                                    visualDensity: VisualDensity.compact,
                                    alignment: Alignment.centerLeft,
                                  ),
                                ),
                              ),
                            )
                          else
                            const Spacer(),
                          IconButton(
                            onPressed: _toggleFlip,
                            icon: Icon(
                              Icons.flip_outlined,
                              size: 20,
                              color: scheme.onSurfaceVariant,
                            ),
                            style: IconButton.styleFrom(
                              padding: const EdgeInsets.all(4),
                              minimumSize: Size.zero,
                              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                              visualDensity: VisualDensity.compact,
                            ),
                          ),
                        ],
                      ),
                    ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildFrontFace(
    BuildContext context, {
    required ColorScheme scheme,
    required TextTheme textTheme,
    required String displayName,
    required String? email,
    required IconData deviceIcon,
    required Color statusColor,
    required String statusLabel,
    required String activeStr,
  }) {
    return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Expanded(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Icon(
                      deviceIcon,
                      size: 18,
                      color: scheme.onSurfaceVariant,
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            displayName,
                            style: textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.w600,
                              height: 1.25,
                            ),
                          ),
                          if (email != null) ...[
                            const SizedBox(height: 2),
                            Text(
                              email,
                              style: textTheme.bodySmall?.copyWith(
                                color: scheme.onSurfaceVariant,
                                height: 1.2,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ],
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 8,
                  vertical: 3,
                ),
                decoration: BoxDecoration(
                  color: statusColor.withValues(alpha: 0.14),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(
                    color: statusColor.withValues(alpha: 0.35),
                    width: 1,
                  ),
                ),
                child: Text(
                  statusLabel,
                  style: TextStyle(
                    color: statusColor,
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.2,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 6,
            children: [
              Tooltip(
                message: widget.localizations.sessionLogsActiveTime,
                child: _statChip(
                  context,
                  null,
                  activeStr,
                  leadingIcon: Icons.touch_app_rounded,
                ),
              ),
              _statChip(
                context,
                widget.localizations.sessionLogsPageViews,
                '${widget.log.pageViews}',
              ),
              _statChip(
                context,
                widget.localizations.sessionLogsActivities,
                '${widget.log.activityCount}',
              ),
            ],
          ),
        ],
    );
  }

  Widget _buildBackFace(
    BuildContext context, {
    required ColorScheme scheme,
    required TextTheme textTheme,
    required AppLocalizations loc,
    required String startStr,
    required String lastStr,
    required String sessionLengthStr,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        _backTimeBlock(
          scheme: scheme,
          textTheme: textTheme,
          icon: Icons.schedule_rounded,
          label: loc.sessionLogsSessionStart,
          value: startStr,
        ),
        const SizedBox(height: 12),
        _backTimeBlock(
          scheme: scheme,
          textTheme: textTheme,
          icon: Icons.update_rounded,
          label: loc.sessionLogsLastActivity,
          value: lastStr,
        ),
        const SizedBox(height: 12),
        _backTimeBlock(
          scheme: scheme,
          textTheme: textTheme,
          icon: Icons.timelapse_rounded,
          label: loc.sessionLogsSessionLength,
          value: sessionLengthStr,
        ),
        ..._buildSessionPathsSection(
          context,
          scheme: scheme,
          textTheme: textTheme,
          loc: loc,
        ),
        ..._buildSessionDeviceDetails(
          scheme: scheme,
          textTheme: textTheme,
          loc: loc,
        ),
      ],
    );
  }

  List<Widget> _buildSessionPathsSection(
    BuildContext context, {
    required ColorScheme scheme,
    required TextTheme textTheme,
    required AppLocalizations loc,
  }) {
    final log = widget.log;
    final hasPathStats = log.pageViews > 0 ||
        log.distinctPageViewPaths > 0 ||
        log.pageViewPathCounts.isNotEmpty;
    if (!hasPathStats) return const [];

    return [
      const SizedBox(height: 14),
      DecoratedBox(
        decoration: BoxDecoration(
          color: scheme.surfaceContainerHigh.withValues(alpha: 0.45),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: scheme.outlineVariant.withValues(alpha: 0.45),
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(
                    Icons.alt_route_rounded,
                    size: 18,
                    color: scheme.onSurfaceVariant,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      loc.sessionLogsPathBreakdownTitle,
                      style: textTheme.labelLarge?.copyWith(
                        fontWeight: FontWeight.w700,
                        color: scheme.onSurface,
                        letterSpacing: 0.2,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 6,
                children: [
                  _statChip(
                    context,
                    loc.sessionLogsPageViews,
                    '${log.pageViews}',
                  ),
                  if (log.distinctPageViewPaths > 0)
                    _statChip(
                      context,
                      loc.sessionLogsDistinctPaths,
                      '${log.distinctPageViewPaths}',
                      leadingIcon: Icons.alt_route_rounded,
                    ),
                ],
              ),
              const SizedBox(height: 10),
              Align(
                alignment: AlignmentDirectional.centerStart,
                child: TextButton.icon(
                  onPressed: () => showSessionPathBreakdownSheet(
                    context,
                    log,
                    loc,
                  ),
                  icon: Icon(
                    Icons.view_list_rounded,
                    size: 18,
                    color: scheme.primary,
                  ),
                  label: Text(loc.sessionLogsPathBreakdownOpen),
                  style: TextButton.styleFrom(
                    foregroundColor: scheme.primary,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 4,
                    ),
                    minimumSize: Size.zero,
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    visualDensity: VisualDensity.compact,
                    alignment: AlignmentDirectional.centerStart,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    ];
  }

  Widget _backTimeBlock({
    required ColorScheme scheme,
    required TextTheme textTheme,
    required IconData icon,
    required String label,
    required String value,
  }) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Icon(
          icon,
          size: 20,
          color: scheme.primary,
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label,
                style: textTheme.labelMedium?.copyWith(
                  color: scheme.onSurfaceVariant,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.15,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                value,
                style: textTheme.bodyLarge?.copyWith(
                  fontWeight: FontWeight.w600,
                  height: 1.25,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  bool _hasNonEmpty(String? s) => s != null && s.trim().isNotEmpty;

  String _titleCaseDeviceKind(String raw) {
    final t = raw.trim();
    if (t.isEmpty) return t;
    return t.length == 1
        ? t.toUpperCase()
        : '${t[0].toUpperCase()}${t.substring(1).toLowerCase()}';
  }

  List<Widget> _buildSessionDeviceDetails({
    required ColorScheme scheme,
    required TextTheme textTheme,
    required AppLocalizations loc,
  }) {
    final log = widget.log;
    final hasDetails = _hasNonEmpty(log.deviceType) ||
        _hasNonEmpty(log.operatingSystem) ||
        _hasNonEmpty(log.browser) ||
        _hasNonEmpty(log.ipAddress) ||
        _hasNonEmpty(log.userAgent);
    if (!hasDetails) return const [];

    final rows = <Widget>[];
    if (_hasNonEmpty(log.deviceType)) {
      rows.add(
        _backKvRow(
          scheme: scheme,
          textTheme: textTheme,
          label: loc.loginLogsDevice,
          value: _titleCaseDeviceKind(log.deviceType!),
        ),
      );
    }
    if (_hasNonEmpty(log.operatingSystem)) {
      rows.add(
        _backKvRow(
          scheme: scheme,
          textTheme: textTheme,
          label: loc.sessionLogsOs,
          value: log.operatingSystem!.trim(),
        ),
      );
    }
    if (_hasNonEmpty(log.browser)) {
      rows.add(
        _backKvRow(
          scheme: scheme,
          textTheme: textTheme,
          label: loc.loginLogsBrowser,
          value: log.browser!.trim(),
        ),
      );
    }
    if (_hasNonEmpty(log.ipAddress)) {
      rows.add(
        _backKvRow(
          scheme: scheme,
          textTheme: textTheme,
          label: loc.loginLogsIpLabel,
          value: log.ipAddress!.trim(),
        ),
      );
    }

    final ua = _hasNonEmpty(log.userAgent) ? log.userAgent!.trim() : null;

    return [
      const SizedBox(height: 14),
      DecoratedBox(
        decoration: BoxDecoration(
          color: scheme.surfaceContainerHigh.withValues(alpha: 0.45),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: scheme.outlineVariant.withValues(alpha: 0.45),
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(
                    Icons.devices_other_rounded,
                    size: 18,
                    color: scheme.onSurfaceVariant,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      loc.sessionLogsDeviceSection,
                      style: textTheme.labelLarge?.copyWith(
                        fontWeight: FontWeight.w700,
                        color: scheme.onSurface,
                        letterSpacing: 0.2,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              if (rows.isNotEmpty)
                ..._withSpacingBetween(rows, 10),
              if (ua != null) ...[
                if (rows.isNotEmpty) const SizedBox(height: 12),
                Text(
                  loc.sessionLogsUserAgent,
                  style: textTheme.labelMedium?.copyWith(
                    color: scheme.onSurfaceVariant,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 6),
                DecoratedBox(
                  decoration: BoxDecoration(
                    color: scheme.surfaceContainerHighest.withValues(alpha: 0.65),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(
                      color: scheme.outlineVariant.withValues(alpha: 0.3),
                    ),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.all(10),
                    child: SelectableText(
                      ua,
                      style: textTheme.bodySmall?.copyWith(
                        fontWeight: FontWeight.w400,
                        fontFamily: 'monospace',
                        height: 1.4,
                      ),
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    ];
  }

  List<Widget> _withSpacingBetween(List<Widget> children, double gap) {
    if (children.isEmpty) return const [];
    final out = <Widget>[children.first];
    for (var i = 1; i < children.length; i++) {
      out.add(SizedBox(height: gap));
      out.add(children[i]);
    }
    return out;
  }

  Widget _backKvRow({
    required ColorScheme scheme,
    required TextTheme textTheme,
    required String label,
    required String value,
  }) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          flex: 12,
          child: Text(
            label,
            style: textTheme.labelMedium?.copyWith(
              color: scheme.onSurfaceVariant,
              fontWeight: FontWeight.w600,
              height: 1.25,
            ),
          ),
        ),
        Expanded(
          flex: 15,
          child: Text(
            value,
            style: textTheme.bodyMedium?.copyWith(
              fontWeight: FontWeight.w500,
              height: 1.3,
            ),
            textAlign: TextAlign.end,
          ),
        ),
      ],
    );
  }

  Widget _statChip(
    BuildContext context,
    String? label,
    String value, {
    IconData? leadingIcon,
  }) {
    final scheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHigh.withValues(alpha: 0.85),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: scheme.outlineVariant.withValues(alpha: 0.35),
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (leadingIcon != null) ...[
            Icon(
              leadingIcon,
              size: 14,
              color: scheme.onSurfaceVariant,
            ),
            const SizedBox(width: 6),
          ],
          Text.rich(
            TextSpan(
              children: [
                if (label != null && label.isNotEmpty)
                  TextSpan(
                    text: '$label ',
                    style: textTheme.labelSmall?.copyWith(
                      color: scheme.onSurfaceVariant,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                TextSpan(
                  text: value,
                  style: textTheme.labelLarge?.copyWith(
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.2,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
