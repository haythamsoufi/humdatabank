import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../config/routes.dart';
import '../providers/shared/auth_provider.dart';

/// Utility class for handling navigation to MainNavigationScreen with tab switching
/// This ensures consistent behavior when navigating from nested screens
class NavigationHelper {
  /// Navigate to MainNavigationScreen with the specified tab index
  /// This will pop all routes until MainNavigationScreen and then navigate to the selected tab
  ///
  /// [context] - The build context
  /// [tabIndex] - The tab index to navigate to (0-4)
  ///
  /// Tab indices:
  /// - For admin: 0: Notifications, 1: Dashboard, 2: Home, 3: Admin Dashboard, 4: Admin
  /// - For authenticated non-admin (focal point): 0: Notifications, 1: Dashboard, 2: Home, 3: Disaggregation Analysis, 4: Settings
  /// - For authenticated non-admin (other): 0: Resources, 1: Dashboard, 2: Home, 3: Disaggregation Analysis, 4: Settings
  /// - For non-authenticated: 0: Resources, 1: Indicator Bank, 2: Home, 3: Disaggregation Analysis, 4: Settings
  static void navigateToMainTab(BuildContext context, int tabIndex) {
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    final user = authProvider.user;
    final isAdmin = user != null &&
        (user.role == 'admin' || user.role == 'system_manager');
    final isAuthenticated = authProvider.isAuthenticated;
    final isFocalPoint = user != null && user.role == 'focal_point';

    // Pop all routes until we reach MainNavigationScreen
    // MainNavigationScreen is created via AppRoutes.dashboard or AppRoutes.notifications
    Navigator.of(context).popUntil((route) {
      final routeName = route.settings.name;
      return route.isFirst ||
          routeName == AppRoutes.dashboard ||
          routeName == AppRoutes.notifications;
    });

    // Navigate to MainNavigationScreen with the selected tab index
    // Use notifications route for notifications tab (index 0) if user has access
    // Otherwise use dashboard route for all other tabs
    if (tabIndex == 0 && (isAdmin || isFocalPoint)) {
      // Navigate to notifications tab
      Navigator.of(context).pushReplacementNamed(
        AppRoutes.notifications,
        arguments: tabIndex,
      );
    } else {
      // Navigate to dashboard route with the selected tab index
      Navigator.of(context).pushReplacementNamed(
        AppRoutes.dashboard,
        arguments: tabIndex,
      );
    }
  }
}
