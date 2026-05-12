import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import '../../providers/admin/user_analytics_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/error_state.dart';
import '../../widgets/loading_indicator.dart';
import '../../config/routes.dart';
import '../../utils/admin_screen_view_logging_mixin.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../l10n/app_localizations.dart';

class UserAnalyticsScreen extends StatefulWidget {
  const UserAnalyticsScreen({super.key});

  @override
  State<UserAnalyticsScreen> createState() => _UserAnalyticsScreenState();
}

class _UserAnalyticsScreenState extends State<UserAnalyticsScreen>
    with AdminScreenViewLoggingMixin {
  @override
  String get adminScreenViewRoutePath => AppRoutes.userAnalytics;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _load();
    });
  }

  void _load() {
    Provider.of<UserAnalyticsProvider>(context, listen: false).loadAnalytics();
  }

  int _intVal(Map<String, dynamic> data, String key) {
    final v = data[key];
    if (v is int) return v;
    return int.tryParse(v?.toString() ?? '') ?? 0;
  }

  String _formatTimestamp(BuildContext context, String? iso) {
    if (iso == null || iso.isEmpty) return '';
    final dt = DateTime.tryParse(iso);
    if (dt == null) return iso;
    final locale = Localizations.localeOf(context).toString();
    try {
      return DateFormat.yMMMd(locale).add_jm().format(dt.toLocal());
    } catch (_) {
      return DateFormat.yMMMd().add_jm().format(dt.toLocal());
    }
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

          final pending = _intVal(data, 'pending_public_submissions_count');
          final overdue = _intVal(data, 'overdue_assignments');
          final failed = _intVal(data, 'failed_logins_24h');
          final hasAttention = pending > 0 || overdue > 0 || failed > 0;

          final activity = data['activity'];
          final recentActivity = activity is Map
              ? activity['recent_activity'] as List<dynamic>?
              : null;

          return RefreshIndicator(
            onRefresh: () async => _load(),
            color: Color(AppConstants.ifrcRed),
            child: SingleChildScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildSectionLabel(context, localizations.keyMetrics),
                  _buildStatCard(
                    localizations.countries,
                    _intVal(data, 'country_count').toString(),
                    Icons.public,
                  ),
                  _buildStatCard(
                    localizations.templates,
                    _intVal(data, 'template_count').toString(),
                    Icons.description_outlined,
                  ),
                  _buildStatCard(
                    localizations.assignments,
                    _intVal(data, 'assignment_count').toString(),
                    Icons.assignment_outlined,
                  ),
                  _buildStatCard(
                    localizations.indicators,
                    _intVal(data, 'indicator_bank_count').toString(),
                    Icons.analytics_outlined,
                  ),
                  const SizedBox(height: 8),
                  if (hasAttention) ...[
                    _buildSectionLabel(
                        context, localizations.itemsRequiringAttention),
                    if (pending > 0)
                      _buildStatCard(
                        localizations.pendingSubmissions,
                        pending.toString(),
                        Icons.pending_actions_outlined,
                        accent: Colors.orange,
                      ),
                    if (overdue > 0)
                      _buildStatCard(
                        localizations.overdueAssignments,
                        overdue.toString(),
                        Icons.event_busy_outlined,
                        accent: theme.colorScheme.error,
                      ),
                    if (failed > 0)
                      _buildStatCard(
                        '${localizations.loginLogsEventFailed} (24h)',
                        failed.toString(),
                        Icons.gpp_maybe_outlined,
                        accent: theme.colorScheme.error,
                      ),
                    const SizedBox(height: 8),
                  ],
                  _buildSectionLabel(context, localizations.manageUsers),
                  _buildStatCard(
                    localizations.totalUsers,
                    _intVal(data, 'user_count').toString(),
                    Icons.people_outline,
                  ),
                  _buildStatCard(
                    '${localizations.activeUsers} (${localizations.last30Days})',
                    _intVal(data, 'active_users').toString(),
                    Icons.person_search_outlined,
                  ),
                  _buildStatCard(
                    localizations.systemAdministrators,
                    _intVal(data, 'admin_count').toString(),
                    Icons.admin_panel_settings_outlined,
                  ),
                  _buildStatCard(
                    localizations.focalPoints,
                    _intVal(data, 'focal_point_count').toString(),
                    Icons.groups_outlined,
                  ),
                  const SizedBox(height: 8),
                  _buildSectionLabel(context, localizations.recentActivity7Days),
                  _buildStatCard(
                    localizations.successfulLoginsToday,
                    _intVal(data, 'today_logins').toString(),
                    Icons.today_outlined,
                  ),
                  _buildStatCard(
                    '${localizations.successfulLogins} (${localizations.last7Days})',
                    _intVal(data, 'recent_logins').toString(),
                    Icons.login,
                  ),
                  _buildStatCard(
                    localizations.metricSubmissions,
                    _intVal(data, 'public_submission_count').toString(),
                    Icons.inbox_outlined,
                  ),
                  _buildStatCard(
                    '${localizations.metricSubmissions} (${localizations.last7Days})',
                    _intVal(data, 'recent_submissions').toString(),
                    Icons.move_to_inbox,
                  ),
                  if (recentActivity != null && recentActivity.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    _buildSectionLabel(context, localizations.recentActivity),
                    Card(
                      elevation: 0,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                        side: BorderSide(
                          color: context.borderColor,
                          width: 1,
                        ),
                      ),
                      child: ListView.separated(
                        shrinkWrap: true,
                        physics: const NeverScrollableScrollPhysics(),
                        itemCount: recentActivity.length.clamp(0, 12),
                        separatorBuilder: (_, _) => Divider(
                          height: 1,
                          color: context.borderColor,
                        ),
                        itemBuilder: (context, index) {
                          final row = recentActivity[index];
                          if (row is! Map) {
                            return const SizedBox.shrink();
                          }
                          final name =
                              row['user_name']?.toString() ?? '—';
                          final action =
                              row['action']?.toString() ?? '';
                          final details = row['details']?.toString();
                          final ts = _formatTimestamp(
                            context,
                            row['timestamp']?.toString(),
                          );
                          return ListTile(
                            dense: true,
                            title: Text(
                              name,
                              style: TextStyle(
                                fontWeight: FontWeight.w600,
                                color: context.textColor,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                            subtitle: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                if (action.isNotEmpty)
                                  Text(
                                    action,
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      color: context.textSecondaryColor,
                                      fontSize: 13,
                                    ),
                                  ),
                                if (details != null &&
                                    details.isNotEmpty &&
                                    details != action)
                                  Text(
                                    details,
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      color: context.textSecondaryColor,
                                      fontSize: 12,
                                    ),
                                  ),
                                if (ts.isNotEmpty)
                                  Text(
                                    ts,
                                    style: TextStyle(
                                      color: context.textSecondaryColor
                                          .withValues(alpha: 0.85),
                                      fontSize: 11,
                                    ),
                                  ),
                              ],
                            ),
                          );
                        },
                      ),
                    ),
                  ],
                  const SizedBox(height: 24),
                ],
              ),
            ),
          );
        },
      ),
      bottomNavigationBar: AppBottomNavigationBar(
        currentIndex: AppBottomNavigationBar.adminTabNavIndex(
          chatbotEnabled: chatbot,
        ),
        chatbotEnabled: chatbot,
        onTap: (index) {
          Navigator.of(context).popUntil((route) {
            return route.isFirst || route.settings.name == AppRoutes.dashboard;
          });
        },
      ),
    );
  }

  Widget _buildSectionLabel(BuildContext context, String title) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8, top: 4),
      child: Text(
        title.toUpperCase(),
        style: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.6,
          color: context.textSecondaryColor,
        ),
      ),
    );
  }

  Widget _buildStatCard(
    String title,
    String value,
    IconData icon, {
    Color? accent,
  }) {
    final c = accent ?? Color(AppConstants.ifrcRed);
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(
          color: context.borderColor,
          width: 1,
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: c.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(
                icon,
                color: c,
                size: 24,
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      fontSize: 14,
                      color: context.textSecondaryColor,
                    ),
                    overflow: TextOverflow.ellipsis,
                    maxLines: 2,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    value,
                    style: TextStyle(
                      fontSize: 24,
                      fontWeight: FontWeight.bold,
                      color: context.textColor,
                    ),
                    overflow: TextOverflow.ellipsis,
                    maxLines: 1,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
