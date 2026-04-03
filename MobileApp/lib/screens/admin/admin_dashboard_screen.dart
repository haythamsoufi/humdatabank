import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../../providers/admin/admin_dashboard_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../utils/ios_constants.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/loading_indicator.dart';
import '../../widgets/error_state.dart';
import '../../l10n/app_localizations.dart';

// Typed models for type safety
class _MetricData {
  final String title;
  final int value;
  final IconData icon;
  final Color color;
  final String? route;

  const _MetricData({
    required this.title,
    required this.value,
    required this.icon,
    required this.color,
    this.route,
  });
}

class _ActionData {
  final IconData icon;
  final String label;
  final Color color;
  final String route;

  const _ActionData({
    required this.icon,
    required this.label,
    required this.color,
    required this.route,
  });
}

// Constants
class _DashboardConstants {
  static const double metricCardHeight = 110.0;
  static const double actionCardHeight = 110.0;
  static const double metricCardMinWidth = 120.0;
  static const double metricCardMaxWidth = 140.0;
  static const double actionCardMinWidth = 90.0;
  static const double actionCardMaxWidth = 100.0;
  static const double cardSpacing = 12.0;
  static const double cardBorderRadius = 12.0;
  static const double iconContainerBorderRadius = 8.0;
  static const double overviewCardBorderRadius = 14.0;
}

class AdminDashboardScreen extends StatefulWidget {
  final bool showBottomNav;

  const AdminDashboardScreen({super.key, this.showBottomNav = false});

  @override
  State<AdminDashboardScreen> createState() => _AdminDashboardScreenState();
}

class _AdminDashboardScreenState extends State<AdminDashboardScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _animationController;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    );
    _fadeAnimation = CurvedAnimation(
      parent: _animationController,
      curve: IOSCurves.easeOut,
    );
    _animationController.forward();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadDashboard();
    });
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  void _loadDashboard() {
    Provider.of<AdminDashboardProvider>(context, listen: false)
        .loadDashboardStats();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthProvider>(
      builder: (context, authProvider, child) {
        final user = authProvider.user;
        final isAdmin = user != null &&
            (user.role == 'admin' || user.role == 'system_manager');

        final localizations = AppLocalizations.of(context)!;

        if (!isAdmin) {
          return Scaffold(
            appBar: AppAppBar(
              title: localizations.adminDashboard,
            ),
            backgroundColor: IOSColors.getGroupedBackground(context),
            body: Center(
              child: Padding(
                    padding: EdgeInsets.symmetric(horizontal: IOSSpacing.xxl),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      Icons.lock_outline_rounded,
                      size: 64,
                      color: Theme.of(context)
                          .colorScheme
                          .onSurface
                          .withOpacity(0.3),
                    ),
                    const SizedBox(height: IOSSpacing.lg),
                    Text(
                      localizations.accessDenied,
                      style: IOSTextStyle.title2(context),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            ),
          );
        }

        final theme = Theme.of(context);
        return Scaffold(
          backgroundColor: IOSColors.getGroupedBackground(context),
          appBar: AppAppBar(
            title: localizations.adminDashboard,
          ),
          body: Container(
            color: IOSColors.getGroupedBackground(context),
            child: RefreshIndicator(
              onRefresh: () async {
                HapticFeedback.lightImpact();
                if (_animationController.isAnimating) {
                  _animationController.stop();
                }
                _animationController.reset();
                _loadDashboard();
                _animationController.forward();
              },
              color: IOSColors.getSystemBlue(context),
              strokeWidth: 2.5,
              displacement: 40,
              backgroundColor: theme.scaffoldBackgroundColor,
              child: Consumer<AdminDashboardProvider>(
                builder: (context, provider, child) {
                  if (provider.isLoading && provider.stats == null) {
                    return AppLoadingIndicator(
                      message: localizations.loadingDashboard,
                      color: Color(AppConstants.ifrcRed),
                    );
                  }

                  if (provider.error != null && provider.stats == null) {
                    return AppErrorState(
                      message: provider.error,
                      onRetry: () {
                        _loadDashboard();
                      },
                      retryLabel: localizations.retry,
                    );
                  }

                  if (provider.stats == null) {
                    return Center(
                      child: Text(
                        localizations.noDataAvailable,
                        style: IOSTextStyle.body(context).copyWith(
                          color: Theme.of(context)
                              .colorScheme
                              .onSurface
                              .withOpacity(0.6),
                        ),
                      ),
                    );
                  }

                  final content = SingleChildScrollView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: EdgeInsets.only(bottom: IOSSpacing.xxl),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        SizedBox(height: IOSSpacing.sm),
                        // Key Metrics - Horizontal Scroll
                        _buildKeyMetrics(provider),

                        SizedBox(height: IOSSpacing.xl),

                        // Quick Actions - Horizontal Scroll
                        _buildQuickActions(provider),

                        SizedBox(height: IOSSpacing.xl),

                        // Overview Section (combines attention + activity)
                        _buildOverviewSection(provider),
                      ],
                    ),
                  );

                  return FadeTransition(
                    opacity: _fadeAnimation,
                    child: content,
                  );
                },
              ),
            ),
          ),
          bottomNavigationBar: widget.showBottomNav
              ? AppBottomNavigationBar(
                  currentIndex: 2,
                  onTap: (index) {
                    Navigator.of(context).popUntil((route) {
                      return route.isFirst ||
                          route.settings.name == AppRoutes.dashboard;
                    });
                  },
                )
              : null,
        );
      },
    );
  }

  // Simplified key metrics - horizontal scroll
  Widget _buildKeyMetrics(AdminDashboardProvider provider) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    final metrics = [
      _MetricData(
        title: localizations.totalUsers,
        value: provider.userCount,
        icon: Icons.people_rounded,
        color: IOSColors.getSystemBlue(context),
      ),
      _MetricData(
        title: localizations.assignments,
        value: provider.assignmentCount,
        icon: Icons.assignment_rounded,
        color: IOSColors.systemGreen,
        route: AppRoutes.assignments,
      ),
      _MetricData(
        title: localizations.templates,
        value: provider.templateCount,
        icon: Icons.description_rounded,
        color: IOSColors.systemOrange,
        route: AppRoutes.templates,
      ),
      _MetricData(
        title: localizations.todaysLogins,
        value: provider.todayLogins,
        icon: Icons.login_rounded,
        color: IOSColors.systemGreen,
      ),
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: EdgeInsets.symmetric(horizontal: IOSSpacing.lg),
          child: Text(
            localizations.keyMetrics.toUpperCase(),
            style: IOSTextStyle.footnote(context).copyWith(
              fontWeight: FontWeight.w600,
              letterSpacing: 0.5,
            ),
          ),
        ),
        SizedBox(height: IOSSpacing.md - 4),
        SizedBox(
          height: _DashboardConstants.metricCardHeight,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding: EdgeInsets.symmetric(horizontal: IOSSpacing.lg),
            itemCount: metrics.length,
            separatorBuilder: (_, __) => const SizedBox(
              width: _DashboardConstants.cardSpacing,
            ),
            itemBuilder: (context, index) {
              final metric = metrics[index];
              return _buildMetricCard(
                title: metric.title,
                value: metric.value.toString(),
                icon: metric.icon,
                color: metric.color,
                semanticLabel: '${metric.title}: ${metric.value}',
                onTap: metric.route != null
                    ? () {
                        HapticFeedback.lightImpact();
                        Navigator.of(context).pushNamed(metric.route!);
                      }
                    : null,
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildMetricCard({
    required String title,
    required String value,
    required IconData icon,
    required Color color,
    String? semanticLabel,
    VoidCallback? onTap,
  }) {
    final theme = Theme.of(context);
    return Semantics(
      label: semanticLabel ?? '$title: $value',
      button: onTap != null,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(_DashboardConstants.cardBorderRadius),
          child: Container(
            constraints: const BoxConstraints(
              minWidth: _DashboardConstants.metricCardMinWidth,
              maxWidth: _DashboardConstants.metricCardMaxWidth,
            ),
            padding: EdgeInsets.all(IOSSpacing.sm + 6),
            decoration: BoxDecoration(
              color: theme.cardTheme.color ?? theme.colorScheme.surface,
              borderRadius: BorderRadius.circular(_DashboardConstants.cardBorderRadius),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon, color: color, size: 22),
                SizedBox(height: IOSSpacing.sm),
                FittedBox(
                  fit: BoxFit.scaleDown,
                  alignment: Alignment.centerLeft,
                  child: Text(
                    value,
                    style: IOSTextStyle.title1(context).copyWith(
                      color: theme.colorScheme.onSurface,
                      height: 1.0,
                    ),
                  ),
                ),
                SizedBox(height: IOSSpacing.xs),
                Flexible(
                  child: Text(
                    title,
                    style: IOSTextStyle.footnote(context).copyWith(
                      fontWeight: FontWeight.w500,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  // Simplified quick actions - horizontal scroll
  Widget _buildQuickActions(AdminDashboardProvider provider) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    final actions = [
      _ActionData(
        icon: Icons.add_circle_rounded,
        label: localizations.newAssignment,
        color: IOSColors.systemGreen,
        route: AppRoutes.assignments,
      ),
      _ActionData(
        icon: Icons.description_rounded,
        label: localizations.newTemplate,
        color: IOSColors.systemOrange,
        route: AppRoutes.templates,
      ),
      _ActionData(
        icon: Icons.storage_rounded,
        label: localizations.indicators,
        color: IOSColors.systemOrange,
        route: AppRoutes.indicatorBankAdmin,
      ),
      _ActionData(
        icon: Icons.folder_open_rounded,
        label: localizations.resources,
        color: IOSColors.getSystemBlue(context),
        route: AppRoutes.resourcesManagement,
      ),
      _ActionData(
        icon: Icons.settings_rounded,
        label: localizations.settings,
        color: theme.colorScheme.onSurface.withOpacity(0.6),
        route: AppRoutes.settings,
      ),
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: EdgeInsets.symmetric(horizontal: IOSSpacing.lg),
          child: Text(
            localizations.quickActions.toUpperCase(),
            style: IOSTextStyle.footnote(context).copyWith(
              fontWeight: FontWeight.w600,
              letterSpacing: 0.5,
            ),
          ),
        ),
        SizedBox(height: IOSSpacing.md - 4),
        SizedBox(
          height: _DashboardConstants.actionCardHeight,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding: EdgeInsets.symmetric(horizontal: IOSSpacing.lg),
            itemCount: actions.length,
            separatorBuilder: (_, __) => const SizedBox(
              width: _DashboardConstants.cardSpacing,
            ),
            itemBuilder: (context, index) {
              final action = actions[index];
              return _buildActionCard(
                icon: action.icon,
                label: action.label,
                color: action.color,
                onTap: () {
                  HapticFeedback.lightImpact();
                  Navigator.of(context).pushNamed(action.route);
                },
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildActionCard({
    required IconData icon,
    required String label,
    required Color color,
    required VoidCallback onTap,
  }) {
    final theme = Theme.of(context);
    return Semantics(
      label: label,
      button: true,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(_DashboardConstants.cardBorderRadius),
          child: Container(
            constraints: const BoxConstraints(
              minWidth: _DashboardConstants.actionCardMinWidth,
              maxWidth: _DashboardConstants.actionCardMaxWidth,
            ),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
            decoration: BoxDecoration(
              color: theme.cardTheme.color ?? theme.colorScheme.surface,
              borderRadius: BorderRadius.circular(_DashboardConstants.cardBorderRadius),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: color.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(
                      _DashboardConstants.iconContainerBorderRadius,
                    ),
                  ),
                  child: Icon(icon, color: color, size: 20),
                ),
                SizedBox(height: IOSSpacing.sm),
                Flexible(
                  child: Text(
                    label,
                    style: IOSTextStyle.footnote(context).copyWith(
                      fontWeight: FontWeight.w500,
                    ),
                    textAlign: TextAlign.center,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  // Combined overview section
  Widget _buildOverviewSection(AdminDashboardProvider provider) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    final hasAttentionItems = provider.pendingSubmissions > 0 ||
        provider.overdueAssignments > 0 ||
        provider.securityAlerts > 0;

    return Container(
      margin: EdgeInsets.symmetric(horizontal: IOSSpacing.lg),
      decoration: BoxDecoration(
        color: theme.cardTheme.color ?? theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(
          _DashboardConstants.overviewCardBorderRadius,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(
              IOSSpacing.lg,
              IOSSpacing.lg,
              IOSSpacing.lg,
              IOSSpacing.md,
            ),
            child: Text(
              localizations.overview.toUpperCase(),
              style: IOSTextStyle.footnote(context).copyWith(
                fontWeight: FontWeight.w600,
                letterSpacing: 0.5,
              ),
            ),
          ),

          // Attention Items (only show if there are items)
          if (hasAttentionItems) ...[
            _buildOverviewItem(
              icon: Icons.warning_rounded,
              title: localizations.itemsRequiringAttention,
              items: [
                if (provider.pendingSubmissions > 0)
                  _buildOverviewSubItem(
                    icon: Icons.access_time_rounded,
                    title: localizations.pendingSubmissions,
                    count: provider.pendingSubmissions,
                    color: IOSColors.systemOrange,
                  ),
                if (provider.overdueAssignments > 0)
                  _buildOverviewSubItem(
                    icon: Icons.calendar_today_rounded,
                    title: localizations.overdueAssignments,
                    count: provider.overdueAssignments,
                    color: IOSColors.systemRed,
                  ),
                if (provider.securityAlerts > 0)
                  _buildOverviewSubItem(
                    icon: Icons.security_rounded,
                    title: localizations.securityAlerts,
                    count: provider.securityAlerts,
                    color: IOSColors.systemRed,
                  ),
              ],
            ),
            if (provider.recentLogins > 0 ||
                provider.recentActivities > 0 ||
                provider.activeSessions > 0)
              Divider(
                height: 1,
                thickness: 0.5,
                indent: IOSSpacing.lg,
                endIndent: IOSSpacing.lg,
                color: theme.dividerColor.withOpacity(0.5),
              ),
          ],

          // Activity Items
          if (provider.recentLogins > 0 ||
              provider.recentActivities > 0 ||
              provider.activeSessions > 0)
            _buildOverviewItem(
              icon: Icons.timeline_rounded,
              title: localizations.recentActivity7Days,
              items: [
                if (provider.recentLogins > 0)
                  _buildOverviewSubItem(
                    icon: Icons.login_rounded,
                    title: localizations.successfulLogins,
                    count: provider.recentLogins,
                    color: IOSColors.systemGreen,
                  ),
                if (provider.recentActivities > 0)
                  _buildOverviewSubItem(
                    icon: Icons.touch_app_rounded,
                    title: localizations.userActivities,
                    count: provider.recentActivities,
                    color: IOSColors.getSystemBlue(context),
                  ),
                if (provider.activeSessions > 0)
                  _buildOverviewSubItem(
                    icon: Icons.people_rounded,
                    title: localizations.activeSessions,
                    count: provider.activeSessions,
                    color: IOSColors.getSystemBlue(context),
                  ),
              ],
            ),

          // Empty state
          if (!hasAttentionItems &&
              provider.recentLogins == 0 &&
              provider.recentActivities == 0 &&
              provider.activeSessions == 0)
            Padding(
              padding: EdgeInsets.all(IOSSpacing.xxl),
              child: Center(
                child: Column(
                  children: [
                    Icon(
                      Icons.check_circle_outline_rounded,
                      size: 48,
                      color: theme.colorScheme.onSurface.withOpacity(0.3),
                    ),
                    SizedBox(height: IOSSpacing.md - 4),
                    Text(
                      localizations.allCaughtUp,
                      style: IOSTextStyle.subheadline(context).copyWith(
                        color: theme.colorScheme.onSurface.withOpacity(0.6),
                      ),
                    ),
                  ],
                ),
              ),
            ),

          SizedBox(height: IOSSpacing.lg),
        ],
      ),
    );
  }

  Widget _buildOverviewItem({
    required IconData icon,
    required String title,
    required List<Widget> items,
  }) {
    if (items.isEmpty) return const SizedBox.shrink();

    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: IOSSpacing.lg,
        vertical: 12,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                icon,
                size: 18,
                color: Theme.of(context).colorScheme.onSurface.withOpacity(0.6),
              ),
              const SizedBox(width: 8),
              Flexible(
                child: Text(
                  title,
                  style: IOSTextStyle.subheadline(context).copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          SizedBox(height: IOSSpacing.md - 4),
          ...items,
        ],
      ),
    );
  }

  Widget _buildOverviewSubItem({
    required IconData icon,
    required String title,
    required int count,
    required Color color,
  }) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(6),
                  decoration: BoxDecoration(
                    color: color.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Icon(icon, color: color, size: 16),
                ),
                const SizedBox(width: 10),
                Flexible(
                  child: Text(
                    title,
                    style: IOSTextStyle.footnote(context).copyWith(
                      fontWeight: FontWeight.w400,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: color.withOpacity(0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              count.toString(),
              style: IOSTextStyle.caption1(context).copyWith(
                fontWeight: FontWeight.w600,
                color: color,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
