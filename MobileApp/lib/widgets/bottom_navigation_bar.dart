import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/shared/notification_provider.dart';
import '../providers/shared/auth_provider.dart';
import '../utils/constants.dart';
import '../utils/theme_extensions.dart';
import '../utils/navigation_helper.dart';

class AppBottomNavigationBar extends StatelessWidget {
  final int currentIndex;
  final Function(int)? onTap;
  final bool? isFocalPoint;
  final bool useDefaultNavigation;

  const AppBottomNavigationBar({
    super.key,
    required this.currentIndex,
    this.onTap,
    this.isFocalPoint,
    this.useDefaultNavigation = true,
  });

  void _handleTap(BuildContext context, int index) {
    if (onTap != null) {
      onTap!(index);
    } else if (useDefaultNavigation) {
      NavigationHelper.navigateToMainTab(context, index);
    }
  }

  bool _isAdmin(context) {
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    final user = authProvider.user;
    return user != null &&
        (user.role == 'admin' || user.role == 'system_manager');
  }

  bool _isAuthenticated(context) {
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    return authProvider.isAuthenticated;
  }

  bool _isFocalPoint(context) {
    if (isFocalPoint != null) {
      return isFocalPoint!;
    }
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    final user = authProvider.user;
    return user != null && user.role == 'focal_point';
  }

  @override
  Widget build(BuildContext context) {
    final isAdmin = _isAdmin(context);
    final isAuthenticated = _isAuthenticated(context);
    final isFocalPoint = _isFocalPoint(context);

    // For admin: 0: Notifications, 1: Dashboard, 2: Home, 3: Admin Dashboard, 4: Admin
    // For authenticated non-admin (focal point): 0: Notifications, 1: Dashboard, 2: Home, 3: Disaggregation Analysis, 4: Settings
    // For authenticated non-admin (other): 0: Resources, 1: Dashboard, 2: Home, 3: Disaggregation Analysis, 4: Settings
    // For non-authenticated: 0: Resources, 1: Indicator Bank, 2: Home, 3: Disaggregation Analysis, 4: Settings
    final int itemCount = isAdmin ? 5 : (isAuthenticated ? 5 : 5);
    final int safeIndex = currentIndex < 0
        ? 0
        : (currentIndex >= itemCount ? itemCount - 1 : currentIndex);

    return Container(
      decoration: BoxDecoration(
        color: context.surfaceColor,
        border: Border(
          top: BorderSide(
            color: context.borderColor,
            width: 0.5,
          ),
        ),
      ),
      child: SafeArea(
        top: false,
        child: Container(
          height: 50,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                if (isAdmin) ...[
                  // Notifications (index 0) - Admin only
                  Flexible(
                    flex: 1,
                    child: _buildNavItem(
                      context: context,
                      index: 0,
                      safeIndex: safeIndex,
                      icon: Icons.notifications_outlined,
                      activeIcon: Icons.notifications,
                      label: 'Notifications',
                      isHome: false,
                      onTap: () => _handleTap(context, 0),
                    ),
                  ),
                  // Dashboard (index 1)
                  Flexible(
                    flex: 1,
                    child: _buildNavItem(
                      context: context,
                      index: 1,
                      safeIndex: safeIndex,
                      icon: Icons.dashboard_outlined,
                      activeIcon: Icons.dashboard,
                      label: 'Dashboard',
                      isHome: false,
                      onTap: () => _handleTap(context, 1),
                    ),
                  ),
                ] else if (isAuthenticated) ...[
                  // For focal points: Notifications (index 0), for other authenticated users: Resources (index 0)
                  Flexible(
                    flex: 1,
                    child: _buildNavItem(
                      context: context,
                      index: 0,
                      safeIndex: safeIndex,
                      icon: isFocalPoint
                          ? Icons.notifications_outlined
                          : Icons.folder_outlined,
                      activeIcon:
                          isFocalPoint ? Icons.notifications : Icons.folder,
                      label: isFocalPoint ? 'Notifications' : 'Resources',
                      isHome: false,
                      onTap: () => _handleTap(context, 0),
                    ),
                  ),
                ],
                // Middle button - fixed position
                // Admin: index 2 (Home), Authenticated non-admin: index 1 (Dashboard), Non-authenticated: index 0 (Resources)
                if (isAdmin) ...[
                  // Home button for admin (stays in middle)
                  Flexible(
                    flex: 1,
                    child: _buildNavItem(
                      context: context,
                      index: 2,
                      safeIndex: safeIndex,
                      icon: Icons.home_outlined,
                      activeIcon: Icons.home,
                      label: 'Home',
                      isHome: true,
                      onTap: () => _handleTap(context, 2),
                    ),
                  ),
                ] else ...[
                  // For non-admin: Dashboard in middle if authenticated, Resources if not authenticated
                  Flexible(
                    flex: 1,
                    child: _buildNavItem(
                      context: context,
                      index: isAuthenticated ? 1 : 0,
                      safeIndex: safeIndex,
                      icon: isAuthenticated
                          ? Icons.dashboard_outlined
                          : Icons.folder_outlined,
                      activeIcon:
                          isAuthenticated ? Icons.dashboard : Icons.folder,
                      label: isAuthenticated ? 'Dashboard' : 'Resources',
                      isHome: false,
                      onTap: () => _handleTap(context, isAuthenticated ? 1 : 0),
                    ),
                  ),
                ],
                // Conditional buttons based on admin status
                if (isAdmin) ...[
                  // Admin Dashboard (index 3)
                  Flexible(
                    flex: 1,
                    child: _buildNavItem(
                      context: context,
                      index: 3,
                      safeIndex: safeIndex,
                      icon: Icons.dashboard_outlined,
                      activeIcon: Icons.dashboard,
                      label: 'Admin Dash',
                      isHome: false,
                      onTap: () => _handleTap(context, 3),
                    ),
                  ),
                  // Admin (index 4)
                  Flexible(
                    flex: 1,
                    child: _buildNavItem(
                      context: context,
                      index: 4,
                      safeIndex: safeIndex,
                      icon: Icons.admin_panel_settings_outlined,
                      activeIcon: Icons.admin_panel_settings,
                      label: 'Admin',
                      isHome: false,
                      onTap: () => _handleTap(context, 4),
                    ),
                  ),
                ] else ...[
                  // For non-admin users (authenticated or not)
                  // If authenticated: indices 2, 3, 4 (Home, Analysis, Settings) - no Indicators
                  // If not authenticated: indices 1, 2, 3, 4 (Indicators, Home, Analysis, Settings)
                  if (!isAuthenticated) ...[
                    // Indicators - only for non-authenticated users
                    Flexible(
                      flex: 1,
                      child: _buildNavItem(
                        context: context,
                        index: 1,
                        safeIndex: safeIndex,
                        icon: Icons.library_books_outlined,
                        activeIcon: Icons.library_books,
                      label: 'Indicators',
                      isHome: false,
                      onTap: () => _handleTap(context, 1),
                      ),
                    ),
                  ],
                  // Home
                  Flexible(
                    flex: 1,
                    child: _buildNavItem(
                      context: context,
                      index: isAuthenticated ? 2 : 2,
                      safeIndex: safeIndex,
                      icon: Icons.home_outlined,
                      activeIcon: Icons.home,
                      label: 'Home',
                      isHome: true,
                      onTap: () => _handleTap(context, isAuthenticated ? 2 : 2),
                    ),
                  ),
                  // Disaggregation Analysis
                  Flexible(
                    flex: 1,
                    child: _buildNavItem(
                      context: context,
                      index: isAuthenticated ? 3 : 3,
                      safeIndex: safeIndex,
                      icon: Icons.analytics_outlined,
                      activeIcon: Icons.analytics,
                      label: 'Analysis',
                      isHome: false,
                      onTap: () => _handleTap(context, isAuthenticated ? 3 : 3),
                    ),
                  ),
                  // Settings
                  Flexible(
                    flex: 1,
                    child: _buildNavItem(
                      context: context,
                      index: isAuthenticated ? 4 : 4,
                      safeIndex: safeIndex,
                      icon: Icons.settings_outlined,
                      activeIcon: Icons.settings,
                      label: 'Settings',
                      isHome: false,
                      onTap: () => _handleTap(context, isAuthenticated ? 4 : 4),
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

  Widget _buildNavItem({
    required BuildContext context,
    required int index,
    required int safeIndex,
    required IconData icon,
    required IconData activeIcon,
    required String label,
    required bool isHome,
    required VoidCallback onTap,
  }) {
    final isSelected = safeIndex == index;
    final isNotifications = label == 'Notifications';

    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: SizedBox.expand(
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 4),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (isNotifications)
                // Notifications with badge
                Consumer<NotificationProvider>(
                  builder: (context, provider, child) {
                    return Stack(
                      clipBehavior: Clip.none,
                      children: [
                        Icon(
                          isSelected ? activeIcon : icon,
                          size: 24,
                          color: context.iconColor,
                        ),
                        if (provider.unreadCount > 0)
                          Positioned(
                            right: -6,
                            top: -6,
                            child: Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 4, vertical: 2),
                              decoration: const BoxDecoration(
                                color: Color(0xFFED4956),
                                shape: BoxShape.circle,
                              ),
                              constraints: const BoxConstraints(
                                minWidth: 16,
                                minHeight: 16,
                              ),
                              child: Center(
                                child: Text(
                                  provider.unreadCount > 9
                                      ? '9+'
                                      : '${provider.unreadCount}',
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ),
                            ),
                          ),
                      ],
                    );
                  },
                )
              else
                Container(
                  padding: const EdgeInsets.all(8),
                  child: Icon(
                    isSelected ? activeIcon : icon,
                    size: 24,
                    color: context.iconColor,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
