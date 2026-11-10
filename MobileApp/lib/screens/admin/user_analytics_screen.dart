import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import '../../providers/admin/user_analytics_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../widgets/app_bar.dart';
import '../../providers/shared/tab_customization_provider.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/error_state.dart';
import '../../widgets/loading_indicator.dart';
import '../../config/routes.dart';
import '../../utils/admin_screen_view_logging_mixin.dart';
import '../../utils/constants.dart';
import '../../utils/ios_constants.dart';
import '../../utils/theme_extensions.dart';
import '../../l10n/app_localizations.dart';

class UserAnalyticsScreen extends StatefulWidget {
  const UserAnalyticsScreen({super.key});

  @override
  State<UserAnalyticsScreen> createState() => _UserAnalyticsScreenState();
}

class _UserAnalyticsScreenState extends State<UserAnalyticsScreen>
    with SingleTickerProviderStateMixin, AdminScreenViewLoggingMixin {
  late final TabController _tabs;

  @override
  String get adminScreenViewRoutePath => AppRoutes.userAnalytics;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _load();
    });
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  Future<void> _load() {
    return Provider.of<UserAnalyticsProvider>(context, listen: false)
        .loadAnalytics();
  }

  int _intVal(Map<String, dynamic> data, String key) {
    final v = data[key];
    if (v is int) return v;
    return int.tryParse(v?.toString() ?? '') ?? 0;
  }

  String _formatCount(BuildContext context, int value) {
    final locale = Localizations.localeOf(context).toString();
    try {
      return NumberFormat.decimalPattern(locale).format(value);
    } catch (_) {
      return NumberFormat.decimalPattern().format(value);
    }
  }

  String _formatTimestamp(BuildContext context, String? iso) {
    if (iso == null || iso.isEmpty) return '';
    final dt = DateTime.tryParse(iso);
    if (dt == null) return iso;
    final locale = Localizations.localeOf(context).toString();
    try {
      return DateFormat.MMMd(locale).add_jm().format(dt.toLocal());
    } catch (_) {
      return DateFormat.MMMd().add_jm().format(dt.toLocal());
    }
  }

  String _humanize(String? raw) {
    final trimmed = raw?.trim() ?? '';
    if (trimmed.isEmpty) return '';
    return trimmed.replaceAll('_', ' ');
  }

  List<Map<String, dynamic>> _mapList(dynamic raw) {
    if (raw is! List) return const [];
    return [
      for (final row in raw)
        if (row is Map) Map<String, dynamic>.from(row),
    ];
  }

  bool _asBool(dynamic value, {bool fallback = true}) {
    if (value is bool) return value;
    if (value is num) return value != 0;
    final text = value?.toString().toLowerCase();
    if (text == null || text.isEmpty) return fallback;
    if (text == 'true' || text == '1' || text == 'yes') return true;
    if (text == 'false' || text == '0' || text == 'no') return false;
    return fallback;
  }

  String _displayName(AppLocalizations localizations, String? raw) {
    final name = raw?.trim() ?? '';
    if (name.isEmpty || name == 'Unknown' || name == '—') {
      return localizations.unknownUser;
    }
    return name;
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final chatbot = context.watch<AuthProvider>().user?.chatbotEnabled ?? false;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: localizations.userAnalytics,
      ),
      body: Consumer<UserAnalyticsProvider>(
        builder: (context, provider, child) {
          if (provider.isLoading && provider.analyticsData == null) {
            return AppLoadingIndicator(
              message: localizations.loadingAnalytics,
              color: Color(AppConstants.ifrcRed),
              useIOSStyle: false,
            );
          }

          if (provider.error != null && provider.analyticsData == null) {
            return AppErrorState(
              message: provider.error!,
              onRetry: () {
                provider.clearError();
                _load();
              },
              retryLabel: localizations.retry,
              retryStyle: AppErrorRetryStyle.materialOutlined,
              iconColor: Color(AppConstants.ifrcRed),
            );
          }

          final data = provider.analyticsData;
          if (data == null || data.isEmpty) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    Icons.bar_chart_outlined,
                    size: 56,
                    color: context.textSecondaryColor,
                  ),
                  const SizedBox(height: 16),
                  Text(
                    localizations.noDataAvailable,
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                      color: context.textColor,
                    ),
                  ),
                ],
              ),
            );
          }

          final activity = data['activity'];
          final activityMap =
              activity is Map ? Map<String, dynamic>.from(activity) : null;
          final recentActivity = _mapList(activityMap?['recent_activity']);
          final recentLogins = _mapList(activityMap?['recent_logins']);
          final recentSecurity =
              _mapList(activityMap?['recent_security_events']);

          return Column(
            children: [
              Material(
                color: theme.scaffoldBackgroundColor,
                child: TabBar(
                  controller: _tabs,
                  indicatorColor: Color(AppConstants.ifrcRed),
                  indicatorWeight: 2.5,
                  indicatorSize: TabBarIndicatorSize.tab,
                  labelColor: Color(AppConstants.ifrcRed),
                  unselectedLabelColor: context.textSecondaryColor,
                  dividerColor: context.dividerColor,
                  labelStyle: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                  ),
                  unselectedLabelStyle: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                  tabs: [
                    Tab(text: localizations.overview),
                    Tab(
                      child: _ActivityTabLabel(
                        label: localizations.recentActivity,
                        count: recentActivity.length +
                            recentLogins.length +
                            recentSecurity.length,
                      ),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: TabBarView(
                  controller: _tabs,
                  children: [
                    _buildOverview(context, localizations, data),
                    _buildActivity(
                      context,
                      localizations,
                      recentActivity: recentActivity,
                      recentLogins: recentLogins,
                      recentSecurity: recentSecurity,
                    ),
                  ],
                ),
              ),
            ],
          );
        },
      ),
      bottomNavigationBar: AppBottomNavigationBar(
        currentIndex: AppBottomNavigationBar.adminTabNavIndex(
          chatbotEnabled: chatbot,
        ),
        selectedTabId: TabIds.admin,
        chatbotEnabled: chatbot,
      ),
    );
  }

  Widget _buildOverview(
    BuildContext context,
    AppLocalizations localizations,
    Map<String, dynamic> data,
  ) {
    final theme = Theme.of(context);
    final brand = Color(AppConstants.ifrcRed);
    final usersColor = IOSColors.getSystemBlue(context);
    final activityColor = IOSColors.getSystemGreen(context);

    final pending = _intVal(data, 'pending_public_submissions_count');
    final overdue = _intVal(data, 'overdue_assignments');
    final failed = _intVal(data, 'failed_logins_24h');

    final attention = <_AttentionItem>[
      if (pending > 0)
        _AttentionItem(
          title: localizations.pendingSubmissions,
          value: _formatCount(context, pending),
          icon: Icons.pending_actions_outlined,
          color: IOSColors.systemOrange,
        ),
      if (overdue > 0)
        _AttentionItem(
          title: localizations.overdueAssignments,
          value: _formatCount(context, overdue),
          icon: Icons.event_busy_outlined,
          color: theme.colorScheme.error,
        ),
      if (failed > 0)
        _AttentionItem(
          title: '${localizations.loginLogsEventFailed} (24h)',
          value: _formatCount(context, failed),
          icon: Icons.gpp_maybe_outlined,
          color: theme.colorScheme.error,
        ),
    ];

    return RefreshIndicator(
      onRefresh: _load,
      color: brand,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
        children: [
          if (attention.isNotEmpty) ...[
            _buildAttentionCard(context, localizations, attention),
            const SizedBox(height: 20),
          ],
          _buildSectionLabel(context, localizations.keyMetrics),
          _buildStatGrid([
            _Stat(
              title: localizations.countries,
              value: _formatCount(context, _intVal(data, 'country_count')),
              icon: Icons.public_rounded,
              color: brand,
            ),
            _Stat(
              title: localizations.templates,
              value: _formatCount(context, _intVal(data, 'template_count')),
              icon: Icons.description_outlined,
              color: brand,
            ),
            _Stat(
              title: localizations.assignments,
              value: _formatCount(context, _intVal(data, 'assignment_count')),
              icon: Icons.assignment_outlined,
              color: brand,
            ),
            _Stat(
              title: localizations.indicators,
              value:
                  _formatCount(context, _intVal(data, 'indicator_bank_count')),
              icon: Icons.analytics_outlined,
              color: brand,
            ),
          ]),
          const SizedBox(height: 20),
          _buildSectionLabel(context, localizations.manageUsers),
          _buildStatGrid([
            _Stat(
              title: localizations.totalUsers,
              value: _formatCount(context, _intVal(data, 'user_count')),
              icon: Icons.people_outline_rounded,
              color: usersColor,
            ),
            _Stat(
              title:
                  '${localizations.activeUsers} (${localizations.last30Days})',
              value: _formatCount(context, _intVal(data, 'active_users')),
              icon: Icons.person_search_outlined,
              color: usersColor,
            ),
            _Stat(
              title: localizations.systemAdministrators,
              value: _formatCount(context, _intVal(data, 'admin_count')),
              icon: Icons.admin_panel_settings_outlined,
              color: usersColor,
            ),
            _Stat(
              title: localizations.focalPoints,
              value: _formatCount(context, _intVal(data, 'focal_point_count')),
              icon: Icons.groups_outlined,
              color: usersColor,
            ),
          ]),
          const SizedBox(height: 20),
          _buildSectionLabel(context, localizations.recentActivity7Days),
          _buildStatGrid([
            _Stat(
              title: localizations.successfulLoginsToday,
              value: _formatCount(context, _intVal(data, 'today_logins')),
              icon: Icons.today_outlined,
              color: activityColor,
            ),
            _Stat(
              title:
                  '${localizations.successfulLogins} (${localizations.last7Days})',
              value: _formatCount(context, _intVal(data, 'recent_logins')),
              icon: Icons.login_rounded,
              color: activityColor,
            ),
            _Stat(
              title: localizations.metricSubmissions,
              value: _formatCount(
                context,
                _intVal(data, 'public_submission_count'),
              ),
              icon: Icons.inbox_outlined,
              color: activityColor,
            ),
            _Stat(
              title:
                  '${localizations.metricSubmissions} (${localizations.last7Days})',
              value:
                  _formatCount(context, _intVal(data, 'recent_submissions')),
              icon: Icons.move_to_inbox_outlined,
              color: activityColor,
            ),
          ]),
        ],
      ),
    );
  }

  Widget _buildAttentionCard(
    BuildContext context,
    AppLocalizations localizations,
    List<_AttentionItem> items,
  ) {
    final theme = Theme.of(context);
    final accent = items.any(
      (item) => item.color == theme.colorScheme.error,
    )
        ? theme.colorScheme.error
        : IOSColors.systemOrange;

    return DecoratedBox(
      decoration: BoxDecoration(
        color: context.cardColor,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: accent.withValues(alpha: 0.28)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 14, 14, 6),
            child: Text(
              localizations.itemsRequiringAttention.toUpperCase(),
              style: IOSTextStyle.footnote(context).copyWith(
                fontWeight: FontWeight.w700,
                letterSpacing: 0.5,
              ),
            ),
          ),
          for (var i = 0; i < items.length; i++) ...[
            if (i > 0)
              Divider(
                height: 1,
                thickness: 0.5,
                indent: 58,
                color: context.dividerColor,
              ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              child: Row(
                children: [
                  _IconBadge(icon: items[i].icon, color: items[i].color),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      items[i].title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        color: context.textColor,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    items[i].value,
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                      color: items[i].color,
                    ),
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 4),
        ],
      ),
    );
  }

  Widget _buildActivity(
    BuildContext context,
    AppLocalizations localizations, {
    required List<Map<String, dynamic>> recentActivity,
    required List<Map<String, dynamic>> recentLogins,
    required List<Map<String, dynamic>> recentSecurity,
  }) {
    final brand = Color(AppConstants.ifrcRed);
    final sections = <Widget>[];

    if (recentActivity.isNotEmpty) {
      sections.add(
        _buildFeedSection(
          context,
          title: localizations.recentActivity,
          count: recentActivity.length,
          entries: [
            for (final row in recentActivity)
              _activityEntry(context, localizations, row),
          ],
        ),
      );
    }

    if (recentLogins.isNotEmpty) {
      sections.add(
        _buildFeedSection(
          context,
          title: localizations.loginLogsTitle,
          count: recentLogins.length,
          entries: [
            for (final row in recentLogins)
              _loginEntry(context, localizations, row),
          ],
        ),
      );
    }

    if (recentSecurity.isNotEmpty) {
      sections.add(
        _buildFeedSection(
          context,
          title: localizations.securityAlerts,
          count: recentSecurity.length,
          entries: [
            for (final row in recentSecurity)
              _securityEntry(context, localizations, row),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _load,
      color: brand,
      child: sections.isEmpty
          ? LayoutBuilder(
              builder: (context, constraints) {
                return ListView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  children: [
                    SizedBox(
                      height: constraints.maxHeight,
                      child: _buildEmptyActivity(context, localizations),
                    ),
                  ],
                );
              },
            )
          : ListView.separated(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
              itemCount: sections.length,
              separatorBuilder: (_, _) => const SizedBox(height: 20),
              itemBuilder: (_, index) => sections[index],
            ),
    );
  }

  _FeedEntry _activityEntry(
    BuildContext context,
    AppLocalizations localizations,
    Map<String, dynamic> row,
  ) {
    final name = _displayName(localizations, row['user_name']?.toString());
    final rawAction = row['action']?.toString().trim() ?? '';
    final action = _humanize(rawAction);
    final details = row['details']?.toString().trim();
    final ip = row['ip_address']?.toString().trim();
    return _FeedEntry(
      headline: name,
      icon: _activityIcon(action),
      accent: Color(AppConstants.ifrcRed),
      detail: action,
      subtitle: (details != null &&
              details.isNotEmpty &&
              details != rawAction &&
              details != action)
          ? details
          : null,
      meta: (ip != null && ip.isNotEmpty)
          ? '${localizations.loginLogsIpLabel}: $ip'
          : null,
      time: _formatTimestamp(context, row['timestamp']?.toString()),
    );
  }

  _FeedEntry _loginEntry(
    BuildContext context,
    AppLocalizations localizations,
    Map<String, dynamic> row,
  ) {
    final name = _displayName(localizations, row['user_name']?.toString());
    final success = _asBool(row['success']);
    final ip = row['ip_address']?.toString().trim();
    final color = success
        ? IOSColors.getSystemGreen(context)
        : Theme.of(context).colorScheme.error;
    return _FeedEntry(
      headline: name,
      icon: success ? Icons.login_rounded : Icons.gpp_bad_outlined,
      accent: color,
      detail: success
          ? localizations.loginLogsEventLogin
          : localizations.loginLogsEventFailed,
      meta: (ip != null && ip.isNotEmpty)
          ? '${localizations.loginLogsIpLabel}: $ip'
          : null,
      time: _formatTimestamp(context, row['login_time']?.toString()),
    );
  }

  _FeedEntry _securityEntry(
    BuildContext context,
    AppLocalizations localizations,
    Map<String, dynamic> row,
  ) {
    final event = _humanize(row['event_type']?.toString());
    final description = row['description']?.toString().trim();
    final ip = row['ip_address']?.toString().trim();
    return _FeedEntry(
      headline: event.isEmpty ? localizations.securityAlerts : event,
      icon: Icons.shield_outlined,
      accent: IOSColors.systemOrange,
      subtitle: (description != null &&
              description.isNotEmpty &&
              description != event)
          ? description
          : null,
      meta: (ip != null && ip.isNotEmpty)
          ? '${localizations.loginLogsIpLabel}: $ip'
          : null,
      time: _formatTimestamp(context, row['occurred_at']?.toString()),
    );
  }

  IconData _activityIcon(String action) {
    final text = action.toLowerCase();
    if (text.contains('delete') || text.contains('remove')) {
      return Icons.delete_outline_rounded;
    }
    if (text.contains('create') || text.contains('add')) {
      return Icons.add_circle_outline_rounded;
    }
    if (text.contains('update') || text.contains('edit')) {
      return Icons.edit_outlined;
    }
    if (text.contains('login') || text.contains('logout')) {
      return Icons.login_rounded;
    }
    if (text.contains('submit')) return Icons.outbox_outlined;
    return Icons.history_rounded;
  }

  Widget _buildFeedSection(
    BuildContext context, {
    required String title,
    required int count,
    required List<_FeedEntry> entries,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionLabel(
          context,
          '$title · ${_formatCount(context, count)}',
        ),
        DecoratedBox(
          decoration: BoxDecoration(
            color: context.cardColor,
            borderRadius: BorderRadius.circular(14),
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(14),
            child: Column(
              children: [
                for (var i = 0; i < entries.length; i++) ...[
                  if (i > 0)
                    Divider(
                      height: 1,
                      thickness: 0.5,
                      indent: 64,
                      color: context.dividerColor,
                    ),
                  _FeedRow(entry: entries[i]),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildEmptyActivity(
    BuildContext context,
    AppLocalizations localizations,
  ) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.history_toggle_off_rounded,
              size: 48,
              color: context.textSecondaryColor,
            ),
            const SizedBox(height: 12),
            Text(
              localizations.noRecentActivities,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: context.textColor,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSectionLabel(BuildContext context, String title) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Text(
        title.toUpperCase(),
        style: IOSTextStyle.footnote(context).copyWith(
          fontWeight: FontWeight.w700,
          letterSpacing: 0.5,
        ),
      ),
    );
  }

  Widget _buildStatGrid(List<_Stat> stats) {
    final rows = <Widget>[];
    for (var i = 0; i < stats.length; i += 2) {
      if (rows.isNotEmpty) rows.add(const SizedBox(height: 12));
      final right = i + 1 < stats.length ? stats[i + 1] : null;
      rows.add(
        IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(child: _StatTile(stat: stats[i])),
              const SizedBox(width: 12),
              Expanded(
                child: right == null
                    ? const SizedBox.shrink()
                    : _StatTile(stat: right),
              ),
            ],
          ),
        ),
      );
    }
    return Column(children: rows);
  }
}

class _Stat {
  final String title;
  final String value;
  final IconData icon;
  final Color color;

  const _Stat({
    required this.title,
    required this.value,
    required this.icon,
    required this.color,
  });
}

class _AttentionItem {
  final String title;
  final String value;
  final IconData icon;
  final Color color;

  const _AttentionItem({
    required this.title,
    required this.value,
    required this.icon,
    required this.color,
  });
}

class _FeedEntry {
  final String headline;
  final IconData icon;
  final Color accent;
  final String? detail;
  final String? subtitle;
  final String? meta;
  final String time;

  const _FeedEntry({
    required this.headline,
    required this.icon,
    required this.accent,
    this.detail,
    this.subtitle,
    this.meta,
    required this.time,
  });
}

class _ActivityTabLabel extends StatelessWidget {
  final String label;
  final int count;

  const _ActivityTabLabel({
    required this.label,
    required this.count,
  });

  @override
  Widget build(BuildContext context) {
    final brand = Color(AppConstants.ifrcRed);
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Flexible(
          child: Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        if (count > 0) ...[
          const SizedBox(width: 6),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
            decoration: BoxDecoration(
              color: brand.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(99),
            ),
            child: Text(
              count > 99 ? '99+' : '$count',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w700,
                color: brand,
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _IconBadge extends StatelessWidget {
  final IconData icon;
  final Color color;

  const _IconBadge({required this.icon, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 36,
      height: 36,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Icon(icon, color: color, size: 20),
    );
  }
}

class _StatTile extends StatelessWidget {
  final _Stat stat;

  const _StatTile({required this.stat});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: '${stat.title}: ${stat.value}',
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: context.cardColor,
          borderRadius: BorderRadius.circular(14),
        ),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _IconBadge(icon: stat.icon, color: stat.color),
              const SizedBox(height: 12),
              FittedBox(
                fit: BoxFit.scaleDown,
                alignment: AlignmentDirectional.centerStart,
                child: Text(
                  stat.value,
                  style: IOSTextStyle.title2(context).copyWith(
                    fontWeight: FontWeight.w800,
                    height: 1.05,
                    color: context.textColor,
                  ),
                ),
              ),
              const SizedBox(height: 4),
              Text(
                stat.title,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: IOSTextStyle.footnote(context).copyWith(
                  fontWeight: FontWeight.w500,
                  height: 1.25,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _FeedRow extends StatelessWidget {
  final _FeedEntry entry;

  const _FeedRow({required this.entry});

  @override
  Widget build(BuildContext context) {
    final secondary = context.textSecondaryColor;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _IconBadge(icon: entry.icon, color: entry.accent),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  entry.headline,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontWeight: FontWeight.w700,
                    color: context.textColor,
                  ),
                ),
                if (entry.detail != null && entry.detail!.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(
                    entry.detail!,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 13, color: secondary),
                  ),
                ],
                if (entry.subtitle != null && entry.subtitle!.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(
                    entry.subtitle!,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 12, color: secondary),
                  ),
                ],
                if (entry.meta != null && entry.meta!.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(
                    entry.meta!,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 12, color: secondary),
                  ),
                ],
                if (entry.time.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    entry.time,
                    style: TextStyle(
                      fontSize: 11,
                      color: secondary.withValues(alpha: 0.9),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
