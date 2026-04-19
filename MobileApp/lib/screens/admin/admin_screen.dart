import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../models/shared/user.dart';
import '../../config/routes.dart';
import '../../utils/ios_constants.dart';
import '../../utils/ios_settings_style.dart';
import '../../utils/theme_extensions.dart';
import '../../utils/admin_screen_view_logging_mixin.dart';
import '../../widgets/admin_user_banner.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/ios_list_tile.dart';
import '../../widgets/ios_settings_scaffold.dart';
import '../../l10n/app_localizations.dart';
import 'login_logs_screen.dart';
import 'session_logs_screen.dart';

class AdminScreen extends StatefulWidget {
  final bool showBottomNav;

  const AdminScreen({
    super.key,
    this.showBottomNav = false,
  });

  @override
  State<AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends State<AdminScreen>
    with AdminScreenViewLoggingMixin {
  @override
  String get adminScreenViewRoutePath => AppRoutes.admin;

  bool _isAdmin(User? user) => user?.isAdmin ?? false;

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthProvider>(
      builder: (context, authProvider, child) {
        final user = authProvider.user;

        final localizations = AppLocalizations.of(context)!;

        if (user == null || !_isAdmin(user)) {
          if (IOSSettingsStyle.useIosSettingsChrome) {
            return IOSSettingsPageScaffold(
              title: localizations.adminPanel,
              children: [
                Padding(
                  padding: EdgeInsets.all(IOSSettingsStyle.pageHorizontalInset),
                  child: Center(
                    child: Text(
                      localizations.accessDenied,
                      textAlign: TextAlign.center,
                    ),
                  ),
                ),
              ],
            );
          }
          return Scaffold(
            appBar: AppAppBar(
              title: localizations.adminPanel,
            ),
            body: Center(
              child: Text(localizations.accessDenied),
            ),
          );
        }

        final hubChildren = _adminHubListChildren(
          context,
          user,
          localizations,
        );

        final bottomBar = widget.showBottomNav
            ? AppBottomNavigationBar(
                currentIndex: AppBottomNavigationBar.adminTabNavIndex(
                  chatbotEnabled: user.chatbotEnabled,
                ),
                chatbotEnabled: user.chatbotEnabled,
              )
            : null;

        if (IOSSettingsStyle.useIosSettingsChrome) {
          return IOSSettingsPageScaffold(
            title: localizations.adminPanel,
            bottomNavigationBar: bottomBar,
            children: hubChildren,
          );
        }

        final groupedBg = IOSSettingsStyle.groupedTableBackground(context);
        return Scaffold(
          appBar: AppAppBar(
            title: localizations.adminPanel,
          ),
          backgroundColor: groupedBg,
          body: ColoredBox(
            color: groupedBg,
            child: SingleChildScrollView(
              physics: IOSSettingsStyle.pageScrollPhysics(),
              padding: const EdgeInsets.only(bottom: IOSSpacing.lg),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: hubChildren,
              ),
            ),
          ),
          bottomNavigationBar: bottomBar,
        );
      },
    );
  }

  List<Widget> _adminHubListChildren(
    BuildContext context,
    User user,
    AppLocalizations localizations,
  ) {
    return [
      const SizedBox(height: IOSSpacing.md),
      Padding(
        padding: EdgeInsets.symmetric(
          horizontal: IOSSettingsStyle.pageHorizontalInset,
        ),
        child: AdminUserBanner(user: user),
      ),
      SizedBox(height: IOSSettingsStyle.sectionSpacing),
      _buildSectionCard(
        context: context,
        title: localizations.general,
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
      SizedBox(height: IOSSettingsStyle.sectionSpacing),
      _buildSectionCard(
        context: context,
        title: localizations.formDataManagement,
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
      SizedBox(height: IOSSettingsStyle.sectionSpacing),
      _buildSectionCard(
        context: context,
        title: localizations.frontendManagement,
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
      SizedBox(height: IOSSettingsStyle.sectionSpacing),
      _buildSectionCard(
        context: context,
        title: localizations.referenceData,
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
      SizedBox(height: IOSSettingsStyle.sectionSpacing),
      _buildSectionCard(
        context: context,
        title: localizations.analyticsMonitoring,
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
    ];
  }

  Widget _buildSectionCard({
    required BuildContext context,
    required String title,
    required List<Widget> children,
  }) {
    return IOSGroupedList(
      header: Text(
        title,
        style: IOSSettingsStyle.sectionHeaderStyle(context),
      ),
      margin: EdgeInsets.symmetric(
        horizontal: IOSSettingsStyle.pageHorizontalInset,
      ),
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
    return IOSListTile(
      leading: Container(
        padding: const EdgeInsets.all(IOSSpacing.sm + 2),
        decoration: BoxDecoration(
          color: iconColor.withValues(alpha: 0.12),
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
        style: IOSSettingsStyle.rowTitleStyle(context),
      ),
      trailing: IOSSettingsStyle.disclosureChevron(context),
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
