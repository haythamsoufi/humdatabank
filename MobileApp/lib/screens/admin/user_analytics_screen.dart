import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/admin/user_analytics_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../widgets/admin_filter_panel.dart';
import '../../widgets/admin_filters_bottom_sheet.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../l10n/app_localizations.dart';

class UserAnalyticsScreen extends StatefulWidget {
  const UserAnalyticsScreen({super.key});

  @override
  State<UserAnalyticsScreen> createState() => _UserAnalyticsScreenState();
}

class _UserAnalyticsScreenState extends State<UserAnalyticsScreen> {
  String _selectedTimeRange = '7d';
  String? _selectedMetricFilter;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _applyFilters();
    });
  }

  void _applyFilters() {
    final provider = Provider.of<UserAnalyticsProvider>(context, listen: false);
    provider.loadAnalytics(
      timeRange: _selectedTimeRange,
      metricFilter: _selectedMetricFilter,
    );
  }

  void _clearFilters() {
    setState(() {
      _selectedTimeRange = '7d';
      _selectedMetricFilter = null;
    });
    Provider.of<UserAnalyticsProvider>(context, listen: false)
        .loadAnalytics(timeRange: '7d');
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
              DropdownButtonFormField<String>(
                initialValue: _selectedTimeRange,
                decoration: InputDecoration(
                  labelText: loc.timeRange,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8),
                  ),
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 12,
                  ),
                  isDense: true,
                ),
                items: [
                  DropdownMenuItem<String>(
                    value: '7d',
                    child: Text(
                      loc.last7Days,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  DropdownMenuItem<String>(
                    value: '30d',
                    child: Text(
                      loc.last30Days,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  DropdownMenuItem<String>(
                    value: '90d',
                    child: Text(
                      loc.last90Days,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  DropdownMenuItem<String>(
                    value: '1y',
                    child: Text(
                      loc.lastYear,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  DropdownMenuItem<String>(
                    value: 'all',
                    child: Text(
                      loc.allTime,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
                onChanged: (value) {
                  if (value != null) {
                    setState(() => _selectedTimeRange = value);
                    setModalState(() {});
                  }
                },
              ),
              AdminFilterPanel.fieldGap,
              DropdownButtonFormField<String?>(
                initialValue: _selectedMetricFilter,
                decoration: InputDecoration(
                  labelText: loc.metric,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8),
                  ),
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 12,
                  ),
                  isDense: true,
                ),
                items: [
                  DropdownMenuItem<String?>(
                    value: null,
                    child: Text(
                      loc.allMetrics,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'active_users',
                    child: Text(
                      loc.activeUsers,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'logins',
                    child: Text(
                      loc.logins,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'submissions',
                    child: Text(
                      loc.metricSubmissions,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'page_views',
                    child: Text(
                      loc.pageViews,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
                onChanged: (value) {
                  setState(() => _selectedMetricFilter = value);
                  setModalState(() {});
                },
              ),
            ],
          ),
        );
      },
    );
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
        actions: [
          IconButton(
            icon: const Icon(Icons.tune),
            tooltip: localizations.adminFilters,
            onPressed: _openFiltersBottomSheet,
          ),
        ],
      ),
      body: Consumer<UserAnalyticsProvider>(
        builder: (context, provider, child) {
          if (provider.isLoading && provider.analyticsData == null) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(
                      Color(AppConstants.ifrcRed),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    AppLocalizations.of(context)!.loadingAnalytics,
                    style: TextStyle(
                      color: context.textSecondaryColor,
                      fontSize: 14,
                    ),
                  ),
                ],
              ),
            );
          }

          if (provider.error != null &&
              provider.analyticsData == null) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      Icons.error_outline,
                      size: 48,
                      color: Theme.of(context).colorScheme.error,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      provider.error!,
                      style: TextStyle(
                        color: context.textSecondaryColor,
                        fontSize: 14,
                      ),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 24),
                    OutlinedButton.icon(
                      onPressed: () {
                        provider.clearError();
                        _applyFilters();
                      },
                      icon: const Icon(Icons.refresh, size: 18),
                      label: Text(AppLocalizations.of(context)!.retry),
                      style: OutlinedButton.styleFrom(
                        foregroundColor:
                            Color(AppConstants.ifrcRed),
                        side: BorderSide(
                          color: Color(AppConstants.ifrcRed),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
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
                    AppLocalizations.of(context)!.noDataAvailable,
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

          return RefreshIndicator(
            onRefresh: () async => _applyFilters(),
            color: Color(AppConstants.ifrcRed),
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (data['total_users'] != null)
                    _buildStatCard(
                      localizations.totalUsers,
                      data['total_users'].toString(),
                      Icons.people,
                    ),
                  if (data['active_users'] != null)
                    _buildStatCard(
                      localizations.activeUsers,
                      data['active_users'].toString(),
                      Icons.person,
                    ),
                  if (data['recent_logins'] != null)
                    _buildStatCard(
                      localizations.logins,
                      data['recent_logins'].toString(),
                      Icons.login,
                    ),
                  if (data['total_submissions'] != null)
                    _buildStatCard(
                      localizations.metricSubmissions,
                      data['total_submissions'].toString(),
                      Icons.assignment,
                    ),
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

  Widget _buildStatCard(String title, String value, IconData icon) {
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
                color: Color(AppConstants.ifrcRed).withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(
                icon,
                color: Color(AppConstants.ifrcRed),
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
