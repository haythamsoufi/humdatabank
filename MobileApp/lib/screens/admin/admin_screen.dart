import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;
import 'package:provider/provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../models/shared/user.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../utils/ios_constants.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/ios_card.dart';
import '../../widgets/ios_button.dart';
import '../../widgets/ios_list_tile.dart';
import '../../l10n/app_localizations.dart';

class AdminScreen extends StatelessWidget {
  final bool showBottomNav;

  const AdminScreen({
    super.key,
    this.showBottomNav = false,
  });

  bool _isAdmin(User? user) {
    if (user == null) return false;
    return user.role == 'admin' || user.role == 'system_manager';
  }

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
          body: Container(
            color: IOSColors.getGroupedBackground(context),
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(
                horizontal: IOSSpacing.md,
                vertical: IOSSpacing.md,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // User Banner
                  _buildUserBanner(context, user),

                  SizedBox(height: IOSSpacing.lg),
                  // General Section
                  _buildSectionCard(
                    context: context,
                    title: localizations.general,
                    icon: Icons.dashboard_rounded,
                    color: const Color(0xFF3B82F6),
                    children: [
                      _buildMenuItem(
                        context: context,
                        icon: Icons.description_rounded,
                        title: localizations.documentManagement,
                        route: AppRoutes.documentManagement,
                        iconColor: const Color(0xFF3B82F6),
                      ),
                      _buildMenuItem(
                        context: context,
                        icon: Icons.translate_rounded,
                        title: localizations.translationManagement,
                        route: AppRoutes.translationManagement,
                        iconColor: const Color(0xFF3B82F6),
                      ),
                    ],
                  ),

                  SizedBox(height: IOSSpacing.md),

                  // Form & Data Management Section
                  _buildSectionCard(
                    context: context,
                    title: localizations.formDataManagement,
                    icon: Icons.article_rounded,
                    color: const Color(0xFF8B5CF6),
                    children: [
                      _buildMenuItem(
                        context: context,
                        icon: Icons.article_rounded,
                        title: localizations.manageTemplates,
                        route: AppRoutes.templates,
                        iconColor: const Color(0xFF8B5CF6),
                      ),
                      _buildMenuItem(
                        context: context,
                        icon: Icons.assignment_rounded,
                        title: localizations.manageAssignments,
                        route: AppRoutes.assignments,
                        iconColor: const Color(0xFF8B5CF6),
                      ),
                    ],
                  ),

                  SizedBox(height: IOSSpacing.md),

                  // Website Management Section
                  _buildSectionCard(
                    context: context,
                    title: localizations.frontendManagement,
                    icon: Icons.folder_open_rounded,
                    color: const Color(0xFFF59E0B),
                    children: [
                      _buildMenuItem(
                        context: context,
                        icon: Icons.folder_open_rounded,
                        title: localizations.manageResources,
                        route: AppRoutes.resourcesManagement,
                        iconColor: const Color(0xFFF59E0B),
                      ),
                    ],
                  ),

                  SizedBox(height: IOSSpacing.md),

                  // Reference Data Section
                  _buildSectionCard(
                    context: context,
                    title: localizations.referenceData,
                    icon: Icons.account_tree_rounded,
                    color: const Color(0xFFEF4444),
                    children: [
                      _buildMenuItem(
                        context: context,
                        icon: Icons.account_tree_rounded,
                        title: localizations.organizationalStructure,
                        route: AppRoutes.organizationalStructure,
                        iconColor: const Color(0xFFEF4444),
                      ),
                      _buildMenuItem(
                        context: context,
                        icon: Icons.storage_rounded,
                        title: localizations.indicatorBank,
                        route: AppRoutes.indicatorBankAdmin,
                        iconColor: const Color(0xFFEF4444),
                      ),
                    ],
                  ),

                  SizedBox(height: IOSSpacing.md),

                  // Analytics & Monitoring Section
                  _buildSectionCard(
                    context: context,
                    title: localizations.analyticsMonitoring,
                    icon: Icons.bar_chart_rounded,
                    color: const Color(0xFF06B6D4),
                    children: [
                      _buildMenuItem(
                        context: context,
                        icon: Icons.bar_chart_rounded,
                        title: localizations.userAnalytics,
                        route: AppRoutes.userAnalytics,
                        iconColor: const Color(0xFF06B6D4),
                      ),
                      _buildMenuItem(
                        context: context,
                        icon: Icons.history_rounded,
                        title: localizations.auditTrail,
                        route: AppRoutes.auditTrail,
                        iconColor: const Color(0xFF06B6D4),
                      ),
                    ],
                  ),

                  SizedBox(height: IOSSpacing.xl),
                ],
              ),
            ),
          ),
          bottomNavigationBar: showBottomNav
              ? AppBottomNavigationBar(
                  currentIndex:
                      -1, // -1 means no tab is active (Admin screen is on top)
                  // onTap is optional - if not provided, uses NavigationHelper.navigateToMainTab by default
                )
              : null,
        );
      },
    );
  }

  Widget _buildUserBanner(BuildContext context, User? user) {
    final localizations = AppLocalizations.of(context)!;
    final displayName = user?.displayName ?? '';
    final email = user?.email ?? '';
    final title = user?.title;
    final role = user?.role ?? '';

    // Parse profile color with error handling
    Color profileColor = const Color(0xFF011E41); // Default IFRC Navy
    if (user?.profileColor != null && user!.profileColor!.isNotEmpty) {
      try {
        final cleanColor = user.profileColor!.replaceFirst('#', '0xFF');
        profileColor = Color(int.parse(cleanColor));
      } catch (e) {
        // If parsing fails, use default color
        profileColor = const Color(0xFF011E41);
      }
    }

    // Create gradient colors from profile color
    final primaryColor = profileColor;
    final secondaryColor = profileColor.withOpacity(0.7);
    final accentColor = profileColor.withOpacity(0.3);

    // Get initial for avatar
    final initial = displayName.isNotEmpty
        ? displayName.substring(0, 1).toUpperCase()
        : email.isNotEmpty
            ? email.substring(0, 1).toUpperCase()
            : 'U';

    // Get role display name
    String getRoleDisplayName(String role) {
      switch (role.toLowerCase()) {
        case 'admin':
          return localizations.adminRole;
        case 'system_manager':
          return localizations.systemManagerRole;
        case 'focal_point':
          return localizations.focalPointRole;
        case 'viewer':
          return localizations.viewerRole;
        default:
          return role
              .split('_')
              .map((word) =>
                  word.isEmpty ? '' : word[0].toUpperCase() + word.substring(1))
              .join(' ');
      }
    }

    return Container(
      margin: EdgeInsets.only(bottom: IOSSpacing.sm),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            primaryColor,
            secondaryColor,
            accentColor,
          ],
        ),
        boxShadow: [
          BoxShadow(
            color: primaryColor.withOpacity(0.4),
            blurRadius: 20,
            spreadRadius: 2,
            offset: const Offset(0, 8),
          ),
          BoxShadow(
            color: Theme.of(context).brightness == Brightness.dark
                ? Colors.black.withOpacity(0.4)
                : Colors.black.withOpacity(0.1),
            blurRadius: 10,
            spreadRadius: 0,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () {
            Navigator.of(context).pushNamed(AppRoutes.settings);
          },
          splashColor: Colors.white.withOpacity(0.2),
          highlightColor: Colors.white.withOpacity(0.1),
          child: Stack(
            children: [
              // Decorative background pattern
              Positioned(
                right: -30,
                top: -30,
                child: Container(
                  width: 120,
                  height: 120,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: Colors.white.withOpacity(0.1),
                  ),
                ),
              ),
              Positioned(
                right: -50,
                bottom: -40,
                child: Container(
                  width: 100,
                  height: 100,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: Colors.white.withOpacity(0.08),
                  ),
                ),
              ),
              // Main content
              Padding(
                padding: EdgeInsets.all(IOSSpacing.lg),
                child: Row(
                  children: [
                    // Avatar with enhanced design
                    Container(
                      width: 60,
                      height: 60,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: Colors.white,
                        boxShadow: [
                          BoxShadow(
                            color:
                                Theme.of(context).brightness == Brightness.dark
                                    ? Colors.black.withOpacity(0.5)
                                    : Colors.black.withOpacity(0.2),
                            blurRadius: 12,
                            spreadRadius: 2,
                            offset: const Offset(0, 4),
                          ),
                        ],
                      ),
                      child: Container(
                        margin: EdgeInsets.all(2),
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          gradient: LinearGradient(
                            begin: Alignment.topLeft,
                            end: Alignment.bottomRight,
                            colors: [
                              primaryColor,
                              primaryColor.withOpacity(0.8),
                            ],
                          ),
                        ),
                        child: Center(
                          child: Text(
                            initial,
                            style: IOSTextStyle.title1(context).copyWith(
                              color: Colors.white,
                              fontWeight: FontWeight.bold,
                              letterSpacing: 0.5,
                            ),
                          ),
                        ),
                      ),
                    ),
                    SizedBox(width: IOSSpacing.md),
                    // User info
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            displayName.isNotEmpty ? displayName : email,
                            style: IOSTextStyle.title3(context).copyWith(
                              fontWeight: FontWeight.bold,
                              color: Colors.white,
                              shadows: [
                                Shadow(
                                  color: Theme.of(context).brightness ==
                                          Brightness.dark
                                      ? Colors.black.withOpacity(0.6)
                                      : Colors.black26,
                                  blurRadius: 4,
                                ),
                              ],
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          if (title != null && title.isNotEmpty) ...[
                            SizedBox(height: IOSSpacing.xs + 2),
                            Container(
                              padding: EdgeInsets.symmetric(
                                horizontal: IOSSpacing.sm + 2,
                                vertical: IOSSpacing.xs,
                              ),
                              decoration: BoxDecoration(
                                color: Colors.white.withOpacity(0.25),
                                borderRadius: BorderRadius.circular(12),
                                border: Border.all(
                                  color: Colors.white.withOpacity(0.3),
                                  width: 1,
                                ),
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(
                                    Icons.work_outline,
                                    size: 14,
                                    color: Colors.white.withOpacity(0.9),
                                  ),
                                  SizedBox(width: IOSSpacing.xs + 2),
                                  Flexible(
                                    child: Text(
                                      title,
                                      style: IOSTextStyle.caption1(context).copyWith(
                                        fontWeight: FontWeight.w600,
                                        color: Colors.white.withOpacity(0.95),
                                      ),
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                          SizedBox(height: IOSSpacing.sm),
                          // Role badge
                          Container(
                            padding: EdgeInsets.symmetric(
                              horizontal: IOSSpacing.sm + 2,
                              vertical: IOSSpacing.xs + 1,
                            ),
                            decoration: BoxDecoration(
                              color: Colors.white.withOpacity(0.25),
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(
                                color: Colors.white.withOpacity(0.3),
                                width: 1,
                              ),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  Icons.verified_user_outlined,
                                  size: 14,
                                  color: Colors.white.withOpacity(0.9),
                                ),
                                SizedBox(width: IOSSpacing.xs + 2),
                                Text(
                                  getRoleDisplayName(role),
                                  style: IOSTextStyle.caption2(context).copyWith(
                                    fontWeight: FontWeight.w600,
                                    color: Colors.white.withOpacity(0.95),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                    // Settings icon
                    Material(
                      color: Colors.transparent,
                      child: InkWell(
                        onTap: () {
                          Navigator.of(context).pushNamed(AppRoutes.settings);
                        },
                        customBorder: const CircleBorder(),
                        child: Container(
                          padding: EdgeInsets.all(IOSSpacing.sm),
                          decoration: BoxDecoration(
                            color: Colors.white.withOpacity(0.2),
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: Colors.white.withOpacity(0.3),
                              width: 1,
                            ),
                          ),
                          child: Icon(
                            Icons.settings_outlined,
                            color: Colors.white,
                            size: 20,
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
      ),
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
            padding: EdgeInsets.all(IOSSpacing.sm),
            decoration: BoxDecoration(
              color: color.withOpacity(0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(
              icon,
              color: color,
              size: 16,
            ),
          ),
          SizedBox(width: IOSSpacing.sm),
          Text(
            title,
            style: IOSTextStyle.footnote(context).copyWith(
              fontWeight: FontWeight.w600,
              color: theme.colorScheme.onSurface.withOpacity(0.6),
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
    required Color iconColor,
  }) {
    final theme = Theme.of(context);
    return IOSListTile(
      leading: Container(
        padding: EdgeInsets.all(IOSSpacing.sm + 2),
        decoration: BoxDecoration(
          color: iconColor.withOpacity(0.1),
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
        color: theme.colorScheme.onSurface.withOpacity(0.3),
        size: 13,
      ),
      onTap: () {
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
