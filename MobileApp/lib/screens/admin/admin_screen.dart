import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;
import 'package:provider/provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../models/shared/user.dart';
import '../../config/routes.dart';
import '../../utils/ios_constants.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/admin_user_banner.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/ios_list_tile.dart';
import '../../l10n/app_localizations.dart';
import 'login_logs_screen.dart';
import 'session_logs_screen.dart';

class AdminScreen extends StatelessWidget {
  final bool showBottomNav;

  const AdminScreen({
    super.key,
    this.showBottomNav = false,
  });

  bool _isAdmin(User? user) => user?.isAdmin ?? false;

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthProvider>(
      builder: (context, authProvider, child) {
        final user = authProvider.user;

        final localizations = AppLocalizations.of(context)!;

        // Only show admin screen for admins
        if (!_isAdmin(user)) {
          return Scaffold(
            appBar: AppAppBar(
              title: localizations.adminPanel,
            ),
            body: Center(
              child: Text(localizations.accessDenied),
            ),
          );
        }

        final theme = Theme.of(context);
        return Scaffold(
          appBar: AppAppBar(
            title: localizations.adminPanel,
          ),
          backgroundColor: theme.scaffoldBackgroundColor,
          body: ColoredBox(
            color: IOSColors.getGroupedBackground(context),
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(
                horizontal: IOSSpacing.md,
                vertical: IOSSpacing.md,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  AdminUserBanner(user: user),

                  const SizedBox(height: IOSSpacing.lg),
                  // General Section
                  _buildSectionCard(
                    context: context,
                    title: localizations.general,
                    icon: Icons.dashboard_rounded,
                    color: context.adminHubBlue,
                    children: [
                      _buildMenuItem(
                        context: context,
                        icon: Icons.space_dashboard_rounded,
                        title: localizations.adminDashboard,
                        route: AppRoutes.adminDashboard,
                        iconColor: context.adminHubBlue,
                      ),
                      _buildMenuItem(
                        context: context,
                        icon: Icons.people_rounded,
                        title: localizations.manageUsers,
                        route: AppRoutes.users,
                        iconColor: context.adminHubBlue,
                      ),
                      _buildMenuItem(
                        context: context,
                        icon: Icons.how_to_reg_rounded,
                        title: localizations.accessRequestsTitle,
                        route: AppRoutes.accessRequests,
                        iconColor: context.adminHubBlue,
                      ),
                      _buildMenuItem(
                        context: context,
                        icon: Icons.description_rounded,
                        title: localizations.documentManagement,
                        route: AppRoutes.documentManagement,
                        iconColor: context.adminHubBlue,
                      ),
                      _buildMenuItem(
                        context: context,
                        icon: Icons.translate_rounded,
                        title: localizations.translationManagement,
                        route: AppRoutes.translationManagement,
                        iconColor: context.adminHubBlue,
                      ),
                    ],
                  ),

                  const SizedBox(height: IOSSpacing.md),

                  // Form & Data Management Section
                  _buildSectionCard(
                    context: context,
                    title: localizations.formDataManagement,
                    icon: Icons.article_rounded,
                    color: context.adminHubPurple,
                    children: [
                      _buildMenuItem(
                        context: context,
                        icon: Icons.article_rounded,
                        title: localizations.manageTemplates,
                        route: AppRoutes.templates,
                        iconColor: context.adminHubPurple,
                      ),
                      _buildMenuItem(
                        context: context,
                        icon: Icons.assignment_rounded,
                        title: localizations.manageAssignments,
                        route: AppRoutes.assignments,
                        iconColor: context.adminHubPurple,
                      ),
                    ],
                  ),

                  const SizedBox(height: IOSSpacing.md),

                  // Website Management Section
                  _buildSectionCard(
                    context: context,
                    title: localizations.frontendManagement,
                    icon: Icons.folder_open_rounded,
                    color: context.adminHubAmber,
                    children: [
                      _buildMenuItem(
                        context: context,
                        icon: Icons.folder_open_rounded,
                        title: localizations.manageResources,
                        route: AppRoutes.resourcesManagement,
                        iconColor: context.adminHubAmber,
                      ),
                    ],
                  ),

                  const SizedBox(height: IOSSpacing.md),

                  // Reference Data Section
                  _buildSectionCard(
                    context: context,
                    title: localizations.referenceData,
                    icon: Icons.account_tree_rounded,
                    color: context.adminHubRed,
                    children: [
                      _buildMenuItem(
                        context: context,
                        icon: Icons.account_tree_rounded,
                        title: localizations.organizationalStructure,
                        route: AppRoutes.organizationalStructure,
                        iconColor: context.adminHubRed,
                      ),
                      _buildMenuItem(
                        context: context,
                        icon: Icons.storage_rounded,
                        title: localizations.indicatorBank,
                        route: AppRoutes.indicatorBankAdmin,
                        iconColor: context.adminHubRed,
                      ),
                    ],
                  ),

                  const SizedBox(height: IOSSpacing.md),

                  // Analytics & Monitoring Section
                  _buildSectionCard(
                    context: context,
                    title: localizations.analyticsMonitoring,
                    icon: Icons.bar_chart_rounded,
                    color: context.adminHubCyan,
                    children: [
                      _buildMenuItem(
                        context: context,
                        icon: Icons.bar_chart_rounded,
                        title: localizations.userAnalytics,
                        route: AppRoutes.userAnalytics,
                        iconColor: context.adminHubCyan,
                      ),
                      _buildMenuItem(
                        context: context,
                        icon: Icons.history_rounded,
                        title: localizations.auditTrail,
                        route: AppRoutes.auditTrail,
                        iconColor: context.adminHubCyan,
                      ),
                      _buildMenuItem(
                        context: context,
                        icon: Icons.key_rounded,
                        title: localizations.loginLogsTitle,
                        iconColor: context.adminHubCyan,
                        onNavigate: () {
                          Navigator.of(context).push(
                            MaterialPageRoute<void>(
                              settings: const RouteSettings(name: AppRoutes.loginLogs),
                              builder: (context) => const LoginLogsScreen(),
                            ),
                          );
                        },
                      ),
                      _buildMenuItem(
                        context: context,
                        icon: Icons.manage_history_rounded,
                        title: localizations.sessionLogsTitle,
                        iconColor: context.adminHubCyan,
                        onNavigate: () {
                          Navigator.of(context).push(
                            MaterialPageRoute<void>(
                              settings: const RouteSettings(name: AppRoutes.sessionLogs),
                              builder: (context) => const SessionLogsScreen(),
                            ),
                          );
                        },
                      ),
                    ],
                  ),

                  const SizedBox(height: IOSSpacing.xl),
                ],
              ),
            ),
          ),
          bottomNavigationBar: showBottomNav
              ? AppBottomNavigationBar(
                  currentIndex: AppBottomNavigationBar.adminTabNavIndex(
                    chatbotEnabled: user?.chatbotEnabled ?? false,
                  ),
                  chatbotEnabled: user?.chatbotEnabled ?? false,
                  // onTap is optional - if not provided, uses NavigationHelper.navigateToMainTab by default
                )
              : null,
        );
      },
    );
  }

  Widget _buildSectionCard({
    required BuildContext context,
    required String title,
    required IconData icon,
    required Color color,
    required List<Widget> children,
  }) {
    final theme = Theme.of(context);
    return IOSGroupedList(
      header: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(IOSSpacing.sm),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(
              icon,
              color: color,
              size: 16,
            ),
          ),
          const SizedBox(width: IOSSpacing.sm),
          Text(
            title,
            style: IOSTextStyle.footnote(context).copyWith(
              fontWeight: FontWeight.w600,
              color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
            ),
          ),
        ],
      ),
      margin: EdgeInsets.zero,
      children: children,
    );
  }

  Widget _buildMenuItem({
    required BuildContext context,
    required IconData icon,
    required String title,
    String? route,
    String? webviewRoute,
    VoidCallback? onNavigate,
    required Color iconColor,
  }) {
    final theme = Theme.of(context);
    return IOSListTile(
      leading: Container(
        padding: const EdgeInsets.all(IOSSpacing.sm + 2),
        decoration: BoxDecoration(
          color: iconColor.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Icon(
          icon,
          color: iconColor,
          size: 18,
        ),
      ),
      title: Text(
        title,
        style: IOSTextStyle.callout(context).copyWith(
          fontWeight: FontWeight.w500,
          letterSpacing: -0.2,
        ),
      ),
      trailing: Icon(
        cupertino.CupertinoIcons.chevron_right,
        color: theme.colorScheme.onSurface.withValues(alpha: 0.3),
        size: 13,
      ),
      onTap: () {
        if (onNavigate != null) {
          onNavigate();
          return;
        }
        if (route != null) {
          Navigator.of(context).pushNamed(route);
        } else if (webviewRoute != null) {
          Navigator.of(context).pushNamed(
            AppRoutes.webview,
            arguments: webviewRoute,
          );
        }
      },
    );
  }
}
