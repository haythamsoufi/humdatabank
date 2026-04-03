import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/shared/auth_provider.dart';
import '../models/shared/user.dart';
import '../config/routes.dart';
import '../utils/constants.dart';

class AdminDrawer extends StatelessWidget {
  const AdminDrawer({super.key});

  bool _isAdmin(User? user) {
    if (user == null) return false;
    return user.role == 'admin' || user.role == 'system_manager';
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthProvider>(
      builder: (context, authProvider, child) {
        final user = authProvider.user;

        // Only show drawer for admins
        if (!_isAdmin(user)) {
          return const SizedBox.shrink();
        }

        return Drawer(
          child: ListView(
            padding: EdgeInsets.zero,
            children: [
              // Header
              DrawerHeader(
                decoration: BoxDecoration(
                  color: Color(AppConstants.ifrcRed),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    const Text(
                      'Admin Panel',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 24,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    if (user != null) ...[
                      const SizedBox(height: 8),
                      Text(
                        user.displayName,
                        style: const TextStyle(
                          color: Colors.white70,
                          fontSize: 14,
                        ),
                      ),
                    ],
                  ],
                ),
              ),

              // General Section
              _buildSectionHeader('General'),
              _buildDrawerItem(
                context: context,
                icon: Icons.home,
                title: 'Dashboard',
                route: AppRoutes.dashboard,
              ),
              _buildDrawerItem(
                context: context,
                icon: Icons.dashboard,
                title: 'Admin Dashboard',
                webviewRoute: '/admin/dashboard',
              ),
              _buildDrawerItem(
                context: context,
                icon: Icons.description,
                title: 'Document Management',
                webviewRoute: '/admin/documents',
              ),
              _buildDrawerItem(
                context: context,
                icon: Icons.translate,
                title: 'Translation Management',
                webviewRoute: '/admin/translations',
              ),
              if (user?.role == 'system_manager')
                _buildDrawerItem(
                  context: context,
                  icon: Icons.settings,
                  title: 'System Configuration',
                  webviewRoute: '/admin/settings',
                ),

              const Divider(),

              // Form & Data Management Section
              _buildSectionHeader('Form & Data Management'),
              _buildDrawerItem(
                context: context,
                icon: Icons.article,
                title: 'Manage Templates',
                route: AppRoutes.templates,
              ),
              _buildDrawerItem(
                context: context,
                icon: Icons.assignment,
                title: 'Manage Assignments',
                route: AppRoutes.assignments,
              ),

              const Divider(),

              // Website Management Section
              _buildSectionHeader('Website Management'),
              _buildDrawerItem(
                context: context,
                icon: Icons.folder_open,
                title: 'Manage Resources',
                webviewRoute: '/admin/resources',
              ),

              const Divider(),

              // Reference Data Section
              _buildSectionHeader('Reference Data'),
              _buildDrawerItem(
                context: context,
                icon: Icons.account_tree,
                title: 'Organizational Structure',
                webviewRoute: '/admin/organization',
              ),
              _buildDrawerItem(
                context: context,
                icon: Icons.storage,
                title: 'Indicator Bank',
                webviewRoute: '/admin/indicator-bank',
              ),

              const Divider(),

              // Analytics & Monitoring Section
              _buildSectionHeader('Analytics & Monitoring'),
              _buildDrawerItem(
                context: context,
                icon: Icons.bar_chart,
                title: 'User Analytics',
                webviewRoute: '/admin/analytics',
              ),
              _buildDrawerItem(
                context: context,
                icon: Icons.history,
                title: 'Audit Trail',
                webviewRoute: '/admin/audit-trail',
              ),

              const Divider(),

              // Footer
              const Padding(
                padding: EdgeInsets.all(16.0),
                child: Text(
                  'Built by Haytham Alsoufi,\nvolunteer of Syrian Arab Red Crescent',
                  style: TextStyle(
                    fontSize: 12,
                    color: Color(AppConstants.textSecondary),
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildSectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
      child: Text(
        title,
        style: const TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: Color(AppConstants.textSecondary),
          letterSpacing: 0.5,
        ),
      ),
    );
  }

  Widget _buildDrawerItem({
    required BuildContext context,
    required IconData icon,
    required String title,
    String? route,
    String? webviewRoute,
  }) {
    return ListTile(
      leading: Icon(icon, color: Color(AppConstants.ifrcRed)),
      title: Text(title),
      onTap: () {
        Navigator.pop(context); // Close drawer

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
